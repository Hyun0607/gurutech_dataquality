"""예방적 품질관리 파일: 기준 엑셀 읽기, 사업단 이행점검 대상 파일 읽기, 결과 엑셀 쓰기.

사업단 파일: '(N차)발주단계'·'(N차)완료단계' 시트, 머리글(순번·기관유형·기관명·접수코드·사업명·사업시작일·사업종료일·
사전협의신청일·비고)이 몇 번째 행에 있어도 찾는다. 평가연도는 파일 이름의 'YYYY년', 없으면 신청일로 정한다.
"""
import re
import shutil
import warnings
from datetime import date, datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..core.preventive import (C_EXPECT, C_LATE, C_MOVE, C_NEXT_ORDER, C_NEXT_YEAR, C_PLANNED, DONE, ITEMS, ORDER, Criteria,
                               Detail, Item, Project, Requirement, Round, won_text)
from ..paths import user_dir
from ..vba import s
from .writer import HEADER_FILL, TEMPLATE_DIR

CRITERIA_NAME = "예방적품질관리_기준.xlsx"
CRITERIA_PATH = TEMPLATE_DIR / CRITERIA_NAME      # 프로그램에 같이 넣은 기준
HEADERS = {"org_type": "기관유형", "org": "기관명", "code": "접수코드", "name": "사업명", "start": "사업시작일",
           "end": "사업종료일", "applied": "사전협의신청일", "note": "비고"}
YELLOW = PatternFill("solid", fgColor="FFFFF4CC")
BLUE = PatternFill("solid", fgColor="FFE8F0FE")
GREEN = PatternFill("solid", fgColor="FFE6F4EA")


class ReadError(Exception):
    pass


def _load(path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return openpyxl.load_workbook(path, read_only=True, data_only=True)


def _date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    m = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", s(value))
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _words(text) -> list:
    return [w.strip() for w in re.split(r"[,\n]", s(text)) if w.strip()]


# ---------------------------------------------------------------------------
# 기준
# ---------------------------------------------------------------------------

def _band_limits(band: str) -> tuple:
    """'1억 이상 10억 미만' → (1e8, 1e9). '모든 금액' → (None, None)."""
    low = re.search(r"([\d.]+)억\s*이상", band)
    high = re.search(r"([\d.]+)억\s*미만", band)
    return (int(float(low.group(1)) * 1e8) if low else None, int(float(high.group(1)) * 1e8) if high else None)


def criteria_path() -> Path:
    """사용자 폴더에 고친 기준이 있고 프로그램 기준보다 새것이면 그것, 아니면 프로그램 기준 (새 버전의 기준이 더 새로우면 그쪽)."""
    mine = user_dir() / CRITERIA_NAME
    if mine.exists() and mine.stat().st_mtime >= CRITERIA_PATH.stat().st_mtime:
        return mine
    return CRITERIA_PATH


def editable_criteria() -> Path:
    """고쳐 쓸 기준: 사용자 폴더 복사본 (없거나 프로그램 기준이 더 새로우면 새로 복사)."""
    mine = user_dir() / CRITERIA_NAME
    if criteria_path() != mine:
        shutil.copy2(CRITERIA_PATH, mine)
        mine.touch()
    return mine


def load_criteria(path: Path | None = None) -> Criteria:
    path = path or criteria_path()
    wb = _load(path)

    def rows(name):
        return [r for r in wb[name].iter_rows(min_row=3, values_only=True) if any(v is not None for v in r)]

    try:
        rounds = sorted((Round(int(r[1]), int(r[2]), _date(r[3]), _date(r[4]), _date(r[5]), _date(r[6]), s(r[7]))
                         for r in rows("회차") if r[1] and r[5] and r[6]), key=lambda x: (x.year, x.no))
        type_words = [(s(r[1]), _words(r[2])) for r in rows("사업유형") if s(r[1])]
        transfer = [s(r[1]) for r in rows("이관") if s(r[1])]
        matrix, bands = {}, {}
        for r in rows("적용표"):
            kind, band, basis = s(r[1]), s(r[2]), s(r[3])
            if not kind:
                continue
            matrix[(kind, band)] = {code: s(v).upper() if s(v).upper() == "O" else s(v) for code, v in zip(ITEMS, r[4:13])}
            bands.setdefault(kind, []).append((band, *_band_limits(band), basis))
        items = {s(r[1]): Item(s(r[1]), s(r[2]), s(r[3]), s(r[4]), _words(r[5]), s(r[6]), _words(r[7]), _words(r[8]),
                      _words(r[9]) if len(r) > 9 else [], s(r[10]) if len(r) > 10 else "",
                      _words(r[11]) if len(r) > 11 else [])
                 for r in rows("지표") if s(r[1])}
        reqs = [Requirement(*(s(v) for v in r[1:9])) for r in rows("요구사항 문안") if s(r[1])] \
            if "요구사항 문안" in wb.sheetnames else []
        details = [Detail(s(r[1]), s(r[2]), s(r[3]), _words(r[4]), _words(r[5]), _words(r[6]), s(r[7]), s(r[8]))
                   for r in rows("세부기준") if s(r[1])] if "세부기준" in wb.sheetnames else []
        details = [Detail(s(r[1]), s(r[2]), s(r[3]), _words(r[4]), _words(r[5]), _words(r[6]), s(r[7]), s(r[8]))
                   for r in rows("세부기준") if s(r[1])] if "세부기준" in wb.sheetnames else []
    finally:
        wb.close()
    if not rounds:
        raise ReadError(f"기준 엑셀 '회차' 시트에 기간이 없습니다: {path}")
    return Criteria(rounds, type_words, transfer, matrix, bands, items, reqs, details)


# ---------------------------------------------------------------------------
# 사업단 대상 파일
# ---------------------------------------------------------------------------

def _year_from(path: Path, projects: list) -> int:
    m = re.search(r"(20\d\d)\s*년", Path(path).name)
    if m:
        return int(m.group(1))
    dates = [p.applied for p in projects if p.applied]
    return max(dates).year if dates else date.today().year


IRM_HEADERS = {"org_type": "기관유형1", "org": "기관명", "code": "접수코드", "name": "사업명", "start": "사업시작일",
               "end": "사업종료일", "done_end": "사업완료종료일", "irm_type": "사전협의사업유형", "budget": "예산총액(천원)",
               "applied": "사전협의신청일", "progress": "현시점진행현황", "result": "결과유형", "review": "검토완료(예정)일",
               "reflect": "반영계획등록여부(기한)", "check_target": "이행점검대상사업여부", "db": "DB의견수"}


def read_irm(path, criteria: Criteria | None = None) -> list:
    """IRM 사전협의(총괄) 목록 → [Project] (사업단 대상 파일보다 먼저 기준1·2 대상을 예측). 형식이 아니면 []."""
    from ..core.preventive import irm_projects
    wb = _load(path)
    try:
        ws = wb.worksheets[0]
        ws.reset_dimensions()
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    head = next((i for i, r in enumerate(rows[:10]) if {"결과유형", "검토완료(예정)일"} <= {re.sub(r"\s", "", s(v)) for v in r}), None)
    if head is None:
        return []
    names = [re.sub(r"\s", "", s(v)) for v in rows[head]]
    index = {k: names.index(h) for k, h in IRM_HEADERS.items() if h in names}

    def get(r, k):
        i = index.get(k)
        return r[i] if i is not None and i < len(r) else None

    def number(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    items = []
    for r in rows[head + 1:]:
        if not s(get(r, "name")).strip():
            continue
        budget = number(get(r, "budget"))
        reflect = re.search(r"\d{4}-\d{2}-\d{2}", s(get(r, "reflect")))
        items.append({"org_type": s(get(r, "org_type")).strip(), "org": s(get(r, "org")).strip(),
                      "code": s(get(r, "code")).strip(), "name": s(get(r, "name")).strip(),
                      "start": _date(get(r, "start")), "end": _date(get(r, "end")), "done_end": _date(get(r, "done_end")),
                      "applied": _date(get(r, "applied")), "progress": s(get(r, "progress")).strip(),
                      "result": s(get(r, "result")).strip(), "review": _date(get(r, "review")),
                      "reflect": _date(reflect.group(0)) if reflect else None, "db": number(get(r, "db")),
                      "check_target": s(get(r, "check_target")).strip().upper(),
                      "irm_type": s(get(r, "irm_type")).strip(), "amount": int(budget * 1000) if budget else None})
    return irm_projects(items, criteria or load_criteria())


def read_targets(path, criteria: Criteria | None = None) -> list:
    """사업단 이행점검 대상 파일 → [Project]. IRM 사전협의(총괄) 목록이면 그 목록으로 예측한 [Project].
    둘 다 아니면 ReadError."""
    wb = _load(path)
    out = []
    try:
        for ws in wb.worksheets:
            m = re.search(r"\((\d+)\s*차\)\s*(발주|완료)", ws.title)
            if not m:
                continue
            ws.reset_dimensions()
            rows = list(ws.iter_rows(values_only=True))
            head = next((i for i, r in enumerate(rows[:15]) if "사업명" in [s(v).strip() for v in r]), None)
            if head is None:
                continue
            names = [re.sub(r"\s", "", s(v)) for v in rows[head]]
            index = {k: names.index(h) for k, h in HEADERS.items() if h in names}
            if "name" not in index or "org" not in index:
                continue

            def get(r, k):
                i = index.get(k)
                return r[i] if i is not None and i < len(r) else None

            for r in rows[head + 1:]:
                if not s(get(r, "name")).strip():
                    continue
                out.append(Project(0, int(m.group(1)), ORDER if m.group(2) == "발주" else DONE, s(get(r, "org_type")).strip(),
                                   s(get(r, "org")).strip(), s(get(r, "code")).strip(), s(get(r, "name")).strip(),
                                   _date(get(r, "start")), _date(get(r, "end")), _date(get(r, "applied")),
                                   s(get(r, "note")).strip()))
    finally:
        wb.close()
    if not out:
        irm = read_irm(path, criteria)
        if irm:
            return irm
        raise ReadError("사업단 이행점검 대상 파일이나 IRM 사전협의(총괄) 목록이 아닙니다. "
                        "'(N차)발주단계'·'(N차)완료단계' 시트, 또는 '결과유형'·'검토완료(예정)일' 머리글이 필요합니다.")
    year = _year_from(path, out)
    for p in out:
        p.year = year
    return out


# ---------------------------------------------------------------------------
# 결과 엑셀
# ---------------------------------------------------------------------------

BASE_HEADERS = ["단계", "기관유형", "기관명", "접수코드", "사업명", "사업시작일", "사업종료일", "사전협의신청일"]
JUDGE_HEADERS = ["분류(예측)", "회차(예측)", "판정 근거", "사업유형", "유형 근거", "금액", "금액구간", "이관", "대응 지표 수", "비고"]


def project_row(j) -> list:
    p = j.project
    bands = ", ".join(b for _, b in j.bands)
    return [p.stage_label, p.org_type, p.org, p.code, p.name, p.start, p.end, p.applied,
            j.category, j.target, p.reason, "+".join(j.types), j.type_basis, won_text(j.amount), bands,
            "Y" if j.transfer else "N", len(j.required), "; ".join(j.flags)]


def _sheet(wb, title, header, rows, widths, fills=None):
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in range(1, len(header) + 1):
        cell = ws.cell(1, c)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, r in enumerate(rows):
        ws.append(list(r))
        for c, v in enumerate(r, start=1):
            if isinstance(v, date):
                ws.cell(i + 2, c).number_format = "yyyy-mm-dd"
        if fills and fills[i]:
            for c in range(1, len(header) + 1):
                ws.cell(i + 2, c).fill = fills[i]
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{len(rows) + 1}"
    for c, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
    return ws


def _fill(j):
    if not j.project.needs_action:
        return None
    if any(k in j.category for k in (C_MOVE, C_PLANNED, C_EXPECT)):
        return BLUE
    if j.category in (C_NEXT_YEAR, C_NEXT_ORDER):
        return GREEN
    if j.category == C_LATE or (j.project.needs_action and j.flags):
        return YELLOW
    return None


def write_targets(judgements: list, criteria: Criteria, path: Path, source: str, summary: list) -> Path:
    """관리 기관 사업만 쓴다. summary: [(항목, 내용)]."""
    mine = [j for j in judgements if j.managed]
    item_heads = [f"{c} {criteria.items[c].name}" if c in criteria.items else c for c in ITEMS]
    header = BASE_HEADERS + JUDGE_HEADERS + item_heads
    widths = [14, 12, 20, 13, 46, 11, 11, 11, 26, 11, 30, 16, 26, 9, 16, 5, 7, 34] + [9] * len(ITEMS)

    def rows(sel):
        return [project_row(j) + [j.mark(c) for c in ITEMS] for j in sel]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "요약"
    ws.append(["예방적 품질관리 대상 사업 분류"])
    ws.cell(1, 1).font = Font(bold=True, size=13)
    for k, v in [("사업단 파일", source), *summary]:
        ws.append([k, v])
    ws.append([])
    ws.append(["지표 칸", "O = 대응 / △ = 금액을 알아야 정해짐 / - = 해당 없음"])
    ws.append(["색", "파랑 = 대상 예측·다음 회차 완료 예상 / 초록 = 내년 후보 / 노랑 = 확인필요"])
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 90

    _sheet(wb, "관리 기관 사업", header, rows(mine), widths, [_fill(j) for j in mine])
    expect = [j for j in mine if C_EXPECT in j.category]
    if expect:
        _sheet(wb, "대상 예측", header, rows(expect), widths)
    move = [j for j in mine if C_MOVE in j.category or C_PLANNED in j.category]
    _sheet(wb, "완료 전환 예상", header, rows(move), widths)
    nxt = [j for j in mine if j.category in (C_NEXT_YEAR, C_NEXT_ORDER)]
    _sheet(wb, "내년 후보", header, rows(nxt), widths)
    check = [j for j in mine if j.project.needs_action and j.flags]
    _sheet(wb, "확인필요", header, rows(check), widths)
    items = [(i.code, i.name, i.area, i.evidence, i.screen) for i in criteria.items.values()]
    ws = _sheet(wb, "지표별 필요 산출물", ["코드", "진단항목", "영역", "완료단계 산출물(택1)", "stdtool 화면"], items,
                [7, 30, 14, 100, 14])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# 문서 점검 결과 (발주단계 RFP / 완료단계 보고서)
# ---------------------------------------------------------------------------

PORTAL_OK, PORTAL_FIX = "점검완료", "보완필요"   # 통합시스템 예방적 품질관리 결과 표기
MATERIALS = TEMPLATE_DIR / "예방적품질관리_자료"   # 사업단 완료단계 산출물 예시·가이드 모음 (가이드 폴더에 복사)
AREAS = [("1. 데이터 표준", ["1.1", "1.2"]), ("2. 데이터 구조", ["2.1", "2.2", "2.3"]), ("3. 데이터 값", ["3.1", "3.2"]),
         ("4. 데이터 관리체계", ["4.1", "4.2"])]
CELL_OK, CELL_NA = "점검 완료", "-"
CELL_FIX = {"발주": "보완 필요", "완료": "보완서류 필요"}   # 사업단 이행점검 결과 표기 (발주는 RFP 요구사항, 완료는 산출물)
RED_BOLD = Font(bold=True, size=9, color="FFFF0000")
FIX_FILL = PatternFill("solid", fgColor="FFFFFF00")
GRAY = PatternFill("solid", fgColor="FFEFEFEF")


def portal_mark(result) -> str:
    return PORTAL_OK if result.status in ("반영", "확인됨") else PORTAL_FIX


def check_record(check, judgement, name: str, year: int, round_no: int, criteria: Criteria) -> dict:
    """점검 한 건을 기록(dict)으로: 기관별 이행점검 결과 엑셀과 가이드 폴더가 쓴다. 문서 본문은 넣지 않는다 (근거 한 줄만)."""
    from ..core.preventive import name_key, org_key
    p = judgement.project if judgement else None
    day = lambda d: d.isoformat() if d else ""   # noqa: E731
    types = judgement.types if judgement else []
    results = []
    for r in check.results:
        s_ = r.suggestion
        results.append({"code": r.code, "name": r.name, "need": r.need, "status": r.status, "mark": portal_mark(r),
                        "evidence": r.evidence, "where": r.where, "comment": r.comment,
                        "suggestion": s_ and {"kind": s_.kind, "band": s_.band, "rid": s_.rid, "name": s_.name,
                                              "definition": s_.definition, "detail": s_.detail, "output": s_.output}})
    return {"kind": check.kind, "year": year, "round": round_no,
            "org": p.org if p else "", "org_key": org_key(p.org) if p else "", "name_key": name_key(p.name if p else name),
            "stage": f"({round_no}차){check.kind}단계" if round_no else f"{check.kind}단계(자체점검)",
            "code": p.code if p else "", "name": p.name if p else name, "start": day(p.start) if p else "",
            "end": day(p.end) if p else "", "applied": day(p.applied) if p else "", "types": types,
            "amount": check.amount or (judgement.amount if judgement else None), "source": check.file, "results": results,
            "criteria": [{"code": d.code, "item": d.item, "text": d.text, "status": d.status, "evidence": d.evidence,
                          "where": d.where, "opinion": d.opinion, "needed": d.needed, "edited": d.edited,
                          "covered_by": getattr(d, "covered_by", "")}
                         for d in getattr(check, "criteria", [])]}


def _note(record) -> str:
    fixes = [r["code"] for r in record["results"] if r["mark"] == PORTAL_FIX]
    if not record["results"]:
        return "대응 지표 없음"
    if not fixes:
        return "대응 지표 모두 점검 완료"
    what = "RFP에 데이터 요구사항(DAR) 보완 필요" if record["kind"] == "발주" else "일부 점검지표 자료가 없음"
    return f"{what} ({', '.join(fixes)} → '보완 사항' 시트)"


def _border(ws, top, bottom, left, right):
    from openpyxl.styles import Border, Side
    thin = Side(style="thin")
    for row in ws.iter_rows(min_row=top, max_row=bottom, min_col=left, max_col=right):
        for cell in row:
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)


def _results_sheet(wb, records, criteria):
    """1. 사업 진단결과: 사업단 이행점검 결과 양식 (점검단계·접수코드·사업명·날짜·지표 9개·비고)."""
    ws = wb.create_sheet("사업 진단결과")
    ws["A1"] = "1. 사업 진단결과"
    ws["A1"].font = Font(bold=True, size=14)
    ws.row_dimensions[1].height = 43.5
    fixed = ["점검단계", "접수코드", "사업명", "사업시작일", "사업종료일", "사전협의신청일"]
    head = Font(bold=True, size=10)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for c, title in enumerate(fixed, start=1):
        ws.cell(2, c, title)
        ws.merge_cells(start_row=2, end_row=3, start_column=c, end_column=c)
    col = len(fixed) + 1
    for area, codes in AREAS:
        ws.cell(2, col, area)
        ws.merge_cells(start_row=2, end_row=2, start_column=col, end_column=col + len(codes) - 1)
        for code in codes:
            item = criteria.items.get(code)
            ws.cell(3, col, f"{code} {item.name if item else ''}")
            col += 1
    extra = ["비고", "사업유형", "금액"]
    for i, title in enumerate(extra):
        ws.cell(2, col + i, title)
        ws.merge_cells(start_row=2, end_row=3, start_column=col + i, end_column=col + i)
    last = col + len(extra) - 1
    for row in ws.iter_rows(min_row=2, max_row=3, max_col=last):
        for cell in row:
            cell.font, cell.alignment, cell.fill = head, center, GRAY
    ws.row_dimensions[2].height, ws.row_dimensions[3].height = 26.25, 45
    for n, rec in enumerate(records, start=4):
        marks = {r["code"]: r["mark"] for r in rec["results"]}
        values = [rec["stage"], rec["code"], rec["name"], rec["start"], rec["end"], rec["applied"]]
        for code in ITEMS:
            values.append(CELL_NA if code not in marks else CELL_OK if marks[code] == PORTAL_OK else CELL_FIX[rec["kind"]])
        values += [_note(rec), " + ".join(rec["types"]), won_text(rec["amount"])]
        for c, v in enumerate(values, start=1):
            cell = ws.cell(n, c, v)
            cell.font = Font(size=9)
            cell.alignment = Alignment(horizontal="left" if c in (3, col) else "center", vertical="center", wrap_text=True)
            if v == CELL_FIX[rec["kind"]]:
                cell.font, cell.fill = RED_BOLD, FIX_FILL
        if any(m == PORTAL_FIX for m in marks.values()):
            ws.cell(n, col).font = RED_BOLD
        ws.row_dimensions[n].height = 51.75
    _border(ws, 2, max(3, len(records) + 3), 1, last)
    for letter, width in zip("ABCDEF", (14, 12, 48, 11.5, 11.5, 13)):
        ws.column_dimensions[letter].width = width
    for c in range(len(fixed) + 1, col):
        ws.column_dimensions[get_column_letter(c)].width = 14.5
    ws.column_dimensions[get_column_letter(col)].width = 48
    ws.column_dimensions[get_column_letter(col + 1)].width = 16
    ws.column_dimensions[get_column_letter(col + 2)].width = 10
    ws.freeze_panes = "D4"


def _howto(rec, r, criteria) -> str:
    item = criteria.items.get(r["code"])
    if rec["kind"] == "발주":
        s_ = r["suggestion"]
        if not s_:
            return r["comment"]
        return (f"RFP에 아래 데이터 요구사항을 추가하세요 (매뉴얼 3.2.2 {s_['kind']} {s_['band']} 기준, 고유번호는 RFP 순서에 맞게)\n"
                f"요구사항 고유번호: {s_['rid']}\n요구사항 명칭: {s_['name']}\n정의: {s_['definition']}\n"
                f"세부내용:\n{s_['detail']}\n산출정보: {s_['output']}")
    screen = f"\n※ stdtool '{item.screen}' 화면에서 만들 수 있습니다." if item and item.screen else ""
    return f"아래 중 하나를 IRM에 등록하세요.\n{item.evidence if item else ''}{screen}"


def _state(r) -> str:
    if r["status"] in ("미반영", "미확인"):
        return f"{r['status']} — " + r["comment"].split("\n")[0]
    where = f" ({r['where']})" if r["where"] else ""
    return f"{r['status']}{where} — {r['evidence'] or r['comment'].splitlines()[0]}"


def _fix_sheet(wb, records, criteria):
    """2. 보완 사항: 보완할 지표마다 진단기준 ①·② 두 줄, 현재 상태와 보완 방법 (사업단 '제출 보완서류' 양식)."""
    ws = wb.create_sheet("보완 사항")
    ws["A1"] = "2. 보완 사항"
    ws["A1"].font = Font(bold=True, size=14)
    ws.row_dimensions[1].height = 36
    header = ["사업명", "진단 사항", "지표", "검토 항목", "현재 상태", "보완 방법"]
    for c, title in enumerate(header, start=1):
        cell = ws.cell(2, c, title)
        cell.font, cell.fill = Font(bold=True, size=10), GRAY
        cell.alignment = Alignment(horizontal="center", vertical="center")
    row = 3
    wrap = Alignment(vertical="center", wrap_text=True)
    for rec in records:
        for r in rec["results"]:
            if r["mark"] != PORTAL_FIX:
                continue
            item = criteria.items.get(r["code"])
            lines = [x for x in (item.criteria if item else "").split("\n") if x.strip()] or [r["name"]]
            top = row
            for i, line in enumerate(lines, start=1):
                ws.cell(row, 3, f"{r['code']}({i})")
                ws.cell(row, 4, re.sub(r"^[①②③]\s*", "", line))
                row += 1
            for c, v in ((1, rec["name"]), (2, f"{r['code']} {r['name']}"), (5, _state(r)), (6, _howto(rec, r, criteria))):
                ws.cell(top, c, v)
                if row - 1 > top:
                    ws.merge_cells(start_row=top, end_row=row - 1, start_column=c, end_column=c)
            for rr in range(top, row):
                for c in range(1, 7):
                    ws.cell(rr, c).alignment = Alignment(horizontal="center", vertical="center") if c == 3 else wrap
                    ws.cell(rr, c).font = Font(size=10)
            ws.cell(top, 6).font = Font(size=10, bold=rec["kind"] == "완료")
            lines_needed = _howto(rec, r, criteria).count("\n") + 2
            for rr in range(top, row):
                ws.row_dimensions[rr].height = max(30, 15 * lines_needed / (row - top))
    if row == 3:
        ws.cell(3, 1, "보완할 지표가 없습니다. 대응 지표가 모두 점검 완료로 예상됩니다.")
        row = 4
    _border(ws, 2, row - 1, 1, 6)
    for letter, width in zip("ABCDEF", (34, 22, 9, 44, 44, 90)):
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "A3"


def _detail_sheet(wb, records):
    rows = [(rec["stage"], rec["name"], r["code"], r["name"], r["need"], r["status"], r["mark"], r["evidence"], r["where"],
             r["comment"].split("\n")[0], rec["source"]) for rec in records for r in rec["results"]]
    ws = _sheet(wb, "지표별 상세", ["단계", "사업명", "코드", "진단항목", "구분", "결과", "예상", "근거", "위치", "의견", "점검 파일"],
                rows, [14, 34, 7, 24, 11, 9, 9, 50, 24, 60, 36], [None if r[6] == PORTAL_OK else YELLOW for r in rows])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


PORTAL_ITEM = {"1.1": "데이터 표준화", "1.2": "데이터 표준 관리", "2.1": "데이터 구조 설계", "2.2": "데이터 구조 검증",
               "2.3": "데이터 구조 관리", "3.1": "데이터 값 검증", "3.2": "이관 데이터 값 검증", "4.1": "데이터 품질관리 체계",
               "4.2": "데이터 개방 관리체계 수립"}   # 사업단 '사업 완료단계 진단결과' 머리글 이름


def ratio_text(record) -> str:
    marks = [c["status"] for c in record.get("criteria", []) if c["status"] in ("Y", "N")]
    return f"{marks.count('Y') / len(marks):.0%}" if marks else "-"


def _portal_done_sheets(wb, records, criteria):
    """사업단 '사업 완료단계 진단결과' 양식: 완료단계 진단결과(기준 18개 Y/N/- + 진단결과반영비율) · 검토의견(기준별 줄)."""
    codes = [c["code"] for c in records[0]["criteria"]]
    heads = [f"{code[:3]} {PORTAL_ITEM.get(code[:3], '')}{code[3:]}" for code in codes]
    rows = [[r["stage"], r["year"], "", r["org"], r["code"], r["name"], *[c["status"] for c in r["criteria"]], ratio_text(r)]
            for r in records]
    ws = _sheet(wb, "완료단계 진단결과", ["점검단계", "평가연도", "기관코드", "기관명", "사업코드", "사업명", *heads, "진단결과반영비율"],
                rows, [16, 9, 9, 16, 13, 46] + [15] * len(codes) + [12])
    for row in ws.iter_rows(min_row=2):
        for cell in row[6:]:
            cell.alignment = Alignment(horizontal="center", vertical="center")
            if cell.value == "N":
                cell.font = Font(bold=True, color="FFFF0000")
    for c in range(7, 7 + len(codes)):
        ws.cell(1, c).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 45
    lines = []
    for r in records:
        for c in r["criteria"]:
            if c.get("edited"):
                note = "(사람이 고침) " + (c["opinion"] if c["status"] == "N" else "")
            elif c["status"] == "N":
                note = c["opinion"]
            elif c.get("covered_by"):
                note = f"{c['covered_by']} 충족으로 지표 충족 ((1)·(2) 중 하나만 충족하면 됨)"
            else:
                note = f"(프로그램 확인) {c['where']} · {c['evidence']}" if c["status"] == "Y" and c["evidence"] else ""
            lines.append([r["stage"], "", r["org"], r["code"], r["name"], c["code"], c["status"], note,
                          c["needed"] if c["status"] == "N" else ""])
    ws = _sheet(wb, "검토의견", ["점검단계", "기관코드", "기관명", "사업코드", "사업명", "검토항목", "검토결과", "검토의견",
                                "사업담당자 제출 산출물"], lines, [16, 9, 16, 13, 40, 9, 9, 70, 70],
                [YELLOW if x[6] == "N" else None for x in lines])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def inspection_name(org: str, name: str, rounds) -> str:
    """'예방적 품질관리 진단 이행점검(1차)_한국문화정보원_20260724.xlsx' (사업단 결과 파일과 같은 이름 짓기).
    rounds: 회차 번호 또는 목록 — 발주·완료가 여러 회차면 '1·2차'."""
    from .writer import safe_name
    numbers = sorted({n for n in ([rounds] if isinstance(rounds, int) else rounds) if n})
    stage = "·".join(map(str, numbers)) + "차" if numbers else "자체점검"
    return safe_name(f"예방적 품질관리 진단 이행점검({stage})_{org or name[:30]}_{date.today():%Y%m%d}.xlsx")


def write_inspection(records: list, criteria: Criteria, path: Path) -> Path:
    """기관별 이행점검 결과 엑셀: 1. 사업 진단결과 · 2. 보완 사항 · 지표별 상세."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _results_sheet(wb, records, criteria)
    _fix_sheet(wb, records, criteria)
    done = [r for r in records if r.get("criteria")]
    if done:
        _portal_done_sheets(wb, done, criteria)
    _detail_sheet(wb, records)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _free_dir(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while (path.parent / f"{path.name}_{n}").exists():
        n += 1
    return path.parent / f"{path.name}_{n}"


def _copy_examples(source: Path, sub: Path):
    """증빙기준 그림은 지표 폴더 맨 위에, 예시 산출물은 '예시' 폴더 한 단계에 (Windows 경로 길이 260자를 넘지 않게).
    이름이 겹치면 원래 하위 폴더 이름을 앞에 붙인다."""
    target = sub / "예시"
    for f in sorted(x for x in source.rglob("*") if x.is_file() and not x.name.startswith("~$")):
        if f.parent == source and "기준" in f.stem:
            shutil.copy2(f, sub / f.name)
            continue
        target.mkdir(exist_ok=True)
        name = f.name if not (target / f.name).exists() else f"{f.parent.name}_{f.name}"
        shutil.copy2(f, target / name)


def build_guide_folder(record: dict, criteria: Criteria, base: Path, inspection: Path | None = None,
                       materials: Path = MATERIALS) -> Path:
    """완료단계 가이드 폴더: 보완이 필요한 지표만 하위 폴더를 만들고, 그 안에 가이드 모음(그 지표를 보완할 수 있는 자료)·
    증빙기준 그림·제출 안내·사업단 예시 산출물을 넣는다. 맨 위에는 '※ 전체 지표 대응 가능 산출물'(감리·완료보고서 예시).
    보완할 지표가 없으면 ValueError."""
    fixes = [r for r in record["results"] if r["mark"] != PORTAL_OK]
    if not fixes:
        raise ValueError("보완이 필요한 지표가 없습니다. 대응 지표가 모두 점검 완료로 예상됩니다.")
    from .writer import safe_name
    who = "_".join(x for x in (record["org"], record["name"][:24]) if x)
    folder = _free_dir(Path(base) / safe_name(f"예방적품질관리_완료가이드_{who}"))
    folder.mkdir(parents=True)
    examples = materials / "산출물 예시"
    for r in fixes:
        item = criteria.items.get(r["code"])
        tag = "보완필요"
        sub = folder / safe_name(f"{r['code']} {r['name']}")
        sub.mkdir()
        source = next((d for d in examples.iterdir() if d.is_dir() and d.name.startswith(r["code"] + " ")), None) \
            if examples.exists() else None
        if source:
            _copy_examples(source, sub)
        for name in (item.guides if item else []):
            if (materials / "가이드" / name).exists():
                (sub / "가이드").mkdir(exist_ok=True)
                shutil.copy2(materials / "가이드" / name, sub / "가이드" / name)
        found = f"{r['where']} · {r['evidence']}" if r["evidence"] else "보고서·산출물에서 찾지 못했습니다."
        text = [f"{r['code']} {r['name']}  [{tag}]", "",
                "■ 진단기준", item.criteria if item else "", "",
                "■ 인정되는 산출물", item.evidence if item else "", "",
                "■ 프로그램이 찾은 것", found, ""]
        if tag == "보완필요":
            text += ["■ 할 일", "위 '인정되는 산출물' 중 하나를 이 사업 내용으로 작성해 IRM(이행점검 화면)에 등록하세요.",
                     "'예시' 폴더의 파일은 사업단 예시 양식입니다. 'DB명_', '기관명_', '_예시'를 그대로 내면 인정되지 않을 수 있습니다.", ""]
        if item and item.screen:
            text += [f"■ stdtool에서 만들 수 있는 화면: {item.screen}", ""]
        (sub / "제출 안내.txt").write_text("\n".join(text), encoding="utf-8-sig")
    common = examples / "※ 전체 지표 대응 가능 산출물"
    if common.exists():
        shutil.copytree(common, folder / "※ 전체 지표 대응 가능 산출물 (감리·완료보고서 예시)")
    if inspection and Path(inspection).exists():
        shutil.copy2(inspection, folder / Path(inspection).name)
    return folder
