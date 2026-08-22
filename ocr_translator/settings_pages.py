from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .config_manager import DEFAULT_MODEL_NAME, DEFAULT_REFRESH_SHORTCUT
from .ui_widgets import (
    Pill,
    PromptTextEdit,
    SegmentedControl,
    ShortcutCaptureEdit,
    StyledComboBox,
)


class SettingsPages(QObject):
    """新 UI 的窗口内设置页面（API 服务 / 提示词 / 快捷键 / 关于）。

    设置不再使用独立的模态对话框：这些页面会被主窗口放进同一个内容卡片里，
    由左侧导航切换。持久化仍然完全交给 AppController，这里只负责界面。
    """

    #: 任意设置页底部的「保存设置」被点击
    saveRequested = pyqtSignal()
    #: API 页或提示词页切换了服务（ocr / translation）
    roleChanged = pyqtSignal(str)

    PAGE_KEYS = ("api", "prompt", "shortcut", "about")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.save_buttons: list[QPushButton] = []
        self.pages: dict[str, QWidget] = {}

        self.pages["api"] = self._build_api_page()
        self.pages["prompt"] = self._build_prompt_page()
        self.pages["shortcut"] = self._build_shortcut_page()
        self.pages["about"] = self._build_about_page()

        self.role_segment.selectionChanged.connect(self._on_role_selected)
        self.prompt_service_segment.selectionChanged.connect(self._on_role_selected)

    # ------------------------------------------------------------------
    # 角色（OCR / 翻译）切换
    # ------------------------------------------------------------------
    def _on_role_selected(self, role: str) -> None:
        self.roleChanged.emit(role)

    def set_role(self, role: str) -> None:
        """同步两处服务切换控件，不触发信号。"""
        self.role_segment.setCurrentKey(role, emit_signal=False)
        self.prompt_service_segment.setCurrentKey(role, emit_signal=False)

    def set_role_locked(self, locked: bool, tooltip: str = "") -> None:
        """模型拉取期间锁定服务切换，避免结果绑定到错误的服务。"""
        for segment in (self.role_segment, self.prompt_service_segment):
            segment.setEnabled(not locked)
            segment.setToolTip(tooltip)

    # ------------------------------------------------------------------
    # 页面骨架
    # ------------------------------------------------------------------
    def _page_scaffold(
        self,
        eyebrow_text: str,
        title_text: str,
        description_text: str,
        with_save: bool = True,
    ) -> tuple[QWidget, QVBoxLayout]:
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
        scroll.viewport().setObjectName("SettingsPageViewport")
        scroll.viewport().setAutoFillBackground(False)

        viewport = QWidget()
        viewport.setObjectName("SettingsPageViewport")
        scroll.setWidget(viewport)

        layout = QVBoxLayout(viewport)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(0)

        eyebrow = QLabel(eyebrow_text)
        eyebrow.setObjectName("Eyebrow")
        title = QLabel(title_text)
        title.setObjectName("PageTitle")
        description = QLabel(description_text)
        description.setObjectName("PageDescription")
        description.setWordWrap(True)

        layout.addWidget(eyebrow)
        layout.addSpacing(4)
        layout.addWidget(title)
        layout.addSpacing(6)
        layout.addWidget(description)
        layout.addSpacing(18)

        page_layout.addWidget(scroll, 1)

        if with_save:
            page_layout.addWidget(self._build_actions_bar())

        return page, layout

    def _build_actions_bar(self) -> QFrame:
        actions = QFrame()
        actions.setObjectName("SettingsPageActions")
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(26, 12, 26, 16)
        actions_layout.setSpacing(8)
        actions_layout.addStretch(1)

        save_button = QPushButton("保存设置")
        save_button.setProperty("variant", "blue")
        save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        save_button.setMinimumWidth(96)
        save_button.setToolTip("验证并保存当前 OCR、翻译和快捷键配置")
        save_button.clicked.connect(lambda _checked=False: self.saveRequested.emit())
        actions_layout.addWidget(save_button)

        self.save_buttons.append(save_button)
        return actions

    def _settings_row(
        self,
        title: str,
        description: str,
        control: QWidget,
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("SettingsRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 12, 0, 12)
        row_layout.setSpacing(16)

        label_column = QWidget()
        label_column.setObjectName("FieldGroup")
        label_column.setFixedWidth(180)
        label_layout = QVBoxLayout(label_column)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.setSpacing(3)

        label = QLabel(title)
        label.setObjectName("RowLabel")
        detail = QLabel(description)
        detail.setObjectName("RowDescription")
        detail.setWordWrap(True)
        label_layout.addWidget(label)
        label_layout.addWidget(detail)

        control.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            control.sizePolicy().verticalPolicy(),
        )
        row_layout.addWidget(label_column)
        row_layout.addWidget(control, 1)
        return row

    @staticmethod
    def _inline_group(spacing: int = 8) -> tuple[QWidget, QHBoxLayout]:
        """设计稿中的 .row-inline：控件与操作按钮同一行。"""
        group = QWidget()
        group.setObjectName("FieldGroup")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        return group, layout

    @staticmethod
    def _field_group(spacing: int = 8) -> tuple[QWidget, QVBoxLayout]:
        group = QWidget()
        group.setObjectName("FieldGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        return group, layout

    # ------------------------------------------------------------------
    # API 服务
    # ------------------------------------------------------------------
    def _build_api_page(self) -> QWidget:
        page, layout = self._page_scaffold(
            "CONNECTIONS",
            "API 服务",
            "分别管理 OCR 与翻译服务的配置档、连接参数和模型。",
        )

        self.role_segment = SegmentedControl(
            [("ocr", "OCR 识别"), ("translation", "翻译")]
        )
        role_holder, role_layout = self._inline_group()
        role_layout.addWidget(self.role_segment)
        role_layout.addStretch(1)
        layout.addWidget(
            self._settings_row(
                "配置用途",
                "切换后显示对应服务的独立配置",
                role_holder,
            )
        )

        profile_group, profile_layout = self._inline_group(8)
        self.api_profile_combo = StyledComboBox()
        self.add_api_profile_button = QPushButton("新增")
        self.add_api_profile_button.setProperty("variant", "soft")
        self.update_api_profile_button = QPushButton("更新")
        self.update_api_profile_button.setProperty("variant", "soft")
        self.delete_api_profile_button = QPushButton("删除")
        self.delete_api_profile_button.setProperty("variant", "danger")
        for compact_button in (
            self.add_api_profile_button,
            self.update_api_profile_button,
            self.delete_api_profile_button,
        ):
            # 设计稿里这组按钮宽度一致，不随文字长度变形。
            compact_button.setMinimumWidth(60)
            compact_button.setCursor(Qt.CursorShape.PointingHandCursor)
        profile_layout.addWidget(self.api_profile_combo, 1)
        profile_layout.addWidget(self.add_api_profile_button)
        profile_layout.addWidget(self.update_api_profile_button)
        profile_layout.addWidget(self.delete_api_profile_button)
        layout.addWidget(
            self._settings_row(
                "已保存配置",
                "选择、创建或维护 API 配置档",
                profile_group,
            )
        )

        self.api_profile_name_input = QLineEdit()
        self.api_profile_name_input.setPlaceholderText("例如：工作区 OCR")
        layout.addWidget(
            self._settings_row(
                "配置名称",
                "用于在配置档列表中识别此连接",
                self.api_profile_name_input,
            )
        )

        api_key_group, api_key_layout = self._inline_group()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("输入访问密钥")
        self.toggle_api_key_button = QPushButton("显示")
        self.toggle_api_key_button.setProperty("variant", "ghost")
        self.toggle_api_key_button.setMinimumWidth(60)
        self.toggle_api_key_button.setCursor(Qt.CursorShape.PointingHandCursor)
        api_key_layout.addWidget(self.api_key_input, 1)
        api_key_layout.addWidget(self.toggle_api_key_button)
        layout.addWidget(
            self._settings_row(
                "API Key",
                "访问服务所需的密钥，仅保存在本地",
                api_key_group,
            )
        )

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.example.com/v1")
        layout.addWidget(
            self._settings_row(
                "Base URL",
                "OpenAI 兼容 API 的基础地址",
                self.base_url_input,
            )
        )

        model_group, model_layout = self._inline_group()
        self.model_name_combo = StyledComboBox()
        self.model_name_combo.setEditable(True)
        self.model_name_combo.addItems(
            [
                "gpt-4o",
                "gpt-4.1",
                "gpt-5",
                "gemini-1.5-pro",
                "qwen-vl-plus",
            ]
        )
        self.model_name_combo.setCurrentText(DEFAULT_MODEL_NAME)
        self.fetch_models_button = QPushButton("拉取模型")
        self.fetch_models_button.setProperty("variant", "ghost")
        self.fetch_models_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fetch_models_button.setMinimumWidth(84)
        self.cancel_fetch_models_button = QPushButton("取消")
        self.cancel_fetch_models_button.setProperty("variant", "ghost")
        self.cancel_fetch_models_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_fetch_models_button.setMinimumWidth(60)
        self.cancel_fetch_models_button.hide()
        model_layout.addWidget(self.model_name_combo, 1)
        model_layout.addWidget(self.fetch_models_button)
        model_layout.addWidget(self.cancel_fetch_models_button)
        layout.addWidget(
            self._settings_row(
                "模型",
                "可直接输入，或从当前服务拉取列表",
                model_group,
            )
        )

        self.target_language_input = QLineEdit()
        self.target_language_input.setPlaceholderText(
            "例如：简体中文、English、日本語"
        )
        self.target_language_row = self._settings_row(
            "目标语言",
            "仅用于翻译服务",
            self.target_language_input,
        )
        layout.addWidget(self.target_language_row)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # 提示词
    # ------------------------------------------------------------------
    def _build_prompt_page(self) -> QWidget:
        page, layout = self._page_scaffold(
            "PROMPTS",
            "提示词",
            "编辑当前服务使用的提示词；OCR 与翻译内容会分别保存。",
        )

        service_row = QHBoxLayout()
        service_row.setSpacing(10)
        service_label = QLabel("当前服务")
        service_label.setObjectName("RowLabel")
        self.prompt_service_segment = SegmentedControl(
            [("ocr", "OCR 识别"), ("translation", "翻译")]
        )
        service_row.addWidget(service_label)
        service_row.addWidget(self.prompt_service_segment)
        service_row.addStretch(1)
        layout.addLayout(service_row)
        layout.addSpacing(16)

        self.prompt_label = QLabel("OCR 提示词")
        self.prompt_label.setObjectName("SectionTitle")
        layout.addWidget(self.prompt_label)
        layout.addSpacing(8)

        self.prompt_input = PromptTextEdit()
        self.prompt_input.setMinimumHeight(220)
        self.prompt_input.setPlaceholderText("输入发送给模型的提示词")
        layout.addWidget(self.prompt_input, 1)
        layout.addSpacing(8)

        prompt_hint = QLabel("保存设置后，新请求将使用这里的内容。")
        prompt_hint.setObjectName("Hint")
        layout.addWidget(prompt_hint)
        return page

    # ------------------------------------------------------------------
    # 快捷键
    # ------------------------------------------------------------------
    def _build_shortcut_page(self) -> QWidget:
        page, layout = self._page_scaffold(
            "KEYBOARD",
            "快捷键",
            "设置从任意应用触发截图识别的全局快捷键。",
        )

        self.refresh_shortcut_hint_label = QLabel()
        self.refresh_shortcut_hint_label.setObjectName("Hint")
        self.refresh_shortcut_input = ShortcutCaptureEdit(
            self.refresh_shortcut_hint_label
        )
        self.refresh_shortcut_input.setKeySequence(DEFAULT_REFRESH_SHORTCUT)

        shortcut_group, shortcut_layout = self._field_group(6)
        shortcut_layout.addWidget(self.refresh_shortcut_input)
        shortcut_layout.addWidget(self.refresh_shortcut_hint_label)
        self.refresh_shortcut_row = self._settings_row(
            "截图快捷键",
            "保存时会重新注册全局快捷键",
            shortcut_group,
        )
        layout.addWidget(self.refresh_shortcut_row)

        note = QFrame()
        # 新 UI：「快捷键冲突」属于警示类提醒，改用橙色 NoteCard（.note-card），
        # 与蓝色的普通说明卡 HintCard 区分开。
        note.setObjectName("NoteCard")
        note_layout = QVBoxLayout(note)
        note_layout.setContentsMargins(14, 12, 14, 12)
        note_layout.setSpacing(4)
        note_title = QLabel("快捷键冲突")
        note_title.setObjectName("CardTitle")
        note_text = QLabel(
            "若组合键已被其他应用占用，保存会失败并恢复原有快捷键。"
        )
        note_text.setObjectName("CardDetail")
        note_text.setWordWrap(True)
        note_layout.addWidget(note_title)
        note_layout.addWidget(note_text)
        layout.addSpacing(14)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # 关于
    # ------------------------------------------------------------------
    def _build_about_page(self) -> QWidget:
        page, layout = self._page_scaffold(
            "ABOUT",
            "关于",
            "应用信息与当前界面版本。",
            with_save=False,
        )

        panel = QFrame()
        panel.setObjectName("AboutPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(8)

        app_name = QLabel("OnT")
        app_name.setObjectName("PageTitle")
        version = Pill("v1.0.0", "outline")
        description = QLabel(
            "基于 PyQt6 的截图 OCR 与翻译工具，支持独立的识别和翻译服务配置。"
        )
        description.setObjectName("PageDescription")
        description.setWordWrap(True)
        stack_label = QLabel("PyQt6 Widgets · OpenAI 兼容 API")
        stack_label.setObjectName("Muted")

        panel_layout.addWidget(app_name)
        panel_layout.addWidget(version)
        panel_layout.addSpacing(6)
        panel_layout.addWidget(description)
        panel_layout.addWidget(stack_label)
        layout.addWidget(panel)
        layout.addStretch(1)
        return page
