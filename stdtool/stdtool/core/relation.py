"""구조 2-1-4-1 물리 ERD 대체: 테이블관계정의서 (부모·자식 테이블과 연결 컬럼).

정의서에 PK·FK가 없으므로 컬럼 이름으로 관계를 짐작한다.
- 여러 테이블에 같은 이름으로 있는 키 컬럼(…_IDX, …_SN, …_ID, …_NO, …_SEQ)을 모은다.
- 그 컬럼의 '주인' 테이블을 부모로 본다: 테이블 이름이 컬럼 줄기와 같거나(LECTURE_IDX → LECTURE,
  BBS_SN → BBS_MST, ENT_SN → AT_ENT_INFO), 테이블 한글명이 컬럼 한글명 줄기와 같은 테이블
  (채용공고일련번호 → 채용공고). 주인이 둘 이상 같은 점수면 판단하지 않는다.
- 다른 테이블이 그 키를 꼬리로 가진 컬럼도 자식으로 본다 (CODE.CODE_IDX → LECTURE.AREA_CODE_IDX).
- 상세 테이블(X_SUB_TB, X_FILE)은 X_TB·X 의 자식으로 본다 (자기 키 UNQ_NO → 상세에만 있는 B_IDX).
- 백업 테이블(이름 끝 _YYYYMMDD), 부모를 그대로 복사한 테이블(컬럼 60% 넘게 같음), 등록자ID 같은 공통 컬럼은 뺀다.
"""
import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass

KEY_SUFFIX = re.compile(r"(_IDX|IDX|_SN|_ID|ID|_NO|_SEQ)$")
KOR_SUFFIX = re.compile(r"(일련번호|아이디|ID|고유번호|번호|인덱스)$")
GENERIC = {"REG_ID", "UP_ID", "UPD_ID", "MDFCN_ID", "MDFR_ID", "RGTR_ID", "FRST_RGTR_ID", "LAST_MDFR_ID", "ANS_ID",
           "ANSWR_ID", "ID", "IDX", "SEQ", "NO", "SN", "UNQ_NO", "LOG_SN", "SSN_ID", "SESSION_ID", "SORT_SEQ"}
TABLE_PREFIX = re.compile(r"^(TB_|TBL_|T_|AT_|ET_|GK_)")
OWNER_TAILS = ("", "_MST", "_MASTER", "_INFO", "_MNG", "_MEMBER", "S")
BACKUP = re.compile(r"_\d{8}$")
DETAIL = re.compile(r"^(.+)_(SUB|FILE|ATCH|ATTACH|DTL|DETAIL)$")


@dataclass
class Relation:
    parent: str
    parent_column: str
    child: str
    child_column: str
    basis: str = ""       # 짐작한 근거 (화면 표시)
    use: bool = True


def _norm(table: str) -> str:
    return re.sub(r"_TB$", "", TABLE_PREFIX.sub("", table.upper()))


def _similar(a, b) -> bool:
    """부모를 그대로 복사한 테이블 (휴면·임시 사본). 컬럼이 몇 개 안 되는 테이블은 보지 않는다."""
    a, b = set(a), set(b)
    return min(len(a), len(b)) >= 4 and len(a & b) / len(a | b) > 0.6


def owner(column: str, kor: str, holders: list, table_kor: dict):
    """키 컬럼의 주인 테이블과 근거. 못 정하면 (None, '')."""
    stem = KEY_SUFFIX.sub("", column)
    kstem = KOR_SUFFIX.sub("", kor.replace(" ", ""))
    best = []
    for t in holders:
        n = _norm(t)
        if any(n == stem + tail for tail in OWNER_TAILS):
            best.append((3, -len(t), t, "테이블명 = 컬럼명"))
        elif kstem and table_kor.get(t.upper(), "").replace(" ", "") == kstem:
            best.append((3, -len(t), t, "한글 테이블명 = 컬럼 한글명"))
        elif stem and n.endswith("_" + stem):
            best.append((2, -len(t), t, "테이블명 끝 = 컬럼명"))
    if not best:
        return None, ""
    best.sort(reverse=True)
    if len(best) > 1 and best[0][:2] == best[1][:2]:
        return None, ""
    return best[0][2], best[0][3]


def infer(columns: list, table_kor: dict) -> list:
    """columns: [(테이블, 영문컬럼명, 한글컬럼명)] (정의서 순서). table_kor: {영문테이블명 대문자: 한글명}."""
    tabs = OrderedDict()
    for table, eng, kor in columns:
        if table and eng:
            tabs.setdefault(table, OrderedDict()).setdefault(eng.upper(), (eng, kor))
    holders = defaultdict(list)
    for t, cols in tabs.items():
        if not BACKUP.search(t):
            for c in cols:
                holders[c].append(t)

    found, seen = [], set()

    def add(p, pc, c, cc, basis):
        if p == c or BACKUP.search(c) or c.upper() == f"INACTIVE_{p.upper()}" or _similar(tabs[p], tabs[c]):
            return
        key = (p, pc, c, cc)
        if key not in seen:
            seen.add(key)
            found.append(Relation(p, tabs[p][pc][0], c, tabs[c][cc][0], basis))

    owners = {}
    for col_key, ts in holders.items():
        if len(ts) < 2 or col_key in GENERIC or not KEY_SUFFIX.search(col_key):
            continue
        parent, basis = owner(col_key, tabs[ts[0]][col_key][1], ts, table_kor)
        if parent:
            owners[col_key] = parent
            for child in ts:
                add(parent, col_key, child, col_key, basis)
    for col_key, parent in owners.items():
        tail = "_" + col_key
        for t, cols in tabs.items():
            for c in cols:
                if c.endswith(tail) and c not in GENERIC:
                    add(parent, col_key, t, c, f"컬럼명 끝 = {tabs[parent][col_key][0]}")
    # 상세 테이블: X_SUB_TB·X_FILE 은 X_TB·X 의 자식. 둘 다 가진 자기 키(UNQ_NO 등) → 상세에만 있는 키 컬럼 하나
    by_norm = {re.sub(r"_TB$", "", t.upper()): t for t in tabs}
    for name, child in by_norm.items():
        m = DETAIL.match(name)
        parent = by_norm.get(m.group(1)) if m else None
        if not parent:
            continue
        own = [c for c in tabs[child] if c in tabs[parent] and c in GENERIC and KEY_SUFFIX.search(c)]
        refs = [c for c in tabs[child] if c not in tabs[parent] and c not in GENERIC and KEY_SUFFIX.search(c)]
        if len(own) == 1 and len(refs) == 1:
            add(parent, own[0], child, refs[0], "상세 테이블(_SUB·_FILE)")
    order = {t: i for i, t in enumerate(tabs)}
    found.sort(key=lambda r: (order[r.parent], r.parent_column, order[r.child], r.child_column))
    return found


def build(columns_def: list, tables_def: list, meta_rows: list, db_name: str) -> tuple:
    """컬럼·테이블 정의서로 관계 목록. 반환: (관계 목록, 테이블 정보 {대문자: (DB명, 소유자, 한글명, 영문명)},
    컬럼 한글명 {(테이블 대문자, 컬럼 대문자): 한글명}). DB명은 메타 영문 DB명(P), 소유자는 메타 테이블 소유자(Y)."""
    from ..model import col
    from ..vba import s
    meta = {}
    for m in meta_rows:
        meta.setdefault(s(m[col("AA")]).upper(), m)
    info, table_kor = {}, {}
    for t in tables_def:
        eng = s(t[col("C")])
        if eng:
            m = meta.get(eng.upper())
            db, owner_name = (s(m[col("P")]) or db_name, s(m[col("Y")])) if m else (db_name, "")
            info[eng.upper()] = (db, owner_name, s(t[col("B")]), eng)
            table_kor[eng.upper()] = s(t[col("B")])
    columns = [(s(c[col("A")]), s(c[col("C")]), s(c[col("B")])) for c in columns_def]
    kor = {(t.upper(), e.upper()): k for t, e, k in columns}
    return infer(columns, table_kor), info, kor


def rows(relations: list, info: dict, kor: dict) -> list:
    """양식 행: 순번, 부모(DB·소유자·한글테이블·영문테이블·한글컬럼·영문컬럼), 자식(같은 6칸). 쓰기로 한 관계만."""
    out = []
    for r in (x for x in relations if x.use):
        line = [len(out) + 1]
        for table, column in ((r.parent, r.parent_column), (r.child, r.child_column)):
            db, owner_name, table_kor, eng = info.get(table.upper(), ("", "", "", table))
            line += [db, owner_name, table_kor, eng, kor.get((table.upper(), column.upper()), ""), column]
        out.append(line)
    return out
