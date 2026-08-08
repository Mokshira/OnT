"""
针对「配置整体回退导致 API Key 丢失」问题修复的回归测试。

运行方式（项目根目录下）：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocr_translator.config_manager import (
    AppConfig,
    ConfigManager,
    DEFAULT_REFRESH_SHORTCUT,
    DEFAULT_SUBTITLE_BACKGROUND_OPACITY,
    DEFAULT_SUBTITLE_FONT_SIZE,
)


def make_config_dict(**overrides):
    """构造一份包含 API Key 的完整新版配置字典。"""
    data = {
        "ocr_api_configs": [
            {
                "profile_id": "ocr-1",
                "profile_name": "我的 OCR",
                "api_key": "sk-ocr-secret",
                "base_url": "https://api.example.com/v1",
                "model_name": "gpt-4o",
            }
        ],
        "selected_ocr_api_config_id": "ocr-1",
        "translation_api_configs": [
            {
                "profile_id": "trans-1",
                "profile_name": "我的翻译",
                "api_key": "sk-trans-secret",
                "base_url": "https://api.example.com/v1",
                "model_name": "gpt-4o",
            }
        ],
        "selected_translation_api_config_id": "trans-1",
        "ocr_enabled": True,
        "translation_enabled": True,
        "target_language": "English",
        "ocr_prompt_template": "OCR 提示词",
        "translation_prompt_template": "翻译提示词",
        "refresh_shortcut": "Ctrl+Shift+T",
        "subtitle_font_size": 20,
        "subtitle_font_color": "#ff0000",
        "subtitle_background_color": "#112233",
        "subtitle_background_opacity": 50,
    }
    data.update(overrides)
    return data


class FieldToleranceTests(unittest.TestCase):
    """单字段损坏时：仅该字段回退默认值，其余字段（尤其 API Key）保留。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config_path = Path(self._tmp.name) / "config.json"
        self.manager = ConfigManager(self.config_path)

    def _write(self, data) -> None:
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_valid_config_round_trip(self):
        self._write(make_config_dict())
        config = self.manager.load()
        self.assertEqual(config.ocr_api_configs[0].api_key, "sk-ocr-secret")
        self.assertEqual(config.subtitle_font_size, 20)
        self.assertEqual(config.refresh_shortcut, "Ctrl+Shift+T")

    def test_bad_font_size_string_keeps_api_keys(self):
        """评审中的典型场景：字号被手改成非数字。"""
        self._write(make_config_dict(subtitle_font_size="abc"))
        config = self.manager.load()

        self.assertEqual(config.subtitle_font_size, DEFAULT_SUBTITLE_FONT_SIZE)
        self.assertEqual(config.ocr_api_configs[0].api_key, "sk-ocr-secret")
        self.assertEqual(config.translation_api_configs[0].api_key, "sk-trans-secret")
        self.assertEqual(config.target_language, "English")
        self.assertEqual(config.subtitle_background_opacity, 50)

    def test_multiple_bad_fields_only_reset_themselves(self):
        self._write(
            make_config_dict(
                subtitle_font_size={"oops": 1},
                subtitle_background_opacity=None,
                target_language=None,
                ocr_enabled=None,
                refresh_shortcut=None,
            )
        )
        config = self.manager.load()

        self.assertEqual(config.subtitle_font_size, DEFAULT_SUBTITLE_FONT_SIZE)
        self.assertEqual(
            config.subtitle_background_opacity, DEFAULT_SUBTITLE_BACKGROUND_OPACITY
        )
        self.assertEqual(config.target_language, "简体中文")
        self.assertTrue(config.ocr_enabled)
        self.assertEqual(config.refresh_shortcut, DEFAULT_REFRESH_SHORTCUT)
        self.assertEqual(config.ocr_api_configs[0].api_key, "sk-ocr-secret")
        self.assertEqual(config.subtitle_font_color, "#ff0000")

    def test_numeric_string_font_size_is_coerced(self):
        self._write(make_config_dict(subtitle_font_size="20"))
        config = self.manager.load()
        self.assertEqual(config.subtitle_font_size, 20)

    def test_out_of_range_font_size_clamped(self):
        self._write(make_config_dict(subtitle_font_size=200))
        config = self.manager.load()
        self.assertEqual(config.subtitle_font_size, 72)

    def test_null_api_key_becomes_empty_not_none_string(self):
        data = make_config_dict()
        data["ocr_api_configs"][0]["api_key"] = None
        self._write(data)
        config = self.manager.load()
        self.assertEqual(config.ocr_api_configs[0].api_key, "")

    def test_null_api_config_list_does_not_reset_other_list(self):
        """ocr_api_configs 为 null 时，不影响 translation 配置的读取。"""
        self._write(make_config_dict(ocr_api_configs=None))
        config = self.manager.load()
        self.assertEqual(config.translation_api_configs[0].api_key, "sk-trans-secret")

    def test_disaster_scenario_save_after_load_keeps_keys(self):
        """完整还原原始 bug 场景：坏字段 → load → save → 重新 load。"""
        self._write(make_config_dict(subtitle_font_size="abc"))
        config = self.manager.load()
        self.manager.save(config)
        reloaded = self.manager.load()

        self.assertEqual(reloaded.ocr_api_configs[0].api_key, "sk-ocr-secret")
        self.assertEqual(
            reloaded.translation_api_configs[0].api_key, "sk-trans-secret"
        )
        self.assertEqual(reloaded.subtitle_font_size, DEFAULT_SUBTITLE_FONT_SIZE)

    def test_ensure_valid_state_never_raises_on_bad_types(self):
        config = AppConfig()
        config.subtitle_font_size = "abc"  # type: ignore[assignment]
        config.subtitle_background_opacity = None  # type: ignore[assignment]
        config.ensure_valid_state()
        self.assertEqual(config.subtitle_font_size, DEFAULT_SUBTITLE_FONT_SIZE)
        self.assertEqual(
            config.subtitle_background_opacity, DEFAULT_SUBTITLE_BACKGROUND_OPACITY
        )


class LegacyStructureToleranceTests(unittest.TestCase):
    """旧版配置结构在字段损坏时同样不应丢失 API Key。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config_path = Path(self._tmp.name) / "config.json"
        self.manager = ConfigManager(self.config_path)

    def test_legacy_api_configs_with_bad_field(self):
        data = {
            "api_configs": [
                {
                    "profile_id": "p1",
                    "profile_name": "旧配置",
                    "api_key": "sk-legacy-secret",
                    "base_url": "https://legacy.example.com",
                    "model_name": "gpt-4o",
                }
            ],
            "selected_api_config_id": "p1",
            "prompt_template": "旧版翻译提示词",
            "subtitle_font_size": "not-a-number",
        }
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        config = self.manager.load()

        self.assertEqual(config.ocr_api_configs[0].api_key, "sk-legacy-secret")
        self.assertEqual(config.translation_api_configs[0].api_key, "sk-legacy-secret")
        self.assertEqual(config.translation_prompt_template, "旧版翻译提示词")
        self.assertEqual(config.subtitle_font_size, DEFAULT_SUBTITLE_FONT_SIZE)

    def test_oldest_flat_structure_with_bad_field(self):
        data = {
            "api_key": "sk-flat-secret",
            "base_url": "https://flat.example.com",
            "model_name": "gpt-4o",
            "subtitle_background_opacity": "oops",
        }
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        config = self.manager.load()

        self.assertEqual(config.ocr_api_configs[0].api_key, "sk-flat-secret")
        self.assertEqual(config.translation_api_configs[0].api_key, "sk-flat-secret")
        self.assertEqual(
            config.subtitle_background_opacity, DEFAULT_SUBTITLE_BACKGROUND_OPACITY
        )


class CorruptFileBackupTests(unittest.TestCase):
    """文件整体损坏时：先备份原文件，再回退默认配置。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config_dir = Path(self._tmp.name)
        self.config_path = self.config_dir / "config.json"
        self.manager = ConfigManager(self.config_path)

    def _backups(self):
        return sorted(self.config_dir.glob("config.json.corrupt-*.bak"))

    def test_invalid_json_backed_up_before_defaults(self):
        corrupt_text = '{"api_key": "sk-do-not-lose-me", "base_url": '
        self.config_path.write_text(corrupt_text, encoding="utf-8")

        config = self.manager.load()

        self.assertEqual(config.subtitle_font_size, DEFAULT_SUBTITLE_FONT_SIZE)
        self.assertEqual(config.ocr_api_configs[0].api_key, "")
        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), corrupt_text)

    def test_same_corrupt_content_backed_up_once(self):
        corrupt_text = '{"api_key": "sk-do-not-lose-me", '
        self.config_path.write_text(corrupt_text, encoding="utf-8")
        self.manager.load()
        self.manager.load()
        self.manager.load()
        self.assertEqual(len(self._backups()), 1)

    def test_backup_survives_subsequent_save(self):
        """即使之后保存覆盖了 config.json，备份仍保留原始内容。"""
        corrupt_text = '{"api_key": "sk-do-not-lose-me", '
        self.config_path.write_text(corrupt_text, encoding="utf-8")

        config = self.manager.load()
        self.manager.save(config)

        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertIn("sk-do-not-lose-me", backups[0].read_text(encoding="utf-8"))

    def test_top_level_array_treated_as_corrupt(self):
        self.config_path.write_text('["not", "a", "dict"]', encoding="utf-8")
        config = self.manager.load()
        self.assertEqual(config.subtitle_font_size, DEFAULT_SUBTITLE_FONT_SIZE)
        self.assertEqual(len(self._backups()), 1)

    def test_empty_file_returns_defaults_without_backup(self):
        self.config_path.write_text("", encoding="utf-8")
        config = self.manager.load()
        self.assertEqual(config.subtitle_font_size, DEFAULT_SUBTITLE_FONT_SIZE)
        self.assertEqual(len(self._backups()), 0)

    def test_missing_file_returns_defaults(self):
        config = self.manager.load()
        self.assertTrue(config.ocr_api_configs)
        self.assertEqual(config.ocr_api_configs[0].api_key, "")


if __name__ == "__main__":
    unittest.main()
