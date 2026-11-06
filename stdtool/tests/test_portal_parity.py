"""통합시스템 점검 결과와 같은지: 예술경영지원센터 시스템들 (workbook/portal.py로 통합시스템 결과를 읽어 맞춰 본다).

통합 문서1.xlsx = 통합시스템 오류 상세내역을 내려받은 것 (시트마다 점검 화면 하나, 화면 첫 쪽 10행일 수 있음).
- 운영시스템 폴더: [ DB표준용어 ] 공통표준용어 준용 점검
- 다운로드 폴더 (한국 미술시장 정보시스템): 공통표준용어 준용 점검 + 점검 요약표(구분·완전성점검 대상·오류…)
점검 대상은 시스템 폴더의 DB표준 파일. 파일이나 공통표준 원본이 없으면 건너뛴다.
"""
from pathlib import Path

import pytest

from stdtool.config import load_settings
from stdtool.core.precheck import run_precheck
from stdtool.history import precheck_items
from stdtool.pipeline import build_matcher
from stdtool.workbook import portal
from stdtool.workbook.reader import read_meta_columns, read_output_folder

BASE = Path.home() / "OneDrive/Desktop/예술경영지원센터_표준"
OPERATION = BASE / "예술경영지원센터_(재)예술경영지원센터 운영시스템"
ART_MARKET = BASE / "예술경영지원센터_한국 미술시장 정보시스템"
EXPORTS = [(OPERATION / "통합 문서1.xlsx", OPERATION), (Path.home() / "Downloads/통합 문서1.xlsx", ART_MARKET)]
MANUALS = {OPERATION: OPERATION / "수동등록_예술경영지원센터_(재)예술경영지원센터 운영시스템.xlsx"}
CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
# 통합시스템에 있지만 공통표준 원본(공개 파일)만으로는 가릴 수 없는 오류.
# '웹주소(URL)'는 공개 공통표준 어디에도 없는데 통합시스템은 유의어 사용(용어명)으로 냈다.
UNSUPPORTED = {"유의어 사용(용어명)"}


@pytest.fixture(scope="module")
def checker():
    if not CONFIG.exists():
        pytest.skip("config.toml 없음")
    settings = load_settings(CONFIG)
    from stdtool.service import load_common
    try:
        common = load_common(settings, lambda *_: None)
    except Exception as e:   # DB 접속 불가 등
        pytest.skip(f"공통표준 원본 없음: {e}")
    if common is None:
        pytest.skip("공통표준 원본 없음")
    matcher = build_matcher(common, settings)

    def run(folder):
        data = read_output_folder(folder)
        if not all(k in data for k in ("domains", "terms", "words", "columns")):
            pytest.skip(f"시스템 폴더에 DB표준 파일 없음: {folder.name}")
        manual = MANUALS.get(folder)
        meta = read_meta_columns([manual]) if manual and manual.exists() else None
        result = run_precheck(data["domains"], data["terms"], data["words"], data["columns"], meta,
                              settings.length_required_types, matcher, common.domains)
        summary = {"counts": {}, "completeness": {a: [t, e] for a, t, e, *_ in result.completeness_rows()}}
        items = precheck_items(result, data["domains"], data["terms"], data["words"])
        for screen, *_ in items:
            summary["counts"][screen] = summary["counts"].get(screen, 0) + 1
        return items, summary
    return run


@pytest.mark.parametrize("export, folder", EXPORTS, ids=["운영시스템", "한국 미술시장 정보시스템"])
def test_matches_portal_exports(checker, export, folder):
    if not (export.exists() and folder.exists()):
        pytest.skip("통합시스템 결과 파일 없음")
    sheets, summary, _ = portal.read_portal([export])
    items, run_summary = checker(folder)
    for d in portal.compare(sheets, items):
        assert not (d.only_portal or d.only_program or d.different), (d.screen, d.only_portal, d.only_program,
                                                                      d.different)
        assert {x[3] for x in d.unsupported} <= UNSUPPORTED, d.screen
    for name, header, theirs, ours in portal.summary_rows(summary, run_summary):
        assert portal.result_text(theirs, ours) in ("같음", "프로그램에 없는 점검"), (name, header, theirs, ours)
