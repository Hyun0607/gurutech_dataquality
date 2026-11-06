"""산출물 쓰기: 매크로 양식(템플릿)에 값만 채운다. 사전점검 리포트와 변경 이력도 만든다."""
import re
import warnings
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..core.precheck import (CODES, COUNTED, GROUPS, PrecheckResult, code_label, group, group_headers,
                              issue_row, severity, short_group)
from ..model import ChangeLog

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
YELLOW = PatternFill("solid", fgColor="FFFFFFCC")   # 매크로 RGB(255, 255, 204)
RED = PatternFill("solid", fgColor="FFFFC7CE")
HEADER_FILL = PatternFill("solid", fgColor="FFEDEDED")

# 템플릿 이름 → (머리글 행 수, 산출물 파일명 앞부분)
TEMPLATES = {
    "테이블정의서": (1, "테이블정의서"),
    "컬럼정의서": (1, "컬럼정의서"),
    "1_도메인": (1, "DB표준도메인"),
    "2_용어": (1, "DB표준용어"),
    "3_단어": (1, "DB표준단어"),
    "제거된 항목": (1, "! 제거된항목"),
    "수동등록": (3, "수동등록"),
    "테이블관계정의서": (10, "물리ERD대체_테이블관계정의서"),
    "연계목록": (1, "2-1-5-1 연계데이터 목록 정의서"),
    "연계현황": (2, "2-1-5-2 연계데이터 관리현황 자료"),
}


def safe_name(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", str(text)).strip()


# 산출물 폴더 {기관}_{DB} 아래 하위 폴더 (표준·구조·연계 / 수동등록)
STANDARD_DIR, MANUAL_DIR = "표준_구조_연계", "수동등록"


def output_folder(settings) -> Path:
    return Path(settings.output_dir) / f"{safe_name(settings.org_name)}_{safe_name(settings.db_name)}"


_NUMBER_TEXT = re.compile(r"^-?\d+(\.\d+)?$")


def excel_value(value, number_format: str):
    """VBA가 문자열을 셀에 넣으면 엑셀은 숫자처럼 보이는 값을 숫자로 바꾼다 (텍스트 서식 셀 제외)."""
    if isinstance(value, str) and number_format != "@" and _NUMBER_TEXT.match(value.strip()):
        number = float(value)
        return int(number) if number.is_integer() else number
    return value


def write_template(template: str, rows: list, path: Path, highlights: dict | None = None) -> Path:
    """템플릿 머리글 아래에 rows를 쓴다. 데이터 행 서식은 템플릿의 첫 데이터 행을 따른다.

    highlights: {행 인덱스(0부터): [열 인덱스, ...]} → 노란색 표시
    """
    header_rows, _ = TEMPLATES[template]
    source = TEMPLATE_DIR / f"{template}.xlsx"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(source)
    ws = wb.worksheets[0]
    first = header_rows + 1
    width = max([len(r) for r in rows] + [ws.max_column])
    styles = [copy(ws.cell(first, c + 1)._style) for c in range(width)]
    for r, values in enumerate(rows):
        for c, value in enumerate(values):
            cell = ws.cell(first + r, c + 1)
            cell._style = copy(styles[c])
            cell.value = excel_value(value, cell.number_format)
        for c in (highlights or {}).get(r, []):
            ws.cell(first + r, c + 1).fill = YELLOW
    if not rows:
        for c in range(width):
            ws.cell(first, c + 1).value = None
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def export_standard(result, settings) -> list:
    """정의서_내보내기: {기관명}_{DB명}/표준_구조_연계 폴더에 5개 파일 (매크로의 '! 제거된항목'은 내보내지 않는다)."""
    org, db = safe_name(settings.org_name), safe_name(settings.db_name)
    folder = output_folder(settings) / STANDARD_DIR
    zero_cols = {i: [7] for i in result.definitions.zero_length_rows}           # 컬럼정의서 H
    domain_fix = {i: [4, 5] for i in result.domain_fixed}                        # 1_도메인 E:F
    items = [
        ("테이블정의서", result.definitions.tables, None),
        ("컬럼정의서", result.definitions.columns, zero_cols),
        ("1_도메인", result.domains, domain_fix),
        ("2_용어", result.terms, None),
        ("3_단어", result.words, None),
    ]
    paths = []
    for template, rows, highlights in items:
        prefix = TEMPLATES[template][1]
        paths.append(write_template(template, rows, folder / f"{prefix}_{org}_{db}.xlsx", highlights))
    return paths


def export_manual(manual_rows: list, settings) -> list:
    """수동등록_문서_내보내기: {기관명}_{DB명}/수동등록 폴더에 5,000행 단위로 나눠 저장."""
    db = safe_name(settings.db_name)
    folder = output_folder(settings) / MANUAL_DIR
    size = settings.manual_chunk_size
    chunks = [manual_rows[i: i + size] for i in range(0, len(manual_rows), size)] or [[]]
    paths = []
    for idx, chunk in enumerate(chunks, start=1):
        suffix = "" if len(chunks) == 1 else f"_{idx}"
        paths.append(write_template("수동등록", chunk, folder / f"수동등록_{db}{suffix}.xlsx"))
    return paths


def export_relations(rows: list, settings) -> Path:
    """구조 2-1-4-1 물리 ERD 대체 테이블관계정의서 (core.relation.rows 행)."""
    org, db = safe_name(settings.org_name), safe_name(settings.db_name)
    folder = output_folder(settings) / STANDARD_DIR
    return write_template("테이블관계정의서", rows, folder / f"{TEMPLATES['테이블관계정의서'][1]}_{org}_{db}.xlsx")


def _table(ws, header, rows, widths=None, bad_rows=None, title: str = ""):
    """title이 있으면 1행에 제목, 2행부터 표."""
    top = 1
    if title:
        ws.append([title])
        ws.cell(1, 1).font = Font(bold=True)
        top = 2
    ws.append(header)
    for c in range(1, len(header) + 1):
        cell = ws.cell(top, c)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, r in enumerate(rows):
        ws.append(list(r))
        if bad_rows and i in bad_rows:
            for c in range(1, len(header) + 1):
                ws.cell(top + 1 + i, c).fill = RED
    ws.freeze_panes = f"A{top + 1}"
    if rows:
        ws.auto_filter.ref = f"A{top}:{get_column_letter(len(header))}{len(rows) + top}"
    for c, w in enumerate(widths or [], start=1):
        ws.column_dimensions[get_column_letter(c)].width = w


def write_precheck_report(result: PrecheckResult, path: Path, title: str = "", standard: tuple | None = None) -> Path:
    """standard: (도메인, 용어, 단어) 시트 행. 있으면 상세내역에 통합시스템처럼 표준용어명·영문약어명·도메인명을 쓴다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "요약"
    ws.append([title or "DB표준적용 사전점검"])
    ws.cell(1, 1).font = Font(bold=True, size=13)
    ws.append([])
    summary = [
        ("적용률 산정 기준", result.basis),
        ("전체 컬럼 수", result.total),
        ("오류 컬럼 수", result.error_columns),
        ("예상 적용률(%)", round(result.rate, 1)),
        ("예상 배점(기준2)", result.score),
    ]
    for k, v in summary:
        ws.append([k, v])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.append([])
    ws.append(["완전성 점검", "전체", "오류", "성공", "결과"])
    for c in range(1, 6):
        ws.cell(ws.max_row, c).font = Font(bold=True)
        ws.cell(ws.max_row, c).fill = HEADER_FILL
    for row in result.completeness_rows():
        ws.append(list(row))
        if row[4].startswith("전체 오류"):
            for c in range(1, 6):
                ws.cell(ws.max_row, c).fill = RED
    ws.append([])
    ws.append(["점검", "오류명", "건수", "적용률 반영", "구분", "코드"])
    for c in range(1, 7):
        ws.cell(ws.max_row, c).font = Font(bold=True)
        ws.cell(ws.max_row, c).fill = HEADER_FILL
    for code, message in CODES.items():
        n = result.count(code)
        if n:
            ws.append([group(code), message, n, "예" if code in COUNTED else "", severity(code), code_label(code)])
            if severity(code) == "완전성 오류":
                for c in range(1, 7):
                    ws.cell(ws.max_row, c).fill = RED
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 40

    # 통합시스템 점검 화면별 오류 상세내역 (DB표준 시트가 있을 때만 이름 칸을 채운다)
    for name in dict.fromkeys(GROUPS.values()):
        items = [i for i in result.issues if group(i.code) == name]
        if not items:
            continue
        sheet = wb.create_sheet(short_group(name).replace(" · ", " "))
        if standard is not None and not name.startswith("[ 컬럼정의서") and not name.startswith("[ 메타"):
            headers = group_headers(name)
            rows = [issue_row(i, *standard, name == "프로그램 추가 점검") for i in items]
        else:
            headers = ["행", "키", "오류명", "오류상세내용", "참고"]
            rows = [(i.row, i.key, i.message, i.description, i.detail) for i in items]
        _table(sheet, headers, rows, [8, 30, 26, 22, 30, 50, 30][:len(headers)],
               {n for n, i in enumerate(items) if severity(i.code) == "완전성 오류"}, name)

    for name, rows in (("컬럼정의서 대조", result.columns), ("메타 대조", result.meta)):
        if not rows:
            continue
        sheet = wb.create_sheet(name)
        bad = {i for i, r in enumerate(rows) if r.codes}
        _table(sheet,
               ["행", "테이블", "한글컬럼명", "영문컬럼명", "타입", "길이", "표준용어", "표준용어 영문", "도메인", "도메인 타입", "도메인 길이", "결과"],
               [(r.row, r.table, r.kor, r.eng, r.data_type, r.length, r.term_kor, r.term, r.domain, r.domain_type,
                 r.domain_length, ", ".join(f"{code_label(c)} {CODES[c]}" for c in r.codes) or "정상") for r in rows],
               [7, 22, 22, 24, 11, 8, 22, 24, 16, 11, 9, 40], bad)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def write_currency_report(result, path: Path, title: str = "") -> Path:
    """구조 현행화 검증 (2-1-4-2). result: core.currency.CurrencyResult."""
    from ..core.currency import CODES as CURRENCY_CODES, code_label as currency_label
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "요약"
    ws.append([title or "구조 현행화 검증"])
    ws.cell(1, 1).font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["구분", "일치", "전체", "현행화율(%)"])
    for c in range(1, 5):
        ws.cell(ws.max_row, c).font = Font(bold=True)
        ws.cell(ws.max_row, c).fill = HEADER_FILL
    for name, matched, total, rate in result.rates:
        ws.append([name, matched, total, round(rate, 1)])
        if matched < total:
            for c in range(1, 5):
                ws.cell(ws.max_row, c).fill = RED
    ws.append([])
    for k, v in (("구조 산출물 현행화율(%) (가장 낮은 값)", round(result.rate, 1)), ("예상 배점", result.score)):
        ws.append([k, v])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.append([])
    ws.append(["코드", "내용", "건수"])
    for c in range(1, 4):
        ws.cell(ws.max_row, c).font = Font(bold=True)
        ws.cell(ws.max_row, c).fill = HEADER_FILL
    for code, message in CURRENCY_CODES.items():
        if result.count(code):
            ws.append([currency_label(code), message, result.count(code)])
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 30

    sheet = wb.create_sheet("대조 결과")
    rows = result.rows
    _table(sheet, ["대상", "행", "영문테이블명", "영문컬럼명", "데이터타입", "데이터길이", "상대 타입", "상대 길이", "코드", "결과"],
           [(r.source, r.row, r.table, r.column, r.data_type, r.length, r.other_type, r.other_length, currency_label(r.code), r.message)
            for r in rows],
           [12, 7, 26, 26, 12, 10, 12, 10, 7, 30],
           {i for i, r in enumerate(rows) if r.code})
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def write_change_log(log: ChangeLog, path: Path, notes: list | None = None, text_fallback: list | None = None) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "변경이력"
    _table(ws, ["단계", "시트", "행", "구분", "대상", "변경 전", "변경 후", "사유"],
           [(c.step, c.sheet, c.row, c.action, c.target, c.before, c.after, c.reason) for c in log.items],
           [16, 12, 7, 7, 30, 24, 24, 40])
    if notes:
        sheet = wb.create_sheet("고도화 요약")
        _table(sheet, ["항목", "값", "건수"], notes, [30, 40, 8])
    if text_fallback is not None:
        sheet = wb.create_sheet("문자값 분류")
        _table(sheet, ["영문 꼬리", "컬럼 수", "한글컬럼명 예시", "영문컬럼명 예시",
                       "같은 약어 공통표준단어", "형식단어여부", "공통표준 도메인분류"],
               text_fallback, [12, 8, 40, 40, 20, 10, 16])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
