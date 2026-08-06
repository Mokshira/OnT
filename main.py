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
    # 禁止“最后一个窗口关闭即退出”，避免绕过控制器的异步线程排空。
    app.setQuitOnLastWindowClosed(False)

    controller = AppController()
    app._controller = controller  # type: ignore[attr-defined]

    try:
        return app.exec()
    finally:
        # 无论 app.exec() 因何返回，都同步排空遗留线程。
        controller.finalize_threads()


if __name__ == "__main__":
    sys.exit(main())
