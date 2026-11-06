"""예방적 품질관리 문서 점검: RFP(발주단계)와 완료·감리보고서(완료단계)에서 지표별 반영 여부를 찾는다.

문서 글자는 workbook/documents.read_document 의 [Para]로 받는다. 판정은 사람이 확인할 수 있게 근거(위치·문장)를 같이 낸다.
- 발주: RFP의 요구사항 블록(고유번호 → 요구사항 명칭) 가운데 DAR(데이터 요구사항) 이름으로 지표를 정한다.
  DAR이 아닌 요구사항이나 본문에만 있으면 '확인필요', 없으면 '미반영' + 매뉴얼 3.2.2 문안.
- 완료: 보고서 본문에서 지표의 산출물·활동 단어를 찾는다. 없으면 '미확인' + 제출할 산출물 안내.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from .preventive import ITEMS, Criteria, Requirement, bands_for, name_key, parse_amount

DONE_OK, DONE_CHECK, DONE_MISSING = "반영", "확인필요", "미반영"
FOUND, NOT_FOUND = "확인됨", "미확인"
NEED, MAYBE = "대응", "금액 확인 후"

RID = re.compile(r"^([A-Z]{2,5})\s*-\s*(\d{2,4})$")
AMOUNT_WORDS = r"(총사업비|사업비|사업예산|소요예산|추정가격|기초금액|사업금액|예산액|계약금액)"
AMOUNT_NUMBER = r"\s*(금)?\s*([\d,]+(?:\.\d+)?)\s*(억원|억|백만원|천원|원)"
AMOUNT = re.compile(AMOUNT_WORDS + r"\s*[:：]?" + AMOUNT_NUMBER)
AMOUNT_STRICT = re.compile(AMOUNT_WORDS + r"\s*[:：]" + AMOUNT_NUMBER)   # 보고서: '사업비 : …' 꼴만 (권고 문장 제외)


@dataclass
class DocRequirement:
    rid: str
    name: str
    where: str
    index: int
    codes: list = field(default_factory=list)

    @property
    def is_data(self) -> bool:
        return self.rid.startswith("DAR")


@dataclass
class ItemResult:
    code: str
    name: str
    need: str                    # 대응 / 금액 확인 후
    status: str
    evidence: str = ""           # 근거 (요구사항 번호·이름 또는 문장)
    where: str = ""
    comment: str = ""
    suggestion: Requirement | None = None


@dataclass
class CriterionResult:
    """완료단계 세부 기준 하나의 판정: Y(확인) / N(없음) / -(해당 없음)."""
    code: str
    item: str
    text: str
    status: str
    evidence: str = ""
    where: str = ""
    opinion: str = ""            # N일 때 검토의견
    needed: str = ""             # N일 때 필요 산출물
    edited: bool = False         # 사람이 고침
    covered_by: str = ""         # 같은 지표의 다른 기준이 Y라서 '-' (지표는 (1)·(2) 중 하나만 충족하면 된다)


@dataclass
class DocCheck:
    kind: str                    # 발주 / 완료
    file: str
    paragraphs: int
    amount: int | None
    amount_where: str
    amount_text: str
    requirements: list
    results: list
    criteria: list = field(default_factory=list)   # 완료단계 [CriterionResult]

    def ratio(self) -> float | None:
        """진단결과반영비율 = Y ÷ (Y + N). 적용 기준이 없으면 None."""
        marks = [c.status for c in self.criteria if c.status in ("Y", "N")]
        return marks.count("Y") / len(marks) if marks else None


def _squash(text: str) -> str:
    return re.sub(r"\s", "", text)


def _hits(words: list, text: str) -> bool:
    sq = _squash(text)
    return any(all(p and p in sq for p in w.split("+")) for w in words if w)


def item_codes(name: str, criteria: Criteria) -> list:
    """요구사항 이름 → 지표 코드 (여러 개일 수 있다)."""
    out = []
    for code in ITEMS:
        item = criteria.items.get(code)
        if not item or not item.name_words:
            continue
        if item.name_except and _hits(item.name_except, name):
            continue
        if _hits(item.name_words, name):
            out.append(code)
    return out


def find_requirements(paras: list, criteria: Criteria) -> list:
    """'고유번호' 다음의 ID(DAR-001 등)와 '요구사항 명칭' 다음 칸을 짝짓는다. 같은 ID가 다시 나오면(총괄표·본문) 이름이 있는 첫 블록만."""
    out, seen = [], set()
    texts = [p.text for p in paras]
    for i, t in enumerate(texts):
        m = RID.match(t)
        if not m or not any("고유번호" in x for x in texts[max(0, i - 3):i]):
            continue
        rid = f"{m.group(1)}-{m.group(2)}"
        j = next((k for k in range(i + 1, min(i + 5, len(texts))) if re.search(r"요구사항\s*(명칭|명)$", texts[k])), None)
        if j is None or j + 1 >= len(texts) or rid in seen:
            continue
        seen.add(rid)
        name = texts[j + 1]
        out.append(DocRequirement(rid, name, paras[i].where, i, item_codes(name, criteria)))
    return out


NAME_LINE = re.compile(r"^\s*(?:\d+\.|□|ㅇ|○|-)?\s*(?:사\s*업\s*명|과\s*업\s*명|용\s*역\s*명)\s*[:：]\s*(.+)$")
NAME_LABEL = re.compile(r"^\s*(사\s*업\s*명|과\s*업\s*명|용\s*역\s*명)\s*$")


AUDIT_NAME = re.compile(r"수행(?:하는|한|중인)\s*[‘“'\"「『]\s*(.+?)\s*[’”'\"」』]\s*(사업|용역)?\s*에\s*대한")
AUDIT_TITLE = re.compile(r"^(.{4,}?)\s*감리\s*용역\s*$")


def _audit_name(paras: list) -> str:
    """감리보고서: 인사말 '…가 수행하는 ‘용인 스마트관광도시 조성’사업에 대한 종료단계 감리' 속 사업명,
    없으면 표지의 '… 감리 용역' 줄에서 '감리 용역'을 뗀 것. 감리보고서가 아니면 ''."""
    head = [p for p in paras if (p.page or 1) <= 4][:200]
    if not any("감리" in p.text for p in head):
        return ""
    text = " ".join(p.text.strip() for p in head)
    m = AUDIT_NAME.search(text)
    if m and len(m.group(1)) > 3:
        name = m.group(1).strip()
        return name + m.group(2) if m.group(2) and not name.endswith(m.group(2)) else name
    for p in head:
        m = AUDIT_TITLE.match(p.text.strip())
        if m:
            return m.group(1).strip(" 「」『』\"'‘’“”")
    return ""


def find_project_name(paras: list, limit: int = 400) -> str:
    """문서 앞쪽의 사업명: 감리보고서는 감리 대상 사업명, 그 밖에는 '1. 사업명 : …' 줄 또는 표지의 '사 업 명' 칸 다음 칸.
    없으면 ''."""
    audit = _audit_name(paras)
    if audit:
        return audit
    head = paras[:limit]
    for p in head:
        m = NAME_LINE.match(p.text)
        if m and len(m.group(1).strip()) > 3:
            return m.group(1).strip(" 「」『』\"'")
    for i, p in enumerate(head[:-1]):
        if NAME_LABEL.match(p.text) and len(head[i + 1].text) > 3:
            return head[i + 1].text.strip(" 「」『』\"'")
    return ""


def _years(text: str) -> set:
    return set(re.findall(r"20\d\d", text))


def match_project(texts: list, names: list, least: float = 0.6) -> int | None:
    """문서 사업명·파일 이름(texts) 중 하나와 가장 비슷한 사업명의 번호. 비슷한 것이 없으면 None.
    한쪽이 다른 쪽을 품으면 바로 맞는 것으로 본다 ('… 사업' 같은 꼬리, 파일 이름 앞 번호 때문에)."""
    best, best_score = None, least
    for text in filter(None, (name_key(t) for t in texts)):
        for i, name in enumerate(name_key(n) for n in names):
            if not name or _years(text) and _years(name) and not _years(text) & _years(name):
                continue   # '2025년 …'과 '2026년 …'처럼 연도가 다르면 다른 사업
            score = SequenceMatcher(None, text, name).ratio()
            if len(name) >= 6 and (name in text or text in name):
                score = max(score, 0.9 + 0.1 * min(len(name), len(text)) / max(len(name), len(text)))
            if score > best_score:
                best, best_score = i, score
    return best


def find_amount(paras: list, strict: bool = False) -> tuple:
    """(금액, 위치, 문장). '사 업 비 : 금308,100,000원'처럼 띄어 쓴 것도 찾는다. 앞쪽(사업개요)에 나온 것을 쓴다.
    strict(완료·감리보고서): 앞 10쪽 안의 '사업비 : …' 꼴만 ('사업비 3억↑ 분리 발주' 같은 권고 문장을 금액으로 읽지 않게)."""
    for p in paras:
        if strict and (p.page or 0) > 10:
            break
        sq = _squash(p.text)
        m = (AMOUNT_STRICT if strict else AMOUNT).search(sq)
        if not m:
            continue
        number, unit = m.group(3), m.group(4)
        amount = parse_amount(number.replace(",", "") + {"억원": "억", "억": "억", "백만원": "", "천원": "천", "원": ""}[unit])
        if amount and unit == "백만원":
            amount *= 1_000_000
        if amount and amount >= 1_000_000:
            return amount, p.where, p.text
    return None, "", ""


def suggestion(code: str, types: list, amount: int | None, criteria: Criteria) -> Requirement | None:
    """이 사업 유형·금액에 맞는 매뉴얼 문안. 금액을 모르면 그 유형의 가장 큰 구간, 유형에 없는 지표면 다른 유형에서."""
    for kind in types:
        bands = bands_for(kind, amount, criteria)
        for band in (bands[:1] if amount is not None else list(reversed(bands))):
            hit = next((r for r in criteria.requirements if r.kind == kind and r.band == band and r.code == code), None)
            if hit:
                return hit
        hit = next((r for r in reversed(criteria.requirements) if r.kind == kind and r.code == code), None)
        if hit:
            return hit
    return next((r for r in reversed(criteria.requirements) if r.code == code), None)


def _body_hit(paras: list, words: list) -> tuple:
    """본문 문장 중 지표 단어가 있고 데이터 이야기인 것 ('웹표준화' 같은 다른 표준은 빼려고 '데이터'·'DB'가 같이 있어야 한다)."""
    for p in paras:
        if _hits(words, p.text) and re.search(r"데이터|DB", p.text):
            return p.where, p.text
    return "", ""


def check_order(paras: list, file: str, types: list, required: list, maybe: list, criteria: Criteria,
                amount: int | None = None) -> DocCheck:
    """발주단계: RFP에 지표별 데이터 요구사항이 있는지."""
    found_amount, where, text = find_amount(paras)
    reqs = find_requirements(paras, criteria)
    results = []
    for code in required + maybe:
        item = criteria.items[code]
        need = NEED if code in required else MAYBE
        data = [r for r in reqs if code in r.codes and r.is_data]
        other = [r for r in reqs if code in r.codes and not r.is_data]
        if data:
            r = data[0]
            results.append(ItemResult(code, item.name, need, DONE_OK, f"{r.rid} {r.name}", r.where))
            continue
        hint = suggestion(code, types, amount or found_amount, criteria)
        add = f" 매뉴얼 3.2.2 '{hint.name}' 문안을 데이터 요구사항(DAR)으로 추가하세요." if hint else ""
        if other:
            r = other[0]
            results.append(ItemResult(code, item.name, need, DONE_CHECK, f"{r.rid} {r.name}", r.where,
                                      f"'{r.rid} {r.name}'에 관련 내용이 있으나 데이터 요구사항(DAR)이 아닙니다.{add}", hint))
            continue
        at, sentence = _body_hit(paras, item.name_words)
        if at:
            results.append(ItemResult(code, item.name, need, DONE_CHECK, sentence[:120], at,
                                      f"본문({at})에 언급은 있으나 요구사항으로 정리되어 있지 않습니다.{add}", hint))
        else:
            results.append(ItemResult(code, item.name, need, DONE_MISSING, "", "",
                                      f"RFP에 '{item.name}' 관련 요구사항이 없습니다.{add}", hint))
    return DocCheck("발주", file, len(paras), found_amount, where, text, reqs, results)


TOC = re.compile(r"\.{5,}|…{2,}|·{5,}|-{5,}\s*\d+$")   # 목차 줄


def _report_hits(paras: list, item) -> list:
    """보고서에서 지표 수행 내역으로 볼 줄: 지표 고유 표현(요구사항 명칭 단어)이 데이터 문맥에서 나온 줄. 목차는 뺀다."""
    return [p for p in paras if _hits(item.name_words, p.text) and re.search(r"데이터|DB|표준|메타", p.text)
            and not TOC.search(p.text) and not (item.name_except and _hits(item.name_except, p.text))]


def _sample(path) -> bool:
    """예시 양식을 그대로 낸 파일: 이름에 '예시'가 있거나 'DB명_'·'기관명_'처럼 자리 표시가 남은 것."""
    stem = Path(path).stem
    return "예시" in stem or bool(re.match(r"(DB명|기관명|시스템명)[_ ]", stem))


def _pages(paras: list) -> str:
    pages = list(dict.fromkeys(p.where for p in paras))
    return ", ".join(pages[:6]) + (" 외" if len(pages) > 6 else "")


NOT_DATA = re.compile(r"웹\s*표준|웹\s*접근성|웹\s*호환성|표준\s*프레임\s*워크|전자정부\s*표준")   # 데이터 표준이 아닌 '표준'


def _detail_hits(paras: list, d) -> list:
    """세부 기준 단어가 데이터 문맥('데이터'·'DB'·'메타')에서 나온 줄. 목차와 웹 표준 등은 뺀다."""
    return [p for p in paras if _hits(d.words, p.text) and re.search(r"데이터|DB|메타", p.text)
            and not TOC.search(p.text) and not NOT_DATA.search(p.text)]


def judge_details(docs: list, files: list, codes: list, types: list, criteria: Criteria) -> list:
    """세부 기준 18개 판정. codes(대응 지표)에 없는 지표와 생략 유형은 '-', 보고서 줄이나 산출물 파일 이름이 있으면 Y, 없으면 N."""
    out = []
    for d in criteria.details:
        if d.item not in codes or "전체" in d.skip_types or any(t in d.skip_types for t in types):
            out.append(CriterionResult(d.code, d.item, d.text, "-"))
            continue
        found = next(((name, hits) for name, paras in docs if (hits := _detail_hits(paras, d))), None)
        named = [f for f in files if _hits(d.file_words, Path(f).stem) and "증빙기준" not in Path(f).stem
                 and (d.item == "4.2" or "메타데이터" not in Path(f).stem)]   # 메타데이터 관리항목 파일은 4.2에만
        real = [f for f in named if not _sample(f)]
        if found:
            name, hits = found
            where = _pages(hits) if len(docs) == 1 else f"{name} {_pages(hits)}"
            out.append(CriterionResult(d.code, d.item, d.text, "Y", hits[0].text[:120], where))
        elif real:
            out.append(CriterionResult(d.code, d.item, d.text, "Y", "산출물 파일: " + ", ".join(Path(f).name for f in real[:3]),
                                       "제출 파일"))
        else:
            note = " (예시 양식 파일만 있음)" if named else ""
            out.append(CriterionResult(d.code, d.item, d.text, "N", opinion=d.opinion + note, needed=d.needed))
    return _one_is_enough(out)


def _one_is_enough(results: list) -> list:
    """지표마다 (1)·(2) 중 하나만 충족하면 된다: 같은 지표에 Y가 있으면 나머지 N은 '-'(그 Y로 충족)."""
    for r in results:
        ok = next((x for x in results if x.item == r.item and x.status == "Y"), None)
        if r.status == "N" and ok:
            r.status, r.opinion, r.needed, r.covered_by = "-", "", "", ok.code
    return results


def item_results(details: list, required: list, maybe: list, criteria: Criteria) -> list:
    """세부 기준 → 지표 9개: (1)·(2) 중 하나라도 Y면 확인됨 (나머지는 judge_details가 이미 '-'), 남은 N이 있으면 미확인."""
    results = []
    for code in required + maybe:
        item = criteria.items[code]
        need = NEED if code in required else MAYBE
        mine = [c for c in details if c.item == code and c.status != "-"]
        bad = [c for c in mine if c.status == "N"]
        if mine and not bad:
            first = mine[0]
            results.append(ItemResult(code, item.name, need, FOUND, first.evidence, first.where))
        else:
            comment = "\n".join(f"{c.code} {c.opinion}" for c in bad) or f"'{item.name}' 수행 내역을 찾지 못했습니다."
            results.append(ItemResult(code, item.name, need, NOT_FOUND, "", "",
                                      f"{comment}\n아래 중 하나를 IRM에 등록하세요.\n{item.evidence}"))
    return results


def check_done(docs: list, files: list, required: list, maybe: list, criteria: Criteria, types: list | None = None) -> DocCheck:
    """완료단계: 보고서(docs = [(파일 이름, [Para])])에 지표별 수행 내역이 있는지, 또는 제출 파일(files = 파일 이름) 중
    지표 산출물로 보이는 것이 있는지. 둘 다 없으면 '미확인'과 제출할 산출물 안내.
    기준 엑셀에 '세부기준'이 있으면 18개 기준 단위로 Y/N/-를 매기고 지표 결과는 거기서 모은다."""
    if criteria.details:
        details = judge_details(docs, files, required + maybe, types or [], criteria)
        names = ", ".join([n for n, _ in docs] + [Path(f).name for f in files][:5])
        return DocCheck("완료", names, sum(len(p) for _, p in docs), None, "", "", [],
                        item_results(details, required, maybe, criteria), details)
    results = []
    for code in required + maybe:
        item = criteria.items[code]
        need = NEED if code in required else MAYBE
        found = next(((name, hits) for name, paras in docs if (hits := _report_hits(paras, item))), None)
        named = [f for f in files if _hits(item.file_words, Path(f).stem) and "증빙기준" not in Path(f).stem]
        real = [f for f in named if not _sample(f)]
        if found:
            name, hits = found
            where = _pages(hits) if len(docs) == 1 else f"{name} {_pages(hits)}"   # 보고서가 하나면 쪽 번호만
            results.append(ItemResult(code, item.name, need, FOUND, hits[0].text[:120], where))
        elif named:
            shown = "산출물 파일: " + ", ".join(Path(f).name for f in (real or named)[:3])
            results.append(ItemResult(code, item.name, need, FOUND, shown, "제출 파일") if real else
                           ItemResult(code, item.name, need, DONE_CHECK, shown, "제출 파일",
                                      "예시 양식 파일만 있습니다. 이 사업 내용으로 작성한 산출물인지 확인하세요."))
        else:
            results.append(ItemResult(code, item.name, need, NOT_FOUND, "", "",
                                      f"'{item.name}' 수행 내역을 보고서·산출물에서 찾지 못했습니다. 아래 중 하나를 IRM에 등록하세요.\n"
                                      f"{item.evidence}"))
    names = ", ".join([n for n, _ in docs] + [Path(f).name for f in files][:5])
    return DocCheck("완료", names, sum(len(p) for _, p in docs), None, "", "", [], results)
