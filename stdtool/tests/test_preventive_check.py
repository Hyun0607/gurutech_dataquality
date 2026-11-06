"""예방적 품질관리 문서 점검: 문서 글자 뽑기(hwpx·hwp·pdf), RFP 요구사항·금액, 발주·완료 판정."""
import zipfile
from pathlib import Path

import openpyxl
import pytest

from stdtool.core import preventive as pv
from stdtool.core import preventive_check as pc
from stdtool.workbook import preventive_report as report
from stdtool.workbook.documents import DocumentError, Para, read_document

REAL = Path.home() / "OneDrive" / "Desktop" / "2026 프로젝트" / "★ 2026 예방적 품질관리"
NRF = REAL / "한국연구재단" / "인문사회 학술연구포털 ISMP 수립_1차 발주단계"
NRF_BEFORE = NRF / "04. 제안요청서_인문사회 학술연구포털 ISMP 수립(최종).hwp"
NRF_AFTER = NRF / "06. 제안요청서_인문사회 학술연구포털 ISMP 수립(수정)_최종.hwp"
YI = REAL / "용인시" / "용인시 홈페이지 기능개선 및 유지관리"
YI_BEFORE = YI / "2. 제안요청서(2026년 용인시 홈페이지 기능개선 및 유지관리)_수정.hwp"
YI_AFTER = YI / "2. 제안요청서(2026년 용인시 홈페이지 기능개선 및 유지관리)_수정(데이터표준화)_추가수정.hwp"
NRF_REPORT = REAL / "한국연구재단" / "인문사회 학술연구포털 ISMP 수립_2차 완료단계" / "03. 완료보고서_인문사회 학술연구포털 ISMP 수립 사업.pdf"


@pytest.fixture(scope="module")
def criteria():
    return report.load_criteria()


def paras(*texts):
    return [Para(t, f"문단 {i + 1}") for i, t in enumerate(texts)]


def dar(rid, name):
    return ["요구사항 분류", "데이터 요구사항", "요구사항 고유번호", rid, "요구사항 명칭", name, "정의", name]


def _hwpx(path, texts):
    ns = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
    body = "".join(f"<hp:p><hp:run><hp:t>{t}</hp:t></hp:run></hp:p>" for t in texts)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/section0.xml", f'<?xml version="1.0"?><hs:sec xmlns:hs="x" {ns}>{body}</hs:sec>')
    return path


def test_hwpx_text(tmp_path):
    got = read_document(_hwpx(tmp_path / "rfp.hwpx", ["□ 사 업 비 : 금308,100,000원", "DAR-001"]))
    assert [p.text for p in got] == ["□ 사 업 비 : 금308,100,000원", "DAR-001"]
    assert got[0].where == "문단 1"


def test_unsupported_file(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(DocumentError):
        read_document(tmp_path / "a.txt")


@pytest.mark.parametrize("text, won", [
    ("□ 사 업 비: 160,000,000원 이내(부가세 포함)", 160_000_000),
    ("4. 사 업 비 : 금308,100,000원 - 부가세 포함", 308_100_000),
    ("□ 소요예산 : 167,000,000원(부가세 포함)", 167_000_000),
    ("ㅇ 사업예산 : 12억원", 1_200_000_000),
    ("총사업비: 450백만원", 450_000_000),
])
def test_find_amount(text, won):
    assert pc.find_amount(paras("사업개요", text))[0] == won


def test_requirement_names_to_items(criteria):
    assert pc.item_codes("데이터 구조, 설계, 검증 관리", criteria) == ["2.1", "2.2", "2.3"]
    assert pc.item_codes("데이터 값 검증 및 데이터 이관 시 계획·검증", criteria) == ["3.1", "3.2"]
    assert pc.item_codes("데이터 개방 및 메타데이터 관리체계", criteria) == ["4.2"]
    assert pc.item_codes("데이터 관리체계 현황분석 및 목표모델 제시", criteria) == ["4.1"]
    assert pc.item_codes("이관 데이터 값 검증 방안 제시", criteria) == ["3.2"]
    assert pc.item_codes("표준 프레임 워크 적용", criteria) == []


def test_manual_requirements_cover_every_type_and_band(criteria):
    got = {(r.kind, r.band) for r in criteria.requirements}
    assert got == set(criteria.matrix)
    for (kind, band), row in criteria.matrix.items():
        codes = {r.code for r in criteria.requirements if (r.kind, r.band) == (kind, band)}
        assert {c for c, v in row.items() if v == "O"} <= codes, (kind, band)


def test_check_order(criteria):
    doc = paras("□ 사 업 비: 300,000,000원", *dar("DAR-001", "데이터 표준 수립 및 상위표준 준수"),
                *dar("SFR-010", "데이터 구조 설계 및 검증"), "데이터 값 검증 방안을 마련한다")
    required, maybe, _ = pv.items_for(["신규구축"], 300_000_000, False, criteria)
    c = pc.check_order(doc, "rfp.hwpx", ["신규구축"], required, maybe, criteria)
    status = {r.code: r.status for r in c.results}
    assert c.amount == 300_000_000
    assert status["1.1"] == pc.DONE_OK
    assert status["2.1"] == status["2.2"] == pc.DONE_CHECK      # DAR가 아닌 요구사항에만 있음
    assert status["3.1"] == pc.DONE_CHECK                       # 본문 언급만
    assert status["4.2"] == pc.DONE_MISSING
    hint = next(r for r in c.results if r.code == "4.2").suggestion
    assert (hint.kind, hint.band, hint.code) == ("신규구축", "1억 이상 10억 미만", "4.2")


def test_check_done_reports_and_files(criteria, tmp_path):
    docs = [("완료보고서.pdf", [Para("데이터 표준화 수행 결과 표준용어 300건 정의", "p.12", 12),
                               Para("1. 데이터 구조 관리 ........ 15", "p.2", 2)])]
    files = ["메타데이터 표준 관리항목_용인시.xlsx", "OODB_값진단 보고서_예시.xlsx", "3.1 데이터 값 검증_증빙기준.png"]
    required, maybe, _ = pv.items_for(["신규구축"], 50_000_000, False, criteria)
    c = pc.check_done(docs, files, required, maybe, criteria)
    status = {r.code: (r.status, r.where) for r in c.results}
    assert status["1.1"] == (pc.FOUND, "p.12")   # 보고서가 하나면 쪽 번호만
    assert status["4.2"] == (pc.FOUND, "제출 파일")
    assert status["3.1"][0] == pc.NOT_FOUND                     # 예시 양식만이면 인정 안 됨, 증빙기준 그림은 무시
    assert "예시 양식" in next(r.comment for r in c.results if r.code == "3.1")
    assert status["2.1"][0] == pc.NOT_FOUND


def test_write_inspection(criteria, tmp_path):
    """사업단 이행점검 결과 양식: 1. 사업 진단결과(지표 9칸: 점검 완료 / 보완 필요 / -) · 2. 보완 사항(진단기준 ①② 두 줄)."""
    doc = paras(*dar("DAR-001", "데이터 표준화 방안 제시"))
    c = pc.check_order(doc, "rfp.hwpx", ["컨설팅"], ["1.1", "1.2"], [], criteria)
    rec = report.check_record(c, None, "인문사회 학술연구포털 ISMP 수립", 2026, 1, criteria)
    out = report.write_inspection([rec], criteria, tmp_path / report.inspection_name("", rec["name"], 1))
    assert out.name.startswith("예방적 품질관리 진단 이행점검(1차)_인문사회")
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["사업 진단결과", "보완 사항", "지표별 상세"]
    ws = wb["사업 진단결과"]
    assert ws["A1"].value == "1. 사업 진단결과" and ws["G2"].value == "1. 데이터 표준"
    row = [ws.cell(4, c).value for c in range(1, 17)]
    assert row[0] == "(1차)발주단계" and row[6:9] == ["점검 완료", "보완 필요", "-"]
    assert "1.2" in row[15]                                    # 비고
    fix = wb["보완 사항"]
    assert [fix.cell(r, 3).value for r in (3, 4)] == ["1.2(1)", "1.2(2)"]
    assert "요구사항 명칭: 데이터 표준관리 방안 제시" in fix.cell(3, 6).value


def test_guide_folder(criteria, tmp_path):
    docs = [("완료보고서.pdf", [Para("데이터 표준화 수행 결과 표준용어 300건 정의", "p.12", 12)])]
    c = pc.check_done(docs, [], ["1.1", "2.1"], [], criteria)
    rec = report.check_record(c, None, "주민자치센터 홈페이지 구축", 2026, 1, criteria)
    folder = report.build_guide_folder(rec, criteria, tmp_path)
    subs = sorted(p.name for p in folder.iterdir())
    assert "2.1 데이터 구조 설계" in subs and not any(s.startswith("1.1") for s in subs)   # 보완할 지표만
    fix = folder / "2.1 데이터 구조 설계"
    text = (fix / "제출 안내.txt").read_text(encoding="utf-8-sig")
    assert "인정되는 산출물" in text and "할 일" in text
    if report.MATERIALS.exists():
        assert (fix / "예시").is_dir() and (fix / "가이드" / "데이터모델링가이드_V1.1.pptx").exists()
        assert any("증빙기준" in p.name for p in fix.iterdir())
    assert report.build_guide_folder(rec, criteria, tmp_path).name.endswith("_2")   # 이미 있으면 새 이름
    done = report.check_record(pc.check_done(docs, [], ["1.1"], [], criteria), None, "다른 사업", 2026, 1, criteria)
    with pytest.raises(ValueError):                                                   # 보완할 지표가 없으면 만들지 않음
        report.build_guide_folder(done, criteria, tmp_path)


def test_inspection_merges_order_and_done_of_one_org(tmp_path, criteria):
    """같은 기관이면 회차가 달라도(발주 1차 · 완료 2차) 한 파일, 사업별로 발주 → 완료."""
    from stdtool import preventive_store as store
    db = tmp_path / "history.sqlite"
    order = pc.check_order(paras(*dar("DAR-001", "데이터 표준화 방안 제시")), "rfp.hwpx", ["컨설팅"], ["1.1"], [], criteria)
    done = pc.check_done([], [], ["1.1"], [], criteria)
    recs = []
    for check, no in ((done, 2), (order, 1)):
        rec = report.check_record(check, None, "ISMP 수립", 2026, no, criteria)
        rec.update(org="한국연구재단", org_key="한국연구재단")
        store.save_check(rec, db)
    recs = store.load_checks("한국연구재단", 2026, db)
    assert [(r["kind"], r["round"]) for r in recs] == [("발주", 1), ("완료", 2)]
    assert report.inspection_name("한국연구재단", "", [r["round"] for r in recs]).startswith(
        "예방적 품질관리 진단 이행점검(1·2차)_한국연구재단_")


@pytest.mark.skipif(not all(p.exists() for p in (NRF_BEFORE, NRF_AFTER, YI_BEFORE, YI_AFTER)), reason="RFP 원본 없음")
@pytest.mark.parametrize("before, after, name, fixed", [
    (NRF_BEFORE, NRF_AFTER, "인문사회 학술연구포털 ISMP 수립", "4.2"),            # NIA 의견: DAR-006 미반영
    (YI_BEFORE, YI_AFTER, "2026년 용인시 홈페이지 기능개선 및 유지관리", "1.1"),   # 보완 시 '데이터 표준 수립' 추가
])
def test_real_rfp_before_and_after_supplement(criteria, before, after, name, fixed):
    """보완 전 RFP는 그 지표만 보완필요, 보완 후 RFP는 모두 점검완료 (2026 이행점검 실제 보완 내역과 같음)."""
    types = pv.classify(name, criteria)[0]
    for path, expect in ((before, {fixed}), (after, set())):
        doc = read_document(path)
        amount = pc.find_amount(doc)[0]
        required, maybe, _ = pv.items_for(types, amount, False, criteria)
        c = pc.check_order(doc, path.name, types, required, maybe, criteria, amount)
        assert {r.code for r in c.results if report.portal_mark(r) == report.PORTAL_FIX} == expect, path.name


@pytest.mark.skipif(not NRF_REPORT.exists(), reason="완료보고서 원본 없음")
def test_real_pdf_report(criteria):
    doc = read_document(NRF_REPORT)
    assert doc[0].where.startswith("p.") and max(p.page for p in doc) > 50


def test_find_project_name():
    assert pc.find_project_name(paras("제 안 요 청 서", "1. 사업명 : 「인문사회 학술연구포털 ISMP 수립」")) == \
        "인문사회 학술연구포털 ISMP 수립"
    assert pc.find_project_name(paras("제 안 요 청 서", "사 업 명", "2026년 KSPO 공공데이터 컨설팅")) == "2026년 KSPO 공공데이터 컨설팅"
    assert pc.find_project_name(paras("4. 사 업 비 : 금308,100,000원")) == ""


def test_match_project_by_name_file_and_year():
    names = ["마을버스 도착정보시스템 고도화 사업", "인문사회 학술연구포털 ISMP 수립", "2025년 용인시 홈페이지 기능개선 및 유지관리"]
    assert pc.match_project(["인문사회 학술연구포털 ISMP 수립"], names) == 1
    assert pc.match_project(["", "04. 제안요청서_인문사회 학술연구포털 ISMP 수립(최종)"], names) == 1   # 파일 이름
    assert pc.match_project(["2026년 용인시 홈페이지 기능개선 및 유지관리 사업"], names) is None      # 연도가 다르면 다른 사업
    assert pc.match_project(["2026년 KSPO 공공데이터 컨설팅"], names) is None


def test_report_amount_is_strict():
    """완료·감리보고서는 앞 10쪽의 '사업비 : …' 꼴만 금액으로 본다 ('사업비 3억↑ 분리 발주' 같은 권고는 아님)."""
    advice = [Para("사업비 3억↑ 분리 발주", "p.60", 60)]
    assert pc.find_amount(advice)[0] == 300_000_000            # RFP에서는 앞쪽 줄이면 금액
    assert pc.find_amount(advice, strict=True)[0] is None
    overview = [Para("□ 사업비 : 160,000,000원", "p.2", 2), *advice]
    assert pc.find_amount(overview, strict=True)[:2] == (160_000_000, "p.2")


def test_done_detail_criteria(criteria, tmp_path):
    """완료단계 세부 기준 18개: 대응 지표가 아니면 '-', 보고서 줄·산출물 이름이 있으면 Y, 없으면 N + 사업단 문구 검토의견.
    지표는 기준이 모두 Y일 때만 확인됨. 진단결과반영비율 = Y ÷ (Y + N). 결과 엑셀에 사업단 양식 두 시트."""
    docs = [("완료보고서.pdf", [Para("데이터 표준화 수행: 표준용어 300건", "p.3", 3),
                               Para("공통표준 및 기관표준 준용 결과", "p.4", 4),
                               Para("웹 표준 준수 (데이터 화면)", "p.5", 5)])]
    req, maybe, _ = pv.items_for(["컨설팅"], None, False, criteria)
    c = pc.check_done(docs, ["메타데이터 표준 관리항목.xlsx"], req, maybe, criteria, ["컨설팅"])
    got = {d.code: d.status for d in c.criteria}
    assert len(c.criteria) == 18
    assert got["1.1(1)"] == got["1.1(2)"] == "Y" and got["4.2(2)"] == "Y"
    assert got["2.1(2)"] == "-" and got["3.1(1)"] == "-"          # 컨설팅은 2.1(2) 생략, 3.1은 대응 지표 아님
    assert got["1.2(1)"] == "N" and "확인할 수 없습니다" in next(d.opinion for d in c.criteria if d.code == "1.2(1)")
    item = {r.code: r.status for r in c.results}
    assert item["1.1"] == pc.FOUND and item["1.2"] == pc.NOT_FOUND
    marks = [s for s in got.values() if s in "YN"]
    assert c.ratio() == marks.count("Y") / len(marks)
    rec = report.check_record(c, None, "사업", 2026, 2, criteria)
    out = report.write_inspection([rec], criteria, tmp_path / "x.xlsx")
    wb = openpyxl.load_workbook(out)
    assert {"완료단계 진단결과", "검토의견"} <= set(wb.sheetnames)
    ws = wb["완료단계 진단결과"]
    assert ws.cell(1, 7).value == "1.1 데이터 표준화(1)" and ws.cell(1, 25).value == "진단결과반영비율"
    assert ws.cell(2, 25).value == report.ratio_text(rec)


def test_audit_report_project_name():
    """감리보고서는 '사업명 :' 칸이 없다 — 인사말의 감리 대상 사업명, 없으면 표지 '… 감리 용역'에서 읽는다."""
    greet = [Para(t, "p.2", 2) for t in (
        "㈜에이씨에스글로벌은 용인특례시와 체결한‘용인 스마트관광도시 조성사업 감리 용역’",
        "(계약번호: R25TA00663998-01, 계약일: 2025.11.28.)에 의거 ㈜이즈피엠피가 수행하는",
        "‘용인 스마트관광도시 조성’사업에 대한 안정화지원단계 감리를 실시하고 본 감리수행")]
    cover = [Para("용인 스마트관광도시 조성사업 감리 용역", "p.1", 1), Para("종료단계", "p.1", 1)]
    assert pc.find_project_name(cover + greet) == "용인 스마트관광도시 조성사업"
    assert pc.find_project_name(cover) == "용인 스마트관광도시 조성사업"
    quoted = [Para("㈜테크원은 “관련근거 1 ”에 의거 아이티메이트 컨소시엄에서 수행한 “차세대", "p.2", 2),
              Para("경영관리시스템 구축” 사업에 대한 종료단계 감리를 실시하고 본", "p.2", 2)]
    assert pc.find_project_name(quoted) == "차세대 경영관리시스템 구축사업"


def test_one_criterion_is_enough_per_item():
    """지표마다 (1)·(2) 중 하나만 충족하면 된다: Y가 있으면 같은 지표의 N은 '-'로, 지표는 점검 완료."""
    R = pc.CriterionResult
    got = pc._one_is_enough([R("2.3(1)", "2.3", "", "Y", "근거"), R("2.3(2)", "2.3", "", "N", opinion="없음", needed="x"),
                             R("3.1(1)", "3.1", "", "N", opinion="없음"), R("3.1(2)", "3.1", "", "N", opinion="없음")])
    assert [(r.code, r.status, r.covered_by, r.opinion) for r in got] == [
        ("2.3(1)", "Y", "", ""), ("2.3(2)", "-", "2.3(1)", ""), ("3.1(1)", "N", "", "없음"), ("3.1(2)", "N", "", "없음")]
