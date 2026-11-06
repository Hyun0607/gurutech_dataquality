"""화면 색·글꼴·간격. 시안(대시보드 + 피그마 느낌): 흰 카드, 얇은 테두리, 연한 회색 바탕, 강조색 하나.

Windows가 어두운 모드여도 늘 밝은 화면으로 그린다 (apply). Qt 6.5부터 시스템 색을 따라가서,
어두운 바탕에 어두운 글자가 겹쳐 안 보이는 일이 생기기 때문이다.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

ACCENT = "#2563EB"
ACCENT_DARK = "#1D4ED8"
GROUND = "#F5F6F8"
SURFACE = "#FFFFFF"
BORDER = "#E4E7EC"
TEXT = "#101828"
MUTED = "#475467"
SUBTLE = "#F2F4F7"

# 상태 배지: (글자, 바탕). 밝기도 달라서 색만으로 구분하지 않아도 된다.
KINDS = {
    "success": ("#067647", "#ECFDF3"),
    "warn": ("#B54708", "#FFFAEB"),
    "error": ("#B42318", "#FEF3F2"),
    "neutral": ("#344054", "#F2F4F7"),
    "info": ("#1D4ED8", "#EFF4FF"),
}
ROW_TINT = {"error": QColor("#FEF3F2"), "warn": QColor("#FFFAEB"), "selected": QColor("#F5F8FF"),
            "blue": QColor("#EFF4FF"), "green": QColor("#ECFDF3")}   # 예방적 품질관리: 전환 예상 / 내년 후보

FONT_FAMILIES = ["Pretendard", "Malgun Gothic", "맑은 고딕", "Segoe UI"]
MONO = "Consolas"

QSS = f"""
QWidget {{ color: {TEXT}; font-size: 13px; }}
QDialog, QMessageBox, QFileDialog {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT}; background: transparent; }}
QDialog#settings {{ background: {GROUND}; }}
QComboBox QAbstractItemView, QMenu {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
                                      selection-background-color: #EFF4FF; selection-color: {TEXT}; }}
QRadioButton, QCheckBox {{ spacing: 8px; background: transparent; }}
QLabel {{ background: transparent; }}
QMainWindow, QWidget#content, QScrollArea, QScrollArea > QWidget > QWidget#page {{ background: {GROUND}; }}
QWidget#sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
QLabel#brand {{ font-size: 15px; font-weight: 700; }}
QLabel#brandSub, QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#navGroup {{ color: {MUTED}; font-size: 11px; font-weight: 600; padding: 14px 10px 4px 10px; }}
QPushButton#nav {{ text-align: left; padding: 0 10px; min-height: 38px; border: 0; border-radius: 8px;
                   color: #344054; font-weight: 500; background: transparent; }}
QPushButton#nav:hover:!checked {{ background: #F9FAFB; }}
QPushButton#nav:checked {{ background: #EFF4FF; color: {TEXT}; font-weight: 600; }}
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#card[clickable="true"]:hover {{ border: 1px solid #B2CCFF; }}
QFrame#statusBox {{ border: 1px solid {BORDER}; border-radius: 10px; background: {SURFACE}; }}
QLabel#cardTitle {{ font-weight: 600; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 700; }}
QLabel#bigNumber {{ font-size: 30px; font-weight: 700; }}
QLabel#bigUnit {{ font-size: 14px; color: {MUTED}; }}
QLabel#infoValue {{ font-size: 16px; font-weight: 600; }}
QLabel#chip {{ font-family: {MONO}; font-size: 11px; color: {MUTED}; background: {SUBTLE};
               border-radius: 6px; padding: 2px 6px; }}
QLabel#sectionTitle {{ font-size: 14px; font-weight: 600; }}
QPushButton#primary {{ background: {ACCENT}; color: #FFFFFF; border: 0; border-radius: 8px; padding: 0 16px;
                       min-height: 36px; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_DARK}; }}
QPushButton#primary:disabled {{ background: #98A2B3; }}
QPushButton#secondary {{ background: {SURFACE}; border: 1px solid #D0D5DD; border-radius: 8px; padding: 0 14px;
                         min-height: 34px; }}
QPushButton#secondary:hover {{ background: #F9FAFB; }}
QPushButton#link {{ border: 0; background: transparent; color: {ACCENT_DARK}; padding: 0 4px; }}
QPushButton#link:hover {{ color: #1E3A8A; text-decoration: underline; }}
QLineEdit, QComboBox, QSpinBox, QDateEdit {{ border: 1px solid #D0D5DD; border-radius: 8px; padding: 0 10px;
                                              min-height: 32px; background: {SURFACE}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QLabel#dropCover {{ background: rgba(239, 244, 255, 215); border: 3px dashed {ACCENT}; border-radius: 12px;
                    color: {ACCENT}; font-size: 22px; font-weight: 700; }}
QLineEdit[dropping="true"] {{ border: 2px dashed {ACCENT}; background: #EFF4FF; }}
QLineEdit:disabled {{ color: #98A2B3; background: #F9FAFB; }}
QPushButton#secondary:disabled {{ color: #98A2B3; background: #F9FAFB; }}
QTableView {{ background: {SURFACE}; border: 0; gridline-color: {SUBTLE}; selection-background-color: #EFF4FF;
              selection-color: {TEXT}; }}
QHeaderView::section {{ background: #F9FAFB; color: {MUTED}; font-size: 12px; font-weight: 600; border: 0;
                        border-bottom: 1px solid {BORDER}; padding: 8px 10px; }}
QTableCornerButton::section {{ background: #F9FAFB; border: 0; }}
QTabWidget::pane {{ border: 0; }}
QTabBar::tab {{ background: transparent; padding: 10px 14px; color: {MUTED}; border: 0;
                border-bottom: 2px solid transparent; font-weight: 500; }}
QTabBar::tab:selected {{ color: {TEXT}; font-weight: 600; border-bottom: 2px solid {ACCENT}; }}
QProgressBar {{ border: 0; background: {SUBTLE}; border-radius: 4px; min-height: 8px; max-height: 8px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QProgressBar#barWarn::chunk {{ background: #F79009; }}
QProgressBar#busy {{ min-height: 3px; max-height: 3px; border-radius: 0; }}
QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QToolTip {{ background: {TEXT}; color: #FFFFFF; border: 0; padding: 6px 8px; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 10px; margin-top: 14px; padding: 14px 12px 10px 12px;
             background: {SURFACE}; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
"""

_CHECK = (Path(__file__).resolve().parent / "assets" / "check.svg").as_posix()
_CHEVRON = (Path(__file__).resolve().parent / "assets" / "chevron.svg").as_posix()
_CHEVRON_RIGHT = (Path(__file__).resolve().parent / "assets" / "chevron_right.svg").as_posix()
_CHECK_BLUE = (Path(__file__).resolve().parent / "assets" / "check_blue.svg").as_posix()
_CALENDAR = (Path(__file__).resolve().parent / "assets" / "calendar.svg").as_posix()
QSS += f"""
QPushButton#target {{ text-align: left; background: {SURFACE}; border: 1px solid #D0D5DD; border-radius: 8px;
                      min-height: 34px; padding-left: 14px; padding-right: 32px; font-weight: 600; }}
QPushButton#target:hover {{ border: 1px solid {ACCENT}; }}
QPushButton#target::menu-indicator {{ image: url({_CHEVRON}); subcontrol-origin: padding;
                                      subcontrol-position: center right; right: 10px; width: 12px; height: 12px; }}
QMenu#targetMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
QMenu#targetMenu::item {{ padding: 8px 28px 8px 28px; border-radius: 6px; color: {TEXT}; }}
QMenu#targetMenu::item:selected {{ background: #EFF4FF; color: {TEXT}; }}
QMenu#targetMenu::indicator {{ width: 14px; height: 14px; left: 8px; }}
QMenu#targetMenu::indicator:checked {{ image: url({_CHECK_BLUE}); }}
QMenu#targetMenu::right-arrow {{ image: url({_CHEVRON_RIGHT}); width: 12px; height: 12px; right: 8px; }}
QFrame#portal {{ background: {SURFACE}; border: 1px solid #D0D5DD; border-right: 0; border-bottom: 0; }}
QLabel#portalHead, QLabel#portalSub {{ background: #F2F4F7; color: #344054; font-size: 12px; font-weight: 600;
                                       border-right: 1px solid #D0D5DD; border-bottom: 1px solid #D0D5DD; padding: 7px 4px; }}
QLabel#portalSub {{ background: #F9FAFB; font-weight: 500; padding: 5px 2px; }}
QLabel#portalName {{ background: {SURFACE}; border-right: 1px solid #D0D5DD; border-bottom: 1px solid #D0D5DD;
                     padding: 12px 14px; font-size: 13px; }}
QLabel#portalRatio {{ background: {SURFACE}; border-right: 1px solid #D0D5DD; border-bottom: 1px solid #D0D5DD;
                      font-size: 16px; font-weight: 700; color: {ACCENT_DARK}; }}
QPushButton#portalCell {{ background: {SURFACE}; border: 0; border-right: 1px solid #D0D5DD; border-bottom: 1px solid #D0D5DD;
                          min-height: 52px; font-size: 15px; font-weight: 600; color: #067647; }}
QPushButton#portalCell[status="N"] {{ color: #D92D20; font-weight: 800; background: #FEF3F2; }}
QPushButton#portalCell[status="-"] {{ color: #98A2B3; font-weight: 500; }}
QPushButton#portalCell:hover {{ background: #F5F8FF; }}
QPushButton#portalCell:checked {{ background: #DCE7FF; border: 2px solid {ACCENT}; }}
QScrollArea#portalScroll {{ background: transparent; }}
QLabel#instCell {{ background: {SURFACE}; border-right: 1px solid #D0D5DD; border-bottom: 1px solid #D0D5DD;
                   padding: 9px 12px; font-size: 13px; }}
QLabel#instCell[bad="true"] {{ color: #B42318; font-weight: 700; background: #FEF3F2; }}
QTextBrowser#criterionText {{ border: 0; background: {SURFACE}; font-size: 13px; }}
QDateEdit {{ padding-right: 30px; }}
QDateEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: 0; }}
QDateEdit::down-arrow {{ image: url({_CALENDAR}); width: 14px; height: 14px; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
QCalendarWidget QToolButton {{ color: {TEXT}; background: transparent; border: 0; padding: 4px 8px; font-weight: 600; }}
QCalendarWidget QToolButton:hover {{ background: #EFF4FF; border-radius: 6px; }}
QCalendarWidget QAbstractItemView {{ background: {SURFACE}; color: {TEXT}; selection-background-color: {ACCENT};
                                      selection-color: #FFFFFF; outline: 0; }}
QCalendarWidget QAbstractItemView:disabled {{ color: #98A2B3; }}
QComboBox {{ padding-right: 30px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: 0;
                        background: transparent; }}
QComboBox::down-arrow {{ image: url({_CHEVRON}); width: 12px; height: 12px; }}
QComboBox:disabled {{ color: #98A2B3; background: #F9FAFB; }}
QComboBox QAbstractItemView {{ padding: 4px; outline: 0; }}
QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 0 8px; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 9px; border: 1px solid #98A2B3; background: {SURFACE}; }}
QRadioButton::indicator:hover {{ border: 1px solid {ACCENT}; }}
QRadioButton::indicator:checked {{ border: 5px solid {ACCENT}; background: {SURFACE}; width: 8px; height: 8px; }}
QCheckBox::indicator, QTableView::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #98A2B3;
                                              background: {SURFACE}; }}
QCheckBox::indicator:hover, QTableView::indicator:hover {{ border: 1px solid {ACCENT}; }}
QCheckBox::indicator:checked, QTableView::indicator:checked {{ border: 1px solid {ACCENT}; background: {ACCENT};
                                                              image: url({_CHECK}); }}
"""

for kind, (fg, bg) in KINDS.items():
    QSS += (f'QLabel[kind="{kind}"] {{ color: {fg}; background: {bg}; border-radius: 10px; padding: 2px 8px;'
            f' font-size: 12px; font-weight: 600; }}\n')


WINDOWS_FONT_FILES = ["malgun.ttf", "malgunbd.ttf", "consola.ttf"]


def asset(name: str) -> str:
    return (Path(__file__).resolve().parent / "assets" / name).as_posix()


def style_calendar(calendar) -> None:
    """달력 위쪽 이전·다음 달 화살표를 다른 아이콘과 같은 모양으로."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QToolButton
    for name, icon in (("qt_calendar_prevmonth", "chevron_left.svg"), ("qt_calendar_nextmonth", "chevron_right.svg")):
        button = calendar.findChild(QToolButton, name)
        if button:
            button.setIcon(QIcon(asset(icon)))


def light_palette() -> QPalette:
    p = QPalette()
    colors = {
        QPalette.Window: GROUND, QPalette.WindowText: TEXT, QPalette.Base: SURFACE, QPalette.AlternateBase: "#F9FAFB",
        QPalette.Text: TEXT, QPalette.Button: SURFACE, QPalette.ButtonText: TEXT, QPalette.BrightText: "#FFFFFF",
        QPalette.Highlight: ACCENT, QPalette.HighlightedText: "#FFFFFF", QPalette.ToolTipBase: TEXT,
        QPalette.ToolTipText: "#FFFFFF", QPalette.PlaceholderText: "#667085", QPalette.Link: ACCENT_DARK,
        QPalette.Light: "#FFFFFF", QPalette.Midlight: "#F2F4F7", QPalette.Mid: "#D0D5DD", QPalette.Dark: "#98A2B3",
        QPalette.Shadow: "#667085",
    }
    for role, color in colors.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#98A2B3"))
    return p


def apply(app) -> None:
    """앱 전체에 밝은 테마를 입힌다 (Windows 어두운 모드 무시)."""
    app.setStyle("Fusion")
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)   # Qt 6.8+
    except AttributeError:
        pass
    app.setPalette(light_palette())
    app.setFont(app_font())
    app.setStyleSheet(QSS)


def app_font() -> QFont:
    """Pretendard(프로그램에 같이 넣은 글꼴, OFL) → 맑은 고딕 순. 한글 글꼴이 없으면 Windows 글꼴 파일을 직접 올린다."""
    for path in sorted((Path(__file__).resolve().parent / "assets" / "fonts").glob("*.otf")):
        QFontDatabase.addApplicationFont(str(path))
    available = set(QFontDatabase.families())
    if not any(f in available for f in FONT_FAMILIES[:3]):
        import os
        fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        for name in WINDOWS_FONT_FILES:
            path = os.path.join(fonts, name)
            if os.path.exists(path):
                QFontDatabase.addApplicationFont(path)
        available = set(QFontDatabase.families())
    family = next((f for f in FONT_FAMILIES if f in available), FONT_FAMILIES[-1])
    font = QFont(family, 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    font.setHintingPreference(QFont.PreferNoHinting)   # 힌팅을 켜면 Pretendard '스'의 가로획이 지워진다 (시스템 → 시ㅅ템)
    return font
