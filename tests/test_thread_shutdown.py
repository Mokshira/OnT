"""
控制器线程注册表清理、退出调度与最终排空的测试。

仅使用最小 QCoreApplication 与手工构造的控制器字段，
不启动完整 Windows UI。
"""
from __future__ import annotations

import unittest
from unittest import mock

from PyQt6.QtCore import QThread

from ocr_translator import app_controller as controller_module
from ocr_translator.app_controller import AppController


def make_controller() -> AppController:
    controller = AppController.__new__(AppController)
    controller._request_threads = {}
    controller._request_workers = {}
    controller._models_fetch_thread = None
    controller._models_fetch_worker = None
    controller._is_quitting = False
    controller._quit_scheduled = False
    return controller


class FakeWorker:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


class FakeThread:
    def __init__(self, name: str) -> None:
        self.name = name
        self.interrupt_calls = 0
        self.quit_calls = 0
        self.wait_calls = 0

    def requestInterruption(self) -> None:
        self.interrupt_calls += 1

    def quit(self) -> None:
        self.quit_calls += 1

    def wait(self, timeout: int | None = None) -> bool:
        self.wait_calls += 1
        return True


class ControllerShutdownTest(unittest.TestCase):
    def test_cleanup_request_only_removes_matching_thread(self) -> None:
        controller = make_controller()
        finished_calls: list[str] = []
        controller._maybe_finish_shutdown = lambda: finished_calls.append("called")

        thread_a = QThread()
        thread_b = QThread()
        controller._request_threads["ocr"] = thread_a
        controller._request_workers["ocr"] = FakeWorker()

        # 迟到的线程不允许清理当前注册项
        controller._cleanup_request("ocr", thread_b)
        self.assertIn("ocr", controller._request_threads)

        # 身份匹配时才清理
        controller._cleanup_request("ocr", thread_a)
        self.assertNotIn("ocr", controller._request_threads)
        self.assertEqual(finished_calls, ["called"])

    def test_maybe_finish_shutdown_waits_for_registered_threads(self) -> None:
        controller = make_controller()
        controller._is_quitting = True
        controller._request_threads["ocr"] = FakeThread("ocr")

        fake_app = mock.Mock()
        with mock.patch.object(
            controller_module.QApplication, "instance", return_value=fake_app
        ), mock.patch.object(controller_module.QTimer, "singleShot") as single_shot:
            controller._maybe_finish_shutdown()
            single_shot.assert_not_called()

            controller._request_threads.clear()
            controller._maybe_finish_shutdown()
            single_shot.assert_called_once()
            self.assertTrue(controller._quit_scheduled)

            # 重复调用仍只调度一次
            controller._maybe_finish_shutdown()
            single_shot.assert_called_once()

    def test_maybe_finish_shutdown_waits_for_models_thread(self) -> None:
        controller = make_controller()
        controller._is_quitting = True
        controller._models_fetch_thread = FakeThread("models")

        fake_app = mock.Mock()
        with mock.patch.object(
            controller_module.QApplication, "instance", return_value=fake_app
        ), mock.patch.object(controller_module.QTimer, "singleShot") as single_shot:
            controller._maybe_finish_shutdown()
            single_shot.assert_not_called()

            controller._models_fetch_thread = None
            controller._maybe_finish_shutdown()
            single_shot.assert_called_once()

    def test_maybe_finish_shutdown_not_quitting_does_nothing(self) -> None:
        controller = make_controller()
        controller._is_quitting = False

        fake_app = mock.Mock()
        with mock.patch.object(
            controller_module.QApplication, "instance", return_value=fake_app
        ), mock.patch.object(controller_module.QTimer, "singleShot") as single_shot:
            controller._maybe_finish_shutdown()
            single_shot.assert_not_called()
            self.assertFalse(controller._quit_scheduled)

    def test_finalize_threads_cancels_quits_waits_and_is_idempotent(self) -> None:
        controller = make_controller()
        controller._is_quitting = True

        worker_ocr = FakeWorker()
        worker_models = FakeWorker()
        thread_ocr = FakeThread("ocr")
        thread_models = FakeThread("models")

        controller._request_threads["ocr"] = thread_ocr
        controller._request_workers["ocr"] = worker_ocr
        controller._models_fetch_thread = thread_models
        controller._models_fetch_worker = worker_models

        controller.finalize_threads()

        self.assertEqual(worker_ocr.cancel_calls, 1)
        self.assertEqual(worker_models.cancel_calls, 1)
        self.assertEqual(thread_ocr.interrupt_calls, 1)
        self.assertEqual(thread_ocr.quit_calls, 1)
        self.assertEqual(thread_ocr.wait_calls, 1)
        self.assertEqual(thread_models.interrupt_calls, 1)
        self.assertEqual(thread_models.quit_calls, 1)
        self.assertEqual(thread_models.wait_calls, 1)

        # 第二次调用保持幂等，不抛异常
        controller.finalize_threads()
        self.assertEqual(worker_ocr.cancel_calls, 2)
        self.assertEqual(thread_ocr.wait_calls, 2)


if __name__ == "__main__":
    unittest.main()
