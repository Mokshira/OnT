"""
针对「SSE 流式回调 O(n²) 拼接」修复的回归测试。

验证 ApiWorker._extract_text_from_sse 的 progress_callback 采用增量
（delta）语义：每次只携带当前 chunk 新增的文本，所有回调拼接后等于
完整结果；不再出现旧实现中“每 chunk 回调一次全量累计文本”的行为。
同时验证 AppController.on_api_partial_text 的占位提示门控与增量追加。

与 test_app_controller_persistence 相同，用 AST 抽取真实方法体独立执行，
不导入 PyQt6，可在无 Qt 环境中运行。

运行方式（项目根目录下）：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import ast
import json
import sys
import types
import unittest
from pathlib import Path
from typing import Any, Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ocr_translator.stream_utils import StreamStartGate

API_WORKER_PATH = PROJECT_ROOT / "ocr_translator" / "api_worker.py"
CONTROLLER_PATH = PROJECT_ROOT / "ocr_translator" / "app_controller.py"


def _method_node(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    class_definition = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in class_definition.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _load_plain_function(path: Path, class_name: str, method_name: str):
    """抽取方法体、去掉 classmethod/staticmethod 装饰器后独立编译执行。"""
    method = _method_node(path, class_name, method_name)
    method.decorator_list = []
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "Any": Any,
        "Callable": Callable,
        "Optional": Optional,
        "StreamStartGate": StreamStartGate,
        "json": json,
        "requests": types.SimpleNamespace(Response=object),
    }
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[method_name]


_extract_text_from_content = _load_plain_function(
    API_WORKER_PATH, "ApiWorker", "_extract_text_from_content"
)
_extract_text_from_sse = _load_plain_function(
    API_WORKER_PATH, "ApiWorker", "_extract_text_from_sse"
)


class FakeWorkerCls:
    _extract_text_from_content = staticmethod(_extract_text_from_content)


class FakeSseResponse:
    """以 OpenAI Chat Completions SSE 格式逐行吐出增量。"""

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas

    def iter_lines(self, decode_unicode: bool = False):
        for delta in self._deltas:
            payload = {"choices": [{"delta": {"content": delta}}]}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}".encode("utf-8")
            yield b""
        yield b"data: [DONE]"


class ExtractTextFromSseTests(unittest.TestCase):
    def _run(self, deltas: list[str]):
        received: list[str] = []
        result = _extract_text_from_sse(
            FakeWorkerCls,
            FakeSseResponse(deltas),
            progress_callback=received.append,
        )
        return result, received

    def test_callbacks_carry_deltas_not_accumulated_text(self):
        deltas = ["第一", "段", "\n", "\n", "第二段", "。"]
        result, received = self._run(deltas)

        self.assertEqual(result, "第一段\n\n第二段。")
        # delta 语义：每次回调恰好是当前 chunk 的内容本身。
        self.assertEqual(received, deltas)

    def test_total_callback_volume_is_linear_not_quadratic(self):
        """回归保护：旧实现每 chunk 发送全量文本，总回调字符量 O(n²)。"""
        chunk = "字"
        chunk_count = 300
        result, received = self._run([chunk] * chunk_count)

        self.assertEqual(result, chunk * chunk_count)
        total_callback_chars = sum(len(item) for item in received)
        self.assertEqual(total_callback_chars, chunk_count * len(chunk))

    def test_whitespace_only_chunks_are_preserved_in_stream(self):
        deltas = ["行一", "\n", "\n", "行二"]
        result, received = self._run(deltas)

        self.assertEqual(result, "行一\n\n行二")
        self.assertEqual("".join(received), "行一\n\n行二")

    def test_without_callback_still_accumulates(self):
        result = _extract_text_from_sse(FakeWorkerCls, FakeSseResponse(["A", "B"]))
        self.assertEqual(result, "AB")

    def test_cancel_mid_stream_returns_empty_result(self):
        state = {"cancelled": False}
        received: list[str] = []

        def progress(delta: str) -> None:
            received.append(delta)
            state["cancelled"] = True

        result = _extract_text_from_sse(
            FakeWorkerCls,
            FakeSseResponse(["AAA", "BBB"]),
            progress_callback=progress,
            should_cancel=lambda: state["cancelled"],
        )

        self.assertEqual(result, "")
        self.assertEqual(received, ["AAA"])


class FakeMainWindow:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def begin_ocr_stream(self) -> None:
        self.calls.append(("begin",))

    def append_ocr_stream_text(self, delta: str) -> None:
        self.calls.append(("append", delta))


class FakeFloatingWindow:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def begin_stream_display(self) -> None:
        self.calls.append(("begin",))

    def append_stream_text(self, delta: str) -> None:
        self.calls.append(("append", delta))


class ControllerStreamHarness:
    on_api_partial_text = _load_plain_function(
        CONTROLLER_PATH, "AppController", "on_api_partial_text"
    )

    def __init__(self) -> None:
        self._is_quitting = False
        self._stream_gates: dict[str, StreamStartGate] = {}
        self.main_window = FakeMainWindow()
        self.floating_window = FakeFloatingWindow()


class ControllerPartialTextTests(unittest.TestCase):
    def test_placeholder_kept_until_first_visible_character(self):
        controller = ControllerStreamHarness()

        controller.on_api_partial_text("ocr", "\n\n  ")
        self.assertEqual(controller.main_window.calls, [])

        controller.on_api_partial_text("ocr", " 你好")
        self.assertEqual(
            controller.main_window.calls,
            [("begin",), ("append", "你好")],
        )

        controller.on_api_partial_text("ocr", "，世界\n")
        self.assertEqual(
            controller.main_window.calls[-1],
            ("append", "，世界\n"),
        )

    def test_translation_deltas_append_to_floating_window(self):
        controller = ControllerStreamHarness()

        controller.on_api_partial_text("translation", "Bonjour")
        controller.on_api_partial_text("translation", " le monde")

        self.assertEqual(
            controller.floating_window.calls,
            [("begin",), ("append", "Bonjour"), ("append", " le monde")],
        )

    def test_quitting_ignores_deltas(self):
        controller = ControllerStreamHarness()
        controller._is_quitting = True

        controller.on_api_partial_text("ocr", "text")

        self.assertEqual(controller.main_window.calls, [])

    def test_unknown_request_kind_is_ignored(self):
        controller = ControllerStreamHarness()

        controller.on_api_partial_text("other", "text")

        self.assertEqual(controller.main_window.calls, [])
        self.assertEqual(controller.floating_window.calls, [])


if __name__ == "__main__":
    unittest.main()
