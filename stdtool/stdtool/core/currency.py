"""구조 현행화 검증 (지표 2-1-4-2): 테이블·컬럼 정의서 ↔ 메타(수동등록)를 맞춰 본다.

근거: 세부 안내서 p.171~172 (현행화율 4가지 중 가장 낮은 값), p.177~179 (현행화점검 오류).
메타 쪽은 기관메타시스템에 올리는 수동등록 파일이다.
"""
from dataclasses import dataclass, field

from ..model import col
from ..vba import s, val

CODES = {
    "S01": "점검 불가능(비교 대상 정보 없음)",
    "S02": "불일치(영문테이블명)",
    "S03": "불일치(영문컬럼명)",
    "S04": "불일치(데이터타입)",
    "S05": "불일치(데이터길이)",
}

# 점검 불가능 오류명은 점검 대상마다 다르다 (안내서 p.177~179: 비교할 상대가 0건일 때)
NO_TARGET = {"테이블정의서": "점검 불가능(메타데이터 테이블 정보 없음)", "메타 테이블": "점검 불가능(테이블정의서 정보 없음)",
             "컬럼정의서": "점검 불가능(메타데이터 컬럼 정보 없음)", "메타 컬럼": "점검 불가능(컬럼정의서 정보 없음)"}
GROUPS = {"테이블정의서": "[ 테이블정의서 ] 현행화 점검", "메타 테이블": "[ 메타데이터 테이블 ] 현행화 점검",
          "컬럼정의서": "[ 컬럼정의서 ] 현행화 점검", "메타 컬럼": "[ 메타데이터 컬럼 ] 현행화 점검"}


def code_label(code: str) -> str:
    """S01 → 현행화-01 (화면·리포트용)."""
    return f"현행화-{code[1:]}" if code else ""


@dataclass
class CurrencyRow:
    source: str        # 테이블정의서 / 컬럼정의서 / 메타 테이블 / 메타 컬럼
    row: int
    table: str
    column: str = ""
    data_type: str = ""
    length: object = None
    other_type: str = ""
    other_length: object = None
    code: str = ""     # 비어 있으면 일치

    @property
    def message(self) -> str:
        if self.code == "S01":
            return NO_TARGET.get(self.source, CODES["S01"])
        return CODES.get(self.code, "일치")


@dataclass
class CurrencyResult:
    rows: list = field(default_factory=list)
    rates: list = field(default_factory=list)   # (구분, 일치, 전체, 현행화율)

    @property
    def rate(self) -> float:
        """4가지 현행화율 중 가장 낮은 값."""
        return min((r[3] for r in self.rates), default=0.0)

    @property
    def score(self) -> float:
        rate = self.rate
        return 1 if rate >= 90 else 0.7 if rate >= 80 else 0.4 if rate >= 70 else 0

    def count(self, code: str) -> int:
        return sum(1 for r in self.rows if r.code == code)


def _rate(matched: int, total: int) -> float:
    return 100.0 * matched / total if total else 0.0


def run_currency(tables_def: list, columns_def: list, meta_columns: list) -> CurrencyResult:
    """tables_def: 테이블정의서 행 (B 한글, C 영문테이블명). columns_def: 컬럼정의서 행 (A 테이블, C 영문컬럼명, G 타입, H 길이).
    meta_columns: [{'row', 'table', 'eng', 'type', 'length'}] (수동등록). 메타 테이블은 메타 컬럼의 테이블 목록."""
    result = CurrencyResult()
    def_tables = [(i + 2, s(t[col("C")])) for i, t in enumerate(tables_def) if s(t[col("C")])]
    def_cols = [(i + 2, s(c[col("A")]), s(c[col("C")]), s(c[col("G")]), c[col("H")]) for i, c in enumerate(columns_def)]
    meta_cols = [(m["row"], s(m["table"]), s(m["eng"]), s(m["type"]), m["length"]) for m in meta_columns]
    meta_tables, seen = [], set()
    for row, table, *_ in meta_cols:
        if table and table.upper() not in seen:
            seen.add(table.upper())
            meta_tables.append((row, table))

    def_table_set = {t.upper() for _, t in def_tables}
    def_col_table_set = {t.upper() for _, t, *_ in def_cols if t}
    meta_table_set = {t.upper() for _, t in meta_tables}
    def_col_map = {(t.upper(), c.upper()): (dt, ln) for _, t, c, dt, ln in def_cols}
    meta_col_map = {(t.upper(), c.upper()): (dt, ln) for _, t, c, dt, ln in meta_cols}

    def table_rows(source, items, other_set):
        out = []
        for row, table in items:
            code = "S01" if not other_set else "" if table.upper() in other_set else "S02"
            out.append(CurrencyRow(source, row, table, code=code))
        return out

    def column_rows(source, items, other_map, other_tables, meta_is_self):
        out = []
        for row, table, column, dtype, length in items:
            r = CurrencyRow(source, row, table, column, dtype, length)
            other = other_map.get((table.upper(), column.upper()))
            if not other_map:
                r.code = "S01"
            elif table.upper() not in other_tables:
                r.code = "S02"
            elif other is None:
                r.code = "S03"
            else:
                r.other_type, r.other_length = other
                meta_length = length if meta_is_self else r.other_length
                if dtype.upper() != s(r.other_type).upper():
                    r.code = "S04"
                elif s(meta_length) != "" and val(length) != val(r.other_length):
                    r.code = "S05"   # 메타에 길이가 있을 때만 비교
            out.append(r)
        return out

    groups = [
        ("① 테이블 현행화율", table_rows("메타 테이블", meta_tables, def_table_set)),
        ("② 테이블 정의서 현행화율", table_rows("테이블정의서", def_tables, meta_table_set)),
        ("③ 컬럼 현행화율", column_rows("메타 컬럼", meta_cols, def_col_map, def_col_table_set, True)),
        ("④ 컬럼 정의서 현행화율", column_rows("컬럼정의서", def_cols, meta_col_map, meta_table_set, False)),
    ]
    for name, rows in groups:
        matched = sum(1 for r in rows if not r.code)
        result.rates.append((name, matched, len(rows), _rate(matched, len(rows))))
        result.rows += rows
    return result
