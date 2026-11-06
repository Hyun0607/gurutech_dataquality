"""기관표준 점검과 A값 (2-1-3-1 상위표준을 준용한 데이터 표준 정의의 가중치).

근거: 기관별 A값 자가진단 가이드(2026.10), 세부 안내서 p.62·p.74~78.
- A = 1   : 공통표준을 준용하여 기관표준을 정의
- A = 0.9 : 기관표준을 정의했으나 공통표준을 준용하지 않음
- A = 0.8 : 기관표준을 정의하지 않음
- 정의 인정: 용어·단어·도메인·코드 전부 (완전성 점검 대상 건수 − 완전성 점검 오류 건수) > 0
- 준용 인정: 용어·단어·도메인 전부 (공통표준 준용 점검 대상 건수 − 공통표준 준용 점검 오류 건수) > 0
- 대상 건수가 0이면 통과가 아니다 (가이드 FAQ). 통합시스템의 '최신' 기관표준 점검 결과가 기준이다.

통합시스템 점검결과 파일이면 그 결과를 그대로 세고(실제 A값), 등록 양식이면 프로그램이 같은 규칙으로 점검한다(예상 A값).
기관표준 완전성·공통표준 준용 규칙은 DB표준과 같아서 core.precheck를 그대로 쓴다. 코드 점검만 여기서 한다(p.76).
"""
from collections import Counter
from dataclasses import dataclass, field

from ..config import DEFAULT_LENGTH_REQUIRED
from ..vba import s
from ..workbook.inst_reader import AREAS, SOURCE_PORTAL, InstStandard
from . import precheck as pc

DEFINE_AREAS = AREAS                  # 정의: 용어·단어·도메인·코드
CONFORM_AREAS = ("용어", "단어", "도메인")   # 준용: 코드는 행정표준코드라 공통표준 준용 점검이 없다

# 기관표준코드 완전성 점검 (안내서 p.64 필수값, p.76)
CODE_MESSAGES = {"K01": "누락(코드명)", "K02": "누락(코드값)", "K03": "누락(코드값의미)", "K04": "중복(코드값)",
                 "K05": "중복(코드값의미)", "K06": "형식 오류(제정일자)"}
CODE_DETAILS = {"K01": "한글코드명과 영문코드명이 모두 비어 있는 경우 (둘 중 하나만 있으면 됨)", "K02": "코드값이 비어 있는 경우",
                "K03": "코드값의미가 비어 있는 경우", "K04": "한글코드명이 같은 코드 안에 코드값이 중복 존재하는 경우",
                "K05": "한글코드명이 같은 코드 안에 코드값의미가 중복 존재하는 경우", "K06": "YYYYMMDD 형식 아닌 경우"}


@dataclass
class InstIssue:
    area: str          # 용어 / 단어 / 도메인 / 코드
    kind: str          # 완전성 / 공통표준 준용
    row: int           # 파일 행 번호 (등록 양식은 머리글 다음이 2)
    key: str
    message: str       # 오류명 (통합시스템과 같게)
    detail: str = ""


@dataclass
class AreaCount:
    total: int = 0          # 완전성 점검 대상 건수
    errors: int = 0         # 완전성 점검 오류 건수
    targets: int = 0        # 공통표준 준용 점검 대상 건수
    conform_errors: int = 0

    @property
    def defined(self) -> bool:
        return self.total - self.errors > 0

    @property
    def conformed(self) -> bool:
        return self.targets - self.conform_errors > 0


@dataclass
class InstCheck:
    inst: InstStandard
    counts: dict                                  # 영역 → AreaCount
    issues: list = field(default_factory=list)    # InstIssue
    actual: bool = False                          # 통합시스템 점검결과로 센 것 (아니면 프로그램 점검 = 예상)

    @property
    def defined(self) -> bool:
        return all(self.counts[a].defined for a in DEFINE_AREAS)

    @property
    def conformed(self) -> bool:
        return all(self.counts[a].conformed for a in CONFORM_AREAS)

    @property
    def a_value(self) -> float:
        return 1.0 if self.defined and self.conformed else 0.9 if self.defined else 0.8

    @property
    def verdict(self) -> str:
        return ("공통표준을 준용하여 기관표준을 정의" if self.a_value == 1 else
                "기관표준을 정의했으나 공통표준 미준용" if self.a_value == 0.9 else "기관표준 미정의")

    def item_a(self, area: str) -> float:
        """세부 안내서 p.78 예시처럼 항목(용어·단어·도메인)별로 볼 때의 A."""
        c = self.counts[area]
        return 0.8 if not c.defined else 1.0 if area == "코드" or c.conformed else 0.9

    def reasons(self) -> list:
        """A값을 깎는 이유 (쉬운 말)."""
        out = []
        for a in DEFINE_AREAS:
            c = self.counts[a]
            if c.total == 0:
                out.append(f"기관표준{a}이(가) 없습니다 (완전성 점검 대상 0건) → 정의 불인정")
            elif not c.defined:
                out.append(f"기관표준{a} {c.total:,}건이 모두 완전성 오류입니다 → 정의 불인정")
        for a in CONFORM_AREAS:
            c = self.counts[a]
            if c.total and c.targets == 0:
                out.append(f"기관표준{a} 중 공통표준과 이름·영문약어가 같은 것이 없습니다 (준용 대상 0건) → 준용 불인정")
            elif c.targets and not c.conformed:
                out.append(f"기관표준{a}의 공통표준 준용 대상 {c.targets:,}건이 모두 오류입니다 → 준용 불인정")
        return out


def check_codes(codes: list) -> list:
    """기관표준코드 완전성. 열: A 관리부서명, B 한글코드명, C 영문코드명, ..., G 코드값, H 코드값의미, I 제정일자."""
    issues = []
    values, meanings = Counter(), Counter()
    for c in codes:
        name = s(c[1]) or s(c[2])
        values[(name, s(c[6]))] += 1
        meanings[(name, s(c[7]))] += 1
    for i, c in enumerate(codes):
        row, name = i + 2, s(c[1]) or s(c[2])
        key = f"{name}={s(c[6])}"
        found = []
        if not name:
            found.append(("K01", ""))
        if not s(c[6]):
            found.append(("K02", ""))
        if not s(c[7]):
            found.append(("K03", ""))
        if s(c[6]) and values[(name, s(c[6]))] > 1:
            found.append(("K04", s(c[6])))
        if s(c[7]) and meanings[(name, s(c[7]))] > 1:
            found.append(("K05", s(c[7])))
        if reason := pc.date_format_error(c[8]):
            found.append(("K06", reason))
        issues += [InstIssue("코드", "완전성", row, key, CODE_MESSAGES[k], d) for k, d in found]
    return issues


def _from_portal(inst: InstStandard) -> InstCheck:
    """통합시스템 점검결과 파일: 결과 열을 그대로 센다."""
    counts, issues = {}, []
    for area in AREAS:
        rows, results = inst.area(area), inst.results.get(area, [])
        c = AreaCount(total=len(rows))
        for i, (comp, comp_text, conf, conf_text) in enumerate(results):
            key = s(rows[i][2] if area == "용어" else rows[i][1] if area in ("단어", "코드") else rows[i][2]) or s(rows[i][0])
            if comp == "오류":
                c.errors += 1
                issues += [InstIssue(area, "완전성", i + 3, key, m.strip()) for m in s(comp_text).split(",") if m.strip()]
            if conf in ("성공", "오류"):
                c.targets += 1
            if conf == "오류":
                c.conform_errors += 1
                issues += [InstIssue(area, "공통표준 준용", i + 3, key, m.strip()) for m in s(conf_text).split(",") if m.strip()]
        counts[area] = c
    return InstCheck(inst, counts, issues, actual=True)


def check_inst(inst: InstStandard, matcher=None, common_domains: dict | None = None,
               length_required: list | None = None, use_portal: bool = True) -> InstCheck:
    """기관표준 점검. 점검결과 파일이면(use_portal) 그 결과로, 아니면 프로그램 점검.
    matcher(공통표준 원본)가 없으면 준용 점검을 못 하므로 준용 대상 0건이 된다."""
    if use_portal and inst.source == SOURCE_PORTAL:
        return _from_portal(inst)
    domains, terms, words, codes = (inst.area(a) for a in ("도메인", "용어", "단어", "코드"))
    issues = pc.check_domains(domains, length_required or DEFAULT_LENGTH_REQUIRED)
    issues += pc.check_terms(terms, domains, None, issues)   # T08(구성 단어)은 기관표준 점검에 없다
    official = {w.name.upper() for w, forbidden in matcher.words.values() if not forbidden} if matcher else None
    issues += pc.check_words(words, official)
    blocking = pc.DOMAIN_BLOCKING | pc.TERM_BLOCKING | pc.WORD_BLOCKING
    targets = {}
    common = pc.check_common(terms, words, matcher, domains, issues, common_domains, targets) if matcher else []
    out = [InstIssue(i.area, "완전성", i.row, i.key, i.message, i.detail) for i in issues if i.code in blocking]
    out += [InstIssue(i.area, "공통표준 준용", i.row, i.key, i.message, i.detail) for i in common]
    out += check_codes(codes)
    counts = {}
    for area in AREAS:
        bad = {i.row for i in out if i.area == area and i.kind == "완전성"}
        conform_bad = {i.row for i in out if i.area == area and i.kind == "공통표준 준용"}
        counts[area] = AreaCount(len(inst.area(area)), len(bad), len(targets.get(area, ())), len(conform_bad))
    return InstCheck(inst, counts, out, actual=False)
