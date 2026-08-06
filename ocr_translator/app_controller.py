from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Optional

from PIL import Image
from PyQt6.QtCore import (
    QObject,
    QRect,
    QThread,
    QTimer,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
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
from .models_worker import ModelsFetchWorker
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
        self._models_fetch_thread: Optional[QThread] = None
        self._models_fetch_worker: Optional[ModelsFetchWorker] = None
        self._models_fetch_role: Optional[str] = None
        self._models_fetch_current_model = ""
        self._models_fetch_url = ""
        self._last_clipboard_image_hash: Optional[str] = None

        self._global_hotkey_manager = GlobalHotkeyManager(self.refresh_last_capture)
        self._is_quitting = False
        self._quit_scheduled = False
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
        self.main_window.cancel_fetch_models_button.clicked.connect(
            self.cancel_fetch_models
        )
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
        """注册或切换全局快捷键；管理器内部保证失败时恢复旧注册。"""
        app = QApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self._global_hotkey_manager)

        try:
            self._global_hotkey_manager.register_shortcut(shortcut_text)
        finally:
            # 即使注册失败，也要恢复 native event filter；旧快捷键可能已被回滚。
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
        """
        事务性保存配置：
        1. 构建并验证新配置（不写盘）；
        2. 尝试注册新快捷键；
        3. 注册成功后才保存配置；
        4. 任一步失败都恢复旧快捷键、旧磁盘配置和旧界面配置。
        """
        old_config = self.config_manager.load()
        old_shortcut = self._global_hotkey_manager.current_shortcut
        shortcut_changed = False

        try:
            new_config = self._build_config_from_ui()
            self._validate_config(new_config, allow_empty_api_for_save=True)

            normalized_new_shortcut = GlobalHotkeyManager._normalize_shortcut_text(
                new_config.refresh_shortcut
            )
            normalized_old_shortcut = GlobalHotkeyManager._normalize_shortcut_text(
                old_shortcut or old_config.refresh_shortcut
            )

            if normalized_new_shortcut != normalized_old_shortcut:
                self._setup_shortcuts(normalized_new_shortcut)
                shortcut_changed = True

            # 快捷键已切换成功，此时才允许写盘。
            self.config_manager.save(new_config)
            self.main_window.set_config(new_config)
            self.floating_window.apply_appearance_config(new_config)
            self._show_info("保存成功", "OCR 与翻译配置已成功保存到本地。")
        except Exception as exc:
            rollback_errors: list[str] = []

            if shortcut_changed:
                try:
                    self._setup_shortcuts(normalized_old_shortcut)
                except Exception as rollback_exc:
                    rollback_errors.append(f"旧快捷键恢复失败：{rollback_exc}")

            # ConfigManager.save 使用原子替换；失败时磁盘旧配置仍在。
            # 这里重新加载磁盘配置，避免回滚时使用已变更的内存对象。
            try:
                restored_config = self.config_manager.load()
                self.main_window.set_config(restored_config)
                self.floating_window.apply_appearance_config(restored_config)
            except Exception as rollback_exc:
                rollback_errors.append(f"旧界面配置恢复失败：{rollback_exc}")

            detail = str(exc)
            if rollback_errors:
                detail = f"{detail}\n\n" + "\n".join(rollback_errors)
            self._show_error("保存失败", detail)

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
        """在专用后台线程中拉取当前 Profile 的模型列表。"""
        if self._is_quitting:
            return
        if self._models_fetch_thread is not None:
            return

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

            thread = QThread(self)
            worker = ModelsFetchWorker(models_url, api_config.api_key)
            worker.moveToThread(thread)

            self._models_fetch_thread = thread
            self._models_fetch_worker = worker
            self._models_fetch_role = role
            self._models_fetch_current_model = api_config.model_name
            self._models_fetch_url = models_url

            thread.started.connect(worker.run)
            worker.succeeded.connect(self.on_models_fetch_success)
            worker.failed.connect(self.on_models_fetch_error)
            worker.cancelled.connect(self.on_models_fetch_cancelled)
            # ModelsFetchWorker 在最外层 finally 发出 finished，驱动线程退出。
            worker.finished.connect(thread.quit)
            # 统一释放顺序：worker.deleteLater、控制器清理、thread.deleteLater。
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(self._on_models_fetch_thread_finished)
            thread.finished.connect(thread.deleteLater)

            self.main_window.set_models_fetching(True)
            thread.start()
        except Exception as exc:
            self._reset_models_fetch_ui()
            self._show_error("获取模型失败", str(exc))

    def cancel_fetch_models(self) -> None:
        """取消正在进行的模型拉取，并让后台 Worker 关闭其会话。"""
        worker = self._models_fetch_worker
        if worker is None:
            return

        self.main_window.set_models_fetch_cancelling()
        worker.cancel()

    def on_models_fetch_success(self, model_names: list[str]) -> None:
        if self._is_quitting:
            return
        current_model = self._models_fetch_current_model
        self.main_window.model_name_combo.clear()
        self.main_window.model_name_combo.addItems(model_names)

        if current_model and current_model in model_names:
            self.main_window.model_name_combo.setCurrentText(current_model)
        else:
            self.main_window.model_name_combo.setCurrentText(model_names[0])

        role_name = "OCR" if self._models_fetch_role == "ocr" else "翻译"
        self._show_info(
            "获取成功",
            f"已从 {self._models_fetch_url} 获取到 {len(model_names)} 个{role_name}模型。",
        )

    def on_models_fetch_error(self, message: str) -> None:
        if self._is_quitting:
            return
        self._show_error("获取模型失败", message)

    def on_models_fetch_cancelled(self) -> None:
        if self._is_quitting:
            return
        self._show_info("已取消", "已取消模型列表拉取。")

    def _reset_models_fetch_ui(self) -> None:
        self.main_window.set_models_fetching(False)

    @pyqtSlot()
    def _on_models_fetch_thread_finished(self) -> None:
        thread = self.sender()
        if isinstance(thread, QThread):
            self._cleanup_models_fetch(thread)

    def _cleanup_models_fetch(self, expected_thread: QThread) -> None:
        if self._models_fetch_thread is not expected_thread:
            return

        self._models_fetch_thread = None
        self._models_fetch_worker = None
        self._models_fetch_role = None
        self._models_fetch_current_model = ""
        self._models_fetch_url = ""

        if not self._is_quitting:
            self._reset_models_fetch_ui()

        self._maybe_finish_shutdown()

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

    def _cleanup_request(self, request_kind: str, expected_thread: QThread) -> None:
        """
        仅做注册表清理：只有当前注册的线程与完成线程身份一致时才移除，
        防止迟到的 thread.finished 清掉未来同名的新任务。
        Worker / 线程的删除统一由 thread.finished 连接完成，这里不再手动删除。
        """
        if self._request_threads.get(request_kind) is not expected_thread:
            return

        self._request_threads.pop(request_kind, None)
        self._request_workers.pop(request_kind, None)
        self._maybe_finish_shutdown()

    def _find_request_kind_for_worker(self, worker: object) -> Optional[str]:
        for kind, registered_worker in self._request_workers.items():
            if registered_worker is worker:
                return kind
        return None

    @pyqtSlot(str)
    def _on_api_partial_text(self, text: str) -> None:
        worker = self.sender()
        kind = self._find_request_kind_for_worker(worker)
        if kind is None:
            return
        self.on_api_partial_text(kind, text)

    @pyqtSlot(str)
    def _on_api_success(self, text: str) -> None:
        worker = self.sender()
        kind = self._find_request_kind_for_worker(worker)
        if kind is None:
            return
        self.on_api_success(kind, text)

    @pyqtSlot(str)
    def _on_api_error(self, message: str) -> None:
        worker = self.sender()
        kind = self._find_request_kind_for_worker(worker)
        if kind is None:
            return
        self.on_api_error(kind, message)

    @pyqtSlot()
    def _on_request_thread_finished(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            return

        for kind, registered_thread in list(self._request_threads.items()):
            if registered_thread is thread:
                self._cleanup_request(kind, thread)
                return

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
        """
        开始两阶段退出（异步阶段）：
        1. 置 quitting，拒绝新任务；
        2. 隐藏托盘、注销全局快捷键；
        3. 协作取消所有 Worker 的网络 I/O；
        4. 对全部受管线程 requestInterruption + quit；
        5. 关闭辅助窗口，然后交由 _maybe_finish_shutdown 决定何时真正退出。
        """
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

        # 协作取消：直接调用线程安全的幂等 cancel()，尽快打断网络读取。
        models_worker = self._models_fetch_worker
        if models_worker is not None:
            models_worker.cancel()
        for worker in list(self._request_workers.values()):
            worker.cancel()

        # requestInterruption 是诊断友好的协作提示；quit 退出线程事件循环。
        # 两者都不能替代 Worker 的 HTTP 取消。
        for thread in list(self._request_threads.values()):
            thread.requestInterruption()
            thread.quit()
        if self._models_fetch_thread is not None:
            self._models_fetch_thread.requestInterruption()
            self._models_fetch_thread.quit()

        for widget in (
            self.floating_window,
            self.capture_overlay,
            self.selection_frame_overlay,
        ):
            try:
                widget.close()
            except Exception:
                pass

        self._maybe_finish_shutdown()

    def _maybe_finish_shutdown(self) -> None:
        """
        只有满足以下全部条件才允许调度 QApplication.quit()：
        - 正在退出；
        - 请求线程注册表为空；
        - 模型列表线程为空；
        - 尚未调度过退出。
        调度时用 QTimer.singleShot(0, app.quit) 让当前一轮清理和
        deferred delete 有机会回到事件循环。
        """
        if not self._is_quitting or self._quit_scheduled:
            return
        if self._request_threads:
            return
        if self._models_fetch_thread is not None:
            return

        self._quit_scheduled = True
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)

    def finalize_threads(self) -> None:
        """
        同步最终保护：仅供 main.py 的 finally 调用，不得显示 UI。

        正常托盘退出时异步阶段已排空，此方法应快速空操作；
        若事件循环因异常或其他原因提前返回，这里兜底执行
        cancel + quit + wait，绝不销毁仍运行的线程。
        """
        self._is_quitting = True

        models_worker = self._models_fetch_worker
        if models_worker is not None:
            models_worker.cancel()
        for worker in list(self._request_workers.values()):
            worker.cancel()

        threads: list[QThread] = []
        if self._models_fetch_thread is not None:
            threads.append(self._models_fetch_thread)
        threads.extend(list(self._request_threads.values()))

        for thread in threads:
            thread.requestInterruption()
            thread.quit()

        for thread in threads:
            thread.wait()

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
        if self._is_quitting:
            return
        if request_kind in self._request_threads:
            return

        thread = QThread(self)
        worker = ApiWorker(
            api_config,
            prompt,
            image_base64=image_base64,
            text_input=text_input,
        )
        worker.moveToThread(thread)

        self._request_threads[request_kind] = thread
        self._request_workers[request_kind] = worker

        # 全部连接必须在 thread.start() 前完成。
        thread.started.connect(worker.run)
        # 三类业务信号通过绑定在控制器上的代理 slot 转发（sender 身份查找），
        # Qt 会以 AutoConnection 将调用排队到控制器所在的主线程。
        worker.partial_text.connect(self._on_api_partial_text)
        worker.finished.connect(self._on_api_success)
        worker.error.connect(self._on_api_error)
        # 唯一的生命周期终止信号是 done，驱动线程退出。
        worker.done.connect(thread.quit)
        # 统一释放顺序：worker.deleteLater、控制器清理、thread.deleteLater。
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_request_thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def on_api_partial_text(self, request_kind: str, text: str) -> None:
        if self._is_quitting:
            return
        preview_text = text.strip()
        if request_kind == "ocr":
            self.main_window.update_ocr_result(
                preview_text or "正在执行 OCR 识别，请稍候..."
            )
            return

        if request_kind == "translation":
            self.floating_window.set_text(preview_text or "正在翻译，请稍候...")

    def on_api_success(self, request_kind: str, text: str) -> None:
        if self._is_quitting:
            return
        if request_kind == "ocr":
            self.main_window.update_ocr_result(text)
            return

        if request_kind == "translation":
            self.floating_window.set_text(text)

    def on_api_error(self, request_kind: str, message: str) -> None:
        if self._is_quitting:
            return
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
