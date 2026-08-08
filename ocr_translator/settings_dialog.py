from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .config_manager import DEFAULT_MODEL_NAME, DEFAULT_REFRESH_SHORTCUT
from .theme import apply_window_theme
from .ui_widgets import (
    Pill,
    SegmentedControl,
    ShortcutCaptureEdit,
    StyledComboBox,
    refresh_widget_style,
)


class SettingsDialog(QDialog):
    """Window-scoped settings surface; persistence stays in AppController."""

    PAGE_KEYS = ("api", "prompt", "shortcut", "about")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("OnT 设置")
        self.setModal(True)
        self.setFixedSize(720, 540)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._page_indices: dict[str, int] = {}
        self._setup_ui()
        apply_window_theme(self)
        self.show_page("api")

    def _setup_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("SettingsRoot")

        dialog_layout = QHBoxLayout(self)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.setSpacing(0)
        dialog_layout.addWidget(root)

        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        rail = self._build_navigation_rail()
        root_layout.addWidget(rail)

        content = QWidget()
        content.setObjectName("ContentViewport")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.page_stack = QStackedWidget()
        self._add_page("api", self._build_api_page())
        self._add_page("prompt", self._build_prompt_page())
        self._add_page("shortcut", self._build_shortcut_page())
        self._add_page("about", self._build_about_page())
        content_layout.addWidget(self.page_stack, 1)

        footer = QFrame()
        footer.setObjectName("SettingsFooter")
        footer.setFixedHeight(60)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 12, 24, 12)
        footer_layout.setSpacing(8)
        footer_layout.addStretch(1)

        self.close_button = QPushButton("关闭")
        self.close_button.setProperty("variant", "ghost")
        self.close_button.clicked.connect(self.reject)

        self.save_button = QPushButton("保存设置")
        self.save_button.setProperty("variant", "blue")
        self.save_button.setToolTip("验证并保存当前 OCR、翻译和快捷键配置")

        footer_layout.addWidget(self.close_button)
        footer_layout.addWidget(self.save_button)
        content_layout.addWidget(footer)
        root_layout.addWidget(content, 1)

    def _build_navigation_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("SettingsRail")
        rail.setFixedWidth(200)

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(4)

        eyebrow = QLabel("ONT PREFERENCES")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("设置")
        title.setObjectName("BrandName")
        layout.addWidget(eyebrow)
        layout.addSpacing(3)
        layout.addWidget(title)
        layout.addSpacing(20)

        items = (
            ("api", "API 服务"),
            ("prompt", "提示词"),
            ("shortcut", "快捷键"),
            ("about", "关于"),
        )
        for key, text in items:
            button = QPushButton(text)
            button.setObjectName("SettingsNavItem")
            button.setProperty("active", False)
            button.clicked.connect(
                lambda _checked=False, selected_key=key: self.show_page(
                    selected_key
                )
            )
            layout.addWidget(button)
            self._nav_buttons[key] = button

        layout.addStretch(1)
        version = QLabel("OnT  v1.0.0")
        version.setObjectName("Muted")
        layout.addWidget(version)
        return rail

    def _add_page(self, key: str, page: QWidget) -> None:
        self._page_indices[key] = self.page_stack.addWidget(page)

    def _page_scaffold(
        self,
        eyebrow_text: str,
        title_text: str,
        description_text: str,
    ) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        viewport = QWidget()
        viewport.setObjectName("SettingsPageViewport")
        scroll.setWidget(viewport)

        layout = QVBoxLayout(viewport)
        layout.setContentsMargins(24, 22, 24, 22)
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
        return scroll, layout

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
    def _field_group(spacing: int = 8) -> tuple[QWidget, QVBoxLayout]:
        group = QWidget()
        group.setObjectName("FieldGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        return group, layout

    def _build_api_page(self) -> QWidget:
        page, layout = self._page_scaffold(
            "CONNECTIONS",
            "API 服务",
            "分别管理 OCR 与翻译服务的配置档、连接参数和模型。",
        )

        self.role_segment = SegmentedControl(
            [("ocr", "OCR 识别"), ("translation", "翻译")]
        )
        self.role_context_label = QLabel("正在编辑 OCR 识别服务")
        self.role_context_label.setObjectName("Hint")
        role_group, role_layout = self._field_group(6)
        role_layout.addWidget(self.role_segment)
        role_layout.addWidget(self.role_context_label)
        layout.addWidget(
            self._settings_row(
                "配置用途",
                "切换后显示对应服务的独立配置",
                role_group,
            )
        )

        profile_group, profile_layout = self._field_group(8)
        self.api_profile_combo = StyledComboBox()
        profile_layout.addWidget(self.api_profile_combo)

        profile_actions = QWidget()
        profile_actions.setObjectName("FieldGroup")
        profile_actions_layout = QHBoxLayout(profile_actions)
        profile_actions_layout.setContentsMargins(0, 0, 0, 0)
        profile_actions_layout.setSpacing(6)

        self.add_api_profile_button = QPushButton("新增")
        self.add_api_profile_button.setProperty("variant", "soft")
        self.update_api_profile_button = QPushButton("更新")
        self.update_api_profile_button.setProperty("variant", "soft")
        self.delete_api_profile_button = QPushButton("删除")
        self.delete_api_profile_button.setProperty("variant", "danger")
        profile_actions_layout.addWidget(self.add_api_profile_button)
        profile_actions_layout.addWidget(self.update_api_profile_button)
        profile_actions_layout.addWidget(self.delete_api_profile_button)
        profile_layout.addWidget(profile_actions)
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

        api_key_group = QWidget()
        api_key_group.setObjectName("FieldGroup")
        api_key_layout = QHBoxLayout(api_key_group)
        api_key_layout.setContentsMargins(0, 0, 0, 0)
        api_key_layout.setSpacing(8)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("输入访问密钥")
        self.toggle_api_key_button = QPushButton("显示")
        self.toggle_api_key_button.setProperty("variant", "ghost")
        self.toggle_api_key_button.setMinimumWidth(58)
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

        model_group, model_layout = self._field_group(8)
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
        self.cancel_fetch_models_button = QPushButton("取消")
        self.cancel_fetch_models_button.setProperty("variant", "ghost")
        self.cancel_fetch_models_button.hide()
        model_layout.addWidget(self.model_name_combo)

        model_actions = QWidget()
        model_actions.setObjectName("FieldGroup")
        model_actions_layout = QHBoxLayout(model_actions)
        model_actions_layout.setContentsMargins(0, 0, 0, 0)
        model_actions_layout.setSpacing(6)
        model_actions_layout.addWidget(self.fetch_models_button)
        model_actions_layout.addWidget(self.cancel_fetch_models_button)
        model_actions_layout.addStretch(1)
        model_layout.addWidget(model_actions)
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

    def _build_prompt_page(self) -> QWidget:
        page, layout = self._page_scaffold(
            "PROMPTS",
            "提示词",
            "编辑当前服务使用的提示词；OCR 与翻译内容会分别保存。",
        )

        role_row = QHBoxLayout()
        role_row.setSpacing(8)
        role_label = QLabel("当前服务")
        role_label.setObjectName("RowLabel")
        self.prompt_role_pill = Pill("OCR 识别", "blue")
        role_row.addWidget(role_label)
        role_row.addWidget(self.prompt_role_pill)
        role_row.addStretch(1)
        layout.addLayout(role_row)
        layout.addSpacing(12)

        self.prompt_label = QLabel("OCR 提示词")
        self.prompt_label.setObjectName("SectionTitle")
        layout.addWidget(self.prompt_label)
        layout.addSpacing(8)

        self.prompt_input = QPlainTextEdit()
        self.prompt_input.setMinimumHeight(285)
        self.prompt_input.setPlaceholderText("输入发送给模型的提示词")
        layout.addWidget(self.prompt_input, 1)
        layout.addSpacing(8)

        prompt_hint = QLabel("保存设置后，新请求将使用这里的内容。")
        prompt_hint.setObjectName("Hint")
        layout.addWidget(prompt_hint)
        return page

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
        note.setObjectName("HintCard")
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

    def _build_about_page(self) -> QWidget:
        page, layout = self._page_scaffold(
            "ABOUT",
            "关于",
            "应用信息与当前界面版本。",
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

    def show_page(self, key: str) -> None:
        if key not in self._page_indices:
            return
        self.page_stack.setCurrentIndex(self._page_indices[key])
        for item_key, button in self._nav_buttons.items():
            button.setProperty("active", item_key == key)
            refresh_widget_style(button)
