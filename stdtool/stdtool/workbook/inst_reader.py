"""기관표준 파일 읽기: 통합시스템 '엑셀양식 다운로드' 등록 양식, 또는 '엑셀 다운로드'(점검결과 포함) 파일.

용어·단어·도메인·코드 파일 4개(또는 그 일부)를 받아 등록 양식 열 순서의 행으로 맞춘다.
등록 양식 열 순서는 DB표준 정의서와 같아서 core.precheck의 완전성·공통표준 준용 점검을 그대로 쓸 수 있다.
점검결과 파일이면 통합시스템이 낸 완전성·공통표준준용 결과(성공/오류, 결과내용)도 같이 읽는다.
"""
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

AREAS = ("용어", "단어", "도메인", "코드")
# 등록 양식 열 (머리글의 '*'·공백을 뺀 이름). 이 순서가 DB 테이블 열 순서이기도 하다.
TEMPLATE = {
    "용어": ["표준용어명", "영문명", "영문약어명", "용어설명", "표준도메인명", "관리부서명", "표준코드명", "업무분야", "제정일자", "비고"],
    "단어": ["표준단어명", "단어영문약어명", "단어영문명", "단어설명", "형식단어여부", "도메인분류명", "이음동의어목록", "금칙어목록",
           "제정일자", "비고"],
    "도메인": ["표준도메인그룹명", "도메인분류명", "도메인명", "도메인설명", "데이터타입", "데이터길이", "소수점길이", "저장형식",
            "표현형식", "단위", "허용값", "제정일자", "비고"],
    "코드": ["관리부서명", "한글코드명", "영문코드명", "코드설명", "데이터타입", "데이터길이", "코드값", "코드값의미", "제정일자", "비고"],
}
KEY_HEADER = {"용어": "표준용어명", "단어": "표준단어명", "도메인": "도메인명", "코드": "코드값의미"}   # 파일 종류를 알아보는 머리글
RESULT_HEADERS = ["완전성점검결과", "완전성점검결과내용", "공통표준준용결과", "공통표준준용결과내용"]
SOURCE_TEMPLATE, SOURCE_PORTAL = "등록 양식", "통합시스템 점검결과"


class InstError(Exception):
    pass


@dataclass
class InstStandard:
    org: str                                       # 기관명
    name: str = ""                                 # 기관표준명 (점검결과 파일에 있음)
    source: str = SOURCE_TEMPLATE
    files: list = field(default_factory=list)      # 읽은 파일 이름
    rows: dict = field(default_factory=dict)       # 영역 → [등록 양식 열 순서의 행]
    results: dict = field(default_factory=dict)    # 영역 → [(완전성, 완전성내용, 준용, 준용내용)] (점검결과 파일일 때)

    def area(self, name: str) -> list:
        return self.rows.get(name, [])

    @property
    def counts(self) -> dict:
        return {a: len(self.area(a)) for a in AREAS}


def _head(value) -> str:
    return re.sub(r"[\s*]", "", str(value or ""))


def _cell(value, keep_dash: bool = False):
    """점검결과 파일은 빈 칸을 '-'로 낸다. 날짜는 YYYYMMDD 글자 그대로 둔다.
    keep_dash: 코드값은 '-'도 값이다 (통합시스템이 코드값 '-'를 누락으로 보지 않았다, 예술경영지원센터 등락구분코드)."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return None if text == "" or (text == "-" and not keep_dash) else text


def read_inst_file(path) -> tuple:
    """파일 하나 → (영역, 행 목록, 결과 목록 또는 None, 기관명, 기관표준명)."""
    path = Path(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        ws.reset_dimensions()
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    for h, row in enumerate(rows[:6]):
        heads = [_head(v) for v in row]
        area = next((a for a in ("용어", "단어", "코드", "도메인") if KEY_HEADER[a] in heads
                     and (a != "도메인" or "표준용어명" not in heads)), None)
        if area:
            break
    else:
        raise InstError(f"기관표준 용어·단어·도메인·코드 파일이 아닙니다 (머리글을 찾지 못함): {path.name}")
    index = {name: i for i, name in enumerate(heads)}
    missing = [c for c in TEMPLATE[area] if c not in index and c not in ("비고",)]
    if KEY_HEADER[area] in missing:
        raise InstError(f"{path.name}: '{KEY_HEADER[area]}' 열이 없습니다.")
    portal = "완전성점검결과" in index
    out, results, org, std_name = [], [] if portal else None, "", ""
    for row in rows[h + 1:]:
        if not any(v not in (None, "") for v in row):
            continue
        values = [_cell(row[index[c]], keep_dash=c == "코드값") if c in index and index[c] < len(row) else None
                  for c in TEMPLATE[area]]
        if not any(values):
            continue
        out.append(values)
        if portal:
            results.append(tuple(_cell(row[index[c]]) if c in index else None for c in RESULT_HEADERS))
            org = org or _cell(row[index["기관명"]]) if "기관명" in index else org
            std_name = std_name or (_cell(row[index["기관표준명"]]) if "기관표준명" in index else "")
    return area, out, results, org or "", std_name or ""


def read_inst(paths, org: str = "") -> InstStandard:
    """파일·폴더 여러 개 → InstStandard. 폴더면 안의 xlsx를 모두 본다. org를 안 주면 점검결과 파일의 기관명, 없으면 폴더 이름."""
    files = []
    for p in map(Path, paths):
        files += sorted(x for x in p.glob("*.xlsx") if not x.name.startswith("~$")) if p.is_dir() else [p]
    inst = InstStandard(org)
    found_org = ""
    for f in files:
        try:
            area, rows, results, file_org, std_name = read_inst_file(f)
        except InstError:
            if len(files) == 1:
                raise
            continue
        if area in inst.rows:
            raise InstError(f"기관표준{area} 파일이 두 개입니다: {', '.join(inst.files)}, {f.name}")
        inst.rows[area] = rows
        inst.files.append(f.name)
        if results is not None:
            inst.results[area] = results
        found_org = found_org or file_org
        inst.name = inst.name or std_name
    if not inst.rows:
        raise InstError("기관표준 용어·단어·도메인·코드 파일을 찾지 못했습니다.")
    if inst.results and len(inst.results) == len(inst.rows):
        inst.source = SOURCE_PORTAL
    elif inst.results:   # 섞여 있으면 프로그램 점검으로 (결과는 버린다)
        inst.results = {}
    inst.org = org or found_org or (Path(paths[0]).name.split("_")[0] if Path(paths[0]).is_dir()
                                    else Path(paths[0]).parent.name.split("_")[0])
    return inst
