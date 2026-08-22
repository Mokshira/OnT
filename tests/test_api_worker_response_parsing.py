"""
针对响应解析层三个修复的回归测试。

1. ApiWorker._looks_like_response_id
   CJK 字符的 isalnum() 同样返回 True，旧实现会把“一行无标点的中文/
   日文文本”误判成响应 ID 并静默丢弃；新实现限定为纯 ASCII 且字母与
   数字混排。

2. ApiWorker._extract_response_text
   - SSE 分支走完后不得再回落 response.json()（流已被 iter_lines 消费）；
   - 不能只信 Content-Type：服务端返回 SSE 却带 application/json 时，
     应通过首行嗅探识别为流式，且不丢失第一个 chunk；
   - 真正的非流式 JSON 响应仍能正常解析（嗅探读走的首行会被拼回）。

与其他测试相同，用 AST 抽取真实方法体独立执行，不导入 PyQt6，
可在无 Qt 环境中运行。

运行方式（项目根目录下）：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import ast
import itertools
import json
import sys
import types
import unittest
from pathlib import Path
from typing import Any, Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

API_WORKER_PATH = PROJECT_ROOT / "ocr_translator" / "api_worker.py"

_HELPER_METHODS = (
    "_extract_response_text",
    "_extract_text_from_sse",
    "_extract_text_from_response",
    "_extract_text_from_content",
    "_find_text_recursively",
    "_looks_like_response_id",
)


def _build_parser_class(path: Path, class_name: str, method_names: tuple[str, ...]):
    """抽取 ApiWorker 的纯解析方法，重组成不依赖 Qt 的同构类。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    class_definition = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )

    selected: list[ast.FunctionDef] = []
    kinds: dict[str, str] = {}
    for node in class_definition.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in method_names:
            continue
        decorators = {getattr(dec, "id", "") for dec in node.decorator_list}
        kinds[node.name] = (
            "classmethod" if "classmethod" in decorators else "staticmethod"
        )
        node.decorator_list = []
        selected.append(node)

    missing = set(method_names) - kinds.keys()
    if missing:
        raise AssertionError(f"未在 {class_name} 中找到方法：{sorted(missing)}")

    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {
        "Any": Any,
        "Callable": Callable,
        "Optional": Optional,
        "itertools": itertools,
        "json": json,
        "requests": types.SimpleNamespace(Response=object),
    }
    exec(compile(module, str(path), "exec"), namespace)

    attributes: dict[str, Any] = {}
    for name, kind in kinds.items():
        function = namespace[name]
        attributes[name] = (
            classmethod(function) if kind == "classmethod" else staticmethod(function)
        )
    return type("ParserUnderTest", (), attributes)


Parser = _build_parser_class(API_WORKER_PATH, "ApiWorker", _HELPER_METHODS)


def _sse_frame(delta: str) -> bytes:
    payload = {"choices": [{"delta": {"content": delta}}]}
    return f"data: {json.dumps(payload, ensure_ascii=False)}".encode("utf-8")


class FakeResponse:
    """只允许被消费一次的响应，且 json() 直接报错。

    真实的 requests.Response 在 stream=True + iter_lines 读完后再调 .json()
    同样会失败，这里用断言把这个约束固定下来。
    """

    def __init__(self, lines: list[bytes], content_type: str) -> None:
        self.headers = {"Content-Type": content_type}
        self._lines = lines
        self.iter_lines_calls = 0
        self.json_calls = 0

    def iter_lines(self, decode_unicode: bool = False):
        self.iter_lines_calls += 1
        assert self.iter_lines_calls == 1, "响应体不得被重复消费"
        yield from self._lines

    def json(self):
        self.json_calls += 1
        raise AssertionError("流已被 iter_lines 消费，不得再调用 response.json()")


class LooksLikeResponseIdTests(unittest.TestCase):
    def test_long_chinese_line_is_not_treated_as_id(self):
        text = "这是一段没有标点的中文文本内容超过二十四个字符了真的"
        self.assertGreaterEqual(len(text), 24)
        self.assertFalse(Parser._looks_like_response_id(text))

    def test_long_japanese_line_is_not_treated_as_id(self):
        self.assertFalse(
            Parser._looks_like_response_id("テスト" * 10)
        )

    def test_pure_alpha_ascii_word_is_not_treated_as_id(self):
        # 纯字母、无数字的长单词（如德语复合词）不应被当成 ID。
        self.assertFalse(
            Parser._looks_like_response_id("Donaudampfschifffahrtsgesellschaft")
        )

    def test_known_id_prefixes_still_detected(self):
        for value in ("chatcmpl-abc123", "resp_0001", "msg_x", "run_42"):
            with self.subTest(value=value):
                self.assertTrue(Parser._looks_like_response_id(value))

    def test_opaque_alnum_id_still_detected(self):
        self.assertTrue(
            Parser._looks_like_response_id("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
        )


class ExtractResponseTextTests(unittest.TestCase):
    def test_sse_with_header_is_streamed(self):
        response = FakeResponse(
            [_sse_frame("你好"), b"", _sse_frame("，世界"), b"data: [DONE]"],
            "text/event-stream; charset=utf-8",
        )
        received: list[str] = []

        result = Parser._extract_response_text(
            response, progress_callback=received.append
        )

        self.assertEqual(result, "你好，世界")
        self.assertEqual(received, ["你好", "，世界"])
        self.assertEqual(response.json_calls, 0)

    def test_sse_without_header_is_sniffed_and_first_chunk_kept(self):
        """服务端返回 SSE 却带 application/json，不得当成整块 JSON 解析。"""
        response = FakeResponse(
            [_sse_frame("第一块"), _sse_frame("第二块"), b"data: [DONE]"],
            "application/json",
        )
        received: list[str] = []

        result = Parser._extract_response_text(
            response, progress_callback=received.append
        )

        # 首行是为了嗅探读走的，必须被补回，否则会丢失第一个 chunk。
        self.assertEqual(result, "第一块第二块")
        self.assertEqual(received, ["第一块", "第二块"])

    def test_empty_sse_raises_value_error_instead_of_rereading_stream(self):
        response = FakeResponse([b"data: [DONE]"], "text/event-stream")

        with self.assertRaises(ValueError):
            Parser._extract_response_text(response)

        self.assertEqual(response.json_calls, 0)

    def test_cancelled_sse_returns_empty_without_raising(self):
        state = {"cancelled": False}

        def progress(_delta: str) -> None:
            state["cancelled"] = True

        response = FakeResponse(
            [_sse_frame("AAA"), _sse_frame("BBB")], "text/event-stream"
        )

        result = Parser._extract_response_text(
            response,
            progress_callback=progress,
            should_cancel=lambda: state["cancelled"],
        )

        self.assertEqual(result, "")
        self.assertEqual(response.json_calls, 0)

    def test_plain_json_response_is_still_parsed(self):
        body = json.dumps(
            {"choices": [{"message": {"content": "普通 JSON 结果"}}]},
            ensure_ascii=False,
            indent=2,
        )
        response = FakeResponse(
            [line.encode("utf-8") for line in body.splitlines()],
            "application/json",
        )

        result = Parser._extract_response_text(response)

        self.assertEqual(result, "普通 JSON 结果")
        self.assertEqual(response.json_calls, 0)

    def test_non_json_body_raises_readable_value_error(self):
        response = FakeResponse([b"<html>502 Bad Gateway</html>"], "text/html")

        with self.assertRaises(ValueError) as ctx:
            Parser._extract_response_text(response)

        self.assertIn("502 Bad Gateway", str(ctx.exception))

    def test_empty_body_raises_value_error(self):
        response = FakeResponse([], "application/json")

        with self.assertRaises(ValueError):
            Parser._extract_response_text(response)


if __name__ == "__main__":
    unittest.main()
