"""매크로 파일에서 산출물 양식(머리글 + 서식 행 1개)을 뽑아 templates/ 에 저장한다.

매크로가 시트를 통째로 복사해 내보내던 것과 같은 서식을 쓰기 위한 1회성 작업.
"""
import tempfile
import warnings
from pathlib import Path

import openpyxl

from .writer import TEMPLATE_DIR, TEMPLATES


def _load(path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return openpyxl.load_workbook(path)


def make_templates(macro_workbook: Path, out_dir: Path = TEMPLATE_DIR) -> list:
    wb = _load(macro_workbook)
    for ws in list(wb.worksheets):
        if ws.title not in TEMPLATES:
            wb.remove(ws)
    # 지운 시트를 가리키는 이름 정의가 남으면 엑셀이 복구 경고를 띄운다
    for name in list(wb.defined_names):
        del wb.defined_names[name]
    for ws in wb.worksheets:
        header_rows, _ = TEMPLATES[ws.title]
        style_row = header_rows + 1
        if ws.max_row > style_row:
            ws.delete_rows(style_row + 1, ws.max_row - style_row)
        for cell in ws[style_row]:
            cell.value = None
        ws.sheet_state = "visible"
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        slim = Path(tmp) / "slim.xlsx"
        wb.save(slim)
        paths = []
        for name in TEMPLATES:
            one = _load(slim)
            for ws in list(one.worksheets):
                if ws.title != name:
                    one.remove(ws)
            one.active = 0
            path = out_dir / f"{name}.xlsx"
            one.save(path)
            paths.append(path)
    return paths
