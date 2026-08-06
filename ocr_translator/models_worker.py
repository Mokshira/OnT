from __future__ import annotations

import threading
from typing import Any

import requests
from PyQt6.QtCore import QObject, pyqtSignal

from .api_utils import extract_model_names
from .api_worker import ApiWorker


class ModelsFetchWorker(QObject):
    """
    在后台线程中请求模型列表。

    requests 无法在任意阻塞点被强制中断，因此取消操作通过两层保障：
    1. 关闭当前 Session，尽快打断处于请求/读取中的连接；
    2. 请求结束后检查取消标志，禁止向界面发出任何成功或失败结果。
    """

    succeeded = pyqtSignal(list)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    finished = pyqtSignal()

    def __init__(
        self,
        models_url: str,
        api_key: str = "",
        *,
        connect_timeout: float = 10.0,
        read_timeout: float = 20.0,
    ) -> None:
        super().__init__()
        self._models_url = models_url
        self._api_key = api_key
        self._timeout = (connect_timeout, read_timeout)
        self._cancelled = threading.Event()
        self._session: requests.Session | None = None
        self._session_lock = threading.Lock()

    def cancel(self) -> None:
        """请求停止；关闭活动会话以尽快释放网络阻塞。"""
        self._cancelled.set()
        with self._session_lock:
            session = self._session
        if session is not None:
            session.close()

    def run(self) -> None:
        try:
            if self._cancelled.is_set():
                self.cancelled.emit()
                return

            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            session = requests.Session()
            with self._session_lock:
                self._session = session

            try:
                response = session.get(
                    self._models_url,
                    headers=headers,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                data: Any = response.json()
            finally:
                session.close()
                with self._session_lock:
                    self._session = None

            if self._cancelled.is_set():
                self.cancelled.emit()
                return

            model_names = extract_model_names(data)
            if not model_names:
                raise ValueError("接口返回成功，但未解析到可用模型。")

            self.succeeded.emit(model_names)
        except requests.exceptions.Timeout:
            if self._cancelled.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit("请求超时，请检查网络状态或稍后重试。")
        except requests.exceptions.HTTPError as exc:
            if self._cancelled.is_set():
                self.cancelled.emit()
            else:
                detail = ApiWorker._extract_error_detail(exc.response)
                self.failed.emit(f"接口请求失败：{detail}")
        except requests.exceptions.RequestException as exc:
            if self._cancelled.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(f"网络请求异常：{exc}")
        except Exception as exc:
            if self._cancelled.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
        finally:
            self.finished.emit()
