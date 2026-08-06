from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional

from PyQt6.QtCore import QAbstractNativeEventFilter


class GlobalHotkeyManager(QAbstractNativeEventFilter):
    HOTKEY_ID = 1001
    WM_HOTKEY = 0x0312

    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback
        self._registered = False
        self._current_shortcut = ""

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0

        msg = wintypes.MSG.from_address(int(message))
        if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
            self.callback()
            return True, 0

        return False, 0

    @property
    def current_shortcut(self) -> str:
        return self._current_shortcut

    def register_shortcut(self, shortcut_text: str) -> None:
        """
        事务性切换全局快捷键。

        先完成格式解析，再注销旧快捷键并尝试注册新快捷键；如果注册失败，
        会立即恢复旧快捷键，避免应用进入“没有可用快捷键”的状态。
        """
        normalized = self._normalize_shortcut_text(shortcut_text)
        if not normalized:
            raise ValueError("快捷键不能为空。")

        # 在动旧注册前先完成全部格式验证。
        modifier, vk = self._parse_qt_shortcut(normalized)
        if self._registered and normalized == self._current_shortcut:
            return

        old_shortcut = self._current_shortcut if self._registered else ""
        self.unregister_shortcut()

        user32 = ctypes.windll.user32
        success = user32.RegisterHotKey(None, self.HOTKEY_ID, modifier, vk)
        if success:
            self._registered = True
            self._current_shortcut = normalized
            return

        restore_error = ""
        if old_shortcut:
            try:
                old_modifier, old_vk = self._parse_qt_shortcut(old_shortcut)
                restored = user32.RegisterHotKey(
                    None,
                    self.HOTKEY_ID,
                    old_modifier,
                    old_vk,
                )
                if restored:
                    self._registered = True
                    self._current_shortcut = old_shortcut
                else:
                    restore_error = "，且旧快捷键恢复失败"
            except Exception:
                restore_error = "，且旧快捷键恢复失败"

        raise RuntimeError(
            f"全局快捷键注册失败：{normalized}。该快捷键可能已被其他程序占用{restore_error}。"
        )

    def unregister_shortcut(self) -> None:
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self._registered = False
            self._current_shortcut = ""

    @staticmethod
    def _normalize_shortcut_text(shortcut_text: str) -> str:
        return shortcut_text.split(",", 1)[0].strip()

    @classmethod
    def _parse_qt_shortcut(cls, shortcut_text: str) -> tuple[int, int]:
        parts = [part.strip() for part in shortcut_text.split("+") if part.strip()]
        if not parts:
            raise ValueError("快捷键不能为空。")

        modifier_map = {
            "CTRL": 0x0002,
            "CONTROL": 0x0002,
            "ALT": 0x0001,
            "SHIFT": 0x0004,
            "META": 0x0008,
            "WIN": 0x0008,
        }

        modifier = 0
        key_part = ""

        for part in parts:
            upper = part.upper()
            if upper in modifier_map:
                modifier |= modifier_map[upper]
            else:
                key_part = upper

        if not key_part:
            raise ValueError("快捷键必须包含一个主键。")

        vk = cls._key_to_vk(key_part)
        if vk is None:
            raise ValueError(f"暂不支持的快捷键主键：{key_part}")

        return modifier, vk

    @staticmethod
    def _key_to_vk(key_part: str) -> Optional[int]:
        if len(key_part) == 1:
            ch = key_part.upper()
            if "A" <= ch <= "Z" or "0" <= ch <= "9":
                return ord(ch)

        function_keys = {f"F{i}": 0x6F + i for i in range(1, 25)}
        if key_part in function_keys:
            return function_keys[key_part]

        extra_keys = {
            "SPACE": 0x20,
            "TAB": 0x09,
            "BACKSPACE": 0x08,
            "ESC": 0x1B,
            "ESCAPE": 0x1B,
            "ENTER": 0x0D,
            "RETURN": 0x0D,
            "LEFT": 0x25,
            "UP": 0x26,
            "RIGHT": 0x27,
            "DOWN": 0x28,
            "HOME": 0x24,
            "END": 0x23,
            "PAGEUP": 0x21,
            "PAGEDOWN": 0x22,
            "INSERT": 0x2D,
            "DELETE": 0x2E,
        }
        return extra_keys.get(key_part)
