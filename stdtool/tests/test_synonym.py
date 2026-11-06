"""② 공통표준 유의어·금칙어 대응."""
from pathlib import Path

from conftest import bris_meta, make_dict, place

from stdtool.config import Settings
from stdtool.core.precheck import check_common
from stdtool.core.synonym import (EXACT, MAPPING, NONE, NORMALIZED, REPLACE, SIMILAR, STANDARD, TERM_SYNONYM,
                                  WORD_SWAP, SynonymMatcher, apply_matches, match_raw)
from stdtool.dictionary import CommonStandard, CommonTerm, CommonWord, split_list
from stdtool.model import TERM_COLS, WORD_COLS, ChangeLog, col
from stdtool.pipeline import run
from stdtool.workbook.mapping_report import read_mapping_decisions, write_mapping_report


def term(name, abbr, domain="명V100", syn=""):
    return CommonTerm(name, abbr, domain, split_list(syn), "VARCHAR", 100)


def word(name, abbr, syn="", bad=""):
    return CommonWord(name, abbr, abbr, "N", "", split_list(syn), split_list(bad))


COMMON = CommonStandard(
    terms=[term("법원명", "CT_NM", syn="법원명칭, 법원이름"), term("SMS전송내용", "SMS_TRSM_CN", "내용V4000", "SMS발송내용"),
           term("사용자아이디", "USER_ID", "명V20"), term("기관관리번호", "INST_MNG_NO", "번호V50"),
           term("관리번호", "MNG_NO", "번호V50"), term("API명", "API_NM"),
           term("참고자료명", "REF_DATA_NM", syn="참고데이터명"), term("참고문헌명", "REF_LTRTR_NM", syn="참고데이터명")],
    words=[word("법원", "CT"), word("명", "NM", syn="명칭, 이름"), word("사용자", "USER", bad="유저"),
           word("아이디", "ID"), word("기관", "INST"), word("관리", "MNG"), word("번호", "NO"), word("고유", "UNQ")],
)


def test_split_list():
    assert split_list("법원명칭, 법원이름") == ["법원명칭", "법원이름"]
    assert split_list("-") == [] and split_list(None) == []


def test_each_stage():
    m = SynonymMatcher(COMMON)
    cases = {
        ("법원명", "X"): (STANDARD, EXACT, "법원명"),
        ("X", "CT_NM"): (STANDARD, EXACT, "법원명"),
        ("API 명", "Y"): (REPLACE, NORMALIZED, "API명"),
        ("법원명칭", "COURT_NAME"): (REPLACE, TERM_SYNONYM, "법원명"),
        ("SMS발송내용", "SMS_SEND"): (REPLACE, TERM_SYNONYM, "SMS전송내용"),
        ("유저아이디", "USR_ID"): (REPLACE, WORD_SWAP, "사용자아이디"),
    }
    for (kor, eng), (category, stage, name) in cases.items():
        r = m.match(kor, eng)
        assert (r.category, r.stage, r.term.name) == (category, stage, name), (kor, r)
    r = m.match("유저아이디", "USR_ID")
    assert r.forbidden == [("유저", "사용자")] and r.rebuilt == "사용자아이디"


def test_ambiguous_synonym_becomes_candidates():
    r = SynonymMatcher(COMMON).match("참고데이터명", "REF_DT_NM")
    assert r.category == MAPPING and r.term is None
    assert sorted(t.name for t, _ in r.candidates) == ["참고문헌명", "참고자료명"]


def test_similar_prefers_shared_words_and_same_last_word():
    r = SynonymMatcher(COMMON).match("기관고유관리번호", "INST_UNQ_MNG_NO")
    assert (r.category, r.stage) == (MAPPING, SIMILAR)
    assert [t.name for t, _ in r.candidates][:2] == ["기관관리번호", "관리번호"]
    assert SynonymMatcher(COMMON).match("배양온도", "CLTVT_TP").category == NONE


def raw_row(table, kor, eng):
    return [table, table, kor, eng, "VARCHAR", 10, None]


def test_apply_auto_replaces_only_recommendations():
    m = SynonymMatcher(COMMON)
    raw = [raw_row("T1", "법원명칭", "COURT_NAME"), raw_row("T2", "법원명칭", "COURT_NAME"),
           raw_row("T1", "기관고유관리번호", "INST_UNQ_MNG_NO")]
    results = match_raw(raw, m)
    assert len(results) == 2 and results[0].rows == [2, 3] and results[0].tables == {"T1", "T2"}
    apply_matches(raw, results, None, True, m, ChangeLog())
    assert raw[0][2:4] == ["법원명", "CT_NM"] and raw[1][2:4] == ["법원명", "CT_NM"]
    assert raw[2][2:4] == ["기관고유관리번호", "INST_UNQ_MNG_NO"]


def test_review_file_round_trip(tmp_path: Path):
    m = SynonymMatcher(COMMON)
    raw = [raw_row("T1", "법원명칭", "COURT_NAME"), raw_row("T1", "기관고유관리번호", "INST_UNQ_MNG_NO")]
    before = [list(r) for r in raw]
    results = match_raw(raw, m)
    apply_matches(raw, results, None, False, m, ChangeLog())
    path = write_mapping_report(results, before, tmp_path / "표준매핑.xlsx")
    decisions = read_mapping_decisions(path)
    assert decisions[("법원명칭", "COURT_NAME")] == (False, "법원명")
    # 사람이 검토: 법원명칭은 확정, 기관고유관리번호는 후보1(기관관리번호)로 확정
    decisions[("법원명칭", "COURT_NAME")] = (True, "법원명")
    decisions[("기관고유관리번호", "INST_UNQ_MNG_NO")] = (True, "기관관리번호")
    raw = [list(r) for r in before]
    apply_matches(raw, match_raw(raw, m), decisions, False, m, ChangeLog())
    assert raw[0][2:4] == ["법원명", "CT_NM"] and raw[1][2:4] == ["기관관리번호", "INST_MNG_NO"]


def domain(name, data_type, length):
    from stdtool.model import DOMAIN_COLS
    return place(DOMAIN_COLS, {"C": name, "E": data_type, "F": length})


def test_check_common_like_integrated_system():
    """통합시스템 공통표준 준용 점검: 준용 대상(이름·영문약어·이음동의어)만, 한 용어에 오류 하나."""
    m = SynonymMatcher(COMMON)
    domains = [domain("명V100", "VARCHAR", 100), domain("명V20", "VARCHAR2", 20), domain("명NV200", "NVARCHAR", 200)]
    terms = [place(TERM_COLS, {"A": "유저아이디", "C": "USR_ID", "E": "명V100"}),   # 준용 대상 아님 → 금칙어도 안 봄
             place(TERM_COLS, {"A": "법원명칭", "C": "COURT_NM", "E": "명NV200"}),  # 이음동의어: 타입·길이도 다르지만 약어 하나만
             place(TERM_COLS, {"A": "법원명", "C": "COURT_NM", "E": "명V100"}),     # 이름 같고 약어 다름
             place(TERM_COLS, {"A": "사용자아이디", "C": "USER_ID", "E": "명V20"}),  # VARCHAR2 = VARCHAR, 길이 20 ≠ 100
             place(TERM_COLS, {"A": "법원이름", "C": "CT_NM", "E": "명V100"}),      # 정상 (이음동의어, 약어·타입·길이 같음)
             place(TERM_COLS, {"A": "관리자", "C": "MNG_NO", "E": "명V100"})]       # 약어로 찾음 → 불일치(용어명)
    words = [place(WORD_COLS, {"A": "유저", "B": "USR"}), place(WORD_COLS, {"A": "법원명", "B": "CT"}),
             place(WORD_COLS, {"A": "기관", "B": "INST"}), place(WORD_COLS, {"A": "법원", "B": "COURT"})]
    issues = check_common(terms, words, m, domains)
    codes = [(i.area, i.row, i.code) for i in issues]
    assert [c for c in codes if c[0] == "용어"] == [("용어", 3, "T10"), ("용어", 4, "T10"), ("용어", 5, "T16"),
                                                   ("용어", 7, "T14")]
    assert [c for c in codes if c[0] == "단어"] == [("단어", 2, "W05"), ("단어", 3, "W11"), ("단어", 5, "W06")]
    assert issues[0].message == "불일치(영문약어명)"
    assert issues[0].description == "공통표준용어 준용 대상이지만 영문약어명이 불일치하는 경우"


def test_check_common_forbidden_only_for_target():
    common = CommonStandard(terms=[term("사용자아이디", "USER_ID", syn="유저아이디")],
                            words=[word("사용자", "USER", bad="유저"), word("아이디", "ID")])
    terms = [place(TERM_COLS, {"A": "유저아이디", "C": "USER_ID", "E": "명V100"})]
    issues = check_common(terms, None, SynonymMatcher(common), [domain("명V100", "VARCHAR", 100)])
    assert [(i.code, i.message) for i in issues] == [("T09", "금칙어 사용(용어명)")]


def test_pipeline_applies_synonym_and_fills_words():
    common = CommonStandard(terms=[term("법원명", "CT_NM", syn="법원명칭")], words=[word("법원", "CT"), word("명", "NM")])
    meta = [place(46, {"B": "기관", "Z": "법원", "AA": "TB_CT", "AI": "법원명칭", "AJ": "COURT_NAME", "AO": "VARCHAR", "AP": 50})]
    dicts = make_dict(common=[["법원명", "CT_NM", "VARCHAR", 100]])
    # 기본은 치환하지 않는다: 정의서는 실제 DB 컬럼명 그대로, ②는 알려 주기만
    r = run(meta, dicts, Settings(enact_date=1), common=common)
    assert r.definitions.columns[0][col("B"):col("D")] == ["법원명칭", "COURT_NAME"]
    assert r.synonym_results and not r.synonym_results[0].confirmed
    r = run(meta, dicts, Settings(enact_date=1, synonym_auto_apply=True), common=common)
    assert r.definitions.columns[0][col("B"):col("D")] == ["법원명", "CT_NM"]
    assert r.definitions.columns[0][col("G"):col("I")] == ["VARCHAR", 100]   # 공통표준 매핑이 타입·길이를 채움
    assert [(w[0], w[1]) for w in r.words] == [("법원", "CT"), ("명", "NM")]
    assert r.synonym_results[0].confirmed
    # 매크로 방식에서는 ②를 하지 않는다
    r = run(meta, dicts, Settings(enact_date=1, enhanced=False), common=common)
    assert r.definitions.columns[0][col("C")] == "COURT_NAME" and not r.synonym_results


def test_bris_with_empty_common_still_runs():
    r = run(bris_meta(), make_dict(), Settings(enact_date=1), common=CommonStandard([], []))
    assert len(r.definitions.columns) == 89
