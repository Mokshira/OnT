"""OCR 与翻译助手应用包。"""

__all__ = ["AppController"]


def __getattr__(name: str):
    if name == "AppController":
        from .app_controller import AppController

        return AppController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
