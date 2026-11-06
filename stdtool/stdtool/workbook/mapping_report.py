"""② 표준 매핑 검토 파일: 결과를 보여 주고, 사람이 '확정' 열을 고쳐 다시 실행하면 그대로 반영한다."""
from collections import Counter
from pathlib import Path

import openpyxl
from openpyxl.styles import Font
from openpyxl.worksheet.datavalidation import DataValidation

from ..core.synonym import MAPPING, NONE, REPLACE, STANDARD
from ..vba import s
from .reader import read_rows
from .writer import YELLOW, _table

SHEET = "매핑결과"
HEADER = ["No", "한글컬럼명", "영문컬럼명", "테이블 수", "컬럼 수", "구분", "판정 단계", "표준용어명", "영문약어명",
          "표준도메인명", "데이터타입", "데이터길이", "확정(Y/N)", "후보1", "후보2", "후보3", "금칙어", "단어 치환 결과"]
KOR, ENG, TERM, CONFIRM = 1, 2, 7, 12   # 0부터 센 열 위치


def _term_text(term, score):
    return f"{term.name} ({term.abbr}, {term.domain}, {score})"


def write_mapping_report(results: list, raw_before: list, path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "요약"
    counts = Counter(r.category for r in results)
    ws.append(["② 공통표준 매핑 검토"])
    ws.cell(1, 1).font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["구분", "한글·영문 쌍 수", "컬럼 수"])
    for category in (STANDARD, REPLACE, MAPPING, NONE):
        ws.append([category, counts[category], sum(len(r.rows) for r in results if r.category == category)])
    ws.append(["(치환 적용됨)", sum(1 for r in results if r.confirmed), sum(len(r.rows) for r in results if r.confirmed)])
    ws.append(["금칙어 사용", sum(1 for r in results if r.forbidden), sum(len(r.rows) for r in results if r.forbidden)])
    ws.append([])
    ws.append(["사용법: '매핑결과' 시트에서 확정(Y/N)과 표준용어명을 고친 뒤 이 파일을 --review 로 넘겨 다시 실행하면 그대로 반영됩니다."])
    ws.column_dimensions["A"].width = 22

    order = {REPLACE: 0, MAPPING: 1, NONE: 2, STANDARD: 3}
    ordered = sorted(results, key=lambda r: (order[r.category], r.kor))
    rows, highlight = [], set()
    for no, r in enumerate(ordered, start=1):
        t = r.term
        cands = [_term_text(c, sc) for c, sc in r.candidates[:3]] + [""] * 3
        rows.append([no, r.kor, r.eng, len(r.tables), len(r.rows), r.category, r.stage,
                     t.name if t else "", t.abbr if t else "", t.domain if t else "",
                     t.data_type if t else "", t.length if t else "",
                     "Y" if r.confirmed else ("" if r.category != REPLACE else "N"),
                     cands[0], cands[1], cands[2],
                     ", ".join(f"{bad}→{rep}" for bad, rep in r.forbidden), r.rebuilt])
        if r.category in (REPLACE, MAPPING):
            highlight.add(no - 1)
    sheet = wb.create_sheet(SHEET)
    _table(sheet, HEADER, rows, [6, 24, 24, 8, 8, 14, 13, 22, 22, 14, 10, 9, 9, 34, 34, 34, 22, 22])
    for i in highlight:
        sheet.cell(i + 2, CONFIRM + 1).fill = YELLOW
    if rows:
        dv = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
        sheet.add_data_validation(dv)
        dv.add(f"M2:M{len(rows) + 1}")

    # 통합시스템 매핑등록용: 치환하지 않고 남은 비표준 컬럼을 테이블별로
    sheet = wb.create_sheet("매핑등록")
    by_key = {(r.kor, r.eng): r for r in results}
    out = []
    for row in raw_before:
        r = by_key.get((s(row[2]), s(row[3])))
        if r is None or r.confirmed or r.category not in (REPLACE, MAPPING):
            continue
        t = r.term or (r.candidates[0][0] if r.candidates else None)
        out.append([s(row[1]), r.kor, r.eng, t.name if t else "", t.abbr if t else "", t.data_type if t else "",
                    t.length if t else "", r.category, r.stage])
    _table(sheet, ["영문테이블명", "한글컬럼명", "영문컬럼명", "표준용어명", "영문약어명", "데이터타입", "데이터길이",
                   "구분", "판정 단계"], out, [24, 24, 24, 22, 22, 10, 9, 14, 13])

    sheet = wb.create_sheet("금칙어")
    bad = [r for r in results if r.forbidden]
    _table(sheet, ["한글컬럼명", "영문컬럼명", "컬럼 수", "금칙어 → 대표 단어", "구분"],
           [(r.kor, r.eng, len(r.rows), ", ".join(f"{b}→{rep}" for b, rep in r.forbidden), r.category) for r in bad],
           [24, 24, 8, 30, 14], set(range(len(bad))))
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def read_mapping_decisions(path: Path) -> dict:
    """검토 파일 → {(한글, 영문): (확정 여부, 표준용어명)}"""
    decisions = {}
    for r in read_rows(path, len(HEADER), 2, SHEET):
        kor, eng = s(r[KOR]), s(r[ENG])
        if kor or eng:
            decisions[(kor, eng)] = (s(r[CONFIRM]).upper() == "Y", s(r[TERM]))
    return decisions
