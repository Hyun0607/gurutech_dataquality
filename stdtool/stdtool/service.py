"""실행 단위: 사전 읽기 → 표준구조 작업 → 산출물 저장. 명령줄(cli)과 화면(ui)이 같이 쓴다.

log: 진행 상황 한 줄을 받는 함수 (명령줄은 print, 화면은 진행 기록).
step(key, detail): 단계 하나를 마칠 때마다 (화면 진행 단계 표시). 순서는 STEPS.
"""
import random
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import db
from .config import Settings
from .core import linkage, relation
from .dictionary import load_common_standard, load_from_macro_workbook
from .pipeline import PIPELINE_STEPS, RunResult, run
from .workbook.linkage_report import export_linkage, read_link_review
from .workbook.mapping_report import read_mapping_decisions
from .workbook.reader import read_domain_pool, read_meta
from .workbook.writer import (STANDARD_DIR, export_manual, export_relations, export_standard,
                              output_folder)


STEPS = [("dict", "표준 사전 읽기"), ("meta", "메타 읽기"), *PIPELINE_STEPS,
         ("export", "산출물 저장"), ("relation", "테이블관계정의서 (물리 ERD 대체)"),
         ("link", "연계 정의서 (컬럼정의서 기준)")]


class RunError(Exception):
    pass


@dataclass
class Outcome:
    result: RunResult
    folder: Path
    paths: list = field(default_factory=list)
    candidates: list = field(default_factory=list)   # 연계후보 (core.linkage.LinkColumn)
    fallback: list = field(default_factory=list)     # 문자값 분류 (RunResult.text_fallback_rows)
    link_list: list = field(default_factory=list)    # 2-1-5-1 목록 정의서에 쓴 행
    link_status: list = field(default_factory=list)  # 2-1-5-2 관리현황 자료에 쓴 행
    relations: list = field(default_factory=list)    # 2-1-4-1 테이블관계 (core.relation.Relation)
    relation_info: tuple = ({}, {})                  # (테이블 정보, 컬럼 한글명) — core.relation.build
    dict_version: str = ""                           # 실행에 쓴 표준 사전 (예: 2026-10-29 · 공통표준 8차 2025.11)


def validate(settings: Settings) -> None:
    if not settings.meta:
        raise RunError("메타 파일을 골라 주세요.")
    if not Path(settings.meta).exists():
        raise RunError(f"메타 파일이 없습니다: {settings.meta}")
    if not (settings.db.use or settings.macro_workbook):
        raise RunError("표준 사전이 필요합니다: 설정에서 DB를 쓰거나 매크로 파일을 지정하세요.")


def load_common(settings: Settings, log=print):
    if settings.db.use:
        with db.connect(settings.db) as conn:
            return db.load_common(conn)
    if not settings.common_term:
        return None
    log(f"      공통표준 원본: {settings.common_term.name}"
        + (f", {settings.common_word.name}" if settings.common_word else "")
        + (f", {settings.common_domain.name}" if settings.common_domain else ""))
    return load_common_standard(settings.common_term, settings.common_word, settings.common_domain)


def execute(settings: Settings, log=print, link_review: Path | None = None, step=None) -> Outcome:
    done = step or (lambda key, detail="": None)
    validate(settings)
    pool = read_domain_pool(settings.domain_pool) if settings.enhanced and settings.domain_pool else {}
    try:
        dict_version = ""
        if settings.db.use:
            source = f"사전 파일 {Path(settings.db.file).name}" if settings.db.file else f"DB {settings.db.database}"
            log(f"[1/4] 표준 사전 읽기: {source}")
            with db.connect(settings.db) as conn:
                dicts = db.load_dicts(conn, settings.org_name)
                common = db.load_common(conn) if settings.enhanced else None
                dict_version = db.dict_label(db.dict_info(conn)) or f"MySQL {settings.db.database}"
        else:
            log(f"[1/4] 표준 사전 읽기: {Path(settings.macro_workbook).name}")
            dicts = load_from_macro_workbook(settings.macro_workbook)
            common = load_common(settings, log) if settings.enhanced else None
            dict_version = f"매크로 {Path(settings.macro_workbook).name}"
    except db.DbError as e:
        raise RunError(str(e)) from e
    if settings.db.use:   # 기관표준여부는 사전에 그 기관의 기관표준이 있는지로 정한다 (화면에서 고르지 않는다)
        settings.inst_std = "Y" if dicts.inst.rows else "N"
        log(f"      기관표준: {f'{len(dicts.inst.rows):,}용어 준용' if dicts.inst.rows else '사전에 없음 (미준용)'}")
    done("dict", f"Code_type {len(dicts.code_type.rows):,} · Code_tail {len(dicts.code_tail.rows):,} · 공통표준 "
                 f"{len(common.terms) if common else 0:,}용어")
    decisions = read_mapping_decisions(settings.synonym_review) if common and settings.synonym_review else None
    if decisions is not None:
        log(f"      검토 파일 반영: {settings.synonym_review.name} ({len(decisions)}건)")
    log(f"[2/4] 메타 읽기: {Path(settings.meta).name}")
    meta = read_meta(settings.meta, settings.meta_sheet)
    log(f"      {len(meta)}행 / 방식: {'고도화' if settings.enhanced else '매크로'}")
    done("meta", f"{len(meta):,}행")
    log("[3/4] 표준구조 작업")

    def stage(key, detail=""):
        name = dict(STEPS)[key]
        log(f"      {name}: {detail}" if detail else f"      {name}")
        done(key, detail)

    result = run(meta, dicts, settings, pool, common, decisions, stage)

    log("[4/4] 산출물 저장")
    # 제출용 정의서만 파일로 낸다. 사전점검·현행화·표준매핑·변경이력은 화면에서 본다.
    folder = output_folder(settings)
    paths = export_standard(result, settings)
    paths += export_manual(result.manual, settings)
    out = Outcome(result, folder, paths)
    out.dict_version = dict_version
    out.fallback = result.text_fallback_rows()
    done("export", f"파일 {len(out.paths):,}개 → {folder}")
    out.relations, info, kor = relation.build(result.definitions.columns, result.definitions.tables, result.meta,
                                              settings.db_eng_name or settings.db_name)
    out.relation_info = (info, kor)
    out.paths.append(export_relation_file(out, settings))
    used = sum(1 for r in out.relations if r.use)
    log(f"      테이블관계정의서: 관계 {used:,}개 (부모 {len({r.parent for r in out.relations}):,} 테이블)")
    done("relation", f"관계 {used:,}개")
    if settings.link_enabled:
        out.candidates = link_candidates(result, settings, link_review or settings.link_review, log)
        out.paths += export_link(out, settings)
        chosen = next((c for c in out.candidates if c.selected), None)
        name = f"{chosen.table}.{chosen.column}" if chosen else "없음"
        log(f"      연계: 컬럼정의서 {len(out.candidates)}개 컬럼 중 1행 ({name}) → 2-1-5-1·2-1-5-2")
        done("link", f"1행 · {name}")
    else:
        done("link", "건너뜀 (설정에서 끔)")
    return out


def export_relation_file(out: Outcome, settings: Settings) -> Path:
    """테이블관계정의서를 다시 쓴다 (화면에서 뺀 관계는 빼고)."""
    return export_relations(relation.rows(out.relations, *out.relation_info), settings)


def link_candidates(result: RunResult, settings: Settings, review: Path | None = None, log=print) -> list:
    """컬럼정의서 행마다 연계후보를 만들고 추천을 표시한다 (PK·FK·개인정보는 메타에서). review가 있으면 그 선택을 따른다."""
    candidates = linkage.candidates_from_definitions(result.definitions.columns, result.definitions.tables, result.meta,
                                                     settings.org_name, settings.db_name, settings.db_eng_name,
                                                     settings.system_name)
    linkage.pick_one(candidates)
    for c in candidates:
        c.direction, c.cycle = settings.link_direction, settings.link_cycle
        c.user = settings.link_user_org or c.user
    if review:
        linkage.apply_review(candidates, read_link_review(Path(review)))
        log(f"      연계후보 검토 파일 반영: {Path(review).name}")
    return candidates


def link_rows(candidates: list, settings: Settings, rng: random.Random | None = None) -> tuple:
    """고른 컬럼 하나로 (2-1-5-1 목록 정의서 행, 2-1-5-2 관리현황 행). 점검 일시는 부를 때마다 새로 뽑는다."""
    selected = [c for c in candidates if c.selected][:1]
    today = date.today()
    month, day = (int(x) for x in settings.link_start.split("-"))
    times = linkage.check_times(len(selected), today, date(today.year, month, day), rng or random.Random())
    return (linkage.list_rows(selected),
            linkage.status_rows(selected, times, settings.link_result, settings.link_action, settings.link_method))


def export_link(out: Outcome, settings: Settings, rng: random.Random | None = None) -> list:
    """2-1-5-1·2-1-5-2 파일을 쓰고, 쓴 행은 out.link_list·link_status에 둔다 (화면에서 미리보기)."""
    out.link_list, out.link_status = link_rows(out.candidates, settings, rng)
    return export_linkage(out.link_list, out.link_status, out.folder / STANDARD_DIR, settings.db_name)
