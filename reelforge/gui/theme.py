"""Light, Apple-inspired look: system-blue accent, white rounded cards on a soft grey canvas,
generous spacing, one obvious primary action."""

from __future__ import annotations

from PyQt5.QtGui import QFont, QFontDatabase

BLUE = "#0071E3"
BLUE_HOVER = "#0077ED"
BLUE_PRESSED = "#0062C4"
TEXT = "#1D1D1F"
TEXT_2 = "#6E6E73"
TEXT_3 = "#AEAEB2"
CANVAS = "#F5F5F7"
SIDEBAR = "#ECECEF"
CARD = "#FFFFFF"
HAIRLINE = "#E3E3E8"
GREEN = "#34C759"
ORANGE = "#FF9F0A"
RED = "#FF3B30"


def ui_font(size: float = 10.5, weight: int = QFont.Normal) -> QFont:
    families = set(QFontDatabase().families())
    for name in ("Inter", "Adwaita Sans", "Cantarell", "Lato", "DejaVu Sans"):
        if name in families:
            f = QFont(name)
            break
    else:
        f = QFont()
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


STYLESHEET = f"""
QWidget {{ color: {TEXT}; }}
QMainWindow, #Canvas {{ background: {CANVAS}; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 4px 8px; border-radius: 6px; }}

#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {HAIRLINE}; }}
#SidebarTitle {{ color: {TEXT}; font-weight: 600; font-size: 15px; }}
#ReelList {{ background: transparent; border: none; outline: 0; }}
#ReelList::item {{ border-radius: 10px; margin: 1px 6px; padding: 0px; }}
#ReelList::item:selected {{ background: #DCDCE1; }}
#ReelList::item:hover:!selected {{ background: #E4E4E8; }}
#RowTitle {{ font-size: 13px; font-weight: 600; color: {TEXT}; background: transparent; }}
#RowSub {{ font-size: 11px; color: {TEXT_2}; background: transparent; }}

#Card {{ background: {CARD}; border: 1px solid {HAIRLINE}; border-radius: 14px; }}
#Title {{ font-size: 24px; font-weight: 600; color: {TEXT}; }}
#Subtitle {{ font-size: 13px; color: {TEXT_2}; }}
#NextHeading {{ font-size: 17px; font-weight: 600; color: {TEXT}; }}
#NextBody {{ font-size: 13px; color: {TEXT_2}; }}
#Muted {{ font-size: 12px; color: {TEXT_2}; }}
#EmptyTitle {{ font-size: 22px; font-weight: 600; color: {TEXT}; }}

QPushButton {{
    background: {CARD}; color: {TEXT}; border: 1px solid {HAIRLINE};
    border-radius: 8px; padding: 6px 14px; font-size: 13px;
}}
QPushButton:hover {{ background: #F7F7F9; }}
QPushButton:pressed {{ background: #EDEDF0; }}
QPushButton:disabled {{ color: {TEXT_3}; background: #F7F7F9; }}
QPushButton#Primary {{
    background: {BLUE}; color: white; border: none; border-radius: 18px;
    padding: 9px 22px; font-size: 14px; font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {BLUE_HOVER}; }}
QPushButton#Primary:pressed {{ background: {BLUE_PRESSED}; }}
QPushButton#Primary:disabled {{ background: #9CC4F2; color: white; }}
QPushButton#Link {{ background: transparent; border: none; color: {BLUE}; padding: 6px 8px; font-size: 13px; }}
QPushButton#Link:hover {{ color: {BLUE_HOVER}; text-decoration: underline; }}
QPushButton#Link:disabled {{ color: {TEXT_3}; }}
QPushButton#Danger {{ background: transparent; border: none; color: {RED}; padding: 6px 8px; font-size: 13px; }}
QPushButton#Round {{
    background: {CARD}; border: 1px solid {HAIRLINE}; border-radius: 14px;
    min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; padding: 0; font-size: 18px; color: {BLUE};
}}
QPushButton#Round:hover {{ background: #F2F2F5; }}
QPushButton#Record {{ background: {RED}; color: white; border: 4px solid #FFD7D4; border-radius: 36px; font-size: 13px; font-weight: 600; }}
QPushButton#Record:checked {{ background: #C7271E; }}

#Segmented {{ background: #EDEDF0; border-radius: 9px; }}
#Segmented QPushButton {{
    background: transparent; border: none; border-radius: 7px; padding: 5px 16px;
    font-size: 12px; color: {TEXT}; margin: 2px;
}}
#Segmented QPushButton:checked {{ background: {CARD}; font-weight: 600; border: 1px solid {HAIRLINE}; }}

QPlainTextEdit, QTextBrowser, QLineEdit {{
    background: {CARD}; border: 1px solid {HAIRLINE}; border-radius: 10px; padding: 8px;
    selection-background-color: #B3D7FF; selection-color: {TEXT}; font-size: 13px;
}}
QLineEdit {{ padding: 6px 10px; }}
QLineEdit:focus {{ border: 2px solid #8AB8F5; }}
#Script {{ border: none; background: transparent; font-size: 14px; }}
#Log {{ font-family: monospace; font-size: 11px; color: {TEXT_2}; background: #FBFBFD; }}

QProgressBar {{ background: #E5E5EA; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {BLUE}; border-radius: 3px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C7C7CC; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ height: 0; }}

#Option {{ background: {CARD}; border: 1px solid {HAIRLINE}; border-radius: 12px; }}
#Option[selected="true"] {{ border: 2px solid {BLUE}; background: #F2F7FE; }}
#OptionTitle {{ font-size: 13px; font-weight: 600; background: transparent; }}
#OptionBody {{ font-size: 12px; color: {TEXT_2}; background: transparent; }}
QCheckBox {{ font-size: 13px; spacing: 8px; }}
QDialog {{ background: {CANVAS}; }}
QMessageBox {{ background: {CANVAS}; }}
"""
