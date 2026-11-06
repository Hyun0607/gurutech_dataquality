"""③ 사전점검: BRIS 산출물에서 도메인 미존재 4건, 점검 불가 8컬럼, 예상 적용률 91.0%."""
from conftest import load_bris, place

from stdtool.core.precheck import run_precheck
from stdtool.model import DOMAIN_COLS


def test_bris_missing_domains_and_rate():
    b = load_bris()
    result = run_precheck(b["domains"], b["terms"], b["words"], b["columns"])
    missing = sorted({i.detail for i in result.issues if i.code == "T06"})
    assert result.count("T06") == 4
    assert missing == ["명칭VC100", "명칭VC200", "코드CH2"]
    blocked = sorted(r.eng for r in result.columns if "C00" in r.codes)
    assert blocked == ["DSS_NM", "PLOR_NM", "PLOR_NM", "PLOR_NM", "REG_INST_NM",
                       "RSRC_MCLSF_CD", "RSRC_MCLSF_CD", "RSRC_MCLSF_CD"]
    assert result.basis == "컬럼정의서(추정)"
    assert (result.total, result.error_columns) == (89, 8)
    assert round(result.rate, 1) == 91.0 and result.score == 3
    # 다른 적용 오류는 없다 (컬럼정의서와 DB표준이 서로 맞음)
    assert {c for r in result.columns for c in r.codes} == {"C00"}


def test_bris_rate_reaches_100_when_domains_added():
    b = load_bris()
    for name, t, n in (("명칭VC100", "VARCHAR", 100), ("명칭VC200", "VARCHAR", 200), ("코드CH2", "CHAR", 2)):
        b["domains"].append(place(DOMAIN_COLS, {"B": name[:2], "C": name, "E": t, "F": n, "L": 20170715}))
    result = run_precheck(b["domains"], b["terms"], b["words"], b["columns"])
    assert result.count("T06") == 0 and result.error_columns == 0 and result.rate == 100.0


def test_meta_basis_counts_type_and_length_mismatch_only_when_length_present():
    b = load_bris()
    meta = [
        {"row": 4, "table": "BOT_ORG_CD", "kor": "생명자원기관명", "eng": "BIORSRC_INST_NM", "type": "VARCHAR", "length": 128},
        {"row": 5, "table": "BOT_ORG_CD", "kor": "생명자원기관명", "eng": "BIORSRC_INST_NM", "type": "VARCHAR", "length": None},
        {"row": 6, "table": "BOT_ORG_CD", "kor": "최초등록일시", "eng": "FRST_REG_DT", "type": "DATETIME", "length": None},
        {"row": 7, "table": "BOT_ORG_CD", "kor": "x", "eng": "UNKNOWN_COL", "type": "CHAR", "length": 1},
        {"row": 8, "table": "BOT_ORG_CD", "kor": "생명자원기관관리코드", "eng": "BIORSRC_INST_MNG_CD", "type": "VARCHAR", "length": 6},
    ]
    result = run_precheck(b["domains"], b["terms"], b["words"], b["columns"], meta)
    assert [r.codes for r in result.meta] == [[], [], ["M03"], ["M01"], ["M04"]]
    assert result.basis == "메타" and (result.total, result.error_columns) == (5, 3)


def test_domain_length_required():
    b = load_bris()
    b["domains"].append(place(DOMAIN_COLS, {"C": "수치값NM0", "E": "NUMBER", "F": 0}))
    result = run_precheck(b["domains"], b["terms"], b["words"], b["columns"])
    assert [i.key for i in result.issues if i.code == "D04"] == ["수치값NM0"]


def test_severity_word_duplicate_is_completeness_error():
    from stdtool.core.precheck import severity
    assert severity("W04") == "완전성 오류"
    assert severity("W03") == "완전성 오류"
    assert severity("D03") == "완전성 오류"
    assert severity("T08") == "경고"
    assert severity("C02") == "경고"
    assert severity("C01") == "적용 오류"
    assert severity("W06") == "공통표준 준용"


def test_format_rules_from_manual():
    from stdtool.core.precheck import (TERM_ABBR_CHARS, TERM_NAME_CHARS, WORD_ABBR_CHARS, WORD_NAME_CHARS,
                                       abbr_format_error, date_format_error, name_format_error)
    assert name_format_error("고객명", TERM_NAME_CHARS) == ""
    assert name_format_error("SMS발송내용", TERM_NAME_CHARS) == ""
    assert name_format_error("고객 명", TERM_NAME_CHARS) == "띄어쓰기 포함"
    assert name_format_error("1234", TERM_NAME_CHARS) == "한글 없음"
    assert name_format_error("고객(명)", TERM_NAME_CHARS) == "허용되지 않는 글자 ( )"
    assert name_format_error("e메일주소", TERM_NAME_CHARS) == "허용되지 않는 글자 e"   # 용어명은 영문대문자만
    assert name_format_error("e메일", WORD_NAME_CHARS) == ""                            # 단어명은 영문 대소문자
    assert abbr_format_error("CUST_NM", TERM_ABBR_CHARS) == ""
    assert abbr_format_error("cust_nm", TERM_ABBR_CHARS) == "허용되지 않는 글자 c m n s t u"
    assert abbr_format_error("1234", TERM_ABBR_CHARS) == "영문 없음"
    assert abbr_format_error("E-MAIL", TERM_ABBR_CHARS) == "허용되지 않는 글자 -"
    assert abbr_format_error("E-MAIL", WORD_ABBR_CHARS) == ""
    assert date_format_error(20170715) == ""
    assert date_format_error("20170715") == ""
    assert date_format_error(20171345) == "없는 날짜 (20171345)"
    assert date_format_error("2017-07-15").startswith("YYYYMMDD 아님")
    from datetime import datetime
    assert date_format_error(datetime(2017, 7, 15)).startswith("날짜 서식")


def test_word_duplicate_includes_synonyms_and_forbidden():
    from stdtool.core.precheck import check_words
    from stdtool.model import WORD_COLS
    words = [place(WORD_COLS, {"A": "성명", "B": "FLNM", "E": "Y", "G": "이름, 성함", "I": 20170715}),
             place(WORD_COLS, {"A": "이름", "B": "NM", "E": "Y", "I": 20170715}),
             place(WORD_COLS, {"A": "주소", "B": "ADDR", "E": "X", "I": 20170715})]
    issues = check_words(words)
    assert [(i.row, i.code, i.detail) for i in issues if i.code == "W04"] == [(2, "W04", "이름"), (3, "W04", "이름")]
    assert [(i.row, i.code) for i in issues if i.code == "W09"] == [(4, "W09")]


def test_official_word_without_hangul_is_not_format_error():
    from stdtool.core.precheck import check_words
    from stdtool.model import WORD_COLS
    words = [place(WORD_COLS, {"A": "URL", "B": "URL", "E": "N", "I": 20170715}),
             place(WORD_COLS, {"A": "XYZ", "B": "XYZ", "E": "N", "I": 20170715})]
    assert [i.key for i in check_words(words) if i.code == "W07"] == ["URL", "XYZ"]
    assert [i.key for i in check_words(words, {"URL"}) if i.code == "W07"] == ["XYZ"]


def test_column_def_english_name_mismatch_when_found_by_korean():
    from stdtool.model import COLUMN_DEF_COLS, TERM_COLS
    domains = [place(DOMAIN_COLS, {"C": "명칭VC100", "E": "VARCHAR", "F": 100, "L": 20170715})]
    terms = [place(TERM_COLS, {"A": "고객명", "C": "CUST_NM", "E": "명칭VC100", "I": 20170715})]
    columns = [place(COLUMN_DEF_COLS, {"A": "T", "B": "고객명", "C": "CSTMR_NM", "G": "VARCHAR", "H": 100}),
               place(COLUMN_DEF_COLS, {"A": "T", "B": "고객명", "C": "CUST_NM", "G": "VARCHAR", "H": 100})]
    result = run_precheck(domains, terms, None, columns)
    assert [r.codes for r in result.columns] == [["C05"], []]


def test_one_completeness_error_per_word_like_portal():
    """통합시스템: '작성항목1'(영문약어명 1)은 중복(단어명)만, 형식 오류(영문약어명)는 안 나옴."""
    from stdtool.core.precheck import check_words, group
    from stdtool.model import WORD_COLS
    words = [place(WORD_COLS, {"A": "작성항목1", "B": "WR", "E": "N", "I": "20260101"}),
             place(WORD_COLS, {"A": "작성항목1", "B": "1", "E": "N", "I": "20260101"})]
    portal = [(i.row, i.code, i.message) for i in check_words(words) if group(i.code) != "프로그램 추가 점검"]
    assert portal == [(2, "W04", "중복(단어명)"), (3, "W04", "중복(단어명)")]


def test_abbr_format_is_program_extra_not_completeness():
    """통합시스템은 'LOT(랏)' 같은 영문약어명을 완전성 오류로 내지 않았다 (한국 미술시장 정보시스템)."""
    from stdtool.core.precheck import check_terms, check_words, group, severity
    from stdtool.model import TERM_COLS, WORD_COLS
    words = [place(WORD_COLS, {"A": "LOT랏", "B": "LOT(랏)", "E": "N", "I": "20171020"})]
    terms = [place(TERM_COLS, {"A": "LOT랏", "C": "LOT(랏)", "E": "문자값NM38", "I": "20171020"})]
    domains = [place(DOMAIN_COLS, {"C": "문자값NM38", "E": "NUMBER", "F": 38, "L": "20171020"})]
    issues = check_words(words) + check_terms(terms, domains, None, [])
    assert [(i.code, group(i.code), severity(i.code)) for i in issues] == [
        ("W08", "프로그램 추가 점검", "경고"), ("T12", "프로그램 추가 점검", "경고")]
