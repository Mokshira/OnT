from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

from PIL import Image
from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QMenu, QWidget


@dataclass
class CaptureResult:
    """
    截图结果对象。
    """

    image: Image.Image
    pixmap: QPixmap
    rect: QRect


def _qimage_to_pil_image(qimage) -> Image.Image:
    """
    将 QImage 安全转换为 PIL.Image。
    """
    if qimage.isNull():
        raise ValueError("QImage 为空，无法转换为 PIL.Image。")

    converted = qimage.convertToFormat(qimage.Format.Format_RGBA8888)

    width = converted.width()
    height = converted.height()
    bytes_per_line = converted.bytesPerLine()

    ptr = converted.bits()
    buffer = ptr.asstring(bytes_per_line * height)

    return Image.frombuffer(
        "RGBA",
        (width, height),
        buffer,
        "raw",
        "RGBA",
        bytes_per_line,
        1,
    ).convert("RGB")


def capture_region(rect: QRect) -> Optional[CaptureResult]:
    """
    根据给定矩形区域直接截图，并返回统一的 CaptureResult。

    这里使用 Qt 自带的 QScreen.grabWindow，而不是 mss。
    原因是鼠标框选得到的是 Qt 的屏幕坐标体系，在开启系统缩放
    （如 125%、150%）时，Qt 与 mss 可能出现逻辑坐标/物理像素偏移，
    导致截图位置整体上移或下移。使用 Qt 原生抓屏可保持坐标一致。
    """
    normalized_rect = rect.normalized()
    if normalized_rect.width() < 1 or normalized_rect.height() < 1:
        return None

    try:
        screen = QGuiApplication.screenAt(normalized_rect.center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None

        screen_geometry = screen.geometry()
        local_x = normalized_rect.left() - screen_geometry.left()
        local_y = normalized_rect.top() - screen_geometry.top()

        pixmap = screen.grabWindow(
            0,
            local_x,
            local_y,
            normalized_rect.width(),
            normalized_rect.height(),
        )
        if pixmap.isNull():
            return None

        image = _qimage_to_pil_image(pixmap.toImage())
        return CaptureResult(image=image, pixmap=pixmap, rect=normalized_rect)
    except Exception:
        return None


class SelectionFrameOverlay(QWidget):
    """
    用于在截图完成后持续显示最近一次框选区域的位置。
    支持用户直接拖动该框、右下角拉伸该框，并同步更新截图区域。
    支持右键菜单：
    - 刷新
    - 关闭框选翻译区
    """

    region_moved = pyqtSignal(QRect)
    refresh_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._target_rect = QRect()
        self._drag_offset = QPoint()
        self._dragging = False
        self._is_resizing = False
        self._resize_margin = 24
        self._resize_start_pos = QPoint()
        self._resize_start_rect = QRect()
        self._min_width = 60
        self._min_height = 40
        self._setup_window()

    def _setup_window(self) -> None:
        self.setWindowTitle("截图区域高亮框")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.hide()

    def show_region(self, rect: QRect) -> None:
        normalized_rect = rect.normalized()
        if normalized_rect.isNull():
            self.hide()
            return

        self._target_rect = normalized_rect
        self.setGeometry(normalized_rect)
        self.show()
        self.raise_()
        self.update()

    def clear_region(self) -> None:
        self._target_rect = QRect()
        self.hide()

    def _is_on_resize_handle(self, pos: QPoint) -> bool:
        return (
            pos.x() >= self.width() - self._resize_margin
            and pos.y() >= self.height() - self._resize_margin
        )

    def _update_cursor(self, pos: QPoint) -> None:
        if self._is_on_resize_handle(pos):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._target_rect.isNull():
            local_pos = event.position().toPoint()

            if self._is_on_resize_handle(local_pos):
                self._is_resizing = True
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_rect = self.geometry()
                event.accept()
                return

            self._dragging = True
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton and not self._target_rect.isNull():
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        local_pos = event.position().toPoint()

        if self._is_resizing and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            new_width = max(self._min_width, self._resize_start_rect.width() + delta.x())
            new_height = max(self._min_height, self._resize_start_rect.height() + delta.y())

            self.setGeometry(
                self._resize_start_rect.x(),
                self._resize_start_rect.y(),
                new_width,
                new_height,
            )
            self._target_rect = self.geometry()
            self.region_moved.emit(self._target_rect.normalized())
            event.accept()
            return

        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            new_top_left = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_top_left)
            self._target_rect.moveTo(new_top_left)
            self.region_moved.emit(self._target_rect.normalized())
            event.accept()
            return

        self._update_cursor(local_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging or self._is_resizing:
                self._dragging = False
                self._is_resizing = False
                self._target_rect = self.geometry()
                self.region_moved.emit(self._target_rect.normalized())
                self._update_cursor(event.position().toPoint())
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self._update_cursor(self.mapFromGlobal(QCursor.pos()))
        super().enterEvent(event)

    def _show_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        refresh_action = menu.addAction("刷新")
        close_action = menu.addAction("关闭")

        chosen = menu.exec(global_pos)
        if chosen == refresh_action:
            self.refresh_requested.emit()
        elif chosen == close_action:
            self.close_requested.emit()

    def paintEvent(self, event) -> None:
        if self._target_rect.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        outer_rect = self.rect().adjusted(1, 1, -2, -2)

        # 添加极浅填充，让鼠标在框内任意位置都能稳定命中该区域
        painter.setBrush(QColor(0, 180, 255, 18))
        painter.setPen(QPen(QColor(0, 180, 255, 235), 2))
        painter.drawRoundedRect(outer_rect, 8, 8)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(outer_rect.adjusted(3, 3, -3, -3), 6, 6)

        # 右下角拉伸手柄标识
        painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
        right = self.width() - 10
        bottom = self.height() - 10
        painter.drawLine(right - 18, bottom, right, bottom - 18)
        painter.drawLine(right - 12, bottom, right, bottom - 12)
        painter.drawLine(right - 6, bottom, right, bottom - 6)


class ScreenCaptureOverlay(QWidget):
    """
    全屏截图遮罩层：
    - 覆盖所有显示器的虚拟桌面区域
    - 支持鼠标拖拽框选
    - 截图完成后发出结果信号
    """

    capture_completed = pyqtSignal(object)
    capture_canceled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._origin = QPoint()
        self._current = QPoint()
        self._selection_rect = QRect()
        self._virtual_geometry = self._get_virtual_geometry()
        self._is_selecting = False
        self._setup_window()

    def _setup_window(self) -> None:
        self.setWindowTitle("屏幕截图")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(self._virtual_geometry)

    @staticmethod
    def _get_virtual_geometry() -> QRect:
        """
        计算所有显示器组成的虚拟桌面边界。
        该方法可确保多显示器下坐标正确。
        """
        screens = QGuiApplication.screens()
        if not screens:
            return QRect(0, 0, 1920, 1080)

        geometry = screens[0].geometry()
        for screen in screens[1:]:
            geometry = geometry.united(screen.geometry())
        return geometry

    def start_capture(self) -> None:
        """
        显示截图遮罩层并进入截图模式。
        """
        self._origin = QPoint()
        self._current = QPoint()
        self._selection_rect = QRect()
        self._is_selecting = False
        self.setGeometry(self._virtual_geometry)
        self.showFullScreen()
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_selecting = True
            self._origin = event.globalPosition().toPoint()
            self._current = self._origin
            self._selection_rect = QRect(self._origin, self._current).normalized()
            self.update()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel_capture()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_selecting:
            self._current = event.globalPosition().toPoint()
            self._selection_rect = QRect(self._origin, self._current).normalized()
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._is_selecting = False
            self._current = event.globalPosition().toPoint()
            self._selection_rect = QRect(self._origin, self._current).normalized()
            self.update()

            if self._selection_rect.width() < 5 or self._selection_rect.height() < 5:
                self._cancel_capture()
                return

            self.hide()
            QApplication.processEvents()
            result = self._capture_selected_region()

            if result is None:
                self.capture_canceled.emit()
            else:
                self.capture_completed.emit(result)
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_capture()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 整体半透明暗罩
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))

        if not self._selection_rect.isNull():
            local_rect = self._map_global_rect_to_local(self._selection_rect)

            # 擦除选区暗罩，突出选中范围
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(local_rect, Qt.GlobalColor.transparent)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(0, 180, 255), 2))
            painter.drawRect(local_rect)

    def _map_global_rect_to_local(self, rect: QRect) -> QRect:
        """
        将全局坐标矩形转换为当前窗口局部坐标。
        因为当前窗口本身可能位于虚拟桌面的负坐标区域。
        """
        top_left = rect.topLeft() - self.geometry().topLeft()
        return QRect(top_left, rect.size())

    def _capture_selected_region(self) -> Optional[CaptureResult]:
        """
        使用 mss 抓取选区，并转换为 PIL Image / QPixmap。
        """
        return capture_region(self._selection_rect)

    def _cancel_capture(self) -> None:
        self._is_selecting = False
        self._selection_rect = QRect()
        self.hide()
        self.capture_canceled.emit()
