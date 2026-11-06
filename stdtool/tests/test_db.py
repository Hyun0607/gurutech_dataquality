"""표준 사전 DB 가져오기 → 다시 읽기. MySQL 대신 SQL 4가지(DELETE·INSERT·SELECT·COUNT)만 흉내 내는 가짜 접속으로 확인한다.

DB 열은 모두 문자열이므로 넣을 때 값을 문자열로 바꿔 저장한다 (실제 MySQL VARCHAR와 같게).
"""
import re

import pytest

from stdtool import db
from stdtool.config import Settings
from stdtool.dictionary import Sheet
from stdtool.pipeline import run
from stdtool.workbook.reader import read_meta
from tests.conftest import COMMON_DIR, MACRO_XLSM
from tests.test_parity_bris_real import META


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        tables = self.conn.tables
        keep = (lambda r: r.get("added_by") != params[0]) if params else (lambda r: False)
        if m := re.fullmatch(r"DELETE FROM (\w+)( WHERE added_by = %s)?", sql):
            tables[m[1]] = [r for r in tables.get(m[1], []) if keep(r)]
        elif sql.startswith("CREATE TABLE IF NOT EXISTS"):
            tables.setdefault(sql.split()[5], [])
        elif "information_schema.tables" in sql:
            self.result = [(1 if params[0] in tables else 0,)]
        elif m := re.fullmatch(r"SELECT COUNT\(\*\) FROM (\w+)( WHERE added_by = %s)?", sql):
            self.result = [(sum(1 for r in tables.get(m[1], []) if not keep(r)),)]
        elif m := re.fullmatch(r"SELECT (.+) FROM (\w+) ORDER BY (\w+)", sql):
            cols = m[1].split(", ")
            rows = sorted(tables.get(m[2], []), key=lambda r: int(r[m[3]]))
            self.result = [tuple(r.get(c) for c in cols) for r in rows]
        else:
            raise AssertionError(sql)

    def executemany(self, sql, rows):
        m = re.fullmatch(r"INSERT INTO (\w+) \((.+)\) VALUES \(.+\)", sql)
        cols = m[2].split(", ")
        self.conn.tables[m[1]] += [{c: None if v is None else str(v) for c, v in zip(cols, r)} for r in rows]

    def fetchone(self):
        return self.result[0]

    def fetchall(self):
        return self.result


class FakeConn:
    def __init__(self):
        self.tables = {}
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


@pytest.fixture(scope="module")
def loaded():
    if not MACRO_XLSM.exists() or not (COMMON_DIR / "공통표준용어.xlsx").exists():
        pytest.skip("매크로 파일 또는 공통표준 원본 없음")
    conn = FakeConn()
    db.import_macro(conn, MACRO_XLSM)
    db.import_common(conn, {t: COMMON_DIR / f for t, f in db.COMMON_FILES.items()})
    return conn


def test_status_counts(loaded, macro_dict):
    counts = db.status(loaded)
    assert counts["macro_common"] == len(macro_dict.common.rows)
    assert counts["code_type"] == len(macro_dict.code_type.rows)
    assert counts["common_term"] > 10000 and counts["common_domain"] > 100
    assert all(r["added_by"] == "MACRO" for r in loaded.tables["code_tail"])


def test_dicts_same_as_macro_sheets(loaded, macro_dict):
    got = db.load_dicts(loaded)
    as_text = lambda rows: [[None if v is None else str(v) for v in r] for r in rows]  # noqa: E731
    for name in ("common", "code_type", "code_tail"):
        assert getattr(got, name).header == getattr(macro_dict, name).header
        assert getattr(got, name).rows == as_text(getattr(macro_dict, name).rows)
    assert got.inst.rows == []


def test_common_same_as_excel(loaded, common_real):
    got = db.load_common(loaded)
    as_text = lambda v: None if v is None else str(v)  # noqa: E731
    assert [(t.name, t.abbr, t.domain, t.synonyms) for t in got.terms] == \
           [(t.name, t.abbr, t.domain, t.synonyms) for t in common_real.terms]
    assert [(t.data_type, t.length, t.scale) for t in got.terms] == \
           [tuple(map(as_text, (t.data_type, t.length, t.scale))) for t in common_real.terms]
    assert got.words == common_real.words


def test_added_codes_survive_import(loaded, macro_dict):
    added = {"seq": "1001", "type_name": "UUID", "type_abbr": "UUID", "added_by": "codetable_additions"}
    loaded.tables["code_type"].append(added)
    report = db.import_macro(loaded, MACRO_XLSM)
    assert str(report["code_type"]).startswith("건너뜀")
    db.import_macro(loaded, MACRO_XLSM, replace_codes=True)
    assert added in loaded.tables["code_type"]
    assert len(loaded.tables["code_type"]) == len(macro_dict.code_type.rows) + 1
    assert db.load_dicts(loaded).code_type.rows[-1] == ["1001", "UUID", "UUID", None]
    loaded.tables["code_type"].remove(added)


def test_macro_rows_added_after_additions(macro_dict):
    """추가 행을 먼저 넣고 나중에 매크로를 가져와도 매크로 행이 채워진다."""
    if not MACRO_XLSM.exists():
        pytest.skip("매크로 파일 없음")
    conn = FakeConn()
    conn.tables["code_tail"] = [{"seq": "1001", "tail": "TELNO", "domain_class": "전화번호", "added_by": "codetable_additions"}]
    report = db.import_macro(conn, MACRO_XLSM)
    assert report["code_tail"] == len(macro_dict.code_tail.rows)
    assert db.load_dicts(conn).code_tail.rows[-1][:3] == ["1001", "TELNO", "전화번호"]


@pytest.mark.parametrize("enhanced", [False, True])
def test_pipeline_same_from_db(loaded, macro_dict, common_real, enhanced):
    if not META.exists():
        pytest.skip(f"BRIS 메타 없음: {META}")
    settings = Settings(org_name="한국농업기술진흥원", db_name="(농진원)생명자원정보서비스(BRIS)",
                        enact_date=20170715, inst_std="N", enhanced=enhanced)
    excel_dicts = type(macro_dict)(macro_dict.common, Sheet(macro_dict.inst.header, []),
                                   macro_dict.code_type, macro_dict.code_tail)
    a = run(read_meta(META), excel_dicts, settings, common=common_real if enhanced else None)
    b = run(read_meta(META), db.load_dicts(loaded), settings, common=db.load_common(loaded) if enhanced else None)
    for attr in ("domains", "terms", "words", "manual"):
        assert getattr(a, attr) == getattr(b, attr), attr
    assert a.definitions.columns == b.definitions.columns
    assert a.definitions.tables == b.definitions.tables


def test_eval_list_round_trip(tmp_path):
    import openpyxl
    path = tmp_path / "list.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in [("기관명", "순번", "정보시스템명", "한글 DB명", "영문 DB명"),          # 머리글 행은 건너뜀
              ("한국농업기술진흥원", 10, "(농진원)생명자원정보서비스(BRIS)", "공객용BRISDB", "brisopen"),
              ("산림청", 6, "산림공간정보시스템", "공간정보_공간포털DB", "FDMS_​FGLS_DB")]:
        ws.append(r)
    wb.save(path)
    conn = FakeConn()
    assert db.load_eval_list(conn) == []
    assert db.import_eval_list(conn, path) == 2
    got = db.load_eval_list(conn)
    assert [(e["org"], e["system"], e["db_eng"]) for e in got] == [
        ("한국농업기술진흥원", "(농진원)생명자원정보서비스(BRIS)", "brisopen"), ("산림청", "산림공간정보시스템", "FDMS_FGLS_DB")]
    assert db.status(conn)["eval_db"] == 2


def test_dict_file_same_as_db(loaded, tmp_path):
    """사전 파일(팀원 배포용)로 만들어 읽어도 DB에서 읽은 것과 같다."""
    from dataclasses import replace

    from stdtool.config import DbSettings
    path = tmp_path / "std_dict.sqlite"
    info = db.export_file(loaded, path, "test", user="관리자")
    assert info["created_by"] == "관리자" and info["common_round"].endswith("2025.11")
    with db.connect(replace(DbSettings(), file=str(path))) as conn:
        assert db.status(conn) == db.status(loaded)
        as_text = lambda d: [[[None if v is None else str(v) for v in r] for r in getattr(d, n).rows]  # noqa: E731
                             for n in ("common", "code_type", "code_tail")]   # 가짜 DB는 숫자도 글자로 준다
        assert as_text(db.load_dicts(conn)) == as_text(db.load_dicts(loaded))
        got, want = db.load_common(conn), db.load_common(loaded)
        assert (got.terms, got.words, got.domains) == (want.terms, want.words, want.domains)
        assert db.dict_info(conn)["created_at"] == info["created_at"]


def test_newer_dict_and_install(loaded, tmp_path):
    shared, mine = tmp_path / "공유", tmp_path / "내 사전.sqlite"
    shared.mkdir()
    old = db.export_file(loaded, mine, "test")
    assert db.newer_dict(shared, old) is None
    (shared / "메모.sqlite").write_text("사전 아님")          # 사전 파일이 아니면 건너뜀
    new = db.export_file(loaded, shared / "std_dict_new.sqlite", "test")
    with db.FileConn(shared / "std_dict_new.sqlite") as conn:  # 같은 분에 만들어도 나중 것으로 보이게
        with conn.cursor() as cur:
            cur.execute("UPDATE dict_info SET value = %s WHERE key = 'created_at'", ("9999-12-31 00:00",))
        conn.commit()
    path, info = db.newer_dict(shared, old)
    assert path.name == "std_dict_new.sqlite" and info["created_at"] == "9999-12-31 00:00"
    assert db.install_dict(path, mine)["created_at"] == "9999-12-31 00:00"
    assert db.read_dict_info(mine)["created_at"] == "9999-12-31 00:00"
    with pytest.raises(db.DbError):
        db.install_dict(shared / "메모.sqlite", mine)
    assert new["source"] == "test"


def test_common_round():
    assert db.common_round(["5차(2022.07월)", "8차(2025.11월)", "-", None, "7차(2024-11)"]) == "8차 2025.11"
    assert db.common_round([]) == ""
