from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import sys
from ctypes import wintypes
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from PIL import Image
from PyQt6.QtCore import (
    QAbstractNativeEventFilter,
    QObject,
    QRect,
    QThread,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QGuiApplication, QIcon, QImage, QKeySequence, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from config_manager import (
    ApiConfig,
    AppConfig,
    ConfigManager,
    DEFAULT_OCR_PROMPT_TEMPLATE,
    DEFAULT_REFRESH_SHORTCUT,
    DEFAULT_TRANSLATION_PROMPT_TEMPLATE,
)
from screenshot_tool import (
    CaptureResult,
    ScreenCaptureOverlay,
    SelectionFrameOverlay,
    capture_region,
)
from ui_windows import FloatingSubtitleWindow, MainWindow


class ApiWorker(QObject):
    """
    通用 API 调用工作对象：
    - OCR：图片 + OCR Prompt
    - 翻译：文本 + 翻译 Prompt
    """

    partial_text = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        api_config: ApiConfig,
        prompt: str,
        *,
        image_base64: str | None = None,
        text_input: str | None = None,
    ) -> None:
        super().__init__()
        self.api_config = api_config
        self.prompt = prompt
        self.image_base64 = image_base64
        self.text_input = text_input

    def run(self) -> None:
        try:
            payload = self._build_payload(
                model_name=self.api_config.model_name,
                prompt=self.prompt,
                image_base64=self.image_base64,
                text_input=self.text_input,
            )
            headers = self._build_headers()

            response = requests.post(
                self.api_config.base_url,
                headers=headers,
                json=payload,
                timeout=60,
                stream=True,
            )
            response.raise_for_status()

            result_text = self._extract_response_text(
                response,
                progress_callback=self.partial_text.emit,
            )
            if not result_text.strip():
                raise ValueError("接口返回成功，但未解析到有效文本内容。")

            self.finished.emit(result_text.strip())

        except requests.exceptions.Timeout:
            self.error.emit("请求超时，请检查网络状态或稍后重试。")
        except requests.exceptions.HTTPError as exc:
            detail = self._extract_error_detail(exc.response)
            self.error.emit(f"接口请求失败：{detail}")
        except requests.exceptions.RequestException as exc:
            self.error.emit(f"网络请求异常：{exc}")
        except ValueError as exc:
            self.error.emit(f"数据处理失败：{exc}")
        except Exception as exc:
            self.error.emit(f"发生未知错误：{exc}")

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_config.api_key:
            headers["Authorization"] = f"Bearer {self.api_config.api_key}"
        return headers

    @staticmethod
    def _build_payload(
        model_name: str,
        prompt: str,
        *,
        image_base64: str | None = None,
        text_input: str | None = None,
    ) -> dict[str, Any]:
        if image_base64:
            content: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}",
                    },
                },
            ]
        else:
            full_text = prompt
            if text_input:
                full_text = f"{prompt}\n\n{text_input}"
            content = [
                {
                    "type": "text",
                    "text": full_text,
                }
            ]

        return {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "temperature": 0.2,
            "stream": True,
            "stream_options": {
                "include_usage": True,
            },
        }

    @classmethod
    def _extract_response_text(
        cls,
        response: requests.Response,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        content_type = response.headers.get("Content-Type", "").lower()

        if "text/event-stream" in content_type:
            streamed_text = cls._extract_text_from_sse(
                response,
                progress_callback=progress_callback,
            )
            if streamed_text:
                return streamed_text

        data = response.json()
        return cls._extract_text_from_response(data)

    @classmethod
    def _extract_text_from_sse(
        cls,
        response: requests.Response,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        text_parts: list[str] = []

        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue

            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue

            data_str = line[5:].strip()
            if not data_str or data_str == "[DONE]":
                continue

            try:
                chunk = json.loads(data_str)
            except Exception:
                continue

            choices = chunk.get("choices")
            if not isinstance(choices, list):
                continue

            for choice in choices:
                if not isinstance(choice, dict):
                    continue

                delta = choice.get("delta", {})
                if not isinstance(delta, dict):
                    continue

                content = delta.get("content")
                extracted = cls._extract_text_from_content(content)
                if extracted:
                    text_parts.append(extracted)
                    if progress_callback is not None:
                        progress_callback("".join(text_parts).strip())

        return "".join(text_parts).strip()

    @classmethod
    def _extract_text_from_response(cls, data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]

            if isinstance(first_choice, dict):
                message = first_choice.get("message", {})
                if isinstance(message, dict):
                    content = message.get("content")
                    extracted = cls._extract_text_from_content(content)
                    if extracted:
                        return extracted

                delta = first_choice.get("delta", {})
                if isinstance(delta, dict):
                    content = delta.get("content")
                    extracted = cls._extract_text_from_content(content)
                    if extracted:
                        return extracted

                direct_text = first_choice.get("text")
                if isinstance(direct_text, str) and direct_text.strip():
                    return direct_text.strip()

        for key in ("output_text", "text", "translated_text", "translation"):
            value = data.get(key)
            if (
                isinstance(value, str)
                and value.strip()
                and not cls._looks_like_response_id(value)
            ):
                return value.strip()

        candidates = data.get("candidates")
        if isinstance(candidates, list) and candidates:
            text_parts: list[str] = []
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue

                content = candidate.get("content", {})
                if not isinstance(content, dict):
                    continue

                parts = content.get("parts", [])
                if isinstance(parts, list):
                    for part in parts:
                        if isinstance(part, dict):
                            text_value = part.get("text")
                            if isinstance(text_value, str) and text_value.strip():
                                text_parts.append(text_value.strip())

            if text_parts:
                return "\n".join(text_parts)

        fallback = cls._find_text_recursively(data)
        if fallback:
            return fallback

        raise ValueError("无法从响应 JSON 中提取文本结果。")

    @staticmethod
    def _extract_text_from_content(content: Any) -> str:
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str) and item.strip():
                    text_parts.append(item.strip())
                    continue

                if not isinstance(item, dict):
                    continue

                for key in ("text", "content", "value", "output_text"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        text_parts.append(value.strip())
                        break

            if text_parts:
                return "\n".join(text_parts)

        if isinstance(content, dict):
            for key in ("text", "content", "value", "output_text"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    @classmethod
    def _find_text_recursively(cls, obj: Any) -> str:
        preferred_keys = {
            "text",
            "content",
            "output_text",
            "translation",
            "translated_text",
            "value",
        }

        if isinstance(obj, dict):
            for key in preferred_keys:
                value = obj.get(key)
                extracted = cls._extract_text_from_content(value)
                if extracted and not cls._looks_like_response_id(extracted):
                    return extracted

            for value in obj.values():
                extracted = cls._find_text_recursively(value)
                if extracted:
                    return extracted

        elif isinstance(obj, list):
            for item in obj:
                extracted = cls._find_text_recursively(item)
                if extracted:
                    return extracted

        elif (
            isinstance(obj, str)
            and obj.strip()
            and not cls._looks_like_response_id(obj)
        ):
            return obj.strip()

        return ""

    @staticmethod
    def _looks_like_response_id(text: str) -> bool:
        value = text.strip()
        id_prefixes = ("resp_", "req_", "msg_", "chatcmpl-", "cmpl-", "run_")
        if value.startswith(id_prefixes):
            return True

        compact = value.replace("_", "").replace("-", "")
        if (
            len(value) >= 24
            and compact.isalnum()
            and " " not in value
            and "\n" not in value
        ):
            return True

        return False

    @staticmethod
    def _extract_error_detail(response: Optional[requests.Response]) -> str:
        if response is None:
            return "HTTP 错误，且未收到响应内容。"

        try:
            data = response.json()
            if isinstance(data, dict):
                if "error" in data:
                    error_obj = data["error"]
                    if isinstance(error_obj, dict):
                        return str(error_obj.get("message", data))
                    return str(error_obj)
                return str(data)
        except Exception:
            pass

        text = response.text.strip()
        return text or f"HTTP {response.status_code}"


class GlobalHotkeyManager(QAbstractNativeEventFilter):
    HOTKEY_ID = 1001
    WM_HOTKEY = 0x0312

    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback
        self._registered = False
        self._current_shortcut = ""

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0

        msg = wintypes.MSG.from_address(int(message))
        if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
            self.callback()
            return True, 0

        return False, 0

    def register_shortcut(self, shortcut_text: str) -> None:
        self.unregister_shortcut()

        normalized = self._normalize_shortcut_text(shortcut_text)
        if not normalized:
            return

        modifier, vk = self._parse_qt_shortcut(normalized)
        user32 = ctypes.windll.user32
        success = user32.RegisterHotKey(None, self.HOTKEY_ID, modifier, vk)
        if not success:
            raise RuntimeError(
                f"全局快捷键注册失败：{normalized}。该快捷键可能已被其他程序占用。"
            )

        self._registered = True
        self._current_shortcut = normalized

    def unregister_shortcut(self) -> None:
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self._registered = False
            self._current_shortcut = ""

    @staticmethod
    def _normalize_shortcut_text(shortcut_text: str) -> str:
        return shortcut_text.split(",", 1)[0].strip()

    @classmethod
    def _parse_qt_shortcut(cls, shortcut_text: str) -> tuple[int, int]:
        parts = [part.strip() for part in shortcut_text.split("+") if part.strip()]
        if not parts:
            raise ValueError("快捷键不能为空。")

        modifier_map = {
            "CTRL": 0x0002,
            "CONTROL": 0x0002,
            "ALT": 0x0001,
            "SHIFT": 0x0004,
            "META": 0x0008,
            "WIN": 0x0008,
        }

        modifier = 0
        key_part = ""

        for part in parts:
            upper = part.upper()
            if upper in modifier_map:
                modifier |= modifier_map[upper]
            else:
                key_part = upper

        if not key_part:
            raise ValueError("快捷键必须包含一个主键。")

        vk = cls._key_to_vk(key_part)
        if vk is None:
            raise ValueError(f"暂不支持的快捷键主键：{key_part}")

        return modifier, vk

    @staticmethod
    def _key_to_vk(key_part: str) -> Optional[int]:
        if len(key_part) == 1:
            ch = key_part.upper()
            if "A" <= ch <= "Z" or "0" <= ch <= "9":
                return ord(ch)

        function_keys = {f"F{i}": 0x6F + i for i in range(1, 25)}
        if key_part in function_keys:
            return function_keys[key_part]

        extra_keys = {
            "SPACE": 0x20,
            "TAB": 0x09,
            "BACKSPACE": 0x08,
            "ESC": 0x1B,
            "ESCAPE": 0x1B,
            "ENTER": 0x0D,
            "RETURN": 0x0D,
            "LEFT": 0x25,
            "UP": 0x26,
            "RIGHT": 0x27,
            "DOWN": 0x28,
            "HOME": 0x24,
            "END": 0x23,
            "PAGEUP": 0x21,
            "PAGEDOWN": 0x22,
            "INSERT": 0x2D,
            "DELETE": 0x2E,
        }
        return extra_keys.get(key_part)


class AppController(QObject):
    """
    统一控制流程：
    截图/剪贴板图片 -> OCR / 翻译（按开关独立执行，可并行）
    """

    def __init__(self) -> None:
        super().__init__()
        self.config_manager = ConfigManager()
        self.main_window = MainWindow()
        self.floating_window = FloatingSubtitleWindow()
        self.capture_overlay = ScreenCaptureOverlay()
        self.selection_frame_overlay = SelectionFrameOverlay()

        self._current_capture: Optional[CaptureResult] = None
        self._last_capture_rect: Optional[QRect] = None
        self._selection_frame_visible = True
        self._request_threads: dict[str, QThread] = {}
        self._request_workers: dict[str, ApiWorker] = {}
        self._last_clipboard_image_hash: Optional[str] = None

        self._global_hotkey_manager = GlobalHotkeyManager(self.refresh_last_capture)
        self._is_quitting = False
        self._tray_icon: Optional[QSystemTrayIcon] = None
        self._tray_menu: Optional[QMenu] = None
        self._has_shown_tray_minimize_tip = False

        self._setup_windows()
        self._setup_system_tray()
        self._connect_signals()
        self._load_initial_config()

    def _setup_windows(self) -> None:
        app_icon = self._load_app_icon()
        if app_icon is not None:
            QApplication.instance().setWindowIcon(app_icon)
            self.main_window.setWindowIcon(app_icon)
            self.floating_window.setWindowIcon(app_icon)
            self.capture_overlay.setWindowIcon(app_icon)
            self.selection_frame_overlay.setWindowIcon(app_icon)

        self.main_window.show()
        self.floating_window.move(120, 120)
        self._set_floating_window_visible(True)

    def _setup_system_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_icon = None
            self._tray_menu = None
            return

        tray_icon = QSystemTrayIcon(self.main_window)
        icon = self.main_window.windowIcon()
        if not icon.isNull():
            tray_icon.setIcon(icon)

        tray_icon.setToolTip("OCR 与翻译助手")

        tray_menu = QMenu(self.main_window)
        restore_action = tray_menu.addAction("显示主窗口")
        restore_action.triggered.connect(self.restore_main_window_from_tray)

        hide_action = tray_menu.addAction("隐藏主窗口")
        hide_action.triggered.connect(self.hide_main_window_to_tray)

        tray_menu.addSeparator()
        exit_action = tray_menu.addAction("退出程序")
        exit_action.triggered.connect(self.request_exit_application)

        tray_icon.setContextMenu(tray_menu)
        tray_icon.activated.connect(self.on_tray_icon_activated)
        tray_icon.show()

        self._tray_icon = tray_icon
        self._tray_menu = tray_menu

    def _connect_signals(self) -> None:
        self.main_window.save_button.clicked.connect(self.save_config)
        self.main_window.capture_button.clicked.connect(self.start_capture)
        self.main_window.fetch_models_button.clicked.connect(self.fetch_models)
        self.main_window.add_api_profile_button.clicked.connect(self.create_api_profile)
        self.main_window.update_api_profile_button.clicked.connect(
            self.update_api_profile
        )
        self.main_window.delete_api_profile_button.clicked.connect(
            self.delete_api_profile
        )
        self.main_window.clipboard_button.toggled.connect(
            self.on_clipboard_monitor_toggled
        )
        self.main_window.display_toggle_button.toggled.connect(
            self.on_display_visibility_toggled
        )
        self.main_window.copy_ocr_button.clicked.connect(self.copy_ocr_result)
        self.main_window.closing.connect(self.on_main_window_closing)

        self.floating_window.display_toggle_requested.connect(
            self.on_display_toggle_requested_from_floating
        )
        self.floating_window.appearance_changed.connect(
            self.on_floating_appearance_changed
        )

        QApplication.clipboard().dataChanged.connect(self.on_clipboard_data_changed)

        self.capture_overlay.capture_completed.connect(self.on_capture_completed)
        self.capture_overlay.capture_canceled.connect(self.on_capture_canceled)
        self.selection_frame_overlay.region_moved.connect(
            self.on_selection_region_moved
        )
        self.selection_frame_overlay.refresh_requested.connect(
            self.refresh_last_capture
        )
        self.selection_frame_overlay.close_requested.connect(
            self.close_selection_translation_area
        )

    def _setup_shortcuts(self, shortcut_text: str) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self._global_hotkey_manager)

        self._global_hotkey_manager.unregister_shortcut()
        self._global_hotkey_manager.register_shortcut(shortcut_text)

        if app is not None:
            app.installNativeEventFilter(self._global_hotkey_manager)

    def _load_initial_config(self) -> None:
        config = self.config_manager.load()
        self.main_window.set_config(config)
        self.floating_window.apply_appearance_config(config)

        try:
            self._setup_shortcuts(config.refresh_shortcut)
        except Exception:
            config.refresh_shortcut = DEFAULT_REFRESH_SHORTCUT
            self.main_window.set_config(config)
            self.floating_window.apply_appearance_config(config)
            self._setup_shortcuts(config.refresh_shortcut)

    def _build_config_from_ui(self) -> AppConfig:
        config = self.main_window.get_config()

        for api_config in config.ocr_api_configs:
            api_config.base_url = self._normalize_base_url(api_config.base_url)

        for api_config in config.translation_api_configs:
            api_config.base_url = self._normalize_base_url(api_config.base_url)

        self.floating_window.fill_appearance_config(config)
        config.ensure_valid_state()
        return config

    def _persist_config_without_validation(self) -> AppConfig:
        config = self._build_config_from_ui()
        self.config_manager.save(config)
        self.main_window.set_config(config)
        self.floating_window.apply_appearance_config(config)
        return config

    def _validate_and_persist_config(
        self,
        *,
        allow_empty_api_for_save: bool,
    ) -> AppConfig:
        config = self._build_config_from_ui()
        self._validate_config(config, allow_empty_api_for_save=allow_empty_api_for_save)
        self.config_manager.save(config)
        self.main_window.set_config(config)
        self.floating_window.apply_appearance_config(config)
        return config

    def save_config(self) -> None:
        try:
            config = self._validate_and_persist_config(allow_empty_api_for_save=True)
            self._setup_shortcuts(config.refresh_shortcut)
            self._show_info("保存成功", "OCR 与翻译配置已成功保存到本地。")
        except Exception as exc:
            self._show_error("保存失败", str(exc))

    def create_api_profile(self) -> None:
        try:
            role = self.main_window.get_active_config_role()
            role_name = "OCR" if role == "ocr" else "翻译"
            self.main_window.create_api_profile()
            self._persist_config_without_validation()
            self._show_info("新增成功", f"已新增{role_name}配置。")
        except Exception as exc:
            self._show_error("新增配置失败", str(exc))

    def update_api_profile(self) -> None:
        try:
            role = self.main_window.get_active_config_role()
            role_name = "OCR" if role == "ocr" else "翻译"
            self.main_window.update_current_api_profile()
            self._persist_config_without_validation()
            self._show_info("更新成功", f"已更新当前{role_name}配置。")
        except Exception as exc:
            self._show_error("更新配置失败", str(exc))

    def delete_api_profile(self) -> None:
        try:
            role = self.main_window.get_active_config_role()
            role_name = "OCR" if role == "ocr" else "翻译"
            self.main_window.delete_current_api_profile()
            self._persist_config_without_validation()
            self._show_info("删除成功", f"已删除当前{role_name}配置。")
        except Exception as exc:
            self._show_error("删除配置失败", str(exc))

    def fetch_models(self) -> None:
        try:
            config = self._build_config_from_ui()
            role = self.main_window.get_active_config_role()
            api_config = (
                config.get_selected_ocr_api_config()
                if role == "ocr"
                else config.get_selected_translation_api_config()
            )
            models_url = self._normalize_models_url(api_config.base_url)

            if not models_url:
                raise ValueError("Base URL 不能为空。")

            if not (
                models_url.startswith("http://") or models_url.startswith("https://")
            ):
                raise ValueError(
                    "Base URL 格式不正确，必须以 http:// 或 https:// 开头。"
                )

            headers = {"Content-Type": "application/json"}
            if api_config.api_key:
                headers["Authorization"] = f"Bearer {api_config.api_key}"

            response = requests.get(models_url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()
            model_names = self._extract_model_names(data)
            if not model_names:
                raise ValueError("接口返回成功，但未解析到可用模型。")

            current_model = api_config.model_name
            self.main_window.model_name_combo.clear()
            self.main_window.model_name_combo.addItems(model_names)

            if current_model and current_model in model_names:
                self.main_window.model_name_combo.setCurrentText(current_model)
            else:
                self.main_window.model_name_combo.setCurrentText(model_names[0])

            role_name = "OCR" if role == "ocr" else "翻译"
            self._show_info(
                "获取成功",
                f"已从 {models_url} 获取到 {len(model_names)} 个{role_name}模型。",
            )
        except requests.exceptions.Timeout:
            self._show_error("获取模型失败", "请求超时，请检查网络状态或稍后重试。")
        except requests.exceptions.HTTPError as exc:
            detail = ApiWorker._extract_error_detail(exc.response)
            self._show_error("获取模型失败", f"接口请求失败：{detail}")
        except requests.exceptions.RequestException as exc:
            self._show_error("获取模型失败", f"网络请求异常：{exc}")
        except Exception as exc:
            self._show_error("获取模型失败", str(exc))

    def start_capture(self) -> None:
        try:
            if self._has_active_requests():
                raise ValueError("已有 OCR / 翻译任务正在处理中，请稍候。")

            self._validate_and_persist_config(allow_empty_api_for_save=False)
            self.selection_frame_overlay.hide()
            self.main_window.hide()
            self.capture_overlay.start_capture()
        except Exception as exc:
            self._show_error("无法开始截图", str(exc))

    def toggle_selection_frame_visibility(self) -> None:
        if self._last_capture_rect is None or self._last_capture_rect.isNull():
            self._show_error(
                "无法切换框选框", "暂无可显示的框选区域，请先执行一次框选截图。"
            )
            return

        if self._selection_frame_visible:
            self.close_selection_translation_area()
            return

        self._selection_frame_visible = True
        self.selection_frame_overlay.show_region(self._last_capture_rect)

    def close_selection_translation_area(self) -> None:
        self._selection_frame_visible = False
        self.selection_frame_overlay.hide()

    def on_capture_completed(self, result: object) -> None:
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()

        if not isinstance(result, CaptureResult):
            self._show_error("截图失败", "截图结果格式无效。")
            return

        self._last_capture_rect = result.rect.normalized()
        self._selection_frame_visible = True
        self.selection_frame_overlay.show_region(self._last_capture_rect)
        self._process_capture_result(result)

    def refresh_last_capture(self) -> None:
        try:
            if self._has_active_requests():
                self._show_error("任务进行中", "已有 OCR / 翻译任务正在处理中，请稍候。")
                return

            if self._last_capture_rect is None or self._last_capture_rect.isNull():
                raise ValueError("暂无可刷新的框选区域，请先执行一次框选截图。")

            target_rect = self._last_capture_rect.normalized()
            self.selection_frame_overlay.hide()
            QApplication.processEvents()

            result = capture_region(target_rect)
            if result is None:
                if self._selection_frame_visible:
                    self.selection_frame_overlay.show_region(target_rect)
                raise ValueError("刷新框选区域失败，请确认目标区域当前可正常截图。")

            if self._selection_frame_visible:
                self.selection_frame_overlay.show_region(target_rect)

            self._process_capture_result(result)
        except Exception as exc:
            self._show_error("刷新框选区域失败", str(exc))

    def _has_active_requests(self) -> bool:
        return bool(self._request_threads)

    def _cleanup_request(self, request_kind: str) -> None:
        thread = self._request_threads.pop(request_kind, None)
        worker = self._request_workers.pop(request_kind, None)

        if worker is not None:
            worker.deleteLater()

        if thread is not None:
            thread.deleteLater()

    def _process_capture_result(self, result: CaptureResult) -> None:
        self._current_capture = result
        self.main_window.update_preview(result.pixmap)

        try:
            image_base64 = self._image_to_base64(result.image)
            config = self._validate_and_persist_config(allow_empty_api_for_save=False)

            if not config.ocr_enabled and not config.translation_enabled:
                self.main_window.update_ocr_result("OCR 与翻译均已关闭。")
                return

            if config.ocr_enabled:
                self.main_window.update_ocr_result("正在执行 OCR 识别，请稍候...")
                ocr_config = config.get_selected_ocr_api_config()
                ocr_prompt = config.ocr_prompt_template or DEFAULT_OCR_PROMPT_TEMPLATE
                self._start_api_request(
                    "ocr",
                    ocr_config,
                    ocr_prompt,
                    image_base64=image_base64,
                )
            else:
                self.main_window.update_ocr_result("OCR 已关闭。")

            if config.translation_enabled:
                translation_config = config.get_selected_translation_api_config()
                translation_prompt = self._build_translation_prompt(config)
                self.floating_window.set_text("正在翻译，请稍候...")
                self._start_api_request(
                    "translation",
                    translation_config,
                    translation_prompt,
                    image_base64=image_base64,
                )
        except Exception as exc:
            self._show_error("图片处理失败", str(exc))

    def on_selection_region_moved(self, rect: QRect) -> None:
        self._last_capture_rect = rect.normalized()

    def on_capture_canceled(self) -> None:
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()

        if (
            self._selection_frame_visible
            and self._last_capture_rect is not None
            and not self._last_capture_rect.isNull()
        ):
            self.selection_frame_overlay.show_region(self._last_capture_rect)

    def on_main_window_closing(self, event: object) -> None:
        if self._is_quitting:
            return

        if self._tray_icon is None:
            self.shutdown_application()
            return

        if hasattr(event, "ignore"):
            event.ignore()

        self.hide_main_window_to_tray(
            show_message=not self._has_shown_tray_minimize_tip
        )

    def hide_main_window_to_tray(
        self,
        _checked: bool = False,
        *,
        show_message: bool = False,
    ) -> None:
        self.main_window.hide()

        if show_message and self._tray_icon is not None:
            self._tray_icon.showMessage(
                "OCR 与翻译助手",
                "主窗口已最小化到系统托盘，可通过托盘菜单恢复或退出程序。",
                QSystemTrayIcon.MessageIcon.Information,
                2800,
            )
            self._has_shown_tray_minimize_tip = True

    def restore_main_window_from_tray(self, _checked: bool = False) -> None:
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def on_tray_icon_activated(
        self,
        reason: QSystemTrayIcon.ActivationReason,
    ) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.restore_main_window_from_tray()

    def request_exit_application(self, _checked: bool = False) -> None:
        self.shutdown_application()

    def shutdown_application(self) -> None:
        if self._is_quitting:
            return

        self._is_quitting = True

        if self._tray_icon is not None:
            try:
                self._tray_icon.hide()
            except Exception:
                pass

        try:
            self._global_hotkey_manager.unregister_shortcut()
        except Exception:
            pass

        for widget in (
            self.floating_window,
            self.capture_overlay,
            self.selection_frame_overlay,
        ):
            try:
                widget.close()
            except Exception:
                pass

        app = QApplication.instance()
        if app is not None:
            app.quit()

    def on_clipboard_monitor_toggled(self, checked: bool) -> None:
        if checked:
            self.main_window.clipboard_button.setText("剪贴板自动处理：已开启")
            self.main_window.clipboard_button.setObjectName("PrimaryButton")
            self._refresh_button_style(self.main_window.clipboard_button)
            self.translate_clipboard_image(force=True, show_no_image_error=True)
            return

        self.main_window.clipboard_button.setText("剪贴板自动处理：已关闭")
        self.main_window.clipboard_button.setObjectName("SecondaryButton")
        self._refresh_button_style(self.main_window.clipboard_button)

    def on_display_visibility_toggled(self, checked: bool) -> None:
        self._set_floating_window_visible(checked)

    def copy_ocr_result(self) -> None:
        text = self.main_window.get_ocr_result_text()
        if not text:
            self._show_info("复制提示", "当前没有可复制的结果。")
            return

        QApplication.clipboard().setText(text)
        self._show_info("复制成功", "OCR 结果已复制到剪贴板。")

    def on_display_toggle_requested_from_floating(self) -> None:
        self.main_window.display_toggle_button.toggle()

    def on_floating_appearance_changed(self) -> None:
        try:
            self._persist_config_without_validation()
        except Exception as exc:
            self._show_error("保存展示区样式失败", str(exc))

    def _set_floating_window_visible(self, is_visible: bool) -> None:
        if is_visible:
            self.floating_window.show()
            self.floating_window.raise_()
        else:
            self.floating_window.hide()

        self.main_window.set_display_visible(is_visible)
        self.floating_window.set_display_toggle_text(is_visible)

    def on_clipboard_data_changed(self) -> None:
        if not self.main_window.clipboard_button.isChecked():
            return

        self.translate_clipboard_image(force=False, show_no_image_error=False)

    def translate_clipboard_image(
        self,
        force: bool = False,
        show_no_image_error: bool = True,
    ) -> None:
        try:
            if self._has_active_requests():
                return

            config = self._validate_and_persist_config(allow_empty_api_for_save=False)
            pil_image, pixmap = self._get_image_from_clipboard()
            image_base64 = self._image_to_base64(pil_image)
            image_hash = hashlib.sha256(image_base64.encode("utf-8")).hexdigest()

            if not force and image_hash == self._last_clipboard_image_hash:
                return

            self._last_clipboard_image_hash = image_hash
            self.main_window.update_preview(pixmap)

            if not config.ocr_enabled and not config.translation_enabled:
                self.main_window.update_ocr_result("OCR 与翻译均已关闭。")
                return

            if config.ocr_enabled:
                self.main_window.update_ocr_result("检测到新的剪贴板图片，正在执行 OCR 识别...")
                ocr_config = config.get_selected_ocr_api_config()
                ocr_prompt = config.ocr_prompt_template or DEFAULT_OCR_PROMPT_TEMPLATE
                self._start_api_request(
                    "ocr",
                    ocr_config,
                    ocr_prompt,
                    image_base64=image_base64,
                )
            else:
                self.main_window.update_ocr_result("OCR 已关闭。")

            if config.translation_enabled:
                translation_config = config.get_selected_translation_api_config()
                translation_prompt = self._build_translation_prompt(config)
                self.floating_window.set_text("正在翻译，请稍候...")
                self._start_api_request(
                    "translation",
                    translation_config,
                    translation_prompt,
                    image_base64=image_base64,
                )
        except Exception as exc:
            if "剪贴板中未检测到图片" in str(exc):
                if not show_no_image_error:
                    return
                self._show_info("剪贴板提示", "剪贴板未检测到图片。")
                return
            self._show_error("剪贴板处理失败", str(exc))

    def _start_api_request(
        self,
        request_kind: str,
        api_config: ApiConfig,
        prompt: str,
        *,
        image_base64: str | None = None,
        text_input: str | None = None,
    ) -> None:
        if request_kind in self._request_threads:
            return

        thread = QThread()
        worker = ApiWorker(
            api_config,
            prompt,
            image_base64=image_base64,
            text_input=text_input,
        )
        worker.moveToThread(thread)

        self._request_threads[request_kind] = thread
        self._request_workers[request_kind] = worker

        thread.started.connect(worker.run)
        worker.partial_text.connect(
            lambda text, kind=request_kind: self.on_api_partial_text(kind, text)
        )
        worker.finished.connect(
            lambda text, kind=request_kind: self.on_api_success(kind, text)
        )
        worker.error.connect(
            lambda message, kind=request_kind: self.on_api_error(kind, message)
        )
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(
            lambda kind=request_kind: self._cleanup_request(kind)
        )
        thread.start()

    def on_api_partial_text(self, request_kind: str, text: str) -> None:
        preview_text = text.strip()
        if request_kind == "ocr":
            self.main_window.update_ocr_result(
                preview_text or "正在执行 OCR 识别，请稍候..."
            )
            return

        if request_kind == "translation":
            self.floating_window.set_text(preview_text or "正在翻译，请稍候...")

    def on_api_success(self, request_kind: str, text: str) -> None:
        if request_kind == "ocr":
            self.main_window.update_ocr_result(text)
            return

        if request_kind == "translation":
            self.floating_window.set_text(text)

    def on_api_error(self, request_kind: str, message: str) -> None:
        if request_kind == "ocr":
            self.main_window.update_ocr_result("OCR 识别失败。")
            self._show_error("OCR 识别失败", message)
            return

        if request_kind == "translation":
            self.floating_window.set_text("")
            self._show_error("翻译失败", message)

    @staticmethod
    def _build_translation_prompt(config: AppConfig) -> str:
        prompt = (
            config.translation_prompt_template
            or DEFAULT_TRANSLATION_PROMPT_TEMPLATE
        )
        prompt = prompt.replace("[目标语言]", config.target_language or "简体中文")
        if "[OCR结果]" in prompt:
            prompt = prompt.replace(
                "[OCR结果]",
                "请直接识别图片中的文本内容，并翻译为目标语言。",
            )
        return prompt

    @staticmethod
    def _image_to_base64(image: Image.Image) -> str:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        url = base_url.strip()
        if not url:
            return ""

        url = url.rstrip("/")

        if url.endswith("/chat/completions"):
            return url

        if url.endswith("/v1"):
            return f"{url}/chat/completions"

        return f"{url}/v1/chat/completions"

    @staticmethod
    def _normalize_models_url(base_url: str) -> str:
        url = base_url.strip()
        if not url:
            return ""

        url = url.rstrip("/")

        if url.endswith("/models"):
            return url

        if url.endswith("/chat/completions"):
            return f"{url[: -len('/chat/completions')]}/models"

        if url.endswith("/v1"):
            return f"{url}/models"

        return f"{url}/v1/models"

    @staticmethod
    def _extract_model_names(data: Any) -> list[str]:
        model_names: list[str] = []

        if isinstance(data, dict):
            items = data.get("data")
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        model_id = item.get("id") or item.get("name")
                        if isinstance(model_id, str) and model_id.strip():
                            model_names.append(model_id.strip())
                    elif isinstance(item, str) and item.strip():
                        model_names.append(item.strip())

            items = data.get("models")
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        model_id = item.get("id") or item.get("name")
                        if isinstance(model_id, str) and model_id.strip():
                            model_names.append(model_id.strip())
                    elif isinstance(item, str) and item.strip():
                        model_names.append(item.strip())

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    model_id = item.get("id") or item.get("name")
                    if isinstance(model_id, str) and model_id.strip():
                        model_names.append(model_id.strip())
                elif isinstance(item, str) and item.strip():
                    model_names.append(item.strip())

        return sorted(set(model_names), key=str.lower)

    @staticmethod
    def _qimage_to_pil_image(qimage: QImage) -> Image.Image:
        if qimage.isNull():
            raise ValueError("剪贴板中的图片数据无效。")

        converted = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
        width = converted.width()
        height = converted.height()
        bytes_per_line = converted.bytesPerLine()

        ptr = converted.bits()
        buffer = ptr.asstring(bytes_per_line * height)

        return Image.frombuffer(
            "RGBA",
            (width, height),
            buffer,
            "raw",
            "RGBA",
            bytes_per_line,
            1,
        ).convert("RGB")

    def _get_image_from_clipboard(self) -> tuple[Image.Image, QPixmap]:
        clipboard = QApplication.clipboard()

        pixmap = clipboard.pixmap()
        if pixmap is not None and not pixmap.isNull():
            qimage = pixmap.toImage()
            pil_image = self._qimage_to_pil_image(qimage)
            return pil_image, pixmap

        qimage = clipboard.image()
        if qimage is not None and not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)
            pil_image = self._qimage_to_pil_image(qimage)
            return pil_image, pixmap

        raise ValueError("剪贴板中未检测到图片。")

    @staticmethod
    def _validate_api_config(
        api_config: ApiConfig,
        *,
        config_name: str,
    ) -> None:
        if not api_config.base_url.strip():
            raise ValueError(f"{config_name} Base URL 不能为空。")

        if not (
            api_config.base_url.startswith("http://")
            or api_config.base_url.startswith("https://")
        ):
            raise ValueError(f"{config_name} Base URL 格式不正确，必须以 http:// 或 https:// 开头。")

        if not api_config.model_name.strip():
            raise ValueError(f"{config_name}模型名称不能为空。")

    @staticmethod
    def _validate_config(
        config: AppConfig,
        allow_empty_api_for_save: bool = False,
    ) -> None:
        config.ensure_valid_state()

        if not allow_empty_api_for_save:
            if not config.ocr_enabled and not config.translation_enabled:
                raise ValueError("OCR 与翻译不能同时关闭，至少开启一个。")

            if config.ocr_enabled:
                if not config.ocr_prompt_template.strip():
                    raise ValueError("OCR 提示词不能为空。")
                AppController._validate_api_config(
                    config.get_selected_ocr_api_config(),
                    config_name="OCR",
                )

            if config.translation_enabled:
                if not config.translation_prompt_template.strip():
                    raise ValueError("翻译提示词不能为空。")
                AppController._validate_api_config(
                    config.get_selected_translation_api_config(),
                    config_name="翻译",
                )

                if not config.target_language.strip():
                    raise ValueError("目标语言不能为空。")

        shortcut_text = GlobalHotkeyManager._normalize_shortcut_text(
            config.refresh_shortcut
        )
        if not shortcut_text:
            raise ValueError("刷新框选区域快捷键不能为空。")

        shortcut = QKeySequence(shortcut_text)
        if shortcut.isEmpty():
            raise ValueError("刷新框选区域快捷键格式无效。")

        GlobalHotkeyManager._parse_qt_shortcut(shortcut_text)

    def __del__(self) -> None:
        try:
            self._global_hotkey_manager.unregister_shortcut()
        except Exception:
            pass

    @staticmethod
    def _resource_search_dirs() -> list[Path]:
        dirs: list[Path] = []

        if getattr(sys, "frozen", False):
            dirs.append(Path(sys.executable).resolve().parent)
            meipass = getattr(sys, "_MEIPASS", None)
            if isinstance(meipass, str) and meipass:
                dirs.append(Path(meipass))
        else:
            dirs.append(Path(__file__).resolve().parent)

        dirs.append(Path.cwd())

        unique_dirs: list[Path] = []
        for directory in dirs:
            if directory not in unique_dirs:
                unique_dirs.append(directory)

        return unique_dirs

    @classmethod
    def _load_app_icon(cls) -> Optional[QIcon]:
        for base_dir in cls._resource_search_dirs():
            for icon_name in ("logo.ico", "logo.png"):
                icon_path = base_dir / icon_name
                if icon_path.exists():
                    icon = QIcon(str(icon_path))
                    if not icon.isNull():
                        return icon
        return None

    @staticmethod
    def _refresh_button_style(button) -> None:
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self.main_window, title, message)

    def _show_info(self, title: str, message: str) -> None:
        toast_text = message.strip() or title.strip()
        self.main_window.show_toast(toast_text)


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Mo.OCR.VLMTranslator"
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("OCR与翻译助手")

    controller = AppController()
    app._controller = controller  # type: ignore[attr-defined]

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
