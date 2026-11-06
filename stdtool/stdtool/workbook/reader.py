"""입력 양식 읽기: 메타 시트, 기존 DB표준 산출물, 수동등록 파일, 도메인 재사용 풀."""
import warnings
from pathlib import Path

import openpyxl

from ..core.naming import pool_key
from ..model import (COLUMN_DEF_COLS, DOMAIN_COLS, MANUAL_COLS, META_COLS, TABLE_DEF_COLS, TERM_COLS,
                     WORD_COLS, col)
from ..vba import s

# 산출물 파일명 앞부분 → (키, 열 개수). 매크로 정의서_내보내기 파일명 규칙과 같다.
OUTPUT_PREFIXES = {
    "DB표준도메인": ("domains", DOMAIN_COLS),
    "DB표준용어": ("terms", TERM_COLS),
    "DB표준단어": ("words", WORD_COLS),
    "컬럼정의서": ("columns", COLUMN_DEF_COLS),
    "테이블정의서": ("tables", TABLE_DEF_COLS),
}


def _open(path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return openpyxl.load_workbook(path, read_only=True, data_only=True)


def read_rows(path, width: int, first_row: int, sheet: str = "") -> list:
    """first_row(1부터)부터 width열까지 읽는다. 끝의 빈 행은 버린다."""
    wb = _open(path)
    try:
        ws = wb[sheet] if sheet else wb.worksheets[0]
        # 시스템에서 내려받은 파일은 시트 크기 정보가 A1:A1로 잘못 적혀 있는 경우가 있다
        ws.reset_dimensions()
        rows = []
        for values in ws.iter_rows(min_row=first_row, values_only=True):
            values = list(values[:width])
            rows.append(values + [None] * (width - len(values)))
    finally:
        wb.close()
    while rows and all(v in (None, "") for v in rows[-1]):
        rows.pop()
    return rows


def read_meta(path, sheet: str = "") -> list:
    """매크로 '메타' 시트와 같은 양식 (A~AT, 4행부터 데이터)."""
    return read_rows(path, META_COLS, 4, sheet)


META_TARGET = {"org": "B", "system": "C", "db_kor": "O", "db_eng": "P"}   # 기관명·정보시스템명·한글 DB명·영문 DB명


def meta_systems(meta_rows: list) -> list:
    """메타 행 → DB별 [(한글 DB명, 영문 DB명, 업무분류체계)] (파일에 나온 순서). 업무분류체계는 Q열, 비면 ''."""
    out = {}
    for row in meta_rows:
        key = (s(row[col("O")]).strip(), s(row[col("P")]).strip())
        if any(key) and not out.get(key):
            out[key] = s(row[col("Q")]).strip()
    return [(*key, biz) for key, biz in out.items()]


def read_meta_target(path, sheet: str = "") -> dict:
    """메타 파일의 기관·시스템·DB명. 담당자 등 다른 칸은 읽지 않는다.
    DB가 여러 개 섞인 파일이면 DB명은 비운다. 칸이 비었으면 1행 제목 '■ 기관 ▷ 시스템'에서 읽는다."""
    wb = _open(path)
    try:
        ws = wb[sheet] if sheet else wb.worksheets[0]
        ws.reset_dimensions()
        title = s(next(ws.iter_rows(min_row=1, max_row=1, max_col=1, values_only=True), [None])[0])
        found, dbs = {}, set()
        for values in ws.iter_rows(min_row=4, max_col=col("P") + 1, values_only=True):
            row = {k: s(values[col(c)]).strip() if col(c) < len(values) else "" for k, c in META_TARGET.items()}
            if row["org"] and row["system"]:
                found = found or row
                dbs.add((row["db_kor"], row["db_eng"]))
    finally:
        wb.close()
    if len(dbs) > 1:
        found["db_kor"] = found["db_eng"] = ""
    if not found and "▷" in title:
        org, system = title.lstrip("■ ").split("▷", 1)
        found = {"org": org.strip(), "system": system.strip(), "db_kor": "", "db_eng": ""}
    return found


def read_output_folder(folder, overrides: dict | None = None) -> dict:
    """매크로 산출물 폴더에서 DB표준 도메인·용어·단어, 컬럼·테이블정의서를 읽는다.

    파일명이 정해진 앞부분으로 시작하는 파일만 고른다 ('수정_'으로 시작하는 파일은 overrides로 지정).
    하위 폴더(표준_구조_연계 등)까지 찾으므로 {기관}_{DB} 폴더를 줘도 된다.
    """
    found = {}
    for path in sorted(Path(folder).rglob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        for prefix, (key, _) in OUTPUT_PREFIXES.items():
            if path.name.startswith(prefix):
                found[key] = path
    found.update({k: Path(v) for k, v in (overrides or {}).items() if v})
    widths = {key: width for key, width in OUTPUT_PREFIXES.values()}
    return {key: read_rows(path, widths[key], 2) for key, path in found.items()} | {"_files": found}


def read_meta_columns(paths) -> list:
    """수동등록 파일(분할된 여러 개 가능) 또는 메타 양식에서 컬럼 정보만 뽑는다."""
    out = []
    for path in paths:
        header = read_rows(path, META_COLS, 3)[:1]
        header = [s(v) for v in header[0]] if header else []
        manual = any(h.startswith("영문 컬럼명(*)") for h in header)
        if manual:
            cols = {"table": "R", "kor": "Z", "eng": "AA", "type": "AF", "length": "AG"}
            width = MANUAL_COLS
        else:
            cols = {"table": "AA", "kor": "AI", "eng": "AJ", "type": "AO", "length": "AP"}
            width = META_COLS
        for i, r in enumerate(read_rows(path, width, 4)):
            item = {k: r[col(v)] for k, v in cols.items()}
            if s(item["eng"]) == "" and s(item["kor"]) == "":
                continue
            item["row"] = i + 4
            item["file"] = Path(path).name
            out.append(item)
    return out


def read_domain_pool(paths) -> dict:
    """기존 도메인 파일(DB표준도메인 양식)에서 (분류, 타입, 길이, 소수점) → 도메인명."""
    pool = {}
    for path in paths:
        rows = read_rows(path, DOMAIN_COLS, 2)
        for d in rows:
            name = s(d[col("C")])
            if name:
                key = pool_key(d[col("B")], d[col("E")], d[col("F")], d[col("G")])
                pool.setdefault(key, name)
    return pool
