"""연계 (2-1-5-1 목록 정의서, 2-1-5-2 관리현황)."""
import random
from datetime import date

from conftest import place

from stdtool.core import linkage
from stdtool.model import META_COLS


def meta_row(table, column, kor, dtype="VARCHAR", length=10, pk=None, fk=None, personal=None):
    return place(META_COLS, {"C": "기획마루", "P": "KDAMDB", "Z": table + "한글", "AA": table, "AI": kor, "AJ": column,
                             "AM": personal, "AO": dtype, "AP": length, "AR": pk, "AS": fk})


def test_recommend_rules():
    rows = [meta_row("T", "LOGIN_ID", "로그인아이디"),
            meta_row("T", "USER_PSWD", "사용자비밀번호"),
            meta_row("T", "REG_DT", "등록일시", "DATE", None),
            meta_row("T", "INST_CD", "기관코드"),
            meta_row("T", "RMK", "비고", pk="Y"),
            meta_row("T", "USER_NM", "사용자명", personal="Y"),
            meta_row("T", "PRJ_NM", "과제명"),
            meta_row("T", "CN", "내용"),
            meta_row("T", "LOGIN_ID", "로그인아이디")]       # 같은 컬럼은 한 번만
    got = [(c.column, c.selected, c.reason) for c in linkage.candidates_from_meta(rows, "한국연구재단", "기획마루")]
    assert got == [("LOGIN_ID", True, "식별자·코드"), ("USER_PSWD", False, "관리·민감 컬럼"),
                   ("REG_DT", False, "관리·민감 컬럼"), ("INST_CD", True, "식별자·코드"), ("RMK", True, "PK"),
                   ("USER_NM", False, "개인정보"), ("PRJ_NM", True, "명칭"), ("CN", False, "")]


def test_rows_follow_sample_layout():
    c = linkage.candidates_from_meta([meta_row("Z_PROPOSER_PRIVACY", "LOGIN_ID", "회원 로그인 아이디", "VARCHAR2", 60)],
                                     "한국연구재단", "기획마루")[0]
    assert linkage.list_rows([c]) == [[1, "송신", "회원 로그인 아이디", "실시간", "회원 로그인 아이디",
                                       "회원 로그인 아이디 실시간 연계", "VARCHAR2", "60", "KDAMDB",
                                       "Z_PROPOSER_PRIVACY", "LOGIN_ID", "한국연구재단", "한국연구재단"]]
    times = linkage.check_times(1, date(2026, 10, 27), rng=random.Random(1))
    row = linkage.status_rows([c], times)[0]
    assert row[:4] == [1, "기획마루", "송신", "회원 로그인 아이디"]
    assert row[5:] == ["실시간", None, "오류 없음", "수시 점검 기조 유지", "한국연구재단", "한국연구재단", None]
    assert len(row[4]) == len("2026.06.28. 15:30:09") and row[4].startswith("2026.")


def test_check_times_range_weekday_and_sorted():
    today = date(2026, 10, 27)
    times = linkage.check_times(200, today, rng=random.Random(7))
    assert times == sorted(times)
    assert all(date(2026, 6, 1) <= t.date() <= today and t.weekday() < 5 and 9 <= t.hour < 18 for t in times)


def test_review_overrides_selection():
    rows = [meta_row("T", "LOGIN_ID", "로그인아이디"), meta_row("T", "CN", "내용")]
    cands = linkage.candidates_from_meta(rows, "기관", "DB")
    linkage.apply_review(cands, {("T", "LOGIN_ID"): {"selected": False}, ("T", "CN"): {"selected": True, "cycle": "매일"}})
    assert [(c.column, c.selected, c.cycle) for c in cands] == [("LOGIN_ID", False, "실시간"), ("CN", True, "매일")]


def test_pick_one_keeps_single_row():
    rows = [meta_row("T", "PRJ_NM", "과제명"), meta_row("T", "INST_CD", "기관코드"), meta_row("T", "RMK", "비고", pk="Y"),
            meta_row("T", "LOGIN_ID", "로그인아이디")]
    cands = linkage.candidates_from_meta(rows, "기관", "DB")
    linkage.pick_one(cands)
    assert [c.column for c in cands if c.selected] == ["RMK"]          # PK가 먼저
    linkage.pick_one(cands[:2])
    assert [c.column for c in cands[:2] if c.selected] == ["INST_CD"]  # 다음은 식별자·코드
    linkage.pick_one([c for c in cands if c.column == "PRJ_NM"])
    assert cands[0].selected                                          # 명칭밖에 없으면 명칭


def test_candidates_follow_column_definitions():
    from stdtool.model import COLUMN_DEF_COLS, TABLE_DEF_COLS
    columns = [place(COLUMN_DEF_COLS, {"A": "T_USER", "B": "로그인아이디", "C": "LOGIN_ID", "G": "VARCHAR", "H": 60}),
               place(COLUMN_DEF_COLS, {"A": "T_USER", "B": "사용자명", "C": "USER_NM", "G": "VARCHAR", "H": 100})]
    tables = [place(TABLE_DEF_COLS, {"B": "사용자", "C": "T_USER"})]
    meta = [meta_row("t_user", "user_nm", "사용자명", personal="Y")]      # 메타 쪽은 소문자여도 짝을 찾는다
    got = linkage.candidates_from_definitions(columns, tables, meta, "기관", "시스템", "ENGDB", "시스템명")
    assert [(c.table, c.column, c.table_kor, c.selected, c.reason) for c in got] == [
        ("T_USER", "LOGIN_ID", "사용자", True, "식별자·코드"), ("T_USER", "USER_NM", "사용자", False, "개인정보")]
    assert got[0].db_name == "ENGDB" and got[0].system == "시스템명"     # 메타에 없으면 평가대상 목록 값
    assert got[1].db_name == "KDAMDB" and got[1].system == "기획마루"   # 메타에 있으면 메타 값
