from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .config_manager import (
    ApiConfig,
    AppConfig,
    DEFAULT_API_PROFILE_NAME,
    DEFAULT_MODEL_NAME,
    DEFAULT_OCR_PROMPT_TEMPLATE,
    DEFAULT_REFRESH_SHORTCUT,
    DEFAULT_TRANSLATION_PROMPT_TEMPLATE,
)
from .ui_widgets import ShortcutCaptureEdit, StyledComboBox


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
        self._toast_hide_timer = QTimer(self)
        self._toast_hide_timer.setSingleShot(True)
        self._is_config_drawer_open = False
        self._setup_window()
        self._setup_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle("OCR 与翻译助手")
        self.resize(980, 640)
        self.setMinimumSize(900, 560)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)

        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root_layout.addWidget(main_scroll)

        content_widget = QWidget()
        main_scroll.setWidget(content_widget)

        outer_layout = QVBoxLayout(content_widget)
        outer_layout.setContentsMargins(16, 16, 16, 16)
        outer_layout.setSpacing(12)

        top_switch_row = QHBoxLayout()
        top_switch_row.setSpacing(10)

        self.ocr_mode_button = QPushButton("识别配置")
        self.ocr_mode_button.setObjectName("SecondaryButton")
        self.ocr_mode_button.setCheckable(True)
        self.ocr_mode_button.clicked.connect(
            lambda: self._open_config_drawer_for_role("ocr")
        )

        self.translation_mode_button = QPushButton("翻译配置")
        self.translation_mode_button.setObjectName("SecondaryButton")
        self.translation_mode_button.setCheckable(True)
        self.translation_mode_button.clicked.connect(
            lambda: self._open_config_drawer_for_role("translation")
        )

        self.top_mode_hint_label = QLabel()
        self.top_mode_hint_label.setObjectName("Desc")
        self.top_mode_hint_label.setWordWrap(True)

        self.drawer_toggle_button = QPushButton("展开设置")
        self.drawer_toggle_button.setObjectName("SecondaryButton")
        self.drawer_toggle_button.clicked.connect(
            lambda: self.set_config_drawer_visible(not self._is_config_drawer_open)
        )

        top_switch_row.addWidget(self.ocr_mode_button)
        top_switch_row.addWidget(self.translation_mode_button)
        top_switch_row.addSpacing(8)
        top_switch_row.addWidget(self.top_mode_hint_label, 1)
        top_switch_row.addWidget(self.drawer_toggle_button)

        self.config_drawer_panel = self._build_config_panel()
        self.preview_panel = self._build_preview_panel()
        self.preview_panel.setMinimumWidth(360)

        outer_layout.addLayout(top_switch_row)
        outer_layout.addWidget(self.config_drawer_panel)
        outer_layout.addWidget(self.preview_panel, 1)

        self._toast_label = QLabel(self)
        self._toast_label.hide()
        self._toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast_label.setWordWrap(False)
        self._toast_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._toast_label.setStyleSheet(
            """
            QLabel {
                background: rgba(15, 23, 42, 220);
                color: white;
                border-radius: 12px;
                padding: 10px 18px;
                font-size: 13px;
                font-weight: 700;
            }
            """
        )
        self._toast_hide_timer.timeout.connect(self._toast_label.hide)

        self.setStyleSheet(
            """
            QMainWindow {
                background: #eef3fb;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QFrame#Card {
                background: #ffffff;
                border: 1px solid #d8e1ef;
                border-radius: 14px;
            }
            QLabel#Title {
                font-size: 20px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#Desc {
                color: #64748b;
                font-size: 12px;
            }
            QLabel#Hint {
                color: #64748b;
                font-size: 12px;
            }
            QLabel#SectionTitle {
                font-size: 14px;
                font-weight: 700;
                color: #1e293b;
                margin-top: 4px;
            }
            QLabel {
                color: #334155;
                font-size: 13px;
            }
            QLineEdit, QPlainTextEdit, QComboBox, QKeySequenceEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 8px 10px;
                font-size: 13px;
                color: #111827;
            }
            QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QKeySequenceEdit:focus {
                border: 1px solid #3b82f6;
            }
            QComboBox {
                min-height: 20px;
                padding-right: 32px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background: white;
                border: 1px solid #cbd5e1;
                selection-background-color: #dbeafe;
                selection-color: #111827;
                outline: none;
            }
            QPushButton {
                border: none;
                border-radius: 10px;
                padding: 10px 16px;
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton#PrimaryButton {
                background: #2563eb;
                color: white;
            }
            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }
            QPushButton#PrimaryButton:pressed {
                background: #1e40af;
            }
            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
            }
            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }
            QPushButton#SecondaryButton:checked {
                background: #dbeafe;
                color: #1d4ed8;
            }
            """
        )

        self.switch_config_role("ocr", save_current=False)
        self.set_config_drawer_visible(False)

    def _build_config_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.config_title_label = QLabel("识别配置")
        self.config_title_label.setObjectName("Title")
        layout.addWidget(self.config_title_label)

        self.config_desc_label = QLabel()
        self.config_desc_label.setObjectName("Desc")
        self.config_desc_label.setWordWrap(True)
        layout.addWidget(self.config_desc_label)

        section_label = QLabel("API 配置管理")
        section_label.setObjectName("SectionTitle")
        layout.addWidget(section_label)

        self.api_profile_list_label = QLabel("已保存配置")
        layout.addWidget(self.api_profile_list_label)

        api_profile_row = QHBoxLayout()
        api_profile_row.setSpacing(8)

        self.api_profile_combo = StyledComboBox()
        self.api_profile_combo.currentIndexChanged.connect(
            self.on_api_profile_selection_changed
        )

        self.add_api_profile_button = QPushButton("新增")
        self.add_api_profile_button.setObjectName("SecondaryButton")

        self.update_api_profile_button = QPushButton("更新")
        self.update_api_profile_button.setObjectName("SecondaryButton")

        self.delete_api_profile_button = QPushButton("删除")
        self.delete_api_profile_button.setObjectName("SecondaryButton")

        api_profile_row.addWidget(self.api_profile_combo, 1)
        api_profile_row.addWidget(self.add_api_profile_button)
        api_profile_row.addWidget(self.update_api_profile_button)
        api_profile_row.addWidget(self.delete_api_profile_button)
        layout.addLayout(api_profile_row)

        self.api_profile_name_label = QLabel("配置名称")
        layout.addWidget(self.api_profile_name_label)

        self.api_profile_name_input = QLineEdit()
        layout.addWidget(self.api_profile_name_input)

        self.api_section_title_label = QLabel("当前 API 连接参数")
        self.api_section_title_label.setObjectName("SectionTitle")
        layout.addWidget(self.api_section_title_label)

        self.api_key_label = QLabel("API Key（访问密钥）")
        layout.addWidget(self.api_key_label)

        api_key_row = QHBoxLayout()
        api_key_row.setSpacing(10)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.toggle_api_key_button = QPushButton("显示密钥")
        self.toggle_api_key_button.setObjectName("SecondaryButton")
        self.toggle_api_key_button.setMinimumWidth(88)
        self.toggle_api_key_button.clicked.connect(self.toggle_api_key_visibility)

        api_key_row.addWidget(self.api_key_input, 1)
        api_key_row.addWidget(self.toggle_api_key_button)
        layout.addLayout(api_key_row)

        self.base_url_label = QLabel("API Base URL")
        layout.addWidget(self.base_url_label)

        self.base_url_input = QLineEdit()
        layout.addWidget(self.base_url_input)

        self.model_name_label = QLabel("模型名称")
        layout.addWidget(self.model_name_label)

        model_row = QHBoxLayout()
        model_row.setSpacing(10)

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
        self.fetch_models_button.setObjectName("SecondaryButton")

        model_row.addWidget(self.model_name_combo, 1)
        model_row.addWidget(self.fetch_models_button)
        layout.addLayout(model_row)

        self.target_language_label = QLabel("翻译目标语言")
        layout.addWidget(self.target_language_label)

        self.target_language_input = QLineEdit()
        self.target_language_input.setPlaceholderText("例如：简体中文、English、日本語")
        layout.addWidget(self.target_language_input)

        self.prompt_label = QLabel("提示词（Prompt）")
        layout.addWidget(self.prompt_label)

        self.prompt_input = QPlainTextEdit()
        self.prompt_input.setMinimumHeight(180)
        self.prompt_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.prompt_input, 1)

        layout.addStretch(1)

        return card

    def _build_preview_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("OCR和翻译并行")
        title.setObjectName("Title")
        layout.addWidget(title)

        first_row = QHBoxLayout()
        first_row.setSpacing(12)
        unified_box_height = 220

        preview_column = QVBoxLayout()
        preview_column.setSpacing(8)
        preview_title = QLabel("截图预览")
        preview_title.setObjectName("SectionTitle")
        preview_column.addWidget(preview_title)

        self.preview_label = QLabel("尚无截图预览")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumWidth(240)
        self.preview_label.setFixedHeight(unified_box_height)
        self.preview_label.setStyleSheet(
            """
            QLabel {
                background: #edf2f7;
                border: 2px dashed #bfd0ea;
                border-radius: 14px;
                color: #64748b;
                font-size: 14px;
                font-weight: 600;
            }
            """
        )
        preview_column.addWidget(self.preview_label, 1)

        ocr_column = QVBoxLayout()
        ocr_column.setSpacing(8)
        ocr_title = QLabel("OCR 识别结果")
        ocr_title.setObjectName("SectionTitle")
        ocr_column.addWidget(ocr_title)

        self.ocr_result_output = QPlainTextEdit()
        self.ocr_result_output.setReadOnly(True)
        self.ocr_result_output.setPlaceholderText(
            "截图后的 OCR 结果将在这里显示，可用于提取数学公式或原文。"
        )
        self.ocr_result_output.setFixedHeight(unified_box_height)
        ocr_column.addWidget(self.ocr_result_output, 1)

        first_row.addLayout(preview_column, 1)
        first_row.addLayout(ocr_column, 1)
        layout.addLayout(first_row, 1)

        shortcut_title = QLabel("快捷键与快捷操作")
        shortcut_title.setObjectName("SectionTitle")
        layout.addWidget(shortcut_title)

        shortcut_row = QHBoxLayout()
        shortcut_row.setSpacing(10)

        self.refresh_shortcut_label = QLabel("刷新快捷键（全局）")
        self.refresh_shortcut_label.setMinimumWidth(120)

        self.refresh_shortcut_hint_label = QLabel()
        self.refresh_shortcut_hint_label.setObjectName("Hint")

        self.refresh_shortcut_input = ShortcutCaptureEdit(
            self.refresh_shortcut_hint_label
        )
        self.refresh_shortcut_input.setKeySequence(DEFAULT_REFRESH_SHORTCUT)

        shortcut_row.addWidget(self.refresh_shortcut_label)
        shortcut_row.addWidget(self.refresh_shortcut_input, 1)
        layout.addLayout(shortcut_row)
        layout.addWidget(self.refresh_shortcut_hint_label)

        self.copy_ocr_button = QPushButton("复制 OCR 结果")
        self.copy_ocr_button.setObjectName("SecondaryButton")

        self.ocr_enabled_button = QPushButton("OCR：开")
        self.ocr_enabled_button.setObjectName("SecondaryButton")
        self.ocr_enabled_button.setCheckable(True)
        self.ocr_enabled_button.setChecked(True)
        self.ocr_enabled_button.clicked.connect(self._update_ocr_enabled_button_text)

        self.translation_enabled_button = QPushButton("翻译：开")
        self.translation_enabled_button.setObjectName("SecondaryButton")
        self.translation_enabled_button.setCheckable(True)
        self.translation_enabled_button.setChecked(True)
        self.translation_enabled_button.clicked.connect(
            self._update_translation_enabled_button_text
        )

        self.save_button = QPushButton("保存配置")
        self.save_button.setObjectName("SecondaryButton")

        self.capture_button = QPushButton("框选")
        self.capture_button.setObjectName("PrimaryButton")

        self.clipboard_button = QPushButton("剪贴板自动处理：已关闭")
        self.clipboard_button.setObjectName("SecondaryButton")
        self.clipboard_button.setCheckable(True)

        self.display_toggle_button = QPushButton("翻译显示区：已开启")
        self.display_toggle_button.setObjectName("SecondaryButton")
        self.display_toggle_button.setCheckable(True)
        self.display_toggle_button.setChecked(True)

        action_buttons = (
            self.copy_ocr_button,
            self.ocr_enabled_button,
            self.translation_enabled_button,
            self.save_button,
            self.capture_button,
            self.clipboard_button,
            self.display_toggle_button,
        )
        for button in action_buttons:
            button.setMinimumHeight(44)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(10)
        action_grid.setVerticalSpacing(10)
        action_grid.setColumnStretch(0, 1)
        action_grid.setColumnStretch(1, 1)
        action_grid.setColumnStretch(2, 1)

        toggle_pair_container = QWidget()
        toggle_pair_layout = QHBoxLayout(toggle_pair_container)
        toggle_pair_layout.setContentsMargins(0, 0, 0, 0)
        toggle_pair_layout.setSpacing(6)
        toggle_pair_layout.addWidget(self.ocr_enabled_button, 1)
        toggle_pair_layout.addWidget(self.translation_enabled_button, 1)

        action_grid.addWidget(self.capture_button, 0, 0)
        action_grid.addWidget(self.copy_ocr_button, 0, 1)
        action_grid.addWidget(self.save_button, 0, 2)
        action_grid.addWidget(toggle_pair_container, 1, 0)
        action_grid.addWidget(self.clipboard_button, 1, 1)
        action_grid.addWidget(self.display_toggle_button, 1, 2)

        layout.addLayout(action_grid)

        return card

    def set_config_drawer_visible(self, is_visible: bool) -> None:
        self._is_config_drawer_open = bool(is_visible)
        self.config_drawer_panel.setVisible(self._is_config_drawer_open)
        self.drawer_toggle_button.setText(
            "收起设置" if self._is_config_drawer_open else "展开设置"
        )
        self.drawer_toggle_button.setToolTip(
            "收起当前配置抽屉"
            if self._is_config_drawer_open
            else "展开配置抽屉并编辑参数"
        )

    def _open_config_drawer_for_role(self, role: str) -> None:
        self.switch_config_role(role)
        self.set_config_drawer_visible(True)

    def _update_ocr_enabled_button_text(self) -> None:
        self.ocr_enabled_button.setText(
            "OCR：开" if self.ocr_enabled_button.isChecked() else "OCR：关"
        )

    def _update_translation_enabled_button_text(self) -> None:
        self.translation_enabled_button.setText(
            "翻译：开" if self.translation_enabled_button.isChecked() else "翻译：关"
        )

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
                self.prompt_input.toPlainText().strip() or DEFAULT_OCR_PROMPT_TEMPLATE
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
        self.ocr_mode_button.setChecked(role == "ocr")
        self.translation_mode_button.setChecked(role == "translation")

        if role == "ocr":
            self.config_title_label.setText("识别配置")
            self.config_desc_label.setText(
                "这里配置 OCR 识别模型。截图后会先使用该模型提取图片中的原文或公式。"
            )
            self.top_mode_hint_label.setText(
                "当前正在编辑 OCR 识别配置。可通过顶部抽屉按钮收起/展开设置。"
            )
            self.api_profile_list_label.setText("已保存 OCR 配置")
            self.api_profile_name_label.setText("OCR 配置名称")
            self.api_section_title_label.setText("当前 OCR API 连接参数")
            self.prompt_label.setText("OCR 提示词（Prompt）")
            self.prompt_input.setPlainText(
                self._ocr_prompt_template or DEFAULT_OCR_PROMPT_TEMPLATE
            )
            self.target_language_label.hide()
            self.target_language_input.hide()
            self.fetch_models_button.setToolTip("拉取 OCR 模型列表")
        else:
            self.config_title_label.setText("翻译配置")
            self.config_desc_label.setText(
                "这里配置翻译模型。仅当“翻译功能”开启时，才会继续送入该模型翻译。"
            )
            self.top_mode_hint_label.setText(
                "当前正在编辑翻译配置。可通过顶部抽屉按钮收起/展开设置。"
            )
            self.api_profile_list_label.setText("已保存翻译配置")
            self.api_profile_name_label.setText("翻译配置名称")
            self.api_section_title_label.setText("当前翻译 API 连接参数")
            self.prompt_label.setText("翻译提示词（Prompt）")
            self.prompt_input.setPlainText(
                self._translation_prompt_template or DEFAULT_TRANSLATION_PROMPT_TEMPLATE
            )
            self.target_language_label.show()
            self.target_language_input.show()
            self.target_language_input.setText(self._target_language)
            self.fetch_models_button.setToolTip("拉取翻译模型列表")

        self._refresh_api_profile_combo()
        self._apply_api_profile_to_fields(
            self._get_selected_api_profile_from_role(self._active_config_role)
        )

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

    def update_current_api_profile(self) -> None:
        self._sync_active_role_state()
        self._refresh_api_profile_combo()
        self._apply_api_profile_to_fields(
            self._get_selected_api_profile_from_role(self._active_config_role)
        )

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

    def toggle_api_key_visibility(self) -> None:
        is_password_mode = self.api_key_input.echoMode() == QLineEdit.EchoMode.Password
        self.api_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal
            if is_password_mode
            else QLineEdit.EchoMode.Password
        )
        self.toggle_api_key_button.setText(
            "隐藏密钥" if is_password_mode else "显示密钥"
        )

    def set_display_visible(self, is_visible: bool) -> None:
        self.display_toggle_button.blockSignals(True)
        self.display_toggle_button.setChecked(is_visible)
        self.display_toggle_button.blockSignals(False)
        self.display_toggle_button.setText(
            "翻译显示：已开启" if is_visible else "翻译显示：已关闭"
        )

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

    def update_ocr_result(self, text: str) -> None:
        self.ocr_result_output.setPlainText(text.strip())

    def clear_ocr_result(self) -> None:
        self.ocr_result_output.clear()

    def get_ocr_result_text(self) -> str:
        return self.ocr_result_output.toPlainText().strip()

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
            config.translation_prompt_template or DEFAULT_TRANSLATION_PROMPT_TEMPLATE
        )
        self._target_language = config.target_language or "简体中文"

        self.set_ocr_enabled(config.ocr_enabled)
        self.set_translation_enabled(config.translation_enabled)
        self.refresh_shortcut_input.setKeySequence(
            config.refresh_shortcut or DEFAULT_REFRESH_SHORTCUT
        )

        self.switch_config_role(self._active_config_role, save_current=False)

    def get_config(self) -> AppConfig:
        self._sync_active_role_state()

        config = AppConfig(
            ocr_api_configs=[
                self._clone_api_config(item) for item in self._ocr_api_configs
            ],
            selected_ocr_api_config_id=self._selected_ocr_api_config_id,
            translation_api_configs=[
                self._clone_api_config(item) for item in self._translation_api_configs
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
            self.preview_label.setText("尚无截图预览")
            self.preview_label.setPixmap(QPixmap())
            return

        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)

    def _update_toast_position(self) -> None:
        if not hasattr(self, "_toast_label"):
            return

        text = self._toast_label.text().strip()
        if not text:
            return

        font_metrics = QFontMetrics(self._toast_label.font())
        horizontal_padding = 38
        max_width = max(220, self.width() - 40)
        preferred_width = font_metrics.horizontalAdvance(text) + horizontal_padding

        use_single_line = preferred_width <= max_width
        self._toast_label.setWordWrap(not use_single_line)

        if use_single_line:
            self._toast_label.setFixedWidth(preferred_width)
        else:
            self._toast_label.setFixedWidth(max_width)

        self._toast_label.adjustSize()

        x = max(20, (self.width() - self._toast_label.width()) // 2)
        y = max(20, self.height() - self._toast_label.height() - 28)
        self._toast_label.move(x, y)

    def show_toast(self, message: str, duration_ms: int = 2200) -> None:
        text = message.strip()
        if not text:
            return

        self._toast_label.setText(text)
        self._update_toast_position()
        self._toast_label.show()
        self._toast_label.raise_()
        self._toast_hide_timer.start(max(800, int(duration_ms)))

    def resizeEvent(self, event) -> None:
        current_pixmap = self.preview_label.pixmap()
        if current_pixmap is not None and not current_pixmap.isNull():
            self.update_preview(current_pixmap)
        if hasattr(self, "_toast_label") and self._toast_label.isVisible():
            self._update_toast_position()
        super().resizeEvent(event)

    def closeEvent(self, event) -> None:
        self.closing.emit(event)
        if event.isAccepted():
            super().closeEvent(event)
