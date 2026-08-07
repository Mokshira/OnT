from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_OCR_PROMPT_TEMPLATE = (
    "请完整提取图片中的所有文本内容。"
    "保持原有段落与换行结构。"
    "如果图片中包含数学公式，请尽量用清晰、可读的数学表达形式输出。"
    "只输出识别结果，不要添加解释。"
)
DEFAULT_TRANSLATION_PROMPT_TEMPLATE = (
    "请完整提取图片中的所有文本内容，识别结果翻译为[目标语言]。"
    "只输出翻译后的纯文本结果，不要任何多余的解释或废话。"
)
# 兼容旧代码中的导入名称
DEFAULT_PROMPT_TEMPLATE = DEFAULT_TRANSLATION_PROMPT_TEMPLATE

DEFAULT_MODEL_NAME = "gpt-5.4"
DEFAULT_REFRESH_SHORTCUT = "Ctrl+Shift+R"
DEFAULT_CONFIG_FILE_NAME = "config.json"
LEGACY_CONFIG_FILE_NAME = "config.son"
DEFAULT_API_PROFILE_NAME = "默认配置"
DEFAULT_SUBTITLE_FONT_SIZE = 18
DEFAULT_SUBTITLE_FONT_COLOR = "#ffffff"
DEFAULT_SUBTITLE_BACKGROUND_COLOR = "#000000"
DEFAULT_SUBTITLE_BACKGROUND_OPACITY = 24


def _new_profile_id() -> str:
    return uuid.uuid4().hex


@dataclass
class ApiConfig:
    """
    单套 API 连接配置。
    """

    profile_id: str = field(default_factory=_new_profile_id)
    profile_name: str = DEFAULT_API_PROFILE_NAME
    api_key: str = ""
    base_url: str = ""
    model_name: str = ""


@dataclass
class AppConfig:
    """
    应用整体配置：
    - ocr_api_configs：OCR 识别使用的多套 API 配置
    - translation_api_configs：翻译使用的多套 API 配置
    - selected_xxx_api_config_id：当前正在使用的配置
    - ocr_enabled：是否执行 OCR
    - translation_enabled：是否执行翻译
    - 其余字段为全局设置
    """

    ocr_api_configs: list[ApiConfig] = field(default_factory=lambda: [ApiConfig()])
    selected_ocr_api_config_id: str = ""
    translation_api_configs: list[ApiConfig] = field(
        default_factory=lambda: [ApiConfig()]
    )
    selected_translation_api_config_id: str = ""
    ocr_enabled: bool = True
    translation_enabled: bool = True
    target_language: str = "简体中文"
    ocr_prompt_template: str = DEFAULT_OCR_PROMPT_TEMPLATE
    translation_prompt_template: str = DEFAULT_TRANSLATION_PROMPT_TEMPLATE
    refresh_shortcut: str = DEFAULT_REFRESH_SHORTCUT
    subtitle_font_size: int = DEFAULT_SUBTITLE_FONT_SIZE
    subtitle_font_color: str = DEFAULT_SUBTITLE_FONT_COLOR
    subtitle_background_color: str = DEFAULT_SUBTITLE_BACKGROUND_COLOR
    subtitle_background_opacity: int = DEFAULT_SUBTITLE_BACKGROUND_OPACITY

    @staticmethod
    def _normalize_color(value: Any, default: str) -> str:
        text = str(value).strip().lower()
        if len(text) == 7 and text.startswith("#"):
            try:
                int(text[1:], 16)
                return text
            except ValueError:
                pass
        return default

    @staticmethod
    def _ensure_api_configs_valid(api_configs: list[ApiConfig]) -> list[ApiConfig]:
        if not api_configs:
            api_configs = [ApiConfig()]

        used_ids: set[str] = set()

        for index, item in enumerate(api_configs):
            if not item.profile_id.strip() or item.profile_id in used_ids:
                item.profile_id = _new_profile_id()
            used_ids.add(item.profile_id)

            if not item.profile_name.strip():
                item.profile_name = (
                    DEFAULT_API_PROFILE_NAME
                    if index == 0
                    else f"{DEFAULT_API_PROFILE_NAME}{index + 1}"
                )

            item.api_key = str(item.api_key).strip()
            item.base_url = str(item.base_url).strip()
            item.model_name = str(item.model_name).strip()

        return api_configs

    @staticmethod
    def _ensure_selected_id(
        api_configs: list[ApiConfig],
        selected_id: str,
    ) -> str:
        if not any(item.profile_id == selected_id for item in api_configs):
            return api_configs[0].profile_id
        return selected_id

    def ensure_valid_state(self) -> None:
        """
        规范化配置结构，确保：
        - OCR / 翻译至少各存在一套 API 配置
        - 每套配置都有合法且唯一的 profile_id
        - 当前选中项始终有效
        - 翻译展示区外观配置处于可用范围
        """
        self.ocr_api_configs = self._ensure_api_configs_valid(self.ocr_api_configs)
        self.translation_api_configs = self._ensure_api_configs_valid(
            self.translation_api_configs
        )

        self.selected_ocr_api_config_id = self._ensure_selected_id(
            self.ocr_api_configs,
            self.selected_ocr_api_config_id,
        )
        self.selected_translation_api_config_id = self._ensure_selected_id(
            self.translation_api_configs,
            self.selected_translation_api_config_id,
        )

        self.ocr_enabled = bool(self.ocr_enabled)
        self.translation_enabled = bool(self.translation_enabled)
        self.target_language = str(self.target_language).strip() or "简体中文"
        self.ocr_prompt_template = (
            str(self.ocr_prompt_template).strip() or DEFAULT_OCR_PROMPT_TEMPLATE
        )
        self.translation_prompt_template = (
            str(self.translation_prompt_template).strip()
            or DEFAULT_TRANSLATION_PROMPT_TEMPLATE
        )
        self.refresh_shortcut = (
            str(self.refresh_shortcut).strip() or DEFAULT_REFRESH_SHORTCUT
        )

        self.subtitle_font_size = min(
            max(int(self.subtitle_font_size), 10),
            72,
        )
        self.subtitle_font_color = self._normalize_color(
            self.subtitle_font_color,
            DEFAULT_SUBTITLE_FONT_COLOR,
        )
        self.subtitle_background_color = self._normalize_color(
            self.subtitle_background_color,
            DEFAULT_SUBTITLE_BACKGROUND_COLOR,
        )
        self.subtitle_background_opacity = min(
            max(int(self.subtitle_background_opacity), 0),
            100,
        )

    def get_selected_ocr_api_config(self) -> ApiConfig:
        self.ensure_valid_state()
        for item in self.ocr_api_configs:
            if item.profile_id == self.selected_ocr_api_config_id:
                return item

        self.selected_ocr_api_config_id = self.ocr_api_configs[0].profile_id
        return self.ocr_api_configs[0]

    def get_selected_translation_api_config(self) -> ApiConfig:
        self.ensure_valid_state()
        for item in self.translation_api_configs:
            if item.profile_id == self.selected_translation_api_config_id:
                return item

        self.selected_translation_api_config_id = self.translation_api_configs[
            0
        ].profile_id
        return self.translation_api_configs[0]


class ConfigManager:
    """
    配置管理器：
    负责将用户配置持久化到本地 JSON 文件，并提供读取能力。
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = (
            Path(config_path) if config_path is not None else self._default_config_path()
        )

    @staticmethod
    def _default_config_path() -> Path:
        """
        默认将配置文件放在“程序所在目录”下：
        - 开发态：项目根目录（ocr_translator 包的父目录）
        - 打包态：exe 所在目录
        """
        if getattr(sys, "frozen", False):
            app_dir = Path(sys.executable).resolve().parent
        else:
            app_dir = Path(__file__).resolve().parent.parent

        return app_dir / DEFAULT_CONFIG_FILE_NAME

    def _resolve_load_path(self) -> Path | None:
        """
        获取用于读取的配置文件路径。
        兼容历史文件名：若 config.json 不存在，则回退读取 config.son。
        """
        if self.config_path.exists():
            return self.config_path

        if self.config_path.name == DEFAULT_CONFIG_FILE_NAME:
            legacy_path = self.config_path.with_name(LEGACY_CONFIG_FILE_NAME)
            if legacy_path.exists():
                return legacy_path

        return None

    def load(self) -> AppConfig:
        """
        从本地读取配置。
        若文件不存在、内容为空或格式损坏，则返回默认配置。
        """
        load_path = self._resolve_load_path()
        if load_path is None:
            config = AppConfig()
            config.ensure_valid_state()
            return config

        try:
            raw_text = load_path.read_text(encoding="utf-8").strip()
            if not raw_text:
                config = AppConfig()
                config.ensure_valid_state()
                return config

            data = json.loads(raw_text)
            config = self._dict_to_config(data)
            config.ensure_valid_state()
            return config
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            config = AppConfig()
            config.ensure_valid_state()
            return config

    def save(self, config: AppConfig) -> None:
        """
        原子保存配置到本地 JSON 文件。

        先在同目录写入临时文件并 flush/fsync，再通过 os.replace 原子替换目标文件；
        任一步失败都保留原配置文件，避免产生半写入或截断的 config.json。

        Windows 上杀毒软件 / 文件索引器可能瞬时锁定 config.json，导致
        os.replace 抛出 WinError 5（拒绝访问）或 WinError 32（被占用）。
        针对这类可恢复的瞬时错误做有限次退避重试；重试耗尽后仍失败才抛出。
        """
        temp_path = self.config_path.with_name(f".{self.config_path.name}.tmp")
        try:
            config.ensure_valid_state()
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(asdict(config), ensure_ascii=False, indent=2)

            with temp_path.open("w", encoding="utf-8", newline="\n") as file:
                file.write(serialized)
                file.flush()
                os.fsync(file.fileno())

            self._atomic_replace(temp_path, self.config_path)
        except OSError as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(f"保存配置失败：{exc}") from exc

    @staticmethod
    def _atomic_replace(temp_path: Path, target_path: Path) -> None:
        """
        带退避重试的原子替换，用于缓解 Windows 上的瞬时文件锁定。

        仅对 WinError 5（拒绝访问）/ WinError 32（文件被占用）重试，
        其余 OSError 立即抛出。最多等待约 1.4 秒，避免长时间阻塞 UI。
        """
        retry_delays = (0.05, 0.1, 0.2, 0.4, 0.6)
        last_error: OSError | None = None

        for attempt, delay in enumerate(retry_delays):
            try:
                os.replace(temp_path, target_path)
                return
            except OSError as exc:
                last_error = exc
                # 真实 WinError 5/32 带 winerror；mock 或跨层转换可能只留 errno。
                winerror = getattr(exc, "winerror", None)
                err_no = getattr(exc, "errno", None)
                if winerror not in (5, 32) and err_no not in (5, 32):
                    raise
                if attempt < len(retry_delays) - 1:
                    time.sleep(delay)

        assert last_error is not None
        raise last_error

    @classmethod
    def _clone_api_configs(cls, api_configs: list[ApiConfig]) -> list[ApiConfig]:
        return [
            ApiConfig(
                profile_id=item.profile_id,
                profile_name=item.profile_name,
                api_key=item.api_key,
                base_url=item.base_url,
                model_name=item.model_name,
            )
            for item in api_configs
        ]

    @classmethod
    def _dict_to_config(cls, data: dict[str, Any]) -> AppConfig:
        """
        将字典安全转换为 AppConfig。
        同时兼容旧版单套 API 配置结构。
        """
        if not isinstance(data, dict):
            raise ValueError("配置文件格式无效。")

        if isinstance(data.get("ocr_api_configs"), list) or isinstance(
            data.get("translation_api_configs"),
            list,
        ):
            ocr_api_configs = [
                cls._dict_to_api_config(item, index)
                for index, item in enumerate(data.get("ocr_api_configs", []))
                if isinstance(item, dict)
            ]
            translation_api_configs = [
                cls._dict_to_api_config(item, index)
                for index, item in enumerate(data.get("translation_api_configs", []))
                if isinstance(item, dict)
            ]

            config = AppConfig(
                ocr_api_configs=ocr_api_configs or [ApiConfig()],
                selected_ocr_api_config_id=str(
                    data.get("selected_ocr_api_config_id", "")
                ),
                translation_api_configs=translation_api_configs or [ApiConfig()],
                selected_translation_api_config_id=str(
                    data.get("selected_translation_api_config_id", "")
                ),
                ocr_enabled=bool(data.get("ocr_enabled", True)),
                translation_enabled=bool(data.get("translation_enabled", True)),
                target_language=str(data.get("target_language", "简体中文")),
                ocr_prompt_template=str(
                    data.get("ocr_prompt_template", DEFAULT_OCR_PROMPT_TEMPLATE)
                ),
                translation_prompt_template=str(
                    data.get(
                        "translation_prompt_template",
                        DEFAULT_TRANSLATION_PROMPT_TEMPLATE,
                    )
                ),
                refresh_shortcut=str(
                    data.get("refresh_shortcut", DEFAULT_REFRESH_SHORTCUT)
                ),
                subtitle_font_size=int(
                    data.get("subtitle_font_size", DEFAULT_SUBTITLE_FONT_SIZE)
                ),
                subtitle_font_color=str(
                    data.get("subtitle_font_color", DEFAULT_SUBTITLE_FONT_COLOR)
                ),
                subtitle_background_color=str(
                    data.get(
                        "subtitle_background_color",
                        DEFAULT_SUBTITLE_BACKGROUND_COLOR,
                    )
                ),
                subtitle_background_opacity=int(
                    data.get(
                        "subtitle_background_opacity",
                        DEFAULT_SUBTITLE_BACKGROUND_OPACITY,
                    )
                ),
            )
            config.ensure_valid_state()
            return config

        if isinstance(data.get("api_configs"), list):
            legacy_api_configs = [
                cls._dict_to_api_config(item, index)
                for index, item in enumerate(data.get("api_configs", []))
                if isinstance(item, dict)
            ] or [ApiConfig()]

            ocr_api_configs = cls._clone_api_configs(legacy_api_configs)
            translation_api_configs = cls._clone_api_configs(legacy_api_configs)

            selected_api_config_id = str(data.get("selected_api_config_id", ""))
            config = AppConfig(
                ocr_api_configs=ocr_api_configs,
                selected_ocr_api_config_id=selected_api_config_id,
                translation_api_configs=translation_api_configs,
                selected_translation_api_config_id=selected_api_config_id,
                ocr_enabled=bool(data.get("ocr_enabled", True)),
                translation_enabled=bool(data.get("translation_enabled", True)),
                target_language=str(data.get("target_language", "简体中文")),
                ocr_prompt_template=DEFAULT_OCR_PROMPT_TEMPLATE,
                translation_prompt_template=str(
                    data.get("prompt_template", DEFAULT_TRANSLATION_PROMPT_TEMPLATE)
                ),
                refresh_shortcut=str(
                    data.get("refresh_shortcut", DEFAULT_REFRESH_SHORTCUT)
                ),
                subtitle_font_size=int(
                    data.get("subtitle_font_size", DEFAULT_SUBTITLE_FONT_SIZE)
                ),
                subtitle_font_color=str(
                    data.get("subtitle_font_color", DEFAULT_SUBTITLE_FONT_COLOR)
                ),
                subtitle_background_color=str(
                    data.get(
                        "subtitle_background_color",
                        DEFAULT_SUBTITLE_BACKGROUND_COLOR,
                    )
                ),
                subtitle_background_opacity=int(
                    data.get(
                        "subtitle_background_opacity",
                        DEFAULT_SUBTITLE_BACKGROUND_OPACITY,
                    )
                ),
            )
            config.ensure_valid_state()
            return config

        legacy_api_config = ApiConfig(
            profile_name=DEFAULT_API_PROFILE_NAME,
            api_key=str(data.get("api_key", "")),
            base_url=str(data.get("base_url", "")),
            model_name=str(data.get("model_name", "")),
        )
        config = AppConfig(
            ocr_api_configs=[
                ApiConfig(
                    profile_name=legacy_api_config.profile_name,
                    api_key=legacy_api_config.api_key,
                    base_url=legacy_api_config.base_url,
                    model_name=legacy_api_config.model_name,
                )
            ],
            selected_ocr_api_config_id="",
            translation_api_configs=[
                ApiConfig(
                    profile_name=legacy_api_config.profile_name,
                    api_key=legacy_api_config.api_key,
                    base_url=legacy_api_config.base_url,
                    model_name=legacy_api_config.model_name,
                )
            ],
            selected_translation_api_config_id="",
            ocr_enabled=bool(data.get("ocr_enabled", True)),
            translation_enabled=bool(data.get("translation_enabled", True)),
            target_language=str(data.get("target_language", "简体中文")),
            ocr_prompt_template=DEFAULT_OCR_PROMPT_TEMPLATE,
            translation_prompt_template=str(
                data.get("prompt_template", DEFAULT_TRANSLATION_PROMPT_TEMPLATE)
            ),
            refresh_shortcut=str(
                data.get("refresh_shortcut", DEFAULT_REFRESH_SHORTCUT)
            ),
            subtitle_font_size=int(
                data.get("subtitle_font_size", DEFAULT_SUBTITLE_FONT_SIZE)
            ),
            subtitle_font_color=str(
                data.get("subtitle_font_color", DEFAULT_SUBTITLE_FONT_COLOR)
            ),
            subtitle_background_color=str(
                data.get(
                    "subtitle_background_color",
                    DEFAULT_SUBTITLE_BACKGROUND_COLOR,
                )
            ),
            subtitle_background_opacity=int(
                data.get(
                    "subtitle_background_opacity",
                    DEFAULT_SUBTITLE_BACKGROUND_OPACITY,
                )
            ),
        )
        config.ensure_valid_state()
        return config

    @staticmethod
    def _dict_to_api_config(data: dict[str, Any], index: int) -> ApiConfig:
        """
        将字典安全转换为单套 API 配置。
        """
        profile_name = str(
            data.get("profile_name")
            or data.get("name")
            or (
                DEFAULT_API_PROFILE_NAME
                if index == 0
                else f"{DEFAULT_API_PROFILE_NAME}{index + 1}"
            )
        ).strip()

        return ApiConfig(
            profile_id=str(data.get("profile_id") or data.get("id") or "").strip()
            or _new_profile_id(),
            profile_name=profile_name or DEFAULT_API_PROFILE_NAME,
            api_key=str(data.get("api_key", "")),
            base_url=str(data.get("base_url", "")),
            model_name=str(data.get("model_name", "")),
        )


if __name__ == "__main__":
    manager = ConfigManager()
    config = manager.load()
    print("当前配置：", config)
