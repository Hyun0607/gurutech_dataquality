"""기관표준 점검 · A값 결과 엑셀 (2-1-3-1): 요약(A값·영역별 건수·이유) · 점검 오류."""
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from ..core.inst_check import CONFORM_AREAS, InstCheck
from .writer import safe_name

HEAD = PatternFill("solid", fgColor="FFF2F4F7")
BAD = PatternFill("solid", fgColor="FFFEF3F2")
SUMMARY_HEADERS = ["구분", "완전성 점검 대상", "완전성 오류", "통과 (대상−오류)", "정의", "공통표준 준용 대상", "준용 오류",
                   "통과 (대상−오류)", "준용", "항목별 A (안내서 p.78 예시)"]
ISSUE_HEADERS = ["영역", "점검", "행", "이름", "오류명", "참고"]


def summary_rows(check: InstCheck) -> list:
    rows = []
    for area, c in check.counts.items():
        conform = area in CONFORM_AREAS
        rows.append([f"기관표준{area}", c.total, c.errors, c.total - c.errors, "인정" if c.defined else "불인정",
                     c.targets if conform else "-", c.conform_errors if conform else "-",
                     c.targets - c.conform_errors if conform else "-",
                     ("인정" if c.conformed else "불인정") if conform else "해당 없음 (행정표준코드)", check.item_a(area)])
    return rows


def file_name(check: InstCheck) -> str:
    return safe_name(f"기관표준점검_A값_{check.inst.org}_{date.today():%Y%m%d}.xlsx")


def write_inst_check(check: InstCheck, path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "요약"
    inst = check.inst
    lines = [("기관", inst.org), ("기관표준명", inst.name or "-"), ("점검 자료", f"{inst.source} · {', '.join(inst.files)}"),
             ("결과 종류", "실제 (통합시스템 점검결과)" if check.actual else "예상 (프로그램 점검, 통합시스템 점검 전)"),
             ("A값", check.a_value), ("판정", check.verdict),
             ("기준", "A=1 공통표준 준용+기관표준 정의 / 0.9 정의했으나 미준용 / 0.8 미정의 · "
                    "정의: 용어·단어·도메인·코드 전부 (완전성 대상−오류) > 0 · 준용: 용어·단어·도메인 전부 (준용 대상−오류) > 0")]
    for i, (k, v) in enumerate(lines, 1):
        ws.cell(i, 1, k).font = Font(bold=True)
        ws.cell(i, 2, v)
    ws.cell(5, 2).font = Font(bold=True, size=14, color="FF1D4ED8")
    top = len(lines) + 2
    for j, h in enumerate(SUMMARY_HEADERS, 1):
        cell = ws.cell(top, j, h)
        cell.font, cell.fill = Font(bold=True), HEAD
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, row in enumerate(summary_rows(check), top + 1):
        for j, v in enumerate(row, 1):
            cell = ws.cell(i, j, v)
            cell.alignment = Alignment(horizontal="center")
            if v == "불인정":
                cell.font, cell.fill = Font(bold=True, color="FFB42318"), BAD
    reasons = check.reasons()
    at = top + len(check.counts) + 2
    ws.cell(at, 1, "A값을 깎는 이유").font = Font(bold=True)
    for k, text in enumerate(reasons or ["없음 — 정의·준용 기준을 모두 통과했습니다."], at + 1):
        ws.cell(k, 1, text)
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 18
    for c in "CDEFGHIJ":
        ws.column_dimensions[c].width = 15
    ws.row_dimensions[top].height = 32

    ws2 = wb.create_sheet("점검 오류")
    ws2.append(ISSUE_HEADERS)
    for cell in ws2[1]:
        cell.font, cell.fill = Font(bold=True), HEAD
    for i in check.issues:
        ws2.append([i.area, i.kind, i.row, i.key, i.message, i.detail])
    for c, w in zip("ABCDEF", (8, 14, 7, 30, 40, 50)):
        ws2.column_dimensions[c].width = w
    ws2.freeze_panes = "A2"
    path = Path(path)
    wb.save(path)
    return path
