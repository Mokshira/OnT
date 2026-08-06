from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from config_manager import AppConfig


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
