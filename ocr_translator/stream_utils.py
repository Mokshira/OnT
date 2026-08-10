"""
流式增量文本的纯 Python 工具（不导入 Qt / requests，便于单元测试）。

针对「SSE 流式回调 O(n²) 拼接 + 每 chunk 全文 Markdown 重渲染」问题：

- PartialTextCoalescer：在 API 工作线程内按时间片合并 SSE 流式增量，
  把“每个 chunk 一次跨线程信号 + 一次全量文本 join”优化为
  “每个时间片最多一次信号，且只携带增量文本（delta）”。
  每个字符只会被 join 一次，总拼接成本 O(n)，与 chunk 数无关。

- StreamStartGate：帮助 UI 层判断流式输出何时出现第一个可见字符：
  在此之前保持占位提示（如“正在翻译，请稍候...”），
  在此之后切换为增量追加显示，并把首段增量的行首空白裁掉
  （与最终结果 strip 后的展示保持一致）。
"""
from __future__ import annotations

import time
from typing import Callable, Optional

# 流式增量的最小发射间隔（秒）。
# 12.5 次/秒足以保持“打字机”式的流畅观感，同时把长输出（数百上千个
# chunk）的跨线程信号量与 UI 刷新次数限制为与时间成正比、与 chunk 数无关。
DEFAULT_PARTIAL_EMIT_INTERVAL_SECONDS = 0.08


class PartialTextCoalescer:
    """
    按时间片合并流式增量文本。

    - add(delta)：追加一段增量。距上次发射不足 min_interval_seconds 时
      仅入队；否则把队列中的增量 join 成一段后通过 emit 回调发出。
    - 首段增量立即发射，保证首字延迟不受合并窗口影响。
    - flush()：立即发射所有待发增量（若有）。

    线程约定：本对象不加锁，应只在同一个（工作）线程内使用；
    emit 回调本身可以是跨线程信号的 emit（Qt 队列连接负责线程切换）。
    """

    def __init__(
        self,
        emit: Callable[[str], None],
        *,
        min_interval_seconds: float = DEFAULT_PARTIAL_EMIT_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._emit = emit
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._clock = clock
        self._pending: list[str] = []
        self._last_emit_at: Optional[float] = None

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def add(self, delta: str) -> None:
        """追加一段增量；由时间片决定是否立即发射。"""
        if not delta:
            return

        self._pending.append(delta)

        now = self._clock()
        if (
            self._last_emit_at is not None
            and now - self._last_emit_at < self._min_interval
        ):
            return

        self._flush(now)

    def flush(self) -> None:
        """立即发射所有待发增量（若有）。"""
        self._flush(self._clock())

    def _flush(self, now: float) -> None:
        if not self._pending:
            return

        merged = "".join(self._pending)
        self._pending.clear()
        self._last_emit_at = now
        self._emit(merged)


class StreamStartGate:
    """
    过滤流式输出的“空白前奏”。

    流首部可能出现零到多段仅含空白字符的增量；在出现第一个可见字符前，
    UI 应继续显示占位提示。feed() 返回 None 表示继续等待；首次返回可见
    内容时，会把之前缓存的空白前奏一起 join，并裁掉行首空白后返回。
    此后 feed() 对增量原样放行。
    """

    def __init__(self) -> None:
        self._pending: list[str] = []
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def feed(self, delta: str) -> Optional[str]:
        """
        送入一段增量，返回本次应向 UI 追加的文本；
        流尚未出现可见字符时返回 None（占位提示保持不变）。
        """
        if self._started:
            return delta or None

        if delta:
            self._pending.append(delta)

        joined = "".join(self._pending)
        if not joined.strip():
            return None

        self._started = True
        self._pending.clear()
        return joined.lstrip()
