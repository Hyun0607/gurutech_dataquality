"""표준 정의(2-1-3-1) 화면 위쪽: 기관표준 점검 · A값 자가진단.

메타 파일·▶ 실행과 상관없이, 위에서 고른 기관의 기관표준(표준 사전에 있는 것)이나 직접 넣은 기관표준 파일로 점검한다.
통합시스템 '엑셀 다운로드'(점검결과 포함) 파일이면 실제 A값, 등록 양식이면 프로그램 점검으로 예상 A값.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QFrame, QGridLayout, QHBoxLayout, QMessageBox, QPushButton

from .. import db, inst_db
from ..config import Settings
from ..core.inst_check import check_inst
from ..pipeline import build_matcher
from ..workbook import inst_report
from ..workbook.inst_reader import InstError, read_inst
from .pages import open_path
from .widgets import Badge, Card, TableBox, label

SUMMARY_HEADERS = ["구분", "완전성 대상", "완전성 오류", "정의", "준용 대상", "준용 오류", "준용", "항목별 A"]


class InstPanel(Card):
    def __init__(self):
        super().__init__()
        self.org, self.db_settings, self.check = "", None, None
        self.output_dir = ""
        self._common = (None, None)   # (사전 위치, (matcher, 공통표준 도메인))
        head = QHBoxLayout()
        head.addWidget(label("기관표준 점검 · A값", "sectionTitle"))
        head.addWidget(label("2-1-3-1 점수 = 평가대상 DB 점수 합계 × A ÷ 평가대상 DB 수", "muted"))
        head.addStretch(1)
        self.pick = QPushButton("기관표준 파일 넣기")
        self.pick.setObjectName("secondary")
        self.pick.setToolTip("기관표준 용어·단어·도메인·코드 xlsx (통합시스템 '엑셀 다운로드' 또는 '엑셀양식 다운로드' 양식). "
                             "점검결과가 든 파일이면 실제 A값, 등록 양식이면 예상 A값")
        self.pick.clicked.connect(self._pick)
        head.addWidget(self.pick)
        self.save = QPushButton("결과 엑셀 저장")
        self.save.setObjectName("primary")
        self.save.clicked.connect(self._save)
        head.addWidget(self.save)
        self.body.addLayout(head)

        top = QGridLayout()
        top.setHorizontalSpacing(18)
        self.a_value = label("—", "bigNumber")
        self.a_value.setMinimumWidth(96)
        top.addWidget(label("A값", "muted"), 0, 0)
        top.addWidget(self.a_value, 1, 0, Qt.AlignTop)
        self.verdict = Badge("—")
        top.addWidget(self.verdict, 0, 1, Qt.AlignLeft)
        self.source = label("", "muted", wrap=True)
        top.addWidget(self.source, 1, 1)
        self.reasons = label("", "", wrap=True)
        top.addWidget(self.reasons, 2, 1)
        top.setColumnStretch(1, 1)
        self.body.addLayout(top)

        self.summary = QFrame()   # 영역 4줄 × 8칸 (품표 표처럼 칸으로)
        self.summary.setObjectName("portal")
        grid = QGridLayout(self.summary)
        grid.setSpacing(0)
        grid.setContentsMargins(0, 0, 0, 0)
        for j, h in enumerate(SUMMARY_HEADERS):
            head_cell = label(h, "portalHead")
            head_cell.setAlignment(Qt.AlignCenter)
            grid.addWidget(head_cell, 0, j)
            grid.setColumnStretch(j, 2 if j == 0 else 1)
        self.cells = []
        for i in range(4):
            row = []
            for j in range(len(SUMMARY_HEADERS)):
                cell = label("", "instCell")
                cell.setAlignment(Qt.AlignCenter if j else Qt.AlignLeft | Qt.AlignVCenter)
                grid.addWidget(cell, i + 1, j)
                row.append(cell)
            self.cells.append(row)
        self.body.addWidget(self.summary)
        self.issues = TableBox(["영역", "점검", "행", "이름", "오류명", "참고"], flag_label=None)
        self.issues.view.setMinimumHeight(200)
        self.body.addWidget(self.issues)
        self._show()

    # --- 자료 ---------------------------------------------------------------

    def set_org(self, org: str, db_settings):
        """위에서 고른 기관이 바뀌면 사전의 기관표준으로 다시 본다."""
        changed = org != self.org or db_settings != self.db_settings
        self.org, self.db_settings = org, db_settings
        if changed:
            self.refresh()

    def _matcher(self, conn):
        key = getattr(self.db_settings, "file", "") or str(self.db_settings)
        if self._common[0] != key:
            common = db.load_common(conn)
            self._common = (key, (build_matcher(common, Settings()), common.domains) if common else (None, None))
        return self._common[1]

    def refresh(self):
        self.check = None
        if not self.org or self.db_settings is None:
            self._show("기관을 고르면 그 기관의 기관표준을 표준 사전에서 찾아 점검합니다.")
            return
        try:
            with db.connect(self.db_settings) as conn:
                inst = inst_db.load_inst(conn, self.org)
                matcher, domains = self._matcher(conn)
        except Exception as e:   # 사전을 못 읽어도 화면은 그대로
            self._show(f"표준 사전을 읽지 못했습니다: {e}")
            return
        if inst is None:
            self._show(f"표준 사전에 '{self.org}'의 기관표준이 없습니다. [기관표준 파일 넣기]로 파일을 넣어 점검하세요. "
                       "(사전에 없으면 기관표준 미준용으로 실행되고, 기관표준이 없으면 A=0.8입니다)")
            return
        self.check = check_inst(inst, matcher, domains)
        self._show(where="표준 사전")

    def _pick(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "기관표준 파일 (용어·단어·도메인·코드)", str(Path.home()), "엑셀 (*.xlsx)")
        if not paths:
            return
        try:
            inst = read_inst(paths, self.org)
            with db.connect(self.db_settings) as conn:
                matcher, domains = self._matcher(conn)
        except InstError as e:
            QMessageBox.warning(self, "기관표준 파일", str(e))
            return
        except Exception as e:
            QMessageBox.warning(self, "기관표준 파일", f"표준 사전(공통표준)을 읽지 못했습니다: {e}")
            return
        self.check = check_inst(inst, matcher, domains)
        self._show(where="넣은 파일")

    # --- 그리기 -------------------------------------------------------------

    def _show(self, message: str = "", where: str = ""):
        c = self.check
        self.save.setEnabled(c is not None)
        self.summary.setVisible(c is not None)
        self.issues.setVisible(c is not None)
        if c is None:
            self.a_value.setText("—")
            self.verdict.set("점검 전", "neutral")
            self.source.setText(message)
            self.reasons.setText("")
            return
        self.a_value.setText(f"{c.a_value:g}")
        self.verdict.set(c.verdict, "success" if c.a_value == 1 else "warn" if c.a_value == 0.9 else "error")
        kind = "실제 (통합시스템 점검결과)" if c.actual else "예상 (프로그램이 통합시스템과 같은 규칙으로 점검)"
        inst = c.inst
        self.source.setText(f"{where} · {inst.org}{f' · {inst.name}' if inst.name else ''} · {inst.source} · {kind}")
        reasons = c.reasons()
        self.reasons.setText("A값을 깎는 이유: " + " / ".join(reasons) if reasons else
                             "정의(용어·단어·도메인·코드 모두 통과 건 있음)와 준용(용어·단어·도메인 모두 통과 건 있음)을 충족합니다.")
        rows = [[r[0], f"{r[1]:,}", f"{r[2]:,}", r[4], r[5] if r[5] == "-" else f"{r[5]:,}",
                 r[6] if r[6] == "-" else f"{r[6]:,}", r[8] if r[8] != "해당 없음 (행정표준코드)" else "해당 없음", f"{r[9]:g}"]
                for r in inst_report.summary_rows(c)]
        for cells, values in zip(self.cells, rows):
            for cell, value in zip(cells, values):
                cell.setText(str(value))
                cell.setProperty("bad", value == "불인정" or value == "0.8" or value == "0.9")
                cell.style().unpolish(cell)
                cell.style().polish(cell)
        self.issues.set_rows([[i.area, i.kind, i.row, i.key, i.message, i.detail] for i in c.issues],
                             ["error" if i.kind == "완전성" else "warn" for i in c.issues],
                             empty="오류 없음 — 기관표준 점검을 통과했습니다.")

    def _save(self):
        if not self.check:
            return
        start = Path(self.output_dir or Path.home()) / inst_report.file_name(self.check)
        path, _ = QFileDialog.getSaveFileName(self, "기관표준 점검 결과", str(start), "엑셀 (*.xlsx)")
        if not path:
            return
        try:
            written = inst_report.write_inst_check(self.check, Path(path))
        except PermissionError:
            QMessageBox.warning(self, "결과 엑셀", "파일을 쓸 수 없습니다. 엑셀에서 열어 두었다면 닫고 다시 저장하세요.")
            return
        if QMessageBox.question(self, "결과 엑셀", f"저장했습니다.\n{written}\n\n열어 볼까요?") == QMessageBox.Yes:
            open_path(written)
