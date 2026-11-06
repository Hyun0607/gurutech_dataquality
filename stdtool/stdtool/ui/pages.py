"""지표별 화면. 각 화면은 show_outcome(outcome, settings)로 실행 결과를 받아 그린다."""
import os
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QMessageBox, QPushButton, QScrollArea,
                               QStyledItemDelegate, QTabWidget, QVBoxLayout, QWidget)

from ..core.currency import CODES as CURRENCY_CODES, code_label as currency_label
from ..core.precheck import (CODES, COUNTED, STANDARD1, STANDARD_GROUPS, code_label, group, group_headers, issue_row,
                              severity, short_group)
from ..workbook.reader import meta_systems
from .widgets import Badge, BigNumber, Card, EmptyState, Kpi, RateBar, TableBox, hbox, label

EMPTY = "메타 파일을 고르거나 창에 끌어다 놓고 ▶ 실행을 누르면 결과가 여기에 나옵니다."


def open_path(path) -> None:
    os.startfile(str(path))   # Windows: 연결된 프로그램(엑셀·탐색기)으로 연다


class Page(QScrollArea):
    """스크롤되는 화면. content에 위젯을 쌓는다."""
    navigate = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        inner.setObjectName("page")
        self.content = QVBoxLayout(inner)
        self.content.setContentsMargins(32, 8, 32, 32)
        self.content.setSpacing(16)
        self.setWidget(inner)
        self.empty = EmptyState(EMPTY)
        self.content.addWidget(self.empty)

    def show_outcome(self, outcome, settings):
        self.empty.setVisible(outcome is None)


def _month_day(text: str) -> str:
    m, d = (int(x) for x in text.split("-"))
    return f"{m}월 {d}일"


def _score(value) -> str:
    return f"{value:g}"


# ---------------------------------------------------------------------------
# 요약
# ---------------------------------------------------------------------------

class SummaryPage(Page):
    def __init__(self):
        super().__init__()
        self.info = Card()
        self.info.body.addWidget(label("시스템 정보", "sectionTitle"))
        self.info_grid = QGridLayout()
        self.info_grid.setHorizontalSpacing(24)
        self.info_grid.setVerticalSpacing(6)
        self.info.body.addLayout(self.info_grid)
        self.content.addWidget(self.info)

        self.cards = QWidget()
        grid = QGridLayout(self.cards)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)

        self.define = Card("표준 정의", "2-1-3-1", clickable=True)
        self.define_rows = {}
        for area in ("도메인", "용어", "단어"):
            row = QHBoxLayout()
            name = label(area)
            badge = Badge("—")
            row.addWidget(name)
            row.addStretch(1)
            row.addWidget(badge)
            self.define.body.addLayout(row)
            self.define_rows[area] = (name, badge)
        self.define_note = label("", "muted", wrap=True)
        self.define.body.addWidget(self.define_note)
        self.define.clicked.connect(lambda: self.navigate.emit("define"))

        self.apply, self.apply_num, self.apply_bar, self.apply_note = self._rate_card("표준 적용률", "2-1-3-2", "apply")
        self.cur, self.cur_num, self.cur_bar, self.cur_note = self._rate_card("구조 현행화", "2-1-4-2", "currency")
        self.link, self.link_num, self.link_bar, self.link_note = self._rate_card("연계", "2-1-5-1·2", "link", warn=True)
        for i, card in enumerate((self.define, self.apply, self.cur, self.link)):
            grid.addWidget(card, 0, i)
            grid.setColumnStretch(i, 1)
        self.content.addWidget(self.cards)

        lower = QHBoxLayout()
        lower.setSpacing(16)
        self.todo = Card()
        self.todo.body.addWidget(label("확인할 항목", "sectionTitle"))
        self.todo_list = QVBoxLayout()
        self.todo_list.setSpacing(2)
        self.todo.body.addLayout(self.todo_list)
        self.todo.body.addStretch(1)
        lower.addWidget(self.todo, 3)

        self.files = Card()
        head = QHBoxLayout()
        head.addWidget(label("산출물", "sectionTitle"))
        head.addStretch(1)
        self.open_folder = QPushButton("폴더 열기")
        self.open_folder.setObjectName("link")
        head.addWidget(self.open_folder)
        self.files.body.addLayout(head)
        self.file_list = QVBoxLayout()
        self.file_list.setSpacing(0)
        self.files.body.addLayout(self.file_list)
        self.files.body.addStretch(1)
        lower.addWidget(self.files, 2)
        self.lower = QWidget()
        self.lower.setLayout(lower)
        self.content.addWidget(self.lower)
        self.content.addStretch(1)
        self._folder = None
        self.open_folder.clicked.connect(lambda: self._folder and open_path(self._folder))
        self.show_outcome(None, None)

    def _rate_card(self, title, code, target, warn=False):
        card = Card(title, code, clickable=True)
        number = BigNumber("—", "%")
        bar = RateBar(warn)
        note = label("", "muted", wrap=True)
        card.body.addWidget(number)
        card.body.addWidget(bar)
        card.body.addWidget(note)
        card.clicked.connect(lambda: self.navigate.emit(target))
        return card, number, bar, note

    def show_outcome(self, outcome, settings):
        super().show_outcome(outcome, settings)
        for w in (self.info, self.cards, self.lower):
            w.setVisible(outcome is not None)
        if outcome is None:
            return
        r = outcome.result
        self._show_info(settings, meta_systems(r.meta))
        pre, cur = r.precheck, r.currency
        for area, total, errors, _, verdict in pre.completeness_rows():
            name, badge = self.define_rows[area]
            name.setText(f"{area} {total:,}건")
            kind = "success" if errors == 0 else "error" if verdict.startswith("전체") else "warn"
            badge.set("성공" if errors == 0 else f"오류 {errors:,}", kind)
        standard1 = sum(pre.count(c) for c in STANDARD1)
        self.define_note.setText(f"공통표준 준용 점검 {standard1:,}건" if standard1 else "공통표준 준용 점검 이상 없음")

        self.apply_num.set(f"{pre.rate:.1f}", "%")
        self.apply_bar.set_rate(pre.rate)
        self.apply_note.setText(f"오류 컬럼 {pre.error_columns:,} / {pre.total:,} ({pre.basis} 기준) · 예상 {_score(pre.score)} / 3점")
        self.cur_num.set(f"{cur.rate:.1f}", "%")
        self.cur_bar.set_rate(cur.rate)
        table, column = cur.rates[1], cur.rates[3]
        self.cur_note.setText(f"테이블 {table[1]}/{table[2]} · 컬럼 {column[1]}/{column[2]} · 예상 {_score(cur.score)} / 1점")
        chosen = next((c for c in outcome.candidates if c.selected), None)
        self.link_num.set("1" if chosen else "0", "행")
        self.link_bar.set_rate(100.0 if chosen else 0)
        self.link_note.setText(f"점검 결과 {settings.link_result} · 점검 일시 {_month_day(settings.link_start)}~오늘")

        _clear(self.todo_list)
        items = []
        counts = Counter(i.code for i in pre.issues)
        for code, n in counts.items():
            sev = severity(code)
            if sev in ("완전성 오류", "적용 오류", "공통표준 준용"):
                target = "apply" if code[0] in "CM" else "define"
                kind = {"완전성 오류": "error", "적용 오류": "error", "공통표준 준용": "neutral"}[sev]
                items.append((kind, code_label(code), f"{group(code)} {CODES[code]} {n:,}건", target))
        if outcome.fallback:
            tails = ", ".join(f"{t} {n}" for t, n, *_ in outcome.fallback[:3])
            items.append(("warn", "꼬리", f"Code_tail에 없어 문자값으로 분류된 컬럼 {sum(f[1] for f in outcome.fallback):,}개 — {tails}", "dict"))
        for code in CURRENCY_CODES:
            if cur.count(code):
                items.append(("error", currency_label(code), f"현행화 {CURRENCY_CODES[code]} {cur.count(code):,}건", "currency"))
        if not items:
            self.todo_list.addWidget(label("확인할 항목이 없습니다.", "muted"))
        for kind, code, text, target in items:
            self.todo_list.addWidget(self._todo_row(kind, code, text, target))

        _clear(self.file_list)
        self._folder = outcome.folder
        for path in outcome.paths:
            self.file_list.addWidget(self._file_row(Path(path)))

    def _show_info(self, settings, systems):
        """기관·시스템과 DB별 업무분류체계 (기관 메타시스템에 올릴 때 시스템별로 넣는 값)."""
        _clear(self.info_grid)
        heads = ["기관", "정보시스템", "DB (한글 · 영문)", "업무분류체계", ""]
        for c, text in enumerate(heads):
            self.info_grid.addWidget(label(text, "muted"), 0, c)
        for r, (kor, eng, biz) in enumerate(systems or [("", "", "")], 1):
            first = r == 1
            self.info_grid.addWidget(label(settings.org_name if first else ""), r, 0)
            self.info_grid.addWidget(label((settings.system_name or settings.db_name) if first else ""), r, 1)
            self.info_grid.addWidget(label(" · ".join(x for x in (kor, eng) if x) or "-"), r, 2)
            if biz:
                text = label(biz.replace(">", "  ›  "), "cardTitle", wrap=True)
                text.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self.info_grid.addWidget(text, r, 3)
                copy = QPushButton("복사")
                copy.setObjectName("link")
                copy.setToolTip(biz)
                copy.clicked.connect(lambda _=False, b=biz, w=copy: (QGuiApplication.clipboard().setText(b),
                                                                      w.setText("복사됨")))
                self.info_grid.addWidget(copy, r, 4)
            else:
                self.info_grid.addWidget(Badge("메타 파일 Q열(업무분류체계)이 비어 있습니다", "warn"), r, 3)
        self.info_grid.setColumnStretch(3, 1)

    def _todo_row(self, kind, code, text, target):
        box = QWidget()
        box.setMinimumHeight(32)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(12)
        chip = Badge(code, kind)
        chip.setMinimumWidth(84)
        row.addWidget(chip)
        row.addWidget(label(text, wrap=True), 1)
        go = QPushButton("보기")
        go.setObjectName("link")
        go.clicked.connect(lambda: self.navigate.emit(target))
        row.addWidget(go)
        return box

    def _file_row(self, path: Path):
        box = QWidget()
        box.setMinimumHeight(26)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 3, 0, 3)
        name = label(path.name)
        name.setToolTip(str(path))
        name.setMinimumWidth(0)
        row.addWidget(name, 1)
        button = QPushButton("열기")
        button.setObjectName("link")
        button.clicked.connect(lambda: open_path(path))
        row.addWidget(button)
        return box


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if widget := item.widget():
            widget.setParent(None)   # 지울 때까지 남아 겹쳐 보이지 않게 바로 뗀다
            widget.deleteLater()


# ---------------------------------------------------------------------------
# 표준 정의 (2-1-3-1)
# ---------------------------------------------------------------------------

class DefinePage(Page):
    """통합시스템 DB표준 점검 화면과 같은 묶음(완전성·공통표준 준용)과 오류명으로 보여 준다."""

    def __init__(self):
        super().__init__()
        self.body = QWidget()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        self.areas = {}
        cards = []
        for area in ("도메인", "용어", "단어"):
            card = Card(f"{area} 완전성")
            number = BigNumber("—", "건")
            badge = Badge("—")
            row = QHBoxLayout()
            row.addWidget(number, 1)
            row.addWidget(badge, 0, Qt.AlignBottom)
            card.body.addLayout(row)
            note = label("", "muted")
            card.body.addWidget(note)
            self.areas[area] = (number, badge, note)
            cards.append(card)
        lay.addLayout(hbox(*cards))
        lay.addWidget(label("완전성 점검(중복·형식 오류 등)이 일부라도 성공해야 하고, 전체가 오류면 해당 표준 정의 점수가 0점입니다. "
                            "탭과 오류명·오류상세내용은 품질·표준관리 통합시스템 점검 결과 화면과 같습니다. "
                            "'프로그램 추가 점검'은 통합시스템에 없는 점검(빈 값 등)입니다.", "muted", wrap=True))
        self.tabs = QTabWidget()
        self.tables = {}
        for name in STANDARD_GROUPS:
            box = TableBox(group_headers(name), flag_label=None)
            box.model.mono_cols = {2} if "용어" in name or "단어" in name else set()
            box.model.result_col = 4
            self.tables[name] = box
            self.tabs.addTab(box, short_group(name))
        lay.addWidget(self.tabs, 1)
        self.content.addWidget(self.body, 1)
        from .inst_panel import InstPanel   # 기관표준 점검 · A값: 메타 실행과 상관없이 늘 보인다
        self.inst = InstPanel()
        self.content.insertWidget(0, self.inst)
        self.show_outcome(None, None)

    def show_outcome(self, outcome, settings):
        super().show_outcome(outcome, settings)
        self.body.setVisible(outcome is not None)
        if outcome is None:
            return
        pre = outcome.result.precheck
        for area, total, errors, ok, verdict in pre.completeness_rows():
            number, badge, note = self.areas[area]
            number.set(f"{total:,}", "건")
            badge.set("성공" if errors == 0 else verdict, "success" if errors == 0 else
                      "error" if verdict.startswith("전체") else "warn")
            note.setText(f"오류 {errors:,}건 · 성공 {ok:,}건")
        r = outcome.result
        for n, (name, box) in enumerate(self.tables.items()):
            issues = [i for i in pre.issues if group(i.code) == name]
            box.set_rows([issue_row(i, r.domains, r.terms, r.words, name == "프로그램 추가 점검") for i in issues],
                         ["error" if severity(i.code) == "완전성 오류" else "warn" for i in issues],
                         empty="오류 없음 — 점검을 통과했습니다.")
            self.tabs.setTabText(n, f"{short_group(name)} {len(issues):,}" if issues else short_group(name))



# ---------------------------------------------------------------------------
# 적용률 (2-1-3-2)
# ---------------------------------------------------------------------------

COLUMN_HEADERS = ["행", "결과", "테이블", "영문컬럼명", "한글컬럼명", "타입", "길이", "표준용어", "도메인", "도메인 타입·길이"]


def _column_rows(rows):
    data, kinds = [], []
    for r in rows:
        result = ", ".join(f"{code_label(c)} {CODES[c]}" for c in r.codes) or "정상"
        dom = f"{r.domain_type}({r.domain_length})" if r.domain_type else ""
        data.append((r.row, result, r.table, r.eng, r.kor, r.data_type, r.length, r.term_kor, r.domain, dom))
        kinds.append("error" if any(c in COUNTED for c in r.codes) else "warn" if r.codes else None)
    return data, kinds


class ApplyPage(Page):
    def __init__(self):
        super().__init__()
        self.body = QWidget()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        self.kpis = [Kpi("예상 적용률"), Kpi("전체 컬럼"), Kpi("오류 컬럼"), Kpi("예상 배점")]
        lay.addLayout(hbox(*self.kpis))
        self.basis = label("", "muted", wrap=True)
        lay.addWidget(self.basis)
        self.tabs = QTabWidget()
        self.meta = TableBox(COLUMN_HEADERS)
        self.defs = TableBox(COLUMN_HEADERS)
        for box in (self.meta, self.defs):
            box.model.mono_cols = {3}
            box.model.result_col = 1
        self.tabs.addTab(self.meta, "메타 점검 · 적용률 산정")
        self.tabs.addTab(self.defs, "컬럼정의서 점검 · 참고")
        lay.addWidget(self.tabs, 1)
        self.content.addWidget(self.body, 1)
        self.show_outcome(None, None)

    def show_outcome(self, outcome, settings):
        super().show_outcome(outcome, settings)
        self.body.setVisible(outcome is not None)
        if outcome is None:
            return
        pre = outcome.result.precheck
        self.kpis[0].number.set(f"{pre.rate:.1f}", "%")
        self.kpis[1].number.set(f"{pre.total:,}", "")
        self.kpis[2].number.set(f"{pre.error_columns:,}", "")
        self.kpis[3].number.set(_score(pre.score), "/ 3")
        self.basis.setText(f"적용률 = (전체 컬럼 - 오류 컬럼) ÷ 전체 컬럼. 산정 기준: {pre.basis}. "
                           "영문약어명·데이터타입·데이터길이(메타에 길이가 있을 때)를 봅니다.")
        self.meta.set_rows(*_column_rows(pre.meta))
        self.defs.set_rows(*_column_rows(pre.columns))


# ---------------------------------------------------------------------------
# 사전 관리
# ---------------------------------------------------------------------------

class DictPage(Page):
    def __init__(self):
        super().__init__()
        self.body = QWidget()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        self.source = label("", "muted", wrap=True)
        lay.addWidget(self.source)
        self.tabs = QTabWidget()
        self.fallback = TableBox(["영문 꼬리", "컬럼 수", "한글컬럼명 예시", "영문컬럼명 예시", "같은 약어 공통표준단어",
                                  "형식단어", "공통표준 도메인분류"], flag_label=None)
        self.fallback.model.mono_cols = {0}
        self.tail = TableBox(["순번", "도메인자르기(꼬리)", "도메인분류", "도메인중분류"], flag_label=None)
        self.tail.model.mono_cols = {1}
        self.type = TableBox(["순번", "데이터 타입", "데이터 약어", "데이터 분류"], flag_label=None)
        self.type.model.mono_cols = {1, 2}
        self.tabs.addTab(self.fallback, "문자값으로 빠진 꼬리")
        self.tabs.addTab(self.tail, "Code_tail")
        self.tabs.addTab(self.type, "Code_type")
        lay.addWidget(self.tabs, 1)
        self.content.addWidget(self.body, 1)
        self.show_outcome(None, None)

    def show_outcome(self, outcome, settings):
        super().show_outcome(outcome, settings)
        self.body.setVisible(outcome is not None)
        if outcome is None:
            return
        dicts = outcome.result.namer.dicts
        where = f"DB {settings.db.database}" if settings.db.use else Path(settings.macro_workbook).name
        self.source.setText(f"표준 사전: {where}. 꼬리·타입을 추가하려면 DB의 code_tail·code_type 에 행을 넣으세요 "
                            "(sql/code_additions.sql 방식). 화면에서 추가하는 기능은 다음 단계에서 붙입니다.")
        self.fallback.set_rows(outcome.fallback)
        self.tail.set_rows([r[:4] for r in dicts.code_tail.rows])
        self.type.set_rows([r[:4] for r in dicts.code_type.rows])
        self.tabs.setTabText(0, f"문자값으로 빠진 꼬리 {len(outcome.fallback)}")
        self.tabs.setTabText(1, f"Code_tail {len(dicts.code_tail.rows)}")
        self.tabs.setTabText(2, f"Code_type {len(dicts.code_type.rows)}")


# ---------------------------------------------------------------------------
# 구조 2-1-4-1 데이터 구조 정의
# ---------------------------------------------------------------------------

class StructurePage(Page):
    """프로그램이 만든 테이블·컬럼 정의서와 테이블관계정의서(물리 ERD 대체)를 본다. DB 정의서는 따로 등록."""
    files_written = Signal(list)

    def __init__(self):
        super().__init__()
        self.outcome = self.settings = None
        self._busy = False
        self.body = QWidget()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        self.kpis = {name: Kpi(name) for name in ("테이블", "컬럼", "테이블 관계", "길이 확인 필요", "중복으로 지운 컬럼")}
        lay.addLayout(hbox(*self.kpis.values()))
        lay.addWidget(label("데이터 구조 정의는 DB 정의서·테이블 정의서·컬럼 정의서·물리 ERD(또는 테이블 관계정의서)를 "
                            "실제 DB 구조대로 통합시스템에 등록했는지 봅니다. 여기서는 프로그램이 만든 테이블·컬럼 정의서와 "
                            "테이블관계정의서(물리 ERD가 없을 때)를 보여 줍니다. DB 정의서는 따로 등록하세요.", "muted", wrap=True))
        self.tabs = QTabWidget()
        self.tables = TableBox(["영문테이블명", "한글테이블명", "컬럼 수", "확인"], flag_label="확인할 것만 보기")
        self.tables.model.mono_cols = {0}
        self.columns = TableBox(["테이블", "한글컬럼명", "영문컬럼명", "타입", "길이", "확인"], flag_label="확인할 것만 보기")
        self.columns.model.mono_cols = {0, 2}
        self.removed = TableBox(["테이블", "한글컬럼명", "영문컬럼명", "타입", "길이", "메타 행"], flag_label=None)
        self.removed.model.mono_cols = {0, 2}
        self.relations = TableBox(["제외", "부모 테이블", "부모 한글명", "부모 컬럼", "자식 테이블", "자식 한글명", "자식 컬럼",
                                   "근거"], flag_label="제외만 보기")
        self.relations.model.check_col = 0
        self.relations.model.mono_cols = {1, 3, 4, 6}
        self.relations.model.checked_changed.connect(self._sync_relations)
        relation_tab = QWidget()
        rl = QVBoxLayout(relation_tab)
        rl.setContentsMargins(0, 8, 0, 0)
        head = QHBoxLayout()
        note = label("정의서에 PK·FK가 없어 컬럼 이름으로 부모·자식을 짐작했습니다 (같은 키 컬럼을 가진 테이블 중 이름이 맞는 쪽이 "
                     "부모). 틀린 관계는 체크해서 빼고 '관계정의서 만들기'를 누르세요. 빠진 관계는 만든 파일에 직접 적습니다.",
                     "muted", wrap=True)
        note.setMinimumWidth(0)
        head.addWidget(note, 1)
        self.make_relations = QPushButton("관계정의서 만들기")
        self.make_relations.setObjectName("primary")
        self.make_relations.clicked.connect(self._make_relations)
        head.addWidget(self.make_relations)
        rl.addLayout(head)
        rl.addWidget(self.relations, 1)
        for box, name in ((self.tables, "테이블정의서"), (self.columns, "컬럼정의서"), (relation_tab, "테이블관계정의서"),
                          (self.removed, "중복으로 지운 컬럼")):
            self.tabs.addTab(box, name)
        lay.addWidget(self.tabs, 1)
        self.content.addWidget(self.body, 1)
        self.show_outcome(None, None)

    def show_outcome(self, outcome, settings):
        super().show_outcome(outcome, settings)
        self.body.setVisible(outcome is not None)
        self.outcome, self.settings = outcome, settings
        if outcome is None:
            return
        from ..model import col
        d = outcome.result.definitions
        per_table = Counter(str(c[col("A")]).upper() for c in d.columns)
        t_rows, t_kinds = [], []
        for t in d.tables:
            eng, kor = t[col("C")], t[col("B")]
            note = "한글테이블명 없음" if not kor else "컬럼 없음" if not per_table[str(eng).upper()] else ""
            t_rows.append((eng, kor, per_table[str(eng).upper()], note))
            t_kinds.append("warn" if note else None)
        self.tables.set_rows(t_rows, t_kinds)
        c_rows, c_kinds = [], []
        for i, c in enumerate(d.columns):
            note = "길이 0 (실제 DB 길이 확인)" if i in d.zero_length_rows else ""
            c_rows.append((c[col("A")], c[col("B")], c[col("C")], c[col("G")], c[col("H")], note))
            c_kinds.append("warn" if note else None)
        self.columns.set_rows(c_rows, c_kinds)
        self.removed.set_rows([r[:6] for r in d.removed], empty="없음 — 같은 테이블에 같은 컬럼이 두 번 나온 곳이 없습니다.")
        info, kor = outcome.relation_info
        self._busy = True
        self.relations.set_rows([("", r.parent, info.get(r.parent.upper(), ("", "", ""))[2], r.parent_column, r.child,
                                  info.get(r.child.upper(), ("", "", ""))[2], r.child_column, r.basis)
                                 for r in outcome.relations], None, [not r.use for r in outcome.relations],
                                empty="이름으로 짐작할 수 있는 관계가 없습니다. 만든 파일에 직접 적으세요.")
        self._busy = False
        for name, value in (("테이블", len(d.tables)), ("컬럼", len(d.columns)),
                            ("길이 확인 필요", len(d.zero_length_rows)), ("중복으로 지운 컬럼", len(d.removed))):
            self.kpis[name].number.set(f"{value:,}", "개")
        self._count_relations()
        self.tabs.setTabText(3, f"중복으로 지운 컬럼 {len(d.removed):,}" if d.removed else "중복으로 지운 컬럼")

    def _sync_relations(self, *_):
        if self._busy or self.outcome is None:
            return
        for r, checked in zip(self.outcome.relations, self.relations.model.checks):
            r.use = not checked
        self._count_relations()

    def _count_relations(self):
        used = sum(1 for r in self.outcome.relations if r.use)
        self.kpis["테이블 관계"].number.set(f"{used:,}", "개")
        self.tabs.setTabText(2, f"테이블관계정의서 {used:,}")

    def _make_relations(self):
        from ..service import export_relation_file
        try:
            path = export_relation_file(self.outcome, self.settings)
        except PermissionError as e:
            QMessageBox.warning(self, "테이블관계정의서", f"파일을 쓸 수 없습니다. 엑셀에서 열려 있으면 닫고 다시 누르세요.\n{e}")
            return
        QMessageBox.information(self, "테이블관계정의서", f"만들었습니다.\n{Path(path).name}")
        self.files_written.emit([path])


# ---------------------------------------------------------------------------
# 구조 2-1-4-2 데이터 구조 현행화
# ---------------------------------------------------------------------------

class CurrencyPage(Page):
    def __init__(self):
        super().__init__()
        self.body = QWidget()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        top = QHBoxLayout()
        top.setSpacing(16)
        main = Card("구조 산출물 현행화율", "가장 낮은 값")
        self.rate = BigNumber("—", "%")
        self.score = label("", "muted", wrap=True)
        main.body.addWidget(self.rate)
        main.body.addWidget(self.score)
        main.body.addStretch(1)
        top.addWidget(main, 1)
        bars = Card("현행화율 4가지", "정의서 ↔ 수동등록")
        self.bars = []
        for _ in range(4):
            head = QHBoxLayout()
            name, value = label(""), label("", "muted")
            head.addWidget(name)
            head.addStretch(1)
            head.addWidget(value)
            bar = RateBar()
            bars.body.addLayout(head)
            bars.body.addWidget(bar)
            self.bars.append((name, value, bar))
        top.addWidget(bars, 2)
        lay.addLayout(top)
        self.table = TableBox(["대상", "행", "결과", "영문테이블명", "영문컬럼명", "타입", "길이", "상대 타입", "상대 길이"],
                              flag_label="불일치만 보기")
        self.table.model.mono_cols = {3, 4}
        self.table.model.result_col = 2
        lay.addWidget(self.table, 1)
        self.content.addWidget(self.body, 1)
        self.show_outcome(None, None)

    def show_outcome(self, outcome, settings):
        super().show_outcome(outcome, settings)
        self.body.setVisible(outcome is not None)
        if outcome is None:
            return
        cur = outcome.result.currency
        self.rate.set(f"{cur.rate:.1f}", "%")
        self.score.setText(f"예상 배점 {_score(cur.score)} / 1점 · 90% 이상 1점, 80% 이상 0.7점, 70% 이상 0.4점")
        for (name, value, bar), (title, matched, total, rate) in zip(self.bars, cur.rates):
            name.setText(title)
            value.setText(f"{matched:,} / {total:,} · {rate:.1f}%")
            bar.set_rate(rate)
        rows = cur.rows
        self.table.set_rows([(r.source, r.row, f"{currency_label(r.code)} {r.message}" if r.code else "일치", r.table, r.column,
                              r.data_type, r.length, r.other_type, r.other_length) for r in rows],
                            ["error" if r.code else None for r in rows])
        self.table.flag.setChecked(any(r.code for r in rows))


# ---------------------------------------------------------------------------
# 연계 2-1-5-1 연계데이터 관리 정보 정의, 2-1-5-2 송·수신 내역 관리
# ---------------------------------------------------------------------------

CYCLES = ["실시간", "매일", "매주", "매월", "분기", "수시"]
LINK_HEADERS = ["선택", "추천 사유", "테이블", "영문컬럼명", "한글컬럼명 (정보명)", "타입", "길이", "주기", "활용기관"]
COL_CYCLE, COL_USER = 7, 8
# 산출물 양식(templates/연계목록·연계현황)의 머리글
LIST_HEADERS = ["NO.", "송·수신 구분", "정보명", "주기", "항목명", "설명", "데이터 타입", "데이터 길이", "DB명", "테이블명",
                "컬럼명", "제공기관", "활용기관"]
STATUS_HEADERS = ["NO.", "연계시스템(DB)명", "송·수신구분", "연계명", "점검 일시", "연계주기", "점검 방법", "점검 결과",
                  "오류조치방안", "제공기관", "활용기관", "비고"]


def _make_link_files(page, outcome, settings) -> list | None:
    """2-1-5-1·2-1-5-2 파일을 다시 쓴다. 엑셀에서 열려 있으면 알리고 None."""
    from ..service import export_link
    try:
        paths = export_link(outcome, settings)
    except PermissionError as e:
        QMessageBox.warning(page, "연계", f"파일을 쓸 수 없습니다. 엑셀에서 열려 있으면 닫고 다시 누르세요.\n{e}")
        return None
    QMessageBox.information(page, "연계", "만들었습니다.\n" + "\n".join(Path(p).name for p in paths))
    return paths


class _ChoiceDelegate(QStyledItemDelegate):
    """칸을 두 번 누르면 목록에서 고르는 상자 (editable이면 직접 입력도)."""

    def __init__(self, choices: list, parent=None, editable: bool = True):
        super().__init__(parent)
        self.choices, self.editable = choices, editable

    def createEditor(self, parent, option, index):
        box = QComboBox(parent)
        box.setEditable(self.editable)
        box.addItems(self.choices)
        return box

    def setEditorData(self, editor, index):
        editor.setCurrentText(index.data())

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText())


class LinkPage(Page):
    files_written = Signal(list)

    def __init__(self):
        super().__init__()
        self.outcome = self.settings = None
        self.body = QWidget()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        bar = Card()
        row = QHBoxLayout()
        self.summary = label("", wrap=True)
        self.summary.setMinimumWidth(0)
        row.addWidget(self.summary, 1)
        self.reset = QPushButton("추천대로 되돌리기")
        self.reset.setObjectName("secondary")
        self.make = QPushButton("양식 만들기")
        self.make.setObjectName("primary")
        self.make.setToolTip("고른 컬럼 하나로 2-1-5-1·2-1-5-2를 다시 만듭니다 (1행). 점검 일시는 새로 뽑습니다.")
        row.addWidget(self.reset)
        row.addWidget(self.make)
        bar.body.addLayout(row)
        bar.body.addWidget(label("정보명 = 한글컬럼명, 설명 = '{항목명} {주기} 연계', DB명 = 메타의 영문 DB명. "
                                 "주기·활용기관은 칸을 두 번 눌러 바꿉니다. 점검 결과는 '오류 없음', 점검 일시는 시작일~오늘 평일 무작위.",
                                 "muted", wrap=True))
        lay.addWidget(bar)
        lay.addWidget(label("목록 정의서 (산출물에 들어간 행)", "sectionTitle"))
        self.preview = TableBox(LIST_HEADERS, flag_label=None)
        self.preview.view.setMinimumHeight(90)
        self.preview.view.setMaximumHeight(110)   # 1행이라 낮게
        self.preview.model.mono_cols = {9, 10}
        lay.addWidget(self.preview)
        lay.addWidget(label("컬럼 고르기 (컬럼정의서 기준)", "sectionTitle"))
        self.table = TableBox(LINK_HEADERS, flag_label=None)
        self.table.model.check_col = 0
        self.table.model.single_check = True
        self.table.model.mono_cols = {2, 3}
        self.table.model.editable_cols = {COL_CYCLE, COL_USER}
        self.table.view.setItemDelegateForColumn(COL_CYCLE, _ChoiceDelegate(CYCLES, self.table.view))
        self.table.model.checked_changed.connect(self._sync)
        self.table.model.dataChanged.connect(lambda *_: self._sync())
        lay.addWidget(self.table, 1)
        self.content.addWidget(self.body, 1)
        self.reset.clicked.connect(self._reset)
        self.make.clicked.connect(self._make)
        self.show_outcome(None, None)

    def show_outcome(self, outcome, settings):
        super().show_outcome(outcome, settings)
        self.body.setVisible(outcome is not None)
        self.outcome, self.settings = outcome, settings
        if outcome is None:
            return
        self._load()

    def _load(self):
        cands = self.outcome.candidates
        self.preview.set_rows(self.outcome.link_list, empty="고른 컬럼이 없습니다.")
        self.table.set_rows([("", c.reason, c.table, c.column, c.column_kor, c.data_type, c.length, c.cycle, c.user)
                             for c in cands], [None] * len(cands), [c.selected for c in cands])
        self._sync()

    def _sync(self):
        """표의 체크·주기·활용기관을 후보에 반영."""
        model = self.table.model
        for c, row, checked in zip(self.outcome.candidates, model.rows, model.checks):
            c.selected, c.cycle, c.user = checked, row[COL_CYCLE], row[COL_USER]
        chosen = next((c for c in self.outcome.candidates if c.selected), None)
        picked = f"<b>{chosen.table}.{chosen.column}</b> ({chosen.column_kor})" if chosen else "<b>선택 없음</b>"
        self.summary.setText(f"연계 양식 1행: {picked} · 전체 {len(model.rows):,}개 중 하나<br>"
                             "<span style='color:#667085'>추천 순서: PK → 식별자·코드 → FK → 명칭 "
                             "(관리·민감 컬럼과 개인정보는 제외)</span>")

    def _reset(self):
        from ..core.linkage import pick_one, recommend
        for c in self.outcome.candidates:
            c.selected, c.reason = recommend(c)
        pick_one(self.outcome.candidates)
        self._load()

    def _make(self):
        paths = _make_link_files(self, self.outcome, self.settings)
        if paths:
            self.files_written.emit(paths)


class LinkStatusPage(Page):
    """2-1-5-2: 관리현황 자료에 들어간 행(점검 일시·점검 결과)을 보고, 점검 일시를 다시 뽑는다."""
    files_written = Signal(list)

    def __init__(self):
        super().__init__()
        self.outcome = self.settings = None
        self.body = QWidget()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        bar = Card()
        row = QHBoxLayout()
        self.summary = label("")
        row.addWidget(self.summary, 1)
        self.make = QPushButton("점검 일시 다시 뽑기")
        self.make.setObjectName("primary")
        self.make.setToolTip("2-1-5-1·2-1-5-2를 다시 만듭니다. 연계 컬럼은 2-1-5-1 화면에서 고릅니다.")
        row.addWidget(self.make)
        bar.body.addLayout(row)
        self.note = label("", "muted", wrap=True)
        bar.body.addWidget(self.note)
        lay.addWidget(bar)
        lay.addWidget(label("관리현황 자료 (산출물에 들어간 행)", "sectionTitle"))
        self.table = TableBox(STATUS_HEADERS, flag_label=None)
        lay.addWidget(self.table, 1)
        self.content.addWidget(self.body, 1)
        self.make.clicked.connect(self._make)
        self.show_outcome(None, None)

    def show_outcome(self, outcome, settings):
        super().show_outcome(outcome, settings)
        self.body.setVisible(outcome is not None)
        self.outcome, self.settings = outcome, settings
        if outcome is None:
            return
        rows = outcome.link_status
        self.table.set_rows(rows, empty="2-1-5-1 화면에서 연계 컬럼을 고르고 양식을 만들면 여기에 나옵니다.")
        self.summary.setText(f"연계명 <b>{rows[0][3]}</b> · 점검 일시 <b>{rows[0][4]}</b>" if rows else "<b>행 없음</b>")
        self.note.setText(f"점검 결과는 '{settings.link_result}', 점검 일시는 올해 {_month_day(settings.link_start)}~오늘 "
                          "평일 09~18시 무작위입니다. 오류가 없으면 현황 점검 내역만으로 만점입니다 (세부 안내서 p.197).")

    def _make(self):
        paths = _make_link_files(self, self.outcome, self.settings)
        if paths:
            self.files_written.emit(paths)
