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


SCRIPT_FIXTURE = (
    'At dusk, Su Wan blocks the man\'s path, '
    'her sword held across her chest.\n'
    '\n'
    'SU WAN: "Stop. What did you take from the study last night?"\n'
    'PEI XUZHI (with a soft laugh): "A heart. Might I have it back?"\n'
    'SU WAN (ears flushing red): "...Smooth talker. '
    'Don\'t think I won\'t run you through."\n'
    'PEI XUZHI: "I believe you. So I\'ve already placed '
    'my heart in your hands."\n'
    'SU WAN (turning away): "I don\'t want your heart. '
    'Just return the letter you stole."'
)
SCRIPT_ROLE_NAMES = ("SU WAN", "PEI XUZHI", "SU WAN", "PEI XUZHI", "SU WAN")


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

    def test_script_fixture_keeps_seven_logical_blocks(self) -> None:
        """剧本 fixture：旁白 + 空白行 + 5 条对白 = 7 个独立文本块。"""
        self.window.set_text(SCRIPT_FIXTURE)

        # 原始缓存逐字符保持 7 个逻辑行
        self.assertEqual(self.window._plain_text, SCRIPT_FIXTURE)
        self.assertEqual(self.window._plain_text.count("\n"), 6)

        document = self.window.text_label.document()
        self.assertEqual(document.blockCount(), 7)

        blocks = [document.findBlockByNumber(i).text() for i in range(7)]
        # 旁白位于第 1 块，空白行占位块存在于第 2 块
        self.assertTrue(blocks[0].startswith("At dusk, Su Wan"))
        self.assertEqual(blocks[1].strip(), "")
        # 5 个角色名各自位于独立文本块，没有被合并到同一行
        for index, role_name in enumerate(SCRIPT_ROLE_NAMES, start=2):
            self.assertTrue(
                blocks[index].startswith(role_name),
                f"块 {index} 应以 {role_name} 开头，实际：{blocks[index]!r}",
            )

    def test_resizing_only_changes_visual_wrapping_not_logical_lines(self) -> None:
        """改变窗口宽度只允许产生视觉折行，逻辑换行数必须保持不变。"""
        self.window.set_text(SCRIPT_FIXTURE)

        for width in (320, 720, 1440):
            self.window.resize(width, 400)
            self.app.processEvents()

            self.assertEqual(self.window._plain_text, SCRIPT_FIXTURE)
            self.assertEqual(self.window.text_label.document().blockCount(), 7)
            self.assertEqual(
                self.window.text_label.toPlainText().count("\n"),
                6,
            )


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

    def test_ocr_script_fixture_keeps_seven_logical_blocks(self) -> None:
        """OCR 展示区：剧本 fixture 渲染为 7 个独立文本块，复制文本不变。"""
        self.window.update_ocr_result(SCRIPT_FIXTURE)

        # 复制路径读取原始缓存，必须逐字符等于 fixture
        self.assertEqual(self.window.get_ocr_result_text(), SCRIPT_FIXTURE)

        document = self.window.ocr_result_output.document()
        self.assertEqual(document.blockCount(), 7)

        blocks = [document.findBlockByNumber(i).text() for i in range(7)]
        self.assertTrue(blocks[0].startswith("At dusk, Su Wan"))
        self.assertEqual(blocks[1].strip(), "")
        for index, role_name in enumerate(SCRIPT_ROLE_NAMES, start=2):
            self.assertTrue(
                blocks[index].startswith(role_name),
                f"块 {index} 应以 {role_name} 开头，实际：{blocks[index]!r}",
            )

    def test_ocr_resize_does_not_change_logical_lines(self) -> None:
        """主窗口缩放只改变视觉折行，不改变复制 / 缓存文本的逻辑行。"""
        self.window.update_ocr_result(SCRIPT_FIXTURE)

        for width in (400, 900):
            self.window.resize(width, 700)
            self.app.processEvents()

            self.assertEqual(self.window.get_ocr_result_text(), SCRIPT_FIXTURE)
            self.assertEqual(
                self.window.ocr_result_output.document().blockCount(),
                7,
            )


if __name__ == "__main__":
    unittest.main()
