from __future__ import annotations

from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QComboBox, QKeySequenceEdit, QLabel


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
