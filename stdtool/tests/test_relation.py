"""구조 2-1-4-1 테이블관계정의서, 오류 코드 이름, MAX 길이, 산출물 하위 폴더."""
from types import SimpleNamespace

import openpyxl

from stdtool.core.cleanse import fix_max_length
from stdtool.core.currency import code_label as currency_label
from stdtool.core.precheck import code_label
from stdtool.core.relation import infer, rows
from stdtool.model import ChangeLog
from stdtool.workbook.writer import MANUAL_DIR, STANDARD_DIR, export_manual, export_relations


def pairs(relations):
    return [(r.parent, r.parent_column, r.child, r.child_column) for r in relations]


def test_owner_by_table_name_and_tail():
    cols = [("LECTURE", "LECTURE_IDX", "강좌일련번호"), ("LECT_APY", "LECTURE_IDX", "강좌일련번호"),
            ("BBS_MST", "BBS_SN", "게시판일련번호"), ("BBS_DETAIL", "BBS_SN", "게시판일련번호"),
            ("LECTURE", "REG_ID", "등록자아이디"), ("LECT_APY", "REG_ID", "등록자아이디"),       # 공통 컬럼은 관계 아님
            ("CODE", "CODE_IDX", "코드일련번호"), ("ADMIN", "CODE_IDX", "부서코드일련번호"),
            ("LECTURE", "AREA_CODE_IDX", "지역코드일련번호")]                                   # 키를 꼬리로 가진 컬럼
    assert pairs(infer(cols, {})) == [
        ("LECTURE", "LECTURE_IDX", "LECT_APY", "LECTURE_IDX"),
        ("BBS_MST", "BBS_SN", "BBS_DETAIL", "BBS_SN"),
        ("CODE", "CODE_IDX", "LECTURE", "AREA_CODE_IDX"),
        ("CODE", "CODE_IDX", "ADMIN", "CODE_IDX"),
    ]


def test_owner_by_korean_name_backup_and_ambiguous():
    cols = [("RECRUIT", "REC_IDX", "채용공고일련번호"), ("REC_SCRAP", "REC_IDX", "채용공고일련번호"),
            ("RECRUIT_20250213", "REC_IDX", "채용공고일련번호"),                               # 백업 테이블
            ("AT_INQRY", "INQRY_SN", "문의일련번호"), ("ET_INQRY", "INQRY_SN", "문의일련번호")]  # 주인이 둘 → 보류
    found = infer(cols, {"RECRUIT": "채용공고", "REC_SCRAP": "채용스크랩"})
    assert pairs(found) == [("RECRUIT", "REC_IDX", "REC_SCRAP", "REC_IDX")]
    assert found[0].basis == "한글 테이블명 = 컬럼 한글명"


def test_detail_table_is_child():
    cols = [("GK_OP_GO_1_TB", c, "") for c in ("UNQ_NO", "C_IDX", "TTL")] + \
           [("GK_OP_GO_1_SUB_TB", c, "") for c in ("UNQ_NO", "B_IDX", "FILE_NM")] + \
           [("T_ENG_KAMS", "UNQ_NO", ""), ("T_ENG_KAMS_FILE", "UNQ_NO", ""), ("T_ENG_KAMS_FILE", "B_IDX", "")]
    assert pairs(infer(cols, {})) == [("GK_OP_GO_1_TB", "UNQ_NO", "GK_OP_GO_1_SUB_TB", "B_IDX"),
                                      ("T_ENG_KAMS", "UNQ_NO", "T_ENG_KAMS_FILE", "B_IDX")]


def test_rows_and_template(tmp_path):
    found = infer([("A", "A_SN", "가일련번호"), ("B", "A_SN", "가번호")], {})
    info = {"A": ("DB", "OWN", "가", "A"), "B": ("DB", "OWN", "나", "B")}
    kor = {("A", "A_SN"): "가일련번호", ("B", "A_SN"): "가번호"}
    assert rows(found, info, kor) == [[1, "DB", "OWN", "가", "A", "가일련번호", "A_SN", "DB", "OWN", "나", "B", "가번호", "A_SN"]]
    found[0].use = False
    assert rows(found, info, kor) == []
    found[0].use = True
    settings = SimpleNamespace(output_dir=tmp_path, org_name="기관", db_name="디비")
    path = export_relations(rows(found, info, kor), settings)
    assert path.parent == tmp_path / "기관_디비" / STANDARD_DIR
    ws = openpyxl.load_workbook(path).active
    assert ws["B10"].value == "영문 DB명" and ws["A11"].value == 1 and ws["M11"].value == "A_SN"


def test_manual_goes_to_subfolder_with_uploadable_header(tmp_path):
    settings = SimpleNamespace(output_dir=tmp_path, org_name="기관", db_name="디비", manual_chunk_size=5000)
    path = export_manual([[None] * 37], settings)[0]
    assert path == tmp_path / "기관_디비" / MANUAL_DIR / "수동등록_디비.xlsx"
    ws = openpyxl.load_workbook(path).worksheets[0]
    assert ws.title == "Sheet" and "5천 건" not in ws["A1"].value   # 기관메타에 올라간 파일과 같은 머리글


def test_max_length_becomes_one():
    raw = [["", "T", "", "C", "VARBINARY", -1, None], ["", "T", "", "D", "VARCHAR", 10, None]]
    log = ChangeLog()
    fix_max_length(raw, log)
    assert [r[5] for r in raw] == [1, 10] and len(log.items) == 1


def test_code_labels():
    assert [code_label(c) for c in ("D01", "T08", "W04", "C03", "M04")] == \
           ["도메인-01", "용어-08", "단어-04", "컬럼정의서-03", "메타-04"]
    assert currency_label("S05") == "현행화-05" and currency_label("") == ""
