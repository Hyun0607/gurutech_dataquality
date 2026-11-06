import csv
import os
from pathlib import Path

import pytest

from stdtool.dictionary import Sheet, StandardDict
from stdtool.model import (COLUMN_DEF_COLS, DOMAIN_COLS, META_COLS, TABLE_DEF_COLS, TERM_COLS, WORD_COLS,
                           blank_row, col)

FIXTURES = Path(__file__).parent / "fixtures"
MACRO_XLSM = Path(os.environ.get(
    "STDTOOL_MACRO_XLSM",
    str(Path.home() / "Downloads" / "공공데이터 품질관리 수준평가_표준구조_매크로_260805_수정.xlsm")))


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def number(text):
    return int(text) if text.isdigit() else text


def _sheet(name):
    header, rows = read_csv(FIXTURES / f"{name}.csv")
    return Sheet(header, [[number(v) if v else None for v in r] for r in rows])


def make_dict(common=None, inst=None) -> StandardDict:
    header = ["한글 컬럼명", "영문 컬럼명", "데이터 타입", "데이터 길이"]
    return StandardDict(Sheet(header, common or []), Sheet(header, inst or []), _sheet("code_type"), _sheet("code_tail"))


def place(width, values: dict):
    row = blank_row(width)
    for letter, v in values.items():
        row[col(letter)] = v
    return row


def load_bris():
    """BRIS 산출물을 매크로 시트 열 배치로."""
    _, d = read_csv(FIXTURES / "bris" / "domains.csv")
    _, t = read_csv(FIXTURES / "bris" / "terms.csv")
    _, w = read_csv(FIXTURES / "bris" / "words.csv")
    _, c = read_csv(FIXTURES / "bris" / "columns.csv")
    _, tb = read_csv(FIXTURES / "bris" / "tables.csv")
    return {
        "domains": [place(DOMAIN_COLS, {"B": r[0], "C": r[1], "E": r[2], "F": int(r[3]), "L": int(r[4])}) for r in d],
        "terms": [place(TERM_COLS, {"A": r[0], "C": r[1], "E": r[2], "I": int(r[3])}) for r in t],
        "words": [place(WORD_COLS, {"A": r[0], "B": r[1], "C": r[2], "E": r[3], "I": int(r[4])}) for r in w],
        "columns": [place(COLUMN_DEF_COLS, {"A": r[0], "B": r[1], "C": r[2], "G": r[3], "H": int(r[4])}) for r in c],
        "tables": [place(TABLE_DEF_COLS, {"B": r[0], "C": r[1]}) for r in tb],
    }


def bris_meta():
    """BRIS 컬럼정의서·테이블정의서로 메타 입력을 되살린다 (매크로 실행 전 원본은 아님)."""
    data = load_bris()
    table_kor = {t[col("C")]: t[col("B")] for t in data["tables"]}
    rows = []
    for c in data["columns"]:
        rows.append(place(META_COLS, {
            "B": "한국농업기술진흥원", "C": "생명자원정보서비스(BRIS)",
            "Z": table_kor[c[col("A")]], "AA": c[col("A")], "AI": c[col("B")], "AJ": c[col("C")],
            "AO": c[col("G")], "AP": c[col("H")] or None,
        }))
    return rows


COMMON_DIR = Path(os.environ.get("STDTOOL_COMMON_DIR",
                                 str(Path.home() / "OneDrive" / "Desktop" / "2026 프로젝트" / "10.계룡시" / "계룡시 A값")))


@pytest.fixture(scope="session")
def common_real():
    term = COMMON_DIR / "공통표준용어.xlsx"
    if not term.exists():
        pytest.skip(f"공통표준 원본 없음: {COMMON_DIR}")
    from stdtool.dictionary import load_common_standard
    return load_common_standard(term, COMMON_DIR / "공통표준단어.xlsx", COMMON_DIR / "공통표준도메인.xlsx")


@pytest.fixture(scope="session")
def macro_dict():
    if not MACRO_XLSM.exists():
        pytest.skip(f"매크로 파일 없음: {MACRO_XLSM}")
    from stdtool.dictionary import load_from_macro_workbook
    return load_from_macro_workbook(MACRO_XLSM)
