"""표준구조_작업_전체 + 메타_작업_전체 흐름. 매크로 순서를 그대로 따르고 고도화는 정해진 지점에만 끼운다."""
from dataclasses import dataclass, field

from .config import Settings
from .core.cleanse import (apply_length_policy, final_refine, fix_max_length, meta_to_raw, refine,
                           split_type_length, unify_type_alias)
from .core.currency import CurrencyResult, run_currency
from .core.consolidate import Definitions, apply_domains, build_definitions, dedupe_terms, fix_domain_lengths
from .core.enhance import drop_unused_domains, ensure_term_domains, number_duplicate_terms
from .core.generate import fill_words_from_common, make_domains, make_terms, make_words
from .core.manual import build_manual, copy_definitions_to_meta
from .core.mapping import apply_dbstd, common_mapping, inst_mapping
from .core.naming import DomainNamer
from .core.precheck import PrecheckResult, run_precheck
from .core.synonym import SynonymMatcher, apply_matches, match_raw
from .dictionary import CommonStandard, StandardDict
from .model import ChangeLog, col


@dataclass
class RunResult:
    raw: list
    domains: list
    terms: list
    words: list
    definitions: Definitions
    domain_fixed: set
    meta: list
    manual: list
    precheck: PrecheckResult
    currency: CurrencyResult
    log: ChangeLog
    namer: DomainNamer
    synonym_results: list = field(default_factory=list)
    raw_before_mapping: list = field(default_factory=list)
    common: CommonStandard | None = None

    def text_fallback_rows(self) -> list:
        """영문 꼬리를 Code_tail에서 못 찾아 '문자값'이 된 컬럼을 꼬리별로 (컬럼 많은 순).
        같은 영문약어의 공통표준단어가 있으면 꼬리를 정할 때 참고하도록 붙인다."""
        words = {}
        for w in self.common.words if self.common else []:
            words.setdefault(w.abbr.upper(), w)
        groups = {}
        for (tail, eng, kor), n in self.namer.text_fallback.items():
            g = groups.setdefault(tail, {"n": 0, "kor": [], "eng": []})
            g["n"] += n
            for key, v in (("kor", kor), ("eng", eng)):
                if v and v not in g[key]:
                    g[key].append(v)
        out = []
        for tail, g in sorted(groups.items(), key=lambda kv: (-kv[1]["n"], kv[0])):
            w = words.get(tail)
            out.append((tail, g["n"], ", ".join(g["kor"][:5]), ", ".join(g["eng"][:5]),
                        w.name if w else "", w.is_format if w else "", w.domain_class if w else ""))
        return out

    def notes(self) -> list:
        """고도화 요약 (변경이력 파일의 두 번째 시트)."""
        out = [("방식", "고도화" if self.namer.enhanced else "매크로", "")]
        out.append(("Code_tail에 꼬리가 없어 문자값으로 분류", "'문자값 분류' 시트", sum(self.namer.text_fallback.values())))
        for t, n in self.namer.unregistered_types.most_common():
            out.append(("① Code_type 미등록 타입", t, n))
        for (kor, cls), n in self.namer.korean_classified.most_common():
            out.append(("① 한글명으로 분류 판정", f"{kor} → {cls}", n))
        for name, n in self.namer.reused.most_common():
            out.append(("① 기존 도메인 재사용", name, n))
        added = sum(1 for c in self.log.items if c.step == "① 도메인 보장" and c.action == "추가")
        out.append(("① 용어 도메인 자동 추가", "", added))
        if self.synonym_results:
            applied = [r for r in self.synonym_results if r.confirmed]
            out.append(("② 공통표준 치환 적용(한글·영문 쌍)", "", len(applied)))
            out.append(("② 공통표준 치환 적용(컬럼)", "", sum(len(r.rows) for r in applied)))
            out.append(("② 공통표준단어로 채운 단어", "", sum(1 for c in self.log.items if c.step == "② 공통표준단어")))
        return out


# 실행 단계 (화면 진행 표시). (키, 이름) — 매크로 표준구조_작업_전체·메타_작업_전체 순서
PIPELINE_STEPS = [
    ("raw", "메타 → RAW"),
    ("refine", "값 정제"),
    ("inst", "기관표준 매핑"),
    ("synonym", "② 공통표준 유의어·금칙어"),
    ("common", "공통표준 매핑"),
    ("domain", "도메인 생성"),
    ("term", "용어·단어 생성"),
    ("apply", "DB표준·도메인 적용"),
    ("definition", "테이블·컬럼 정의서"),
    ("manual", "수동등록"),
    ("precheck", "③ 사전점검"),
    ("currency", "구조 현행화 검증"),
]


def s_upper(value) -> str:
    return str(value or "").strip().upper()


def manual_columns(manual: list) -> list:
    return [{"row": i + 4, "table": r[col("R")], "kor": r[col("Z")], "eng": r[col("AA")],
             "type": r[col("AF")], "length": r[col("AG")]} for i, r in enumerate(manual)]


def build_matcher(common: CommonStandard | None, settings: Settings) -> SynonymMatcher | None:
    if common is None:
        return None
    return SynonymMatcher(common, settings.synonym_top, settings.synonym_min_score)


def run(meta_rows: list, dicts: StandardDict, settings: Settings, pool: dict | None = None,
        common: CommonStandard | None = None, decisions: dict | None = None, progress=None) -> RunResult:
    """common: 공통표준 원본(② 사용 시). decisions: 검토 파일에서 읽은 확정 값.
    progress(key, detail): 단계 하나를 마칠 때마다 부른다 (key는 PIPELINE_STEPS의 첫 값)."""
    report = progress or (lambda key, detail="": None)
    log = ChangeLog()
    enhanced = settings.enhanced
    reg_date = settings.enact_date
    matcher = build_matcher(common, settings) if enhanced else None

    raw = meta_to_raw(meta_rows)
    if enhanced and settings.parse_type_length:
        split_type_length(raw, log)
    report("raw", f"{len(raw):,}행")
    refine(raw, log)
    report("refine", f"변경 {len(log.items):,}건")
    inst_mapping(raw, dicts.inst, settings.inst_std, log)
    report("inst", "기관표준 준용" if s_upper(settings.inst_std) == "Y" else "미준용 (건너뜀)")
    raw_before, synonym_results = [], []
    if matcher is not None:
        raw_before = [list(r) for r in raw]
        synonym_results = match_raw(raw, matcher)
        apply_matches(raw, synonym_results, decisions, settings.synonym_auto_apply, matcher, log)
        report("synonym", f"한글·영문 쌍 {len(synonym_results):,}개 · 치환 {sum(1 for r in synonym_results if r.confirmed):,}")
    else:
        report("synonym", "건너뜀 (공통표준 원본 없음)")
    common_mapping(raw, dicts.common, log)
    if enhanced and settings.type_alias:   # 공통표준 매핑이 넣은 오라클식 표기(CHAR·VARCHAR)까지 맞추도록 그 뒤에
        unify_type_alias(raw, meta_rows, settings.type_alias, log)
    if enhanced:
        fix_max_length(raw, log)
    if enhanced and settings.length_policy:
        apply_length_policy(raw, settings.length_policy, log)
    report("common", f"공통표준 {len(dicts.common.rows):,}행과 대조")

    namer = DomainNamer(dicts, settings if enhanced else None, pool or {})
    domains = make_domains(raw, namer, reg_date, log)
    report("domain", f"도메인 {len(domains):,}건")
    terms = make_terms(raw, namer, reg_date)
    words = make_words(terms, reg_date, log)
    if matcher is not None and settings.fill_words_from_common and common.words:
        fill_words_from_common(words, common.words, log)
    if enhanced:   # 같은 용어명은 번호로 나눠야 DB표준 적용이 컬럼을 한 영문으로 합치지 않는다.
        # 중복 처리 전에 나눈다: 뒤에 나누면 '용어명별 최빈 도메인만 유지'가 도메인이 다른 영문(수정일 MOD_DT 날짜형 등)을
        # 먼저 지워, 그 컬럼들이 '표준용어 미존재'가 된다 (2026-10-30 기관별 실제 적용률 대조).
        common_eng = {s_upper(r[1]) for r in dicts.common.rows if len(r) > 1}
        terms = number_duplicate_terms(terms, common_eng, log)
    terms = dedupe_terms(terms, log)
    report("term", f"용어 {len(terms):,}건 · 단어 {len(words):,}건")
    apply_dbstd(raw, terms, log)
    apply_domains(raw, terms, domains, log, with_scale=enhanced)
    final_refine(raw, log)
    report("apply", "DB표준·도메인 적용, 최종 정제")
    definitions = build_definitions(raw, log)
    domain_fixed = fix_domain_lengths(domains, log)
    if enhanced and settings.ensure_term_domains:
        domains = ensure_term_domains(raw, terms, domains, namer, reg_date, log)
    if enhanced:
        domains = drop_unused_domains(terms, domains, log)
    report("definition", f"테이블 {len(definitions.tables):,} · 컬럼 {len(definitions.columns):,}"
                         + (f" · 제거 {len(definitions.removed):,}" if definitions.removed else ""))

    removed = set(definitions.removed_raw_index)
    meta = [m for j, m in enumerate(meta_rows) if j not in removed]
    meta = copy_definitions_to_meta(meta, definitions.columns)
    manual = build_manual(meta)
    report("manual", f"수동등록 {len(manual):,}행")

    meta_columns = manual_columns(manual)
    precheck = run_precheck(domains, terms, words, definitions.columns, meta_columns,
                            settings.length_required_types, matcher, common.domains if matcher else None,
                            dicts.inst.rows if s_upper(settings.inst_std) == "Y" else None)
    report("precheck", f"예상 적용률 {precheck.rate:.1f}% · 오류 컬럼 {precheck.error_columns:,}")
    currency = run_currency(definitions.tables, definitions.columns, meta_columns)
    report("currency", f"현행화율 {currency.rate:.1f}%")
    return RunResult(raw, domains, terms, words, definitions, domain_fixed, meta, manual, precheck, currency, log, namer,
                     synonym_results, raw_before, common)
