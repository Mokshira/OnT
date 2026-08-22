from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import QFont, QFontMetrics, QPixmap, QTextCursor
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
from .settings_pages import SettingsPages
from .theme import (
    CONTENT_MARGIN,
    NAV_ITEM_SPACING,
    SIDEBAR_COLLAPSED_WIDTH,
    SIDEBAR_TOGGLE_BOTTOM_MARGIN,
    SIDEBAR_TOGGLE_HEIGHT,
    SIDEBAR_TOGGLE_MARGIN,
    SIDEBAR_TOGGLE_MARGIN_COLLAPSED,
    SIDEBAR_TOGGLE_WIDTH,
    SIDEBAR_WIDTH,
    TOAST_BOTTOM_OFFSET,
    apply_window_theme,
)
from .ui_widgets import (
    KbdBadge,
    Pill,
    SidebarNavButton,
    SidebarToggleButton,
    ToggleSwitch,
    apply_line_height,
    refresh_widget_style,
)


class MainWindow(QMainWindow):
    closing = pyqtSignal(object)

    #: 左侧导航（新 UI）：设置不再是弹窗，而是与概览/结果平级的页面。
    NAV_ITEMS = (
        ("overview", "概览"),
        ("results", "识别结果"),
        ("api", "API 服务"),
        ("prompt", "提示词"),
        ("shortcut", "快捷键"),
        ("about", "关于"),
    )
    SETTINGS_PAGE_KEYS = ("api", "prompt", "shortcut", "about")
    #: 设计稿 .result-output 的行高（1.7 → 170%）
    RESULT_LINE_HEIGHT_PERCENT = 170

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
        self._ocr_stream_parts: list[str] = []
        self._is_ocr_streaming = False
        self._preview_source_pixmap = QPixmap()
        self._is_config_drawer_open = False
        self._current_page_key = ""
        self._is_sidebar_collapsed = False
        self._nav_buttons: dict[str, SidebarNavButton] = {}
        self._page_indices: dict[str, int] = {}
        self._page_animation: QPropertyAnimation | None = None
        self._page_effects: dict[int, QGraphicsOpacityEffect] = {}

        self._toast_hide_timer = QTimer(self)
        self._toast_hide_timer.setSingleShot(True)

        self._setup_window()
        self._setup_ui()
        apply_window_theme(self)
        self.switch_config_role("ocr", save_current=False)
        self.show_page("overview", animate=False)

    def _setup_window(self) -> None:
        self.setObjectName("MainWindow")
        self.setWindowTitle("OCR 与翻译助手")
        self.resize(1040, 680)
        self.setMinimumSize(900, 560)

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("AppRoot")
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

        content_area = QFrame()
        content_area.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(
            CONTENT_MARGIN,
            CONTENT_MARGIN,
            CONTENT_MARGIN,
            CONTENT_MARGIN,
        )
        content_layout.setSpacing(0)

        content_card = QFrame()
        content_card.setObjectName("ContentCard")
        self.content_card = content_card
        card_layout = QVBoxLayout(content_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self.settings_pages = SettingsPages(self)

        self.page_stack = QStackedWidget()
        self.overview_page = self._build_overview_page()
        self.results_page = self._build_results_page()
        self._register_page("overview", self.overview_page)
        self._register_page("results", self.results_page)
        for key in self.SETTINGS_PAGE_KEYS:
            self._register_page(key, self.settings_pages.pages[key])

        card_layout.addWidget(self.page_stack)
        content_layout.addWidget(content_card)
        root_layout.addWidget(content_area, 1)

        # 新 UI：收起按钮固定在侧边栏内部的右下角，不再压在分隔线上。
        # 它是侧边栏的浮层子控件（不进入布局），随侧边栏尺寸变化重新定位。
        self.sidebar_toggle_button = SidebarToggleButton(self.sidebar)
        # 按钮靠下对齐、提示条靠内容卡片对齐，而 QMainWindow.resizeEvent 触发时
        # 子控件几何信息可能还是旧值，所以直接监听它们自己的 Resize 事件。
        self.sidebar.installEventFilter(self)
        self.content_card.installEventFilter(self)
        self._sidebar_animation = QVariantAnimation(self)
        self._sidebar_animation.setDuration(180)
        self._sidebar_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._sidebar_animation.valueChanged.connect(self._on_sidebar_width_changed)
        self._update_sidebar_toggle_position()

        self._bind_settings_controls()
        self._connect_ui_signals()
        self._setup_toast()

    # ------------------------------------------------------------------
    # 侧边栏
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setProperty("collapsed", False)
        sidebar.setFixedWidth(SIDEBAR_WIDTH)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(0)
        self._sidebar_layout = layout

        self.brand_label = QLabel("OnT")
        self.brand_label.setObjectName("AppBrand")
        self.brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 设计稿 .app-brand 的 letter-spacing 是 -0.045em（26px 字号约 -1.2px），
        # QSS 无法表达字距，只能在 QFont 上设。
        brand_font = QFont(self.brand_label.font())
        brand_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -1.2)
        self.brand_label.setFont(brand_font)
        layout.addWidget(self.brand_label)
        layout.addSpacing(20)

        nav_container = QWidget()
        nav_container.setObjectName("SidebarNav")
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(NAV_ITEM_SPACING)
        self._nav_layout = nav_layout

        for key, text in self.NAV_ITEMS:
            button = SidebarNavButton(key, text)
            nav_layout.addWidget(button)
            self._nav_buttons[key] = button

        layout.addWidget(nav_container)
        layout.addStretch(1)
        return sidebar

    def _update_sidebar_toggle_position(self, sidebar_width: int | None = None) -> None:
        if not hasattr(self, "sidebar_toggle_button"):
            return
        width = self.sidebar.width() if sidebar_width is None else int(sidebar_width)
        # 新 UI：按钮完全落在侧边栏内部的右下角（坐标相对侧边栏）。
        # 展开时距右 16px，收起后窄栏只剩 52px，距右收到 8px 才能居中。
        margin_right = (
            SIDEBAR_TOGGLE_MARGIN_COLLAPSED
            if self._is_sidebar_collapsed
            else SIDEBAR_TOGGLE_MARGIN
        )
        self.sidebar_toggle_button.move(
            max(0, width - margin_right - SIDEBAR_TOGGLE_WIDTH),
            max(
                0,
                self.sidebar.height()
                - SIDEBAR_TOGGLE_BOTTOM_MARGIN
                - SIDEBAR_TOGGLE_HEIGHT,
            ),
        )
        self.sidebar_toggle_button.raise_()

    def _on_sidebar_width_changed(self, value) -> None:
        width = int(value)
        self.sidebar.setFixedWidth(width)
        self._update_sidebar_toggle_position(width)

    def is_sidebar_collapsed(self) -> bool:
        return self._is_sidebar_collapsed

    def toggle_sidebar(self) -> None:
        self.set_sidebar_collapsed(not self._is_sidebar_collapsed)

    def set_sidebar_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        collapsed = bool(collapsed)
        self._is_sidebar_collapsed = collapsed

        self.sidebar.setProperty("collapsed", collapsed)
        refresh_widget_style(self.sidebar)
        self.brand_label.setVisible(not collapsed)
        self._sidebar_layout.setContentsMargins(
            *((8, 18, 8, 16) if collapsed else (16, 18, 16, 16))
        )
        for button in self._nav_buttons.values():
            button.setCollapsed(collapsed)
        self.sidebar_toggle_button.setCollapsed(collapsed)

        target_width = SIDEBAR_COLLAPSED_WIDTH if collapsed else SIDEBAR_WIDTH
        self._sidebar_animation.stop()
        if animate and self.isVisible():
            self._sidebar_animation.setStartValue(self.sidebar.width())
            self._sidebar_animation.setEndValue(target_width)
            self._sidebar_animation.start()
        else:
            self.sidebar.setFixedWidth(target_width)
            self._update_sidebar_toggle_position(target_width)

    # ------------------------------------------------------------------
    # 内容页
    # ------------------------------------------------------------------
    def _register_page(self, key: str, page: QWidget) -> None:
        self._page_indices[key] = self.page_stack.addWidget(page)

    def _new_content_page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("ContentViewport")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # QScrollArea 默认带一层下沉边框，会在内容卡片里多画一道灰线。
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setObjectName("ContentViewport")
        scroll.viewport().setAutoFillBackground(False)
        viewport = QWidget()
        viewport.setObjectName("ContentViewport")
        content_layout = QVBoxLayout(viewport)
        content_layout.setContentsMargins(26, 24, 26, 26)
        content_layout.setSpacing(0)
        scroll.setWidget(viewport)

        page_layout.addWidget(scroll)
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
        # 新 UI：概览页标题栏的两个操作统一为中性浅色按钮（.overview-head-actions），
        # 不再把「开始框选」做成黑底主按钮。
        self.capture_button.setObjectName("OverviewHeadButton")
        self.capture_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.capture_button.setMinimumWidth(96)
        self.capture_button.setToolTip("打开截图选区工具")

        self.clipboard_button = QPushButton("剪贴板自动处理：已关闭")
        self.clipboard_button.setObjectName("OverviewHeadButton")
        self.clipboard_button.setCheckable(True)
        self.clipboard_button.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.copy_ocr_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_ocr_button.setMinimumWidth(88)
        self.copy_ocr_button.setToolTip("把当前 OCR 原文复制到剪贴板")
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
        # 文档自带 4px 内边距，会叠在 QSS 的 padding 上，让文字对不齐卡片。
        self.ocr_result_output.document().setDocumentMargin(0)
        apply_line_height(self.ocr_result_output, self.RESULT_LINE_HEIGHT_PERCENT)
        text_layout.addWidget(result_title)
        text_layout.addWidget(self.ocr_result_output, 1)

        result_row.addWidget(preview_card, 1)
        result_row.addWidget(result_card, 1)
        layout.addLayout(result_row, 1)
        return page

    def _bind_settings_controls(self) -> None:
        pages = self.settings_pages
        self.api_profile_combo = pages.api_profile_combo
        self.add_api_profile_button = pages.add_api_profile_button
        self.update_api_profile_button = pages.update_api_profile_button
        self.delete_api_profile_button = pages.delete_api_profile_button
        self.api_profile_name_input = pages.api_profile_name_input
        self.api_key_input = pages.api_key_input
        self.toggle_api_key_button = pages.toggle_api_key_button
        self.base_url_input = pages.base_url_input
        self.model_name_combo = pages.model_name_combo
        self.fetch_models_button = pages.fetch_models_button
        self.cancel_fetch_models_button = pages.cancel_fetch_models_button
        self.target_language_input = pages.target_language_input
        self.target_language_row = pages.target_language_row
        self.prompt_input = pages.prompt_input
        self.prompt_label = pages.prompt_label
        self.refresh_shortcut_input = pages.refresh_shortcut_input
        self.refresh_shortcut_hint_label = pages.refresh_shortcut_hint_label

        # 每个设置页底部都有一个「保存设置」按钮；这个不可见的代理按钮把它们
        # 汇聚成 AppController 一直使用的单一 save_button 入口。
        self.save_button = QPushButton("保存设置", self)
        self.save_button.hide()
        pages.saveRequested.connect(self.save_button.click)

        self.ocr_mode_button = pages.role_segment.button("ocr")
        self.translation_mode_button = pages.role_segment.button("translation")
        self.preview_panel = self.results_page

    def _connect_ui_signals(self) -> None:
        for key, button in self._nav_buttons.items():
            button.clicked.connect(
                lambda _checked=False, page_key=key: self.show_page(page_key)
            )
        self.sidebar_toggle_button.clicked.connect(
            lambda _checked=False: self.toggle_sidebar()
        )
        self.settings_pages.roleChanged.connect(self.switch_config_role)
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
        # 新 UI：提示条挂在内容卡片上（.toast-host 位于 .content 内），
        # 而不是整个窗口，因此不会再被侧边栏宽度拉偏。
        self._toast_label = QLabel(self.content_card)
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

    # ------------------------------------------------------------------
    # 导航
    # ------------------------------------------------------------------
    def current_page_key(self) -> str:
        return self._current_page_key

    def show_page(self, key: str, animate: bool = True) -> None:
        if key not in self._page_indices:
            return

        previous_key = self._current_page_key
        if previous_key != key and previous_key in self.SETTINGS_PAGE_KEYS:
            # 离开设置页时回写输入内容，与旧版关闭设置对话框的行为一致。
            self._sync_active_role_state()
            self._refresh_overview_status()
            self._refresh_shortcut_badges()

        self._current_page_key = key
        self._is_config_drawer_open = key in self.SETTINGS_PAGE_KEYS

        index = self._page_indices[key]
        self.page_stack.setCurrentIndex(index)
        for item_key, button in self._nav_buttons.items():
            button.setActive(item_key == key)

        if self._page_animation is not None:
            # stop() 不会发出 finished，这里手动收尾，
            # 否则被打断的那一页会永远停在半透明状态。
            self._page_animation.stop()
            self._page_animation = None
        self._clear_all_page_effects()

        if not animate or not self.isVisible():
            return

        page = self.page_stack.widget(index)
        # QGraphicsOpacityEffect 会把整页改成离屏合成渲染：文字发虚、滚动变重。
        # 因此只在淡入期间挂上它，动画结束立刻摘掉，静态时回到原生渲染。
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.0)
        page.setGraphicsEffect(effect)
        self._page_effects[index] = effect

        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(
            lambda page_index=index: self._clear_page_effect(page_index)
        )
        self._page_animation = animation
        animation.start()

    def _clear_page_effect(self, index: int) -> None:
        """摘掉指定页的透明度特效，让它回到原生渲染路径。"""
        effect = self._page_effects.pop(index, None)
        if effect is None:
            return
        page = self.page_stack.widget(index)
        if page is not None:
            page.setGraphicsEffect(None)

    def _clear_all_page_effects(self) -> None:
        for index in list(self._page_effects.keys()):
            self._clear_page_effect(index)

    def set_models_fetching(self, is_fetching: bool) -> None:
        """同步模型拉取状态，并锁定所有会改变结果绑定目标的入口。"""
        self.fetch_models_button.setEnabled(not is_fetching)
        self.fetch_models_button.setText("正在拉取…" if is_fetching else "拉取模型")
        self.cancel_fetch_models_button.setVisible(is_fetching)
        self.cancel_fetch_models_button.setEnabled(is_fetching)
        self.cancel_fetch_models_button.setText("取消")
        self.model_name_combo.setEnabled(not is_fetching)

        lock_tooltip = "模型拉取进行中，完成或取消后才能切换" if is_fetching else ""
        self.settings_pages.set_role_locked(is_fetching, lock_tooltip)
        self.api_profile_combo.setEnabled(not is_fetching)
        self.api_profile_combo.setToolTip(lock_tooltip)
        self.add_api_profile_button.setEnabled(not is_fetching)
        self.update_api_profile_button.setEnabled(not is_fetching)
        self.delete_api_profile_button.setEnabled(not is_fetching)

    def set_models_fetch_cancelling(self) -> None:
        """取消已发出，保留禁用状态直到后台线程退出。"""
        self.fetch_models_button.setText("正在取消…")
        self.cancel_fetch_models_button.setEnabled(False)
        self.cancel_fetch_models_button.setText("取消中…")

    def set_config_drawer_visible(self, is_visible: bool) -> None:
        """兼容旧接口：设置已内嵌到主窗口，这里改为导航到设置页。"""
        if is_visible:
            self.show_page("api")
        elif self._current_page_key in self.SETTINGS_PAGE_KEYS:
            self.show_page("overview")
        else:
            self._is_config_drawer_open = False

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

    def get_api_profiles_snapshot(
        self,
    ) -> tuple[list[ApiConfig], str, list[ApiConfig], str]:
        """返回两组 Profile 列表及选中 ID 的独立克隆快照。"""
        return (
            [self._clone_api_config(item) for item in self._ocr_api_configs],
            self._selected_ocr_api_config_id,
            [
                self._clone_api_config(item)
                for item in self._translation_api_configs
            ],
            self._selected_translation_api_config_id,
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
        self.settings_pages.set_role(role)

        if role == "ocr":
            self.prompt_label.setText("OCR 提示词")
            self.prompt_input.setPlainText(
                self._ocr_prompt_template or DEFAULT_OCR_PROMPT_TEMPLATE
            )
            self.target_language_row.hide()
            self.fetch_models_button.setToolTip("拉取 OCR 模型列表")
        else:
            self.prompt_label.setText("翻译提示词")
            self.prompt_input.setPlainText(
                self._translation_prompt_template
                or DEFAULT_TRANSLATION_PROMPT_TEMPLATE
            )
            self.target_language_row.show()
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
        # 完整渲染入口：占位提示、错误提示与最终结果都走这里。
        # 流式增量不再走此方法（见 append_ocr_stream_text），因此一次
        # 请求中全文 Markdown 解析渲染只发生一次（请求结束时）。
        self._is_ocr_streaming = False
        self._ocr_stream_parts = []
        self._ocr_result_text = text.strip()
        self.ocr_result_output.setMarkdown(
            render_markdown_preserving_line_breaks(self._ocr_result_text)
        )
        # setMarkdown 会重建文档，行高需要重新应用。
        apply_line_height(self.ocr_result_output, self.RESULT_LINE_HEIGHT_PERCENT)

    def begin_ocr_stream(self) -> None:
        """进入 OCR 流式显示模式：清空旧内容，等待纯文本增量追加。"""
        self._is_ocr_streaming = True
        self._ocr_stream_parts = []
        self._ocr_result_text = ""
        self.ocr_result_output.clear()
        # 流式追加的文本会继承当前段落格式，因此只需在开头设一次行高。
        apply_line_height(self.ocr_result_output, self.RESULT_LINE_HEIGHT_PERCENT)

    def append_ocr_stream_text(self, delta: str) -> None:
        """
        在 OCR 结果文档末尾以纯文本方式追加一段流式增量。

        QTextDocument 的 setMarkdown 没有增量接口，流式期间逐 chunk 全文
        重排是长输出卡顿的根源；这里改用 QTextCursor 在尾部 insertText，
        单次代价只与增量长度成正比。滚动条仅在原本就位于底部时跟随，
        用户上滚阅读时不再被强制复位。请求完成后由 update_ocr_result
        对最终全文做一次 Markdown 渲染。
        """
        if not delta:
            return
        if not self._is_ocr_streaming:
            self.begin_ocr_stream()

        self._ocr_stream_parts.append(delta)

        scroll_bar = self.ocr_result_output.verticalScrollBar()
        should_follow_tail = scroll_bar.value() >= scroll_bar.maximum() - 4

        cursor = QTextCursor(self.ocr_result_output.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(delta)

        if should_follow_tail:
            scroll_bar.setValue(scroll_bar.maximum())

    def clear_ocr_result(self) -> None:
        self._is_ocr_streaming = False
        self._ocr_stream_parts = []
        self._ocr_result_text = ""
        self.ocr_result_output.clear()

    def get_ocr_result_text(self) -> str:
        if self._is_ocr_streaming:
            # 流式进行中：返回已接收增量的拼接结果（例如复制按钮）。
            return "".join(self._ocr_stream_parts).strip()
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

        # 高 DPI 屏上先按逻辑像素缩小会白丢一半分辨率，预览图看起来发虚；
        # 改成按真实设备像素缩放，再把 devicePixelRatio 交回给 Qt。
        # 同时给虚线边框留出 1px，避免图片盖住卡片描边。
        ratio = max(1.0, self.preview_label.devicePixelRatioF())
        label_size = self.preview_label.size()
        target_size = QSize(
            max(1, int(round((label_size.width() - 2) * ratio))),
            max(1, int(round((label_size.height() - 2) * ratio))),
        )
        scaled = self._preview_source_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(ratio)
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)

    def _update_toast_position(self) -> None:
        text = self._toast_label.text().strip()
        if not text:
            return

        # 提示条以内容卡片为参系居中（坐标相对 content_card）。
        card = self.content_card
        font_metrics = QFontMetrics(self._toast_label.font())
        horizontal_padding = 38
        max_width = max(220, card.width() - 44)
        preferred_width = font_metrics.horizontalAdvance(text) + horizontal_padding
        use_single_line = preferred_width <= max_width
        self._toast_label.setWordWrap(not use_single_line)
        self._toast_label.setFixedWidth(
            preferred_width if use_single_line else max_width
        )
        self._toast_label.adjustSize()

        x = max(12, (card.width() - self._toast_label.width()) // 2)
        y = max(
            12,
            card.height() - self._toast_label.height() - TOAST_BOTTOM_OFFSET,
        )
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

    def eventFilter(self, watched, event) -> bool:
        # 侧边栏收起按钮靠底对齐、提示条靠内容卡片居中，两者都依赖
        # 宿主控件的最新几何尺寸，因此在宿主自身 Resize 时重算位置。
        if event.type() == QEvent.Type.Resize:
            if watched is getattr(self, "sidebar", None):
                self._update_sidebar_toggle_position()
            elif watched is getattr(self, "content_card", None):
                if hasattr(self, "_toast_label") and self._toast_label.isVisible():
                    self._update_toast_position()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        if hasattr(self, "preview_label") and not self._preview_source_pixmap.isNull():
            self._render_preview()
        if hasattr(self, "_toast_label") and self._toast_label.isVisible():
            self._update_toast_position()
        self._update_sidebar_toggle_position()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_sidebar_toggle_position()

    def closeEvent(self, event) -> None:
        self.closing.emit(event)
        if event.isAccepted():
            super().closeEvent(event)
