"""회차 기록 화면. 실행 결과가 아니라 회차 기록(history.sqlite)을 보여 준다."""
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QMessageBox, QPushButton, QTabWidget

from .. import history
from .pages import Page, open_path
from .widgets import Card, TableBox, label

ITEM_HEADERS = ["점검 화면", "이름", "영문약어명", "오류명"]


def _pct(value) -> str:
    return "" if value is None else f"{value:.1f}%"


def _run_name(r: history.Run) -> str:
    return f"{r.id}회 · {r.at} · {r.kind} · {r.user}"


def _section(title: str, hint: str = "") -> Card:
    card = Card()
    card.body.addWidget(label(title, "sectionTitle"))
    if hint:
        card.body.addWidget(label(hint, "muted", wrap=True))
    return card


class _Target:
    """기관·시스템을 받아 두는 화면 (머리글에서 고르면 set_target)."""

    def set_target(self, org: str, system: str, db_name: str):
        self.org, self.system, self.db_name = org, system, db_name
        self.refresh()

    def show_outcome(self, outcome, settings):
        self.empty.setVisible(False)
        self.refresh()


# ---------------------------------------------------------------------------
# 회차 기록
# ---------------------------------------------------------------------------

RUN_HEADERS = ["회차", "구분", "일시", "실행자", "표준 사전", "입력 파일", "표준 적용률", "구조 현행화율",
               "완전성 오류", "준용 오류", "적용 오류", "현행화 오류"]


class HistoryPage(_Target, Page):
    def __init__(self):
        super().__init__()
        self.org = self.system = self.db_name = ""
        self.runs = []
        self.empty.setVisible(False)
        self.title = label("", "muted", wrap=True)
        self.content.addWidget(self.title)

        self.table = TableBox(RUN_HEADERS, flag_label=None)
        self.table.model.mono_cols = {0}
        self.content.addWidget(self.table)

        compare = _section("두 회차 비교", "이전 회차와 이후 회차를 고르면 지표 변화와 고쳐진 오류·새로 생긴 오류를 보여 줍니다. "
                                         "오류는 점검 화면·이름·영문약어명·오류명이 같으면 같은 오류로 봅니다.")
        row = QHBoxLayout()
        self.before, self.after = QComboBox(), QComboBox()
        for box in (self.before, self.after):
            box.setMinimumWidth(320)
            box.currentIndexChanged.connect(self._compare)
        row.addWidget(label("이전"))
        row.addWidget(self.before, 1)
        row.addWidget(label("→  이후"))
        row.addWidget(self.after, 1)
        self.open_folder = QPushButton("이후 회차 산출물 폴더")
        self.open_folder.setObjectName("secondary")
        self.open_folder.clicked.connect(self._open_folder)
        row.addWidget(self.open_folder)
        self.remove = QPushButton("이후 회차 지우기")
        self.remove.setObjectName("secondary")
        self.remove.clicked.connect(self._remove)
        row.addWidget(self.remove)
        compare.body.addLayout(row)
        self.changes = TableBox(["지표", "이전", "이후"], flag_label=None)
        self.changes.view.setMinimumHeight(150)
        compare.body.addWidget(self.changes)
        self.tabs = QTabWidget()
        self.lists = {}
        for name in ("고쳐진 오류", "새로 생긴 오류", "그대로인 오류"):
            box = TableBox(ITEM_HEADERS, flag_label=None)
            box.model.mono_cols = {2}
            self.lists[name] = box
            self.tabs.addTab(box, name)
        compare.body.addWidget(self.tabs, 1)
        self.compare_card = compare
        self.content.addWidget(compare, 1)
        self.refresh()

    def refresh(self):
        if not (self.org and self.db_name):
            self.title.setText("위쪽에서 기관·시스템을 고르면 그 시스템의 회차가 나옵니다.")
            self.runs = []
        else:
            self.runs = history.runs(self.org, self.db_name)
            self.title.setText(f"{self.org} · {self.db_name} — 회차 {len(self.runs)}개. ▶ 실행할 때마다 자동으로 쌓입니다. "
                               f"기록 위치: {history.history_path()}")
        self.table.set_rows([(r.id, r.kind, r.at, r.user, r.dict_version, r.source, _pct(r.rate), _pct(r.currency_rate),
                              r.total("완전성"), r.total("준용"), r.total("적용"), r.total("현행화")) for r in self.runs],
                            empty="아직 회차가 없습니다. 이 시스템을 ▶ 실행하면 첫 회차가 남습니다.")
        names = [_run_name(r) for r in self.runs]
        for box, pick in ((self.before, 1), (self.after, 0)):
            box.blockSignals(True)
            box.clear()
            box.addItems(names)
            box.setCurrentIndex(min(pick, len(names) - 1))
            box.blockSignals(False)
        self.compare_card.setVisible(len(self.runs) >= 1)
        self._compare()

    def _pick(self, box):
        i = box.currentIndex()
        return self.runs[i] if 0 <= i < len(self.runs) else None

    def _compare(self, *_):
        old, new = self._pick(self.before), self._pick(self.after)
        self.open_folder.setEnabled(bool(new and new.folder))
        self.remove.setEnabled(new is not None)
        if not (old and new):
            self.changes.set_rows([])
            for box in self.lists.values():
                box.set_rows([])
            return
        self.changes.set_rows(history.change_text(old, new))
        fixed, added, kept = history.compare(history.items(old.id), history.items(new.id))
        for n, (name, rows) in enumerate(zip(self.lists, (fixed, added, kept))):
            kinds = ["success" if name == "고쳐진 오류" else "error" if name == "새로 생긴 오류" else None] * len(rows)
            self.lists[name].set_rows(rows, kinds, empty="없음")
            self.tabs.setTabText(n, f"{name} {len(rows):,}")

    def _open_folder(self):
        new = self._pick(self.after)
        if new and new.folder and Path(new.folder).exists():
            open_path(new.folder)
        elif new:
            QMessageBox.information(self, "산출물 폴더", f"폴더가 없습니다: {new.folder}")

    def _remove(self):
        new = self._pick(self.after)
        if new and QMessageBox.question(self, "회차 지우기", f"{_run_name(new)}\n\n이 회차 기록을 지울까요? 산출물 파일은 그대로 둡니다.") \
                == QMessageBox.Yes:
            history.delete(new.id)
            self.refresh()

