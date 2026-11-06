"""화면 설정: 실행 기본값·표준 사전·평가대상 DB 목록·연계 기본값을 Windows 사용자 설정(QSettings)에 기억한다.

표준 사전은 사전 파일(팀원 기본, 사용자 폴더의 std_dict.sqlite) 또는 MySQL(관리자 원본)에서 읽는다.
관리자는 MySQL에서 사전 파일을 만들어 공유 폴더에 두고, 팀원 프로그램은 켤 때 공유 폴더의 새 사전을 알려 준다.
기관·시스템은 위쪽 머리글에서 평가대상 DB 목록으로 고른다.
고급 설정(도메인 정책 등)은 config.toml이 있으면 그 값을 바탕으로 쓰고, 화면에서 고친 값이 그 위에 덮인다.
DB 비밀번호는 파일에 두지 않고 Windows 자격 증명 관리자에 저장한다.
"""
from collections import OrderedDict
from datetime import datetime
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

from PySide6.QtCore import QDate, QSettings, QStandardPaths, Qt
from PySide6.QtGui import QGuiApplication, QIntValidator
from PySide6.QtWidgets import (QButtonGroup, QCalendarWidget, QDateEdit, QDialog, QFileDialog, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .. import db
from . import theme
from ..config import DbSettings, Settings, load_settings
from ..paths import BUNDLED_DICT, DICT_NAME, user_dir

COMMON_FILES = ("공통표준용어.xlsx", "공통표준단어.xlsx", "공통표준도메인.xlsx")
OLD_DEFAULT_OUTPUT = Path.home() / "Documents" / "stdtool 산출물"


def desktop_dir() -> str:
    """바탕화면 폴더 (OneDrive로 옮겨진 바탕화면도 Windows가 알려 주는 실제 위치)."""
    path = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
    return path or str(Path.home() / "Desktop")


@dataclass
class AppConfig:
    org_name: str = ""
    db_name: str = ""               # 산출물 파일에 쓰는 DB명 (db.db_label)
    system_name: str = ""
    db_kor_name: str = ""
    db_eng_name: str = ""
    enact_date: str = ""
    output_dir: str = field(default_factory=lambda: desktop_dir())   # 매크로처럼 바탕화면
    meta: str = ""
    dict_source: str = "file"       # 표준 사전: file(사전 파일) / mysql
    dict_file: str = ""             # 비우면 사용자 폴더의 std_dict.sqlite
    dict_update_dir: str = ""       # 새 사전 파일을 찾을 공유 폴더
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_database: str = "std_dict"
    link_cycle: str = "실시간"
    link_user_org: str = ""
    link_start: str = "06-01"
    config_path: str = ""           # 고급 설정 config.toml (선택)
    # 아래는 화면에 없다: 테스트·개발에서만 매크로 파일로 돌릴 때 쓴다
    source: str = "db"
    macro_workbook: str = ""
    common_dir: str = ""

    @classmethod
    def load(cls) -> "AppConfig":
        store = QSettings("stdtool", "stdtool")
        cfg = cls()
        for f in fields(cls):
            value = store.value(f.name)
            if value is not None:
                setattr(cfg, f.name, int(value) if f.type is int or f.type == "int" else str(value))
        if store.value("dict_source") is None and db.saved_password(cfg.db_settings_mysql()):
            cfg.dict_source = "mysql"   # 사전 파일 기능 전에 MySQL을 쓰던 PC(관리자)는 그대로
        cfg.source = "db"   # 화면은 DB로만
        if not cfg.output_dir or Path(cfg.output_dir) == OLD_DEFAULT_OUTPUT:
            cfg.output_dir = desktop_dir()   # 예전 기본값(문서\stdtool 산출물)은 바탕화면으로
        if not cfg.config_path and Path("config.toml").exists():
            cfg.config_path = str(Path("config.toml").resolve())
        return cfg

    def save(self):
        store = QSettings("stdtool", "stdtool")
        for f in fields(self):
            store.setValue(f.name, getattr(self, f.name))
        store.sync()

    def db_settings_mysql(self) -> DbSettings:
        return DbSettings(use=self.source == "db", host=self.db_host, port=int(self.db_port), user=self.db_user,
                          database=self.db_database)

    def db_settings(self) -> DbSettings:
        settings = self.db_settings_mysql()
        if self.dict_source == "file":
            settings.file = str(self.dict_path())
        return settings

    def dict_path(self) -> Path:
        return Path(self.dict_file) if self.dict_file else user_dir() / DICT_NAME

    def dict_info(self) -> dict:
        return db.read_dict_info(self.dict_path()) if self.dict_source == "file" and self.dict_path().exists() else {}

    def ensure_dict(self) -> str:
        """사전 파일 방식인데 파일이 없거나, 프로그램에 같이 넣은 사전이 더 새것이면(새 버전 exe) 사용자 폴더로 복사.
        반환: 안내 문구 (없으면 '')."""
        if self.dict_source != "file":
            return ""
        if self.dict_path().exists():
            if self.dict_file or not BUNDLED_DICT.exists():   # 직접 고른 사전 파일은 건드리지 않는다
                return ""
            bundled = db.read_dict_info(BUNDLED_DICT)
            if bundled.get("created_at", "") <= self.dict_info().get("created_at", ""):
                return ""
            try:
                db.install_dict(BUNDLED_DICT, self.dict_path())
            except Exception:   # 바꾸지 못해도 쓰던 사전으로 계속
                return ""
            return f"프로그램에 들어 있는 새 표준 사전으로 바꿨습니다 ({db.dict_label(bundled)})"
        if not BUNDLED_DICT.exists():
            return "사전 파일이 없습니다 · 설정 → 표준 사전에서 사전 파일을 고르세요"
        db.install_dict(BUNDLED_DICT, self.dict_path())
        return ""

    def dict_text(self) -> tuple:
        """(제목, 설명) — 왼쪽 아래 상태 상자."""
        if self.dict_source == "mysql":
            return "표준 사전: MySQL", f"{self.db_user}@{self.db_host}:{self.db_port} · {self.db_database}"
        return "표준 사전: 사전 파일", db.dict_label(self.dict_info()) or "파일 없음 · 설정에서 고르세요"

    def choose(self, entry: dict, entries: list):
        """평가대상 목록의 한 행(기관·시스템·DB)을 고른다."""
        self.org_name, self.system_name = entry["org"], entry["system"]
        self.db_kor_name, self.db_eng_name = entry.get("db_kor") or "", entry.get("db_eng") or ""
        self.db_name = db.db_label(entry, entries)

    def missing(self) -> list:
        need = []
        if not self.org_name:
            need.append("기관")
        if not self.db_name:
            need.append("시스템")
        if self.source == "macro" and not self.macro_workbook:
            need.append("매크로 파일")
        return need

    def build(self) -> Settings:
        """화면 실행용 Settings. 화면에서는 늘 고도화 방식으로 돌린다."""
        path = Path(self.config_path) if self.config_path else None
        settings = load_settings(path) if path and path.exists() else Settings()
        settings.org_name, settings.db_name = self.org_name, self.db_name
        settings.system_name, settings.db_eng_name = self.system_name, self.db_eng_name
        settings.enact_date = int(self.enact_date) if self.enact_date.isdigit() else (self.enact_date or None)
        settings.output_dir = Path(self.output_dir)
        settings.meta = Path(self.meta) if self.meta else None
        settings.enhanced = True
        settings.db = self.db_settings()
        if self.source == "macro":
            settings.macro_workbook = Path(self.macro_workbook) if self.macro_workbook else None
            if self.common_dir:
                d = Path(self.common_dir)
                term, word, domain = (d / f for f in COMMON_FILES)
                settings.common_term = term if term.exists() else None
                settings.common_word = word if word.exists() else None
                settings.common_domain = domain if domain.exists() else None
        settings.link_cycle = self.link_cycle or settings.link_cycle
        settings.link_user_org = self.link_user_org
        settings.link_start = self.link_start or settings.link_start
        return settings


def group_by_org(entries: list) -> OrderedDict:
    """기관명 → 그 기관의 목록 행들 (목록 순서 유지)."""
    out = OrderedDict()
    for e in entries:
        out.setdefault(e["org"], []).append(e)
    return out


def match_meta(found: dict, entries: list) -> list:
    """메타 파일에서 읽은 기관·시스템 → 평가대상 목록의 행들. DB가 여럿이면 DB명으로 좁히고,
    목록에 없으면 파일 값으로 만든 행 하나."""
    def key(x):
        return "".join(str(x or "").split()).upper()
    rows = [e for e in entries if key(e["org"]) == key(found["org"]) and key(e["system"]) == key(found["system"])]
    if len(rows) > 1:
        rows = [e for e in rows if found["db_eng"] and key(e.get("db_eng")) == key(found["db_eng"])
                or found["db_kor"] and key(e.get("db_kor")) == key(found["db_kor"])] or rows
    return rows or [{"org": found["org"], "system": found["system"], "db_kor": "", "db_eng": found["db_eng"]}]


def eval_summary(entries: list) -> str:
    if not entries:
        return "아직 가져온 목록이 없습니다."
    return f"기관 {len(group_by_org(entries)):,}곳 · DB {len(entries):,}개"


def _path_row(edit: QLineEdit, pick) -> QWidget:
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(edit, 1)
    button = QPushButton("찾기")
    button.setObjectName("secondary")
    button.clicked.connect(pick)
    row.addWidget(button)
    return box


class _Section(QFrame):
    """설정 묶음: 흰 카드 안에 제목과 입력 칸 (QGroupBox 제목이 잘리는 문제를 피한다)."""

    def __init__(self, title: str, hint: str = ""):
        super().__init__()
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 14, 18, 16)
        self.lay.setSpacing(10)
        head = QLabel(title)
        head.setObjectName("sectionTitle")
        self.lay.addWidget(head)
        if hint:
            note = QLabel(hint)
            note.setObjectName("muted")
            note.setWordWrap(True)
            self.lay.addWidget(note)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.form.setHorizontalSpacing(14)
        self.form.setVerticalSpacing(10)
        self.lay.addLayout(self.form)
        self.lay.addStretch(1)

    def row(self, text: str, field):
        name = QLabel(text)
        name.setMinimumWidth(92)
        self.form.addRow(name, field)


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.eval_changed = False
        self.setObjectName("settings")
        self.setWindowTitle("설정")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(14)
        title = QLabel("설정")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        run = _Section("실행 기본값", "기관·시스템은 위쪽 머리글에서 고릅니다. 산출물은 이 폴더 아래 '기관_DB' 폴더에 만들어집니다.")
        self.enact = QDateEdit()
        self.enact.setCalendarPopup(True)          # 누르면 달력
        self.enact.setDisplayFormat("yyyy-MM-dd")
        self.enact.setMinimumDate(QDate(1990, 1, 1))
        self.enact.setMaximumDate(QDate.currentDate().addYears(1))
        self.enact.setSpecialValueText("날짜를 고르세요")   # 최소 날짜 = 아직 안 고름
        self.enact.setDate(_to_qdate(cfg.enact_date) or self.enact.minimumDate())
        self.enact.calendarWidget().setGridVisible(False)
        self.enact.calendarWidget().setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        theme.style_calendar(self.enact.calendarWidget())
        self.output = QLineEdit(cfg.output_dir)
        run.row("제정일자", self.enact)
        run.row("산출물 폴더", _path_row(self.output, lambda: self._pick_dir(self.output)))

        dictbox = _Section("표준 사전", "사전(매크로 코드표·공통표준·평가대상 목록)을 어디서 읽을지 고릅니다. "
                                      "팀원은 사전 파일, 관리자는 MySQL을 씁니다.")
        self.use_file = QRadioButton("사전 파일")
        self.use_mysql = QRadioButton("MySQL (관리자)")
        choice = QButtonGroup(self)
        for b in (self.use_file, self.use_mysql):
            choice.addButton(b)
        (self.use_mysql if cfg.dict_source == "mysql" else self.use_file).setChecked(True)
        dictbox.row("읽는 곳", _wrap(self.use_file, self.use_mysql))
        self.dict_status = QLabel("")
        self.dict_status.setWordWrap(True)
        self.dict_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        swap = QPushButton("다른 파일로")
        swap.setObjectName("secondary")
        swap.clicked.connect(self._swap_dict)
        dictbox.row("사전 파일", _wrap(self.dict_status, swap))
        self.update_dir = QLineEdit(cfg.dict_update_dir)
        self.update_dir.setPlaceholderText("팀 공유 폴더 (선택) — 켤 때 새 사전이 있는지 봅니다")
        check = QPushButton("지금 확인")
        check.setObjectName("secondary")
        check.clicked.connect(self._check_update)
        dictbox.row("공유 폴더", _wrap(_path_row(self.update_dir, lambda: self._pick_dir(self.update_dir)), check))
        self.file_widgets = [swap, self.update_dir, check]
        self._show_dict()

        dbbox = _Section("MySQL 접속 (관리자)", "사전 원본 DB입니다. 비밀번호는 Windows 자격 증명 관리자에 저장됩니다. "
                                            "'사전 파일 만들기'로 팀원에게 나눠 줄 사전 파일을 만듭니다.")
        self.host = QLineEdit(cfg.db_host)
        self.port = QLineEdit(str(cfg.db_port))
        self.port.setValidator(QIntValidator(1, 65535, self))
        self.user = QLineEdit(cfg.db_user)
        self.database = QLineEdit(cfg.db_database)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        saved = db.saved_password(cfg.db_settings())
        self.password.setPlaceholderText("저장됨 (바꿀 때만 입력)" if saved else "입력하면 저장")
        dbbox.row("호스트", self.host)
        dbbox.row("포트", self.port)
        dbbox.row("계정", self.user)
        dbbox.row("데이터베이스", self.database)
        test = QPushButton("연결 테스트")
        test.setObjectName("secondary")
        test.clicked.connect(self._test)
        dbbox.row("비밀번호", _wrap(self.password, test))
        export = QPushButton("사전 파일 만들기")
        export.setObjectName("secondary")
        export.clicked.connect(self._export_dict)
        dbbox.row("배포", _wrap(export, QLabel("")))
        self.mysql_widgets = [self.host, self.port, self.user, self.database, self.password, test, export]

        evalbox = _Section("평가대상 DB 목록", "기관명·순번·정보시스템명·한글 DB명·영문 DB명 엑셀을 DB(eval_db)에 넣습니다. "
                                         "다시 가져오면 내용을 통째로 바꿉니다.")
        self.eval_status = QLabel("")
        self.eval_status.setWordWrap(True)
        load = QPushButton("목록 파일 가져오기")
        load.setObjectName("secondary")
        load.clicked.connect(self._import_eval)
        evalbox.row("현재", _wrap(self.eval_status, load))
        self.use_file.toggled.connect(self._sync_source)
        self._sync_source()

        link = _Section("연계 기본값")
        self.cycle = QLineEdit(cfg.link_cycle)
        self.user_org = QLineEdit(cfg.link_user_org)
        self.user_org.setPlaceholderText("비우면 기관명")
        self.start = QLineEdit(cfg.link_start)
        self.start.setPlaceholderText("MM-DD (예: 06-01)")
        link.row("주기", self.cycle)
        link.row("활용기관", self.user_org)
        link.row("점검 일시 시작", self.start)

        grid = QWidget()
        cols = QGridLayout(grid)
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setHorizontalSpacing(16)
        cols.setVerticalSpacing(16)
        cols.addWidget(run, 0, 0)
        cols.addWidget(dictbox, 0, 1)
        cols.addWidget(evalbox, 1, 0)
        cols.addWidget(dbbox, 1, 1, 2, 1)
        cols.addWidget(link, 2, 0)
        cols.setColumnStretch(0, 1)
        cols.setColumnStretch(1, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.setWidget(grid)
        outer.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("취소")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("저장")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        outer.addLayout(buttons)
        self._fit(grid)

    def _fit(self, grid: QWidget):
        """내용 크기에 맞추되 화면을 넘지 않게 (넘으면 스크롤)."""
        want = grid.sizeHint()
        screen = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        width = min(max(want.width() + 60, 960), screen.width() - 40)
        height = min(want.height() + 150, screen.height() - 60)
        self.resize(width, height)

    def _pick_dir(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "폴더 선택", edit.text())
        if path:
            edit.setText(path)

    def _apply(self):
        c = self.cfg
        chosen = self.enact.date()
        c.enact_date = "" if chosen == self.enact.minimumDate() else chosen.toString("yyyyMMdd")   # 저장은 YYYYMMDD
        c.output_dir = self.output.text().strip()
        c.dict_source = "file" if self.use_file.isChecked() else "mysql"
        c.dict_update_dir = self.update_dir.text().strip()
        c.db_host, c.db_port = self.host.text().strip(), int(self.port.text() or 3306)
        c.db_user, c.db_database = self.user.text().strip(), self.database.text().strip()
        c.link_cycle, c.link_user_org = self.cycle.text().strip(), self.user_org.text().strip()
        c.link_start = self.start.text().strip()
        if self.password.text():
            db.save_password(c.db_settings_mysql(), self.password.text())
            self.password.clear()

    def _sync_source(self, *_):
        on_file = self.use_file.isChecked()
        for w in self.file_widgets:
            w.setEnabled(on_file)
        for w in self.mysql_widgets:
            w.setEnabled(not on_file)
        self._refresh_eval()

    def _db_settings(self) -> DbSettings:
        """저장 전에도 고른 사전(파일·MySQL)으로 읽는다."""
        return replace(self.cfg, dict_source="file" if self.use_file.isChecked() else "mysql").db_settings()

    def _show_dict(self):
        path = self.cfg.dict_path()
        info = db.read_dict_info(path) if path.exists() else {}
        who = f" · 만든 사람 {info['created_by']}" if info.get("created_by") else ""
        self.dict_status.setText(f"{db.dict_label(info)}{who}\n{path}" if info else f"없음\n{path}")

    def _swap_dict(self):
        path, _ = QFileDialog.getOpenFileName(self, "사전 파일", self.update_dir.text() or str(Path.home()),
                                              "사전 파일 (*.sqlite)")
        if path:
            self._install(Path(path))

    def _install(self, source: Path) -> bool:
        try:
            info = db.install_dict(source, self.cfg.dict_path())
        except Exception as e:
            QMessageBox.warning(self, "사전 파일", f"바꾸지 못했습니다.\n{e}")
            return False
        self.eval_changed = True
        self._show_dict()
        self._refresh_eval()
        QMessageBox.information(self, "사전 파일", f"사전을 바꿨습니다: {db.dict_label(info)}")
        return True

    def _check_update(self):
        folder = self.update_dir.text().strip()
        current = db.read_dict_info(self.cfg.dict_path()) if self.cfg.dict_path().exists() else {}
        found = db.newer_dict(folder, current)
        if not found:
            QMessageBox.information(self, "사전 파일", "지금 사전이 최신입니다." if folder else "공유 폴더를 먼저 고르세요.")
            return
        path, info = found
        answer = QMessageBox.question(self, "사전 파일", f"새 사전이 있습니다: {db.dict_label(info)}\n{path.name}\n\n받을까요?")
        if answer == QMessageBox.Yes:
            self._install(path)

    def _export_dict(self):
        self._apply()
        start = Path(self.update_dir.text().strip() or Path.home()) / f"std_dict_{datetime.now():%Y%m%d}.sqlite"
        path, _ = QFileDialog.getSaveFileName(self, "사전 파일 만들기", str(start), "사전 파일 (*.sqlite)")
        if not path:
            return
        c = self.cfg
        try:
            with db.connect(c.db_settings_mysql()) as conn:
                info = db.export_file(conn, Path(path), f"MySQL {c.db_host}:{c.db_port}/{c.db_database}")
        except Exception as e:
            QMessageBox.warning(self, "사전 파일 만들기", f"만들지 못했습니다.\n{e}")
            return
        QMessageBox.information(self, "사전 파일 만들기", f"만들었습니다: {db.dict_label(info)}\n{path}\n\n"
                                "공유 폴더에 두면 팀원 프로그램이 켤 때 알려 줍니다.")

    def _refresh_eval(self):
        try:
            with db.connect(self._db_settings()) as conn:
                self.eval_status.setText(eval_summary(db.load_eval_list(conn)))
        except Exception:   # 접속 정보가 아직 없으면 안내만
            self.eval_status.setText("표준 사전에 연결하면 표시됩니다.")

    def _import_eval(self):
        self._apply()
        path, _ = QFileDialog.getOpenFileName(self, "평가대상 DB 목록", str(Path.home()), "엑셀 (*.xlsx)")
        if not path:
            return
        try:
            with db.connect(self.cfg.db_settings()) as conn:
                n = db.import_eval_list(conn, Path(path))
                entries = db.load_eval_list(conn)
        except Exception as e:
            QMessageBox.warning(self, "평가대상 DB 목록", f"가져오지 못했습니다.\n{e}")
            return
        self.eval_changed = True
        self.eval_status.setText(eval_summary(entries))
        QMessageBox.information(self, "평가대상 DB 목록", f"{n:,}행을 가져왔습니다. ({eval_summary(entries)})")

    def _test(self):
        self._apply()
        try:
            with db.connect(self.cfg.db_settings_mysql()) as conn:
                counts = db.status(conn)
            QMessageBox.information(self, "연결 테스트", "연결되었습니다.\n" +
                                    "\n".join(f"{t}: {n:,}행" for t, n in counts.items()))
            self._refresh_eval()
        except Exception as e:   # 접속·권한·테이블 없음 모두 그대로 보여 준다
            QMessageBox.warning(self, "연결 테스트", f"연결하지 못했습니다.\n{e}")

    def _save(self):
        self._apply()
        if self.cfg.link_start and not _valid_md(self.cfg.link_start):
            QMessageBox.warning(self, "설정", "점검 일시 시작은 MM-DD 형식으로 입력하세요 (예: 06-01).")
            return
        self.cfg.save()
        self.accept()


def _to_qdate(text: str):
    """'20170715' → QDate. 형식이 맞지 않으면 None."""
    d = QDate.fromString(str(text or "").strip(), "yyyyMMdd")
    return d if d.isValid() else None


def _wrap(*widgets) -> QWidget:
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        row.addWidget(w, 1 if isinstance(w, (QLineEdit, QLabel)) else 0)
    return box


def _valid_md(text: str) -> bool:
    parts = text.split("-")
    return len(parts) == 2 and all(p.isdigit() for p in parts) and 1 <= int(parts[0]) <= 12 and 1 <= int(parts[1]) <= 31
