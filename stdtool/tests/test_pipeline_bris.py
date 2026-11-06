"""BRIS 산출물로 되살린 메타를 실제 공통표준과 함께 돌려 매크로 산출물과 비교 (매크로 파일이 있을 때만)."""
from conftest import bris_meta, load_bris

from stdtool.config import Settings
from stdtool.model import col
from stdtool.pipeline import run


def pick(rows, letters):
    return [tuple(r[col(x)] for x in letters) for r in rows]


def settings(enhanced):
    return Settings(org_name="기관", db_name="BRIS", enact_date=20170715, inst_std="N", enhanced=enhanced)


def test_macro_mode_matches_bris_outputs(macro_dict):
    b = load_bris()
    r = run(bris_meta(), macro_dict, settings(False))
    assert pick(r.definitions.tables, "BC") == pick(b["tables"], "BC")
    assert pick(r.definitions.columns, "ABCGH") == pick(b["columns"], "ABCGH")
    assert pick(r.terms, "ACEI") == pick(b["terms"], "ACEI")
    assert pick(r.words, "ABCEI") == pick(b["words"], "ABCEI")
    # 도메인: BRIS 산출물에 없던 3개(용어가 가리키던 도메인)가 함께 만들어진다
    names = [d[col("C")] for d in r.domains]
    extra = {"명칭VC100", "코드CH2", "명칭VC200"}
    assert [n for n in names if n not in extra] == [d[col("C")] for d in b["domains"]]
    assert extra <= set(names)
    assert r.precheck.rate == 100.0


def test_real_common_standard_stages(common_real):
    from stdtool.core.synonym import SynonymMatcher
    assert len(common_real.terms) == 13159 and len(common_real.words) == 3280
    m = SynonymMatcher(common_real)
    expect = {"SMS발송내용": "SMS전송내용", "업데이트일자": "갱신일자", "유저아이디": "사용자아이디",
              "컨텐츠명": "콘텐츠명", "주민번호": "주민등록번호", "가족순번": "가족일련번호"}
    for kor, name in expect.items():
        r = m.match(kor, "X")
        assert r.category == "치환 권고" and r.term.name == name, kor


def test_bris_with_real_common_words(macro_dict, common_real):
    r = run(bris_meta(), macro_dict, settings(True), common=common_real)
    # 공통표준단어로 한글명을 채우면 단어명 중복 경고가 크게 준다 (37 → 5)
    assert r.precheck.count("W04") == 5
    cats = {}
    for x in r.synonym_results:
        cats[x.category] = cats.get(x.category, 0) + 1
    assert cats["표준 그대로"] == 6 and sum(cats.values()) == 40


def test_enhanced_mode_classifies_by_korean_name(macro_dict):
    r = run(bris_meta(), macro_dict, settings(True))
    term = next(t for t in r.terms if t[col("C")] == "SCNCENM")
    assert term[col("E")] == "명칭TXT0"
    assert r.precheck.count("T06") == 0
