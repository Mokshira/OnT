"""
ApiWorker 生命周期与协作取消测试。

仅使用 unittest + unittest.mock，不访问公网、不读取真实 API Key。
"""
from __future__ import annotations

import threading
import time
import unittest
from unittest import mock

import requests
from PyQt6.QtCore import Qt

from ocr_translator import api_worker as api_worker_module
from ocr_translator.api_worker import ApiWorker
from ocr_translator.config_manager import ApiConfig


def make_worker(**overrides) -> ApiWorker:
    api_config = ApiConfig(
        profile_name="test",
        api_key="test-key",
        base_url="https://example.test/v1/chat/completions",
        model_name="test-model",
    )
    return ApiWorker(
        api_config,
        "prompt",
        text_input="hello",
        **overrides,
    )


class JSONResponse:
    headers = {"Content-Type": "application/json"}
    closed = False

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"choices": [{"message": {"content": "ok"}}]}

    def close(self) -> None:
        self.closed = True


class JSONErrorResponse(JSONResponse):
    def raise_for_status(self) -> None:
        raise requests.exceptions.HTTPError(response=self)


class FakeSession:
    """会话把 close 转发给响应，模拟 requests 行为。"""

    def __init__(self, response):
        self.response = response
        self.closed = False

    def post(self, *args, **kwargs):
        return self.response

    def close(self) -> None:
        self.closed = True
        try:
            self.response.close()
        except Exception:
            pass


class BlockingSSEResponse:
    """SSE 响应：iter_lines 阻塞直到被释放，模拟长时间流式读取。"""

    headers = {"Content-Type": "text/event-stream"}
    closed = False

    def __init__(self, release: threading.Event):
        self.release = release
        self.iterations_started = threading.Event()

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, decode_unicode=False):
        self.iterations_started.set()
        while not self.release.is_set():
            time.sleep(0.01)
        return
        yield  # pragma: no cover

    def close(self) -> None:
        self.closed = True
        self.release.set()


class LifecycleSignals:
    """用 DirectConnection 记录信号，避免依赖事件循环。"""

    def __init__(self, worker: ApiWorker):
        self.finished: list[str] = []
        self.errors: list[str] = []
        self.done_count = 0
        self.partial: list[str] = []
        worker.finished.connect(
            self.finished.append,
            Qt.ConnectionType.DirectConnection,
        )
        worker.error.connect(
            self.errors.append,
            Qt.ConnectionType.DirectConnection,
        )
        worker.done.connect(
            self._on_done,
            Qt.ConnectionType.DirectConnection,
        )
        worker.partial_text.connect(
            self.partial.append,
            Qt.ConnectionType.DirectConnection,
        )

    def _on_done(self) -> None:
        self.done_count += 1

    def assert_no_business_signals(self, testcase: unittest.TestCase) -> None:
        testcase.assertEqual(self.finished, [])
        testcase.assertEqual(self.errors, [])
        testcase.assertEqual(self.partial, [])


def wait_thread(testcase: unittest.TestCase, thread: threading.Thread) -> None:
    thread.join(timeout=3.0)
    if thread.is_alive():
        testcase.fail("Worker 线程未在看门狗时间内结束（疑似取消未生效）")


class ApiWorkerLifecycleTest(unittest.TestCase):
    def test_success_emits_finished_and_done_once(self) -> None:
        response = JSONResponse()
        session = FakeSession(response)
        with mock.patch.object(
            api_worker_module.requests, "Session", return_value=session
        ):
            worker = make_worker()
            signals = LifecycleSignals(worker)
            worker.run()

        self.assertEqual(signals.finished, ["ok"])
        self.assertEqual(signals.errors, [])
        self.assertEqual(signals.done_count, 1)
        self.assertTrue(response.closed)
        self.assertTrue(session.closed)

    def test_http_error_emits_error_and_done_once(self) -> None:
        response = JSONErrorResponse()
        session = FakeSession(response)
        with mock.patch.object(
            api_worker_module.requests, "Session", return_value=session
        ):
            worker = make_worker()
            signals = LifecycleSignals(worker)
            worker.run()

        self.assertEqual(signals.finished, [])
        self.assertEqual(len(signals.errors), 1)
        self.assertEqual(signals.done_count, 1)

    def test_cancel_during_sse_read_closes_handles_and_silently_ends(self) -> None:
        release = threading.Event()
        response = BlockingSSEResponse(release)
        session = FakeSession(response)
        worker = make_worker()

        with mock.patch.object(
            api_worker_module.requests, "Session", return_value=session
        ):
            signals = LifecycleSignals(worker)
            runner = threading.Thread(target=worker.run, daemon=True)
            runner.start()
            if not response.iterations_started.wait(timeout=3.0):
                self.fail("SSE 读取未在预期时间内开始")

            worker.cancel()
            wait_thread(self, runner)

        self.assertTrue(response.closed)
        self.assertTrue(session.closed)
        signals.assert_no_business_signals(self)
        self.assertEqual(signals.done_count, 1)

    def test_cancel_before_request_and_repeated_cancel_are_safe(self) -> None:
        response = JSONResponse()
        session = FakeSession(response)
        worker = make_worker()

        with mock.patch.object(
            api_worker_module.requests, "Session", return_value=session
        ):
            worker.cancel()
            worker.cancel()  # 重复取消不抛异常
            signals = LifecycleSignals(worker)
            worker.run()
            worker.cancel()  # 结束后再取消仍然安全

        # 请求尚未建立即被取消：无任何业务信号，done 仍恰好一次。
        signals.assert_no_business_signals(self)
        self.assertEqual(signals.done_count, 1)

    def test_sse_preserves_chunk_boundary_spaces_and_line_breaks(self) -> None:
        class FormattingSSE:
            def iter_lines(self, decode_unicode=False):
                yield from [
                    b'data: {"choices": [{"delta": {"content": "first"}}]}',
                    b'data: {"choices": [{"delta": {"content": " line\\n"}}]}',
                    b'data: {"choices": [{"delta": {"content": "second line"}}]}',
                    b"data: [DONE]",
                ]

        partial: list[str] = []
        result = ApiWorker._extract_text_from_sse(
            FormattingSSE(),
            progress_callback=partial.append,
        )

        self.assertEqual(result, "first line\nsecond line")
        self.assertEqual(partial[-1], "first line\nsecond line")

    def test_sse_cancel_callback_stops_parsing(self) -> None:
        """验证 should_cancel 回调能停止 SSE 解析并返回。"""

        class CancellableSSE:
            content_type = "text/event-stream"

            def __init__(self, lines):
                self._lines = lines

            def iter_lines(self, decode_unicode=False):
                yield from self._lines

        lines = [
            b"data: {\"choices\": [{\"delta\": {\"content\": \"hi\"}}]}\n",
            b"data: {\"choices\": [{\"delta\": {\"content\": \" there\"}}]}\n",
        ]
        response = CancellableSSE(lines)

        def should_cancel() -> bool:
            return False

        result = ApiWorker._extract_text_from_sse(
            response,
            should_cancel=should_cancel,
        )
        self.assertEqual(result, "hi there")

        cancelled_calls: list[bool] = []

        def should_cancel_after_first() -> bool:
            cancelled_calls.append(True)
            return len(cancelled_calls) >= 1

        response2 = CancellableSSE(lines)
        result2 = ApiWorker._extract_text_from_sse(
            response2,
            should_cancel=should_cancel_after_first,
        )
        self.assertEqual(result2, "")


if __name__ == "__main__":
    unittest.main()
