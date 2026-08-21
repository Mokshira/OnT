from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextBlockFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from .theme import (
    BLUE,
    BLUE_SOFT,
    COMBO_HEIGHT,
    INK_2,
    INK_3,
    NAV_ITEM_HEIGHT,
    RADIUS_CONTROL,
    SIDEBAR_TOGGLE_SIZE,
)


def refresh_widget_style(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def apply_line_height(text_widget, percent: int = 170) -> None:
    """给文本控件的全文设置行高。

    设计稿里正文行高是 1.6~1.7，但 Qt Style Sheet 并不支持 line-height，
    只能通过 QTextBlockFormat 在文档层面设置。注意：setMarkdown /
    setPlainText 会重建文档，因此每次整体赋值后都需要重新调用。
    """
    try:
        document = text_widget.document()
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(
            float(percent),
            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
        )
        cursor.mergeBlockFormat(block_format)
        cursor.endEditBlock()
    except Exception:
        # 行高纯属视觉细节，不应因为 Qt 版本差异而影响功能。
        pass


class ShortcutCaptureEdit(QKeySequenceEdit):
    def __init__(self, status_label: QLabel, parent=None) -> None:
        super().__init__(parent)
        self._status_label = status_label
        self._idle_text = "点击输入框后，按下要绑定的组合键"
        self._recording_text = "正在录制快捷键，请直接按下组合键…"
        self._status_label.setText(self._idle_text)

    def focusInEvent(self, event) -> None:
        self._status_label.setText(self._recording_text)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._status_label.setText(self._idle_text)
        super().focusOutEvent(event)


class PromptTextEdit(QPlainTextEdit):
    """提示词编辑框：整体赋值后自动恢复设计稿的 1.6 行高。"""

    LINE_HEIGHT_PERCENT = 160

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        apply_line_height(self, self.LINE_HEIGHT_PERCENT)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        apply_line_height(self, self.LINE_HEIGHT_PERCENT)


class StyledComboBox(QComboBox):
    """下拉框：自绘 9x6 的 chevron，与设计稿 .combo .chevron 对齐。"""

    CHEVRON_WIDTH = 9.0
    CHEVRON_HEIGHT = 6.0
    CHEVRON_RIGHT_MARGIN = 12.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(COMBO_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_open = self.view().isVisible() if self.view() is not None else False
        arrow_color = QColor(BLUE) if (self.hasFocus() or is_open) else QColor(INK_3)
        pen = QPen(arrow_color, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        right = self.width() - self.CHEVRON_RIGHT_MARGIN
        left = right - self.CHEVRON_WIDTH
        top = (self.height() - self.CHEVRON_HEIGHT) / 2.0

        path = QPainterPath()
        path.moveTo(left, top)
        path.lineTo(left + (self.CHEVRON_WIDTH / 2.0), top + self.CHEVRON_HEIGHT)
        path.lineTo(right, top)
        painter.drawPath(path)


class ToggleSwitch(QAbstractButton):
    """Compact animated switch with the standard toggled(bool) contract."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(32, 18)
        self._offset = 0.0
        # 设计稿里开关没有焦点环；鼠标点击后也保留焦点环会很脏，
        # 因此只在键盘（Tab）获焦时才画。
        self._focus_visible = False
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to_state)

    def sizeHint(self) -> QSize:
        return QSize(32, 18)

    def setChecked(self, checked: bool) -> None:
        changed = bool(checked) != self.isChecked()
        super().setChecked(bool(checked))
        if changed and self.signalsBlocked():
            self._animation.stop()
            self.offset = 1.0 if checked else 0.0

    def focusInEvent(self, event) -> None:
        self._focus_visible = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        self._focus_visible = False
        super().focusOutEvent(event)
        self.update()

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = min(max(float(value), 0.0), 1.0)
        self.update()

    offset = pyqtProperty(float, fget=_get_offset, fset=_set_offset)

    def _animate_to_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.isEnabled():
            track_color = QColor(212, 212, 216, 150)
        elif self.isChecked():
            track_color = QColor(BLUE)
        else:
            track_color = QColor(0, 0, 0, 46)

        track_rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        if self._focus_visible:
            painter.setPen(QPen(QColor(BLUE), 1.0))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, 8.5, 8.5)

        knob_size = 14.0
        left = 2.0
        right = self.width() - knob_size - 2.0
        knob_x = left + ((right - left) * self._offset)
        knob_color = QColor("#ffffff")
        if not self.isEnabled():
            knob_color.setAlpha(190)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(QRectF(knob_x, 2.0, knob_size, knob_size))


class SegmentedControl(QWidget):
    selectionChanged = pyqtSignal(str)

    #: 设计稿：.segmented{padding:2px} + .seg-btn{height:28px}
    SEGMENT_HEIGHT = 28

    def __init__(self, segments: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SegmentedControl")
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.setFixedHeight(self.SEGMENT_HEIGHT + 4)
        self._buttons: dict[str, QPushButton] = {}
        self._current_key = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        for key, text in segments:
            button = QPushButton(text)
            button.setObjectName("SegmentButton")
            button.setCheckable(True)
            button.setProperty("active", False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            # 分段控件的选中态已经是强视觉反馈，再叠一层焦点框只会变脏。
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setFixedHeight(self.SEGMENT_HEIGHT)
            button.clicked.connect(
                lambda _checked=False, selected_key=key: self.setCurrentKey(
                    selected_key
                )
            )
            layout.addWidget(button)
            self._buttons[key] = button

        if segments:
            self.setCurrentKey(segments[0][0], emit_signal=False)

    def currentKey(self) -> str:
        return self._current_key

    def button(self, key: str) -> QPushButton:
        return self._buttons[key]

    def setCurrentKey(self, key: str, emit_signal: bool = True) -> None:
        if key not in self._buttons:
            return

        changed = key != self._current_key
        self._current_key = key
        for item_key, button in self._buttons.items():
            active = item_key == key
            button.blockSignals(True)
            button.setChecked(active)
            button.blockSignals(False)
            button.setProperty("active", active)
            refresh_widget_style(button)

        if changed and emit_signal:
            self.selectionChanged.emit(key)


class Pill(QLabel):
    #: 设计稿：.pill{height:22px}
    PILL_HEIGHT = 22

    def __init__(self, text: str = "", tone: str = "default", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.setFixedHeight(self.PILL_HEIGHT)
        self.setTone(tone)

    def setTone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        refresh_widget_style(self)


class KbdBadge(QLabel):
    #: 设计稿：.kbd{height:21px}
    KBD_HEIGHT = 21

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Kbd")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.setFixedHeight(self.KBD_HEIGHT)


# --------------------------------------------------------------------------
# 侧边栏（新 UI）：图标 + 可收起导航
# --------------------------------------------------------------------------

NAV_ICON_SIZE = 17
NAV_ICON_STROKE = 1.65
NAV_COLLAPSED_ITEM_SIZE = 36
#: 设计稿：.sidebar-item{padding:6px 10px} 且图标与文字间隔 10px
NAV_ICON_LEFT = 10
NAV_ICON_TEXT_GAP = 10
NAV_TEXT_RIGHT_PADDING = 8
#: 兼容保留（旧版用前导空格模拟图标间距，现在已改为自绘）
NAV_LABEL_PREFIX = ""

_NAV_PIXMAP_CACHE: dict[tuple[str, str, int, int], QPixmap] = {}


def _build_nav_icon_geometry(key: str) -> tuple[QPainterPath, list[QPointF]]:
    """按 24x24 画布还原设计稿里的线性图标（描边路径 + 实心圆点）。"""
    path = QPainterPath()
    dots: list[QPointF] = []

    if key == "overview":
        for x, y in ((3.0, 3.0), (15.0, 3.0), (3.0, 15.0), (15.0, 15.0)):
            path.addRoundedRect(QRectF(x, y, 6.0, 6.0), 1.2, 1.2)
    elif key == "results":
        path.moveTo(6.0, 3.5)
        path.lineTo(15.0, 3.5)
        path.lineTo(18.0, 6.5)
        path.lineTo(18.0, 20.5)
        path.lineTo(6.0, 20.5)
        path.closeSubpath()
        path.moveTo(15.0, 3.5)
        path.lineTo(15.0, 6.5)
        path.lineTo(18.0, 6.5)
        path.moveTo(9.0, 11.0)
        path.lineTo(15.0, 11.0)
        path.moveTo(9.0, 15.0)
        path.lineTo(15.0, 15.0)
    elif key == "api":
        path.moveTo(9.5, 8.5)
        path.lineTo(9.5, 6.0)
        path.arcTo(QRectF(9.5, 3.5, 5.0, 5.0), 180.0, -180.0)
        path.lineTo(14.5, 8.5)
        path.moveTo(14.5, 15.5)
        path.lineTo(14.5, 18.0)
        path.arcTo(QRectF(9.5, 15.5, 5.0, 5.0), 0.0, -180.0)
        path.lineTo(9.5, 15.5)
        path.addRoundedRect(QRectF(7.0, 8.5, 10.0, 7.0), 1.4, 1.4)
        path.moveTo(4.0, 12.0)
        path.lineTo(7.0, 12.0)
        path.moveTo(17.0, 12.0)
        path.lineTo(20.0, 12.0)
    elif key == "prompt":
        path.addRoundedRect(QRectF(4.0, 3.0, 16.0, 13.0), 2.5, 2.5)
        path.moveTo(11.0, 16.0)
        path.lineTo(6.5, 20.0)
        path.lineTo(6.5, 16.0)
        path.moveTo(8.0, 8.5)
        path.lineTo(16.0, 8.5)
        path.moveTo(8.0, 12.0)
        path.lineTo(13.0, 12.0)
    elif key == "shortcut":
        path.addRoundedRect(QRectF(3.0, 6.0, 18.0, 12.0), 2.0, 2.0)
        path.moveTo(7.0, 14.0)
        path.lineTo(17.0, 14.0)
        dots.extend(
            [
                QPointF(7.0, 10.0),
                QPointF(10.5, 10.0),
                QPointF(14.0, 10.0),
                QPointF(17.0, 10.0),
            ]
        )
    elif key == "about":
        path.addEllipse(QPointF(12.0, 12.0), 8.5, 8.5)
        path.moveTo(12.0, 10.8)
        path.lineTo(12.0, 15.6)
        dots.append(QPointF(12.0, 8.0))
    else:
        path.addRoundedRect(QRectF(4.0, 4.0, 16.0, 16.0), 3.0, 3.0)

    return path, dots


def build_nav_pixmap(
    key: str,
    color: str,
    size: int = NAV_ICON_SIZE,
    ratio: float = 2.0,
) -> QPixmap:
    """按屏幕缩放率渲染导航图标，结果缓存复用。

    ratio 传入真实的 devicePixelRatioF（125% 缩放下是 1.25），避免固定
    2.0 再被缩小到非整数倍而发虚；同时 QPainter 会自动按 pixmap 的
    devicePixelRatio 工作在逻辑像素上，因此缩放只需 size/24。
    """
    ratio = max(1.0, float(ratio))
    cache_key = (key, str(color), int(size), int(round(ratio * 100)))
    cached = _NAV_PIXMAP_CACHE.get(cache_key)
    if cached is not None:
        return cached

    pixmap = QPixmap(int(round(size * ratio)), int(round(size * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24.0, size / 24.0)

    icon_color = QColor(color)
    pen = QPen(icon_color, NAV_ICON_STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    path, dots = _build_nav_icon_geometry(key)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

    if dots:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_color)
        for dot in dots:
            painter.drawEllipse(dot, NAV_ICON_STROKE / 2.0, NAV_ICON_STROKE / 2.0)

    painter.end()
    _NAV_PIXMAP_CACHE[cache_key] = pixmap
    return pixmap


def build_nav_icon(key: str, color: str, size: int = NAV_ICON_SIZE) -> QIcon:
    """把导航图标包成 QIcon（保留给外部调用方使用）。"""
    return QIcon(build_nav_pixmap(key, color, size, 2.0))


def _build_chevron_pixmap(
    pointing_left: bool,
    color: str = INK_3,
    size: int = 14,
    ratio: float = 2.0,
) -> QPixmap:
    ratio = max(1.0, float(ratio))
    cache_key = (
        "chevron-left" if pointing_left else "chevron-right",
        str(color),
        int(size),
        int(round(ratio * 100)),
    )
    cached = _NAV_PIXMAP_CACHE.get(cache_key)
    if cached is not None:
        return cached

    pixmap = QPixmap(int(round(size * ratio)), int(round(size * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 16.0, size / 16.0)

    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    path = QPainterPath()
    if pointing_left:
        path.moveTo(9.8, 3.5)
        path.lineTo(5.3, 8.0)
        path.lineTo(9.8, 12.5)
    else:
        path.moveTo(6.2, 3.5)
        path.lineTo(10.7, 8.0)
        path.lineTo(6.2, 12.5)
    painter.drawPath(path)
    painter.end()

    _NAV_PIXMAP_CACHE[cache_key] = pixmap
    return pixmap


class SidebarNavButton(QAbstractButton):
    """侧边栏导航项：图标 + 文字完全自绘。

    Qt 无法用 QSS 控制 QPushButton 的图标位置和图标-文字间距，旧实现
    靠给文字加前导空格“凑”出间距，在不同字体下会微妙偏移。这里改成
    自己画：背景圆角 8px、图标左边距 10px、文字 13px，与设计稿一致。
    """

    def __init__(self, key: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._key = key
        self._label_text = text
        self._is_active = False
        self._is_collapsed = False

        self.setText(text)
        self.setProperty("active", False)
        self.setProperty("collapsed", False)
        self.setFixedHeight(NAV_ITEM_HEIGHT)

    def key(self) -> str:
        return self._key

    def labelText(self) -> str:
        return self._label_text

    def isActive(self) -> bool:
        return self._is_active

    def isCollapsed(self) -> bool:
        return self._is_collapsed

    def setActive(self, active: bool) -> None:
        self._is_active = bool(active)
        self.setProperty("active", self._is_active)
        self.update()

    def setCollapsed(self, collapsed: bool) -> None:
        self._is_collapsed = bool(collapsed)
        self.setProperty("collapsed", self._is_collapsed)

        if self._is_collapsed:
            self.setToolTip(self._label_text)
            self.setFixedSize(NAV_COLLAPSED_ITEM_SIZE, NAV_COLLAPSED_ITEM_SIZE)
        else:
            self.setToolTip("")
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.setFixedHeight(NAV_ITEM_HEIGHT)

        self.updateGeometry()
        self.update()

    def _label_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setWeight(
            QFont.Weight.DemiBold if self._is_active else QFont.Weight.Medium
        )
        return font

    def sizeHint(self) -> QSize:
        if self._is_collapsed:
            return QSize(NAV_COLLAPSED_ITEM_SIZE, NAV_COLLAPSED_ITEM_SIZE)

        text_width = QFontMetrics(self._label_font()).horizontalAdvance(
            self._label_text
        )
        width = (
            NAV_ICON_LEFT
            + NAV_ICON_SIZE
            + NAV_ICON_TEXT_GAP
            + text_width
            + NAV_TEXT_RIGHT_PADDING
        )
        return QSize(width, NAV_ITEM_HEIGHT)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._is_active:
            background = QColor(BLUE_SOFT)
        elif self.isDown():
            background = QColor(0, 0, 0, 20)
        elif self.underMouse():
            background = QColor(0, 0, 0, 10)
        else:
            background = None

        if background is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(
                QRectF(self.rect()),
                float(RADIUS_CONTROL),
                float(RADIUS_CONTROL),
            )

        color = BLUE if self._is_active else INK_2
        pixmap = build_nav_pixmap(
            self._key,
            color,
            NAV_ICON_SIZE,
            self.devicePixelRatioF(),
        )
        icon_top = int(round((self.height() - NAV_ICON_SIZE) / 2.0))

        if self._is_collapsed:
            icon_left = int(round((self.width() - NAV_ICON_SIZE) / 2.0))
            painter.drawPixmap(icon_left, icon_top, pixmap)
            return

        painter.drawPixmap(NAV_ICON_LEFT, icon_top, pixmap)

        font = self._label_font()
        painter.setFont(font)
        painter.setPen(QColor(color))

        text_left = NAV_ICON_LEFT + NAV_ICON_SIZE + NAV_ICON_TEXT_GAP
        text_width = max(0, self.width() - text_left - NAV_TEXT_RIGHT_PADDING)
        elided = QFontMetrics(font).elidedText(
            self._label_text,
            Qt.TextElideMode.ElideRight,
            text_width,
        )
        painter.drawText(
            QRect(text_left, 0, text_width, self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elided,
        )


class SidebarToggleButton(QPushButton):
    """垂直居中悬浮在侧边栏右边界上的圆形收起/展开按钮（抽屉把手样式）。"""

    ICON_SIZE = 14

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarToggle")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(SIDEBAR_TOGGLE_SIZE, SIDEBAR_TOGGLE_SIZE)
        self.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))

        self._is_collapsed = False
        self._is_hovered = False
        self.setCollapsed(False)

    def enterEvent(self, event) -> None:
        self._is_hovered = True
        self._refresh_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._is_hovered = False
        self._refresh_icon()
        super().leaveEvent(event)

    def _refresh_icon(self) -> None:
        # QSS 只能改文字颜色，图标颜色需要跟着 hover 手动切。
        pixmap = _build_chevron_pixmap(
            pointing_left=not self._is_collapsed,
            color=BLUE if self._is_hovered else INK_3,
            size=self.ICON_SIZE,
            ratio=self.devicePixelRatioF(),
        )
        self.setIcon(QIcon(pixmap))

    def setCollapsed(self, collapsed: bool) -> None:
        self._is_collapsed = bool(collapsed)
        if self._is_collapsed:
            self.setToolTip("展开侧边栏")
            self.setAccessibleName("展开侧边栏")
        else:
            self.setToolTip("收起侧边栏")
            self.setAccessibleName("收起侧边栏")
        self._refresh_icon()
