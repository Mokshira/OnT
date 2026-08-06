from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Optional

import requests
from PIL import Image
from PyQt6.QtCore import QObject, QRect, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .api_utils import extract_model_names, normalize_base_url, normalize_models_url
from .api_worker import ApiWorker
from .config_manager import (
    ApiConfig,
    AppConfig,
    ConfigManager,
    DEFAULT_OCR_PROMPT_TEMPLATE,
    DEFAULT_REFRESH_SHORTCUT,
    DEFAULT_TRANSLATION_PROMPT_TEMPLATE,
)
from .floating_window import FloatingSubtitleWindow
from .hotkey_manager import GlobalHotkeyManager
from .image_utils import image_to_base64, qimage_to_pil_image
from .main_window import MainWindow
from .screenshot_tool import (
    CaptureResult,
    ScreenCaptureOverlay,
    SelectionFrameOverlay,
    capture_region,
)


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
            api_config.base_url = normalize_base_url(api_config.base_url)

        for api_config in config.translation_api_configs:
            api_config.base_url = normalize_base_url(api_config.base_url)

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
            models_url = normalize_models_url(api_config.base_url)

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
            model_names = extract_model_names(data)
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
            image_base64 = image_to_base64(result.image)
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
            image_base64 = image_to_base64(pil_image)
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

    def _get_image_from_clipboard(self) -> tuple[Image.Image, QPixmap]:
        clipboard = QApplication.clipboard()

        pixmap = clipboard.pixmap()
        if pixmap is not None and not pixmap.isNull():
            qimage = pixmap.toImage()
            pil_image = qimage_to_pil_image(qimage)
            return pil_image, pixmap

        qimage = clipboard.image()
        if qimage is not None and not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)
            pil_image = qimage_to_pil_image(qimage)
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
            package_dir = Path(__file__).resolve().parent
            dirs.append(package_dir.parent / "assets")
            dirs.append(package_dir.parent)

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
