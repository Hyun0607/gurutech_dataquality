"""실제 BRIS 메타(메타데이터 표준 관리항목)를 매크로 방식으로 돌려 실제 매크로 산출물과 셀 단위로 비교.

파일은 프로젝트 폴더(Data Quality processing)에 있을 때만 쓴다. 개인정보가 있는 메타 파일은 테스트 데이터로 복사하지 않는다.
"""
from pathlib import Path

import pytest

from stdtool.config import Settings
from stdtool.model import COLUMN_DEF_COLS, DOMAIN_COLS, MANUAL_COLS, TABLE_DEF_COLS, TERM_COLS, WORD_COLS, col
from stdtool.pipeline import run
from stdtool.vba import cstr
from stdtool.workbook.reader import read_meta, read_rows

ROOT = Path(__file__).resolve().parents[2]
TAIL = "한국농업기술진흥원_(농진원)생명자원정보서비스(BRIS).xlsx"
META = ROOT / f"메타데이터 표준 관리항목_{TAIL}"


def norm(v):
    t = cstr(v).strip()
    try:
        f = float(t)
        return str(int(f)) if f.is_integer() else str(f)
    except ValueError:
        return t


def rows(data, width):
    return [[norm(v) for v in r[:width]] for r in data]


@pytest.fixture(scope="module")
def result(macro_dict):
    if not META.exists():
        pytest.skip(f"BRIS 메타 없음: {META}")
    settings = Settings(org_name="한국농업기술진흥원", db_name="(농진원)생명자원정보서비스(BRIS)",
                        enact_date=20170715, inst_std="N", enhanced=False)
    return run(read_meta(META), macro_dict, settings)


@pytest.mark.parametrize("name,attr,width,first", [
    ("테이블정의서", "tables", TABLE_DEF_COLS, 2),
    ("컬럼정의서", "columns", COLUMN_DEF_COLS, 2),
])
def test_definitions_identical(result, name, attr, width, first):
    expected = read_rows(ROOT / f"{name}_{TAIL}", width, first)
    assert rows(getattr(result.definitions, attr), width) == rows(expected, width)


@pytest.mark.parametrize("name,attr,width", [("DB표준용어", "terms", TERM_COLS), ("DB표준단어", "words", WORD_COLS)])
def test_terms_words_identical(result, name, attr, width):
    expected = read_rows(ROOT / f"{name}_{TAIL}", width, 2)
    assert rows(getattr(result, attr), width) == rows(expected, width)


def test_manual_identical(result):
    expected = read_rows(ROOT / "수동등록_(농진원)생명자원정보서비스(BRIS).xlsx", MANUAL_COLS, 4)
    assert len(result.manual) == 89
    assert rows(result.manual, MANUAL_COLS) == rows(expected, MANUAL_COLS)


def test_domains_superset_of_actual(result):
    """실제 산출물에 없는 3개는 용어가 가리키는 도메인이다 (매크로 코드대로면 만들어짐)."""
    expected = rows(read_rows(ROOT / f"DB표준도메인_{TAIL}", DOMAIN_COLS, 2), DOMAIN_COLS)
    got = rows(result.domains, DOMAIN_COLS)
    extra = [g for g in got if g not in expected]
    assert [g for g in got if g in expected] == expected
    assert sorted(g[col("C")] for g in extra) == ["명칭VC100", "명칭VC200", "코드CH2"]
