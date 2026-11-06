"""구조 현행화 검증 (2-1-4-2): 정의서 ↔ 수동등록."""
from conftest import place

from stdtool.core.currency import run_currency
from stdtool.model import COLUMN_DEF_COLS, TABLE_DEF_COLS


def tables(*names):
    return [place(TABLE_DEF_COLS, {"B": n + "한글", "C": n}) for n in names]


def columns(*items):
    return [place(COLUMN_DEF_COLS, {"A": t, "B": c, "C": c, "G": dt, "H": ln}) for t, c, dt, ln in items]


def meta(*items):
    return [{"row": i + 4, "table": t, "kor": c, "eng": c, "type": dt, "length": ln} for i, (t, c, dt, ln) in enumerate(items)]


def codes(result, source):
    return [(r.table, r.column, r.code) for r in result.rows if r.source == source]


def test_all_match_is_100():
    r = run_currency(tables("T1"), columns(("T1", "A", "VARCHAR", 10), ("T1", "B", "NUMBER", 5)),
                     meta(("T1", "A", "VARCHAR", 10), ("T1", "B", "number", 5)))
    assert r.rate == 100.0 and r.score == 1
    assert [x[1:3] for x in r.rates] == [(1, 1), (1, 1), (2, 2), (2, 2)]


def test_mismatch_codes_and_lowest_rate():
    r = run_currency(
        tables("T1", "T2"),
        columns(("T1", "A", "VARCHAR", 10), ("T1", "B", "VARCHAR", 10), ("T1", "C", "CHAR", 1), ("T2", "X", "DATE", 0)),
        meta(("T1", "A", "VARCHAR", 20),       # 길이 불일치
             ("T1", "B", "CHAR", 10),          # 타입 불일치
             ("T1", "D", "VARCHAR", 10),       # 컬럼정의서에 없는 컬럼
             ("T3", "Z", "VARCHAR", 5)))       # 정의서에 없는 테이블
    assert codes(r, "메타 컬럼") == [("T1", "A", "S05"), ("T1", "B", "S04"), ("T1", "D", "S03"), ("T3", "Z", "S02")]
    assert codes(r, "컬럼정의서") == [("T1", "A", "S05"), ("T1", "B", "S04"), ("T1", "C", "S03"), ("T2", "X", "S02")]
    assert codes(r, "메타 테이블") == [("T1", "", ""), ("T3", "", "S02")]
    assert codes(r, "테이블정의서") == [("T1", "", ""), ("T2", "", "S02")]
    assert r.rate == 0.0 and r.score == 0


def test_length_compared_only_when_meta_has_length():
    r = run_currency(tables("T1"), columns(("T1", "A", "DATE", 0)), meta(("T1", "A", "DATE", None)))
    assert r.rate == 100.0


def test_no_meta_is_not_checkable():
    r = run_currency(tables("T1"), columns(("T1", "A", "VARCHAR", 10)), [])
    assert codes(r, "컬럼정의서") == [("T1", "A", "S01")]
    assert codes(r, "테이블정의서") == [("T1", "", "S01")]
