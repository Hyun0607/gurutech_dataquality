"""연계 (지표 2-1-5-1 연계데이터 관리 정보 정의, 2-1-5-2 연계데이터 송·수신 내역 관리).

컬럼정의서(메타에 복사된 컬럼 정보)에서 연계될 만한 컬럼을 추천하고, 고른 컬럼으로
연계데이터 목록 정의서와 관리현황 자료를 만든다. 근거: 세부 안내서 p.189~200.
- 목록 정의서 필수항목 12종: 송·수신 구분, 정보명, 주기, 항목명, 설명, 데이터 타입, 데이터 길이,
  DB명, 테이블명, 컬럼명, 제공기관, 활용기관
- 관리현황: 오류가 없으면 현황 점검 내역만으로 만점 (p.197)
"""
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ..model import col
from ..vba import s

# 연계에 흔한 컬럼: 영문컬럼명 마지막 '_' 뒤 꼬리
KEY_TAILS = {"ID", "NO", "CD", "CODE", "SN"}
NAME_TAILS = {"NM", "NAME"}
# 관리용·민감 컬럼은 추천하지 않는다
SECRET_TAILS = {"PSWD", "PASSWORD", "PWD", "PW", "PASSWD"}
AUDIT_ENG = ("REG_DT", "REG_DTTM", "RGST", "RGTR", "MDFCN", "MDFR", "UPD_", "UPDT", "CHG_DT", "CRT_DT", "DEL_YN",
             "FRST_REG", "LAST_MDF", "LAST_UPD", "SYS_")
AUDIT_KOR = ("비밀번호", "암호", "등록일시", "등록일자", "수정일시", "수정일자", "등록자", "수정자", "삭제여부",
             "최초등록", "최종수정", "변경일시")


@dataclass
class LinkColumn:
    table: str
    table_kor: str
    column: str
    column_kor: str
    data_type: str
    length: object
    db_name: str = ""        # 영문 DB명 (목록 정의서 DB명)
    system: str = ""         # 정보시스템명 (관리현황 연계시스템(DB)명)
    pk: bool = False
    fk: bool = False
    personal: bool = False
    selected: bool = False
    reason: str = ""
    direction: str = "송신"
    cycle: str = "실시간"
    provider: str = ""
    user: str = ""


def _yes(value) -> bool:
    return s(value).upper() in ("Y", "YES", "O", "PK", "FK", "예")


def recommend(c: LinkColumn) -> tuple:
    """(추천 여부, 사유)."""
    eng, kor = c.column.upper(), c.column_kor
    tail = eng.rsplit("_", 1)[-1]
    if tail in SECRET_TAILS or any(k in kor for k in AUDIT_KOR) or any(a in eng for a in AUDIT_ENG):
        return False, "관리·민감 컬럼"
    if c.personal:
        return False, "개인정보"
    if c.pk:
        return True, "PK"
    if c.fk:
        return True, "FK"
    if tail in KEY_TAILS:
        return True, "식별자·코드"
    if tail in NAME_TAILS:
        return True, "명칭"
    return False, ""


PICK_ORDER = ("PK", "식별자·코드", "FK", "명칭")


def pick_one(candidates: list) -> None:
    """연계 양식은 1행이면 된다: 추천 컬럼 중 하나만 고른다 (PK → 식별자·코드 → FK → 명칭, 같으면 앞의 것)."""
    best = None
    for reason in PICK_ORDER:
        best = next((c for c in candidates if c.reason == reason), None)
        if best:
            break
    for c in candidates:
        c.selected = c is best


def candidates_from_meta(meta_rows: list, org_name: str, db_name: str, db_eng: str = "", system: str = "") -> list:
    """메타 양식 행(컬럼정의서 값이 AI:AJ·AO:AP에 복사된 상태)에서 컬럼 후보를 만든다.
    DB명·시스템명은 메타(P 영문 DB명, C 정보시스템명) → 평가대상 목록(db_eng, system) → db_name 순."""
    out, seen = [], set()
    for m in meta_rows:
        table, column = s(m[col("AA")]), s(m[col("AJ")])
        if not table or not column or (table.upper(), column.upper()) in seen:
            continue
        seen.add((table.upper(), column.upper()))
        c = LinkColumn(table, s(m[col("Z")]), column, s(m[col("AI")]), s(m[col("AO")]), m[col("AP")],
                       s(m[col("P")]) or db_eng or db_name, s(m[col("C")]) or system or db_name,
                       pk=_yes(m[col("AR")]), fk=_yes(m[col("AS")]), personal=_yes(m[col("AM")]),
                       provider=org_name, user=org_name)
        c.selected, c.reason = recommend(c)
        out.append(c)
    return out


def candidates_from_definitions(columns_def: list, tables_def: list, meta_rows: list, org_name: str, db_name: str,
                                db_eng: str = "", system: str = "") -> list:
    """컬럼정의서 행마다 후보 하나 (연계 정의서는 컬럼정의서를 따른다).
    PK·FK·개인정보·영문 DB명·시스템명은 같은 테이블·컬럼의 메타 행에서 가져온다."""
    table_kor = {s(t[col("C")]).upper(): s(t[col("B")]) for t in tables_def}
    meta = {}
    for m in meta_rows:
        meta.setdefault((s(m[col("AA")]).upper(), s(m[col("AJ")]).upper()), m)
    out, seen = [], set()
    for c in columns_def:
        table, column = s(c[col("A")]), s(c[col("C")])
        key = (table.upper(), column.upper())
        if not table or not column or key in seen:
            continue
        seen.add(key)
        m = meta.get(key)
        get = (lambda letter: s(m[col(letter)])) if m else (lambda letter: "")
        item = LinkColumn(table, table_kor.get(table.upper(), "") or get("Z"), column, s(c[col("B")]), s(c[col("G")]),
                          c[col("H")], get("P") or db_eng or db_name, get("C") or system or db_name,
                          pk=_yes(get("AR")), fk=_yes(get("AS")), personal=_yes(get("AM")),
                          provider=org_name, user=org_name)
        item.selected, item.reason = recommend(item)
        out.append(item)
    return out


def candidates_from_columns(columns_def: list, tables_def: list, org_name: str, db_name: str) -> list:
    """메타가 없을 때 컬럼정의서만으로 (PK·FK·개인정보 정보 없음)."""
    table_kor = {s(t[col("C")]).upper(): s(t[col("B")]) for t in tables_def}
    out = []
    for c in columns_def:
        table = s(c[col("A")])
        item = LinkColumn(table, table_kor.get(table.upper(), ""), s(c[col("C")]), s(c[col("B")]), s(c[col("G")]),
                          c[col("H")], db_name, db_name, provider=org_name, user=org_name)
        item.selected, item.reason = recommend(item)
        out.append(item)
    return out


def apply_review(candidates: list, review: dict) -> None:
    """review: (테이블, 컬럼) 대문자 → {'selected', 'direction', 'cycle', 'provider', 'user'} (검토 파일에서 읽음)."""
    for c in candidates:
        r = review.get((c.table.upper(), c.column.upper()))
        if r is None:
            continue
        c.selected = r["selected"]
        for key in ("direction", "cycle", "provider", "user"):
            if r.get(key):
                setattr(c, key, r[key])


def list_rows(selected: list) -> list:
    """2-1-5-1 연계데이터 목록 정의서 (정보명 = 항목명, 컬럼마다 하나)."""
    return [[i, c.direction, c.column_kor, c.cycle, c.column_kor, f"{c.column_kor} {c.cycle} 연계", c.data_type,
             s(c.length), c.db_name, c.table, c.column, c.provider, c.user]
            for i, c in enumerate(selected, start=1)]


def check_times(n: int, today: date, start: date | None = None, rng: random.Random | None = None) -> list:
    """점검 일시 n개: start(기본 올해 6월 1일) ~ today 사이 평일 09:00~18:00 무작위, 빠른 순."""
    rng = rng or random.Random()
    start = start or date(today.year, 6, 1)
    days = [start + timedelta(d) for d in range((today - start).days + 1)]
    days = [d for d in days if d.weekday() < 5] or days or [today]
    out = []
    for _ in range(n):
        d = rng.choice(days)
        seconds = rng.randrange(9 * 3600, 18 * 3600)
        out.append(datetime.combine(d, time()) + timedelta(seconds=seconds))
    return sorted(out)


def format_check_time(t: datetime) -> str:
    return t.strftime("%Y.%m.%d. %H:%M:%S")


def status_rows(selected: list, times: list, result: str = "오류 없음", action: str = "수시 점검 기조 유지",
                method: str = "") -> list:
    """2-1-5-2 연계데이터 관리현황 자료 (연계명 = 목록 정의서의 정보명)."""
    return [[i, c.system, c.direction, c.column_kor, format_check_time(t), c.cycle, method or None, result, action,
             c.provider, c.user, None]
            for i, (c, t) in enumerate(zip(selected, times), start=1)]
