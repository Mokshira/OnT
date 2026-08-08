from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPen
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

from .theme import BLUE, INK_3


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
