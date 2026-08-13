from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from .theme import BLUE, INK_2, INK_3, SIDEBAR_TOGGLE_SIZE


def refresh_widget_style(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


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

        arrow_color = QColor(BLUE) if self.hasFocus() else QColor(INK_3)
        painter.setPen(QPen(arrow_color, 1.5))

        center_x = self.width() - 18
        center_y = self.height() // 2 + 1

        painter.drawLine(center_x - 4, center_y - 2, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 4, center_y - 2)


class ToggleSwitch(QAbstractButton):
    """Compact animated switch with the standard toggled(bool) contract."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(32, 18)
        self._offset = 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to_state)

    def sizeHint(self) -> QSize:
        return QSize(32, 18)

    def setChecked(self, checked: bool) -> None:
        changed = bool(checked) != self.isChecked()
        super().setChecked(bool(checked))
        if changed and self.signalsBlocked():
            self._animation.stop()
            self.offset = 1.0 if checked else 0.0

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = min(max(float(value), 0.0), 1.0)
        self.update()

    offset = pyqtProperty(float, fget=_get_offset, fset=_set_offset)

    def _animate_to_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.isEnabled():
            track_color = QColor(212, 212, 216, 150)
        elif self.isChecked():
            track_color = QColor(BLUE)
        else:
            track_color = QColor(0, 0, 0, 46)

        track_rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        if self.hasFocus():
            painter.setPen(QPen(QColor(BLUE), 1.0))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, 8.5, 8.5)

        knob_size = 14.0
        left = 2.0
        right = self.width() - knob_size - 2.0
        knob_x = left + ((right - left) * self._offset)
        knob_color = QColor("#ffffff")
        if not self.isEnabled():
            knob_color.setAlpha(190)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(QRectF(knob_x, 2.0, knob_size, knob_size))


class SegmentedControl(QWidget):
    selectionChanged = pyqtSignal(str)

    def __init__(self, segments: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SegmentedControl")
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self._buttons: dict[str, QPushButton] = {}
        self._current_key = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        for key, text in segments:
            button = QPushButton(text)
            button.setObjectName("SegmentButton")
            button.setCheckable(True)
            button.setProperty("active", False)
            button.clicked.connect(
                lambda _checked=False, selected_key=key: self.setCurrentKey(
                    selected_key
                )
            )
            layout.addWidget(button)
            self._buttons[key] = button

        if segments:
            self.setCurrentKey(segments[0][0], emit_signal=False)

    def currentKey(self) -> str:
        return self._current_key

    def button(self, key: str) -> QPushButton:
        return self._buttons[key]

    def setCurrentKey(self, key: str, emit_signal: bool = True) -> None:
        if key not in self._buttons:
            return

        changed = key != self._current_key
        self._current_key = key
        for item_key, button in self._buttons.items():
            active = item_key == key
            button.blockSignals(True)
            button.setChecked(active)
            button.blockSignals(False)
            button.setProperty("active", active)
            refresh_widget_style(button)

        if changed and emit_signal:
            self.selectionChanged.emit(key)


class Pill(QLabel):
    def __init__(self, text: str = "", tone: str = "default", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.setTone(tone)

    def setTone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        refresh_widget_style(self)


class KbdBadge(QLabel):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Kbd")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )


# --------------------------------------------------------------------------
# 侧边栏（新 UI）：图标 + 可收起导航
# --------------------------------------------------------------------------

NAV_ICON_SIZE = 17
NAV_ICON_STROKE = 1.65
NAV_COLLAPSED_ITEM_SIZE = 36
# 图标与文字之间的间距：Qt 不支持在 QSS 里设置 QPushButton 的 icon-text 间距，
# 这里用一个前导空格补足设计稿中的 10px 视觉间隔。
NAV_LABEL_PREFIX = " "


def _build_nav_icon_geometry(key: str) -> tuple[QPainterPath, list[QPointF]]:
    """按 24x24 画布还原设计稿里的线性图标（描边路径 + 实心圆点）。"""
    path = QPainterPath()
    dots: list[QPointF] = []

    if key == "overview":
        for x, y in ((3.0, 3.0), (15.0, 3.0), (3.0, 15.0), (15.0, 15.0)):
            path.addRoundedRect(QRectF(x, y, 6.0, 6.0), 1.2, 1.2)
    elif key == "results":
        path.moveTo(6.0, 3.5)
        path.lineTo(15.0, 3.5)
        path.lineTo(18.0, 6.5)
        path.lineTo(18.0, 20.5)
        path.lineTo(6.0, 20.5)
        path.closeSubpath()
        path.moveTo(15.0, 3.5)
        path.lineTo(15.0, 6.5)
        path.lineTo(18.0, 6.5)
        path.moveTo(9.0, 11.0)
        path.lineTo(15.0, 11.0)
        path.moveTo(9.0, 15.0)
        path.lineTo(15.0, 15.0)
    elif key == "api":
        path.moveTo(9.5, 8.5)
        path.lineTo(9.5, 6.0)
        path.arcTo(QRectF(9.5, 3.5, 5.0, 5.0), 180.0, -180.0)
        path.lineTo(14.5, 8.5)
        path.moveTo(14.5, 15.5)
        path.lineTo(14.5, 18.0)
        path.arcTo(QRectF(9.5, 15.5, 5.0, 5.0), 0.0, -180.0)
        path.lineTo(9.5, 15.5)
        path.addRoundedRect(QRectF(7.0, 8.5, 10.0, 7.0), 1.4, 1.4)
        path.moveTo(4.0, 12.0)
        path.lineTo(7.0, 12.0)
        path.moveTo(17.0, 12.0)
        path.lineTo(20.0, 12.0)
    elif key == "prompt":
        path.addRoundedRect(QRectF(4.0, 3.0, 16.0, 13.0), 2.5, 2.5)
        path.moveTo(11.0, 16.0)
        path.lineTo(6.5, 20.0)
        path.lineTo(6.5, 16.0)
        path.moveTo(8.0, 8.5)
        path.lineTo(16.0, 8.5)
        path.moveTo(8.0, 12.0)
        path.lineTo(13.0, 12.0)
    elif key == "shortcut":
        path.addRoundedRect(QRectF(3.0, 6.0, 18.0, 12.0), 2.0, 2.0)
        path.moveTo(7.0, 14.0)
        path.lineTo(17.0, 14.0)
        dots.extend(
            [
                QPointF(7.0, 10.0),
                QPointF(10.5, 10.0),
                QPointF(14.0, 10.0),
                QPointF(17.0, 10.0),
            ]
        )
    elif key == "about":
        path.addEllipse(QPointF(12.0, 12.0), 8.5, 8.5)
        path.moveTo(12.0, 10.8)
        path.lineTo(12.0, 15.6)
        dots.append(QPointF(12.0, 8.0))
    else:
        path.addRoundedRect(QRectF(4.0, 4.0, 16.0, 16.0), 3.0, 3.0)

    return path, dots


def build_nav_icon(key: str, color: str, size: int = NAV_ICON_SIZE) -> QIcon:
    """把导航图标绘制成 QIcon，避免额外依赖 QtSvg。"""
    ratio = 2.0
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # QPainter 会按 pixmap 的 devicePixelRatio 自动进入逻辑像素；
    # 这里只需把 24x24 设计坐标映射到 size，不要再乘一遍 ratio。
    painter.scale(size / 24.0, size / 24.0)

    icon_color = QColor(color)
    pen = QPen(icon_color, NAV_ICON_STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    path, dots = _build_nav_icon_geometry(key)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

    if dots:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_color)
        for dot in dots:
            painter.drawEllipse(dot, NAV_ICON_STROKE / 2.0, NAV_ICON_STROKE / 2.0)

    painter.end()
    return QIcon(pixmap)


class SidebarNavButton(QPushButton):
    """带图标的侧边栏导航项，支持展开/收起两种形态。"""

    def __init__(self, key: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._key = key
        self._label_text = text
        self._is_active = False
        self._is_collapsed = False
        self._normal_icon = build_nav_icon(key, INK_2)
        self._active_icon = build_nav_icon(key, BLUE)

        self.setProperty("active", False)
        self.setProperty("collapsed", False)
        self.setText(NAV_LABEL_PREFIX + text)
        self.setIcon(self._normal_icon)

    def key(self) -> str:
        return self._key

    def labelText(self) -> str:
        return self._label_text

    def isActive(self) -> bool:
        return self._is_active

    def setActive(self, active: bool) -> None:
        self._is_active = bool(active)
        self.setProperty("active", self._is_active)
        self.setIcon(self._active_icon if self._is_active else self._normal_icon)
        refresh_widget_style(self)

    def setCollapsed(self, collapsed: bool) -> None:
        self._is_collapsed = bool(collapsed)
        self.setProperty("collapsed", self._is_collapsed)

        if self._is_collapsed:
            self.setText("")
            self.setToolTip(self._label_text)
            self.setFixedSize(NAV_COLLAPSED_ITEM_SIZE, NAV_COLLAPSED_ITEM_SIZE)
        else:
            self.setText(NAV_LABEL_PREFIX + self._label_text)
            self.setToolTip("")
            self.setMinimumSize(0, 34)
            self.setMaximumSize(16777215, 16777215)

        refresh_widget_style(self)


class SidebarToggleButton(QPushButton):
    """悬在侧边栏右边界上的圆形收起/展开按钮。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarToggle")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(SIDEBAR_TOGGLE_SIZE, SIDEBAR_TOGGLE_SIZE)
        self.setIconSize(QSize(14, 14))

        self._collapse_icon = self._build_chevron_icon(pointing_left=True)
        self._expand_icon = self._build_chevron_icon(pointing_left=False)
        self.setCollapsed(False)

    @staticmethod
    def _build_chevron_icon(pointing_left: bool, size: int = 14) -> QIcon:
        ratio = 2.0
        pixmap = QPixmap(int(size * ratio), int(size * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 16.0, size / 16.0)

        pen = QPen(QColor(INK_3), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        path = QPainterPath()
        if pointing_left:
            path.moveTo(9.8, 3.5)
            path.lineTo(5.3, 8.0)
            path.lineTo(9.8, 12.5)
        else:
            path.moveTo(6.2, 3.5)
            path.lineTo(10.7, 8.0)
            path.lineTo(6.2, 12.5)
        painter.drawPath(path)
        painter.end()
        return QIcon(pixmap)

    def setCollapsed(self, collapsed: bool) -> None:
        if collapsed:
            self.setIcon(self._expand_icon)
            self.setToolTip("展开侧边栏")
            self.setAccessibleName("展开侧边栏")
        else:
            self.setIcon(self._collapse_icon)
            self.setToolTip("收起侧边栏")
            self.setAccessibleName("收起侧边栏")
