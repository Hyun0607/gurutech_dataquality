"""연계 산출물: 연계후보 검토 파일과 2-1-5-1·2-1-5-2 양식."""
from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill

from ..vba import s
from .reader import read_rows
from .writer import TEMPLATES, _table, safe_name, write_template

GREEN = PatternFill("solid", fgColor="FFE2EFDA")   # 추천된 행

REVIEW_HEADER = ["선택(Y/N)", "추천 사유", "영문테이블명", "한글테이블명", "영문컬럼명", "한글컬럼명", "데이터 타입", "데이터 길이",
                 "송·수신 구분", "주기", "제공기관", "활용기관"]


def write_link_candidates(candidates: list, path: Path) -> Path:
    """모든 컬럼을 추천 여부와 함께. 선택을 Y/N으로 고쳐 --link-review 로 넘기면 그대로 반영된다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "연계후보"
    rows = [("Y" if c.selected else "N", c.reason, c.table, c.table_kor, c.column, c.column_kor, c.data_type, s(c.length),
             c.direction, c.cycle, c.provider, c.user) for c in candidates]
    _table(ws, REVIEW_HEADER, rows, [9, 14, 24, 20, 24, 20, 11, 9, 10, 9, 18, 18])
    for i, c in enumerate(candidates):
        if c.selected:
            for k in range(1, len(REVIEW_HEADER) + 1):
                ws.cell(i + 2, k).fill = GREEN
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def read_link_review(path: Path) -> dict:
    """(영문테이블명, 영문컬럼명) 대문자 → {'selected', 'direction', 'cycle', 'provider', 'user'}."""
    out = {}
    for r in read_rows(path, len(REVIEW_HEADER), 2):
        table, column = s(r[2]), s(r[4])
        if table and column:
            out[(table.upper(), column.upper())] = {"selected": s(r[0]).upper() == "Y", "direction": s(r[8]),
                                                    "cycle": s(r[9]), "provider": s(r[10]), "user": s(r[11])}
    return out


def export_linkage(list_rows: list, status_rows: list, folder: Path, db_name: str) -> list:
    name = safe_name(db_name)
    return [write_template("연계목록", list_rows, folder / f"{TEMPLATES['연계목록'][1]}_{name}.xlsx"),
            write_template("연계현황", status_rows, folder / f"{TEMPLATES['연계현황'][1]}_{name}.xlsx")]
