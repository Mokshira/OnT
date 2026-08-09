from __future__ import annotations

import ast
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ocr_translator.api_utils import normalize_base_url
from ocr_translator.config_manager import ApiConfig, AppConfig, ConfigManager


CONTROLLER_PATH = PROJECT_ROOT / "ocr_translator" / "app_controller.py"
MAIN_WINDOW_PATH = PROJECT_ROOT / "ocr_translator" / "main_window.py"


class FakeGlobalHotkeyManager:
    @staticmethod
    def _normalize_shortcut_text(shortcut_text: str) -> str:
        return shortcut_text.strip()


def _class_node(path: Path, class_name: str) -> ast.ClassDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )


def _method_node(
    path: Path,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef:
    class_definition = _class_node(path, class_name)
    return next(
        node
        for node in class_definition.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _load_method(
    path: Path,
    class_name: str,
    method_name: str,
):
    """Load one real method body without importing the PyQt6 application."""
    method = _method_node(path, class_name, method_name)
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "ApiConfig": ApiConfig,
        "AppConfig": AppConfig,
        "Callable": Callable,
        "GlobalHotkeyManager": FakeGlobalHotkeyManager,
        "copy": copy,
        "normalize_base_url": normalize_base_url,
    }
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[method_name]


class CountingConfigManager:
    def __init__(self) -> None:
        self.saved: list[AppConfig] = []

    def save(self, config: AppConfig) -> None:
        self.saved.append(copy.deepcopy(config))


class TransactionConfigManager:
    def __init__(self, config: AppConfig) -> None:
        self.disk_config = copy.deepcopy(config)
        self.saved: list[AppConfig] = []
        self.fail_save = False

    def load(self) -> AppConfig:
        return copy.deepcopy(self.disk_config)

    def save(self, config: AppConfig) -> None:
        if self.fail_save:
            raise RuntimeError("disk save failed")
        self.disk_config = copy.deepcopy(config)
        self.saved.append(copy.deepcopy(config))


class Toggle:
    def __init__(self, checked: bool) -> None:
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


def _saved_config() -> AppConfig:
    ocr = ApiConfig(
        profile_id="ocr-saved",
        profile_name="Saved OCR",
        api_key="sk-saved-ocr",
        base_url="https://saved.example/v1",
        model_name="ocr-model",
    )
    translation = ApiConfig(
        profile_id="translation-saved",
        profile_name="Saved translation",
        api_key="sk-saved-translation",
        base_url="https://saved.example/v1",
        model_name="translation-model",
    )
    config = AppConfig(
        ocr_api_configs=[ocr],
        selected_ocr_api_config_id=ocr.profile_id,
        translation_api_configs=[translation],
        selected_translation_api_config_id=translation.profile_id,
        ocr_enabled=True,
        translation_enabled=True,
        target_language="English",
        ocr_prompt_template="saved ocr prompt",
        translation_prompt_template="saved translation prompt",
        refresh_shortcut="Ctrl+Shift+R",
    )
    config.ensure_valid_state()
    return config


class ControllerHarness:
    _clone_config = _load_method(
        CONTROLLER_PATH,
        "AppController",
        "_clone_config",
    )
    _build_runtime_config = _load_method(
        CONTROLLER_PATH,
        "AppController",
        "_build_runtime_config",
    )
    _persist_scoped_config = _load_method(
        CONTROLLER_PATH,
        "AppController",
        "_persist_scoped_config",
    )
    _persist_api_profiles = _load_method(
        CONTROLLER_PATH,
        "AppController",
        "_persist_api_profiles",
    )
    on_service_enabled_toggled = _load_method(
        CONTROLLER_PATH,
        "AppController",
        "on_service_enabled_toggled",
    )
    save_config = _load_method(
        CONTROLLER_PATH,
        "AppController",
        "save_config",
    )

    def __init__(self, persisted_config: AppConfig) -> None:
        self._persisted_config = persisted_config
        self.config_manager = CountingConfigManager()
        self._is_quitting = False
        self.validated: list[AppConfig] = []
        self.messages: list[tuple[str, str]] = []
        self.main_window = None

    def _validate_config(
        self,
        config: AppConfig,
        allow_empty_api_for_save: bool = False,
    ) -> None:
        self.validated.append(config)

    def _show_info(self, title: str, message: str) -> None:
        self.messages.append((title, message))


class ConfigConsumer:
    def __init__(self) -> None:
        self.applied: list[AppConfig] = []

    def set_config(self, config: AppConfig) -> None:
        self.applied.append(copy.deepcopy(config))

    def apply_appearance_config(self, config: AppConfig) -> None:
        self.applied.append(copy.deepcopy(config))


class SaveControllerHarness(ControllerHarness):
    def __init__(self, old_config: AppConfig, new_config: AppConfig) -> None:
        super().__init__(copy.deepcopy(old_config))
        self.config_manager = TransactionConfigManager(old_config)
        self._ui_config = copy.deepcopy(new_config)
        self._global_hotkey_manager = type(
            "HotkeyState",
            (),
            {"current_shortcut": old_config.refresh_shortcut},
        )()
        self.main_window = ConfigConsumer()
        self.floating_window = ConfigConsumer()
        self.errors: list[tuple[str, str]] = []
        self.shortcut_calls: list[str] = []
        self.fail_registration = False

    def _build_config_from_ui(self) -> AppConfig:
        return copy.deepcopy(self._ui_config)

    def _setup_shortcuts(self, shortcut_text: str) -> None:
        self.shortcut_calls.append(shortcut_text)
        if self.fail_registration:
            self.fail_registration = False
            raise RuntimeError("registration failed")
        self._global_hotkey_manager.current_shortcut = shortcut_text

    def _show_error(self, title: str, message: str) -> None:
        self.errors.append((title, message))


class MainWindowHarness:
    _clone_api_config = _load_method(
        MAIN_WINDOW_PATH,
        "MainWindow",
        "_clone_api_config",
    )
    get_api_profiles_snapshot = _load_method(
        MAIN_WINDOW_PATH,
        "MainWindow",
        "get_api_profiles_snapshot",
    )


class PersistenceBehaviorTests(unittest.TestCase):
    def test_runtime_config_is_read_only_deep_copy(self) -> None:
        persisted = _saved_config()
        controller = ControllerHarness(persisted)

        runtime = controller._build_runtime_config()

        self.assertEqual(controller.config_manager.saved, [])
        self.assertIsNot(runtime, persisted)
        self.assertIs(controller.validated[0], runtime)
        self.assertEqual(runtime.ocr_api_configs[0].api_key, "sk-saved-ocr")
        self.assertEqual(
            runtime.ocr_api_configs[0].base_url,
            "https://saved.example/v1/chat/completions",
        )
        self.assertEqual(
            persisted.ocr_api_configs[0].base_url,
            "https://saved.example/v1",
        )
        runtime.ocr_api_configs[0].api_key = "mutated"
        self.assertEqual(persisted.ocr_api_configs[0].api_key, "sk-saved-ocr")

    def test_scoped_write_preserves_unowned_fields(self) -> None:
        persisted = _saved_config()
        controller = ControllerHarness(persisted)

        def apply_appearance(config: AppConfig) -> None:
            config.subtitle_font_size = 31
            config.subtitle_background_opacity = 63

        result = controller._persist_scoped_config(apply_appearance)

        self.assertEqual(len(controller.config_manager.saved), 1)
        self.assertIs(controller._persisted_config, result)
        self.assertEqual(result.subtitle_font_size, 31)
        self.assertEqual(result.subtitle_background_opacity, 63)
        self.assertEqual(result.refresh_shortcut, "Ctrl+Shift+R")
        self.assertEqual(result.ocr_prompt_template, "saved ocr prompt")
        self.assertEqual(result.ocr_api_configs[0].api_key, "sk-saved-ocr")

    def test_profile_write_does_not_leak_other_drafts(self) -> None:
        persisted = _saved_config()
        controller = ControllerHarness(persisted)
        new_ocr = ApiConfig(
            profile_id="ocr-new",
            profile_name="New OCR",
            api_key="sk-new",
            base_url="https://new.example/v1",
            model_name="new-model",
        )
        controller.main_window = type(
            "ProfileWindow",
            (),
            {
                "get_api_profiles_snapshot": lambda self: (
                    [copy.deepcopy(new_ocr)],
                    new_ocr.profile_id,
                    copy.deepcopy(persisted.translation_api_configs),
                    persisted.selected_translation_api_config_id,
                )
            },
        )()

        result = controller._persist_api_profiles()

        self.assertEqual(result.selected_ocr_api_config_id, "ocr-new")
        self.assertEqual(result.ocr_api_configs[0].api_key, "sk-new")
        self.assertEqual(
            result.ocr_api_configs[0].base_url,
            "https://new.example/v1/chat/completions",
        )
        self.assertEqual(result.refresh_shortcut, "Ctrl+Shift+R")
        self.assertEqual(result.ocr_prompt_template, "saved ocr prompt")
        self.assertTrue(result.ocr_enabled)

    def test_service_toggle_only_persists_service_fields(self) -> None:
        persisted = _saved_config()
        controller = ControllerHarness(persisted)
        controller.main_window = type(
            "ToggleWindow",
            (),
            {
                "ocr_enabled_button": Toggle(False),
                "translation_enabled_button": Toggle(True),
            },
        )()

        controller.on_service_enabled_toggled()

        self.assertEqual(len(controller.config_manager.saved), 1)
        result = controller._persisted_config
        self.assertFalse(result.ocr_enabled)
        self.assertTrue(result.translation_enabled)
        self.assertEqual(result.refresh_shortcut, "Ctrl+Shift+R")
        self.assertEqual(result.ocr_prompt_template, "saved ocr prompt")

    def test_profile_snapshot_is_independent_clone(self) -> None:
        harness = MainWindowHarness()
        original_ocr = _saved_config().ocr_api_configs[0]
        original_translation = _saved_config().translation_api_configs[0]
        harness._ocr_api_configs = [original_ocr]
        harness._selected_ocr_api_config_id = original_ocr.profile_id
        harness._translation_api_configs = [original_translation]
        harness._selected_translation_api_config_id = original_translation.profile_id

        ocr, ocr_id, translation, translation_id = (
            harness.get_api_profiles_snapshot()
        )
        ocr[0].api_key = "mutated"
        translation[0].model_name = "mutated"

        self.assertEqual(ocr_id, original_ocr.profile_id)
        self.assertEqual(translation_id, original_translation.profile_id)
        self.assertEqual(original_ocr.api_key, "sk-saved-ocr")
        self.assertEqual(original_translation.model_name, "translation-model")

    def test_scoped_write_updates_real_config_file(self) -> None:
        persisted = _saved_config()
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ConfigManager(Path(temp_dir) / "config.json")
            manager.save(persisted)
            controller = ControllerHarness(persisted)
            controller.config_manager = manager

            controller._persist_scoped_config(
                lambda config: setattr(config, "ocr_enabled", False)
            )
            restored = manager.load()

        self.assertFalse(restored.ocr_enabled)
        self.assertEqual(restored.refresh_shortcut, "Ctrl+Shift+R")
        self.assertEqual(restored.ocr_prompt_template, "saved ocr prompt")

    def test_save_transaction_updates_registered_shortcut_and_cache(self) -> None:
        old_config = _saved_config()
        new_config = copy.deepcopy(old_config)
        new_config.refresh_shortcut = "Ctrl+Shift+T"
        new_config.ocr_prompt_template = "new prompt"
        controller = SaveControllerHarness(old_config, new_config)

        controller.save_config()

        self.assertEqual(controller.shortcut_calls, ["Ctrl+Shift+T"])
        self.assertEqual(
            controller._global_hotkey_manager.current_shortcut,
            "Ctrl+Shift+T",
        )
        self.assertEqual(
            controller.config_manager.disk_config.refresh_shortcut,
            "Ctrl+Shift+T",
        )
        self.assertEqual(controller._persisted_config.refresh_shortcut, "Ctrl+Shift+T")
        self.assertEqual(controller._persisted_config.ocr_prompt_template, "new prompt")
        self.assertEqual(controller.errors, [])

    def test_save_transaction_registration_failure_restores_disk_and_cache(self) -> None:
        old_config = _saved_config()
        new_config = copy.deepcopy(old_config)
        new_config.refresh_shortcut = "Ctrl+Shift+T"
        controller = SaveControllerHarness(old_config, new_config)
        controller.fail_registration = True

        controller.save_config()

        self.assertEqual(controller.config_manager.saved, [])
        self.assertEqual(
            controller._global_hotkey_manager.current_shortcut,
            "Ctrl+Shift+R",
        )
        self.assertEqual(
            controller.config_manager.disk_config.refresh_shortcut,
            "Ctrl+Shift+R",
        )
        self.assertEqual(controller._persisted_config.refresh_shortcut, "Ctrl+Shift+R")
        self.assertEqual(controller.main_window.applied[-1].refresh_shortcut, "Ctrl+Shift+R")
        self.assertTrue(controller.errors)

    def test_save_transaction_disk_failure_rolls_back_registered_shortcut(self) -> None:
        old_config = _saved_config()
        new_config = copy.deepcopy(old_config)
        new_config.refresh_shortcut = "Ctrl+Shift+T"
        controller = SaveControllerHarness(old_config, new_config)
        controller.config_manager.fail_save = True

        controller.save_config()

        self.assertEqual(
            controller.shortcut_calls,
            ["Ctrl+Shift+T", "Ctrl+Shift+R"],
        )
        self.assertEqual(
            controller._global_hotkey_manager.current_shortcut,
            "Ctrl+Shift+R",
        )
        self.assertEqual(
            controller.config_manager.disk_config.refresh_shortcut,
            "Ctrl+Shift+R",
        )
        self.assertEqual(controller._persisted_config.refresh_shortcut, "Ctrl+Shift+R")
        self.assertTrue(controller.errors)


class PersistenceArchitectureTests(unittest.TestCase):
    def test_removed_legacy_persistence_helpers(self) -> None:
        controller = _class_node(CONTROLLER_PATH, "AppController")
        methods = {
            node.name
            for node in controller.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertNotIn("_validate_and_" + "persist_config", methods)
        self.assertNotIn("_persist_config_" + "without_validation", methods)

    def test_hot_paths_only_build_runtime_config(self) -> None:
        for method_name in (
            "start_capture",
            "_process_capture_result",
            "translate_clipboard_image",
        ):
            method = _method_node(
                CONTROLLER_PATH,
                "AppController",
                method_name,
            )
            self_calls = {
                node.func.attr
                for node in ast.walk(method)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
            }
            self.assertIn("_build_runtime_config", self_calls)
            self.assertNotIn("_build_config_from_ui", self_calls)
            self.assertNotIn("_persist_scoped_config", self_calls)

    def test_config_manager_save_has_only_two_owners(self) -> None:
        controller = _class_node(CONTROLLER_PATH, "AppController")
        owners: set[str] = set()
        for method in controller.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                function = node.func
                if not isinstance(function, ast.Attribute) or function.attr != "save":
                    continue
                manager = function.value
                if (
                    isinstance(manager, ast.Attribute)
                    and isinstance(manager.value, ast.Name)
                    and manager.value.id == "self"
                    and manager.attr == "config_manager"
                ):
                    owners.add(method.name)

        self.assertEqual(owners, {"_persist_scoped_config", "save_config"})

    def test_ui_builder_is_limited_to_save_and_model_fetch(self) -> None:
        controller = _class_node(CONTROLLER_PATH, "AppController")
        callers: set[str] = set()
        for method in controller.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
                and node.func.attr == "_build_config_from_ui"
                for node in ast.walk(method)
            ):
                callers.add(method.name)

        self.assertEqual(callers, {"fetch_models", "save_config"})


if __name__ == "__main__":
    unittest.main()
