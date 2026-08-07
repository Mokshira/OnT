from __future__ import annotations

import json
import threading
from typing import Any, Callable, Optional

import requests
from PyQt6.QtCore import QObject, pyqtSignal

from .config_manager import ApiConfig


class ApiWorker(QObject):
    """
    通用 API 调用工作对象：
    - OCR：图片 + OCR Prompt
    - 翻译：文本 + 翻译 Prompt

    生命周期约定：
    - `finished(str)` 只表示业务成功结果；
    - `done()` 在 run() 的最外层 finally 发出，每次运行恰好一次；
    - `cancel()` 线程安全且幂等，可打断阻塞中的网络读取。
    """

    partial_text = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    done = pyqtSignal()

    def __init__(
        self,
        api_config: ApiConfig,
        prompt: str,
        *,
        image_base64: str | None = None,
        text_input: str | None = None,
    ) -> None:
        super().__init__()
        self.api_config = api_config
        self.prompt = prompt
        self.image_base64 = image_base64
        self.text_input = text_input

        self._cancelled = threading.Event()
        self._http_lock = threading.Lock()
        self._session: requests.Session | None = None
        self._response: requests.Response | None = None

    def cancel(self) -> None:
        """
        协作取消当前请求。

        先设置取消标志，再关闭活动的 Response / Session，尽快打断
        iter_lines() 与网络读取。可重复调用，任何一次都不抛异常。
        """
        self._cancelled.set()

        with self._http_lock:
            response = self._response
            session = self._session

        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    def _set_active_handles(
        self,
        session: requests.Session | None,
        response: requests.Response | None,
    ) -> None:
        with self._http_lock:
            self._session = session
            self._response = response

    def _close_active_handles(self) -> None:
        with self._http_lock:
            response = self._response
            session = self._session
            self._response = None
            self._session = None

        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    def run(self) -> None:
        try:
            if self._cancelled.is_set():
                return

            payload = self._build_payload(
                model_name=self.api_config.model_name,
                prompt=self.prompt,
                image_base64=self.image_base64,
                text_input=self.text_input,
            )
            headers = self._build_headers()

            session = requests.Session()
            # 处理“cancel() 与句柄赋值并发”的窗口：
            # 赋值后立即复查取消标志，若已取消则直接进入收尾。
            self._set_active_handles(session, None)

            response: requests.Response | None = None
            if not self._cancelled.is_set():
                response = session.post(
                    self.api_config.base_url,
                    headers=headers,
                    json=payload,
                    timeout=60,
                    stream=True,
                )
                self._set_active_handles(session, response)

            if self._cancelled.is_set():
                return
            if response is None:
                return

            response.raise_for_status()

            if self._cancelled.is_set():
                return

            result_text = self._extract_response_text(
                response,
                progress_callback=self.partial_text.emit,
                should_cancel=self._cancelled.is_set,
            )

            if self._cancelled.is_set():
                return

            if not result_text.strip():
                raise ValueError("接口返回成功，但未解析到有效文本内容。")

            if self._cancelled.is_set():
                return

            self.finished.emit(result_text.strip())

        except requests.exceptions.Timeout:
            if not self._cancelled.is_set():
                self.error.emit("请求超时，请检查网络状态或稍后重试。")
        except requests.exceptions.HTTPError as exc:
            if not self._cancelled.is_set():
                detail = self._extract_error_detail(exc.response)
                self.error.emit(f"接口请求失败：{detail}")
        except requests.exceptions.RequestException as exc:
            if not self._cancelled.is_set():
                self.error.emit(f"网络请求异常：{exc}")
        except ValueError as exc:
            if not self._cancelled.is_set():
                self.error.emit(f"数据处理失败：{exc}")
        except Exception as exc:
            if not self._cancelled.is_set():
                self.error.emit(f"发生未知错误：{exc}")
        finally:
            self._close_active_handles()
            self.done.emit()

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_config.api_key:
            headers["Authorization"] = f"Bearer {self.api_config.api_key}"
        return headers

    @staticmethod
    def _build_payload(
        model_name: str,
        prompt: str,
        *,
        image_base64: str | None = None,
        text_input: str | None = None,
    ) -> dict[str, Any]:
        if image_base64:
            content: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}",
                    },
                },
            ]
        else:
            full_text = prompt
            if text_input:
                full_text = f"{prompt}\n\n{text_input}"
            content = [
                {
                    "type": "text",
                    "text": full_text,
                }
            ]

        return {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "temperature": 0.2,
            "stream": True,
            "stream_options": {
                "include_usage": True,
            },
        }

    @classmethod
    def _extract_response_text(
        cls,
        response: requests.Response,
        progress_callback: Callable[[str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> str:
        content_type = response.headers.get("Content-Type", "").lower()

        if "text/event-stream" in content_type:
            streamed_text = cls._extract_text_from_sse(
                response,
                progress_callback=progress_callback,
                should_cancel=should_cancel,
            )
            if streamed_text:
                return streamed_text

        data = response.json()
        return cls._extract_text_from_response(data)

    @classmethod
    def _extract_text_from_sse(
        cls,
        response: requests.Response,
        progress_callback: Callable[[str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> str:
        text_parts: list[str] = []

        for raw_line in response.iter_lines(decode_unicode=False):
            if should_cancel is not None and should_cancel():
                return ""
            if not raw_line:
                continue

            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue

            data_str = line[5:].strip()
            if not data_str or data_str == "[DONE]":
                continue

            try:
                chunk = json.loads(data_str)
            except Exception:
                continue

            choices = chunk.get("choices")
            if not isinstance(choices, list):
                continue

            for choice in choices:
                if not isinstance(choice, dict):
                    continue

                delta = choice.get("delta", {})
                if not isinstance(delta, dict):
                    delta = {}

                # 流式增量必须原样拼接，不能 strip，
                # 否则 chunk 首尾的空格/换行会丢失，破坏段落与单词边界
                content = delta.get("content")
                if content is None:
                    # 兼容 completions 风格的 legacy 字段
                    content = choice.get("text")
                extracted = cls._extract_text_from_content(
                    content,
                    preserve_format=True,
                )
                if extracted:
                    text_parts.append(extracted)
                    if should_cancel is not None and should_cancel():
                        return ""
                    if progress_callback is not None:
                        progress_callback("".join(text_parts))
                elif isinstance(content, str) and content.strip() == "":
                    # 仅含空白字符（如 "\n"、" "）的流式增量同样携带结构信息，
                    # 必须原样拼接，否则模型拆分在独立 chunk 中的换行会丢失，
                    # 空白行（\n\n）会被吞成单个换行。此类 chunk 不触发进度刷新，
                    # 等下一个含可见字符的 chunk 一并发出即可。
                    text_parts.append(content)
                    if should_cancel is not None and should_cancel():
                        return ""

        return "".join(text_parts).strip()

    @classmethod
    def _extract_text_from_response(cls, data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]

            if isinstance(first_choice, dict):
                message = first_choice.get("message", {})
                if isinstance(message, dict):
                    content = message.get("content")
                    extracted = cls._extract_text_from_content(content)
                    if extracted:
                        return extracted

                delta = first_choice.get("delta", {})
                if isinstance(delta, dict):
                    content = delta.get("content")
                    extracted = cls._extract_text_from_content(content)
                    if extracted:
                        return extracted

                direct_text = first_choice.get("text")
                if isinstance(direct_text, str) and direct_text.strip():
                    return direct_text.strip()

        for key in ("output_text", "text", "translated_text", "translation"):
            value = data.get(key)
            if (
                isinstance(value, str)
                and value.strip()
                and not cls._looks_like_response_id(value)
            ):
                return value.strip()

        candidates = data.get("candidates")
        if isinstance(candidates, list) and candidates:
            text_parts: list[str] = []
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue

                content = candidate.get("content", {})
                if not isinstance(content, dict):
                    continue

                parts = content.get("parts", [])
                if isinstance(parts, list):
                    for part in parts:
                        if isinstance(part, dict):
                            text_value = part.get("text")
                            if isinstance(text_value, str) and text_value.strip():
                                text_parts.append(text_value.strip())

            if text_parts:
                return "\n".join(text_parts)

        fallback = cls._find_text_recursively(data)
        if fallback:
            return fallback

        raise ValueError("无法从响应 JSON 中提取文本结果。")

    @staticmethod
    def _extract_text_from_content(
        content: Any,
        *,
        preserve_format: bool = False,
    ) -> str:
        """
        从消息 content 中提取文本。

        preserve_format=False（默认，用于非流式 JSON 响应）：
            去除每个片段首尾空白，列表片段用换行拼接。
        preserve_format=True（用于 SSE 流式增量）：
            片段内容原样保留，列表片段直接顺序拼接，
            避免吞掉 chunk 边界的空格与换行。
        """

        def clean(text: str) -> str:
            return text if preserve_format else text.strip()

        if isinstance(content, str) and content.strip():
            return clean(content)

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    cleaned = clean(item)
                    if cleaned:
                        text_parts.append(cleaned)
                    continue

                if not isinstance(item, dict):
                    continue

                for key in ("text", "content", "value", "output_text"):
                    value = item.get(key)
                    if isinstance(value, str):
                        cleaned = clean(value)
                        if cleaned:
                            text_parts.append(cleaned)
                        break

            if text_parts:
                joiner = "" if preserve_format else "\n"
                return joiner.join(text_parts)

        if isinstance(content, dict):
            for key in ("text", "content", "value", "output_text"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    return clean(value)

        return ""

    @classmethod
    def _find_text_recursively(cls, obj: Any) -> str:
        preferred_keys = {
            "text",
            "content",
            "output_text",
            "translation",
            "translated_text",
            "value",
        }

        if isinstance(obj, dict):
            for key in preferred_keys:
                value = obj.get(key)
                extracted = cls._extract_text_from_content(value)
                if extracted and not cls._looks_like_response_id(extracted):
                    return extracted

            for value in obj.values():
                extracted = cls._find_text_recursively(value)
                if extracted:
                    return extracted

        elif isinstance(obj, list):
            for item in obj:
                extracted = cls._find_text_recursively(item)
                if extracted:
                    return extracted

        elif (
            isinstance(obj, str)
            and obj.strip()
            and not cls._looks_like_response_id(obj)
        ):
            return obj.strip()

        return ""

    @staticmethod
    def _looks_like_response_id(text: str) -> bool:
        value = text.strip()
        id_prefixes = ("resp_", "req_", "msg_", "chatcmpl-", "cmpl-", "run_")
        if value.startswith(id_prefixes):
            return True

        compact = value.replace("_", "").replace("-", "")
        if (
            len(value) >= 24
            and compact.isalnum()
            and " " not in value
            and "\n" not in value
        ):
            return True

        return False

    @staticmethod
    def _extract_error_detail(response: Optional[requests.Response]) -> str:
        if response is None:
            return "HTTP 错误，且未收到响应内容。"

        try:
            data = response.json()
            if isinstance(data, dict):
                if "error" in data:
                    error_obj = data["error"]
                    if isinstance(error_obj, dict):
                        return str(error_obj.get("message", data))
                    return str(error_obj)
                return str(data)
        except Exception:
            pass

        text = response.text.strip()
        return text or f"HTTP {response.status_code}"
