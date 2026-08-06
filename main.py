from __future__ import annotations

import ctypes
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from ocr_translator.app_controller import AppController


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Mo.OCR.VLMTranslator"
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("OCR与翻译助手")

    controller = AppController()
    app._controller = controller  # type: ignore[attr-defined]

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
