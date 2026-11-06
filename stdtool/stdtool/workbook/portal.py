"""통합시스템 점검 결과 비교: 내려받은 오류 상세내역 엑셀을 읽어 프로그램 결과(회차 오류 목록)와 맞춰 본다.

시트마다 점검 화면 하나. 화면은 머리글(표준용어명·표준단어명…)과 오류명·오류상세내용으로 알아낸다.
요약표(구분·완전성점검 대상·완전성점검 오류…) 시트는 건수만 비교한다.
통합시스템 화면은 한 쪽에 10행이라, 딱 10행인 시트는 첫 쪽만 받은 것으로 보고 '프로그램에만 있음'을 판단하지 않는다.
"""
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from ..core import currency, precheck
from ..vba import s

PAGE_ROWS = 10
EXTRA = "프로그램 추가 점검"

# (오류명, 오류상세내용) → 점검 화면들. 현행화 오류는 상세내용 문구를 몰라 오류명으로만 찾는다.
_BY_TEXT, _BY_MESSAGE = {}, {}
for _code, _message in precheck.CODES.items():
    _screen = precheck.group(_code)
    if _screen == EXTRA:
        continue
    _BY_TEXT.setdefault((_message, precheck.DETAILS[_code]), set()).add(_screen)
    _BY_MESSAGE.setdefault(_message, set()).add(_screen)
for _source, _screen in currency.GROUPS.items():
    for _message in [currency.NO_TARGET[_source], *list(currency.CODES.values())[1:]]:
        _BY_MESSAGE.setdefault(_message, set()).add(_screen)
KNOWN_MESSAGES = set(_BY_MESSAGE)

AREA_HEADERS = [("용어", "표준용어명"), ("단어", "표준단어명"), ("도메인", "표준도메인명")]
NAME_ABBR = {"용어": ("표준용어명", ["영문약어명"]), "단어": ("표준단어명", ["단어영문약어명", "영문약어명"]),
             "도메인": ("표준도메인명", [])}
TABLE_COLUMN = [("영문테이블명", "영문컬럼명"), ("영문 테이블명", "영문 컬럼명"), ("테이블명", "컬럼명")]
SKIP_HEADERS = {"점검일련번호", "오류명", "오류상세내용", "번호", "순번", "행"}


@dataclass
class PortalSheet:
    file: str
    sheet: str
    screen: str                      # 점검 화면 이름 (precheck.group 과 같은 이름)
    items: list                      # [(점검 화면, 이름, 영문약어명, 오류명)]
    has_abbr: bool = True            # 영문약어명(또는 컬럼명) 칸이 있는지
    partial: bool = False            # 딱 10행: 첫 쪽만 받은 것 같음
    headers: list = field(default_factory=list)


@dataclass
class ScreenDiff:
    screen: str
    portal: int                      # 통합시스템 건수 (받은 행 수)
    program: int
    partial: bool
    only_portal: list = field(default_factory=list)     # 시스템에만 있음 (프로그램이 놓침)
    only_program: list = field(default_factory=list)    # 프로그램에만 있음 (프로그램이 더 잡음)
    different: list = field(default_factory=list)       # [(이름, 영문약어명, 통합시스템 오류명, 프로그램 오류명)]
    unsupported: list = field(default_factory=list)     # 프로그램이 내지 않는 오류명

    @property
    def same(self) -> bool:
        return not (self.only_portal or self.only_program or self.different or self.unsupported)


def _screen_of(area: str | None, rows: list) -> str:
    """오류명·오류상세내용 표를 보고 가장 많이 맞는 점검 화면."""
    votes = Counter()
    for message, detail in rows:
        found = _BY_TEXT.get((message, detail)) or _BY_MESSAGE.get(message, set())
        if area:
            found = {x for x in found if f"DB표준{area}" in x} or found
        for screen in found:
            votes[screen] += 1 / len(found)
    if votes:
        return votes.most_common(1)[0][0]
    if area:   # 프로그램에 없는 오류명뿐이면 상세내용으로 짐작
        kind = f"공통표준{area} 준용 점검" if any("준용" in d for _, d in rows) else "완전성 점검"
        return f"[ DB표준{area} ] {kind}"
    return ""


def _key_columns(head: list, area: str | None):
    if area:
        name, abbrs = NAME_ABBR[area]
        return head.index(name), next((head.index(a) for a in abbrs if a in head), None)
    for table, column in TABLE_COLUMN:
        if table in head:
            return head.index(table), head.index(column) if column in head else None
    rest = [i for i, h in enumerate(head) if h and h not in SKIP_HEADERS]
    return (rest[0] if rest else 0), (rest[1] if len(rest) > 1 else None)


def read_portal(paths) -> tuple:
    """([PortalSheet], 요약 {구분: {머리글: 값}}, [읽지 못한 시트 이름])."""
    sheets, summary, skipped = [], {}, []
    for path in paths:
        path = Path(path)
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            for ws in wb.worksheets:
                rows = [r for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]
                if not rows:
                    continue
                head = [s(h) for h in rows[0]]
                if head[0] == "구분" and any("점검" in h for h in head):
                    for r in rows[1:]:
                        summary[s(r[0])] = dict(zip(head[1:], r[1:]))
                    continue
                if "오류명" not in head:
                    skipped.append(f"{path.name} · {ws.title}")
                    continue
                area = next((a for a, h in AREA_HEADERS if h in head), None)
                message_col = head.index("오류명")
                detail_col = head.index("오류상세내용") if "오류상세내용" in head else None
                texts = [(s(r[message_col]), s(r[detail_col]) if detail_col is not None else "") for r in rows[1:]]
                screen = _screen_of(area, texts)
                name_col, abbr_col = _key_columns(head, area)
                items = [(screen, s(r[name_col]), s(r[abbr_col]) if abbr_col is not None else "", s(r[message_col]))
                         for r in rows[1:]]
                sheets.append(PortalSheet(path.name, ws.title, screen, items, abbr_col is not None,
                                          len(items) == PAGE_ROWS, head))
        finally:
            wb.close()
    return sheets, summary, skipped


def _key(item, use_abbr=True):
    _, name, abbr, message = item
    return s(name).upper(), s(abbr).upper() if use_abbr else "", message


def compare(sheets: list, program_items: list) -> list:
    """점검 화면별 차이. 같은 화면을 여러 시트(쪽)로 받았으면 합쳐서 본다."""
    out = []
    by_screen = {}
    for sheet in sheets:
        by_screen.setdefault(sheet.screen, []).append(sheet)
    for screen, parts in by_screen.items():
        portal = [x for p in parts for x in p.items]
        use_abbr = all(p.has_abbr for p in parts)
        partial = all(p.partial for p in parts)
        ours = [x for x in program_items if x[0] == screen]
        diff = ScreenDiff(screen, len(portal), len(ours), partial)
        diff.unsupported = [x for x in portal if x[3] not in KNOWN_MESSAGES]
        portal = [x for x in portal if x[3] in KNOWN_MESSAGES]
        left = Counter(_key(x, use_abbr) for x in ours)
        for x in portal:
            k = _key(x, use_abbr)
            if left[k]:
                left[k] -= 1
            else:
                diff.only_portal.append(x)
        rest = []
        for x in ours:
            k = _key(x, use_abbr)
            if left[k]:
                left[k] -= 1
                rest.append(x)
        # 이름·영문약어명은 같고 오류명만 다른 것은 따로
        for x in list(diff.only_portal):
            match = next((y for y in rest if _key(y, use_abbr)[:2] == _key(x, use_abbr)[:2]), None)
            if match:
                diff.only_portal.remove(x)
                rest.remove(match)
                diff.different.append((x[1], x[2], x[3], match[3]))
        diff.only_program = [] if partial else rest
        out.append(diff)
    return out


# 요약표 열 → 프로그램 회차 요약에서 같은 숫자를 꺼내는 방법
def summary_rows(summary: dict, run_summary: dict) -> list:
    """[(구분, 항목, 통합시스템, 프로그램 또는 None(프로그램에 없는 점검))]."""
    counts = run_summary.get("counts", {})
    completeness = run_summary.get("completeness", {})
    out = []
    for name, values in summary.items():
        area = name.replace("DB표준", "")
        for header, portal in values.items():
            if portal in (None, "-", ""):
                continue
            if header == "완전성점검 대상":
                ours = completeness.get(area, [None])[0]
            elif header == "완전성점검 오류":
                ours = counts.get(f"[ DB표준{area} ] 완전성 점검", 0) if area in completeness else None
            elif header == "공통표준 준용 오류":
                ours = counts.get(f"[ DB표준{area} ] 공통표준{area} 준용 점검", 0)
            else:
                ours = None   # 준용 대상 수·기관표준 준용은 프로그램이 세지 않는다
            out.append((name, header, portal, ours))
    return out


def write_report(diffs: list, rows: list, path: Path, title: str = "") -> Path:
    """비교 결과 엑셀: 요약, 시스템에만, 프로그램에만, 오류명 다름, 프로그램 미지원."""
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "요약"
    if title:
        ws.append([title])
        ws.append([])
    ws.append(["점검 화면", "통합시스템", "프로그램", "시스템에만", "프로그램에만", "오류명 다름", "프로그램 미지원", "비고"])
    for d in diffs:
        ws.append([d.screen, d.portal, d.program, len(d.only_portal), len(d.only_program), len(d.different),
                   len(d.unsupported), "첫 쪽만 받음: '프로그램에만'은 판단하지 않음" if d.partial else ""])
    if rows:
        ws.append([])
        ws.append(["요약표 구분", "항목", "통합시스템", "프로그램", "결과"])
        for name, header, portal, ours in rows:
            ws.append([name, header, portal, ours, result_text(portal, ours)])
    for title_, pick in (("시스템에만", lambda d: d.only_portal), ("프로그램에만", lambda d: d.only_program),
                         ("프로그램 미지원", lambda d: d.unsupported)):
        sheet = wb.create_sheet(title_)
        sheet.append(["점검 화면", "이름", "영문약어명", "오류명"])
        for d in diffs:
            for x in pick(d):
                sheet.append(list(x))
    sheet = wb.create_sheet("오류명 다름")
    sheet.append(["점검 화면", "이름", "영문약어명", "통합시스템 오류명", "프로그램 오류명"])
    for d in diffs:
        for x in d.different:
            sheet.append([d.screen, *x])
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            if row and row[0].value in ("점검 화면", "요약표 구분") or (row and row[0].row == 1 and sheet.title != "요약"):
                for cell in row:
                    cell.font = Font(bold=True)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def result_text(portal, ours) -> str:
    if ours is None:
        return "프로그램에 없는 점검"
    try:
        return "같음" if int(portal) == int(ours) else "다름"
    except (TypeError, ValueError):
        return ""
