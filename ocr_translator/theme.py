from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget


# --------------------------------------------------------------------------
# 颜色令牌（与设计稿 index.css 的 :root 一一对应）
# --------------------------------------------------------------------------
# 新 UI：窗口底色改为纯 #fafafa。原来的白→灰竖向渐变会让侧边栏（纯 #fafafa）
# 与窗口背景在不同高度出现色差，收起/展开侧边栏时那道竖直接缝尤其明显。
WINDOW_BG = "#fafafa"
BG_BASE = "#fafafa"
SURFACE = "#ffffff"
SURFACE_2 = "#f4f4f5"
# 设计稿里按钮 hover 是 filter:brightness(.97)，QSS 没有滤镜，
# 因此把变暗后的结果预先算成静态颜色。
SURFACE_3 = "#e9e9ec"
SIDEBAR_BG = "#fafafa"
NAV_HOVER = "rgba(0, 0, 0, 10)"
NAV_PRESSED = "rgba(0, 0, 0, 20)"
LINE = "#e4e4e7"
LINE_STRONG = "#d4d4d8"
LINE_SOFT = "#f4f4f5"
INK = "#09090b"
INK_HOVER = "#27272a"
INK_PRESSED = "#18181b"
INK_2 = "#3f3f46"
INK_3 = "#71717a"
INK_4 = "#a1a1aa"
INK_5 = "#d4d4d8"
BLUE = "#2563eb"
BLUE_HOVER = "#1d4ed8"
BLUE_PRESSED = "#1e40af"
BLUE_SOFT = "#eff4ff"
BLUE_SOFT_STRONG = "#e0e9ff"
BLUE_RING = "rgba(37, 99, 235, 56)"
OK = "#16a34a"
OK_SOFT = "#ecfdf5"
WARN = "#d97706"
WARN_SOFT = "#fff7ed"
ERR = "#dc2626"
ERR_SOFT = "#fef2f2"
ERR_BORDER = "#fca5a5"
# 新 UI：浅色语义块用的描边，比主色淡一档，避免大面积蓝/橙描边过重。
BLUE_BORDER = "#c7dbff"
BLUE_BORDER_HOVER = "#a9c8ff"
WARN_BORDER = "#fed7aa"
SEG_BG = "rgba(0, 0, 0, 10)"
TOGGLE_OFF = "rgba(0, 0, 0, 46)"
TOAST_BG = "#18181b"

# --------------------------------------------------------------------------
# 尺寸令牌
# --------------------------------------------------------------------------
RADIUS_CARD = 14
RADIUS_PANEL = 12
RADIUS_CONTROL = 8
RADIUS_SM = 6
SIDEBAR_WIDTH = 188
SIDEBAR_COLLAPSED_WIDTH = 52
# 新 UI：收起按钮从「压在分隔线上的 26px 圆钮」改为侧边栏内右下角的
# 36x34 浅蓝按钮（设计稿 .sidebar-toggle）。
SIDEBAR_TOGGLE_WIDTH = 36
SIDEBAR_TOGGLE_HEIGHT = 34
SIDEBAR_TOGGLE_MARGIN = 16
SIDEBAR_TOGGLE_MARGIN_COLLAPSED = 8
SIDEBAR_TOGGLE_BOTTOM_MARGIN = 14
#: 兼容旧代码的别名：按钮已不再是正方形，请改用上面的宽/高常量。
SIDEBAR_TOGGLE_SIZE = SIDEBAR_TOGGLE_HEIGHT
CONTENT_MARGIN = 14
TOAST_BOTTOM_OFFSET = 28
# 设计稿：.sidebar{gap:6px} / .sidebar-item{height:34px}
NAV_ITEM_HEIGHT = 34
NAV_ITEM_SPACING = 6
# 设计稿：.btn{height:34px} / .combo{height:36px} / 正文基准字号 13px
CONTROL_HEIGHT = 34
COMBO_HEIGHT = 36
BASE_FONT_PIXEL_SIZE = 13

FONT_FAMILIES = [
    "Segoe UI Variable Display",
    "Segoe UI",
    "Microsoft YaHei",
]
MONO_FONT_FAMILIES = ["Cascadia Code", "Consolas", "Microsoft YaHei"]


def build_stylesheet() -> str:
    """Return the light, window-scoped stylesheet used by OnT's main UI."""
    return f"""
    QMainWindow#MainWindow {{
        background: {WINDOW_BG};
        color: {INK};
    }}

    QWidget#AppRoot,
    QWidget#SettingsRoot,
    QWidget#ContentViewport,
    QWidget#SettingsPageViewport,
    QWidget#SidebarNav,
    QWidget#FieldGroup {{
        background: transparent;
        color: {INK};
    }}

    QLabel {{
        background: transparent;
        color: {INK_2};
        font-size: 13px;
    }}
    QLabel#AppBrand {{
        color: {INK};
        font-size: 26px;
        font-weight: 700;
    }}
    QLabel#BrandName {{
        color: {INK};
        font-size: 16px;
        font-weight: 600;
    }}
    QLabel#Eyebrow {{
        color: {INK_4};
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#PageTitle {{
        color: {INK};
        font-size: 22px;
        font-weight: 600;
    }}
    QLabel#PageDescription {{
        color: {INK_3};
        font-size: 13px;
    }}
    QLabel#SectionTitle {{
        color: {INK};
        font-size: 16px;
        font-weight: 600;
    }}
    QLabel#CardTitle {{
        color: {INK};
        font-size: 13px;
        font-weight: 600;
    }}
    QLabel#CardDetail,
    QLabel#Hint,
    QLabel#RowDescription {{
        color: {INK_3};
        font-size: 11px;
    }}
    QLabel#RowLabel {{
        color: {INK};
        font-size: 13px;
        font-weight: 500;
    }}
    QLabel#Muted {{
        color: {INK_4};
        font-size: 11px;
    }}

    QFrame#Sidebar {{
        background: {SIDEBAR_BG};
        border: none;
        border-right: 1px solid {LINE};
    }}
    QFrame#ContentArea {{
        background: transparent;
        border: none;
    }}
    QFrame#ContentCard {{
        background: {SURFACE};
        border: 1px solid {LINE};
        border-radius: {RADIUS_CARD}px;
    }}
    QFrame#SettingsPageActions {{
        background: transparent;
        border: none;
        border-top: 1px solid {LINE_SOFT};
    }}
    QFrame#HintCard {{
        background: {BLUE_SOFT};
        border: 1px solid {BLUE_RING};
        border-radius: {RADIUS_PANEL}px;
    }}
    /* 新 UI：提示卡拆成两种语义 —— 蓝色 HintCard 用于普通说明，
       橙色 NoteCard 用于「注意 / 可能失败」类提醒（.note-card）。 */
    QFrame#NoteCard {{
        background: {WARN_SOFT};
        border: 1px solid {WARN_BORDER};
        border-radius: {RADIUS_PANEL}px;
    }}
    QFrame#NoteCard QLabel#CardTitle {{
        color: {WARN};
    }}
    QFrame#StatusCard,
    QFrame#PreviewCard,
    QFrame#ResultCard,
    QFrame#AboutPanel {{
        background: {SURFACE};
        border: 1px solid {LINE};
        border-radius: {RADIUS_PANEL}px;
    }}
    QFrame#SettingsRow {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {LINE_SOFT};
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QStackedWidget {{
        background: transparent;
        border: none;
    }}

    /* ---------------- 按钮 ---------------- */
    QPushButton {{
        min-height: 18px;
        padding: 7px 14px;
        border: 1px solid transparent;
        border-radius: {RADIUS_CONTROL}px;
        background: transparent;
        color: {INK_2};
        font-size: 12px;
        font-weight: 600;
    }}
    /* 新 UI：中性按钮的 hover 改为浅底 + 实描边（.btn:not(:disabled):hover）。
       原来的半透明黑底叠在白卡片上几乎看不出反馈。 */
    QPushButton:hover {{
        background: {SURFACE_2};
        border-color: {LINE_STRONG};
    }}
    QPushButton:pressed {{
        background: {SURFACE_3};
        border-color: {LINE_STRONG};
    }}
    QPushButton:disabled {{
        background: {SURFACE_2};
        color: {INK_5};
        border-color: transparent;
    }}
    QPushButton[variant="primary"],
    QPushButton#PrimaryButton {{
        background: {INK};
        color: {SURFACE};
        border-color: {INK};
    }}
    QPushButton[variant="primary"]:hover,
    QPushButton#PrimaryButton:hover {{
        background: {INK_HOVER};
        border-color: {INK_HOVER};
    }}
    QPushButton[variant="primary"]:pressed,
    QPushButton#PrimaryButton:pressed {{
        background: {INK_PRESSED};
        border-color: {INK_PRESSED};
    }}
    QPushButton[variant="blue"] {{
        background: {BLUE};
        color: {SURFACE};
        border-color: {BLUE};
    }}
    QPushButton[variant="blue"]:hover {{
        background: {BLUE_HOVER};
        border-color: {BLUE_HOVER};
    }}
    QPushButton[variant="blue"]:pressed {{
        background: {BLUE_PRESSED};
        border-color: {BLUE_PRESSED};
    }}
    QPushButton[variant="ghost"],
    QPushButton#SecondaryButton {{
        background: transparent;
        color: {INK_2};
        border-color: {LINE_STRONG};
    }}
    QPushButton[variant="ghost"]:hover,
    QPushButton#SecondaryButton:hover {{
        background: {SURFACE_2};
        border-color: {LINE_STRONG};
    }}
    QPushButton[variant="ghost"]:pressed,
    QPushButton#SecondaryButton:pressed {{
        background: {SURFACE_3};
        border-color: {LINE_STRONG};
    }}
    QPushButton[variant="soft"],
    QPushButton#SecondaryButton:checked {{
        background: {SURFACE_2};
        color: {INK_2};
        border-color: transparent;
    }}
    QPushButton[variant="soft"]:hover,
    QPushButton#SecondaryButton:checked:hover {{
        background: {SURFACE_3};
    }}
    QPushButton[variant="soft"]:pressed,
    QPushButton#SecondaryButton:checked:pressed {{
        background: {LINE};
    }}
    QPushButton[variant="danger"] {{
        background: transparent;
        color: {ERR};
        border-color: {LINE_STRONG};
    }}
    QPushButton[variant="danger"]:hover {{
        background: {ERR_SOFT};
        border-color: {ERR_BORDER};
    }}
    QPushButton[variant="danger"]:pressed {{
        background: #fee2e2;
        border-color: {ERR_BORDER};
    }}

    /* 新 UI：概览页标题栏的两个操作同属中性次要操作，统一成浅色语义，
       不再用黑底主按钮把「开始框选」抬成整页主视觉（.overview-head-actions）。 */
    QPushButton#OverviewHeadButton {{
        background: {SURFACE};
        color: {INK};
        border-color: {LINE};
    }}
    QPushButton#OverviewHeadButton:hover {{
        background: {SURFACE_2};
        border-color: {LINE_STRONG};
        color: {INK};
    }}
    QPushButton#OverviewHeadButton:pressed {{
        background: {SURFACE_3};
        border-color: {LINE_STRONG};
    }}
    /* 开关型按钮（剪贴板自动处理）的选中态：保留一档可见的浅底，
       不然开/关两种状态在界面上完全一样。 */
    QPushButton#OverviewHeadButton:checked {{
        background: {SURFACE_2};
        border-color: {LINE_STRONG};
        color: {INK};
    }}
    QPushButton#OverviewHeadButton:checked:hover {{
        background: {SURFACE_3};
        border-color: {LINE_STRONG};
    }}
    QPushButton#OverviewHeadButton:disabled {{
        background: {SURFACE_2};
        color: {INK_5};
        border-color: transparent;
    }}

    /* 侧边栏导航项由 SidebarNavButton 自行绘制（图标 + 文字精确对齐），
       这里仅保留旧的设置导航样式。 */
    QPushButton#SettingsNavItem {{
        min-height: 20px;
        padding: 6px 10px;
        border: 1px solid transparent;
        border-radius: {RADIUS_CONTROL}px;
        color: {INK_2};
        font-size: 13px;
        font-weight: 500;
        text-align: left;
    }}
    QPushButton#SettingsNavItem:hover {{
        background: {NAV_HOVER};
    }}
    QPushButton#SettingsNavItem[active="true"] {{
        background: {BLUE_SOFT};
        color: {BLUE};
        font-weight: 600;
    }}
    /* 新 UI：收起按钮不再是“白底灰描边的圆把手”，而是侧边栏内右下角的
       浅蓝胶囊按钮（.sidebar-toggle），常态就带蓝色语义，hover 只加深一档。 */
    QPushButton#SidebarToggle {{
        min-width: {SIDEBAR_TOGGLE_WIDTH}px;
        max-width: {SIDEBAR_TOGGLE_WIDTH}px;
        min-height: {SIDEBAR_TOGGLE_HEIGHT}px;
        max-height: {SIDEBAR_TOGGLE_HEIGHT}px;
        padding: 0px;
        background: {BLUE_SOFT};
        border: 1px solid {BLUE_BORDER};
        border-radius: {RADIUS_CONTROL}px;
        color: {BLUE};
    }}
    QPushButton#SidebarToggle:hover {{
        background: {BLUE_SOFT_STRONG};
        border-color: {BLUE_BORDER_HOVER};
        color: {BLUE};
    }}
    QPushButton#SidebarToggle:pressed {{
        background: {BLUE_SOFT_STRONG};
        border-color: {BLUE};
    }}

    /* ---------------- 输入控件 ---------------- */
    QLineEdit,
    QPlainTextEdit,
    QTextBrowser,
    QComboBox,
    QKeySequenceEdit {{
        background: {SURFACE};
        border: 1px solid {LINE};
        border-radius: {RADIUS_CONTROL}px;
        padding: 7px 10px;
        color: {INK};
        selection-background-color: {BLUE_SOFT};
        selection-color: {INK};
        font-size: 13px;
    }}
    QLineEdit:hover,
    QPlainTextEdit:hover,
    QComboBox:hover,
    QKeySequenceEdit:hover {{
        border-color: {LINE_STRONG};
    }}
    QLineEdit:focus,
    QPlainTextEdit:focus,
    QTextBrowser:focus,
    QComboBox:focus,
    QComboBox:on,
    QKeySequenceEdit:focus {{
        border-color: {BLUE};
    }}
    QLineEdit:disabled,
    QPlainTextEdit:disabled,
    QTextBrowser:disabled,
    QComboBox:disabled,
    QKeySequenceEdit:disabled {{
        background: {SURFACE_2};
        color: {INK_5};
    }}
    QLineEdit[readOnly="true"] {{
        background: {SURFACE_2};
    }}
    QComboBox {{
        min-height: 20px;
        padding-right: 32px;
    }}
    /* 可编辑下拉框的内嵌输入框：去掉套套叠叠的第二层边框与底色。 */
    QComboBox QLineEdit {{
        background: transparent;
        border: none;
        border-radius: 0px;
        padding: 0px;
        color: {INK};
        font-size: 13px;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 30px;
        border: none;
        background: transparent;
    }}
    QComboBox::down-arrow {{
        image: none;
        width: 0;
        height: 0;
    }}
    QComboBox QAbstractItemView {{
        background: {SURFACE};
        border: 1px solid {LINE};
        border-radius: {RADIUS_CONTROL}px;
        color: {INK};
        selection-background-color: {BLUE_SOFT};
        selection-color: {BLUE};
        outline: none;
        padding: 4px;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 26px;
        padding: 0px 8px;
        border: none;
        border-radius: {RADIUS_SM}px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background: {SURFACE_2};
        color: {INK};
    }}

    /* ---------------- 小组件 ---------------- */
    QWidget#SegmentedControl {{
        background: {SEG_BG};
        border: none;
        border-radius: {RADIUS_CONTROL}px;
    }}
    QPushButton#SegmentButton {{
        min-height: 20px;
        padding: 3px 12px;
        border: 1px solid transparent;
        border-radius: {RADIUS_SM}px;
        color: {INK_3};
        background: transparent;
        font-size: 12px;
        font-weight: 500;
    }}
    QPushButton#SegmentButton:hover {{
        color: {INK};
        background: transparent;
    }}
    QPushButton#SegmentButton:pressed {{
        background: transparent;
    }}
    QPushButton#SegmentButton[active="true"] {{
        color: {INK};
        background: {SURFACE};
        border-color: {LINE};
        font-weight: 600;
    }}
    QPushButton#SegmentButton:disabled {{
        background: transparent;
        color: {INK_5};
    }}
    QPushButton#SegmentButton[active="true"]:disabled {{
        background: {SURFACE};
        border-color: {LINE};
        color: {INK_4};
    }}

    QLabel#Pill {{
        padding: 3px 9px;
        border: none;
        border-radius: 9px;
        background: {SURFACE_2};
        color: {INK_2};
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#Pill[tone="blue"] {{
        background: {BLUE_SOFT};
        color: {BLUE};
    }}
    QLabel#Pill[tone="ok"] {{
        background: {OK_SOFT};
        color: {OK};
    }}
    QLabel#Pill[tone="warn"] {{
        background: {WARN_SOFT};
        color: {WARN};
    }}
    QLabel#Pill[tone="outline"] {{
        background: transparent;
        color: {INK_2};
        border: 1px solid {LINE};
    }}
    QLabel#Kbd {{
        padding: 2px 6px;
        background: {SURFACE};
        color: {INK_2};
        border: 1px solid {LINE_STRONG};
        border-radius: {RADIUS_SM}px;
        font-family: "Cascadia Code", "Consolas", monospace;
        font-size: 11px;
        font-weight: 600;
    }}

    QLabel#PreviewCanvas {{
        background: {BG_BASE};
        border: 1px dashed {LINE_STRONG};
        border-radius: 10px;
        color: {INK_4};
        font-size: 12px;
    }}
    QTextBrowser#ResultOutput {{
        background: {BG_BASE};
        border-color: {LINE_SOFT};
    }}
    QTextBrowser#ResultOutput:focus {{
        border-color: {LINE_STRONG};
    }}
    QLabel#Toast {{
        padding: 8px 16px;
        background: {TOAST_BG};
        color: {SURFACE};
        border: none;
        border-radius: 16px;
        font-size: 12px;
        font-weight: 600;
    }}

    /* 收起后的导航完全依赖 tooltip，因此它也需要跟设计稿一致。 */
    QToolTip {{
        background: {TOAST_BG};
        color: #fafafa;
        border: none;
        border-radius: {RADIUS_SM}px;
        padding: 5px 8px;
        font-size: 11px;
        font-weight: 500;
    }}

    /* ---------------- 滚动条 ---------------- */
    QScrollBar:vertical {{
        width: 6px;
        margin: 2px 2px 2px 0;
        background: transparent;
    }}
    QScrollBar::handle:vertical {{
        min-height: 24px;
        background: rgba(0, 0, 0, 46);
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(0, 0, 0, 72);
    }}
    QScrollBar::handle:vertical:pressed {{
        background: rgba(0, 0, 0, 96);
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        width: 0;
        height: 0;
        background: transparent;
    }}
    QScrollBar:horizontal {{
        height: 6px;
        margin: 0 2px 2px 2px;
        background: transparent;
    }}
    QScrollBar::handle:horizontal {{
        min-width: 24px;
        background: rgba(0, 0, 0, 46);
        border-radius: 3px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: rgba(0, 0, 0, 72);
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {{
        width: 0;
        height: 0;
        background: transparent;
    }}
    """


def apply_window_theme(widget: QWidget) -> None:
    """Apply the theme to one window without touching QApplication state."""
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    # 设计稿的字号全部是 px；基准字体也用 px 才能与 QSS 对得上，
    # 否则 pt/px 混用会让没被 QSS 命中的控件（菜单、下拉项）字号偏大。
    font.setPixelSize(BASE_FONT_PIXEL_SIZE)
    widget.setFont(font)
    widget.setStyleSheet(build_stylesheet())
