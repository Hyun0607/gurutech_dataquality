"""1) 메타 → RAW, 2) 값 정제, 값 정제 최종마무리 + ① 타입 파싱·길이 정책."""
import re

from ..model import RAW_COLS, ChangeLog, col
from ..vba import clean_text, cstr, is_empty, last_row, s, trim, ucase, val

A, B, C, D, E, F, G = range(RAW_COLS)


def meta_to_raw(meta_rows: list) -> list:
    """메타_시트_값_가져오기: Z·AA·AI·AJ·AO·AP → RAW A~F."""
    count = last_row(meta_rows, col("Z"))
    picks = [col(x) for x in ("Z", "AA", "AI", "AJ", "AO", "AP")]
    return [[meta_rows[i][p] for p in picks] + [None] for i in range(count)]


def refine(raw: list, log: ChangeLog) -> None:
    """값_정제: 대문자화, 길이 누락 → 0, 한글 컬럼명 정제, 같은 한글 테이블명에 _01 번호."""
    groups = {}
    for i, row in enumerate(raw):
        row[E] = ucase(s(row[E]))

        length = row[F]
        text = cstr(length)
        if "," in text:
            length = text[: text.index(",")]
        length_text = trim(cstr(length))
        if row[E] != "" and length_text == "":
            log.changed("값 정제", "RAW", i + 2, "데이터 길이", row[F], 0, "길이 누락 → 0")
            row[F] = 0
        else:
            row[F] = val(length_text)

        row[A] = ucase(s(row[A]))
        row[B] = ucase(s(row[B]))
        row[D] = ucase(s(row[D]))
        cleaned = clean_text(row[C])
        log.changed("값 정제", "RAW", i + 2, "한글 컬럼명", row[C], cleaned, "특수문자 제거")
        row[C] = cleaned

        if row[A] != "" and row[B] != "":
            inner = groups.setdefault(row[A], {})
            if row[B] not in inner:
                inner[row[B]] = len(inner) + 1

    for i, row in enumerate(raw):
        if row[A] != "" and row[B] != "":
            inner = groups[row[A]]
            if len(inner) > 1:
                new = f"{row[A]}_{inner[row[B]]:02d}"
                log.changed("값 정제", "RAW", i + 2, "한글 테이블명", row[A], new, "같은 한글 테이블명 번호 부여")
                row[A] = new


def final_refine(raw: list, log: ChangeLog) -> None:
    """값_정제_최종마무리: 정의서 복사 직전 길이 누락 재확인."""
    for i, row in enumerate(raw):
        type_text = ucase(s(row[E]))
        length_text = s(row[F])
        if "," in length_text:
            length_text = length_text[: length_text.index(",")]
        if type_text != "" and length_text in ("", "0"):
            log.changed("값 정제 최종", "RAW", i + 2, "데이터 길이", row[F], 0, "길이 누락 → 0")
            row[F] = 0
        elif length_text != "":
            row[F] = val(length_text)


# ---- ① 고도화 -------------------------------------------------------------

_TYPE_WITH_LENGTH = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _]*?)\s*\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)\s*$")


def parse_scale(length) -> int | None:
    """'10,2' → 2. 소수점 길이가 없으면 None."""
    text = cstr(length)
    if "," not in text:
        return None
    tail = trim(text[text.index(",") + 1:])
    return int(tail) if tail.isdigit() else None


def split_type_length(raw: list, log: ChangeLog) -> None:
    """VARCHAR2(100), NUMBER(10,2) 형태를 타입·길이·소수점으로 나눈다 (값 정제 전에 실행)."""
    for i, row in enumerate(raw):
        match = _TYPE_WITH_LENGTH.match(cstr(row[E]))
        if match:
            base, length, scale = match.groups()
            log.changed("① 타입 파싱", "RAW", i + 2, "데이터 타입", row[E], base.upper(), "타입에 포함된 길이 분리")
            row[E] = base.upper()
            if is_empty(row[F]) or s(row[F]) == "":
                row[F] = f"{length},{scale}" if scale else length
                log.add("① 타입 파싱", "RAW", i + 2, "변경", "데이터 길이", None, row[F], "타입에 포함된 길이 사용")
        row[G] = parse_scale(row[F])


def unify_type_alias(raw: list, meta_rows: list, aliases: dict, log: ChangeLog) -> None:
    """같은 타입의 다른 표기를 DBMS 공식 표기로 맞춘다 (예: PostgreSQL CHAR → CHARACTER).

    aliases: {DBMS: {표기: 공식 표기}}. DBMS는 메타 R열(DBMS 종류). 표기가 섞이면 한 용어가 한 도메인만 가리킬 수 있어
    적은 쪽이 타입 불일치가 된다.
    """
    for i, row in enumerate(raw):
        dbms = ucase(s(meta_rows[i][col("R")])) if i < len(meta_rows) else ""
        target = aliases.get(dbms, {}).get(ucase(s(row[E])))
        if target:
            log.changed("① 타입 표기 통일", "RAW", i + 2, "데이터 타입", row[E], target, f"{dbms} 공식 표기")
            row[E] = target


def fix_max_length(raw: list, log: ChangeLog) -> None:
    """MAX 길이(-1, 예: SQL Server VARBINARY(MAX))는 기관메타 수동등록이 받지 않아 1로 바꾼다 (예술경영지원센터 업로드본)."""
    for i, row in enumerate(raw):
        if s(row[F]) != "" and val(row[F]) < 0:
            log.changed("① 길이 정책", "RAW", i + 2, "데이터 길이", row[F], 1, f"{s(row[E])} 길이 {s(row[F])}(MAX) → 1 (수동등록 업로드 불가)")
            row[F] = 1


def apply_length_policy(raw: list, policy: dict, log: ChangeLog) -> None:
    """길이가 필수인 타입의 길이 누락에 정책값을 넣는다 (예: NUMBER 38, 세부 안내서 p.76)."""
    for i, row in enumerate(raw):
        data_type = ucase(s(row[E]))
        if data_type in policy and val(row[F]) == 0:
            log.changed("① 길이 정책", "RAW", i + 2, "데이터 길이", row[F], policy[data_type], f"{data_type} 길이 누락 → 정책값")
            row[F] = policy[data_type]
