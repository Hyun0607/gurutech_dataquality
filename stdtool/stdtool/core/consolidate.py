"""6) 용어 중복값 처리, 8) 도메인 적용, 9) 중복 제거 및 정의서 작성, 정의서 데이터 길이 최종 보정."""
from dataclasses import dataclass, field

from ..model import COLUMN_DEF_COLS, REMOVED_COLS, TABLE_DEF_COLS, ChangeLog, blank_row, col
from ..vba import TextDict, cstr, last_row, norm_key, s, val
from .cleanse import A, B, C, D, E, F, G

TA, TC, TE = col("A"), col("C"), col("E")


def _remove_if_exists(rows, last, key_of, step, log, reason):
    """RemoveIfExists를 아래에서 위로: 같은 키는 가장 아래 행만 남긴다."""
    seen, drop = TextDict(), set()
    for i in range(last - 1, -1, -1):
        key = key_of(rows[i])
        if key == "||":
            continue
        if key in seen:
            drop.add(i)
            log.add(step, "2_용어", i + 2, "삭제", key, None, None, reason)
        else:
            seen[key] = True
    return [r for i, r in enumerate(rows) if i not in drop]


def _keep_max(rows, group_of, value_of, step, log, reason, blank):
    """그룹별 최빈값(동률이면 먼저 나온 값)만 남기고 나머지 행을 지운다."""
    counts = {}
    for r in rows:
        group = group_of(r)
        if group is None:
            continue
        inner = counts.setdefault(norm_key(group), {})
        value = value_of(r) or blank
        spelling, n = inner.get(norm_key(value), (value, 0))
        inner[norm_key(value)] = (spelling, n + 1)
    best = {}
    for group, inner in counts.items():
        top, top_n = "", 0
        for spelling, n in inner.values():
            if n > top_n:
                top, top_n = spelling, n
        best[group] = top
    kept = []
    for i, r in enumerate(rows):
        group = group_of(r)
        if group is not None and best[norm_key(group)] != (value_of(r) or blank):
            log.add(step, "2_용어", i + 2, "삭제", f"{s(r[TA])}|{s(r[TC])}|{s(r[TE])}", None, best[norm_key(group)], reason)
            continue
        kept.append(r)
    return kept


def dedupe_terms(terms: list, log: ChangeLog) -> list:
    """용어_중복값_처리."""
    step = "용어 중복 처리"
    terms = _remove_if_exists(terms, last_row(terms, TA),
                              lambda r: f"{s(r[TA])}|{s(r[TC])}|{s(r[TE])}", step, log, "용어·영문·도메인 완전 중복")

    def by(key_col):
        return lambda r: s(r[key_col]) or None

    n = last_row(terms, TC)
    terms = _keep_max(terms[:n], by(TC), lambda r: s(r[TE]), step, log, "영문약어명별 최빈 도메인만 유지", "(blank)") + terms[n:]
    n = last_row(terms, TA)
    terms = _keep_max(terms[:n], by(TA), lambda r: s(r[TE]), step, log, "용어명별 최빈 도메인만 유지", "(blank)") + terms[n:]
    n = last_row(terms, TC)
    terms = _keep_max(terms[:n], lambda r: f"{s(r[TC])}|{s(r[TE]) or '(blank)'}" if s(r[TC]) else None,
                      lambda r: s(r[TA]), step, log, "영문약어명·도메인별 최빈 용어명만 유지", "(blankKor)") + terms[n:]
    terms = _remove_if_exists(terms, last_row(terms, TA),
                              lambda r: f"{s(r[TA])}|{s(r[TC])}", step, log, "용어명·영문약어명 중복")
    # 한글명 번호 부여(NumberSuffix)는 매크로와 같이 값을 바꾸지 않는다.
    return terms


def apply_domains(raw: list, terms: list, domains: list, log: ChangeLog, with_scale: bool) -> None:
    """도메인_적용: 용어가 가리키는 도메인의 타입·길이를 같은 영문컬럼명의 RAW 행에 반영."""
    by_name = {}
    for d in domains[: last_row(domains, col("C"))]:
        name = s(d[col("C")])
        if len(name) > 0:
            by_name[name] = (d[col("E")], d[col("F")], d[col("G")])
    rows_by_abbr = {}
    for i, r in enumerate(raw[: last_row(raw, D)]):
        abbr = s(r[D])
        if len(abbr) > 0:
            rows_by_abbr.setdefault(abbr, []).append(i)
    for t in terms[: last_row(terms, TC)]:
        abbr, name = s(t[TC]), s(t[TE])
        if name in by_name and abbr in rows_by_abbr:
            data_type, length, scale = by_name[name]
            for i in rows_by_abbr[abbr]:
                log.changed("도메인 적용", "RAW", i + 2, "데이터 타입", raw[i][E], data_type, f"도메인 {name}")
                log.changed("도메인 적용", "RAW", i + 2, "데이터 길이", raw[i][F], length, f"도메인 {name}")
                raw[i][E], raw[i][F] = data_type, length
                if with_scale:
                    raw[i][G] = scale


@dataclass
class Definitions:
    tables: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    removed_raw_index: list = field(default_factory=list)   # 0부터 시작하는 RAW 행 = 메타 데이터 행
    zero_length_rows: set = field(default_factory=set)      # 컬럼정의서에서 노란색으로 표시할 행


def build_definitions(raw: list, log: ChangeLog) -> Definitions:
    """중복제거_및_정의서_복사."""
    out = Definitions()
    seen_tables, seen_columns = set(), set()
    for i, r in enumerate(raw[: last_row(raw, A)]):
        tbl_ko, tbl_en, col_ko, col_en = s(r[A]), s(r[B]), s(r[C]), s(r[D])
        dtype, dlen = s(r[E]), s(r[F])
        if dtype == "":
            dtype, dlen = "VARCHAR", "0"
        elif dlen == "":
            dlen = "0"

        if tbl_en != "" and tbl_en not in seen_tables:
            seen_tables.add(tbl_en)
            t = blank_row(TABLE_DEF_COLS)
            t[col("B")], t[col("C")] = tbl_ko, tbl_en
            out.tables.append(t)

        key = (tbl_en, col_ko, col_en, dtype, dlen)
        if tbl_en != "" and col_ko != "" and col_en != "":
            if key not in seen_columns:
                seen_columns.add(key)
                c = blank_row(COLUMN_DEF_COLS)
                c[col("A")], c[col("B")], c[col("C")] = tbl_en, col_ko, col_en
                c[col("G")], c[col("H")] = dtype, val(dlen)
                if dlen == "0":
                    out.zero_length_rows.add(len(out.columns))
                out.columns.append(c)
            else:
                d = blank_row(REMOVED_COLS)
                d[:5] = [tbl_en, col_ko, col_en, dtype, val(dlen)]
                d[5] = i + 2
                out.removed.append(d)
                out.removed_raw_index.append(i)
                log.add("정의서 작성", "컬럼정의서", i + 2, "삭제", f"{tbl_en}.{col_en}", None, None, "같은 테이블의 같은 컬럼 중복 → 제거된 항목")
    return out


def fix_domain_lengths(domains: list, log: ChangeLog) -> set:
    """정의서_데이터길이_최종보정 (1_도메인): 빈 타입은 VARCHAR, 빈 길이는 0. 고친 행 번호를 돌려준다."""
    fixed = set()
    for i, d in enumerate(domains):
        type_text, len_text = s(d[col("E")]), s(d[col("F")])
        if type_text == "" or len_text == "":
            if type_text != "" and len_text == "":
                d[col("F")] = 0
            elif type_text == "":
                d[col("E")], d[col("F")] = "VARCHAR", 0
            fixed.add(i)
            log.add("도메인 길이 보정", "1_도메인", i + 2, "변경", cstr(d[col("C")]), None, None, "빈 타입·길이 보정")
    return fixed
