"""예방적 품질관리(2-1-2) 화면. 메타 파일·▶ 실행과 상관없이 사업단 이행점검 대상 파일로 움직인다."""
import html
from datetime import date
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QTextBrowser, QWidget)

from .. import preventive_store as store
from ..core import preventive as pv
from ..core import preventive_check as pc
from ..workbook import preventive_report as report
from ..workbook.documents import SUFFIXES, DocumentError, read_document
from ..workbook.writer import safe_name
from .pages import Page, _ChoiceDelegate, open_path
from . import theme
from .widgets import Badge, Card, Kpi, TableBox, hbox, label

HEADERS = ["단계", "기관명", "사업명", "사업시작일", "사업종료일", "사전협의신청일", "분류(예측)", "회차(예측)", "사업유형", "이관",
           "대응 지표", "금액 확인 후", "비고"]
COL_TYPE, COL_TRANSFER = 8, 9
ALL = "전체"
TYPE_CHOICES = pv.TYPES + ["운영유지보수+고도화", "운영유지보수+신규구축"]
EMPTY = ("사업단이 보낸 '이행점검(N차) 대상.xlsx'를 창에 끌어다 놓거나 [대상 파일 찾기]를 누르세요. "
         "관리 기관(설정의 평가대상 DB 목록) 사업만 골라 단계·사업유형·대응 지표·다음 회차를 판정합니다.")


def _tidy(page, bar):
    """빈 화면 안내는 위쪽 입력 줄 바로 아래, 남는 세로 공간은 맨 아래 빈칸이 받는다 (입력 줄·안내가 늘어나지 않게)."""
    page.content.removeWidget(page.empty)
    page.content.insertWidget(page.content.indexOf(bar) + 1, page.empty)
    for w in (bar, page.empty):
        w.setSizePolicy(w.sizePolicy().horizontalPolicy(), QSizePolicy.Maximum)
    page.content.addStretch(0)


def _kind(j) -> str | None:
    """행 색: 파랑 = 다음 회차 완료 전환 예상, 초록 = 내년 후보, 노랑 = 확인필요. 대응 불필요는 None('대응 필요만 보기'에서 빠짐)."""
    if not j.project.needs_action:
        return None
    if any(k in j.category for k in (pv.C_MOVE, pv.C_PLANNED, pv.C_EXPECT)):
        return "blue"
    if j.category in (pv.C_NEXT_YEAR, pv.C_NEXT_ORDER):
        return "green"
    return "warn" if j.flags else "plain"


def _order(j) -> tuple:
    """할 일이 있는 사업부터: 대상 예측·전환 예상 → 내년 후보 → 확인필요 → 완료단계 점검 → 나머지 → 대응 불필요 → 비대상."""
    c, p = j.category, j.project
    if p.stage == pv.C_OUT:
        rank = 7
    elif not p.needs_action:
        rank = 6
    elif any(k in c for k in (pv.C_EXPECT, pv.C_MOVE, pv.C_PLANNED)):
        rank = 0
    elif c in (pv.C_NEXT_YEAR, pv.C_NEXT_ORDER):
        rank = 1
    else:
        rank = 2 if j.flags else 3 if pv.C_DONE in c else 4
    return rank, p.org, p.name, p.stage != pv.ORDER


class TargetsPage(Page):
    """대상 사업: 관리 기관 필터 · 단계 · 다음 회차 예측 · 내년 후보 · 사업유형 · 대응 지표."""
    changed = Signal()   # 판정을 다시 했을 때 (점검 화면의 사업 목록)

    def __init__(self):
        super().__init__()
        self.empty.setText(EMPTY)
        self.orgs, self.projects, self.judgements, self.source = [], [], [], ""
        self.output_dir = ""
        self.criteria = None

        bar = Card()
        row = QHBoxLayout()
        self.info = label("", wrap=True)
        self.info.setMinimumWidth(0)
        row.addWidget(self.info, 1)
        self.pick = QPushButton("대상 파일 찾기")
        self.pick.setObjectName("secondary")
        self.pick.clicked.connect(self._pick)
        self.criteria_button = QPushButton("기준 엑셀 열기")
        self.criteria_button.setObjectName("secondary")
        self.criteria_button.setToolTip("회차 기간·사업유형 키워드·적용표·지표별 산출물·요구사항 문안. 사용자 폴더에 복사해 열고, "
                                        "고쳐 저장하면 다음에 대상 파일을 읽을 때부터 반영됩니다.")
        self.criteria_button.clicked.connect(lambda: open_path(report.editable_criteria()))
        self.save = QPushButton("결과 엑셀 저장")
        self.save.setObjectName("primary")
        self.save.clicked.connect(self._save)
        for w in (self.pick, self.criteria_button, self.save):
            row.addWidget(w)
        bar.body.addLayout(row)
        bar.body.addWidget(label("사업유형은 사업명 키워드로 정합니다(매뉴얼 3.2.1.3). 사업유형·이관 칸을 두 번 눌러 고치면 "
                                 "대응 지표가 다시 계산되고, 고친 값은 다음 회차에도 이어집니다. 금액은 발주단계 점검에 RFP를 넣으면 채워져 "
                                 "'금액 확인 후' 지표가 정해집니다.",
                                 "muted", wrap=True))
        self.content.addWidget(bar)

        self.kpis = {name: Kpi(name) for name in ("관리 기관 사업", "대응 필요", "다음 회차 완료 예상", "내년 후보", "확인필요")}
        self.kpi_row = hbox(*self.kpis.values())
        self.content.addLayout(self.kpi_row)

        # 거르기: 단계 · 분류 · 사업유형 · 사업종료(회차 기간) · 기관. 고르면 표만 다시 거른다 (판정은 그대로)
        self.filter_bar = QWidget()
        fl = QHBoxLayout(self.filter_bar)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(8)
        self.filters = {}
        for key, title in (("stage", "단계"), ("category", "분류"), ("type", "사업유형"), ("end", "사업종료"), ("org", "기관")):
            box = QComboBox()
            box.setToolTip(f"{title}로 거르기")
            box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            box.setMinimumContentsLength(3)   # 좁은 창에서는 글자가 줄어 보이고, 펼치면 다 보인다
            box.view().setMinimumWidth(240)
            box.currentIndexChanged.connect(self._apply_filters)
            self.filters[key] = (title, box)
            fl.addWidget(box, 1)
        reset = QPushButton("초기화")
        reset.setObjectName("secondary")
        reset.clicked.connect(self._reset_filters)
        fl.addWidget(reset)
        self.content.addWidget(self.filter_bar)

        self.mine = QCheckBox("관리 기관만")
        self.mine.setChecked(True)
        self.mine.toggled.connect(self._render)
        self.table = TableBox(HEADERS, flag_label="대응 필요만 보기")
        self.table.body.itemAt(0).layout().addWidget(self.mine)
        self.table.model.editable_cols = {COL_TYPE, COL_TRANSFER}
        self.table.proxy.row_filter = self._row_ok
        self.table.wrap({len(HEADERS) - 1: 320})   # 비고는 길어도 다 보이게
        self.table.view.setItemDelegateForColumn(COL_TYPE, _ChoiceDelegate(TYPE_CHOICES, self.table.view, editable=False))
        self.table.view.setItemDelegateForColumn(COL_TRANSFER, _ChoiceDelegate(["Y", "N"], self.table.view, editable=False))
        self.table.model.dataChanged.connect(self._edited)
        self.content.addWidget(self.table, 1)
        self.shown = []   # 표에 그린 판정 (행 순서)
        _tidy(self, bar)
        self._restore()

    # --- 바깥에서 부르는 것 ----------------------------------------------------

    def set_orgs(self, entries: list):
        """평가대상 DB 목록의 기관 = 관리 기관."""
        self.orgs = sorted({e["org"] for e in entries})
        if self.projects:
            self._judge()

    drop_label = "사업단 대상 파일"

    @staticmethod
    def accepts(paths: list) -> bool:
        return len(paths) == 1 and Path(paths[0]).suffix.lower() in (".xlsx", ".xlsm")

    def drop_files(self, paths: list):
        """창에 끌어다 놓은 엑셀. 사업단 대상 파일로 읽는다."""
        self.load(paths[0])

    def show_outcome(self, outcome, settings):
        self.empty.setVisible(not self.projects)   # 메타 실행 결과와 상관없다

    # --- 읽기·판정 ------------------------------------------------------------

    def _irm(self) -> bool:
        return any(p.category for p in self.projects)

    def _restore(self):
        """마지막으로 읽은 파일을 다시 읽어 보여 준다. 파일이 없어졌으면 기록의 마지막 사업단 회차."""
        try:
            last = store.recall("targets_file")
            if last and Path(last).exists():
                self.load(last, quiet=True)
                if self.projects:
                    return
            last = store.rounds()[-1:]
            if last:
                year, no, _, source = last[0]
                self.projects, self.source = store.load_round(year, no), source
                self._judge()
                return
        except Exception:   # 기록을 못 읽어도 화면은 뜬다
            pass
        self._render()

    def _pick(self):
        start = str(Path(self.source).parent) if self.source and Path(self.source).parent.exists() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "사업단 이행점검 대상 파일 또는 IRM 사전협의(총괄) 목록", start,
                                              "엑셀 (*.xlsx *.xlsm)")
        if path:
            self.load(path)

    def load(self, path: str, quiet: bool = False):
        """사업단 이행점검 대상 파일 또는 IRM 사전협의(총괄) 목록."""
        try:
            self.criteria = report.load_criteria()
            projects = report.read_targets(path, self.criteria)
        except Exception as e:
            if not quiet:
                QMessageBox.warning(self, "대상 파일", f"읽지 못했습니다.\n{e}")
            return
        self.projects, self.source = projects, str(path)
        try:
            store.remember("targets_file", str(path))
            if not any(p.category for p in projects):   # 사업단 회차만 기록 (IRM 예측은 회차 기록을 덮어쓰지 않는다)
                store.save_round(projects, Path(path).name)
        except Exception as e:
            if not quiet:
                QMessageBox.warning(self, "대상 파일", f"회차 기록을 남기지 못했습니다 (판정은 그대로 보여 줍니다).\n{e}")
        self._judge()

    def _judge(self):
        if self.criteria is None:
            self.criteria = report.load_criteria()
        managed = {pv.org_key(o) for o in self.orgs}
        previous, done = store.earlier(self.projects)
        self.judgements = pv.judge(self.projects, self.criteria, managed, store.load_edits(), previous, done)
        self._render()
        self.changed.emit()

    def _render(self, *_):
        has = bool(self.projects)
        self.empty.setVisible(not has)
        self.table.setVisible(has)
        self.filter_bar.setVisible(has)
        for k in self.kpis.values():
            k.setVisible(has)
        self.save.setEnabled(has)
        if not has:
            self.info.setText("아직 읽은 대상 파일이 없습니다.")
            return
        c = pv.counts(self.judgements)
        org_note = f"관리 기관 {len(self.orgs)}곳 중 {c['기관']}곳" if self.orgs else "관리 기관 목록 없음 (설정 → 평가대상 DB 목록) · 모든 기관 표시"
        if self._irm():
            what = (f"IRM 사전협의(총괄) 목록으로 예측 (사업단 대상 목록 전) · 사업 {len({p.key for p in self.projects}):,}건"
                    f" · 기준: 발주 통보일·완료 종료일 → 기준 엑셀 '회차' 기간")
        else:
            p0 = self.projects[0]
            rounds = sorted({(p.year, p.round) for p in self.projects})
            what = f"{p0.year}년 {', '.join(f'{n}차' for _, n in rounds)} 사업단 대상 목록 · 전체 {len(self.projects):,}건"
        self.info.setText(f"<b>{Path(self.source).name}</b><br>{what} · {org_note}"
                          f" · 관리 기관 발주 {c['발주']} · 완료 {c['완료']}")
        self.kpis["관리 기관 사업"].number.set(f"{c['사업']:,}", "건")
        self.kpis["대응 필요"].number.set(f"{c['대응 필요']:,}", "건")
        self.kpis["다음 회차 완료 예상"].number.set(f"{c['전환 예상']:,}", "건")
        self.kpis["내년 후보"].number.set(f"{c['내년 후보']:,}", "건")
        self.kpis["확인필요"].number.set(f"{c['확인필요']:,}", "건")
        only_mine = self.mine.isChecked() and bool(self.orgs)
        self.shown = sorted((j for j in self.judgements if j.managed or not only_mine), key=_order)
        self._fill_filters()
        self.table.set_rows([self._row(j) for j in self.shown], [_kind(j) for j in self.shown],
                            empty="관리 기관 사업이 없습니다. '관리 기관만'을 끄면 전체가 보입니다.")

    @staticmethod
    def _row(j) -> list:
        p = j.project
        day = lambda d: d.isoformat() if d else ""   # noqa: E731
        return [p.stage_label, p.org, p.name, day(p.start), day(p.end), day(p.applied), j.category, j.target,
                "+".join(j.types), "Y" if j.transfer else "N", " ".join(j.required), " ".join(j.maybe),
                "\n".join(([p.reason] if p.reason else []) + j.flags)]

    # --- 거르기 ------------------------------------------------------------------

    def _end_label(self, j) -> str:
        """사업종료일이 드는 완료 기간 (기준 엑셀 '회차' 시트). 추정 행은 (추정)."""
        if j.project.end is None:
            return "종료일 없음"
        r = pv.done_round(j.project.end, self.criteria) if self.criteria else None
        if r is None:
            return "기간 밖"
        guess = " (추정)" if "추정" in r.note else ""
        return f"{r.label} {r.done_start:%y.%m.%d}~{r.done_end:%y.%m.%d}{guess}"

    def _values(self, j) -> dict:
        return {"stage": f"{j.project.stage}단계", "category": j.category, "type": "+".join(j.types),
                "end": self._end_label(j), "org": j.project.org}

    def _fill_filters(self):
        """지금 표에 있는 값으로 고르는 상자를 채운다 (고른 값이 남아 있으면 유지)."""
        values = [self._values(j) for j in self.shown]
        for key, (title, box) in self.filters.items():
            current = box.currentData()
            box.blockSignals(True)
            box.clear()
            box.addItem(f"{title}: {ALL}", ALL)
            for v in sorted({v[key] for v in values}):
                box.addItem(f"{title}: {v}", v)
            index = box.findData(current)
            box.setCurrentIndex(index if index >= 0 else 0)
            box.blockSignals(False)

    def _row_ok(self, row: int) -> bool:
        if not (0 <= row < len(self.shown)):
            return True
        values = self._values(self.shown[row])
        return all(box.currentData() in (ALL, None) or values[key] == box.currentData()
                   for key, (_, box) in self.filters.items())

    def _apply_filters(self, *_):
        self.table.refilter()

    def _reset_filters(self):
        for _, box in self.filters.values():
            box.blockSignals(True)
            box.setCurrentIndex(0)
            box.blockSignals(False)
        self.table.refilter()

    # --- 고치기·저장 ------------------------------------------------------------

    def _edited(self, top, bottom, *_):
        col = top.column()
        if col not in (COL_TYPE, COL_TRANSFER) or not (0 <= top.row() < len(self.shown)):
            return
        j = self.shown[top.row()]
        value = str(self.table.model.rows[top.row()][col] or "").strip()
        edit = store.load_edits().get(j.project.key) or pv.Edit()
        if col == COL_TYPE:
            edit.types = value if value != "+".join(pv.classify(j.project.name, self.criteria)[0]) else ""
        else:
            edit.transfer = value if value in ("Y", "N") else ""
        store.save_edit(j.project.key, edit)
        QTimer.singleShot(0, self._judge)   # 편집이 끝난 뒤 표를 다시 그린다

    def _save(self):
        if not self.judgements:
            return
        p0 = self.projects[0]
        rounds = "·".join(f"{n}차" for n in sorted({p.round for p in self.projects}))
        name = safe_name(f"예방적품질관리_대상사업_{p0.year}_{rounds}_{date.today():%Y%m%d}.xlsx")
        start = str(Path(self.output_dir or Path.home()) / name)
        path, _ = QFileDialog.getSaveFileName(self, "결과 엑셀 저장", start, "엑셀 (*.xlsx)")
        if not path:
            return
        c = pv.counts(self.judgements)
        summary = [("평가연도·회차", f"{p0.year}년 {rounds}"),
                   ("관리 기관", f"{len(self.orgs)}곳 (stdtool 평가대상 DB 목록) · 사업이 있는 기관 {c['기관']}곳"),
                   ("관리 기관 사업", f"{c['사업']}건 (발주 {c['발주']} · 완료 {c['완료']}) · 대응 필요 {c['대응 필요']}건"),
                   ("다음 회차 완료 전환 예상", f"{c['전환 예상']}건 — 의견 있음 + 사업종료일이 다음 회차 완료 기간 안"),
                   ("내년 후보", f"{c['내년 후보']}건 — 의견 있음 + 통보일·완료일이 내년 평가 기간 안 (기준 엑셀 '회차'의 추정 행)"),
                   ("확인필요", f"{c['확인필요']}건 — 사업유형 추정·금액 없음·기간 연장 등"),
                   ("기준", f"{report.criteria_path()} (회차 기간: "
                           + ", ".join(f"{r.label} 완료 {r.done_start}~{r.done_end}" for r in self.criteria.rounds) + ")")]
        try:
            written = report.write_targets(self.judgements, self.criteria, Path(path), Path(self.source).name, summary)
        except PermissionError:
            QMessageBox.warning(self, "결과 엑셀", "파일을 쓸 수 없습니다. 엑셀에서 열어 두었다면 닫고 다시 저장하세요.")
            return
        if QMessageBox.question(self, "결과 엑셀", f"저장했습니다.\n{written}\n\n열어 볼까요?") == QMessageBox.Yes:
            open_path(written)


# ---------------------------------------------------------------------------
# 발주단계 점검(RFP) · 완료단계 점검(완료·감리보고서)
# ---------------------------------------------------------------------------

CHECK_HEADERS = ["코드", "진단항목", "구분", "결과", "예상", "근거", "위치", "의견"]
STATUS_TEXT = {"Y": ("Y · 확인", "success"), "N": ("N · 보완서류 필요", "error"), "-": ("- · 해당 없음", "neutral")}


class PortalTable(Card):
    """품질·표준관리 통합시스템 '사업 진단결과' 표: 사업명 | 지표별 (1)(2) Y/N/- | 진단결과반영비율.
    칸을 누르면 picked(기준 코드)."""
    picked = Signal(str)

    def __init__(self, details: list):
        super().__init__()
        head = QHBoxLayout()
        head.addWidget(label("사업 진단결과", "sectionTitle"))
        head.addWidget(label("품질·표준관리 통합시스템 양식 · 칸을 누르면 아래에 판단 이유가 나옵니다", "muted"))
        head.addStretch(1)
        for text, kind in (("Y 확인", "success"), ("N 보완서류 필요", "error"), ("- 해당 없음", "neutral")):
            head.addWidget(Badge(text, kind))
        self.body.addLayout(head)
        grid_box = QFrame()
        grid_box.setObjectName("portal")
        grid = QGridLayout(grid_box)
        grid.setSpacing(0)
        grid.setContentsMargins(0, 0, 0, 0)
        groups = {}
        for d in details:
            groups.setdefault(d.item, []).append(d)
        grid.addWidget(self._head("사업명"), 0, 0, 2, 1)
        self.cells, col = {}, 1
        for item, members in groups.items():
            title = f"{item}\n{report.PORTAL_ITEM.get(item, '')}"
            if len(members) == 1:
                grid.addWidget(self._head(title), 0, col, 2, 1)
            else:
                grid.addWidget(self._head(title), 0, col, 1, len(members))
            for i, d in enumerate(members):
                if len(members) > 1:
                    grid.addWidget(self._head(d.code[len(item):] or d.code, sub=True), 1, col + i)
                cell = QPushButton("")
                cell.setObjectName("portalCell")
                cell.setCheckable(True)
                cell.setCursor(Qt.PointingHandCursor)
                cell.setToolTip(f"{d.code} {d.text}")
                cell.setMinimumWidth(52)
                cell.clicked.connect(lambda _=False, code=d.code: self.picked.emit(code))
                grid.addWidget(cell, 2, col + i)
                grid.setColumnMinimumWidth(col + i, 52)
                grid.setColumnStretch(col + i, 1)
                self.cells[d.code] = cell
            col += len(members)
        grid.addWidget(self._head("진단결과\n반영비율"), 0, col, 2, 1)
        self.name = label("", "portalName", wrap=True)
        self.name.setMinimumWidth(200)
        grid.addWidget(self.name, 2, 0)
        grid.setColumnStretch(0, 4)
        self.ratio = label("", "portalRatio")
        self.ratio.setAlignment(Qt.AlignCenter)
        self.ratio.setMinimumWidth(84)
        grid.addWidget(self.ratio, 2, col)
        scroll = QScrollArea()   # 창이 좁으면 표만 옆으로 밀어 본다
        scroll.setObjectName("portalScroll")
        scroll.setWidget(grid_box)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid_box.setMinimumWidth(200 + 52 * len(self.cells) + 84)
        self.scroll = scroll
        self.body.addWidget(scroll)

    @staticmethod
    def _head(text: str, sub: bool = False) -> QLabel:
        w = label(text, "portalSub" if sub else "portalHead", wrap=True)
        w.setAlignment(Qt.AlignCenter)
        return w

    def show_check(self, name: str, criteria: list, ratio: str, selected: str):
        self.name.setText(name)
        self.ratio.setText(ratio)
        for d in criteria:
            cell = self.cells.get(d.code)
            if cell is None:
                continue
            cell.setText(d.status)
            cell.setProperty("status", d.status)
            cell.setChecked(d.code == selected)
            cell.style().unpolish(cell)
            cell.style().polish(cell)
        QTimer.singleShot(0, self._fit)

    def _fit(self):
        """표 높이를 내용(사업명 줄바꿈)에 맞춘다. 창이 좁아 옆 스크롤이 생기면 그만큼 더."""
        box = self.scroll.widget()
        width = max(box.minimumWidth(), self.scroll.viewport().width())
        layout = box.layout()
        height = layout.totalHeightForWidth(width) if layout.hasHeightForWidth() else layout.totalSizeHint().height()
        bar = self.scroll.horizontalScrollBar().sizeHint().height() if box.minimumWidth() > self.scroll.width() else 0
        self.scroll.setFixedHeight(height + bar + 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit)


def _esc(text) -> str:
    return html.escape(str(text or ""))


def _section(title: str, color: str, body: str) -> str:
    return (f"<p style='margin:0 0 4px 0; font-weight:600; color:{color}'>{html.escape(title)}</p>"
            f"<p style='margin:0 0 14px 0; line-height:150%'>{body}</p>")


def _words(words: list) -> str:
    return ", ".join(f"'{w.replace('+', ' + ')}'" for w in words[:6]) + (" 등" if len(words) > 6 else "")


def _short_band(band: str) -> str:
    """'1억 이상 10억 미만' → '1억~10억 미만' (카드에 짧게)."""
    return band.replace(" 이상 ", "~")
OTHER = "목록에 없는 사업 (사업명을 직접 입력)"


class CheckPage(Page):
    """kind = '발주': RFP(hwpx·hwp) → 금액, 지표별 데이터 요구사항, 넣을 문안.
    kind = '완료': 완료·감리보고서(pdf·hwpx·hwp) → 지표별 수행 내역, 보완할 지표의 가이드 폴더."""

    def __init__(self, kind: str, targets: TargetsPage):
        super().__init__()
        self.kind, self.targets = kind, targets
        self.check, self.options, self.output_dir, self.source = None, [], "", ""
        self.matched = self.match_note = ""
        self.record = None
        self.codes = ([], [])
        order = kind == "발주"
        self.drop_label = "RFP" if order else "완료·감리보고서"
        self.empty.setText("RFP(hwpx·hwp)를 창에 끌어다 놓거나 [RFP 찾기]를 누르세요. 사업 금액을 읽고, 이 사업 유형·금액에 맞는 "
                           "데이터 요구사항(DAR)이 RFP에 있는지 지표별로 봅니다. 빠진 지표에는 매뉴얼 3.2.2 문안을 붙여 줍니다."
                           if order else
                           "완료보고서·감리보고서(pdf·hwpx·hwp)를 창에 끌어다 놓거나 [보고서 찾기]를 누르세요. 지표별 수행 내역이 "
                           "보고서에 있는지 보고, 빠진 지표는 [가이드 폴더 만들기]로 기관 담당자에게 전달할 보완 자료를 모아 줍니다.")

        bar = Card()
        row = QHBoxLayout()
        row.addWidget(label("사업", "muted"))
        self.project = QComboBox()
        self.project.setMinimumWidth(200)
        self.project.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.project.setMinimumContentsLength(12)
        self.project.currentIndexChanged.connect(self._project_changed)
        self.manual = False   # 사람이 직접 고른 사업이면 문서 사업명을 못 찾아도 그대로 둔다
        self.project.activated.connect(lambda *_: setattr(self, "manual", True))
        row.addWidget(self.project, 1)
        self.name = QComboBox()
        self.name.setEditable(True)
        self.name.lineEdit().setPlaceholderText("사업명 (사업유형 판정에 씁니다)")
        self.name.setVisible(False)
        self.name.lineEdit().textEdited.connect(lambda *_: setattr(self, "manual", True))
        row.addWidget(self.name, 1)
        self.pick = QPushButton("RFP 찾기" if order else "보고서 찾기")
        self.pick.setObjectName("secondary")
        self.pick.clicked.connect(self._pick)
        row.addWidget(self.pick)
        self.guide = None
        if not order:
            self.guide = QPushButton("가이드 폴더 만들기")
            self.guide.setObjectName("secondary")
            self.guide.setToolTip("보완이 필요한 지표만 폴더를 만들어 가이드 모음·제출 안내·증빙기준·사업단 예시 산출물을 넣고, "
                                  "이행점검 결과 엑셀도 같이 넣습니다.")
            self.guide.clicked.connect(self._make_guide)
            row.addWidget(self.guide)
        self.save = QPushButton("결과 엑셀 저장")
        self.save.setObjectName("primary")
        self.save.setToolTip("사업단 이행점검 결과 양식(사업 진단결과 · 보완 사항 · 지표별 상세). "
                             "같은 기관이면 발주·완료단계 점검이 한 파일에 모입니다.")
        self.save.clicked.connect(self._save)
        row.addWidget(self.save)
        bar.body.addLayout(row)
        self.info = label("", "muted", wrap=True)
        bar.body.addWidget(self.info)
        self.content.addWidget(bar)

        # 사업 정보(사업유형·금액)는 글이라 숫자 카드와 따로, 왼쪽 카드 하나에 두 줄로
        self.project_card = Card()
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.type_value, self.amount_value = label("", "infoValue", wrap=True), label("", "infoValue", wrap=True)
        self.amount_note = label("", "muted", wrap=True)
        for r, (title, value) in enumerate((("사업유형", self.type_value), ("금액", self.amount_value))):
            grid.addWidget(label(title, "muted"), r, 0, Qt.AlignVCenter)
            grid.addWidget(value, r, 1)
        grid.addWidget(self.amount_note, 2, 1)
        grid.setColumnStretch(1, 1)
        self.project_card.body.addLayout(grid)
        self.kpis = {n: Kpi(n) for n in ("대응 지표", "점검완료 예상", "보완필요 예상")}
        if not order:   # 완료단계는 품질·표준관리 통합시스템처럼 세부 기준 Y/N
            for key, title in (("대응 지표", "진단결과반영비율"), ("점검완료 예상", "Y (확인)"), ("보완필요 예상", "N (보완서류 필요)")):
                self.kpis[key].title.setText(title)
        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addWidget(self.project_card, 2)
        for kpi in self.kpis.values():
            cards.addWidget(kpi, 1)
        self.content.addLayout(cards)
        self.portal = None
        self.sel_code = ""
        if not order:
            # 사업 진단결과 (품질·표준관리 통합시스템 '사업 완료단계 진단결과' 양식: 사업명 + 기준 18개 Y/N/- + 비율)
            self.portal = PortalTable((targets.criteria or report.load_criteria()).details)
            self.portal.picked.connect(self._pick_criterion)
            self.content.addWidget(self.portal)
        self.table = TableBox(CHECK_HEADERS, flag_label="보완필요만 보기")   # 발주단계 (완료는 세부기준이 없을 때만)
        self.table.wrap({5: 300, 7: 360})   # 근거·의견은 길어도 다 보이게
        self.table.view.setMinimumHeight(220)
        self.table.view.selectionModel().selectionChanged.connect(self._selected)
        self.content.addWidget(self.table, 1)

        self.detail = Card()
        head = QHBoxLayout()
        self.detail_title = label("", "sectionTitle")
        self.detail_title.setWordWrap(True)
        head.addWidget(self.detail_title, 1)
        self.badge = Badge()
        head.addWidget(self.badge)
        self.copy = QPushButton("문안 복사")
        self.copy.setObjectName("secondary")
        self.copy.clicked.connect(self._copy)
        head.addWidget(self.copy)
        self.detail.body.addLayout(head)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(180)
        self.detail.body.addWidget(self.text)
        self.html = QTextBrowser()   # 완료단계 기준 설명 (누락 이유 · 근거 · 필요 산출물 · 인정 산출물)
        self.html.setObjectName("criterionText")
        self.html.setOpenLinks(False)
        self.html.setMinimumHeight(300)
        self.html.setVisible(False)
        self.detail.body.addWidget(self.html)
        self.content.addWidget(self.detail, 1)
        _tidy(self, bar)
        targets.changed.connect(self._fill_projects)
        self._fill_projects()
        self._render()

    # --- 사업 고르기 --------------------------------------------------------------

    def _fill_projects(self):
        """대상 사업 화면의 관리 기관 사업 (이 단계·대응 필요 사업 먼저)."""
        current = self.project.currentText()
        stage = pv.ORDER if self.kind == "발주" else pv.DONE
        mine = [j for j in self.targets.judgements if j.managed and j.project.stage != pv.C_OUT]
        mine.sort(key=lambda j: (j.project.stage != stage, not j.project.needs_action, j.project.org, j.project.name))
        self.options = mine
        self.project.blockSignals(True)
        self.project.clear()
        for j in mine:
            free = "" if j.project.needs_action else " · 대응 불필요"
            self.project.addItem(f"{j.project.stage_label} · {j.project.org} · {j.project.name}{free}")
        self.project.addItem(OTHER)
        index = self.project.findText(current)
        self.project.setCurrentIndex(index if index >= 0 else 0)
        self.project.blockSignals(False)
        self._project_changed()

    def _judgement(self):
        i = self.project.currentIndex()
        return self.options[i] if 0 <= i < len(self.options) else None

    def _project_changed(self, *_):
        self.name.setVisible(self._judgement() is None)

    def _criteria(self):
        if self.targets.criteria is None:
            self.targets.criteria = report.load_criteria()
        return self.targets.criteria

    def _types_items(self, amount):
        """(유형, 대응, 금액 확인 후, 판정) — 고른 사업의 판정, 목록에 없으면 직접 적은 사업명으로."""
        criteria = self._criteria()
        j = self._judgement()
        if j:
            types, transfer, amount = j.types, j.transfer, j.amount or amount
        else:
            name = self.name.currentText()
            types, transfer = pv.classify(name, criteria)[0], pv.guess_transfer(name, criteria)[0]
        required, maybe, _ = pv.items_for(types, amount, transfer, criteria)
        return types, required, maybe, j

    # --- 파일 ----------------------------------------------------------------------

    def accepts(self, paths: list) -> bool:
        if self.kind == "발주":
            return len(paths) == 1 and Path(paths[0]).suffix.lower() in (".hwpx", ".hwp")
        return bool(paths) and all(Path(p).is_file() and Path(p).suffix.lower() in SUFFIXES for p in paths)

    def drop_files(self, paths: list):
        self.run(paths)

    def _pick(self):
        if self.kind == "발주":
            path, _ = QFileDialog.getOpenFileName(self, "RFP", str(Path.home()), "한글 문서 (*.hwpx *.hwp)")
            if path:
                self.run([path])
        else:
            paths, _ = QFileDialog.getOpenFileNames(self, "완료·감리보고서", str(Path.home()), "보고서 (*.pdf *.hwpx *.hwp)")
            if paths:
                self.run(paths)

    def run(self, paths: list):
        try:
            if self.kind == "발주":
                paras = read_document(paths[0])
                self._pick_project([pc.find_project_name(paras)], paths)
                self._run_order(paths[0], paras)
            else:
                docs, files = self._read_done(paths)
                self._pick_project([pc.find_project_name(p) for _, p in docs], paths)
                self._run_done(docs, files)
        except DocumentError as e:
            QMessageBox.warning(self, self.drop_label, str(e))
            return
        self.source = ", ".join(Path(p).name for p in paths)
        self.sel_code = ""   # 새 보고서는 첫 N 기준부터
        self.record = self._record()
        try:
            store.save_check(self.record)   # 기관별 이행점검 결과 엑셀에 모인다
        except Exception:   # 기록을 못 남겨도 점검 결과는 보여 준다
            pass
        self._render()

    def _record(self) -> dict:
        """이번 점검의 기록. 목록에 없는 사업은 지금 읽은 사업단 파일의 마지막 회차(없으면 자체점검)로 남긴다."""
        j = self._judgement()
        if j:
            year, no = j.project.year, j.project.round
        else:
            latest = max(((p.year, p.round) for p in self.targets.projects), default=(date.today().year, 0))
            year, no = latest
        return report.check_record(self.check, j, self.name.currentText().strip() or self.source, year, no,
                                   self._criteria())

    def _records(self) -> list:
        """같은 기관의 그 평가연도 점검 기록 — 발주·완료를 한 파일로 (이번 점검 포함). 기관을 모르면 이번 점검만."""
        r = self.record
        if not r["org_key"]:
            return [r]
        try:
            return store.load_checks(r["org_key"], r["year"]) or [r]
        except Exception:
            return [r]

    def _pick_project(self, doc_names: list, paths: list):
        """문서의 사업명(없으면 파일·폴더 이름)으로 사업을 고른다. 위에서 고른 사업과 다르면 문서 쪽으로 바꾼다.
        목록에 없으면 '목록에 없는 사업'으로 두고 문서 사업명으로 유형을 판정한다."""
        doc_names = [n for n in doc_names if n]
        stems = [Path(p).stem for p in paths]
        found = pc.match_project(doc_names + stems, [j.project.name for j in self.options])
        self.matched = doc_names[0] if doc_names else ""
        if found is not None:
            self.project.setCurrentIndex(found)
            self.match_note = f"문서 사업명 '{self.matched}' → 대상 사업에서 찾음" if self.matched else "파일 이름으로 대상 사업에서 찾음"
        elif doc_names or not self.manual:   # 앞 문서로 자동으로 골라진 사업은 다음 문서에 이어 쓰지 않는다
            self.project.setCurrentIndex(self.project.count() - 1)   # 목록에 없는 사업
            self.name.setCurrentText(doc_names[0] if doc_names else stems[0])
            self.match_note = (f"대상 사업 목록에 없는 사업 · 문서 사업명 '{doc_names[0]}'으로 유형 판정" if doc_names
                               else "문서에서 사업명을 찾지 못해 파일 이름으로 유형 판정")
        else:
            self.match_note = "문서에서 사업명을 찾지 못해 직접 고른 사업으로 점검"
        self.manual = False

    def _run_order(self, path, paras):
        amount = pc.find_amount(paras)[0]
        self._remember_amount(amount)
        types, required, maybe, _ = self._types_items(amount)
        self.check = pc.check_order(paras, Path(path).name, types, required, maybe, self._criteria(), amount)

    def _read_done(self, paths) -> tuple:
        docs, files = [], []
        for p in map(Path, paths):
            for f in (sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]):
                if f.name.startswith("~$"):
                    continue
                files.append(str(f))
                if f.suffix.lower() in SUFFIXES:
                    try:
                        docs.append((f.name, read_document(f)))
                    except DocumentError:
                        pass   # 그림뿐인 pdf 등은 파일 이름으로만 본다
        return docs, files

    def _run_done(self, docs, files):
        j = self._judgement()
        if j and j.amount:   # RFP에서 읽어 둔 사업 금액이 먼저
            found = (j.amount, "")
        else:
            found = next(((amount, f"{name} {where}") for name, paras in docs
                          for amount, where, _ in [pc.find_amount(paras, strict=True)] if amount), (None, ""))
            self._remember_amount(found[0])
        types, required, maybe, _ = self._types_items(found[0])
        self.codes = (required, maybe)
        self.check = pc.check_done(docs, files, required, maybe, self._criteria(), types)
        self.check.amount, self.check.amount_where = found

    def _remember_amount(self, amount):
        """문서에서 읽은 금액을 이 사업 금액으로 남긴다 (이미 있으면 그대로). 대상 사업 화면의 지표도 다시 계산된다."""
        j = self._judgement()
        if j and amount and not j.amount:
            edit = store.load_edits().get(j.project.key) or pv.Edit()
            edit.amount = amount
            store.save_edit(j.project.key, edit)
            j.amount = amount
            QTimer.singleShot(0, self.targets._judge)

    # --- 그리기 --------------------------------------------------------------------

    def _render(self):
        has = self.check is not None
        self.empty.setVisible(not has)
        portal = has and self.portal is not None and bool(self.check.criteria)
        for w in (self.table, self.detail, self.project_card, *self.kpis.values()):
            w.setVisible(has)
        self.table.setVisible(has and not portal)
        if self.portal:
            self.portal.setVisible(portal)
        self.html.setVisible(portal)
        self.text.setVisible(not portal)
        self.badge.setVisible(portal)
        self.save.setEnabled(has)
        if self.guide:
            self.guide.setEnabled(has)
        if not has:
            self.info.setText("사업을 고른 뒤 파일을 넣으세요. 사업유형·대응 지표는 대상 사업 화면의 판정을 씁니다.")
            return
        c, j = self.check, self._judgement()
        criteria = self._criteria()
        types = j.types if j else pv.classify(self.name.currentText(), criteria)[0]
        amount = c.amount or (j.amount if j else None)
        text = f"<b>{self.source}</b> · {self.match_note}"
        if c.amount_where:
            text += f" · 금액 위치 {c.amount_where}"
        if self.kind == "발주":
            text += f" · RFP 요구사항 {len(c.requirements)}개 (DAR {sum(r.is_data for r in c.requirements)}개)"
        self.info.setText(text)
        self.type_value.setText(" + ".join(types))
        basis = "·".join(sorted({b[3] for t in types for b in criteria.bands.get(t, [])}))
        bands = " / ".join(dict.fromkeys((f"{t} " if len(types) > 1 else "")
                                         + ", ".join(map(_short_band, pv.bands_for(t, amount, criteria))) for t in types))
        if amount:
            self.amount_value.setText(f"{pv.won_text(amount)}  ({basis})" if basis else pv.won_text(amount))
            self.amount_note.setText(f"금액구간: {bands}")
        else:
            self.amount_value.setText("모름")
            self.amount_note.setText("RFP를 발주단계 점검에 넣으면 채워집니다" if self.kind == "완료" else "RFP에서 사업비를 찾지 못했습니다")
        if self.kind == "완료" and c.criteria:
            self._render_details()
            return
        marks = [report.portal_mark(r) for r in c.results]
        self.kpis["대응 지표"].number.set(f"{len(c.results)}", "개")
        self.kpis["점검완료 예상"].number.set(f"{marks.count(report.PORTAL_OK)}", "개")
        self.kpis["보완필요 예상"].number.set(f"{marks.count(report.PORTAL_FIX)}", "개")
        rows = [(r.code, r.name, r.need, r.status, m, r.evidence, r.where, r.comment.split("\n")[0])
                for r, m in zip(c.results, marks)]
        self.table.set_rows(rows, [None if m == report.PORTAL_OK else "warn" for m in marks], empty="대응 지표가 없습니다.")
        if rows:
            self.table.view.selectRow(next((i for i, m in enumerate(marks) if m == report.PORTAL_FIX), 0))
        self._selected()

    def _render_details(self):
        """완료단계: 품표 양식 사업 진단결과(사업명 + 기준 18개 Y/N/- + 진단결과반영비율). 고른 기준의 설명은 아래 카드."""
        c = self.check
        ratio = c.ratio()
        ratio_text = "-" if ratio is None else f"{ratio:.0%}"
        statuses = [d.status for d in c.criteria]
        self.kpis["대응 지표"].number.set(ratio_text, "")
        self.kpis["점검완료 예상"].number.set(f"{statuses.count('Y')}", "개")
        self.kpis["보완필요 예상"].number.set(f"{statuses.count('N')}", "개")
        codes = [d.code for d in c.criteria]
        if self.sel_code not in codes:   # 처음엔 첫 N (없으면 첫 Y)
            self.sel_code = next((d.code for d in c.criteria if d.status == "N"),
                                 next((d.code for d in c.criteria if d.status == "Y"), codes[0] if codes else ""))
        r = self.record or {}
        name, org = r.get("name") or self.name.currentText(), r.get("org", "")
        title = f"<b>{_esc(name)}</b>" + (f"<br><span style='color:{theme.MUTED}; font-size:12px'>{_esc(org)}</span>"
                                          if org else "")
        self.portal.show_check(title, c.criteria, ratio_text, self.sel_code)
        self._show_criterion()

    def _pick_criterion(self, code: str):
        self.sel_code = code
        self._render_details()

    def _dash_reason(self, d, detail) -> str:
        required, maybe = self.codes
        if d.covered_by:
            return (f"같은 지표의 {d.covered_by}이(가) Y라서 이 기준은 보지 않습니다. "
                    "지표마다 (1)·(2) 중 하나만 충족하면 됩니다.")
        if d.item not in required + maybe:
            return "이 사업의 사업유형·금액구간·이관 여부로는 대응 지표가 아니어서 점검하지 않습니다 (매뉴얼 3.2.1.3)."
        if detail and "전체" in detail.skip_types:
            return ("기본값을 '-'로 두었습니다. 개방 대상 데이터가 있는 사업이면 위 [Y]/[N]으로 고치세요 "
                    "(사업단도 사업마다 '-' 또는 N으로 다르게 봅니다).")
        j = self._judgement()
        types = j.types if j else []
        skip = [t for t in types if detail and t in detail.skip_types]
        return f"{', '.join(skip) or '이 사업유형'} 사업은 이 기준을 보지 않습니다."

    def _show_criterion(self):
        """고른 기준 하나의 판단: 결과 배지 · 누락 이유(N) / 확인 근거(Y) / 해당 없음 이유(-) · 필요 산출물 · 인정 산출물."""
        d = next((x for x in self.check.criteria if x.code == self.sel_code), None) if self.check else None
        self.detail.setVisible(d is not None)
        if d is None:
            return
        criteria = self._criteria()
        detail = next((x for x in criteria.details if x.code == d.code), None)
        item = criteria.items.get(d.item)
        self.copy.setVisible(False)
        area = report.PORTAL_ITEM.get(d.item, item.name if item else "")
        self.detail_title.setText(f"{d.code} {area} — {d.text}")
        text, kind = STATUS_TEXT.get(d.status, (d.status, "neutral"))
        self.badge.set(text, kind)
        parts = []
        if d.status == "N":
            parts.append(_section("누락된 이유", theme.KINDS["error"][0], _esc(d.opinion or "수행 내역을 찾지 못했습니다.")))
            how = []
            if detail and detail.words:
                how.append(f"보고서의 데이터 관련 문장에서 {_esc(_words(detail.words))} 같은 말을 찾지 못했습니다.")
            if detail and detail.file_words:
                how.append(f"넣은 파일 이름에도 {_esc(_words(detail.file_words))} 이(가) 들어간 산출물이 없습니다.")
            if "예시 양식" in d.opinion:
                how.append("예시 양식 파일만 있어서 인정하지 않았습니다 (이 사업 내용으로 채운 산출물이 필요합니다).")
            if how:
                parts.append(_section("프로그램이 확인한 내용", theme.MUTED, "<br>".join(how)))
            if d.needed:
                parts.append(_section("필요 산출물", theme.TEXT, _esc(d.needed)))
        elif d.status == "Y":
            body = f"<b>{_esc(d.where)}</b><br>{_esc(d.evidence)}" if d.where else _esc(d.evidence)
            parts.append(_section("확인된 근거", theme.KINDS["success"][0], body))
        else:
            parts.append(_section("해당 없음 이유", theme.MUTED, _esc(self._dash_reason(d, detail))))
        if item and d.status != "-":
            evidence = _esc(item.evidence).replace("\n", "<br>")
            parts.append(_section(f"{item.code} {item.name} — 인정되는 산출물 (①·② 중 택1)", theme.TEXT, evidence))
            if item.screen and d.status == "N":
                parts.append(_section("stdtool에서 만들 수 있는 화면", theme.ACCENT_DARK, _esc(item.screen)))
        self.html.setHtml("".join(parts))

    def _selected(self, *_):
        rows = self.table.view.selectionModel().selectedRows() if self.check else []
        if not rows:
            self.detail.setVisible(False)
            return
        self.detail.setVisible(True)
        r = self.check.results[self.table.proxy.mapToSource(rows[0]).row()]
        s = r.suggestion if r.status != pc.DONE_OK else None
        self.copy.setVisible(bool(s))
        if s:
            self.detail_title.setText(f"{r.code} {r.name} — 넣을 요구사항 문안 (매뉴얼 3.2.2 {s.kind} {s.band})")
            self.text.setPlainText(f"요구사항 고유번호: {s.rid}\n요구사항 명칭: {s.name}\n정의: {s.definition}\n세부내용:\n{s.detail}\n"
                                   f"산출정보: {s.output}")
        elif self.kind == "발주":
            self.detail_title.setText(f"{r.code} {r.name}")
            self.text.setPlainText(f"RFP {r.where}: {r.evidence}" if r.where else r.comment)
        else:
            item = self._criteria().items[r.code]
            self.detail_title.setText(f"{r.code} {r.name} — 인정되는 산출물 (①·② 중 택1)")
            found = f"찾은 근거: {r.where} · {r.evidence}\n\n" if r.evidence else (r.comment.split("\n")[0] + "\n\n")
            screen = f"\n\nstdtool에서 만들 수 있는 화면: {item.screen}" if item.screen else ""
            self.text.setPlainText(found + item.evidence + screen)

    def _copy(self):
        QGuiApplication.clipboard().setText(self.text.toPlainText())
        self.copy.setText("복사됨")
        QTimer.singleShot(1500, lambda: self.copy.setText("문안 복사"))

    def _save(self):
        if not self.check:
            return
        r, records = self.record, self._records()
        name = report.inspection_name(r["org"], r["name"], [x["round"] for x in records])
        path, _ = QFileDialog.getSaveFileName(self, "이행점검 결과 엑셀 저장", str(Path(self.output_dir or Path.home()) / name),
                                              "엑셀 (*.xlsx)")
        if not path:
            return
        try:
            written = report.write_inspection(records, self._criteria(), Path(path))
        except PermissionError:
            QMessageBox.warning(self, "결과 엑셀", "파일을 쓸 수 없습니다. 엑셀에서 열어 두었다면 닫고 다시 저장하세요.")
            return
        kinds = "·".join(dict.fromkeys(x["kind"] for x in records))
        others = f"\n(이 기관의 {kinds} 점검 {len(records)}건이 한 파일에 들어갔습니다)" if len(records) > 1 else ""
        if QMessageBox.question(self, "결과 엑셀", f"저장했습니다.\n{written}{others}\n\n열어 볼까요?") == QMessageBox.Yes:
            open_path(written)

    def _make_guide(self):
        if not self.check:
            return
        base = QFileDialog.getExistingDirectory(self, "가이드 폴더를 만들 곳", str(Path(self.output_dir or Path.home())))
        if not base:
            return
        r = self.record
        records = self._records()
        try:
            folder = report.build_guide_folder(r, self._criteria(), Path(base))
            report.write_inspection(records, self._criteria(),
                                    folder / report.inspection_name(r["org"], r["name"], [x["round"] for x in records]))
        except ValueError as e:   # 보완할 지표가 없음
            QMessageBox.information(self, "가이드 폴더", str(e))
            return
        except OSError as e:
            QMessageBox.warning(self, "가이드 폴더", f"만들지 못했습니다.\n{e}")
            return
        fixes = [x["code"] for x in r["results"] if x["mark"] == report.PORTAL_FIX]
        if QMessageBox.question(self, "가이드 폴더", f"보완이 필요한 지표 {len(fixes)}개({', '.join(fixes)})의 폴더를 만들었습니다.\n"
                                f"{folder}\n\n폴더를 열까요?") == QMessageBox.Yes:
            open_path(folder)

    def show_outcome(self, outcome, settings):
        self.empty.setVisible(self.check is None)
