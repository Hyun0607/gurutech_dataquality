"""매크로 단계별 동작 (VBA 코드와 같은 결과인지)."""
from conftest import make_dict, place

from stdtool.core.cleanse import meta_to_raw, refine
from stdtool.core.consolidate import build_definitions, dedupe_terms
from stdtool.core.generate import make_domains, make_terms, make_words
from stdtool.core.manual import build_manual, copy_definitions_to_meta
from stdtool.core.mapping import apply_dbstd, common_mapping, inst_mapping
from stdtool.core.naming import DomainNamer
from stdtool.model import META_COLS, TERM_COLS, ChangeLog, col


def raw_row(a, b, c, d, e, f):
    return [a, b, c, d, e, f, None]


def test_meta_to_raw_picks_columns_until_last_table_name():
    meta = [place(META_COLS, {"Z": "테이블", "AA": "TB", "AI": "컬럼", "AJ": "COL", "AO": "VARCHAR", "AP": 10}),
            place(META_COLS, {"AI": "끝"})]
    assert meta_to_raw(meta) == [["테이블", "TB", "컬럼", "COL", "VARCHAR", 10, None]]


def test_refine_uppercases_cuts_scale_and_numbers_same_korean_table():
    raw = [raw_row("고객", "tb_a", "고객 명(1)", "cust_nm", "varchar", None),
           raw_row("고객", "tb_b", "금액", "amt", " number ", "10,2"),
           raw_row("주문", "tb_c", "번호", "no", "", None)]
    refine(raw, ChangeLog())
    assert raw[0][:6] == ["고객_01", "TB_A", "고객명1", "CUST_NM", "VARCHAR", 0]
    assert raw[1][:6] == ["고객_02", "TB_B", "금액", "AMT", "NUMBER", 10]
    assert raw[2][5] == 0 and raw[2][0] == "주문"


def test_common_mapping_fills_other_name_and_overwrites_type():
    common = [["고객명", "CUST_NM", "VARCHAR", 100], ["금액", "AMT", "NUMBER", 15]]
    raw = [raw_row("T", "T", "고객명", "CNM", "CHAR", 5),     # 한글만 일치 → 영문 채움 + 타입 적용
           raw_row("T", "T", "돈", "AMT", "INT", 4),          # 영문만 일치 → 한글 채움
           raw_row("T", "T", "없음", "NONE", "INT", 4)]
    common_mapping(raw, make_dict(common).common, ChangeLog())
    assert raw[0][2:6] == ["고객명", "CUST_NM", "VARCHAR", 100]
    assert raw[1][2:6] == ["금액", "AMT", "NUMBER", 15]
    assert raw[2][2:6] == ["없음", "NONE", "INT", 4]


def test_inst_mapping_skipped_when_flag_n_and_uses_clean_text_when_y():
    inst = [["고객명", "CUST_NM", "VARCHAR", 50]]
    raw = [raw_row("T", "T", "고객명", "X", "CHAR", 1)]
    inst_mapping(raw, make_dict(inst=inst).inst, "N", ChangeLog())
    assert raw[0][3] == "X"
    inst_mapping(raw, make_dict(inst=inst).inst, "Y", ChangeLog())
    assert raw[0][3] == "CUSTNM"   # 매크로 CleanText 정규화 결과 그대로


def test_domain_and_term_names_follow_macro_rule():
    namer = DomainNamer(make_dict())
    raw = [raw_row("T", "T", "고객명", "CUST_NM", "VARCHAR", 100),
           raw_row("T", "T", "등록일", "REG_DT", "DATE", 0),
           raw_row("T", "T", "성별", "SXDC", "VARCHAR", 10),
           raw_row("T", "T", "고객명", "CUST_NM", "VARCHAR", 100)]
    domains = make_domains(raw, namer, 20170715, ChangeLog())
    assert [d[col("C")] for d in domains] == ["명칭VC100", "날짜DT0", "문자값VC10"]
    assert all(d[col("L")] == 20170715 for d in domains)
    terms = make_terms(raw, namer, 20170715)
    assert [t[col("E")] for t in terms] == ["명칭VC100", "날짜DT0", "문자값VC10", "명칭VC100"]


def test_unregistered_type_uses_type_name():
    namer = DomainNamer(make_dict())
    assert namer.name("문자값", "UUID", 36) == "문자값UUID36"


def test_words_take_most_frequent_korean_and_keep_bottom_row():
    terms = [place(TERM_COLS, {"A": "고객명", "C": "CUST_NM"}),
             place(TERM_COLS, {"A": "고객번호", "C": "CUST_NO"}),
             place(TERM_COLS, {"A": "고객번호", "C": "CUST_NO"})]
    words = make_words(terms, 1, ChangeLog())
    assert [(w[0], w[1]) for w in words] == [("고객명", "NM"), ("고객번호", "CUST"), ("고객번호", "NO")]


def test_term_dedupe_keeps_most_frequent_domain_and_last_row():
    terms = [place(TERM_COLS, {"A": "고객명", "C": "CUST_NM", "E": "명칭VC100"}),
             place(TERM_COLS, {"A": "고객이름", "C": "CUST_NM", "E": "명칭VC50"}),
             place(TERM_COLS, {"A": "고객성명", "C": "CUST_NM", "E": "명칭VC100"}),
             place(TERM_COLS, {"A": "주소", "C": "ADDR", "E": "주소VC200"})]
    out = dedupe_terms(terms, ChangeLog())
    assert [(t[0], t[2], t[4]) for t in out] == [("고객명", "CUST_NM", "명칭VC100"), ("주소", "ADDR", "주소VC200")]


def test_term_dedupe_removes_exact_duplicates_before_counting():
    """완전 중복을 먼저 지우므로 같은 행 2개는 1표가 되고, 동률이면 먼저 나온 도메인이 남는다."""
    terms = [place(TERM_COLS, {"A": "고객명", "C": "CUST_NM", "E": "명칭VC100"}),
             place(TERM_COLS, {"A": "고객명", "C": "CUST_NM", "E": "명칭VC50"}),
             place(TERM_COLS, {"A": "고객명", "C": "CUST_NM", "E": "명칭VC100"})]
    out = dedupe_terms(terms, ChangeLog())
    assert [t[4] for t in out] == ["명칭VC50"]


def test_apply_dbstd_maps_kor_then_eng():
    terms = [place(TERM_COLS, {"A": "고객명", "C": "CUST_NM"})]
    raw = [raw_row("T", "T", "고객명", "CNAME", "VARCHAR", 10)]
    apply_dbstd(raw, terms, ChangeLog())
    assert raw[0][3] == "CUST_NM"


def test_definitions_dedupe_columns_and_track_removed_rows():
    raw = [raw_row("고객", "TB", "고객명", "CUST_NM", "VARCHAR", 100),
           raw_row("고객", "TB", "고객명", "CUST_NM", "VARCHAR", 100),
           raw_row("고객", "TB", "비고", "RMK", "", "")]
    defs = build_definitions(raw, ChangeLog())
    assert len(defs.tables) == 1 and len(defs.columns) == 2
    assert defs.removed_raw_index == [1] and defs.removed[0][5] == 3
    assert defs.columns[1][col("G")] == "VARCHAR" and defs.columns[1][col("H")] == 0
    assert defs.zero_length_rows == {1}


def test_manual_layout_and_code_conversion():
    meta = [place(META_COLS, {"B": "기관", "C": "시스템", "O": "DB", "P": "ENG_DB", "R": "ORACLE",
                              "AB": "공개", "AC": "제 6 호 (이름·주민등록번호 등 개인정보)", "AG": "수시",
                              "AI": "옛이름", "AJ": "OLD", "AL": "기타(로그 및 임시백업 등)"})]
    defs = build_definitions([raw_row("T", "TB", "새이름", "NEW", "CHAR", 1)], ChangeLog())
    meta = copy_definitions_to_meta(meta, defs.columns)
    assert meta[0][col("AJ")] == "NEW" and meta[0][col("AO")] == "CHAR"
    m = build_manual(meta)[0]
    assert m[col("B")] == "F" and m[col("E")] == "01" and m[col("C")] == "기관" and m[col("I")] == "ORACLE"
    assert m[col("S")] == "01" and m[col("T")] == "06" and m[col("AC")] == "09"
    assert m[col("X")] is None and m[col("AA")] == "NEW"
