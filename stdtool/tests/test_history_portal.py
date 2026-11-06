"""회차 기록, 통합시스템 결과 읽기(일치 시험용), 메타 파일의 기관·시스템 (BRIS 산출물과 만든 엑셀로)."""
import copy
from dataclasses import replace
from types import SimpleNamespace

import openpyxl
from conftest import load_bris

from stdtool import history
from stdtool.config import Settings
from stdtool.core.currency import CurrencyResult
from stdtool.core.precheck import run_precheck
from stdtool.ui.settings import match_meta
from stdtool.workbook import portal
from stdtool.workbook.reader import read_meta_target


def bris_outcome(tmp_path):
    b = load_bris()
    pre = run_precheck(b["domains"], b["terms"], b["words"], b["columns"])
    result = SimpleNamespace(precheck=pre, currency=CurrencyResult(), domains=b["domains"], terms=b["terms"],
                             words=b["words"], definitions=SimpleNamespace(tables=[], columns=b["columns"]))
    return SimpleNamespace(result=result, value=None, relations=[], link_list=[], folder=tmp_path / "산출물",
                           dict_version="2026-10-29 · 공통표준 8차 2025.11")


def test_record_and_compare_runs(tmp_path):
    db_path = tmp_path / "history.sqlite"
    settings = Settings(org_name="한국농업기술진흥원", db_name="BRIS", system_name="BRIS", meta=tmp_path / "메타.xlsx")
    out = bris_outcome(tmp_path)
    first = history.record(out, settings, db_path, user="팀원")
    items = history.items(first, db_path)
    assert len(items) == len(out.result.precheck.issues)
    assert ("[ 컬럼정의서 ] DB표준 적용 점검", "BOT_ORG_CD", "REG_INST_NM",
            "점검 불가능(연관된 표준용어 완전성점검 오류)") in items or any(x[0].startswith("[ 컬럼정의서 ]") for x in items)
    # 두 번째 회차: 오류 하나를 고치고 하나가 새로 생김
    fixed_one = items[0]
    pre = out.result.precheck
    added_issue = replace(next(i for i in pre.issues if i.area == "컬럼정의서" and "." in i.key), key="NEW_TBL.NEW_COL")
    new_one = history.precheck_items(SimpleNamespace(issues=[added_issue]), None, None, None)[0]
    out2 = copy.copy(out)
    out2.result = copy.copy(out.result)
    out2.result.precheck = copy.copy(pre)
    out2.result.precheck.issues = pre.issues[1:] + [added_issue]
    second = history.record(out2, settings, db_path)
    runs = history.runs("한국농업기술진흥원", "BRIS", db_path)
    assert [r.id for r in runs] == [second, first] and runs[1].source == "메타.xlsx" and runs[1].user == "팀원"
    assert runs[1].dict_version.startswith("2026-10-29") and runs[1].summary["completeness"]["도메인"][0] > 0
    fixed, added, kept = history.compare(history.items(first, db_path), history.items(second, db_path))
    assert fixed == [fixed_one] and added == [new_one] and len(kept) == len(items) - 1
    assert ("완전성 오류", f"{runs[1].total('완전성'):,}", f"{runs[0].total('완전성'):,}") in history.change_text(
        runs[1], runs[0])
    log = history.write_log(tmp_path / "산출물", "한국농업기술진흥원", "BRIS", first, db_path)
    wb = openpyxl.load_workbook(log)
    assert wb["회차"].max_row == 3 and wb["오류"].max_row == len(items) + 1
    history.delete(second, db_path)
    assert [r.id for r in history.runs("한국농업기술진흥원", "BRIS", db_path)] == [first]


def portal_file(path, rows, summary=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["점검일련번호", "표준용어명", "영문약어명", "표준도메인명", "오류명", "오류상세내용"])
    for name, abbr, message, detail in rows:
        ws.append([1, name, abbr, "명V100", message, detail])
    if summary:
        s2 = wb.create_sheet("Sheet2")
        for r in summary:
            s2.append(r)
    wb.save(path)
    return path


ABBR = ("불일치(영문약어명)", "공통표준용어 준용 대상이지만 영문약어명이 불일치하는 경우")
SCREEN = "[ DB표준용어 ] 공통표준용어 준용 점검"


def test_portal_compare_finds_each_kind_of_difference(tmp_path):
    path = portal_file(tmp_path / "통합 문서1.xlsx", [
        ("신청자이름", "APPLICANT_NM", *ABBR),                       # 같음
        ("담당자이름", "MANAGER_NM", *ABBR),                         # 프로그램은 다른 오류명
        ("웹주소", "URL", "유의어 사용(용어명)", "공통표준용어가 아닌 유의어를 사용한 경우"),   # 프로그램에 없는 오류명
        ("사업이름", "BUSINESS_NM", *ABBR)],                         # 프로그램이 놓침
        [("구분", "완전성점검 대상", "완전성점검 오류", "기관표준 준용 대상", "기관표준 준용 오류", "공통표준 준용 대상"),
         ("DB표준용어", 480, 0, 53, 0, 57), ("DB표준단어", 349, 53, 114, 12, 115), ("DB표준코드", 1, 0, "-", "-", "-")])
    sheets, summary, skipped = portal.read_portal([path])
    assert [s.screen for s in sheets] == [SCREEN] and not sheets[0].partial and skipped == []
    ours = [(SCREEN, "신청자이름", "APPLICANT_NM", ABBR[0]), (SCREEN, "담당자이름", "MANAGER_NM", "불일치(용어명)"),
            (SCREEN, "공연명", "PERF_NM", ABBR[0])]
    [d] = portal.compare(sheets, ours)
    assert (d.portal, d.program) == (4, 3)
    assert [x[1] for x in d.only_portal] == ["사업이름"]
    assert [x[1] for x in d.only_program] == ["공연명"]
    assert d.different == [("담당자이름", "MANAGER_NM", "불일치(영문약어명)", "불일치(용어명)")]
    assert [x[1] for x in d.unsupported] == ["웹주소"]
    rows = portal.summary_rows(summary, {"counts": {"[ DB표준단어 ] 완전성 점검": 53},
                                         "completeness": {"용어": [480, 0], "단어": [349, 53]}})
    results = {(n, h): portal.result_text(t, o) for n, h, t, o in rows}
    assert results[("DB표준용어", "완전성점검 대상")] == "같음" and results[("DB표준단어", "완전성점검 오류")] == "같음"
    assert results[("DB표준단어", "기관표준 준용 오류")] == "프로그램에 없는 점검"
    report = portal.write_report([d], rows, tmp_path / "비교.xlsx", "테스트")
    assert openpyxl.load_workbook(report)["시스템에만"].max_row == 2


def test_first_page_only_does_not_blame_program(tmp_path):
    rows = [(f"용어{i}", f"T{i}", *ABBR) for i in range(10)]
    sheets, _, _ = portal.read_portal([portal_file(tmp_path / "첫쪽.xlsx", rows)])
    assert sheets[0].partial
    ours = [(SCREEN, f"용어{i}", f"T{i}", ABBR[0]) for i in range(15)]
    [d] = portal.compare(sheets, ours)
    assert d.same and d.program == 15


def test_meta_target_from_columns_or_title(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "■ 산림청 ▷ 산림공간정보시스템"
    ws["B4"], ws["C4"], ws["O4"], ws["P4"] = "산림청", "산림공간정보시스템", "공간포털DB", "FGIS_PORTAL"
    wb.save(tmp_path / "메타.xlsx")
    found = read_meta_target(tmp_path / "메타.xlsx")
    assert found == {"org": "산림청", "system": "산림공간정보시스템", "db_kor": "공간포털DB", "db_eng": "FGIS_PORTAL"}
    ws["B4"] = ws["C4"] = None
    wb.save(tmp_path / "제목만.xlsx")
    assert read_meta_target(tmp_path / "제목만.xlsx")["system"] == "산림공간정보시스템"

    entries = [{"org": "산림청", "system": "산림공간정보시스템", "db_kor": k, "db_eng": e}
               for k, e in (("공간포털DB", "FGIS_PORTAL"), ("대국민DB", "FGIS_PUB"))]
    assert match_meta(found, entries) == [entries[0]]
    assert len(match_meta({**found, "db_kor": "", "db_eng": "모름"}, entries)) == 2   # DB를 못 정하면 둘 다
    assert match_meta({**found, "system": "새 시스템"}, entries)[0]["system"] == "새 시스템"   # 목록에 없으면 파일 값


def test_meta_systems_by_db():
    from stdtool.model import META_COLS, col
    from stdtool.workbook.reader import meta_systems

    def row(kor, eng, biz):
        r = [None] * META_COLS
        r[col("O")], r[col("P")], r[col("Q")] = kor, eng, biz
        return r
    rows = [row("식물종DB", "PLANT", None), row("식물종DB", "PLANT", "농림>임업·산촌>산림자원보호"),
            row("공통DB", "COMMON", "농림>임업·산촌>산림정보화"), row(None, None, None)]
    assert meta_systems(rows) == [("식물종DB", "PLANT", "농림>임업·산촌>산림자원보호"),
                                  ("공통DB", "COMMON", "농림>임업·산촌>산림정보화")]
