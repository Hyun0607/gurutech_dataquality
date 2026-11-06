"""① 도메인 사전 고도화: 용어가 가리키는 도메인이 반드시 존재하도록 보장. 같은 용어명은 번호로 나눔."""
import re

from ..model import DOMAIN_COLS, ChangeLog, blank_row, col
from ..vba import norm_key, s, val
from .cleanse import C, D, E, F, G
from .naming import DomainNamer


def number_duplicate_terms(terms: list, common_eng: set, log: ChangeLog) -> list:
    """한 용어명에 영문약어명이 여럿 남으면 용어명 뒤에 번호를 붙여 따로 만든다.

    매크로 NumberSuffix가 하려던 일 (매크로는 조건식 때문에 실제로는 안 바뀜). 안 붙이면 DB표준 적용이 컬럼들을
    마지막 영문 하나로 바꾸고, 같은 컬럼이 되어 정의서에서 지워진다 (예: OPT1_NAME~OPT15_NAME 여분필드명지정 → OPT9_NAME 하나).
    번호는 영문약어명의 숫자를 쓰고 (OPT10_NAME → 여분필드명지정10), 겹치거나 없으면 01, 02 … 순서.
    공통표준 영문약어명이거나 용어명이 영문뿐이면 매크로처럼 두지 않고 그대로 둔다.
    """
    groups = {}
    for i, t in enumerate(terms):
        kor, eng = s(t[col("A")]), s(t[col("C")]).upper()
        if kor and eng and not re.fullmatch(r"[A-Za-z]+", kor) and eng not in common_eng:
            groups.setdefault(norm_key(kor), []).append(i)
    used = {norm_key(s(t[col("A")])) for t in terms}
    for kor_key, rows in groups.items():
        engs = {s(terms[i][col("C")]).upper() for i in rows}
        if len(engs) < 2:
            continue
        digits = {e: "".join(re.findall(r"\d+", e)) for e in engs}
        by_digits = all(digits.values()) and len(set(digits.values())) == len(engs)
        seq, names = 0, {}
        for e in sorted(engs, key=lambda x: (len(x), x)):
            base = s(terms[rows[0]][col("A")])
            if by_digits and norm_key(base + digits[e]) not in used:
                names[e] = base + digits[e]
            else:
                while True:
                    seq += 1
                    if norm_key(f"{base}{seq:02d}") not in used:
                        break
                names[e] = f"{base}{seq:02d}"
            used.add(norm_key(names[e]))
        for i in rows:
            t = terms[i]
            new = names[s(t[col("C")]).upper()]
            log.changed("① 용어명 번호", "2_용어", i + 2, "용어명", t[col("A")], new,
                        f"같은 용어명에 영문약어명 {len(engs)}개 ({s(t[col('C')])})")
            t[col("A")] = new
    return terms


def drop_unused_domains(terms: list, domains: list, log: ChangeLog) -> list:
    """어떤 용어도 쓰지 않는 도메인을 뺀다. 용어 중복 처리에서 그 도메인의 용어가 모두 다른 도메인으로 합쳐지면
    도메인만 남아, 제출하면 쓰이지도 않는 도메인이 완전성 오류(예: 길이 누락 문자값VC0)를 낸다."""
    used = {s(t[col("E")]).upper() for t in terms if s(t[col("E")])}
    out = []
    for i, d in enumerate(domains):
        name = s(d[col("C")])
        if name and name.upper() not in used:
            log.add("① 미사용 도메인", "1_도메인", i + 2, "삭제", name, None, None, "이 도메인을 쓰는 용어 없음")
            continue
        out.append(d)
    return out


def ensure_term_domains(raw: list, terms: list, domains: list, namer: DomainNamer, reg_date, log: ChangeLog) -> list:
    """용어의 도메인이 1_도메인에 없으면 같은 영문컬럼명 RAW 값으로 도메인을 추가한다."""
    existing = {s(d[col("C")]).upper() for d in domains}
    first_raw = {}
    for r in raw:
        first_raw.setdefault(s(r[D]), r)
    added = []
    for t in terms:
        name = s(t[col("E")])
        if name == "" or name.upper() in existing:
            continue
        r = first_raw.get(s(t[col("C")]))
        if r is None:
            log.add("① 도메인 보장", "1_도메인", "-", "경고", name, None, None, f"용어 {s(t[col('A')])}의 RAW 행 없음 → 수동 확인")
            continue
        d = blank_row(DOMAIN_COLS)
        namer.counting = False   # 도메인 생성 때 이미 집계한 RAW 행
        try:
            d[col("B")] = namer.classify(r[D], r[C])
        finally:
            namer.counting = True
        d[col("C")] = name
        d[col("E")] = "VARCHAR" if s(r[E]) == "" else r[E]
        d[col("F")] = 0 if s(r[F]) == "" or val(r[F]) == 0 else r[F]
        d[col("G")] = r[G]
        d[col("L")] = reg_date
        existing.add(name.upper())
        added.append(d)
        log.add("① 도메인 보장", "1_도메인", len(domains) + len(added) + 1, "추가", name, None, f"{d[col('E')]}/{d[col('F')]}",
                f"용어 {s(t[col('A')])}가 가리키는 도메인 없음")
    return domains + added
