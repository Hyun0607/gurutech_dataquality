"""예방적 품질관리(2-1-2): 기관명 맞추기, 사업유형·지표, 다음 회차 예측, 사업단 파일 읽기, 기록."""
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from stdtool import preventive_store as store
from stdtool.core import preventive as pv
from stdtool.workbook import preventive_report as report

REAL = Path.home() / "OneDrive" / "Desktop" / "2026 프로젝트" / "★ 2026 예방적 품질관리"
REAL1 = REAL / "2026년 공공데이터 예방적 품질관리 진단 이행점검(1차) 대상.xlsx"
REAL2 = REAL / "2026년 공공데이터 예방적 품질관리 진단 이행점검(2차) 대상.xlsx"


@pytest.fixture(scope="module")
def criteria():
    return report.load_criteria()


def project(name, stage=pv.ORDER, end=date(2026, 6, 30), note="", org="한국연구재단", no=1):
    return pv.Project(2026, no, stage, "공공기관", org, "", name, date(2026, 1, 1), end, date(2025, 12, 1), note)


def test_org_key_matches_affiliated_and_corporate_names():
    assert pv.org_key("국립산림과학원(산림청)") == pv.org_key("산림청 국립산림과학원")
    assert pv.org_key("(재)예술경영지원센터") == pv.org_key("예술경영지원센터")
    assert pv.org_key("한전원자력연료(주)") == pv.org_key("한전원자력연료")
    assert pv.org_key("경기도용인시") == pv.org_key("경기도 용인시")


@pytest.mark.parametrize("name, types", [
    ("인문사회 학술연구포털 ISMP 수립", ["컨설팅"]),
    ("차세대 경영시스템 구축을 위한 정보화전략계획 수립", ["컨설팅"]),      # 컨설팅이 걸리면 컨설팅만
    ("마을버스 도착정보시스템 고도화 사업", ["고도화"]),
    ("2026년 용인시 홈페이지 기능개선 및 유지관리", ["운영유지보수", "고도화"]),
    ("2026년 특허정보시스템 구축 및 운영 사업", ["운영유지보수", "신규구축"]),
    ("종이기록물 전자화 사업", ["DB구축"]),
    ("PM 주정차 위반 신고 시스템 구축", ["신규구축"]),
    ("생성형 AI 법령검색 서비스", ["신규구축"]),                          # 키워드 없음 → 신규구축(확인필요)
])
def test_classify(criteria, name, types):
    assert pv.classify(name, criteria)[0] == types


def test_parse_amount():
    assert pv.parse_amount("3억") == 300_000_000
    assert pv.parse_amount("1.5억원") == 150_000_000
    assert pv.parse_amount("300,000,000") == 300_000_000
    assert pv.parse_amount("300000천원") == 300_000_000
    assert pv.parse_amount("12억 3,000만원") == 1_230_000_000
    assert pv.parse_amount("미정") is None
    assert pv.won_text(1_230_000_000) == "12.3억"


def test_items_follow_manual_matrix(criteria):
    # 신규구축 1억 미만: 1.1·2.1·2.2·3.1·4.2 / 10억 이상은 1.2·2.3·4.1 추가
    assert pv.items_for(["신규구축"], 50_000_000, False, criteria)[0] == ["1.1", "2.1", "2.2", "3.1", "4.2"]
    assert pv.items_for(["신규구축"], 2_000_000_000, False, criteria)[0] == \
        ["1.1", "1.2", "2.1", "2.2", "2.3", "3.1", "4.1", "4.2"]
    # 금액이 없으면 모든 구간 공통만 대응, 나머지는 △
    sure, maybe, _ = pv.items_for(["고도화"], None, False, criteria)
    assert sure == ["1.1", "2.1", "2.2", "3.1", "4.2"] and maybe == ["1.2", "2.3", "4.1"]
    # 이관이 있으면 3.2 추가, 운영유지보수는 사업비 10억 기준
    assert "3.2" in pv.items_for(["고도화"], 50_000_000, True, criteria)[0]
    assert pv.items_for(["운영유지보수"], 2_000_000_000, False, criteria)[0] == ["1.2", "2.3", "3.1", "4.1", "4.2"]
    assert pv.items_for(["컨설팅"], None, False, criteria) [:2] == (["1.1", "1.2", "2.1", "2.3", "4.2"], [])


def test_predict_next_round_next_year_and_late(criteria):
    ps = [project("ISMP 수립", end=date(2026, 5, 11)),                      # 2차 완료 기간 → 전환 예상
          project("고도화 사업", end=date(2026, 12, 31)),                    # 내년 1차
          project("구축 사업", end=date(2026, 3, 31)),                       # 이번 회차 완료 기간인데 완료 목록에 없음
          project("홈페이지 구축", note="대응 불필요(만점)"),
          project("완료 사업", stage=pv.DONE, end=date(2026, 3, 1))]
    js = pv.judge(ps, criteria, set())
    assert [j.category for j in js] == ["2차 완료 전환 예상", pv.C_NEXT_YEAR, pv.C_LATE, pv.C_FREE, "1차 완료단계 점검"]
    assert js[0].target == "2026 2차" and js[1].target == "2027 1차"
    assert "사업기간 연장 여부 확인" in js[2].flags
    assert js[3].flags == []                    # 대응 불필요 사업은 확인할 것이 없다


def test_managed_filter_and_edits(criteria):
    ps = [project("마을버스 고도화", org="경기도 용인시"), project("다른 사업", org="다른 기관")]
    managed = {pv.org_key("경기도 용인시")}
    edits = {ps[0].key: pv.Edit(amount=300_000_000, transfer="Y")}
    js = pv.judge(ps, criteria, managed, edits)
    assert [j.managed for j in js] == [True, False]
    assert js[0].required == ["1.1", "1.2", "2.1", "2.2", "2.3", "3.1", "3.2", "4.2"] and js[0].maybe == []
    assert pv.counts(js)["사업"] == 1


def _nia_file(path, no, rows_order, rows_done):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    head = ["순번", "기관유형", "기관명", "접수코드", "사업명", "사업시작일", "사업종료일", "사전협의신청일", "비고"]
    for stage, rows in (("발주", rows_order), ("완료", rows_done)):
        ws = wb.create_sheet(f"({no}차){stage}단계")
        ws.append([f"({no}차) {stage}단계 점검 대상 사업"])
        ws.append(["`"])
        ws.append(head)
        for i, r in enumerate(rows, 1):
            ws.append([i, "공공기관", *r])
    wb.save(path)
    return path


def test_read_targets_and_round_history(tmp_path, criteria):
    first = _nia_file(tmp_path / "2026년 이행점검(1차) 대상.xlsx", 1,
                      [("한국연구재단", "2025중공916", "인문사회 학술연구포털 ISMP 수립", date(2026, 1, 1), date(2026, 5, 11),
                        date(2025, 10, 1), None)], [])
    second = _nia_file(tmp_path / "2026년 이행점검(2차) 대상.xlsx", 2, [],
                       [("한국연구재단", "2025중공916", "인문사회 학술연구포털 ISMP 수립", date(2026, 1, 1), date(2026, 5, 11),
                         date(2025, 10, 1), None)])
    db = tmp_path / "history.sqlite"
    p1 = report.read_targets(first)
    assert (p1[0].year, p1[0].round, p1[0].stage, p1[0].end) == (2026, 1, pv.ORDER, date(2026, 5, 11))
    store.save_round(p1, first.name, db)
    p2 = report.read_targets(second)
    store.save_round(p2, second.name, db)
    previous, done = store.earlier(p2, db)
    j = pv.judge(p2, criteria, set(), {}, previous, done)[0]
    assert j.previous == "2026 (1차)발주단계" and j.category == "2차 완료단계 점검"
    assert [r[:3] for r in store.rounds(db)] == [(2026, 1, 1), (2026, 2, 1)]
    store.save_edit(p2[0].key, pv.Edit(types="컨설팅", amount=90_000_000), db)
    assert store.load_edits(db)[p2[0].key].amount == 90_000_000
    out = report.write_targets(pv.judge(p2, criteria, set(), store.load_edits(db)), criteria, tmp_path / "out.xlsx",
                               second.name, [("x", "y")])
    wb = openpyxl.load_workbook(out)
    assert {"요약", "관리 기관 사업", "완료 전환 예상", "내년 후보", "확인필요", "지표별 필요 산출물"} <= set(wb.sheetnames)
    assert wb["관리 기관 사업"].cell(2, 5).value == "인문사회 학술연구포털 ISMP 수립"


def test_not_a_target_file(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["아무 내용"])
    wb.save(tmp_path / "x.xlsx")
    with pytest.raises(report.ReadError):
        report.read_targets(tmp_path / "x.xlsx")


@pytest.mark.skipif(not (REAL1.exists() and REAL2.exists()), reason="사업단 1·2차 대상 파일 없음")
def test_real_round1_prediction_matches_round2(criteria):
    """1차 발주 중 '2차 완료 전환 예상' 41건 가운데 37건이 실제 2차 완료 목록에 있다 (2026-11-02 대조)."""
    p1, p2 = report.read_targets(REAL1), report.read_targets(REAL2)
    done2 = {p.key for p in p2 if p.stage == pv.DONE}
    predicted = {j.project.key for j in pv.judge(p1, criteria, set()) if pv.C_MOVE in j.category}
    assert len(predicted) == 41 and len(predicted & done2) == 37


def test_criteria_copy_in_user_folder(tmp_path, monkeypatch):
    """고칠 때는 사용자 폴더 복사본, 프로그램 기준이 더 새로우면(새 버전) 다시 프로그램 기준."""
    import os
    monkeypatch.setenv("STDTOOL_HOME", str(tmp_path))
    assert report.criteria_path() == report.CRITERIA_PATH
    mine = report.editable_criteria()
    assert mine.parent == tmp_path and report.criteria_path() == mine
    old = report.CRITERIA_PATH.stat().st_mtime - 10
    os.utime(mine, (old, old))
    assert report.criteria_path() == report.CRITERIA_PATH


_IRM = "사전협의(총괄) 목록_20261104155544.xlsx"
IRM_LIST = next((p for p in (Path(r"C:\Data Quality processing\공공데이터 품질관리 메뉴얼 및 참고 파일") / _IRM,
                             Path(r"C:\Data Quality processing") / _IRM) if p.exists()),
                Path(r"C:\Data Quality processing") / _IRM)


def _irm_row(**kw):
    row = dict(org_type="공공기관", org="한국연구재단", code="", name="데이터 플랫폼 고도화", start=date(2026, 1, 1),
               end=date(2026, 12, 31), done_end=None, applied=date(2025, 12, 1), progress="사업추진중", result="보완추진",
               review=date(2026, 3, 3), reflect=None, db=1, check_target="", irm_type="SW개발", amount=400_000_000)
    row.update(kw)
    return row


def test_irm_criteria(criteria):
    """기준1: 반려·신청대기·신청반려·결과유형 빈칸은 제외, 통보일(보완 후 협의는 반영계획 등록일)로 1차(~4.30)·2차(~8.31).
    기준2: '21.3.12 이후 신청 + DB 의견 + 사업완료 종료일(없으면 계획 종료일로 완료 예정)로 1차·2차, 그 뒤는 내년."""
    rows = [_irm_row(name="가 사업", review=date(2026, 3, 3)),
            _irm_row(name="나 사업", review=date(2026, 6, 9), db=0),
            _irm_row(name="다 사업", result="보완후협의", review=date(2026, 3, 1), reflect=date(2026, 5, 10)),
            _irm_row(name="라 사업", progress="사전협의완료(반려/취소)", result="신청반려"),
            _irm_row(name="마 사업", result="", review=None),
            _irm_row(name="바 사업", review=date(2025, 11, 13), done_end=date(2026, 5, 29)),
            _irm_row(name="사 사업", review=date(2025, 10, 1), end=date(2026, 7, 1)),
            _irm_row(name="아 사업", review=date(2026, 9, 20))]
    ps = pv.irm_projects(rows, criteria)
    got = {(p.name, p.stage): (p.category, p.target) for p in ps}
    assert got[("가 사업", pv.ORDER)] == ("2026 1차 발주단계 대상 예측", "2026 1차")
    assert got[("나 사업", pv.ORDER)] == (pv.C_FREE, "2026 2차")                       # DB 의견 없음 → 대응 불필요
    assert got[("다 사업", pv.ORDER)][1] == "2026 2차"                                  # 반영계획 점검등록일 기준
    assert got[("라 사업", pv.C_OUT)][0].startswith(pv.C_OUT)
    assert got[("마 사업", pv.C_OUT)][0].startswith(pv.C_OUT)
    assert got[("바 사업", pv.DONE)] == ("2026 2차 완료단계 대상 예측", "2026 2차")
    assert got[("사 사업", pv.DONE)] == (f"2026 2차 {pv.C_PLANNED}", "2026 2차")        # 완료 등록 전 → 계획 종료일
    assert got[("아 사업", pv.ORDER)] == (pv.C_NEXT_ORDER, "2027 1차")                  # 9월 이후 통보 → 내년
    assert ("나 사업", pv.DONE) not in got                                               # DB 의견 없으면 완료 점검 대상 아님
    j = {x.project.name: x for x in pv.judge(ps, criteria, set())}
    assert j["가 사업"].types == ["신규구축"] and j["가 사업"].amount == 400_000_000      # IRM 사업유형·예산총액


def test_irm_type_mapping(criteria):
    assert pv.classify_irm("기획(BPR/ISP, ISMP 등), DB구축", "앵커 성과 플랫폼", criteria)[0] == ["컨설팅"]
    assert pv.classify_irm("SW개발, 운영유지보수", "유망기술 발굴시스템 고도화사업", criteria)[0] == ["운영유지보수", "고도화"]
    assert pv.classify_irm("", "인문사회 ISMP 수립", criteria)[0] == ["컨설팅"]


@pytest.mark.skipif(not IRM_LIST.exists(), reason="IRM 사전협의(총괄) 목록 없음")
def test_real_irm_list_matches_nia_lists(criteria):
    """한국연구재단 11건: 발주 1·2차, 완료 2차, 대응 불필요가 사업단 1·2차 대상 목록과 모두 같다 (2026-11-05 대조)."""
    ps = report.read_targets(IRM_LIST, criteria)
    got = {(p.name, p.stage_label, p.needs_action) for p in ps if p.stage != pv.C_OUT}
    assert ("인문사회 학술연구포털 ISMP 수립", "(1차)발주단계", True) in got
    assert ("인문사회 학술연구포털 ISMP 수립", "(2차)완료단계", True) in got
    assert ("4단계 BK21 종합정보관리시스템 클라우드 전환", "(2차)발주단계", False) in got
    assert ("KRI 포털 클라우드 네이티브 전환 사업", "(1차)발주단계", False) in got
    assert sum(p.stage == pv.C_OUT for p in ps) == 2
