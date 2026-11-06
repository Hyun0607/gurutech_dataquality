"""표준 사전 읽기. 지금은 매크로 파일 시트에서 읽고, 나중에 DB로 바꿀 때 이 모듈만 교체한다."""
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from .vba import ColumnFinder, cstr

SHEET_COMMON = "공통표준"
SHEET_INST = "기관표준"
SHEET_CODE_TYPE = "Code_type"
SHEET_CODE_TAIL = "Code_tail"


@dataclass
class Sheet:
    header: list
    rows: list = field(default_factory=list)


@dataclass
class StandardDict:
    common: Sheet       # A 한글 컬럼명, B 영문 컬럼명, C 데이터 타입, D 데이터 길이
    inst: Sheet
    code_type: Sheet    # A 순번, B 데이터 타입, C 데이터 약어, D 데이터 분류
    code_tail: Sheet    # A 순번, B 도메인자르기, C 도메인분류, D 도메인중분류

    def tail_finder(self) -> ColumnFinder:
        return ColumnFinder(self.code_tail.header, self.code_tail.rows, 1, 2)

    def type_finder(self) -> ColumnFinder:
        return ColumnFinder(self.code_type.header, self.code_type.rows, 1, 2)

    def tail_classes(self) -> set:
        return {cstr(r[2]) for r in self.code_tail.rows if r[2] not in (None, "")}


@dataclass
class CommonTerm:
    name: str
    abbr: str
    domain: str
    synonyms: list
    data_type: object = None
    length: object = None
    scale: object = None


@dataclass
class CommonWord:
    name: str
    abbr: str
    eng_name: str
    is_format: str
    domain_class: str
    synonyms: list
    forbidden: list


@dataclass
class CommonStandard:
    """공통표준 원본 (행정안전부 공통표준 용어·단어·도메인 파일)."""
    terms: list
    words: list
    domains: dict = field(default_factory=dict)   # 도메인명 → (타입, 길이, 소수점)


def split_list(value) -> list:
    """'법원명칭, 법원이름' → ['법원명칭', '법원이름']"""
    return [p.strip() for p in cstr(value).replace("，", ",").split(",") if p.strip() and p.strip() != "-"]


def _rows_by_header(path: Path) -> list:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        ws.reset_dimensions()   # 내려받은 파일의 잘못된 시트 크기 정보 무시
        it = ws.iter_rows(values_only=True)
        header = [cstr(h).strip() for h in next(it)]
        return [dict(zip(header, r)) for r in it if any(v not in (None, "") for v in r)]
    finally:
        wb.close()


def _pick(row: dict, *names):
    for n in names:
        if n in row:
            return row[n]
    return None


def load_common_standard(term_path: Path, word_path: Path | None = None, domain_path: Path | None = None) -> CommonStandard:
    """공통표준용어·단어·도메인 엑셀 (공공데이터 포털 배포 양식). 사용여부가 N인 행은 뺀다."""
    return common_standard_from_rows(_rows_by_header(term_path),
                                     _rows_by_header(word_path) if word_path else [],
                                     _rows_by_header(domain_path) if domain_path else [])


def common_standard_from_rows(term_rows: list, word_rows: list, domain_rows: list) -> CommonStandard:
    """원본 열 이름을 키로 한 행(dict) 목록 → CommonStandard. 엑셀·DB 둘 다 이 함수를 쓴다."""
    def in_use(r):
        return cstr(_pick(r, "사용여부")).strip().upper() != "N"

    domains = {}
    if domain_rows:
        for r in domain_rows:
            if in_use(r):
                name = cstr(_pick(r, "공통표준도메인명")).strip()
                domains[name] = (_pick(r, "데이터 타입"), _pick(r, "데이터 길이"), _pick(r, "소수점 길이"))
    terms = []
    for r in term_rows:
        if not in_use(r):
            continue
        domain = cstr(_pick(r, "공통표준도메인명")).strip()
        data_type, length, scale = domains.get(domain, (None, None, None))
        terms.append(CommonTerm(cstr(_pick(r, "공통표준용어명")).strip(), cstr(_pick(r, "공통표준용어영문약어명")).strip(),
                                domain, split_list(_pick(r, "용어 이음동의어 목록")), data_type, length, scale))
    words = []
    if word_rows:
        for r in word_rows:
            if in_use(r):
                cls = cstr(_pick(r, "공통표준도메인 분류명")).strip()
                words.append(CommonWord(cstr(_pick(r, "공통표준단어명")).strip(), cstr(_pick(r, "공통표준단어영문약어명")).strip(),
                                        cstr(_pick(r, "공통표준단어영문명")).strip(), cstr(_pick(r, "형식단어여부")).strip(),
                                        "" if cls == "-" else cls, split_list(_pick(r, "이음동의어 목록")),
                                        split_list(_pick(r, "금칙어 목록"))))
    return CommonStandard(terms, words, domains)


def _read_sheet(ws, width: int) -> Sheet:
    rows = []
    header = None
    ws.reset_dimensions()
    for values in ws.iter_rows(values_only=True):
        values = list(values[:width]) + [None] * max(0, width - len(values))
        if header is None:
            header = values
        else:
            rows.append(values)
    while rows and all(v in (None, "") for v in rows[-1]):
        rows.pop()
    return Sheet(header or [None] * width, rows)


def load_from_macro_workbook(path: Path) -> StandardDict:
    """매크로 파일(.xlsm)에서 사전 시트 4개만 읽는다 (읽기 전용)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return StandardDict(
            common=_read_sheet(wb[SHEET_COMMON], 4),
            inst=_read_sheet(wb[SHEET_INST], 4),
            code_type=_read_sheet(wb[SHEET_CODE_TYPE], 4),
            code_tail=_read_sheet(wb[SHEET_CODE_TAIL], 4),
        )
    finally:
        wb.close()
