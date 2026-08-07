"""
运行时版式协议（ONT_LAYOUT_V1）的纯字符串工具。

职责：
- 在请求发送前，向用户可编辑的任务 Prompt 末尾幂等地追加统一的
  视觉行版式协议，保证模型按图片视觉行输出真实换行。
- 不导入 Qt / requests / 配置对象，只做纯字符串处理，便于单元测试。

注意：
- 协议只存在于发送给模型的最终 Prompt 中，绝不写回 config.json，
  不覆盖用户在设置页看到 / 编辑的自定义 Prompt。
"""
from __future__ import annotations

LAYOUT_CONTRACT_MARKER = "【ONT_LAYOUT_V1】"

_COMMON_LAYOUT_RULES = (
    f"{LAYOUT_CONTRACT_MARKER}\n"
    "必须按图片中的视觉文本行输出：\n"
    "1. 图片中每一个视觉文本行对应输出中的一个逻辑行。\n"
    "2. 图片中的空白行对应输出中的空白行。\n"
    "3. 必须输出真实换行字符；不要输出字面量反斜杠+n。\n"
    "4. 即使相邻行属于同一句，也不得合并；不得自行重排、补段或美化版式。\n"
    "5. 不同说话人、标题、项目或段落不得合并到同一行。\n"
    "6. 只输出纯文本正文，不要 Markdown、代码围栏、解释、行号或版式标记。"
)

_OCR_EXTRA_RULE = "逐行转写图片文字，不改写文字内容。"

_TRANSLATION_EXTRA_RULE = (
    "每个译文行与图片中的对应视觉行一一对应；只允许在该行内部调整词序。"
    "角色名、括号舞台说明和对白保持在其对应行内，不得合并相邻角色行。"
)

_TASK_EXTRA_RULES = {
    "ocr": _OCR_EXTRA_RULE,
    "translation": _TRANSLATION_EXTRA_RULE,
}


def build_layout_contract(task: str) -> str:
    """
    构造指定任务的完整版式协议文本。

    task 只允许 "ocr" 或 "translation"，非法值抛 ValueError。
    """
    if task not in _TASK_EXTRA_RULES:
        raise ValueError(f"未知的版式协议任务类型：{task!r}")
    return f"{_COMMON_LAYOUT_RULES}\n{_TASK_EXTRA_RULES[task]}"


def append_visual_layout_contract(prompt: str, *, task: str) -> str:
    """
    在用户 Prompt 末尾追加 ONT_LAYOUT_V1 版式协议。

    不变量：
    - task 只允许 "ocr" / "translation"，非法值抛 ValueError；
    - 保留用户 Prompt 全文，仅去除末尾多余空白；
    - 协议位于用户 Prompt 之后，占据“最后指令”位置；
    - 已包含 LAYOUT_CONTRACT_MARKER 时不重复追加（幂等）；
    - 不修改、不写回任何配置。
    """
    contract = build_layout_contract(task)

    base = str(prompt).rstrip()
    if LAYOUT_CONTRACT_MARKER in base:
        return base
    if not base:
        return contract
    return f"{base}\n\n{contract}"
