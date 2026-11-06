"""② 공통표준용어 유의어·금칙어 대응.

매칭 순서 (앞 단계에서 찾으면 멈춤):
  1. 정확 일치: 용어명 또는 영문약어명
  2. 정규화 일치: 공백·전각·특수문자를 뺀 용어명
  3. 용어 이음동의어 일치 → 대표 용어로 치환 권고
  4. 단어 단위 분해: 단어별 이음동의어·금칙어를 대표 단어로 바꾼 뒤 다시 검색
  5. 유사 후보: 자동 치환하지 않고 상위 후보만 제시
결과 구분: 표준 그대로 / 치환 권고 / 비표준 매핑 대상 / 대응 공통표준 없음
"""
from dataclasses import dataclass, field

from ..dictionary import CommonStandard, CommonTerm
from ..model import ChangeLog
from ..vba import narrow, s
from .cleanse import C, D

STANDARD, REPLACE, MAPPING, NONE = "표준 그대로", "치환 권고", "비표준 매핑 대상", "대응 공통표준 없음"
EXACT, NORMALIZED, TERM_SYNONYM, WORD_SWAP, SIMILAR = "정확 일치", "정규화 일치", "용어 이음동의어", "단어 치환", "유사 후보"


def norm(text) -> str:
    """비교용: 전각 → 반각, 한글·영문·숫자만, 대문자."""
    return "".join(ch for ch in narrow(s(text)).upper() if "가" <= ch <= "힣" or ch.isascii() and ch.isalnum())


def _abbr_tokens(abbr) -> set:
    return {p for p in s(abbr).upper().split("_") if p}


@dataclass
class MatchResult:
    kor: str
    eng: str
    rows: list = field(default_factory=list)       # RAW 행 번호 (시트 기준)
    tables: set = field(default_factory=set)
    category: str = NONE
    stage: str = ""
    term: CommonTerm | None = None
    candidates: list = field(default_factory=list)  # [(CommonTerm, 점수)]
    forbidden: list = field(default_factory=list)   # [(금칙어, 대표 단어)]
    rebuilt: str = ""                               # 단어 치환 후 이름
    confirmed: bool = False                         # 치환 적용 여부


class SynonymMatcher:
    def __init__(self, common: CommonStandard, top: int = 3, min_score: float = 0.5):
        self.top, self.min_score = top, min_score
        self.terms = common.terms
        self.by_name, self.by_abbr, self.by_norm = {}, {}, {}
        self.by_synonym = {}
        for t in self.terms:
            self.by_name.setdefault(t.name, t)
            self.by_abbr.setdefault(t.abbr.upper(), t)
            self.by_norm.setdefault(norm(t.name), t)
        for t in self.terms:
            for syn in t.synonyms:
                key = norm(syn)
                if key and key not in self.by_norm:
                    self.by_synonym.setdefault(key, []).append(t)
        # 단어 사전: 표준단어·이음동의어·금칙어 → (대표 단어, 금칙어 여부)
        self.words = {}
        self.word_abbr = {}
        for w in common.words:
            self.words.setdefault(norm(w.name), (w, False))
            self.word_abbr[norm(w.name)] = w.abbr
        for w in common.words:
            for syn in w.synonyms:
                self.words.setdefault(norm(syn), (w, False))
            for bad in w.forbidden:
                key = norm(bad)
                if key:
                    self.words[key] = (w, True)
        self.max_word = max((len(k) for k in self.words), default=1)
        # 유사 후보용 색인: 한글 단어(대표 단어로 바꾼 것)와 영문약어 조각
        self.term_tokens = [self.tokens(t.name) for t in self.terms]
        self.term_abbr_tokens = [_abbr_tokens(t.abbr) for t in self.terms]
        self.index, self.abbr_index = {}, {}
        for i, toks in enumerate(self.term_tokens):
            for tok in set(toks):
                self.index.setdefault(tok, []).append(i)
        for i, toks in enumerate(self.term_abbr_tokens):
            for tok in toks:
                self.abbr_index.setdefault(tok, []).append(i)

    # ---- 단어 분해 -------------------------------------------------------
    def segment(self, text: str) -> list:
        """사전 단어로 최대한 덮도록 나눈다: [(조각, CommonWord 또는 None, 금칙어 여부)]."""
        n = len(text)
        best = [None] * (n + 1)
        best[0] = (0, 0, [])
        for i in range(n):
            if best[i] is None:
                continue
            unknown, segs, path = best[i]
            for j in range(min(n, i + self.max_word), i, -1):
                piece = text[i:j]
                if piece in self.words:
                    word, bad = self.words[piece]
                    cand = (unknown, segs + 1, path + [(piece, word, bad)])
                    if best[j] is None or cand[:2] < best[j][:2]:
                        best[j] = cand
            cand = (unknown + 1, segs + 1, path + [(text[i], None, False)])
            if best[i + 1] is None or cand[:2] < best[i + 1][:2]:
                best[i + 1] = cand
        return best[n][2]

    def forbidden_in(self, name) -> list:
        return [(piece, w.name) for piece, w, bad in self.segment(norm(name)) if bad]

    def tokens(self, name) -> list:
        """단어 단위로 나누고 이음동의어·금칙어는 대표 단어로. 사전에 없는 글자는 이어 붙여 한 조각으로."""
        out, unknown = [], ""
        for piece, w, _ in self.segment(norm(name)):
            if w is None:
                unknown += piece
                continue
            if unknown:
                out.append(unknown)
                unknown = ""
            out.append(norm(w.name))
        if unknown:
            out.append(unknown)
        return out

    # ---- 매칭 -----------------------------------------------------------
    def lookup(self, name: str):
        key = norm(name)
        if key in self.by_norm:
            return self.by_norm[key], NORMALIZED
        if key in self.by_synonym and len(self.by_synonym[key]) == 1:
            return self.by_synonym[key][0], TERM_SYNONYM
        return None, ""

    def similar(self, kor: str, eng: str = "") -> list:
        """같은 단어를 얼마나 공유하는지로 점수를 매긴다. 끝 단어(명·코드·번호 등)가 같으면 가산점."""
        q = self.tokens(kor)
        q_abbr = _abbr_tokens(eng)
        ids = set()
        for tok in set(q):
            ids.update(self.index.get(tok, ()))
        for tok in q_abbr:
            ids.update(self.abbr_index.get(tok, ()))
        q_len, q_abbr_len = sum(map(len, q)), sum(map(len, q_abbr))
        scored = []
        for i in ids:
            t, t_abbr = self.term_tokens[i], self.term_abbr_tokens[i]
            score = 0.0
            if q and t:
                common = set(q) & set(t)
                shared = sum(len(tok) for tok in common)
                score = 2 * shared / (q_len + sum(map(len, t)))
                if shared and q[-1] == t[-1]:
                    score += 0.1
                if common == {q[-1]}:
                    score *= 0.7   # 끝 단어(명·정보 등)만 같은 후보는 약하게

            if q_abbr and t_abbr:
                shared = sum(len(tok) for tok in q_abbr & t_abbr)
                score = max(score, 0.9 * 2 * shared / (q_abbr_len + sum(map(len, t_abbr))))
            scored.append((self.terms[i], min(score, 1.0)))
        scored.sort(key=lambda x: (-x[1], len(x[0].name)))
        return [(t, round(sc, 2)) for t, sc in scored[: self.top] if sc >= self.min_score]

    def match(self, kor: str, eng: str) -> MatchResult:
        r = MatchResult(kor, eng)
        r.forbidden = self.forbidden_in(kor)
        if kor in self.by_name or eng.upper() in self.by_abbr:
            r.category, r.stage = STANDARD, EXACT
            r.term = self.by_abbr.get(eng.upper()) or self.by_name.get(kor)
            return r
        key = norm(kor)
        if key in self.by_norm:
            r.category, r.stage, r.term = REPLACE, NORMALIZED, self.by_norm[key]
            return r
        if key in self.by_synonym:
            found = self.by_synonym[key]
            if len(found) == 1:
                r.category, r.stage, r.term = REPLACE, TERM_SYNONYM, found[0]
            else:
                r.category, r.stage, r.candidates = MAPPING, TERM_SYNONYM, [(t, 1.0) for t in found]
            return r
        pieces = self.segment(key)
        if any(w is not None and norm(w.name) != piece for piece, w, _ in pieces):
            r.rebuilt = "".join(w.name if w else piece for piece, w, _ in pieces)
            term, _ = self.lookup(r.rebuilt)
            if term is None and all(w for _, w, _ in pieces):
                term = self.by_abbr.get("_".join(w.abbr for _, w, _ in pieces).upper())
            if term is not None:
                r.category, r.stage, r.term = REPLACE, WORD_SWAP, term
                return r
        r.candidates = self.similar(kor, eng)
        if r.candidates:
            r.category, r.stage = MAPPING, SIMILAR
        return r


def match_raw(raw: list, matcher: SynonymMatcher) -> list:
    """RAW의 (한글컬럼명, 영문컬럼명) 쌍마다 한 번씩 매칭한다."""
    results = {}
    for i, row in enumerate(raw):
        kor, eng = s(row[C]), s(row[D])
        if kor == "" and eng == "":
            continue
        key = (kor, eng)
        if key not in results:
            results[key] = matcher.match(kor, eng)
        results[key].rows.append(i + 2)
        results[key].tables.add(s(row[1]))
    return list(results.values())


def apply_matches(raw: list, results: list, decisions: dict | None, auto_apply: bool, matcher: SynonymMatcher,
                  log: ChangeLog) -> None:
    """확정된 치환을 RAW에 반영한다. 이어지는 공통표준 매핑이 타입·길이를 채운다.

    decisions: {(한글, 영문): (확정 여부, 표준용어명)} — 검토 파일에서 읽은 값. 없으면 auto_apply 기준.
    """
    by_name = {t.name: t for t in matcher.terms}
    for r in results:
        key = (r.kor, r.eng)
        if decisions is not None and key in decisions:
            ok, chosen = decisions[key]
            term = by_name.get(chosen) if chosen else r.term
            if chosen and term is None:
                log.add("② 표준 매핑", "RAW", ",".join(map(str, r.rows[:5])), "경고", f"{r.kor}/{r.eng}", None, chosen,
                        "검토 파일의 표준용어명을 공통표준에서 찾지 못함")
                continue
        else:
            ok, term = auto_apply and r.category == REPLACE, r.term
        if not ok or term is None or (term.name == r.kor and term.abbr.upper() == r.eng.upper()):
            continue
        r.confirmed, r.term = True, term
        for row_no in r.rows:
            row = raw[row_no - 2]
            log.changed("② 표준 매핑", "RAW", row_no, "한글 컬럼명", row[C], term.name, f"{r.stage} → {term.name}")
            log.changed("② 표준 매핑", "RAW", row_no, "영문 컬럼명", row[D], term.abbr, f"{r.stage} → {term.abbr}")
            row[C], row[D] = term.name, term.abbr
