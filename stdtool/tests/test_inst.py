"""기관표준: 파일 읽기(등록 양식·통합시스템 점검결과), 점검·A값, DB(사전 파일)·DBeaver 스크립트, 기관표준 매핑·준용 점검."""
import shutil
import sqlite3
from pathlib import Path

import openpyxl
import pytest

from stdtool import db, inst_db
from stdtool.core import inst_check as ic
from stdtool.core import precheck as pc
from stdtool.paths import BUNDLED_DICT
from stdtool.workbook.inst_reader import SOURCE_PORTAL, SOURCE_TEMPLATE, TEMPLATE, InstStandard, read_inst

ROOT = next((p for p in (Path(r"C:\Data Quality processing\공공데이터 품질관리 메뉴얼 및 참고 파일"),
                         Path(r"C:\Data Quality processing")) if (p / "계룡시_기관표준").exists()),
            Path(r"C:\Data Quality processing"))   # 참고 파일 폴더로 옮긴 뒤에도
GYERYONG, ARTS = ROOT / "계룡시_기관표준", ROOT / "예술경영지원센터_기관표준"


def _template(folder: Path, rows: dict):
    """등록 양식 파일 (머리글에 '*'·공백이 있는 통합시스템 양식처럼)."""
    names = {"용어": "기관표준용어", "단어": "기관표준단어", "도메인": "기관표준도메인", "코드": "기관표준코드"}
    for area, data in rows.items():
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append([h + "*" if i in (0, 2) else h for i, h in enumerate(TEMPLATE[area])])
        for r in data:
            ws.append(r)
        wb.save(folder / f"{names[area]}.xlsx")


def _small(tmp_path, term_domain="연도C4"):
    folder = tmp_path / "테스트시_기관표준"
    folder.mkdir()
    _template(folder, {
        "용어": [["기준연도", None, "CRTR_YR", None, term_domain, None, None, None, "20261007", None],
                ["사업명", None, "BIZ_NM", None, "명V100", None, None, None, "20261007", None]],
        "단어": [["연도", "YR", None, None, "N", None, None, None, "20261007", None],
                ["기준", "CRTR", None, None, "N", None, None, None, "20261007", None]],
        "도메인": [["날짜", "연도", "연도C4", None, "CHAR", "4", None, None, None, None, None, "20261007", None],
                 ["명칭", "명", "명V100", None, "VARCHAR", "100", None, None, None, None, None, "20261007", None]],
        "코드": [[None, "성별코드", "SEX_CD", None, None, None, "M", "남자", "20261007", None],
                [None, "성별코드", "SEX_CD", None, None, None, "M", "남자", "20261007", None],
                [None, "성별코드", "SEX_CD", None, None, None, "-", "기타", "20261007", None]],
    })
    return folder


def test_template_folder_reads_in_template_order(tmp_path):
    inst = read_inst([_small(tmp_path)])
    assert inst.org == "테스트시" and inst.source == SOURCE_TEMPLATE and not inst.results
    assert inst.counts == {"용어": 2, "단어": 2, "도메인": 2, "코드": 3}
    assert inst.area("용어")[0][:5] == ["기준연도", None, "CRTR_YR", None, "연도C4"]
    assert inst.area("코드")[2][6] == "-"   # 코드값 '-'는 값 (통합시스템도 누락으로 보지 않음)


def test_code_completeness_and_a_value_without_common(tmp_path):
    check = ic.check_inst(read_inst([_small(tmp_path)]))
    messages = sorted((i.row, i.message) for i in check.issues if i.area == "코드")
    assert messages == [(2, "중복(코드값)"), (2, "중복(코드값의미)"), (3, "중복(코드값)"), (3, "중복(코드값의미)")]
    assert check.counts["코드"].total == 3 and check.counts["코드"].errors == 2
    assert check.defined and not check.conformed   # 공통표준이 없으면 준용 대상 0건 → 0.9
    assert check.a_value == 0.9 and not check.actual


def test_all_terms_broken_means_not_defined(tmp_path):
    inst = read_inst([_small(tmp_path, term_domain="없는도메인")])
    check = ic.check_inst(inst)
    assert check.counts["용어"].errors == 1 and check.counts["용어"].defined   # 2건 중 1건만 오류 → 정의 인정
    for t in inst.area("용어"):
        t[4] = "없는도메인"
    check = ic.check_inst(inst)
    assert not check.counts["용어"].defined and check.a_value == 0.8
    assert check.item_a("용어") == 0.8 and check.item_a("단어") == 0.9
    assert any("용어" in r and "정의 불인정" in r for r in check.reasons())


@pytest.fixture(scope="module")
def common():
    if not BUNDLED_DICT.exists():
        pytest.skip("사전 파일 없음")
    from stdtool.config import Settings
    from stdtool.pipeline import build_matcher
    with db.FileConn(BUNDLED_DICT) as conn:
        std = db.load_common(conn)
    return build_matcher(std, Settings()), std.domains


@pytest.mark.skipif(not ARTS.exists(), reason="예술경영지원센터 기관표준 파일 없음")
def test_portal_export_matches_program_check(common):
    """통합시스템 점검결과 파일: 결과를 그대로 센 실제 A값 = 프로그램 점검 예상 A값 (영역별 건수까지)."""
    inst = read_inst([ARTS])
    assert inst.source == SOURCE_PORTAL and inst.org == "예술경영지원센터"
    actual = ic.check_inst(inst, *common)
    program = ic.check_inst(inst, *common, use_portal=False)
    assert actual.actual and actual.a_value == 0.8 and actual.verdict == "기관표준 미정의"
    for area in ic.AREAS:
        a, p = actual.counts[area], program.counts[area]
        assert (a.total, a.errors) == (p.total, p.errors), area
    for area in ic.CONFORM_AREAS:
        assert (actual.counts[area].targets, actual.counts[area].conform_errors) == \
               (program.counts[area].targets, program.counts[area].conform_errors), area
    assert actual.counts["코드"].errors == 1681


@pytest.mark.skipif(not GYERYONG.exists(), reason="계룡시 기관표준 파일 없음")
def test_gyeryong_template_expected_a(common):
    check = ic.check_inst(read_inst([GYERYONG]), *common)
    assert check.a_value == 1.0 and check.counts["용어"].targets > 0
    assert [(i.area, i.message) for i in check.issues] == [("단어", "중복(단어명)")]


def test_import_load_and_sheet_in_dict_file(tmp_path):
    path = tmp_path / "dict.sqlite"
    inst = read_inst([_small(tmp_path)], "충청남도 테스트시")
    with db.FileConn(path) as conn:
        inst_db.import_inst(conn, inst)
        inst_db.import_inst(conn, inst)   # 다시 넣어도 그 기관 행만 바뀐다
        assert [o["org"] for o in inst_db.inst_orgs(conn)] == ["충청남도 테스트시"]
        got = inst_db.load_inst(conn, "테스트시")   # 평가대상 목록 이름과 조금 달라도 찾는다
    assert got.org == "충청남도 테스트시" and got.counts == inst.counts and got.area("용어") == inst.area("용어")
    assert inst_db.inst_sheet(got) == [["기준연도", "CRTR_YR", "CHAR", "4"], ["사업명", "BIZ_NM", "VARCHAR", "100"]]
    assert not inst_db.same_org("계룡시", "충청남도 논산시") and inst_db.same_org("충청남도 계룡시", "계룡시")


def test_inst_sql_runs(tmp_path):
    """DBeaver 스크립트의 넣기 부분이 그대로 실행된다 (작은따옴표·빈 값 포함)."""
    inst = read_inst([_small(tmp_path)], "테스트시")
    inst.rows["용어"][1][3] = "기관's 사업 이름"
    sql = inst_db.inst_sql([inst])
    assert "CREATE TABLE IF NOT EXISTS std_dict.inst_term" in sql and "PRIMARY KEY (org_name, row_no)" in sql
    body = sql[sql.index("START TRANSACTION;"):].replace("START TRANSACTION;", "BEGIN;").replace("std_dict.", "")
    conn = sqlite3.connect(":memory:")
    for ddl in inst_db._file_ddl():
        conn.execute(ddl)
    conn.executescript(body)
    assert conn.execute("SELECT COUNT(*) FROM inst_code").fetchone()[0] == 3
    assert conn.execute("SELECT description FROM inst_term WHERE row_no = 2").fetchone()[0] == "기관's 사업 이름"


@pytest.mark.skipif(not BUNDLED_DICT.exists(), reason="사전 파일 없음")
def test_bundled_dict_has_two_orgs_and_load_dicts_fills_inst_sheet(tmp_path):
    with db.FileConn(BUNDLED_DICT) as conn:
        orgs = {o["org"]: o for o in inst_db.inst_orgs(conn)}
        assert {"충청남도 계룡시", "예술경영지원센터"} <= set(orgs)
        dicts = db.load_dicts(conn, "충청남도 계룡시")
        none = db.load_dicts(conn, "한국문화정보원")
    assert len(dicts.inst.rows) == 549 and dicts.inst.header == db.COMMON_HEADER
    assert none.inst.rows == []


def test_db_terms_checked_against_inst_terms():
    """DB표준용어의 기관표준 준용 점검 (p.79): 용어명 또는 영문약어명이 같은 것만 보고, 한 건에 오류 하나."""
    inst_rows = [["기준연도", "CRTR_YR", "CHAR", "4"], ["사업명", "BIZ_NM", "VARCHAR", "100"], ["금액", "AMT", "NUMERIC", "15,2"]]
    terms = [["기준연도", None, "BASE_YR", None, "연도C4"], ["사업이름", None, "BIZ_NM", None, "명V100"],
             ["금액", None, "AMT", None, "금액N10"], ["무관", None, "ETC", None, "명V100"]]
    domains = [[None, None, "연도C4", None, "CHAR", "4"], [None, None, "명V100", None, "VARCHAR", "100"],
               [None, None, "금액N10", None, "NUMERIC", "10"]]
    terms = [t + [None] * 5 for t in terms]
    domains = [d + [None] * 7 for d in domains]
    got = [(i.row, i.code) for i in pc.check_inst_terms(terms, domains, inst_rows)]
    assert got == [(2, "I02"), (3, "I01"), (4, "I04")]
    assert pc.group("I01") == "[ DB표준용어 ] 기관표준용어 준용 점검"
    assert pc.short_group(pc.group("I01")) == "용어 · 기관표준 준용"


def test_newer_bundled_dict_replaces_user_copy(tmp_path, monkeypatch):
    if not BUNDLED_DICT.exists():
        pytest.skip("사전 파일 없음")
    from stdtool.ui import settings as ui_settings
    old = tmp_path / "std_dict.sqlite"
    shutil.copyfile(BUNDLED_DICT, old)
    with db.FileConn(old) as conn, conn.cursor() as cur:
        cur.execute("UPDATE dict_info SET value = '2000-01-01 00:00' WHERE key = 'created_at'")
        conn.commit()
    monkeypatch.setenv("STDTOOL_HOME", str(tmp_path))
    cfg = ui_settings.AppConfig()
    cfg.dict_source, cfg.dict_file = "file", ""
    message = cfg.ensure_dict()
    assert "새 표준 사전" in message
    assert db.read_dict_info(old)["created_at"] == db.read_dict_info(BUNDLED_DICT)["created_at"]
    assert cfg.ensure_dict() == ""   # 이미 같으면 그대로
