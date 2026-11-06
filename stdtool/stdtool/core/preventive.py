"""예방적 품질관리(2-1-2): 사업단 이행점검 대상 사업을 관리 기관으로 거르고, 사업유형·대응 지표·다음 회차를 판정한다.

기준(templates/예방적품질관리_기준.xlsx)은 workbook/preventive_report.load_criteria 가 읽어 Criteria로 넘긴다.
여기에는 파일·화면을 모르는 계산만 둔다.
"""
import re
from dataclasses import dataclass, field
from datetime import date

ITEMS = ["1.1", "1.2", "2.1", "2.2", "2.3", "3.1", "3.2", "4.1", "4.2"]
TYPES = ["컨설팅", "신규구축", "고도화", "운영유지보수", "DB구축"]
TRANSFER_ITEM = "3.2"
NO_OPINION = "대응 불필요"      # 사업단 비고: DB 분야 검토의견 없음(만점)
ORDER, DONE = "발주", "완료"

# 분류 (다음 회차 예측)
C_DONE = "완료단계 점검"
C_FREE = "대응 불필요(만점)"
C_MOVE = "완료 전환 예상"
C_MOVED = "완료 전환됨"
C_BOTH = "같은 회차 완료단계에도 있음"
C_LATE = "종료일 지남·완료 목록 없음(연장 확인)"
C_NEXT_YEAR = "내년 완료단계 후보"
C_LATER = "내후년 이후 완료"
C_NO_END = "종료일 없음"
# IRM 사전협의(총괄) 목록으로 먼저 예측할 때
C_EXPECT = "대상 예측"                       # '2026 2차 발주단계 대상 예측'
C_PLANNED = "완료 예정(완료 등록 전)"
C_NEXT_ORDER = "내년 발주단계 후보"
C_OUT = "비대상"
EXCLUDED_PROGRESS = ("사전협의완료(반려/취소)", "사전협의신청대기")
EXCLUDED_RESULT = ("신청반려", "")
LOWER_APPLY = date(2021, 3, 12)              # 기준2: '21.3.12. 이후 사전협의 신청


@dataclass
class Round:
    year: int
    no: int
    order_start: date | None
    order_end: date | None
    done_start: date
    done_end: date
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.year} {self.no}차"


@dataclass
class Item:
    code: str
    name: str
    area: str
    evidence: str
    words: list                  # 본문에서 찾을 단어
    screen: str = ""
    name_words: list = field(default_factory=list)    # 요구사항 이름으로 지표를 정할 때 ('구조+설계' = 둘 다)
    name_except: list = field(default_factory=list)
    file_words: list = field(default_factory=list)    # 완료단계 제출 파일 이름
    criteria: str = ""                                 # 진단기준 ①·② (줄바꿈으로 나눔)
    guides: list = field(default_factory=list)        # 가이드 폴더에 넣을 가이드 파일 이름


@dataclass
class Detail:
    """완료단계 세부 기준 하나 (사업단 '사업 완료단계 진단결과'의 1.1(1)~4.2(2))."""
    code: str                    # '1.1(1)'
    item: str                    # '1.1'
    text: str                    # 검토 항목
    words: list                  # 보고서에서 찾을 단어 ('A+B' = 같은 줄에 둘 다)
    file_words: list             # 산출물 파일 이름 단어
    skip_types: list             # 이 사업유형이면 '-'
    opinion: str                 # 못 찾았을 때 검토의견 (사업단 문구)
    needed: str                  # 필요 산출물


@dataclass
class Requirement:
    """매뉴얼 3.2.2 표준 요구사항 한 개."""
    kind: str
    band: str
    code: str
    rid: str
    name: str
    definition: str
    detail: str
    output: str


@dataclass
class Criteria:
    rounds: list                 # [Round] 연도·회차 순
    type_words: list             # [(유형, [키워드])] 위에서부터 본다
    transfer_words: list
    matrix: dict                 # {(유형, 금액구간): {코드: 'O'|'이관'|''}}
    bands: dict                  # {유형: [(금액구간, 하한, 상한, 금액기준)]}
    items: dict                  # {코드: Item}
    requirements: list = field(default_factory=list)   # [Requirement]
    details: list = field(default_factory=list)        # [Detail] 완료단계 세부 기준 18개

    def round(self, year: int, no: int) -> Round | None:
        return next((r for r in self.rounds if r.year == year and r.no == no), None)


@dataclass
class Project:
    year: int                    # 평가연도
    round: int                   # 회차
    stage: str                   # 발주 / 완료
    org_type: str
    org: str
    code: str
    name: str
    start: date | None
    end: date | None
    applied: date | None
    note: str = ""
    # IRM 사전협의(총괄) 목록에서 예측한 사업만
    category: str = ""           # 정해 둔 분류 (있으면 predict 대신)
    target: str = ""             # 예측 회차 ('2026 2차')
    amount: int | None = None    # 예산총액(원)
    irm_type: str = ""           # 사전협의 사업유형 ('SW개발, 운영유지보수')
    reason: str = ""             # 판정 근거 (통보일·완료일 등)

    @property
    def key(self) -> tuple:
        return org_key(self.org), name_key(self.name)

    @property
    def stage_label(self) -> str:
        return f"({self.round}차){self.stage}단계" if self.round else self.stage

    @property
    def needs_action(self) -> bool:
        return NO_OPINION not in self.note


@dataclass
class Edit:
    """사람이 고친 값 (회차가 바뀌어도 같은 사업이면 유지)."""
    types: str = ""              # '고도화' 또는 '운영유지보수+고도화'
    amount: int | None = None    # 원
    transfer: str = ""           # 'Y' / 'N' / ''(자동)


@dataclass
class Judgement:
    project: Project
    managed: bool
    types: list
    type_basis: str
    transfer: bool
    transfer_basis: str
    amount: int | None
    bands: list                  # [(유형, 금액구간)] 금액이 없으면 그 유형의 모든 구간
    required: list               # 대응 지표 코드
    maybe: list                  # 금액을 알아야 정해지는 지표
    category: str
    target: str = ""             # 예측한 회차 ('2026 2차' / '2027 1차' …)
    previous: str = ""           # 이전 회차에서의 단계 ('(1차)발주단계' …)
    flags: list = field(default_factory=list)
    edited: bool = False

    def mark(self, code: str) -> str:
        """지표 칸 표시: O(대응) / △(금액 확인 후) / -(해당 없음)."""
        return "O" if code in self.required else "△" if code in self.maybe else "-"


# ---------------------------------------------------------------------------
# 이름 맞추기
# ---------------------------------------------------------------------------

def _squash(text) -> str:
    return re.sub(r"[\s·ㆍ・.,\-_/()\[\]<>「」『』\"']", "", str(text or "")).upper()


def org_key(name) -> str:
    """기관명 비교용. 사업단은 '국립산림과학원(산림청)', 평가대상 목록은 '산림청 국립산림과학원'으로 쓴다. (재)·(주) 등은 뗀다."""
    text = re.sub(r"\((재|사|주)\)|㈜|\(주식회사\)|주식회사", "", text_or(name)).strip()
    m = re.match(r"^(.+)\(([^()]+)\)$", text)
    if m:
        text = f"{m.group(2)}{m.group(1)}"
    return _squash(text)


def text_or(value) -> str:
    return "" if value is None else str(value)


def name_key(name) -> str:
    return _squash(name)


# ---------------------------------------------------------------------------
# 유형·금액·지표
# ---------------------------------------------------------------------------

def classify(name: str, criteria: Criteria) -> tuple:
    """(유형 목록, 근거, 확인필요). 컨설팅이 걸리면 컨설팅만, 운영유지보수와 고도화가 같이 걸리면 둘 다(지표 합집합)."""
    squashed = _squash(name)
    hits = []
    for kind, words in criteria.type_words:
        word = next((w for w in words if _squash(w) and _squash(w) in squashed), None)
        if word:
            hits.append((kind, word))
    if not hits:
        return ["신규구축"], "키워드 없음 → 신규구축", ["사업유형 키워드 없음"]
    if hits[0][0] == "컨설팅":
        return ["컨설팅"], f"'{hits[0][1]}' → 컨설팅", []
    kinds = [k for k, _ in hits]
    basis = ", ".join(f"'{w}' → {k}" for k, w in hits)
    if kinds[0] == "운영유지보수" and len(kinds) > 1 and kinds[1] in ("고도화", "신규구축"):
        return kinds[:2], basis, [f"운영·유지관리와 {kinds[1]}가 함께 있음 (두 유형 지표를 모두 표시)"]
    return [kinds[0]], basis, []


def classify_irm(irm_type: str, name: str, criteria: Criteria) -> tuple:
    """IRM '사전협의 사업유형'(쉼표로 여러 개)으로 정하고, SW개발은 사업명으로 신규구축/고도화를 가른다.
    IRM 유형이 없으면 사업명 키워드(classify)."""
    tokens = [t.strip() for t in re.split(r",\s*(?![^()]*\))", irm_type or "") if t.strip()]
    if not tokens:
        return classify(name, criteria)
    if any(t.startswith("기획") for t in tokens):
        return ["컨설팅"], f"IRM '{irm_type}' → 컨설팅", []
    out, flags = [], []
    if any("운영" in t or "유지" in t for t in tokens):
        out.append("운영유지보수")
    if any("SW" in t.upper() or "개발" in t for t in tokens):
        by_name, _, _ = classify(name, criteria)
        out.append("고도화" if "고도화" in by_name else "신규구축")
        if "고도화" not in by_name:
            flags.append("SW개발: 사업명에 고도화 키워드가 없어 신규구축으로 봄")
    if any("DB" in t.upper() for t in tokens):
        out.append("DB구축")
    if not out:
        return classify(name, criteria)
    if len(out) > 1:
        flags.append(f"IRM 사업유형 {len(out)}개 (지표 합집합)")
    return out, f"IRM '{irm_type}'", flags


def order_round(day: date | None, criteria: Criteria):
    """검토결과 통보일이 발주 기간 안에 드는 회차."""
    if day is None:
        return None
    return next((r for r in criteria.rounds if r.order_start and r.order_end and r.order_start <= day <= r.order_end), None)


def eval_year(criteria: Criteria) -> int:
    """지금 평가연도: 기준 엑셀 '회차'에서 추정이 아닌 마지막 연도."""
    known = [r.year for r in criteria.rounds if "추정" not in r.note]
    return max(known) if known else criteria.rounds[0].year


def irm_projects(rows: list, criteria: Criteria) -> list:
    """IRM 사전협의(총괄) 목록 행([dict]) → [Project]. 기준1(발주)·기준2(완료)를 따로 판정하고, 둘 다 아니면 비대상 한 건.
    dict 키: org_type, org, code, name, start, end, done_end, applied, progress, result, review, reflect, db, check_target,
    irm_type, amount(원)."""
    year_now = eval_year(criteria)
    out = []
    for r in rows:
        base = dict(org_type=r["org_type"], org=r["org"], code=r["code"], name=r["name"], start=r["start"], end=r["end"],
                    applied=r["applied"], amount=r["amount"], irm_type=r["irm_type"])
        opinion = (r["db"] or 0) > 0 or r["check_target"] == "Y"
        free = "" if opinion else NO_OPINION + " (DB 분야 의견 없음)"
        made = []
        excluded = r["progress"] in EXCLUDED_PROGRESS or r["result"] in EXCLUDED_RESULT   # 검토결과를 못 받음 → 1·2 모두 아님
        # 기준1 사업발주: 검토결과를 통보받았는지 → 통보일이 기간 안인지
        if excluded:
            why_order = f"진행현황 '{r['progress']}'" if r["progress"] in EXCLUDED_PROGRESS else f"결과유형 '{r['result'] or '빈칸'}'"
        else:
            notice, kind = (r["reflect"], "반영계획 점검등록일") if r["result"] == "보완후협의" and r["reflect"] else                 (r["review"], "검토완료(예정)일")
            rnd = order_round(notice, criteria)
            why_order = f"{kind} {notice}"
            if rnd:
                cat = (C_FREE if not opinion else
                       f"{rnd.label} 발주단계 {C_EXPECT}" if rnd.year == year_now else C_NEXT_ORDER)
                made.append(Project(rnd.year, rnd.no, ORDER, note=free, category=cat, target=rnd.label,
                                    reason=why_order, **base))
            else:
                why_order += " (발주 기간 밖)"
        # 기준2 사업완료: 사업완료 종료일이 기간 안 + '21.3.12. 이후 신청 + DB 분야 의견
        if not excluded and opinion and r["applied"] and r["applied"] > LOWER_APPLY:
            done, planned = r["done_end"], r["done_end"] is None
            day = done or r["end"]
            rnd = done_round(day, criteria)
            if rnd:
                if rnd.year > year_now:
                    cat = C_NEXT_YEAR
                elif planned:
                    cat = f"{rnd.label} {C_PLANNED}"
                else:
                    cat = f"{rnd.label} 완료단계 {C_EXPECT}"
                why = f"사업완료 종료일 {done}" if done else f"사업완료 등록 전 · 계획 종료일 {r['end']}"
                made.append(Project(rnd.year, rnd.no, DONE, note="", category=cat, target=rnd.label, reason=why, **base))
        if not made:
            made.append(Project(year_now, 0, C_OUT, note=NO_OPINION, category=f"{C_OUT} ({why_order})", reason=why_order,
                                **base))
        out.extend(made)
    return out


def guess_transfer(name: str, criteria: Criteria) -> tuple:
    squashed = _squash(name)
    word = next((w for w in criteria.transfer_words if _squash(w) and _squash(w) in squashed), None)
    return (True, f"'{word}' → 이관 있음") if word else (False, "")


def parse_amount(text) -> int | None:
    """'3억', '1.5억원', '300,000,000', '300000천원', '12억 3,000만원' → 원. 못 읽으면 None."""
    if text is None or text == "":
        return None
    if isinstance(text, (int, float)):
        return int(text) if text > 0 else None
    t = re.sub(r"[\s,원]", "", str(text))
    if not t:
        return None
    total, rest = 0.0, t
    for unit, mul in (("억", 1e8), ("천만", 1e7), ("백만", 1e6), ("만", 1e4)):
        m = re.match(rf"^([\d.]+){unit}(.*)$", rest)
        if m:
            total += float(m.group(1)) * mul
            rest = m.group(2)
    m = re.match(r"^([\d.]+)(천)?$", rest)
    if m:
        total += float(m.group(1)) * (1000 if m.group(2) else 1)
    elif rest:
        return None
    return int(round(total)) if total > 0 else None


def won_text(amount: int | None) -> str:
    if not amount:
        return ""
    if amount >= 1e8:
        return f"{amount / 1e8:,.2f}".rstrip("0").rstrip(".") + "억"
    return f"{amount / 1e4:,.0f}만"


def bands_for(kind: str, amount: int | None, criteria: Criteria) -> list:
    rows = criteria.bands.get(kind, [])
    if amount is None or len(rows) <= 1:
        return [b[0] for b in rows]
    return [b for b, low, high, _ in rows if (low is None or amount >= low) and (high is None or amount < high)] or \
        [rows[-1][0]]


def items_for(types: list, amount: int | None, transfer: bool, criteria: Criteria) -> tuple:
    """(대응 지표, 금액 확인 후 지표). 금액이 없으면 모든 금액구간에 공통인 지표만 대응, 나머지는 △."""
    sure, maybe, picked = set(), set(), []
    for kind in types:
        bands = bands_for(kind, amount, criteria)
        picked += [(kind, b) for b in bands]
        sets = []
        for band in bands:
            row = criteria.matrix.get((kind, band), {})
            sets.append({c for c, v in row.items() if v == "O" or (v == "이관" and transfer)})
        if sets:
            common = set.intersection(*sets)
            sure |= common
            maybe |= set.union(*sets) - common
    maybe -= sure
    return [c for c in ITEMS if c in sure], [c for c in ITEMS if c in maybe], picked


# ---------------------------------------------------------------------------
# 다음 회차 예측
# ---------------------------------------------------------------------------

def done_round(end: date | None, criteria: Criteria) -> Round | None:
    """사업종료일이 완료 기간 안에 드는 회차."""
    if end is None:
        return None
    return next((r for r in criteria.rounds if r.done_start <= end <= r.done_end), None)


def predict(p: Project, criteria: Criteria, done_keys: set, same_round: set = frozenset()) -> tuple:
    """(분류, 예측 회차). done_keys: 지금까지 읽은 완료단계 사업 키. same_round: 같은 파일 완료 시트의 사업 키."""
    if p.stage == DONE:
        return f"{p.round}차 {C_DONE}", f"{p.year} {p.round}차"
    if not p.needs_action:
        return C_FREE, ""
    if p.key in same_round:
        return C_BOTH, f"{p.year} {p.round}차"
    if p.end is None:
        return C_NO_END, ""
    target = done_round(p.end, criteria)
    if target is None:
        first, last = criteria.rounds[0], criteria.rounds[-1]
        if p.end < first.done_start:
            return C_LATE, ""
        return (C_LATER if p.end > last.done_end else C_LATE), ""
    if (target.year, target.no) <= (p.year, p.round):
        return (C_MOVED if p.key in done_keys else C_LATE), target.label
    if p.key in done_keys:
        return C_MOVED, target.label
    if target.year == p.year:
        return f"{target.no}차 {C_MOVE}", target.label
    if target.year == p.year + 1:
        return C_NEXT_YEAR, target.label
    return C_LATER, target.label


def judge(projects: list, criteria: Criteria, managed: set, edits: dict | None = None,
          previous: dict | None = None, done_keys: set | None = None) -> list:
    """managed: org_key 집합(비면 모두 관리 기관으로 본다). edits: {사업 키: Edit}.
    previous: {사업 키: 이전 회차 단계 표시}. done_keys: 이전 회차까지 포함한 완료단계 사업 키."""
    edits, previous = edits or {}, previous or {}
    same_round = {p.key for p in projects if p.stage == DONE}
    done = set(done_keys or ()) | same_round
    out = []
    for p in projects:
        e = edits.get(p.key)
        types, basis, flags = classify_irm(p.irm_type, p.name, criteria) if p.irm_type else classify(p.name, criteria)
        if e and e.types:
            types = [t for t in e.types.split("+") if t in TYPES] or types
            basis, flags = "직접 입력", []
        transfer, t_basis = guess_transfer(p.name, criteria)
        if e and e.transfer in ("Y", "N"):
            transfer, t_basis = e.transfer == "Y", "직접 입력"
        amount = (e.amount if e else None) or p.amount
        required, maybe, picked = items_for(types, amount, transfer, criteria)
        category, target = (p.category, p.target) if p.category else predict(p, criteria, done, same_round)
        flags = list(flags) if p.needs_action else []   # 대응 불필요 사업은 확인할 것이 없다
        if p.needs_action and amount is None and maybe:
            flags.append("금액 없음 (발주단계 점검에 RFP를 넣으면 채워짐)")
        if category == C_LATE:
            flags.append("사업기간 연장 여부 확인")
        if C_PLANNED in category:
            flags.append("사업완료 등록 후 완료일로 다시 확인")
        out.append(Judgement(p, not managed or org_key(p.org) in managed, types, basis, transfer, t_basis, amount, picked,
                             required, maybe, category, target, previous.get(p.key, ""), flags, bool(e)))
    return out


def counts(judgements: list) -> dict:
    """요약 숫자 (관리 기관만)."""
    mine = [j for j in judgements if j.managed]
    return {
        "사업": len(mine),
        "기관": len({org_key(j.project.org) for j in mine}),
        "발주": sum(j.project.stage == ORDER for j in mine),
        "완료": sum(j.project.stage == DONE for j in mine),
        "대응 필요": sum(j.project.needs_action for j in mine),
        "전환 예상": sum(C_MOVE in j.category or C_PLANNED in j.category for j in mine),
        "내년 후보": sum(j.category in (C_NEXT_YEAR, C_NEXT_ORDER) for j in mine),
        "확인필요": sum(bool(j.flags) for j in mine if j.project.needs_action),
    }
