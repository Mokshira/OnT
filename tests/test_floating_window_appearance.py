"""翻译悬浮窗透明度与原生拖动回归测试。"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from ocr_translator.floating_window import (
    FloatingSubtitleWindow,
    render_markdown_preserving_line_breaks,
)
from ocr_translator.main_window import MainWindow


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

    def test_translation_result_preserves_all_line_break_styles(self) -> None:
        self.window.set_text("第一行\r\n第二行\r第三行\n第四行")

        self.assertEqual(
            self.window.text_label.toPlainText(),
            "第一行\n第二行\n第三行\n第四行",
        )
        self.assertEqual(self.window.text_label.document().blockCount(), 4)

    def test_markdown_rendering_keeps_formatting_and_line_breaks(self) -> None:
        rendered = render_markdown_preserving_line_breaks("**标题**\n下一行")
        self.window.text_label.setMarkdown(rendered)

        self.assertEqual(self.window.text_label.toPlainText(), "标题\n下一行")
        self.assertEqual(self.window.text_label.document().blockCount(), 2)

    def test_translation_result_preserves_blank_lines(self) -> None:
        self.window.set_text("第一段\n\n第二段")

        self.assertEqual(self.window._plain_text, "第一段\n\n第二段")
        self.assertEqual(self.window.text_label.toPlainText(), "第一段\n \n第二段")
        self.assertEqual(self.window.text_label.document().blockCount(), 3)


class MainWindowOcrResultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_ocr_result_preserves_line_breaks_and_copy_text(self) -> None:
        self.window.update_ocr_result("第一行\n第二行\n\n第四行")

        self.assertEqual(
            self.window.get_ocr_result_text(),
            "第一行\n第二行\n\n第四行",
        )
        self.assertEqual(
            self.window.ocr_result_output.toPlainText(),
            "第一行\n第二行\n \n第四行",
        )
        self.assertEqual(self.window.ocr_result_output.document().blockCount(), 4)


if __name__ == "__main__":
    unittest.main()
