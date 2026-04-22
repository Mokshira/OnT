from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from config_manager import (
    ApiConfig,
    AppConfig,
    DEFAULT_API_PROFILE_NAME,
    DEFAULT_MODEL_NAME,
    DEFAULT_OCR_PROMPT_TEMPLATE,
    DEFAULT_REFRESH_SHORTCUT,
    DEFAULT_TRANSLATION_PROMPT_TEMPLATE,
)


class FloatingSubtitleWindow(QWidget):
    """
    桌面悬浮翻译窗口：
    - 无边框
    - 透明背景
    - 始终置顶
    - 支持鼠标拖拽移动
    """

    display_toggle_requested = pyqtSignal()
    appearance_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._drag_offset: Optional[QPoint] = None
        self._is_resizing = False
        self._is_locked = False
        self._resize_margin = 22
        self._resize_start_pos = QPoint()
        self._resize_start_size = QSize()
        self._font_size = 18
        self._font_color = QColor("white")
        self._background_color = QColor("#000000")
        self._background_opacity = 24
        self._is_applying_appearance = False
        self._setup_window()
        self._setup_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle("翻译悬浮字幕")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(720, 160)
        self.setMinimumSize(320, 100)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(0)

        self.background_panel = QFrame(self)
        self.background_panel.setObjectName("FloatingBackgroundPanel")
        self.background_panel.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        self.menu_frame = QFrame(self)
        self.menu_frame.setObjectName("FloatingMenu")
        self.menu_frame.setStyleSheet(
            """
            QFrame#FloatingMenu {
                background: rgba(15, 23, 42, 205);
                border: 1px solid rgba(255, 255, 255, 95);
                border-radius: 10px;
            }
            QFrame#FloatingMenu QPushButton {
                color: white;
                background: rgba(37, 99, 235, 175);
                border: none;
                border-radius: 7px;
                padding: 5px 8px;
                font-size: 12px;
                font-weight: 700;
            }
            QFrame#FloatingMenu QPushButton:hover {
                background: rgba(59, 130, 246, 235);
            }
            QFrame#FloatingMenu QLabel {
                color: rgba(255, 255, 255, 215);
                font-size: 12px;
                font-weight: 600;
                padding-left: 6px;
            }
            QFrame#FloatingMenu QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 70);
                height: 6px;
                border-radius: 3px;
            }
            QFrame#FloatingMenu QSlider::sub-page:horizontal {
                background: rgba(59, 130, 246, 220);
                border-radius: 3px;
            }
            QFrame#FloatingMenu QSlider::add-page:horizontal {
                background: rgba(255, 255, 255, 35);
                border-radius: 3px;
            }
            QFrame#FloatingMenu QSlider::handle:horizontal {
                background: white;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
                border: 1px solid rgba(37, 99, 235, 200);
            }
            """
        )

        menu_layout = QHBoxLayout(self.menu_frame)
        menu_layout.setContentsMargins(8, 6, 8, 6)
        menu_layout.setSpacing(6)

        menu_style = """
            QMenu {
                background: rgba(15, 23, 42, 235);
                color: white;
                border: 1px solid rgba(255, 255, 255, 95);
                border-radius: 10px;
                padding: 6px;
            }
            QMenu::item {
                padding: 8px 16px;
                border-radius: 6px;
                margin: 2px 6px;
            }
            QMenu::item:selected {
                background: rgba(59, 130, 246, 220);
            }
            """

        self.font_button = QPushButton("修改字体")
        self.font_menu = QMenu(self.font_button)
        self.font_menu.setStyleSheet(menu_style)
        self.font_menu.setMinimumWidth(260)

        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setRange(10, 72)
        self.font_size_slider.setSingleStep(1)
        self.font_size_slider.setPageStep(2)
        self.font_size_slider.setValue(self._font_size)
        self.font_size_value_label = QLabel()
        self.font_size_value_label.setMinimumWidth(48)
        self.font_size_value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.font_size_action = QWidgetAction(self.font_menu)
        self.font_size_action.setDefaultWidget(
            self._build_menu_slider_panel(
                "字体大小",
                self.font_size_slider,
                self.font_size_value_label,
            )
        )
        self.font_menu.addAction(self.font_size_action)
        self.font_color_action = self.font_menu.addAction("字体颜色")
        self.font_button.setMenu(self.font_menu)
        self.font_menu.aboutToHide.connect(self._schedule_menu_hide_check)

        self.background_button = QPushButton("背景控制")
        self.background_menu = QMenu(self.background_button)
        self.background_menu.setStyleSheet(menu_style)
        self.background_menu.setMinimumWidth(260)
        self.background_color_action = self.background_menu.addAction("背景颜色")

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setSingleStep(1)
        self.opacity_slider.setPageStep(5)
        self.opacity_slider.setValue(self._background_opacity)
        self.opacity_value_label = QLabel()
        self.opacity_value_label.setMinimumWidth(48)
        self.opacity_value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.opacity_action = QWidgetAction(self.background_menu)
        self.opacity_action.setDefaultWidget(
            self._build_menu_slider_panel(
                "透明度",
                self.opacity_slider,
                self.opacity_value_label,
            )
        )
        self.background_menu.addAction(self.opacity_action)
        self.background_button.setMenu(self.background_menu)
        self.background_menu.aboutToHide.connect(self._schedule_menu_hide_check)

        self.display_toggle_button = QPushButton("隐藏显示")
        self.lock_button = QPushButton("锁定窗口")
        self.style_status_label = QLabel()
        self.style_status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.style_status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        standard_button_size = self.lock_button.sizeHint()
        standard_button_width = max(
            standard_button_size.width(),
            self.font_button.sizeHint().width(),
            self.background_button.sizeHint().width(),
            self.display_toggle_button.sizeHint().width(),
        )
        standard_button_height = standard_button_size.height()

        for button in (
            self.font_button,
            self.background_button,
            self.display_toggle_button,
            self.lock_button,
        ):
            button.setFixedSize(standard_button_width, standard_button_height)

        self.font_button.setToolTip("打开字体设置菜单，可调整字号滑块和字体颜色")
        self.font_size_slider.setToolTip("拖动调节字幕字号")
        self.font_size_value_label.setToolTip("当前字幕字号")
        self.background_button.setToolTip("打开背景控制菜单，可调整背景颜色与透明度")
        self.opacity_slider.setToolTip("拖动调节翻译显示区背景透明度")
        self.opacity_value_label.setToolTip("当前翻译显示区背景透明度")
        self.display_toggle_button.setToolTip("显示或隐藏翻译")
        self.lock_button.setToolTip("锁定后不可拖动和缩放窗口")

        self.font_size_slider.valueChanged.connect(self.set_font_size)
        self.font_color_action.triggered.connect(self.choose_font_color)
        self.background_color_action.triggered.connect(self.choose_background_color)
        self.opacity_slider.valueChanged.connect(self.set_background_opacity)
        self.display_toggle_button.clicked.connect(self.request_toggle_display)
        self.lock_button.clicked.connect(self.toggle_lock)

        menu_layout.addWidget(self.font_button)
        menu_layout.addWidget(self.background_button)
        menu_layout.addWidget(self.display_toggle_button)
        menu_layout.addWidget(self.lock_button)
        menu_layout.addStretch(1)
        menu_layout.addWidget(self.style_status_label)

        self.menu_frame.hide()

        self.text_label = QPlainTextEdit()
        self.text_label.setPlainText("翻译结果将在这里显示")
        self.text_label.setReadOnly(True)
        self.text_label.setFrameShape(QFrame.Shape.NoFrame)
        self.text_label.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.text_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.text_label.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        font = QFont("Microsoft YaHei UI", self._font_size)
        font.setBold(True)
        self.text_label.setFont(font)
        self._apply_text_style()

        layout.addWidget(self.text_label, 1)

        self._apply_background_style()
        self._apply_font_size()
        self._apply_text_style()
        self._update_style_status_label()
        self._update_menu_geometry()
        self.background_panel.lower()

    def _update_background_geometry(self) -> None:
        self.background_panel.setGeometry(self.rect().adjusted(4, 4, -4, -4))
        self.background_panel.lower()

    def _update_menu_geometry(self) -> None:
        menu_width = max(280, self.width() - 36)
        self.menu_frame.setFixedWidth(menu_width)
        self.menu_frame.adjustSize()
        self.menu_frame.setGeometry(
            18,
            10,
            menu_width,
            self.menu_frame.sizeHint().height(),
        )
        self._update_background_geometry()

    def set_text(self, text: str) -> None:
        self.text_label.setPlainText(text.strip() or "翻译结果将在这里显示")
        self.text_label.verticalScrollBar().setValue(0)

    def _emit_appearance_changed(self) -> None:
        if not self._is_applying_appearance:
            self.appearance_changed.emit()

    def _update_style_status_label(self) -> None:
        self.style_status_label.setText(
            f"字号 {self._font_size}px | 透明度 {self._background_opacity}%"
        )
        self.font_size_value_label.setText(f"{self._font_size}px")
        self.opacity_value_label.setText(f"{self._background_opacity}%")

    def apply_appearance_config(self, config: AppConfig) -> None:
        self._is_applying_appearance = True
        try:
            self._font_size = int(config.subtitle_font_size)
            font_color = QColor(config.subtitle_font_color)
            background_color = QColor(config.subtitle_background_color)

            if font_color.isValid():
                self._font_color = font_color
            if background_color.isValid():
                self._background_color = background_color

            self._background_opacity = int(config.subtitle_background_opacity)

            self.font_size_slider.blockSignals(True)
            self.font_size_slider.setValue(self._font_size)
            self.font_size_slider.blockSignals(False)

            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(self._background_opacity)
            self.opacity_slider.blockSignals(False)

            self._apply_font_size()
            self._apply_background_style()
            self._apply_text_style()
            self._update_style_status_label()
        finally:
            self._is_applying_appearance = False

    def fill_appearance_config(self, config: AppConfig) -> None:
        config.subtitle_font_size = self._font_size
        config.subtitle_font_color = self._font_color.name().lower()
        config.subtitle_background_color = self._background_color.name().lower()
        config.subtitle_background_opacity = self._background_opacity

    def set_font_size(self, value: int) -> None:
        clamped_value = min(max(int(value), 10), 72)
        if (
            self._font_size == clamped_value
            and self.font_size_slider.value() == clamped_value
        ):
            self._update_style_status_label()
            return

        self._font_size = clamped_value
        self.font_size_slider.blockSignals(True)
        self.font_size_slider.setValue(clamped_value)
        self.font_size_slider.blockSignals(False)
        self._apply_font_size()
        self._update_style_status_label()
        self._emit_appearance_changed()

    def choose_font_color(self) -> None:
        color = QColorDialog.getColor(self._font_color, self, "选择字幕颜色")
        if color.isValid():
            self._font_color = color
            self._apply_text_style()
            self._update_style_status_label()
            self._emit_appearance_changed()

    def choose_background_color(self) -> None:
        color = QColorDialog.getColor(
            self._background_color, self, "选择显示区背景颜色"
        )
        if color.isValid():
            self._background_color = color
            self._apply_background_style()
            self._update_style_status_label()
            self._emit_appearance_changed()

    def set_background_opacity(self, value: int) -> None:
        clamped_value = min(max(int(value), 0), 100)
        if (
            self._background_opacity == clamped_value
            and self.opacity_slider.value() == clamped_value
        ):
            self._update_style_status_label()
            return

        self._background_opacity = clamped_value
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(clamped_value)
        self.opacity_slider.blockSignals(False)
        self._apply_background_style()
        self._update_style_status_label()
        self._emit_appearance_changed()

    def toggle_lock(self) -> None:
        self._is_locked = not self._is_locked
        self.lock_button.setText("解锁窗口" if self._is_locked else "锁定窗口")
        self.lock_button.setToolTip(
            "当前已锁定，点击后解锁" if self._is_locked else "锁定后不可拖动和缩放窗口"
        )
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def request_toggle_display(self) -> None:
        self.display_toggle_requested.emit()

    def set_display_toggle_text(self, is_visible: bool) -> None:
        self.display_toggle_button.setText("隐藏展示" if is_visible else "显示展示")

    def _apply_font_size(self) -> None:
        font = self.text_label.font()
        font.setPointSize(self._font_size)
        font.setBold(True)
        self.text_label.setFont(font)

    def _apply_background_style(self) -> None:
        alpha = round(self._background_opacity / 100 * 255)
        self.background_panel.setStyleSheet(
            f"""
            QFrame#FloatingBackgroundPanel {{
                background: rgba(
                    {self._background_color.red()},
                    {self._background_color.green()},
                    {self._background_color.blue()},
                    {alpha}
                );
                border-radius: 16px;
            }}
            """
        )
        self.update()

    def _apply_text_style(self) -> None:
        top_padding = self.menu_frame.sizeHint().height() + 10
        self.text_label.setStyleSheet(
            f"""
            QPlainTextEdit {{
                color: {self._font_color.name()};
                background: transparent;
                border: none;
                border-radius: 10px;
                padding: {top_padding}px 8px 6px 8px;
                selection-background-color: rgba(59, 130, 246, 120);
                selection-color: white;
            }}
            QScrollBar:vertical {{
                background: rgba(255, 255, 255, 35);
                width: 10px;
                border-radius: 5px;
                margin: 4px 0 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 120);
                min-height: 24px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255, 255, 255, 170);
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
                height: 0px;
            }}
            """
        )

    def _build_menu_slider_panel(
        self,
        title: str,
        slider: QSlider,
        value_label: QLabel,
    ) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(
            """
            QWidget {
                background: transparent;
            }
            QLabel {
                color: white;
                font-size: 12px;
                font-weight: 600;
            }
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 70);
                height: 6px;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(59, 130, 246, 220);
                border-radius: 3px;
            }
            QSlider::add-page:horizontal {
                background: rgba(255, 255, 255, 35);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
                border: 1px solid rgba(37, 99, 235, 200);
            }
            """
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(0, 0, 0, 0)
        slider_row.setSpacing(8)
        slider_row.addWidget(slider, 1)
        slider_row.addWidget(value_label)

        layout.addWidget(title_label)
        layout.addLayout(slider_row)
        return panel

    def _show_menu(self) -> None:
        self._update_menu_geometry()
        self.menu_frame.show()
        self.menu_frame.raise_()

    def _schedule_menu_hide_check(self) -> None:
        QTimer.singleShot(0, self._hide_menu_if_cursor_outside)

    def _hide_menu_if_cursor_outside(self) -> None:
        cursor_pos = QCursor.pos()

        if self.frameGeometry().contains(cursor_pos):
            return

        for popup_menu in (self.font_menu, self.background_menu):
            if popup_menu.isVisible() and popup_menu.frameGeometry().contains(
                cursor_pos
            ):
                return

        self.menu_frame.hide()
        if not self._is_resizing and self._drag_offset is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def enterEvent(self, event) -> None:
        self._show_menu()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._schedule_menu_hide_check()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._is_locked:
            if self._is_on_resize_edge(event.position().toPoint()):
                self._is_resizing = True
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_size = self.size()
                event.accept()
                return

            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_locked:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            super().mouseMoveEvent(event)
            return

        if self._is_resizing:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            new_width = max(260, self._resize_start_size.width() + delta.x())
            new_height = max(90, self._resize_start_size.height() + delta.y())
            self.resize(new_width, new_height)
            event.accept()
            return

        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return

        self._update_resize_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        self._is_resizing = False
        self._update_resize_cursor(event.position().toPoint())
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        self._update_menu_geometry()
        self._apply_text_style()
        super().resizeEvent(event)

    def _is_on_resize_edge(self, pos: QPoint) -> bool:
        return (
            pos.x() >= self.width() - self._resize_margin
            and pos.y() >= self.height() - self._resize_margin
        )

    def _update_resize_cursor(self, pos: QPoint) -> None:
        if self._is_on_resize_edge(pos):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        border_alpha = min(
            220, max(60, round(self._background_opacity / 100 * 255) + 20)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, border_alpha), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 16, 16)

        handle_color = (
            QColor(255, 255, 255, 190)
            if not self._is_locked
            else QColor(255, 255, 255, 70)
        )
        painter.setPen(QPen(handle_color, 2))

        right = self.width() - 10
        bottom = self.height() - 10

        painter.drawLine(right - 18, bottom, right, bottom - 18)
        painter.drawLine(right - 12, bottom, right, bottom - 12)
        painter.drawLine(right - 6, bottom, right, bottom - 6)

        super().paintEvent(event)


class ShortcutCaptureEdit(QKeySequenceEdit):
    def __init__(self, status_label: QLabel, parent=None) -> None:
        super().__init__(parent)
        self._status_label = status_label
        self._idle_text = "点击输入框后，按下要绑定的组合键"
        self._recording_text = "正在录制快捷键，请直接按下组合键…"
        self._status_label.setText(self._idle_text)

    def focusInEvent(self, event) -> None:
        self._status_label.setText(self._recording_text)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._status_label.setText(self._idle_text)
        super().focusOutEvent(event)


class StyledComboBox(QComboBox):
    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        arrow_color = QColor("#3b82f6") if self.hasFocus() else QColor("#64748b")
        painter.setPen(QPen(arrow_color, 2))

        center_x = self.width() - 18
        center_y = self.height() // 2 + 1

        painter.drawLine(center_x - 5, center_y - 3, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 5, center_y - 3)


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
