"""기관표준을 표준 사전 DB(MySQL std_dict 또는 사전 파일)에 두기.

한 DB 안에 테이블 5개를 두고 기관명 열로 나눈다 (기관이 늘어도 테이블은 늘지 않는다).
- inst_std    : 기관별 기관표준 목록 (기관표준명, 가져온 형식·파일·날짜)
- inst_term · inst_word · inst_domain · inst_code : 등록 양식 열 그대로 + 통합시스템 점검결과 4열(있을 때)
버전 관리는 하지 않는다: 한 기관을 다시 가져오면 그 기관 행만 지우고 새로 넣는다 (다른 기관은 그대로).
"""
from datetime import datetime

from .dictionary import Sheet
from .workbook.inst_reader import AREAS, InstStandard, SOURCE_PORTAL, TEMPLATE

INFO = "inst_std"
INFO_COLUMNS = ["org_name", "std_name", "source", "file_names", "imported_at", "term_count", "word_count",
                "domain_count", "code_count"]
RESULT_COLUMNS = ["comp_result", "comp_detail", "conf_result", "conf_detail"]
TABLES = {   # 영역: (테이블, 등록 양식 열 순서의 DB 열)
    "용어": ("inst_term", ["term_name", "term_eng", "term_abbr", "description", "domain_name", "dept_name", "code_name",
                         "biz_area", "enact_date", "note"]),
    "단어": ("inst_word", ["word_name", "word_abbr", "word_eng", "description", "is_format", "domain_class", "synonyms",
                         "forbidden", "enact_date", "note"]),
    "도메인": ("inst_domain", ["group_name", "domain_class", "domain_name", "description", "data_type", "data_length",
                            "data_scale", "storage_format", "display_format", "unit", "allowed_value", "enact_date", "note"]),
    "코드": ("inst_code", ["dept_name", "code_kor", "code_eng", "description", "data_type", "data_length", "code_value",
                         "code_meaning", "enact_date", "note"]),
}
for _area, (_t, _cols) in TABLES.items():
    assert len(_cols) == len(TEMPLATE[_area]), _area

# MySQL 열 크기 (긴 설명·허용값·이음동의어는 TEXT)
_TEXT = {"description", "allowed_value", "synonyms", "forbidden", "note", "comp_detail", "conf_detail", "code_meaning"}
_SIZES = {"org_name": 100, "term_name": 200, "term_eng": 300, "term_abbr": 200, "domain_name": 100, "word_name": 100,
          "word_abbr": 100, "word_eng": 200, "code_kor": 200, "code_eng": 200, "code_value": 200}
_LABELS = {"comp_result": "완전성점검결과", "comp_detail": "완전성점검결과내용", "conf_result": "공통표준준용결과",
           "conf_detail": "공통표준준용결과내용"}
for _area, (_t, _cols) in TABLES.items():
    for _c, _h in zip(_cols, TEMPLATE[_area]):
        _LABELS.setdefault(_c, _h)
_INDEX = {"inst_term": ["term_name", "term_abbr"], "inst_word": ["word_name", "word_abbr"], "inst_domain": ["domain_name"],
          "inst_code": ["code_kor"]}


def _columns(area: str) -> list:
    return ["org_name", "row_no", *TABLES[area][1], *RESULT_COLUMNS]


def mysql_ddl() -> str:
    """MySQL 테이블 만들기 (sql/schema.sql 과 DBeaver 스크립트에 쓴다)."""
    def col(name, area):
        if name in _TEXT:
            kind = "TEXT"
        elif name == "row_no":
            kind = "INT NOT NULL"
        else:
            kind = f"VARCHAR({_SIZES.get(name, 50 if name in ('enact_date', 'is_format', 'comp_result', 'conf_result') else 100)})"
        if name == "org_name":
            kind += " NOT NULL"
        own = dict(zip(TABLES[area][1], TEMPLATE[area]))   # 같은 열 이름(description 등)도 표마다 이름이 다르다
        label = {"org_name": "기관명 (평가대상 목록의 기관명)", "row_no": "원본 행 순서"}.get(name) or own.get(name) \
            or _LABELS.get(name, name)
        return f"  {name:<15} {kind} COMMENT '{label}'"

    parts = [f"""CREATE TABLE IF NOT EXISTS std_dict.{INFO} (
  org_name     VARCHAR(100) NOT NULL PRIMARY KEY COMMENT '기관명 (평가대상 목록의 기관명)',
  std_name     VARCHAR(200) COMMENT '기관표준명',
  source       VARCHAR(30)  COMMENT '가져온 형식 (등록 양식 / 통합시스템 점검결과)',
  file_names   TEXT         COMMENT '가져온 파일',
  imported_at  VARCHAR(20)  COMMENT '가져온 날짜',
  term_count   INT, word_count INT, domain_count INT, code_count INT
) COMMENT '기관별 기관표준 목록';"""]
    for area, (table, _) in TABLES.items():
        cols = ",\n".join(col(c, area) for c in _columns(area))
        keys = "".join(f",\n  KEY ix_{table}_{c} (org_name, {c}{'(100)' if c in _TEXT else ''})" for c in _INDEX[table])
        parts.append(f"CREATE TABLE IF NOT EXISTS std_dict.{table} (\n{cols},\n  PRIMARY KEY (org_name, row_no){keys}\n)"
                     f" COMMENT '기관표준{area}';")
    return "\n\n".join(parts)


def _file_ddl() -> list:
    return [f"CREATE TABLE IF NOT EXISTS {INFO} ({', '.join(INFO_COLUMNS)})"] + [
        f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(_columns(area))})" for area, (table, _) in TABLES.items()]


def _rows(inst: InstStandard, area: str) -> list:
    results = inst.results.get(area) or []
    out = []
    for i, values in enumerate(inst.area(area)):
        res = results[i] if i < len(results) else (None,) * 4
        out.append((inst.org, i + 1, *values, *res))
    return out


def _info_row(inst: InstStandard) -> tuple:
    c = inst.counts
    return (inst.org, inst.name, inst.source, ", ".join(inst.files), datetime.now().strftime("%Y-%m-%d %H:%M"),
            c["용어"], c["단어"], c["도메인"], c["코드"])


def import_inst(conn, inst: InstStandard) -> dict:
    """기관표준 하나를 DB(MySQL 또는 사전 파일)에 넣는다. 그 기관 행만 바꾼다. 반환: 영역별 행 수."""
    from . import db
    with conn.cursor() as cur:
        if db._is_file(conn):
            for ddl in _file_ddl():
                cur.execute(ddl)
        elif not db._has_table(conn, cur, INFO):
            raise db.DbError("MySQL에 기관표준 테이블이 없습니다. sql/schema.sql(기관표준 부분)을 DBeaver에서 먼저 실행하세요.")
        try:
            cur.execute(f"DELETE FROM {INFO} WHERE org_name = %s", (inst.org,))
            cur.execute(f"INSERT INTO {INFO} ({', '.join(INFO_COLUMNS)}) VALUES ({', '.join(['%s'] * len(INFO_COLUMNS))})",
                        _info_row(inst))
            for area, (table, _) in TABLES.items():
                cur.execute(f"DELETE FROM {table} WHERE org_name = %s", (inst.org,))
                cols = _columns(area)
                cur.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                                _rows(inst, area))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return inst.counts


def touch_file_info(conn, note: str) -> dict:
    """사전 파일에 기관표준을 넣은 뒤: 만든 날짜를 지금으로 (새 사전으로 알아보게), 행 수·바꾼 내용을 남긴다."""
    import json
    from . import db
    with conn.cursor() as cur:
        cur.execute(f"SELECT key, value FROM {db.INFO_TABLE}")
        info = dict(cur.fetchall())
        counts = json.loads(info.get("counts") or "{}")
        for table in [INFO] + [t for t, _ in TABLES.values()]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cur.fetchone()[0]
        info.update(created_at=datetime.now().strftime("%Y-%m-%d %H:%M"), counts=json.dumps(counts, ensure_ascii=False),
                    note=note)
        cur.execute(f"DELETE FROM {db.INFO_TABLE}")
        cur.executemany(f"INSERT INTO {db.INFO_TABLE} VALUES (%s, %s)", list(info.items()))
    conn.commit()
    return info


def _sql_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def inst_sql(insts: list, with_ddl: bool = True, batch: int = 500) -> str:
    """DBeaver에서 실행할 MySQL 스크립트: (테이블 만들기) + 기관별로 지우고 넣기, 한 트랜잭션."""
    lines = ["-- stdtool 기관표준 (DBeaver: SQL 편집기로 열고 '스크립트 실행' Alt+X)",
             "-- 같은 기관을 다시 실행하면 그 기관 행만 지우고 새로 넣는다.",
             f"-- 만든 날짜 {datetime.now():%Y-%m-%d %H:%M} · 기관 " + ", ".join(i.org for i in insts), ""]
    if with_ddl:
        lines += [mysql_ddl(), ""]
    lines.append("START TRANSACTION;")
    for inst in insts:
        org = _sql_value(inst.org)
        lines.append(f"\n-- {inst.org} · {inst.name or '기관표준'} · {inst.source} · "
                     + " · ".join(f"{a} {n:,}" for a, n in inst.counts.items()))
        lines.append(f"DELETE FROM std_dict.{INFO} WHERE org_name = {org};")
        lines.append(f"INSERT INTO std_dict.{INFO} ({', '.join(INFO_COLUMNS)}) VALUES "
                     f"({', '.join(map(_sql_value, _info_row(inst)))});")
        for area, (table, _) in TABLES.items():
            lines.append(f"DELETE FROM std_dict.{table} WHERE org_name = {org};")
            rows = _rows(inst, area)
            for start in range(0, len(rows), batch):
                values = ",\n".join("(" + ", ".join(map(_sql_value, r)) + ")" for r in rows[start:start + batch])
                lines.append(f"INSERT INTO std_dict.{table} ({', '.join(_columns(area))}) VALUES\n{values};")
    lines += ["", "COMMIT;", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------

def same_org(a: str, b: str) -> bool:
    """'충청남도 계룡시'와 '계룡시'처럼 한쪽이 다른 쪽 끝에 붙어 있으면 같은 기관."""
    from .core.preventive import org_key
    x, y = org_key(a), org_key(b)
    if not x or not y:
        return False
    short, long_ = sorted((x, y), key=len)
    return x == y or (len(short) >= 3 and long_.endswith(short))


def inst_orgs(conn) -> list:
    """DB에 있는 기관표준 목록 [{'org', 'name', 'source', 'files', 'imported_at', 'counts'}]. 표가 없으면 빈 목록."""
    from . import db
    with conn.cursor() as cur:
        if not db._has_table(conn, cur, INFO):
            return []
        cur.execute(f"SELECT {', '.join(INFO_COLUMNS)} FROM {INFO} ORDER BY org_name")
        rows = cur.fetchall()
    return [{"org": r[0], "name": r[1] or "", "source": r[2] or "", "files": r[3] or "", "imported_at": r[4] or "",
             "counts": dict(zip(AREAS, r[5:9]))} for r in rows]


def find_org(conn, org: str) -> str | None:
    """평가대상 목록의 기관명(예: 충청남도 계룡시)에 맞는 DB 기관표준의 기관명."""
    names = [o["org"] for o in inst_orgs(conn)]
    return next((n for n in names if n == org), None) or next((n for n in names if same_org(n, org)), None)


def load_inst(conn, org: str) -> InstStandard | None:
    """DB의 기관표준 (기관명이 조금 달라도 찾는다). 없으면 None."""
    found = find_org(conn, org) if org else None
    if found is None:
        return None
    info = next(o for o in inst_orgs(conn) if o["org"] == found)
    inst = InstStandard(found, info["name"], info["source"], [f for f in info["files"].split(", ") if f])
    with conn.cursor() as cur:
        for area, (table, cols) in TABLES.items():
            cur.execute(f"SELECT {', '.join(cols + RESULT_COLUMNS)} FROM {table} WHERE org_name = %s ORDER BY row_no",
                        (found,))
            data = [list(r) for r in cur.fetchall()]
            inst.rows[area] = [[None if v is None else str(v) for v in r[:len(cols)]] for r in data]
            if inst.source == SOURCE_PORTAL:
                inst.results[area] = [tuple(r[len(cols):]) for r in data]
    return inst


def inst_sheet(inst: InstStandard | None) -> list:
    """매크로 '기관표준' 시트 행 [한글 컬럼명, 영문 컬럼명, 데이터 타입, 데이터 길이]: 기관표준용어 + 그 도메인의 타입·길이."""
    if inst is None:
        return []
    domains = {}
    for d in inst.area("도메인"):
        domains.setdefault((d[2] or "").upper(), d)
    rows = []
    for t in inst.area("용어"):
        if not t[0] or not t[2]:
            continue
        d = domains.get((t[4] or "").upper())
        length = None
        if d is not None and d[5] not in (None, ""):
            length = f"{d[5]},{d[6]}" if d[6] not in (None, "", "0") else d[5]
        rows.append([t[0], t[2], d[4] if d is not None else None, length])
    return rows


def sheet(inst: InstStandard | None, header: list) -> Sheet:
    return Sheet(header, inst_sheet(inst))
