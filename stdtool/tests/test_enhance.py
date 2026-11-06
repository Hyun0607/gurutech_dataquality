"""① 도메인 사전 고도화."""
from conftest import make_dict, place

from stdtool.config import Settings
from stdtool.core.cleanse import apply_length_policy, refine, split_type_length
from stdtool.core.enhance import ensure_term_domains
from stdtool.core.generate import make_domains
from stdtool.core.naming import DomainNamer, pool_key
from stdtool.model import TERM_COLS, ChangeLog, col


def raw_row(c, d, e, f):
    return ["T", "T", c, d, e, f, None]


def test_type_with_length_is_split_and_scale_kept():
    raw = [raw_row("금액", "AMT", "NUMBER(10,2)", None), raw_row("명", "NM", "varchar2(100)", None),
           raw_row("비율", "RT", "NUMBER", "5,2")]
    split_type_length(raw, ChangeLog())
    refine(raw, ChangeLog())
    assert [(r[4], r[5], r[6]) for r in raw] == [("NUMBER", 10, 2), ("VARCHAR2", 100, None), ("NUMBER", 5, 2)]


def test_scale_goes_into_domain_name_and_column():
    namer = DomainNamer(make_dict(), Settings())
    raw = [raw_row("금액", "PAY_AMT", "NUMBER", 10)]
    raw[0][6] = 2
    d = make_domains(raw, namer, 1, ChangeLog())[0]
    assert (d[col("C")], d[col("G")]) == ("금액NM10_2", 2)
    # 매크로 방식은 소수점을 무시
    d = make_domains(raw, DomainNamer(make_dict()), 1, ChangeLog())[0]
    assert (d[col("C")], d[col("G")]) == ("금액NM10", None)


def test_length_policy_only_for_listed_types():
    raw = [raw_row("값", "VAL", "NUMBER", 0), raw_row("내용", "CN", "VARCHAR", 0)]
    apply_length_policy(raw, {"NUMBER": 38}, ChangeLog())
    assert [r[5] for r in raw] == [38, 0]


def test_korean_suffix_classifies_when_tail_unknown():
    enhanced, macro = DomainNamer(make_dict(), Settings()), DomainNamer(make_dict())
    assert macro.classify("SCNCENM", "학명") == "문자값"
    assert enhanced.classify("SCNCENM", "학명") == "명칭"
    assert enhanced.classify("RMK_DSCRP", "비고설명") == "내용"      # 긴 끝말 우선
    assert enhanced.classify("CUST_NM", "아무거나") == "명칭"        # 영문 접미어가 있으면 그대로
    assert enhanced.classify("SXDC", "성별") == "문자값"


def test_unregistered_type_reported_and_override():
    settings = Settings(type_abbr_override={"NAME": "NAM"}, type_extra={"UUID": "UID"})
    namer = DomainNamer(make_dict(), settings)
    assert namer.name("명칭", "NAME", 22) == "명칭NAM22"
    assert namer.name("ID", "UUID", 36) == "IDUID36"
    assert namer.name("문자값", "INT4", 0) == "문자값INT40"
    assert namer.unregistered_types == {"INT4": 1}


def test_pool_reuses_existing_domain_name():
    pool = {pool_key("명칭", "VARCHAR", 100, None): "명칭V100"}
    namer = DomainNamer(make_dict(), Settings(), pool)
    assert namer.name("명칭", "VARCHAR", 100) == "명칭V100"
    assert namer.name("명칭", "VARCHAR", 50) == "명칭VC50"


def test_ensure_term_domains_adds_missing():
    namer = DomainNamer(make_dict(), Settings())
    raw = [raw_row("질병명", "DSS_NM", "VARCHAR", 100)]
    terms = [place(TERM_COLS, {"A": "질병명", "C": "DSS_NM", "E": "명칭VC100"})]
    log = ChangeLog()
    domains = ensure_term_domains(raw, terms, [], namer, 20170715, log)
    assert [(d[col("B")], d[col("C")], d[col("E")], d[col("F")]) for d in domains] == [("명칭", "명칭VC100", "VARCHAR", 100)]
    assert log.items[0].action == "추가"


def test_text_fallback_recorded_only_when_tail_not_found():
    enhanced, macro = DomainNamer(make_dict(), Settings()), DomainNamer(make_dict())
    macro.classify("CUST_WGT", "고객무게")
    macro.classify("PROD_WGT", "상품무게")
    macro.classify("CUST_NM", "고객명")          # Code_tail에 있음
    macro.classify("SCNCENM", "학명")             # 밑줄 없으면 이름 전체가 꼬리
    macro.counting = False
    macro.classify("ETC_WGT", "기타무게")         # 집계 안 함
    assert macro.text_fallback == {("WGT", "CUST_WGT", "고객무게"): 1, ("WGT", "PROD_WGT", "상품무게"): 1,
                                   ("SCNCENM", "SCNCENM", "학명"): 1}
    enhanced.classify("SCNCENM", "학명")          # 한글 끝말로 분류되면 문자값 아님
    assert not enhanced.text_fallback


def test_text_fallback_rows_grouped_by_tail():
    from types import SimpleNamespace
    from stdtool.dictionary import CommonWord
    from stdtool.pipeline import RunResult
    namer = DomainNamer(make_dict())
    for eng, kor in [("A_WGT", "가무게"), ("B_WGT", "나무게"), ("C_XYZ", "다")]:
        namer.classify(eng, kor)
    common = SimpleNamespace(words=[CommonWord("무게", "WGT", "Weight", "Y", "수", [], [])])
    result = SimpleNamespace(namer=namer, common=common)
    rows = RunResult.text_fallback_rows(result)
    assert rows == [("WGT", 2, "가무게, 나무게", "A_WGT, B_WGT", "무게", "Y", "수"), ("XYZ", 1, "다", "C_XYZ", "", "", "")]


def test_nm_belongs_to_number_by_default():
    enhanced, macro = DomainNamer(make_dict(), Settings()), DomainNamer(make_dict())
    assert enhanced.type_abbr("NUMBER") == "NM"
    assert enhanced.type_abbr("NAME") == "NAM"
    assert macro.type_abbr("NAME") == "NM"          # 매크로 방식은 매크로 그대로


def test_char_and_character_get_different_domain_names():
    """둘 다 CH면 여부CH1이 두 개 생겨 D03(도메인명 중복) → 그 도메인을 쓰는 용어·컬럼이 모두 오류."""
    enhanced, macro = DomainNamer(make_dict(), Settings()), DomainNamer(make_dict())
    assert macro.type_abbr("CHAR") == macro.type_abbr("CHARACTER") == "CH"
    assert enhanced.name("여부", "CHAR", 1) == "여부CH1"
    assert enhanced.name("여부", "CHARACTER", 1) == "여부CHR1"


def test_type_alias_unified_to_dbms_spelling():
    from stdtool.config import DEFAULT_TYPE_ALIAS
    from stdtool.core.cleanse import unify_type_alias
    from stdtool.model import META_COLS
    raw = [raw_row("여부", "USE_YN", "CHAR", 1), raw_row("명", "NM", "VARCHAR", 100), raw_row("일시", "DT", "DATE", 0),
           raw_row("여부", "DEL_YN", "CHAR", 1)]
    meta = [place(META_COLS, {"R": "POSTGRESQL"})] * 3 + [place(META_COLS, {"R": "ORACLE"})]
    log = ChangeLog()
    unify_type_alias(raw, meta, DEFAULT_TYPE_ALIAS, log)
    assert [r[4] for r in raw] == ["CHARACTER", "CHARACTER VARYING", "DATE", "CHAR"]   # 오라클은 그대로
    assert len(log.items) == 2


def test_same_term_name_with_several_english_gets_numbers():
    """번호가 없으면 DB표준 적용이 15개 컬럼을 마지막 영문 하나로 바꾸고, 정의서에서 14개가 지워진다."""
    from stdtool.core.enhance import number_duplicate_terms
    terms = [place(TERM_COLS, {"A": "여분필드명지정", "C": f"OPT{n}_NAME", "E": "명칭VC100"}) for n in (10, 1, 2)]
    terms += [place(TERM_COLS, {"A": "비밀번호", "C": e, "E": "문자값VC100"}) for e in ("PSWD", "PSSRD")]
    terms += [place(TERM_COLS, {"A": "법원명", "C": "CT_NM", "E": "명칭VC100"}),
              place(TERM_COLS, {"A": "법원명", "C": "COURT_NM", "E": "명칭VC100"})]   # 공통표준 영문이면 그대로
    log = ChangeLog()
    number_duplicate_terms(terms, {"CT_NM"}, log)
    assert [(t[col("A")], t[col("C")]) for t in terms] == [
        ("여분필드명지정10", "OPT10_NAME"), ("여분필드명지정1", "OPT1_NAME"), ("여분필드명지정2", "OPT2_NAME"),
        ("비밀번호01", "PSWD"), ("비밀번호02", "PSSRD"), ("법원명", "CT_NM"), ("법원명", "COURT_NM")]
