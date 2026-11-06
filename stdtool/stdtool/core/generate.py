"""5) 도메인·용어·단어 생성."""
from ..model import DOMAIN_COLS, TERM_COLS, WORD_COLS, ChangeLog, blank_row, col
from ..vba import cstr, last_row, s, trim, ucase, val
from .cleanse import C, D, E, F, G
from .naming import DomainNamer


def make_domains(raw: list, namer: DomainNamer, reg_date, log: ChangeLog) -> list:
    """도메인_생성: RAW 행마다 도메인을 만들고 (도메인명, 타입, 길이) 중복을 제거한다."""
    rows = []
    for row in raw[: last_row(raw, D)]:
        domain_class = namer.classify(row[D], row[C])
        raw_type, raw_len = row[E], row[F]
        if s(raw_len) == "" or val(raw_len) == 0:
            raw_len = 0
        out = blank_row(DOMAIN_COLS)
        out[col("B")] = domain_class
        out[col("E")] = "VARCHAR" if s(raw_type) == "" else raw_type
        out[col("F")] = raw_len
        out[col("G")] = row[G] if namer.enhanced else None
        out[col("C")] = namer.name(domain_class, raw_type, raw_len, row[G] if namer.enhanced else None)
        rows.append(out)

    seen, unique = set(), []
    for i, out in enumerate(rows):
        key = (cstr(out[col("C")]).upper(), cstr(out[col("E")]).upper(), cstr(out[col("F")]))
        if key in seen:
            continue
        seen.add(key)
        out[col("L")] = reg_date
        unique.append(out)
    log.add("도메인 생성", "1_도메인", "-", "정보", "", len(rows), len(unique), "(도메인명, 타입, 길이) 중복 제거")
    return unique


def make_terms(raw: list, namer: DomainNamer, reg_date) -> list:
    """용어_생성: RAW 행마다 용어 하나 (중복은 용어 중복 처리에서 정리)."""
    rows = []
    namer.counting = False
    try:
        for row in raw[: last_row(raw, C)]:
            domain_class = namer.classify(row[D], row[C])
            out = blank_row(TERM_COLS)
            out[col("A")] = row[C]
            out[col("C")] = row[D]
            out[col("I")] = reg_date
            out[col("E")] = namer.name(domain_class, row[E], row[F], row[G] if namer.enhanced else None)
            rows.append(out)
    finally:
        namer.counting = True
    return rows


def make_words(terms: list, reg_date, log: ChangeLog) -> list:
    """단어_생성: 용어 영문약어명을 '_'로 나눠 단어를 만들고 영문약어별로 하나만 남긴다."""
    TA, TC = col("A"), col("C")
    rows = []
    for term in terms[: last_row(terms, TA)]:
        kor, eng = s(term[TA]), s(term[TC])
        if kor != "" and eng != "":
            for part in eng.split("_"):
                single = ucase(trim(part))
                if len(single) > 0:
                    out = blank_row(WORD_COLS)
                    out[col("A")] = kor
                    out[col("B")] = single
                    out[col("C")] = single
                    out[col("E")] = "N"
                    out[col("I")] = reg_date
                    rows.append(out)
    return _dedupe_words(rows, log)


def fill_words_from_common(words: list, common_words: list, log: ChangeLog) -> None:
    """② 단어 영문약어가 공통표준단어에 있으면 한글명·영문명·형식단어 여부·도메인 분류명을 공통표준으로 채운다."""
    by_abbr = {w.abbr.upper(): w for w in common_words}
    for i, row in enumerate(words):
        w = by_abbr.get(s(row[col("B")]).upper())
        if w is None:
            continue
        log.changed("② 공통표준단어", "3_단어", i + 2, "표준단어명", row[col("A")], w.name, "공통표준단어 영문약어 일치")
        row[col("A")] = w.name
        row[col("C")] = w.eng_name or row[col("C")]
        row[col("E")] = w.is_format or row[col("E")]
        row[col("F")] = w.domain_class or None


def _dedupe_words(rows: list, log: ChangeLog) -> list:
    """단어_중복_최종정제: 영문약어별 최빈 한글명으로 바꾸고, 아래쪽 행 하나만 남긴다."""
    WA, WB = col("A"), col("B")
    rows = rows[: last_row(rows, WB)]
    counts = {}
    for r in rows:
        key = (s(r[WB]), s(r[WA]))
        counts[key] = counts.get(key, 0) + 1
    best = {}
    for (b, a), n in counts.items():
        if b not in best or n > counts[(b, best[b])]:
            best[b] = a

    kept, flagged = [], set()
    for index in range(len(rows) - 1, -1, -1):
        r = rows[index]
        b, a = s(r[WB]), s(r[WA])
        if b in best:
            r[WA] = best[b]
            a = best[b]
        if a == best.get(b) and b not in flagged:
            flagged.add(b)
            kept.append(r)
        else:
            log.add("단어 생성", "3_단어", index + 2, "삭제", b, a, None, "영문약어 중복")
    kept.reverse()
    return kept
