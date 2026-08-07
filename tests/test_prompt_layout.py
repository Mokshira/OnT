"""
ONT_LAYOUT_V1 运行时版式协议测试。

只使用 unittest / unittest.mock，不访问公网、不读取真实 API Key；
不实例化 AppController（避免创建窗口 / 托盘），直接调用其静态 Prompt 构造方法。
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ocr_translator.app_controller import AppController
from ocr_translator.config_manager import (
    AppConfig,
    DEFAULT_OCR_PROMPT_TEMPLATE,
    DEFAULT_TRANSLATION_PROMPT_TEMPLATE,
)
from ocr_translator.prompt_utils import (
    LAYOUT_CONTRACT_MARKER,
    append_visual_layout_contract,
    build_layout_contract,
)


def count_marker(text: str) -> int:
    return text.count(LAYOUT_CONTRACT_MARKER)


class AppendVisualLayoutContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_ocr_prompt_keeps_user_text_and_appends_ocr_rules(self) -> None:
        user_prompt = "识别这张图片里的文字。"
        result = append_visual_layout_contract(user_prompt, task="ocr")

        self.assertTrue(result.startswith(user_prompt))
        self.assertIn(LAYOUT_CONTRACT_MARKER, result)
        self.assertIn("逐行转写", result)
        self.assertIn("视觉文本行", result)
        self.assertEqual(count_marker(result), 1)
        # 协议必须位于用户 Prompt 之后，占据“最后指令”位置
        self.assertLess(
            result.index(user_prompt),
            result.index(LAYOUT_CONTRACT_MARKER),
        )

    def test_translation_prompt_appends_line_alignment_rules(self) -> None:
        result = append_visual_layout_contract("把图片翻译成英文。", task="translation")

        self.assertIn(LAYOUT_CONTRACT_MARKER, result)
        self.assertIn("一一对应", result)
        self.assertIn("角色名", result)
        self.assertIn("不得合并相邻角色行", result)

    def test_idempotent_when_called_twice(self) -> None:
        once = append_visual_layout_contract("任意 Prompt", task="ocr")
        twice = append_visual_layout_contract(once, task="ocr")

        self.assertEqual(once, twice)
        self.assertEqual(count_marker(twice), 1)

    def test_legacy_prompt_without_layout_wording_still_gets_contract(self) -> None:
        legacy_prompt = "提取图片文字。"  # 旧版 Prompt，不含“保持换行”类文字
        result = append_visual_layout_contract(legacy_prompt, task="translation")

        self.assertTrue(result.startswith(legacy_prompt))
        self.assertEqual(count_marker(result), 1)

    def test_custom_prompt_text_is_preserved_verbatim(self) -> None:
        custom = "第一行要求。\n第二行要求：保留 $pecial 字符 & <html>。\n\n"
        result = append_visual_layout_contract(custom, task="ocr")

        # 用户正文逐字保留，仅去除末尾多余空白
        self.assertTrue(result.startswith(custom.rstrip()))
        self.assertIn("$pecial 字符 & <html>", result)

    def test_invalid_task_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            append_visual_layout_contract("p", task="summarize")
        with self.assertRaises(ValueError):
            build_layout_contract("")

    def test_empty_prompt_returns_contract_only(self) -> None:
        result = append_visual_layout_contract("   \n", task="ocr")
        self.assertTrue(result.startswith(LAYOUT_CONTRACT_MARKER))
        self.assertEqual(count_marker(result), 1)


class AppControllerPromptBuildingTest(unittest.TestCase):
    """
    直接调用 AppController 的静态 Prompt 构造方法，验证四条请求路径
    共享同一版式协议，且不会一条有协议、一条没有。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _make_config(self, **overrides) -> AppConfig:
        config = AppConfig()
        config.ensure_valid_state()
        for key, value in overrides.items():
            setattr(config, key, value)
        return config

    def test_translation_prompt_replaces_target_language(self) -> None:
        config = self._make_config(target_language="English")
        prompt = AppController._build_translation_prompt(config)

        self.assertIn("English", prompt)
        self.assertNotIn("[目标语言]", prompt)

    def test_translation_prompt_legacy_ocr_placeholder_still_supported(self) -> None:
        config = self._make_config(
            translation_prompt_template="翻译[目标语言]：[OCR结果]",
            target_language="日本語",
        )
        prompt = AppController._build_translation_prompt(config)

        self.assertIn("日本語", prompt)
        self.assertNotIn("[OCR结果]", prompt)
        self.assertNotIn("[目标语言]", prompt)
        self.assertIn("请直接识别图片中的文本内容，并翻译为目标语言。", prompt)

    def test_ocr_and_translation_prompts_contain_exactly_one_marker(self) -> None:
        config = self._make_config()

        ocr_prompt = AppController._build_ocr_prompt(config)
        translation_prompt = AppController._build_translation_prompt(config)

        self.assertEqual(count_marker(ocr_prompt), 1)
        self.assertEqual(count_marker(translation_prompt), 1)
        # OCR 与翻译使用不同的追加规则
        self.assertIn("逐行转写", ocr_prompt)
        self.assertIn("不得合并相邻角色行", translation_prompt)

    def test_empty_templates_fall_back_to_defaults_with_contract(self) -> None:
        config = self._make_config(ocr_prompt_template="", translation_prompt_template="")

        ocr_prompt = AppController._build_ocr_prompt(config)
        translation_prompt = AppController._build_translation_prompt(config)

        self.assertTrue(ocr_prompt.startswith(DEFAULT_OCR_PROMPT_TEMPLATE))
        self.assertTrue(
            translation_prompt.startswith(
                DEFAULT_TRANSLATION_PROMPT_TEMPLATE.replace("[目标语言]", "简体中文")
            )
        )
        self.assertEqual(count_marker(ocr_prompt), 1)
        self.assertEqual(count_marker(translation_prompt), 1)

    def test_custom_templates_are_not_overwritten(self) -> None:
        custom_ocr = "我的自定义 OCR 提示词"
        custom_translation = "我的自定义翻译提示词，目标语言：[目标语言]"
        config = self._make_config(
            ocr_prompt_template=custom_ocr,
            translation_prompt_template=custom_translation,
            target_language="Deutsch",
        )

        ocr_prompt = AppController._build_ocr_prompt(config)
        translation_prompt = AppController._build_translation_prompt(config)

        self.assertTrue(ocr_prompt.startswith(custom_ocr))
        self.assertIn("我的自定义翻译提示词", translation_prompt)
        self.assertIn("Deutsch", translation_prompt)
        # 用户配置对象本身不被协议污染
        self.assertNotIn(LAYOUT_CONTRACT_MARKER, config.ocr_prompt_template)
        self.assertNotIn(LAYOUT_CONTRACT_MARKER, config.translation_prompt_template)

    def test_capture_and_clipboard_paths_share_same_prompt_builders(self) -> None:
        """
        截图与剪贴板路径不各自拼 Prompt：
        源码中唯一直接读取 config.ocr_prompt_template 构造请求 Prompt 的
        入口是 _build_ocr_prompt；翻译统一走 _build_translation_prompt。
        """
        import inspect

        from ocr_translator import app_controller as controller_module

        source = inspect.getsource(controller_module)
        direct_reads = source.count("ocr_prompt = config.ocr_prompt_template")
        self.assertEqual(
            direct_reads,
            0,
            "存在绕过 _build_ocr_prompt 的直接模板读取，路径可能分叉。",
        )
        self.assertEqual(source.count("self._build_ocr_prompt(config)"), 2)
        self.assertEqual(source.count("self._build_translation_prompt(config)"), 2)


if __name__ == "__main__":
    unittest.main()
