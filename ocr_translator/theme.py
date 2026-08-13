from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget


WINDOW_BG = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #fafafa)"
BG_BASE = "#fafafa"
SURFACE = "#ffffff"
SURFACE_2 = "#f4f4f5"
SIDEBAR_BG = "#fafafa"
NAV_HOVER = "rgba(0, 0, 0, 10)"
LINE = "#e4e4e7"
LINE_STRONG = "#d4d4d8"
LINE_SOFT = "#f4f4f5"
INK = "#09090b"
INK_2 = "#3f3f46"
INK_3 = "#71717a"
INK_4 = "#a1a1aa"
INK_5 = "#d4d4d8"
BLUE = "#2563eb"
BLUE_HOVER = "#1d4ed8"
BLUE_SOFT = "#eff4ff"
BLUE_RING = "rgba(37, 99, 235, 56)"
OK = "#16a34a"
OK_SOFT = "#ecfdf5"
WARN = "#d97706"
WARN_SOFT = "#fff7ed"
ERR = "#dc2626"
SEG_BG = "rgba(0, 0, 0, 10)"
TOGGLE_OFF = "rgba(0, 0, 0, 46)"
TOAST_BG = "#18181b"

# 新 UI 的尺寸令牌（与设计稿 index.css 中的数值一致）。
RADIUS_CARD = 14
RADIUS_PANEL = 12
RADIUS_CONTROL = 8
RADIUS_SM = 6
SIDEBAR_WIDTH = 188
SIDEBAR_COLLAPSED_WIDTH = 52
SIDEBAR_TOGGLE_SIZE = 26
CONTENT_MARGIN = 14
TOAST_BOTTOM_OFFSET = 28

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
    QPushButton:hover {{
        background: {NAV_HOVER};
    }}
    QPushButton:focus {{
        border: 1px solid {BLUE};
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
        background: #27272a;
        border-color: #27272a;
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
    QPushButton[variant="ghost"],
    QPushButton#SecondaryButton {{
        background: transparent;
        color: {INK_2};
        border-color: {LINE_STRONG};
    }}
    QPushButton[variant="ghost"]:hover,
    QPushButton#SecondaryButton:hover {{
        background: {NAV_HOVER};
    }}
    QPushButton[variant="soft"],
    QPushButton#SecondaryButton:checked {{
        background: {SURFACE_2};
        color: {INK_2};
        border-color: transparent;
    }}
    QPushButton[variant="danger"] {{
        background: transparent;
        color: {ERR};
        border-color: {LINE_STRONG};
    }}

    QPushButton#SidebarItem,
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
    QPushButton#SidebarItem:hover,
    QPushButton#SettingsNavItem:hover {{
        background: {NAV_HOVER};
    }}
    QPushButton#SidebarItem[active="true"],
    QPushButton#SettingsNavItem[active="true"] {{
        background: {BLUE_SOFT};
        color: {BLUE};
        font-weight: 600;
    }}
    QPushButton#SidebarItem[collapsed="true"] {{
        padding: 0px;
        text-align: center;
    }}
    QPushButton#SidebarToggle {{
        min-width: {SIDEBAR_TOGGLE_SIZE}px;
        max-width: {SIDEBAR_TOGGLE_SIZE}px;
        min-height: {SIDEBAR_TOGGLE_SIZE}px;
        max-height: {SIDEBAR_TOGGLE_SIZE}px;
        padding: 0px;
        background: {SURFACE};
        border: 1px solid {LINE_STRONG};
        border-radius: {SIDEBAR_TOGGLE_SIZE // 2}px;
        color: {INK_3};
    }}
    QPushButton#SidebarToggle:hover {{
        background: {BLUE_SOFT};
        border-color: {BLUE};
        color: {BLUE};
    }}

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
    QLineEdit:focus,
    QPlainTextEdit:focus,
    QTextBrowser:focus,
    QComboBox:focus,
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
    QPushButton#SegmentButton[active="true"] {{
        color: {INK};
        background: {SURFACE};
        border-color: {LINE};
        font-weight: 600;
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
    QLabel#Toast {{
        padding: 8px 16px;
        background: {TOAST_BG};
        color: {SURFACE};
        border: none;
        border-radius: 16px;
        font-size: 12px;
        font-weight: 600;
    }}

    QScrollBar:vertical {{
        width: 6px;
        margin: 0;
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
        margin: 0;
        background: transparent;
    }}
    QScrollBar::handle:horizontal {{
        min-width: 24px;
        background: rgba(0, 0, 0, 46);
        border-radius: 3px;
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
    font.setPointSize(10)
    widget.setFont(font)
    widget.setStyleSheet(build_stylesheet())
