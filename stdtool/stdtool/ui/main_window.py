"""메인 창: 왼쪽 메뉴(요약 / 예방적 품질관리 / 표준 / 구조 / 연계), 위쪽 메타 파일·실행, 가운데 지표 화면."""
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QThread, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (QButtonGroup, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QMainWindow,
                               QMenu, QMessageBox, QProgressBar, QPushButton, QScrollArea, QStackedWidget, QStatusBar,
                               QVBoxLayout, QApplication, QLabel, QWidget)

from .. import __version__, db, history
from . import theme
from .pages import (ApplyPage, CurrencyPage, DefinePage, DictPage, LinkPage, LinkStatusPage, StructurePage,
                    SummaryPage)
from .preventive_pages import CheckPage, TargetsPage
from .record_pages import HistoryPage
from .run_panel import RunPanel
from ..workbook.reader import read_meta_target
from .settings import AppConfig, SettingsDialog, group_by_org, match_meta
from .widgets import label

# (지표, 지표 번호, [(화면 키, 세부지표, 세부지표 번호)]) — 세부 안내서 2026 ①-3~①-5, ②-1
MENU = [
    ("", "", [("summary", "요약", ""), ("history", "회차 기록", "")]),
    ("예방적 품질관리", "2-1-2", [("pqc_targets", "대상 사업", ""), ("pqc_order", "발주단계 점검", ""),
                                 ("pqc_done", "완료단계 점검", "")]),
    ("표준", "2-1-3", [("define", "표준 정의", "2-1-3-1"), ("apply", "표준 적용률", "2-1-3-2"), ("dict", "사전 관리", "")]),
    ("구조", "2-1-4", [("structure", "구조 정의", "2-1-4-1"), ("currency", "구조 현행화", "2-1-4-2")]),
    ("연계", "2-1-5", [("link", "관리 정보 정의", "2-1-5-1"), ("link_status", "송·수신 내역", "2-1-5-2")]),
]
PAD = "   "
PQC_PAGES = ("pqc_targets", "pqc_order", "pqc_done")
TITLES = {"summary": "요약", "history": "회차 기록",
          "pqc_targets": "예방적 품질관리 대상 사업", "pqc_order": "예방적 품질관리 발주단계 점검 (RFP)",
          "pqc_done": "예방적 품질관리 완료단계 점검",
          "define": "표준 정의", "apply": "표준 적용률", "dict": "사전 관리",
          "structure": "데이터 구조 정의", "currency": "데이터 구조 현행화",
          "link": "연계데이터 관리 정보 정의", "link_status": "연계데이터 송·수신 내역 관리"}


class NavButton(QPushButton):
    """왼쪽 메뉴 버튼: 이름은 왼쪽, 지표 번호는 오른쪽."""

    def __init__(self, name: str, code: str = ""):
        super().__init__()
        self.setObjectName("nav")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(f"{name} {code}".strip())
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 10, 0)
        self.name = label(name)
        self.code = label(code, "muted")
        for w in (self.name, self.code):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            w.setStyleSheet("background: transparent;")
        self.code.setStyleSheet(f"background: transparent; font-family: {theme.MONO}; font-size: 11px;")
        row.addWidget(self.name)
        row.addStretch(1)
        row.addWidget(self.code)
        self.toggled.connect(self._mark)

    def _mark(self, on: bool):
        font = self.name.font()
        font.setBold(on)
        self.name.setFont(font)


class RunWorker(QObject):
    """뒤에서 service.execute 실행 (화면이 멈추지 않게)."""
    progress = Signal(str)
    step = Signal(str, str)
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def run(self):
        from ..service import RunError, execute
        try:
            outcome = execute(self.settings, self.progress.emit, step=self.step.emit)
        except (RunError, db.DbError) as e:
            self.failed.emit(str(e))
            return
        except PermissionError as e:
            self.failed.emit(f"파일을 쓸 수 없습니다. 산출물을 엑셀에서 열어 두었다면 닫고 다시 실행하세요.\n{e}")
            return
        except Exception as e:   # 예상 못 한 오류도 창을 닫지 않고 알린다
            self.failed.emit(f"{type(e).__name__}: {e}")
            return
        self.finished.emit(outcome, self.settings)


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig | None = None):
        super().__init__()
        self.cfg = cfg or AppConfig.load()
        self.outcome = None
        self._thread = None
        self.setWindowTitle("stdtool — 표준화 점검 프로그램")
        self._fit_to_screen()
        self.setAcceptDrops(True)   # 메타 파일을 창 아무 곳에나 끌어다 놓기 (eventFilter)

        root = QWidget()
        root.setObjectName("content")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._sidebar())

        main = QWidget()
        col = QVBoxLayout(main)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._header())
        self.busy = QProgressBar()
        self.busy.setObjectName("busy")
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setVisible(False)
        col.addWidget(self.busy)
        from ..service import STEPS
        self.run_panel = RunPanel(STEPS)
        self.run_panel.setVisible(False)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(32, 0, 32, 8)
        hl.addWidget(self.run_panel)
        col.addWidget(holder)

        self.stack = QStackedWidget()
        self.pages = {"summary": SummaryPage(), "define": DefinePage(), "apply": ApplyPage(), "dict": DictPage(),
                      "structure": StructurePage(), "currency": CurrencyPage(), "link": LinkPage(),
                      "link_status": LinkStatusPage(),
                      "history": HistoryPage(), "pqc_targets": TargetsPage()}
        self.pages["pqc_order"] = CheckPage("발주", self.pages["pqc_targets"])
        self.pages["pqc_done"] = CheckPage("완료", self.pages["pqc_targets"])
        for key, page in self.pages.items():
            self.stack.addWidget(page)
            page.navigate.connect(self.go)
        for key in ("structure", "link", "link_status"):
            self.pages[key].files_written.connect(self._files_written)
        for key in PQC_PAGES:
            self.pages[key].output_dir = self.cfg.output_dir
        col.addWidget(self.stack, 1)
        outer.addWidget(main, 1)
        self.setCentralWidget(root)
        self.drop_cover = QLabel("여기에 놓으면 메타 파일로 씁니다", self)
        self.drop_cover.setObjectName("dropCover")
        self.drop_cover.setAlignment(Qt.AlignCenter)
        self.drop_cover.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.drop_cover.setVisible(False)
        QApplication.instance().installEventFilter(self)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.panel_button = QPushButton("진행 상황")
        self.panel_button.setObjectName("link")
        self.panel_button.setEnabled(False)
        self.panel_button.clicked.connect(lambda: self.run_panel.setVisible(not self.run_panel.isVisible()))
        self.status.addPermanentWidget(self.panel_button)
        self.entries, self.groups, self._actions = [], {}, []
        self._detected = ""   # 기관·시스템을 읽어 둔 메타 파일
        self.go("summary")
        problem = self.cfg.ensure_dict()   # 처음 켜면 같이 넣은 사전을 사용자 폴더로
        if self.cfg.source == "db":
            self.load_eval_list()
        if problem:
            self.status.showMessage(problem)
        self._refresh_target()
        self._meta_edited()   # 지난번 메타 파일의 기관·시스템으로 맞춘다

    def check_dict_update(self):
        """공유 폴더에 더 새 사전 파일이 있으면 받을지 묻는다 (창을 띄운 뒤 한 번)."""
        if self.cfg.dict_source != "file" or not self.cfg.dict_update_dir:
            return
        found = db.newer_dict(self.cfg.dict_update_dir, self.cfg.dict_info())
        if not found:
            return
        path, info = found
        if QMessageBox.question(self, "새 사전", f"공유 폴더에 새 사전이 있습니다: {db.dict_label(info)}\n"
                                f"{path.name}\n\n받을까요?") != QMessageBox.Yes:
            return
        try:
            db.install_dict(path, self.cfg.dict_path())
        except Exception as e:
            QMessageBox.warning(self, "새 사전", f"받지 못했습니다.\n{e}")
            return
        self.load_eval_list()
        self._refresh_target()
        self.status.showMessage(f"사전을 바꿨습니다: {db.dict_label(info)}")

    # --- 레이아웃 -----------------------------------------------------------

    def _fit_to_screen(self):
        """1440×920을 기본으로, 화면(배율 적용 후)이 더 작으면 화면 안에 들어오게."""
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        width, height = 1440, 920
        if area:
            width, height = min(width, area.width() - 40), min(height, area.height() - 40)
        self.resize(width, height)
        self.setMinimumSize(min(1100, width), min(640, height))

    def _sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(244)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 20, 14, 16)
        lay.setSpacing(2)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand.addWidget(label("stdtool", "brand"))
        brand.addWidget(label(f"표준화 점검 프로그램 · v{__version__}", "brandSub"))
        lay.addLayout(brand)
        lay.addSpacing(14)
        # 메뉴 목록은 스크롤 영역 안: 창 높이가 줄어도 버튼이 찌그러지지 않고 아래 사전·설정 상자가 잘리지 않는다
        menu = QWidget()
        menu.setObjectName("sideMenu")
        items_lay = QVBoxLayout(menu)
        items_lay.setContentsMargins(0, 0, 0, 0)
        items_lay.setSpacing(2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea, QWidget#sideMenu {{ background: {theme.SURFACE}; border: none; }}")
        scroll.setWidget(menu)
        self.nav = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for title, code, items in MENU:
            if title:
                head = QHBoxLayout()
                head.setContentsMargins(0, 0, 10, 0)
                head.addWidget(label(title, "navGroup"))
                head.addStretch(1)
                chip = label(code, "navGroup")
                chip.setStyleSheet(f"font-family: {theme.MONO};")
                head.addWidget(chip, 0, Qt.AlignBottom)
                items_lay.addLayout(head)
            for key, name, code in items:
                button = NavButton(name, code)
                button.clicked.connect(lambda _=False, k=key: self.go(k))
                group.addButton(button)
                items_lay.addWidget(button)
                self.nav[key] = button
        items_lay.addStretch(1)
        lay.addWidget(scroll, 1)
        lay.addSpacing(8)
        box = QFrame()
        box.setObjectName("statusBox")
        b = QVBoxLayout(box)
        b.setContentsMargins(12, 10, 12, 10)
        b.setSpacing(2)
        self.source_title = label("", "cardTitle")
        self.source_detail = label("", "muted", wrap=True)
        b.addWidget(self.source_title)
        b.addWidget(self.source_detail)
        settings = QPushButton("설정")
        settings.setObjectName("secondary")
        settings.clicked.connect(self.open_settings)
        b.addSpacing(6)
        b.addWidget(settings)
        lay.addWidget(box)
        return side

    def _header(self) -> QWidget:
        head = QWidget()
        lay = QHBoxLayout(head)
        lay.setContentsMargins(32, 18, 32, 14)
        lay.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(2)
        self.project = label("", "muted")
        self.title = label("요약", "pageTitle")
        left.addWidget(self.project)
        left.addWidget(self.title)
        lay.addLayout(left, 1)

        self.meta_box = QWidget()   # 메타 파일·실행·기관·시스템 (예방적 품질관리 화면에서는 숨긴다)
        right = QGridLayout(self.meta_box)
        right.setContentsMargins(0, 0, 0, 0)
        right.setHorizontalSpacing(8)
        right.setVerticalSpacing(8)
        self.target = QPushButton()
        self.target.setObjectName("target")
        self.target.setMinimumWidth(360)
        self.target.setCursor(Qt.PointingHandCursor)
        self.target.setAccessibleName("기관·시스템 선택")
        self.target_menu = QMenu(self.target)
        self.target_menu.setObjectName("targetMenu")
        self.target.setMenu(self.target_menu)
        right.addWidget(label("메타 파일", "muted"), 0, 0)
        self.meta = QLineEdit(self.cfg.meta)
        self.meta.setPlaceholderText("메타데이터 표준 관리항목 엑셀 · 창에 끌어다 놓아도 됩니다")
        self.meta.setAcceptDrops(False)   # 끌어다 놓은 파일은 창(dropEvent)이 받는다
        self.meta.setAccessibleName("메타 파일 경로")
        self.meta.editingFinished.connect(self._meta_edited)
        right.addWidget(self.meta, 0, 1)
        pick = QPushButton("찾기")
        pick.setObjectName("secondary")
        pick.clicked.connect(self._pick_meta)
        right.addWidget(pick, 0, 2)
        self.run_button = QPushButton("▶  실행")
        self.run_button.setObjectName("primary")
        self.run_button.setCursor(Qt.PointingHandCursor)
        self.run_button.clicked.connect(self.run)
        right.addWidget(self.run_button, 0, 3)
        right.addWidget(label("기관·시스템", "muted"), 1, 0)
        right.addWidget(self.target, 1, 1, 1, 3)
        self.target.setToolTip("메타 파일을 고르면 파일의 기관명·정보시스템명으로 정해집니다. 바꾸려면 눌러서 고르세요.")
        right.setColumnStretch(1, 1)
        lay.addWidget(self.meta_box)
        return head

    # --- 기관·시스템 ---------------------------------------------------------

    def load_eval_list(self):
        """DB의 평가대상 목록으로 기관·시스템 메뉴를 채운다."""
        try:
            with db.connect(self.cfg.db_settings()) as conn:
                entries = db.load_eval_list(conn)
            problem = "" if entries else "설정 → 평가대상 DB 목록에서 목록 파일을 가져오세요"
        except Exception as e:   # 사전 접속 실패: 메뉴를 비우고 이유를 보여 준다
            entries, problem = [], f"표준 사전을 읽지 못했습니다 · 설정에서 확인하세요 ({e})"
        self.fill_eval(entries, problem)

    def fill_eval(self, entries: list, problem: str = ""):
        """드롭다운: 기관에 마우스를 올리면 그 기관의 시스템 목록이 옆에 펼쳐지고, 시스템을 누르면 둘 다 정해진다."""
        self.entries = entries
        self.groups = group_by_org(self.entries)
        self.pages["pqc_targets"].set_orgs(entries)   # 예방적 품질관리의 관리 기관
        self.target_menu.clear()
        self._actions = []
        self.target.setEnabled(bool(self.groups))
        for org, rows in self.groups.items():
            sub = self.target_menu.addMenu(f"{org}   ({len(rows)})")
            sub.setObjectName("targetMenu")
            for e in rows:
                text = e["system"] if not e.get("db_kor") else f"{e['system']}  ·  {e['db_kor']}"
                action = sub.addAction(text)
                action.setCheckable(True)
                action.setChecked(self._is_current(e))
                action.setToolTip(f"영문 DB명 {e.get('db_eng') or '-'} · 순번 {e.get('seq') or '-'}")
                action.triggered.connect(lambda _=False, entry=e: self.choose(entry))
                self._actions.append((action, e))
            sub.setToolTipsVisible(True)
        if problem:
            self.status.showMessage(problem)
        current = next((e for e in entries if self._is_current(e)), None)
        if current:
            self.cfg.choose(current, entries)
        self._refresh_target()

    def _is_current(self, e: dict) -> bool:
        return (e["org"] == self.cfg.org_name and e["system"] == self.cfg.system_name
                and (e.get("db_kor") or "") == (self.cfg.db_kor_name or ""))

    def choose(self, entry: dict):
        self.cfg.choose(entry, self.entries)
        for action, e in self._actions:
            action.setChecked(e is entry)
        self._refresh_target()

    def _refresh_target(self):
        c = self.cfg
        if c.org_name and c.system_name:
            db_part = f"  ·  {c.db_kor_name}" if c.db_kor_name else ""
            text = f"{c.org_name}   ›   {c.system_name}{db_part}"
        else:
            text = "메타 파일을 고르면 자동으로 정해집니다"
        self.target.setText(PAD + text)   # 메뉴 달린 버튼은 왼쪽 여백(padding)이 먹지 않아 공백으로 띄운다
        self._refresh_project()
        if hasattr(self, "pages"):
            self.pages["history"].set_target(c.org_name, c.system_name, c.db_name)
            inst = self.pages["define"].inst   # 기관표준 점검 · A값 (그 기관의 기관표준을 사전에서)
            inst.output_dir = self.cfg.output_dir
            try:
                inst.set_org(c.org_name, c.db_settings())
            except Exception:
                pass

    # --- 동작 ---------------------------------------------------------------

    def go(self, key: str):
        self.stack.setCurrentWidget(self.pages[key])
        if key in self.nav:   # 메뉴에서 뺀 화면(값)도 다른 화면에서 넘어올 수 있다
            self.nav[key].setChecked(True)
        self.title.setText(TITLES[key])
        self.meta_box.setVisible(key not in PQC_PAGES)   # 예방적 품질관리는 메타 파일과 상관없다
        if key in PQC_PAGES:
            self.status.clearMessage()
        self._refresh_project()

    def _refresh_project(self):
        c = self.cfg
        parts = [c.org_name, c.db_name, c.db_eng_name and f"영문 DB명 {c.db_eng_name}"]
        self.project.setText(" · ".join(x for x in parts if x) or "기관과 시스템을 고르세요")
        if not self.meta_box.isVisibleTo(self):   # 예방적 품질관리 화면: 메타 파일의 기관·시스템과 상관없다
            self.project.setText("사업단 대상 파일 · RFP · 완료 보고서로 봅니다")
        title, detail = c.dict_text()
        self.source_title.setText(title)
        self.source_detail.setText(detail)

    def _pick_meta(self):
        start = self.meta.text() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "메타 파일 선택", start, "엑셀 (*.xlsx *.xlsm)")
        if path:
            self.meta.setText(path)
            self._meta_edited()

    # --- 끌어다 놓기 ---------------------------------------------------------

    @staticmethod
    def _dropped(event) -> list:
        """끌어 온 로컬 파일·폴더 경로."""
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        return [str(Path(u.toLocalFile())) for u in urls if u.isLocalFile()]

    @staticmethod
    def _dropped_excel(paths: list) -> str:
        """끌어 온 것이 엑셀 파일 하나면 그 경로."""
        if len(paths) == 1 and Path(paths[0]).suffix.lower() in (".xlsx", ".xlsm"):
            return paths[0]
        return ""

    def _set_dropping(self, on: bool, meta: bool = True):
        self.meta.setProperty("dropping", on and meta)
        self.meta.style().unpolish(self.meta)
        self.meta.style().polish(self.meta)
        self.drop_cover.setGeometry(self.centralWidget().geometry())
        self.drop_cover.setVisible(on)
        self.drop_cover.raise_()

    def eventFilter(self, obj, event):
        """창 안 어디에 놓아도 메타 파일로 받는다. 입력칸·표 같은 안쪽 위젯이 먼저 가로채지 않게 앱 전체에서 거른다."""
        kind = event.type()
        if kind not in (QEvent.DragEnter, QEvent.DragMove, QEvent.DragLeave, QEvent.Drop)                 or not isinstance(obj, QWidget) or obj.window() is not self:
            return False
        if kind == QEvent.DragLeave:
            if not self.frameGeometry().contains(QCursor.pos()):   # 창 밖으로 나갔을 때만
                self._set_dropping(False)
                self.status.clearMessage()
            return True
        page = self.stack.currentWidget()
        paths = self._dropped(event)
        receiver = hasattr(page, "drop_files")   # 자기 파일을 받는 화면(예방적 품질관리)은 그 화면으로
        ok = page.accepts(paths) if receiver else bool(self._dropped_excel(paths)) and self.run_button.isEnabled()
        if not ok:
            event.ignore()
            return True
        event.acceptProposedAction()
        what = page.drop_label if receiver else "메타 파일"
        if kind == QEvent.Drop:
            self._set_dropping(False)
            if receiver:
                self.status.showMessage(f"{what} 읽는 중…")
                page.drop_files(paths)
                self.status.showMessage(f"{what}: {', '.join(Path(x).name for x in paths)[:120]}")
            else:
                self.meta.setText(self._dropped_excel(paths))
                self._meta_edited()
        elif not self.drop_cover.isVisible():
            self.drop_cover.setText(f"여기에 놓으면 {what}(으)로 씁니다")
            self._set_dropping(True, meta=not receiver)
            self.status.showMessage(f"놓으면 {what}(으)로 씁니다")
        return True

    def _meta_edited(self):
        if self.meta.text().strip() != self._detected:
            self.status.showMessage(self.detect_target() or self.status.currentMessage())

    def detect_target(self) -> str:
        """메타 파일의 기관명·정보시스템명으로 위쪽 기관·시스템을 정한다.
        반환: 하나로 못 정했을 때(시스템에 DB가 여럿) 안내. 정했거나 파일에 없으면 빈 문자열."""
        path = self._detected = self.meta.text().strip()
        if not path or not Path(path).is_file():
            return ""
        try:
            found = read_meta_target(path)
        except Exception as e:   # 읽지 못하는 파일은 실행할 때 다시 알린다
            self.status.showMessage(f"메타 파일을 읽지 못했습니다: {e}")
            return ""
        if not found:
            self.status.showMessage("메타 파일에 기관명·정보시스템명이 없습니다. 위쪽 '기관·시스템'에서 고르세요.")
            return ""
        rows = match_meta(found, self.entries)
        current = next((e for e in rows if self._is_current(e)), None)
        if current or len(rows) == 1:
            self.choose(current or rows[0])
            self.status.showMessage(f"메타 파일에서 읽었습니다: {self.target.text().strip()}")
            return ""
        self._detected = ""   # DB를 고를 때까지 실행할 때마다 다시 확인
        return (f"{found['org']} {found['system']}에는 DB가 {len(rows)}개 있습니다. "
                f"위쪽 '기관·시스템'에서 이 파일의 DB를 고르세요.")

    def open_settings(self):
        if SettingsDialog(self.cfg, self).exec():
            for key in PQC_PAGES:
                self.pages[key].output_dir = self.cfg.output_dir
            self.load_eval_list()

    def run(self):
        self.cfg.meta = self.meta.text().strip()
        if self.cfg.meta != self._detected and (problem := self.detect_target()):
            QMessageBox.information(self, "실행", problem)
            return
        missing = self.cfg.missing()
        if missing:
            QMessageBox.information(self, "실행", f"먼저 고르세요: {', '.join(missing)}")
            return
        self.cfg.save()
        settings = self.cfg.build()
        self.run_button.setEnabled(False)
        self.busy.setVisible(True)
        self.status.showMessage("실행 중…")
        self._thread = QThread(self)
        self._worker = RunWorker(settings)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(lambda text: self.status.showMessage(text.strip()))
        self._worker.progress.connect(self.run_panel.add_log)
        self._worker.step.connect(self.run_panel.step_done)
        self.run_panel.start()
        self.panel_button.setEnabled(True)
        self._worker.finished.connect(self._done)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _done(self, outcome, settings):
        self._idle()
        self._record(outcome, settings)
        self.run_panel.finish(True, f"산출물 {len(outcome.paths)}개", outcome.folder)
        self.show_outcome(outcome, settings)
        self.status.showMessage(f"완료 · 산출물 {len(outcome.paths)}개 · {outcome.folder}", 0)

    def _record(self, outcome, settings):
        """회차 기록에 남기고 산출물 폴더에 실행기록.xlsx. 기록이 안 돼도 실행 결과는 그대로 보여 준다."""
        try:
            run_id = history.record(outcome, settings)
            outcome.paths.append(history.write_log(outcome.folder, settings.org_name, settings.db_name, run_id))
        except Exception as e:
            self.run_panel.add_log(f"      회차 기록을 남기지 못했습니다: {e}")

    def _failed(self, message: str):
        self._idle()
        self.run_panel.finish(False, message)
        self.status.showMessage("실행하지 못했습니다")
        QMessageBox.warning(self, "실행", message)

    def _idle(self):
        self.run_button.setEnabled(True)
        self.busy.setVisible(False)

    def show_outcome(self, outcome, settings):
        self.outcome = outcome
        for page in self.pages.values():
            page.show_outcome(outcome, settings)

    def _files_written(self, paths):
        if self.outcome:
            names = {Path(p).name for p in paths}
            self.outcome.paths = [p for p in self.outcome.paths if Path(p).name not in names] + list(paths)
            settings = self.pages["link"].settings
            for key in ("summary", "link", "link_status"):   # 두 연계 화면의 미리보기도 새 행으로
                self.pages[key].show_outcome(self.outcome, settings)
            self.status.showMessage(f"양식을 다시 만들었습니다 · {self.outcome.folder}")
