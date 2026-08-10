"""
针对「SSE 流式回调 O(n²) 拼接 + 每 chunk 全文 Markdown 重渲染」修复的
单元测试（纯 Python 部分：增量合并器与流式起始门控）。

运行方式（项目根目录下）：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocr_translator.stream_utils import PartialTextCoalescer, StreamStartGate


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


class PartialTextCoalescerTests(unittest.TestCase):
    def _make(self, interval: float = 0.08):
        emitted: list[str] = []
        clock = FakeClock()
        coalescer = PartialTextCoalescer(
            emitted.append,
            min_interval_seconds=interval,
            clock=clock,
        )
        return coalescer, emitted, clock

    def test_first_delta_emits_immediately(self):
        """首段增量应立即发射，保证首字延迟不受合并窗口影响。"""
        coalescer, emitted, _clock = self._make()
        coalescer.add("你好")
        self.assertEqual(emitted, ["你好"])

    def test_within_interval_deltas_are_buffered_then_merged(self):
        coalescer, emitted, clock = self._make()
        coalescer.add("A")
        clock.advance(0.01)
        coalescer.add("B")
        clock.advance(0.01)
        coalescer.add("C")
        self.assertEqual(emitted, ["A"])

        clock.advance(0.08)
        coalescer.add("D")
        self.assertEqual(emitted, ["A", "BCD"])

    def test_concatenation_of_emissions_preserves_all_text(self):
        """合并只改变分组，不改变内容：所有发射拼接后等于全部输入。"""
        coalescer, emitted, clock = self._make()
        pieces = ["第", "一", "行\n", "\n", "  ", "second line", "！"]
        for piece in pieces:
            coalescer.add(piece)
            clock.advance(0.03)
        coalescer.flush()
        self.assertEqual("".join(emitted), "".join(pieces))

    def test_each_character_is_emitted_exactly_once(self):
        """回归保护：旧实现每 chunk 发送全量累计文本，总量 O(n²)。"""
        coalescer, emitted, clock = self._make()
        chunk_count = 500
        for _ in range(chunk_count):
            coalescer.add("x")
            clock.advance(0.001)
        coalescer.flush()

        total_emitted_chars = sum(len(item) for item in emitted)
        self.assertEqual(total_emitted_chars, chunk_count)
        # 发射次数应远小于 chunk 数（按时间片合并）。
        self.assertLess(len(emitted), chunk_count // 10)

    def test_empty_delta_is_ignored(self):
        coalescer, emitted, _clock = self._make()
        coalescer.add("")
        coalescer.flush()
        self.assertEqual(emitted, [])

    def test_flush_without_pending_is_noop(self):
        coalescer, emitted, _clock = self._make()
        coalescer.add("A")
        coalescer.flush()
        coalescer.flush()
        self.assertEqual(emitted, ["A"])

    def test_zero_interval_emits_every_delta(self):
        coalescer, emitted, _clock = self._make(interval=0.0)
        for piece in ("A", "B", "C"):
            coalescer.add(piece)
        self.assertEqual(emitted, ["A", "B", "C"])

    def test_has_pending_reflects_buffer_state(self):
        coalescer, _emitted, clock = self._make()
        coalescer.add("A")
        self.assertFalse(coalescer.has_pending)
        clock.advance(0.01)
        coalescer.add("B")
        self.assertTrue(coalescer.has_pending)
        coalescer.flush()
        self.assertFalse(coalescer.has_pending)


class StreamStartGateTests(unittest.TestCase):
    def test_whitespace_prelude_is_held_back(self):
        gate = StreamStartGate()
        self.assertIsNone(gate.feed("\n"))
        self.assertIsNone(gate.feed("  \n"))
        self.assertFalse(gate.started)

    def test_first_visible_delta_releases_lstripped_text(self):
        gate = StreamStartGate()
        self.assertIsNone(gate.feed("\n  "))
        released = gate.feed("你好，世界\n")
        self.assertEqual(released, "你好，世界\n")
        self.assertTrue(gate.started)

    def test_after_start_deltas_pass_through_unchanged(self):
        gate = StreamStartGate()
        gate.feed("Hello")
        self.assertEqual(gate.feed("\n\n  World  "), "\n\n  World  ")

    def test_empty_delta_returns_none(self):
        gate = StreamStartGate()
        self.assertIsNone(gate.feed(""))
        gate.feed("text")
        self.assertIsNone(gate.feed(""))

    def test_visible_first_delta_keeps_internal_whitespace(self):
        gate = StreamStartGate()
        released = gate.feed("  第一行\n第二行")
        self.assertEqual(released, "第一行\n第二行")


if __name__ == "__main__":
    unittest.main()
