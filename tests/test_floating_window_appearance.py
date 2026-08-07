"""翻译悬浮窗透明度与原生拖动回归测试。"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from ocr_translator.floating_window import FloatingSubtitleWindow


class FloatingWindowAppearanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = FloatingSubtitleWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_mouse_press_prefers_native_system_move(self) -> None:
        handle = mock.Mock()
        handle.startSystemMove.return_value = True
        self.window.windowHandle = mock.Mock(return_value=handle)
        self.window._is_on_resize_edge = mock.Mock(return_value=False)

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(40, 40),
            QPointF(140, 140),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.window.mousePressEvent(event)

        handle.startSystemMove.assert_called_once_with()
        self.assertIsNone(self.window._drag_offset)
        self.assertTrue(event.isAccepted())

    def test_mouse_press_falls_back_when_system_move_unavailable(self) -> None:
        handle = mock.Mock()
        handle.startSystemMove.return_value = False
        self.window.windowHandle = mock.Mock(return_value=handle)
        self.window._is_on_resize_edge = mock.Mock(return_value=False)
        self.window.move(100, 100)

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(40, 40),
            QPointF(140, 140),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.window.mousePressEvent(event)

        handle.startSystemMove.assert_called_once_with()
        self.assertIsInstance(self.window._drag_offset, QPoint)
        self.assertTrue(event.isAccepted())


if __name__ == "__main__":
    unittest.main()
