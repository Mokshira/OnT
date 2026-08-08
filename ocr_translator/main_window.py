from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .config_manager import (
    ApiConfig,
    AppConfig,
    DEFAULT_API_PROFILE_NAME,
    DEFAULT_OCR_PROMPT_TEMPLATE,
    DEFAULT_REFRESH_SHORTCUT,
    DEFAULT_TRANSLATION_PROMPT_TEMPLATE,
)
from .floating_window import render_markdown_preserving_line_breaks
from .settings_dialog import SettingsDialog
from .theme import apply_window_theme
from .ui_widgets import KbdBadge, Pill, ToggleSwitch, refresh_widget_style


class MainWindow(QMainWindow):
    closing = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self._ocr_api_configs: list[ApiConfig] = [ApiConfig()]
        self._selected_ocr_api_config_id = self._ocr_api_configs[0].profile_id
        self._translation_api_configs: list[ApiConfig] = [ApiConfig()]
        self._selected_translation_api_config_id = self._translation_api_configs[
            0
        ].profile_id
        self._active_config_role = "ocr"
        self._is_switching_api_profile = False
        self._ocr_prompt_template = DEFAULT_OCR_PROMPT_TEMPLATE
        self._translation_prompt_template = DEFAULT_TRANSLATION_PROMPT_TEMPLATE
        self._target_language = "简体中文"
        self._ocr_result_text = ""
        self._preview_source_pixmap = QPixmap()
        self._is_config_drawer_open = False
        self._page_animation: QPropertyAnimation | None = None
        self._page_effects: dict[int, QGraphicsOpacityEffect] = {}

        self._toast_hide_timer = QTimer(self)
        self._toast_hide_timer.setSingleShot(True)

        self._setup_window()
        self._setup_ui()
        apply_window_theme(self)
        self.switch_config_role("ocr", save_current=False)
        self.set_config_drawer_visible(False)
        self._set_page(0, animate=False)

    def _setup_window(self) -> None:
        self.setObjectName("MainWindow")
        self.setWindowTitle("OCR 与翻译助手")
        self.resize(1040, 680)
        self.setMinimumSize(900, 560)

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("AppRoot")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        body = QWidget()
        body.setObjectName("ContentViewport")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        body_layout.addWidget(self._build_sidebar())

        content_area = QFrame()
        content_area.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(0)

        self.page_stack = QStackedWidget()
        self.overview_page = self._build_overview_page()
        self.results_page = self._build_results_page()
        self.page_stack.addWidget(self.overview_page)
        self.page_stack.addWidget(self.results_page)
        content_layout.addWidget(self.page_stack)
        body_layout.addWidget(content_area, 1)

        root_layout.addWidget(body, 1)
        root_layout.addWidget(self._build_bottom_bar())

        self.settings_dialog = SettingsDialog(self)
        self._bind_settings_controls()
        self._connect_ui_signals()
        self._setup_toast()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(188)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(4)

        brand = QLabel("OnT")
        brand.setObjectName("BrandName")
        eyebrow = QLabel("OCR TRANSLATOR")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(brand)
        layout.addSpacing(2)
        layout.addWidget(eyebrow)
        layout.addSpacing(22)

        self.overview_nav_button = QPushButton("概览")
        self.overview_nav_button.setObjectName("SidebarItem")
        self.overview_nav_button.setProperty("active", True)

        self.results_nav_button = QPushButton("识别结果")
        self.results_nav_button.setObjectName("SidebarItem")
        self.results_nav_button.setProperty("active", False)

        layout.addWidget(self.overview_nav_button)
        layout.addWidget(self.results_nav_button)
        layout.addStretch(1)
        return sidebar

    def _new_content_page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("ContentViewport")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("ContentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        viewport = QWidget()
        viewport.setObjectName("ContentViewport")
        content_layout = QVBoxLayout(viewport)
        content_layout.setContentsMargins(26, 24, 26, 26)
        content_layout.setSpacing(0)
        scroll.setWidget(viewport)

        card_layout.addWidget(scroll)
        page_layout.addWidget(card)
        return page, content_layout

    def _page_header(
        self,
        eyebrow_text: str,
        title_text: str,
        description_text: str,
        actions: list[QPushButton] | None = None,
    ) -> QWidget:
        header = QWidget()
        header.setObjectName("ContentViewport")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        labels = QWidget()
        labels.setObjectName("ContentViewport")
        labels_layout = QVBoxLayout(labels)
        labels_layout.setContentsMargins(0, 0, 0, 0)
        labels_layout.setSpacing(4)

        eyebrow = QLabel(eyebrow_text)
        eyebrow.setObjectName("Eyebrow")
        title = QLabel(title_text)
        title.setObjectName("PageTitle")
        description = QLabel(description_text)
        description.setObjectName("PageDescription")
        description.setWordWrap(True)

        labels_layout.addWidget(eyebrow)
        labels_layout.addWidget(title)
        labels_layout.addWidget(description)
        header_layout.addWidget(labels, 1)

        if actions:
            action_box = QWidget()
            action_box.setObjectName("ContentViewport")
            action_layout = QHBoxLayout(action_box)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(8)
            for button in actions:
                action_layout.addWidget(button)
            header_layout.addWidget(action_box, 0, Qt.AlignmentFlag.AlignTop)

        return header

    def _build_overview_page(self) -> QWidget:
        page, layout = self._new_content_page()

        self.capture_button = QPushButton("开始框选")
        self.capture_button.setProperty("variant", "primary")
        self.capture_button.setToolTip("打开截图选区工具")

        self.clipboard_button = QPushButton("剪贴板自动处理：已关闭")
        self.clipboard_button.setObjectName("SecondaryButton")
        self.clipboard_button.setCheckable(True)
        self.clipboard_button.setToolTip("监控剪贴板中的图片并自动识别")

        layout.addWidget(
            self._page_header(
                "OVERVIEW",
                "概览",
                "查看服务状态，并从这里开始一次截图识别。",
                [self.clipboard_button, self.capture_button],
            )
        )
        layout.addSpacing(24)

        hint_card = QFrame()
        hint_card.setObjectName("HintCard")
        hint_layout = QHBoxLayout(hint_card)
        hint_layout.setContentsMargins(16, 14, 16, 14)
        hint_layout.setSpacing(16)

        hint_copy = QWidget()
        hint_copy.setObjectName("ContentViewport")
        hint_copy_layout = QVBoxLayout(hint_copy)
        hint_copy_layout.setContentsMargins(0, 0, 0, 0)
        hint_copy_layout.setSpacing(3)
        hint_title = QLabel("按下截图快捷键开始识别")
        hint_title.setObjectName("CardTitle")
        hint_detail = QLabel("在任意应用中框选需要处理的画面区域")
        hint_detail.setObjectName("CardDetail")
        hint_copy_layout.addWidget(hint_title)
        hint_copy_layout.addWidget(hint_detail)

        self.shortcut_kbd_container = QWidget()
        self.shortcut_kbd_container.setObjectName("ContentViewport")
        self.shortcut_kbd_layout = QHBoxLayout(self.shortcut_kbd_container)
        self.shortcut_kbd_layout.setContentsMargins(0, 0, 0, 0)
        self.shortcut_kbd_layout.setSpacing(5)

        hint_layout.addWidget(hint_copy, 1)
        hint_layout.addWidget(self.shortcut_kbd_container)
        layout.addWidget(hint_card)
        layout.addSpacing(24)

        status_title = QLabel("服务状态")
        status_title.setObjectName("SectionTitle")
        layout.addWidget(status_title)
        layout.addSpacing(10)

        self.ocr_enabled_button = ToggleSwitch()
        self.ocr_enabled_button.setChecked(True)
        (
            ocr_card,
            self.ocr_status_pill,
            self.ocr_profile_summary_label,
            self.ocr_model_summary_label,
        ) = self._build_status_card(
            "OCR 服务",
            self.ocr_enabled_button,
        )

        self.translation_enabled_button = ToggleSwitch()
        self.translation_enabled_button.setChecked(True)
        (
            translation_card,
            self.translation_status_pill,
            self.translation_profile_summary_label,
            self.translation_model_summary_label,
        ) = self._build_status_card(
            "翻译服务",
            self.translation_enabled_button,
        )

        self.display_toggle_button = ToggleSwitch()
        self.display_toggle_button.setChecked(True)
        (
            display_card,
            self.display_status_pill,
            self.display_profile_summary_label,
            self.display_model_summary_label,
        ) = self._build_status_card(
            "悬浮字幕",
            self.display_toggle_button,
        )
        self.display_profile_summary_label.setText("原有展示窗口")
        self.display_model_summary_label.setText("外观与交互保持不变")

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        status_row.addWidget(ocr_card, 1)
        status_row.addWidget(translation_card, 1)
        status_row.addWidget(display_card, 1)
        layout.addLayout(status_row)
        layout.addStretch(1)
        return page

    def _build_status_card(
        self,
        title_text: str,
        toggle: ToggleSwitch,
    ) -> tuple[QFrame, Pill, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("StatusCard")
        card.setMinimumWidth(170)
        card.setMinimumHeight(132)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 14, 15, 14)
        card_layout.setSpacing(5)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        top_row.addWidget(title)
        top_row.addStretch(1)
        top_row.addWidget(toggle, 0, Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(top_row)

        status = Pill("开启", "ok")
        card_layout.addWidget(status)
        card_layout.addSpacing(4)

        profile = QLabel("默认配置")
        profile.setObjectName("CardDetail")
        profile.setWordWrap(True)
        model = QLabel("未选择模型")
        model.setObjectName("Muted")
        model.setWordWrap(True)
        card_layout.addWidget(profile)
        card_layout.addWidget(model)
        card_layout.addStretch(1)
        return card, status, profile, model

    def _build_results_page(self) -> QWidget:
        page, layout = self._new_content_page()

        self.copy_ocr_button = QPushButton("复制结果")
        self.copy_ocr_button.setProperty("variant", "ghost")
        layout.addWidget(
            self._page_header(
                "RESULTS",
                "识别结果",
                "查看最近一次截图与 OCR 原文。",
                [self.copy_ocr_button],
            )
        )
        layout.addSpacing(24)

        result_row = QHBoxLayout()
        result_row.setSpacing(12)

        preview_card = QFrame()
        preview_card.setObjectName("PreviewCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(16, 15, 16, 16)
        preview_layout.setSpacing(10)
        preview_title = QLabel("截图预览")
        preview_title.setObjectName("CardTitle")
        self.preview_label = QLabel("尚无截图预览")
        self.preview_label.setObjectName("PreviewCanvas")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(250, 270)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.preview_label, 1)

        result_card = QFrame()
        result_card.setObjectName("ResultCard")
        text_layout = QVBoxLayout(result_card)
        text_layout.setContentsMargins(16, 15, 16, 16)
        text_layout.setSpacing(10)
        result_title = QLabel("OCR 原文")
        result_title.setObjectName("CardTitle")
        self.ocr_result_output = QTextBrowser()
        self.ocr_result_output.setObjectName("ResultOutput")
        self.ocr_result_output.setReadOnly(True)
        self.ocr_result_output.setPlaceholderText(
            "完成截图后，OCR 识别结果会显示在这里。"
        )
        self.ocr_result_output.setMinimumSize(250, 270)
        text_layout.addWidget(result_title)
        text_layout.addWidget(self.ocr_result_output, 1)

        result_row.addWidget(preview_card, 1)
        result_row.addWidget(result_card, 1)
        layout.addLayout(result_row, 1)
        return page

    def _build_bottom_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("BottomBar")
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        version = QLabel("v1.0.0")
        version.setObjectName("Muted")
        layout.addWidget(version)
        layout.addStretch(1)

        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("BottomSettingsButton")
        self.settings_button.setToolTip("打开设置")
        self.settings_button.setAccessibleName("设置")
        layout.addWidget(self.settings_button)
        return bar

    def _bind_settings_controls(self) -> None:
        dialog = self.settings_dialog
        self.api_profile_combo = dialog.api_profile_combo
        self.add_api_profile_button = dialog.add_api_profile_button
        self.update_api_profile_button = dialog.update_api_profile_button
        self.delete_api_profile_button = dialog.delete_api_profile_button
        self.api_profile_name_input = dialog.api_profile_name_input
        self.api_key_input = dialog.api_key_input
        self.toggle_api_key_button = dialog.toggle_api_key_button
        self.base_url_input = dialog.base_url_input
        self.model_name_combo = dialog.model_name_combo
        self.fetch_models_button = dialog.fetch_models_button
        self.cancel_fetch_models_button = dialog.cancel_fetch_models_button
        self.target_language_input = dialog.target_language_input
        self.prompt_input = dialog.prompt_input
        self.prompt_label = dialog.prompt_label
        self.refresh_shortcut_input = dialog.refresh_shortcut_input
        self.refresh_shortcut_hint_label = dialog.refresh_shortcut_hint_label
        self.save_button = dialog.save_button

        self.ocr_mode_button = dialog.role_segment.button("ocr")
        self.translation_mode_button = dialog.role_segment.button("translation")
        self.config_drawer_panel = dialog
        self.drawer_toggle_button = self.settings_button
        self.preview_panel = self.results_page

    def _connect_ui_signals(self) -> None:
        self.overview_nav_button.clicked.connect(
            lambda _checked=False: self._set_page(0)
        )
        self.results_nav_button.clicked.connect(
            lambda _checked=False: self._set_page(1)
        )
        self.settings_button.clicked.connect(
            lambda _checked=False: self.set_config_drawer_visible(True)
        )
        self.settings_dialog.finished.connect(self._on_settings_dialog_finished)
        self.settings_dialog.role_segment.selectionChanged.connect(
            self.switch_config_role
        )
        self.api_profile_combo.currentIndexChanged.connect(
            self.on_api_profile_selection_changed
        )
        self.toggle_api_key_button.clicked.connect(self.toggle_api_key_visibility)
        self.ocr_enabled_button.toggled.connect(
            self._update_ocr_enabled_button_text
        )
        self.translation_enabled_button.toggled.connect(
            self._update_translation_enabled_button_text
        )
        self.display_toggle_button.toggled.connect(self._update_display_status_text)

    def _setup_toast(self) -> None:
        self._toast_label = QLabel(self)
        self._toast_label.setObjectName("Toast")
        self._toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast_label.setWordWrap(False)
        self._toast_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._toast_label.hide()

        self._toast_opacity = QGraphicsOpacityEffect(self._toast_label)
        self._toast_opacity.setOpacity(0.0)
        self._toast_label.setGraphicsEffect(self._toast_opacity)

        self._toast_fade_in = QPropertyAnimation(
            self._toast_opacity,
            b"opacity",
            self,
        )
        self._toast_fade_in.setDuration(180)
        self._toast_fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._toast_fade_out = QPropertyAnimation(
            self._toast_opacity,
            b"opacity",
            self,
        )
        self._toast_fade_out.setDuration(180)
        self._toast_fade_out.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._toast_fade_out.finished.connect(self._toast_label.hide)
        self._toast_hide_timer.timeout.connect(self._hide_toast)

    def _set_page(self, index: int, animate: bool = True) -> None:
        if index < 0 or index >= self.page_stack.count():
            return

        self.page_stack.setCurrentIndex(index)
        self.overview_nav_button.setProperty("active", index == 0)
        self.results_nav_button.setProperty("active", index == 1)
        refresh_widget_style(self.overview_nav_button)
        refresh_widget_style(self.results_nav_button)

        if not animate or not self.isVisible():
            return

        if self._page_animation is not None:
            self._page_animation.stop()

        page = self.page_stack.widget(index)
        effect = self._page_effects.get(index)
        if effect is None:
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
            self._page_effects[index] = effect

        effect.setOpacity(0.0)
        self._page_animation = QPropertyAnimation(effect, b"opacity", self)
        self._page_animation.setDuration(180)
        self._page_animation.setStartValue(0.0)
        self._page_animation.setEndValue(1.0)
        self._page_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._page_animation.start()

    def set_models_fetching(self, is_fetching: bool) -> None:
        """同步模型列表后台请求的按钮与输入控件状态。"""
        self.fetch_models_button.setEnabled(not is_fetching)
        self.fetch_models_button.setText("正在拉取…" if is_fetching else "拉取模型")
        self.cancel_fetch_models_button.setVisible(is_fetching)
        self.cancel_fetch_models_button.setEnabled(is_fetching)
        self.cancel_fetch_models_button.setText("取消")
        self.model_name_combo.setEnabled(not is_fetching)

    def set_models_fetch_cancelling(self) -> None:
        """取消已发出，保留禁用状态直到后台线程退出。"""
        self.fetch_models_button.setText("正在取消…")
        self.cancel_fetch_models_button.setEnabled(False)
        self.cancel_fetch_models_button.setText("取消中…")

    def set_config_drawer_visible(self, is_visible: bool) -> None:
        self._is_config_drawer_open = bool(is_visible)
        if self._is_config_drawer_open:
            self.settings_dialog.show_page("api")
            self.settings_dialog.open()
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            self.settings_button.setToolTip("设置窗口已打开")
        else:
            self.settings_dialog.hide()
            self.settings_button.setToolTip("打开设置")

    def _on_settings_dialog_finished(self, _result: int) -> None:
        self._is_config_drawer_open = False
        self.settings_button.setToolTip("打开设置")
        self._sync_active_role_state()
        self._refresh_overview_status()
        self._refresh_shortcut_badges()

    def _open_config_drawer_for_role(self, role: str) -> None:
        self.switch_config_role(role)
        self.set_config_drawer_visible(True)

    def _update_ocr_enabled_button_text(self, *_args) -> None:
        enabled = self.ocr_enabled_button.isChecked()
        self.ocr_enabled_button.setText("OCR：开" if enabled else "OCR：关")
        self.ocr_enabled_button.setToolTip(
            "OCR 服务已开启" if enabled else "OCR 服务已关闭"
        )
        self.ocr_status_pill.setText("开启" if enabled else "关闭")
        self.ocr_status_pill.setTone("ok" if enabled else "default")

    def _update_translation_enabled_button_text(self, *_args) -> None:
        enabled = self.translation_enabled_button.isChecked()
        self.translation_enabled_button.setText(
            "翻译：开" if enabled else "翻译：关"
        )
        self.translation_enabled_button.setToolTip(
            "翻译服务已开启" if enabled else "翻译服务已关闭"
        )
        self.translation_status_pill.setText("开启" if enabled else "关闭")
        self.translation_status_pill.setTone("ok" if enabled else "default")

    def _update_display_status_text(self, *_args) -> None:
        visible = self.display_toggle_button.isChecked()
        self.display_toggle_button.setText(
            "翻译显示：已开启" if visible else "翻译显示：已关闭"
        )
        self.display_toggle_button.setToolTip(
            "悬浮字幕已显示" if visible else "悬浮字幕已隐藏"
        )
        self.display_status_pill.setText("可见" if visible else "隐藏")
        self.display_status_pill.setTone("ok" if visible else "default")

    def _clone_api_config(self, api_config: ApiConfig) -> ApiConfig:
        return ApiConfig(
            profile_id=api_config.profile_id,
            profile_name=api_config.profile_name,
            api_key=api_config.api_key,
            base_url=api_config.base_url,
            model_name=api_config.model_name,
        )

    def get_active_config_role(self) -> str:
        return self._active_config_role

    def _get_role_title(self, role: str) -> str:
        return "识别" if role == "ocr" else "翻译"

    def _get_api_configs_by_role(self, role: str) -> list[ApiConfig]:
        return self._ocr_api_configs if role == "ocr" else self._translation_api_configs

    def _get_selected_profile_id_by_role(self, role: str) -> str:
        return (
            self._selected_ocr_api_config_id
            if role == "ocr"
            else self._selected_translation_api_config_id
        )

    def _set_selected_profile_id_by_role(self, role: str, profile_id: str) -> None:
        if role == "ocr":
            self._selected_ocr_api_config_id = profile_id
        else:
            self._selected_translation_api_config_id = profile_id

    def _get_selected_api_profile_from_role(self, role: str) -> ApiConfig:
        api_configs = self._get_api_configs_by_role(role)
        if not api_configs:
            api_configs.append(ApiConfig())

        selected_id = self._get_selected_profile_id_by_role(role)
        for item in api_configs:
            if item.profile_id == selected_id:
                return item

        self._set_selected_profile_id_by_role(role, api_configs[0].profile_id)
        return api_configs[0]

    def _refresh_api_profile_combo(self) -> None:
        self._is_switching_api_profile = True
        self.api_profile_combo.blockSignals(True)
        self.api_profile_combo.clear()

        api_configs = self._get_api_configs_by_role(self._active_config_role)
        selected_id = self._get_selected_profile_id_by_role(self._active_config_role)

        for item in api_configs:
            self.api_profile_combo.addItem(item.profile_name, item.profile_id)

        index = self.api_profile_combo.findData(selected_id)
        if index < 0 and self.api_profile_combo.count() > 0:
            index = 0
            self._set_selected_profile_id_by_role(
                self._active_config_role,
                str(self.api_profile_combo.itemData(0) or ""),
            )

        if index >= 0:
            self.api_profile_combo.setCurrentIndex(index)

        self.api_profile_combo.blockSignals(False)
        self._is_switching_api_profile = False

    def _apply_api_profile_to_fields(self, api_config: ApiConfig) -> None:
        self.api_profile_name_input.setText(api_config.profile_name)
        self.api_key_input.setText(api_config.api_key)
        self.base_url_input.setText(api_config.base_url)
        self.model_name_combo.setCurrentText(api_config.model_name)

    def _sync_active_role_state(self) -> None:
        profile = self._get_selected_api_profile_from_role(self._active_config_role)
        profile.profile_name = (
            self.api_profile_name_input.text().strip()
            or profile.profile_name.strip()
            or DEFAULT_API_PROFILE_NAME
        )
        profile.api_key = self.api_key_input.text().strip()
        profile.base_url = self.base_url_input.text().strip()
        profile.model_name = self.model_name_combo.currentText().strip()

        if self._active_config_role == "ocr":
            self._ocr_prompt_template = (
                self.prompt_input.toPlainText().strip()
                or DEFAULT_OCR_PROMPT_TEMPLATE
            )
        else:
            self._target_language = (
                self.target_language_input.text().strip() or "简体中文"
            )
            self._translation_prompt_template = (
                self.prompt_input.toPlainText().strip()
                or DEFAULT_TRANSLATION_PROMPT_TEMPLATE
            )

    def switch_config_role(self, role: str, save_current: bool = True) -> None:
        if role not in {"ocr", "translation"}:
            return

        if save_current:
            self._sync_active_role_state()

        self._active_config_role = role
        self.settings_dialog.role_segment.setCurrentKey(role, emit_signal=False)

        if role == "ocr":
            self.settings_dialog.role_context_label.setText(
                "正在编辑 OCR 识别服务"
            )
            self.settings_dialog.prompt_role_pill.setText("OCR 识别")
            self.prompt_label.setText("OCR 提示词")
            self.prompt_input.setPlainText(
                self._ocr_prompt_template or DEFAULT_OCR_PROMPT_TEMPLATE
            )
            self.settings_dialog.target_language_row.hide()
            self.fetch_models_button.setToolTip("拉取 OCR 模型列表")
        else:
            self.settings_dialog.role_context_label.setText("正在编辑翻译服务")
            self.settings_dialog.prompt_role_pill.setText("翻译")
            self.prompt_label.setText("翻译提示词")
            self.prompt_input.setPlainText(
                self._translation_prompt_template
                or DEFAULT_TRANSLATION_PROMPT_TEMPLATE
            )
            self.settings_dialog.target_language_row.show()
            self.target_language_input.setText(self._target_language)
            self.fetch_models_button.setToolTip("拉取翻译模型列表")

        self._refresh_api_profile_combo()
        self._apply_api_profile_to_fields(
            self._get_selected_api_profile_from_role(self._active_config_role)
        )
        self._refresh_overview_status()

    def get_selected_api_profile_id(self) -> str:
        current_data = self.api_profile_combo.currentData()
        if isinstance(current_data, str) and current_data.strip():
            return current_data
        return self._get_selected_profile_id_by_role(self._active_config_role)

    def on_api_profile_selection_changed(self) -> None:
        if self._is_switching_api_profile:
            return

        self._sync_active_role_state()
        self._set_selected_profile_id_by_role(
            self._active_config_role,
            self.get_selected_api_profile_id(),
        )
        self._refresh_api_profile_combo()
        self._apply_api_profile_to_fields(
            self._get_selected_api_profile_from_role(self._active_config_role)
        )
        self._refresh_overview_status()

    def create_api_profile(self) -> None:
        self._sync_active_role_state()
        new_profile = ApiConfig(
            profile_name=DEFAULT_API_PROFILE_NAME,
            api_key="",
            base_url="",
            model_name="",
        )
        self._get_api_configs_by_role(self._active_config_role).append(new_profile)
        self._set_selected_profile_id_by_role(
            self._active_config_role,
            new_profile.profile_id,
        )
        self._refresh_api_profile_combo()
        self._apply_api_profile_to_fields(new_profile)
        self._refresh_overview_status()

    def update_current_api_profile(self) -> None:
        self._sync_active_role_state()
        self._refresh_api_profile_combo()
        self._apply_api_profile_to_fields(
            self._get_selected_api_profile_from_role(self._active_config_role)
        )
        self._refresh_overview_status()

    def delete_current_api_profile(self) -> None:
        self._sync_active_role_state()
        api_configs = self._get_api_configs_by_role(self._active_config_role)
        current_profile_id = self._get_selected_profile_id_by_role(
            self._active_config_role
        )

        remaining = [
            item for item in api_configs if item.profile_id != current_profile_id
        ]
        if not remaining:
            remaining = [ApiConfig()]

        if self._active_config_role == "ocr":
            self._ocr_api_configs = remaining
            self._selected_ocr_api_config_id = remaining[0].profile_id
        else:
            self._translation_api_configs = remaining
            self._selected_translation_api_config_id = remaining[0].profile_id

        self._refresh_api_profile_combo()
        self._apply_api_profile_to_fields(
            self._get_selected_api_profile_from_role(self._active_config_role)
        )
        self._refresh_overview_status()

    def toggle_api_key_visibility(self) -> None:
        is_password_mode = self.api_key_input.echoMode() == QLineEdit.EchoMode.Password
        self.api_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal
            if is_password_mode
            else QLineEdit.EchoMode.Password
        )
        self.toggle_api_key_button.setText("隐藏" if is_password_mode else "显示")

    def set_display_visible(self, is_visible: bool) -> None:
        self.display_toggle_button.blockSignals(True)
        self.display_toggle_button.setChecked(is_visible)
        self.display_toggle_button.blockSignals(False)
        self._update_display_status_text()

    def set_ocr_enabled(self, enabled: bool) -> None:
        self.ocr_enabled_button.blockSignals(True)
        self.ocr_enabled_button.setChecked(enabled)
        self.ocr_enabled_button.blockSignals(False)
        self._update_ocr_enabled_button_text()

    def set_translation_enabled(self, enabled: bool) -> None:
        self.translation_enabled_button.blockSignals(True)
        self.translation_enabled_button.setChecked(enabled)
        self.translation_enabled_button.blockSignals(False)
        self._update_translation_enabled_button_text()

    def _refresh_overview_status(self) -> None:
        ocr_profile = self._get_selected_api_profile_from_role("ocr")
        translation_profile = self._get_selected_api_profile_from_role("translation")

        self.ocr_profile_summary_label.setText(
            ocr_profile.profile_name.strip() or DEFAULT_API_PROFILE_NAME
        )
        self.ocr_model_summary_label.setText(
            ocr_profile.model_name.strip() or "未选择模型"
        )
        self.translation_profile_summary_label.setText(
            translation_profile.profile_name.strip() or DEFAULT_API_PROFILE_NAME
        )
        self.translation_model_summary_label.setText(
            translation_profile.model_name.strip() or "未选择模型"
        )
        self._update_ocr_enabled_button_text()
        self._update_translation_enabled_button_text()
        self._update_display_status_text()

    def _refresh_shortcut_badges(self) -> None:
        while self.shortcut_kbd_layout.count():
            item = self.shortcut_kbd_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        shortcut = (
            self.refresh_shortcut_input.keySequence().toString().strip()
            or DEFAULT_REFRESH_SHORTCUT
        )
        keys = [part.strip() for part in shortcut.split("+") if part.strip()]
        if not keys:
            keys = [DEFAULT_REFRESH_SHORTCUT]

        for index, key in enumerate(keys):
            if index:
                plus = QLabel("+")
                plus.setObjectName("Muted")
                self.shortcut_kbd_layout.addWidget(plus)
            self.shortcut_kbd_layout.addWidget(KbdBadge(key))

    def update_ocr_result(self, text: str) -> None:
        self._ocr_result_text = text.strip()
        self.ocr_result_output.setMarkdown(
            render_markdown_preserving_line_breaks(self._ocr_result_text)
        )

    def clear_ocr_result(self) -> None:
        self._ocr_result_text = ""
        self.ocr_result_output.clear()

    def get_ocr_result_text(self) -> str:
        return self._ocr_result_text

    def set_config(self, config: AppConfig) -> None:
        config.ensure_valid_state()

        self._ocr_api_configs = [
            self._clone_api_config(item) for item in config.ocr_api_configs
        ]
        self._selected_ocr_api_config_id = config.selected_ocr_api_config_id
        self._translation_api_configs = [
            self._clone_api_config(item) for item in config.translation_api_configs
        ]
        self._selected_translation_api_config_id = (
            config.selected_translation_api_config_id
        )
        self._ocr_prompt_template = (
            config.ocr_prompt_template or DEFAULT_OCR_PROMPT_TEMPLATE
        )
        self._translation_prompt_template = (
            config.translation_prompt_template
            or DEFAULT_TRANSLATION_PROMPT_TEMPLATE
        )
        self._target_language = config.target_language or "简体中文"

        self.set_ocr_enabled(config.ocr_enabled)
        self.set_translation_enabled(config.translation_enabled)
        self.refresh_shortcut_input.setKeySequence(
            config.refresh_shortcut or DEFAULT_REFRESH_SHORTCUT
        )
        self.switch_config_role(self._active_config_role, save_current=False)
        self._refresh_shortcut_badges()
        self._refresh_overview_status()

    def get_config(self) -> AppConfig:
        self._sync_active_role_state()

        config = AppConfig(
            ocr_api_configs=[
                self._clone_api_config(item) for item in self._ocr_api_configs
            ],
            selected_ocr_api_config_id=self._selected_ocr_api_config_id,
            translation_api_configs=[
                self._clone_api_config(item)
                for item in self._translation_api_configs
            ],
            selected_translation_api_config_id=self._selected_translation_api_config_id,
            ocr_enabled=self.ocr_enabled_button.isChecked(),
            translation_enabled=self.translation_enabled_button.isChecked(),
            target_language=self._target_language or "简体中文",
            ocr_prompt_template=self._ocr_prompt_template
            or DEFAULT_OCR_PROMPT_TEMPLATE,
            translation_prompt_template=self._translation_prompt_template
            or DEFAULT_TRANSLATION_PROMPT_TEMPLATE,
            refresh_shortcut=self.refresh_shortcut_input.keySequence()
            .toString()
            .strip()
            or DEFAULT_REFRESH_SHORTCUT,
        )
        config.ensure_valid_state()
        return config

    def update_preview(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self._preview_source_pixmap = QPixmap()
            self.preview_label.setText("尚无截图预览")
            self.preview_label.setPixmap(QPixmap())
            return

        self._preview_source_pixmap = QPixmap(pixmap)
        self._render_preview()

    def _render_preview(self) -> None:
        if self._preview_source_pixmap.isNull():
            return
        scaled = self._preview_source_pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)

    def _update_toast_position(self) -> None:
        text = self._toast_label.text().strip()
        if not text:
            return

        font_metrics = QFontMetrics(self._toast_label.font())
        horizontal_padding = 38
        max_width = max(220, self.width() - 44)
        preferred_width = font_metrics.horizontalAdvance(text) + horizontal_padding
        use_single_line = preferred_width <= max_width
        self._toast_label.setWordWrap(not use_single_line)
        self._toast_label.setFixedWidth(
            preferred_width if use_single_line else max_width
        )
        self._toast_label.adjustSize()

        x = max(22, (self.width() - self._toast_label.width()) // 2)
        y = max(22, self.height() - self._toast_label.height() - 58)
        self._toast_label.move(x, y)

    def _hide_toast(self) -> None:
        if not self._toast_label.isVisible():
            return
        self._toast_fade_in.stop()
        self._toast_fade_out.stop()
        self._toast_fade_out.setStartValue(self._toast_opacity.opacity())
        self._toast_fade_out.setEndValue(0.0)
        self._toast_fade_out.start()

    def show_toast(self, message: str, duration_ms: int = 2200) -> None:
        text = message.strip()
        if not text:
            return

        self._toast_hide_timer.stop()
        self._toast_fade_out.stop()
        self._toast_fade_in.stop()
        self._toast_label.setText(text)
        self._update_toast_position()
        self._toast_opacity.setOpacity(0.0)
        self._toast_label.show()
        self._toast_label.raise_()
        self._toast_fade_in.setStartValue(0.0)
        self._toast_fade_in.setEndValue(1.0)
        self._toast_fade_in.start()
        self._toast_hide_timer.start(max(800, int(duration_ms)))

    def resizeEvent(self, event) -> None:
        if hasattr(self, "preview_label") and not self._preview_source_pixmap.isNull():
            self._render_preview()
        if hasattr(self, "_toast_label") and self._toast_label.isVisible():
            self._update_toast_position()
        super().resizeEvent(event)

    def closeEvent(self, event) -> None:
        self.closing.emit(event)
        if event.isAccepted():
            super().closeEvent(event)
