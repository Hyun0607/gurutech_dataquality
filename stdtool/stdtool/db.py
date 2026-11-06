"""표준 사전 DB: MySQL std_dict(관리자 원본) 또는 사전 파일(SQLite, 팀원 배포용). 테이블 구조는 sql/schema.sql.

버전 관리는 하지 않는다: 가져오기는 테이블 내용을 한 트랜잭션 안에서 지우고 새로 넣는다.
Code_type·Code_tail은 사람이 행을 추가해 쓰는 테이블이라 매크로에서 온 행(added_by = 'MACRO')만 다룬다:
매크로 행이 없을 때만 채우고(replace_codes면 매크로 행만 바꿈), 직접 추가한 행은 지우지 않는다.
비밀번호는 환경변수 STDTOOL_DB_PASSWORD 또는 Windows 자격 증명 관리자(화면 설정에서 저장)에서 읽는다. 설정 파일에는 두지 않는다.

사전 파일은 관리자가 MySQL에서 만든다(export_file). 같은 테이블·같은 값(열 타입 없이 MySQL이 준 값 그대로)이라
읽는 코드는 MySQL과 같고, dict_info 표에 만든 날짜·공통표준 차수가 있다.
"""
import getpass
import json
import os
import re
import shutil
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .config import DbSettings
from .dictionary import (SHEET_CODE_TAIL, SHEET_CODE_TYPE, SHEET_COMMON, Sheet, StandardDict, _rows_by_header,
                         common_standard_from_rows, load_from_macro_workbook)

PASSWORD_ENV = "STDTOOL_DB_PASSWORD"

# 매크로 시트 머리글 (Range.Find가 머리글 행도 보므로 시트와 같게)
COMMON_HEADER = ["한글 컬럼명", "영문 컬럼명", "데이터 타입", "데이터 길이"]
CODE_TYPE_HEADER = ["순번", "데이터 타입", "데이터 약어", "데이터 분류"]
CODE_TAIL_HEADER = ["순번", "도메인자르기", "도메인분류", "도메인중분류"]

MACRO_TABLES = {
    # 테이블: (시트, 열 4개)
    "macro_common": (SHEET_COMMON, ["row_no", "kor_name", "eng_name", "data_type", "data_length"]),
    "code_type": (SHEET_CODE_TYPE, ["seq", "type_name", "type_abbr", "type_class"]),
    "code_tail": (SHEET_CODE_TAIL, ["seq", "tail", "domain_class", "domain_mid_class"]),
}

_REVISION = [("use_yn", "사용여부"), ("revision_type", "개정구분명 (변경, 폐기)"),
             ("revision_item", "개정항목"), ("revision_note", "개정사유")]

# DB 열 ↔ 공통표준 원본 머리글
COMMON_TABLES = {
    "common_term": [
        ("enact_round", "제정차수"), ("term_name", "공통표준용어명"), ("description", "공통표준용어 설명"),
        ("term_abbr", "공통표준용어영문약어명"), ("domain_name", "공통표준도메인명"), ("allowed_value", "허용값"),
        ("storage_format", "저장형식"), ("display_format", "표현형식"), ("code_name", "행정표준코드명"),
        ("owner_org", "소관 기관명"), ("synonyms", "용어 이음동의어 목록"), *_REVISION,
        ("category_path", "1순위분류 경로"),
    ],
    "common_word": [
        ("enact_round", "제정차수"), ("word_name", "공통표준단어명"), ("word_abbr", "공통표준단어영문약어명"),
        ("word_eng", "공통표준단어영문명"), ("description", "공통표준단어설명"), ("is_format", "형식단어여부"),
        ("domain_class", "공통표준도메인 분류명"), ("synonyms", "이음동의어 목록"), ("forbidden", "금칙어 목록"),
        *_REVISION,
    ],
    "common_domain": [
        ("enact_round", "제정차수"), ("group_name", "공통표준도메인 그룹명"), ("domain_class", "공통표준도메인 분류명"),
        ("domain_name", "공통표준도메인명"), ("description", "공통표준도메인 설명"), ("data_type", "데이터 타입"),
        ("data_length", "데이터 길이"), ("data_scale", "소수점 길이"), ("storage_format", "저장형식"),
        ("display_format", "표현형식"), ("unit", "단위"), ("allowed_value", "허용값"), *_REVISION,
    ],
}
COMMON_FILES = {"common_term": "공통표준용어.xlsx", "common_word": "공통표준단어.xlsx", "common_domain": "공통표준도메인.xlsx"}


class DbError(Exception):
    pass


KEYRING_SERVICE = "stdtool"


def _keyring_user(db: DbSettings) -> str:
    return f"{db.user}@{db.host}:{db.port}"


def saved_password(db: DbSettings) -> str | None:
    """Windows 자격 증명 관리자에 저장된 비밀번호 (화면 설정에서 저장)."""
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, _keyring_user(db))
    except Exception:
        return None


def save_password(db: DbSettings, password: str) -> None:
    import keyring
    keyring.set_password(KEYRING_SERVICE, _keyring_user(db), password)


class _FileCursor:
    """MySQL 커서처럼 쓰는 SQLite 커서 (%s 자리표시자, with 문)."""

    def __init__(self, cur):
        self.cur = cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cur.close()
        return False

    def execute(self, sql, params=None):
        self.cur.execute(sql.replace("%s", "?"), params or ())

    def executemany(self, sql, rows):
        self.cur.executemany(sql.replace("%s", "?"), rows)

    def fetchone(self):
        return self.cur.fetchone()

    def fetchall(self):
        return self.cur.fetchall()


class FileConn:
    """사전 파일 접속. pymysql 접속과 같은 모양 (cursor·commit·rollback, with 문이 끝나면 닫힘)."""
    is_file = True

    def __init__(self, path):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)

    def cursor(self):
        return _FileCursor(self.conn.cursor())

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def connect(db: DbSettings):
    """사전 파일이 정해져 있으면 그 파일. 아니면 MySQL (비밀번호: 환경변수 STDTOOL_DB_PASSWORD, 없으면 자격 증명 관리자)."""
    if db.file:
        if not Path(db.file).exists():
            raise DbError(f"사전 파일이 없습니다: {db.file}\n설정 → 표준 사전에서 사전 파일을 고르세요.")
        return FileConn(db.file)
    import pymysql
    password = os.environ.get(PASSWORD_ENV) or saved_password(db)
    if not password:
        raise DbError(f"DB 비밀번호가 없습니다. 화면 설정에서 저장하거나 환경변수 {PASSWORD_ENV} 에 넣어 주세요.")
    try:
        return pymysql.connect(host=db.host, port=db.port, user=db.user, password=password,
                               database=db.database, charset="utf8mb4", autocommit=False)
    except pymysql.MySQLError as e:
        raise DbError(f"DB 접속 실패 ({db.user}@{db.host}:{db.port}/{db.database}): {e}") from e


# ---------------------------------------------------------------------------
# 엑셀 → DB 행
# ---------------------------------------------------------------------------

def macro_rows(dicts: StandardDict) -> dict:
    """매크로 사전 → {테이블: [행 튜플]}. macro_common.row_no 는 시트 행 번호 (머리글이 1행)."""
    return {
        "macro_common": [(i + 2, *r[:4]) for i, r in enumerate(dicts.common.rows)],
        "code_type": [tuple(r[:4]) for r in dicts.code_type.rows],
        "code_tail": [tuple(r[:4]) for r in dicts.code_tail.rows],
    }


def common_rows(table: str, rows: list) -> list:
    """원본 행(dict) 목록 → [(row_no, 열...)]. row_no 는 원본 순서 (머리글 다음부터 2)."""
    names = [h for _, h in COMMON_TABLES[table]]
    return [(i + 2, *(r.get(h) for h in names)) for i, r in enumerate(rows)]


# ---------------------------------------------------------------------------
# 가져오기
# ---------------------------------------------------------------------------

MACRO_AUTHOR = "MACRO"


def _count(cur, table: str, macro_only: bool = False) -> int:
    if macro_only:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE added_by = %s", (MACRO_AUTHOR,))
    else:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def _replace(cur, table: str, columns: list, rows: list, macro_only: bool = False):
    """macro_only면 매크로에서 온 행만 지우고 넣는다 (Code_type·Code_tail의 직접 추가한 행 보존)."""
    extra = {"added_by": MACRO_AUTHOR} if macro_only else {}
    cols = columns + list(extra)
    # TRUNCATE는 바로 커밋되므로 쓰지 않는다
    if macro_only:
        cur.execute(f"DELETE FROM {table} WHERE added_by = %s", (MACRO_AUTHOR,))
    else:
        cur.execute(f"DELETE FROM {table}")
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
    cur.executemany(sql, [(*r, *extra.values()) for r in rows])


def import_macro(conn, path: Path, replace_codes: bool = False) -> dict:
    """매크로 파일 공통표준·Code_type·Code_tail 시트 → DB. 반환: {테이블: 넣은 행 수 또는 '건너뜀'}."""
    data = macro_rows(load_from_macro_workbook(path))
    report = {}
    with conn.cursor() as cur:
        try:
            for table, (_, columns) in MACRO_TABLES.items():
                codes = table != "macro_common"
                if codes and not replace_codes and _count(cur, table, macro_only=True):
                    report[table] = f"건너뜀 (매크로 행 {_count(cur, table, macro_only=True)}개 있음, 바꾸려면 --replace-codes)"
                    continue
                _replace(cur, table, columns, data[table], macro_only=codes)
                report[table] = len(data[table])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return report


def import_common(conn, paths: dict) -> dict:
    """공통표준 원본 3개 → DB. paths: {테이블: 파일 경로}. 셋 다 한 번에 바꾼다."""
    data = {table: common_rows(table, _rows_by_header(Path(p))) for table, p in paths.items()}
    with conn.cursor() as cur:
        try:
            for table, rows in data.items():
                _replace(cur, table, ["row_no"] + [c for c, _ in COMMON_TABLES[table]], rows)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {table: len(rows) for table, rows in data.items()}


EVAL_TABLE = "eval_db"
EVAL_COLUMNS = ["row_no", "org_name", "org_seq", "system_name", "db_kor_name", "db_eng_name"]
EVAL_FILE_DDL = f"CREATE TABLE IF NOT EXISTS {EVAL_TABLE} ({', '.join(EVAL_COLUMNS)})"
EVAL_DDL = """CREATE TABLE IF NOT EXISTS eval_db (
  row_no      INT          NOT NULL PRIMARY KEY COMMENT '목록 행 번호',
  org_name    VARCHAR(100) NOT NULL COMMENT '기관명',
  org_seq     INT          COMMENT '기관 안 순번',
  system_name VARCHAR(200) NOT NULL COMMENT '정보시스템명',
  db_kor_name VARCHAR(200) COMMENT '한글 DB명',
  db_eng_name VARCHAR(100) COMMENT '영문 DB명',
  KEY ix_eval_org (org_name)
) COMMENT '전체 평가대상 DB 목록'"""


def _clean(value):
    """앞뒤 공백과 눈에 안 보이는 글자(폭 없는 공백 등) 제거."""
    if value is None:
        return None
    text = str(value).replace("​", "").replace("﻿", "").replace("\xa0", " ").strip()
    return text or None


def read_eval_list(path: Path) -> list:
    """전체 평가대상 DB리스트.xlsx: 기관명, 순번, 정보시스템명, 한글 DB명, 영문 DB명 (머리글 행은 있어도 없어도 됨)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        ws.reset_dimensions()
        out = []
        for r in ws.iter_rows(values_only=True):
            r = [_clean(v) for v in list(r[:5]) + [None] * (5 - len(r[:5]))]
            if not r[0] or not r[2]:
                continue
            if not str(r[1] or "").isdigit() and out == []:
                continue   # 머리글 행
            seq = int(r[1]) if str(r[1] or "").isdigit() else None
            out.append((len(out) + 1, r[0], seq, r[2], r[3], r[4]))
        return out
    finally:
        wb.close()


def import_eval_list(conn, path: Path) -> int:
    rows = read_eval_list(path)
    if not rows:
        raise DbError(f"평가대상 DB 목록에서 읽은 행이 없습니다: {path}")
    with conn.cursor() as cur:
        cur.execute(EVAL_FILE_DDL if _is_file(conn) else EVAL_DDL)   # 처음이면 표를 만든다 (DDL은 바로 반영됨)
        try:
            _replace(cur, EVAL_TABLE, EVAL_COLUMNS, rows)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return len(rows)


def load_eval_list(conn) -> list:
    """[{'org', 'seq', 'system', 'db_kor', 'db_eng'}], 목록 순서대로. 표가 없으면 빈 목록."""
    with conn.cursor() as cur:
        if not _has_table(conn, cur, EVAL_TABLE):
            return []
        rows = _select(cur, EVAL_TABLE, EVAL_COLUMNS[1:], "row_no")
    return [dict(zip(("org", "seq", "system", "db_kor", "db_eng"), r)) for r in rows]


def _is_file(conn) -> bool:
    return getattr(conn, "is_file", False)


def _has_table(conn, cur, table: str) -> bool:
    if _is_file(conn):
        cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = %s", (table,))
    else:
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
                    (table,))
    return bool(cur.fetchone()[0])


def db_label(entry: dict, entries: list) -> str:
    """산출물 파일에 쓰는 DB명: 시스템에 DB가 하나면 시스템명, 여러 개면 '시스템명_한글DB명'."""
    same = [e for e in entries if e["org"] == entry["org"] and e["system"] == entry["system"]]
    if len(same) > 1 and entry.get("db_kor"):
        return f"{entry['system']}_{entry['db_kor']}"
    return entry["system"]


def status(conn) -> dict:
    with conn.cursor() as cur:
        out = {t: _count(cur, t) for t in [*MACRO_TABLES, *COMMON_TABLES]}
    out[EVAL_TABLE] = len(load_eval_list(conn))
    return out


# ---------------------------------------------------------------------------
# DB → 프로그램 (엑셀에서 읽은 것과 같은 모양)
# ---------------------------------------------------------------------------

def _select(cur, table: str, columns: list, order: str) -> list:
    cur.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order}")
    return [list(r) for r in cur.fetchall()]


def load_dicts(conn, org: str = "") -> StandardDict:
    """매크로 사전. 기관표준 시트는 그 기관(org)의 기관표준이 DB에 있으면 기관표준용어로 채운다 (없으면 빈 시트 = 미준용)."""
    from . import inst_db
    with conn.cursor() as cur:
        common = _select(cur, "macro_common", MACRO_TABLES["macro_common"][1][1:], "row_no")
        code_type = _select(cur, "code_type", MACRO_TABLES["code_type"][1], "seq")
        code_tail = _select(cur, "code_tail", MACRO_TABLES["code_tail"][1], "seq")
    if not common or not code_type or not code_tail:
        raise DbError("DB에 매크로 사전이 비어 있습니다. 먼저 stdtool db import 를 실행하세요.")
    inst = inst_db.load_inst(conn, org) if org else None
    return StandardDict(Sheet(COMMON_HEADER, common), inst_db.sheet(inst, COMMON_HEADER),
                        Sheet(CODE_TYPE_HEADER, code_type), Sheet(CODE_TAIL_HEADER, code_tail))


def load_common(conn):
    """공통표준 원본. 비어 있으면 None (② 건너뜀)."""
    rows = {}
    with conn.cursor() as cur:
        for table, pairs in COMMON_TABLES.items():
            data = _select(cur, table, [c for c, _ in pairs], "row_no")
            rows[table] = [dict(zip([h for _, h in pairs], r)) for r in data]
    if not rows["common_term"]:
        return None
    return common_standard_from_rows(rows["common_term"], rows["common_word"], rows["common_domain"])


# ---------------------------------------------------------------------------
# 사전 파일 (팀원 배포용): MySQL → SQLite, 만든 날짜·공통표준 차수, 공유 폴더의 새 파일 찾기
# ---------------------------------------------------------------------------

INFO_TABLE = "dict_info"
_CODE_EXTRA = ["added_by", "added_at", "note"]
FILE_TABLES = {   # 테이블: (열, 정렬 열). 열 타입 없이 만들어 MySQL이 준 값(int·str)을 그대로 둔다
    "macro_common": (MACRO_TABLES["macro_common"][1], "row_no"),
    "code_type": (MACRO_TABLES["code_type"][1] + _CODE_EXTRA, "seq"),
    "code_tail": (MACRO_TABLES["code_tail"][1] + _CODE_EXTRA, "seq"),
    **{t: (["row_no"] + [c for c, _ in pairs], "row_no") for t, pairs in COMMON_TABLES.items()},
}


def _plain(value):
    """SQLite에 넣을 수 있는 값으로 (날짜는 글자로)."""
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def common_round(rounds) -> str:
    """제정차수 값들 중 가장 최근 차수 ('8차(2025.11월)' → '8차 2025.11')."""
    best = None
    for text in rounds:
        m = re.match(r"\s*(\d+)\s*차\s*\(?\s*(\d{4})[.\-](\d{1,2})", str(text or ""))
        if m:
            key = (int(m[1]), int(m[2]), int(m[3]))
            best = max(best or key, key)
    return f"{best[0]}차 {best[1]}.{best[2]:02d}" if best else ""


def export_file(conn, path: Path, source: str = "", user: str | None = None) -> dict:
    """지금 사전(MySQL)을 사전 파일 하나로. 다 쓴 뒤에 바꿔 넣으므로 쓰다가 실패해도 이전 파일이 남는다. 반환: dict_info."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.unlink(missing_ok=True)
    data = {}
    with conn.cursor() as cur:
        for table, (columns, order) in FILE_TABLES.items():
            data[table] = (columns, _select(cur, table, columns, order))
        if _has_table(conn, cur, EVAL_TABLE):
            data[EVAL_TABLE] = (EVAL_COLUMNS, _select(cur, EVAL_TABLE, EVAL_COLUMNS, "row_no"))
        from . import inst_db
        if _has_table(conn, cur, inst_db.INFO):   # 기관표준 (MySQL에 기관표준 테이블을 만든 뒤부터)
            data[inst_db.INFO] = (inst_db.INFO_COLUMNS, _select(cur, inst_db.INFO, inst_db.INFO_COLUMNS, "org_name"))
            for area, (table, _) in inst_db.TABLES.items():
                cols = inst_db._columns(area)
                data[table] = (cols, _select(cur, table, cols, "org_name, row_no"))
    rounds = [r[1] for r in data["common_term"][1]]
    info = {"created_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "created_by": user or getpass.getuser(),
            "source": source, "common_round": common_round(rounds),
            "counts": json.dumps({t: len(rows) for t, (_, rows) in data.items()}, ensure_ascii=False)}
    out = sqlite3.connect(temp)
    try:
        for table, (columns, rows) in data.items():
            out.execute(f"CREATE TABLE {table} ({', '.join(columns)})")
            # 정렬 열(row_no·seq, 맨 앞)은 숫자로: 글자면 '10'이 '9'보다 앞에 온다
            # 기관표준 표는 맨 앞이 기관명이라 그대로 둔다
            first = (lambda v: v) if columns[0] == "org_name" else int
            out.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(columns))})",
                            [(first(r[0]), *(_plain(v) for v in r[1:])) for r in rows])
        out.execute(f"CREATE TABLE {INFO_TABLE} (key TEXT PRIMARY KEY, value TEXT)")
        out.executemany(f"INSERT INTO {INFO_TABLE} VALUES (?, ?)", list(info.items()))
        out.commit()
    finally:
        out.close()
    os.replace(temp, path)
    return info


def dict_info(conn) -> dict:
    """사전 파일의 만든 날짜·만든 사람·공통표준 차수. MySQL이면 빈 dict."""
    if not _is_file(conn):
        return {}
    with conn.cursor() as cur:
        if not _has_table(conn, cur, INFO_TABLE):
            return {}
        cur.execute(f"SELECT key, value FROM {INFO_TABLE}")
        return dict(cur.fetchall())


def read_dict_info(path) -> dict:
    """사전 파일 하나의 dict_info (사전 파일이 아니면 빈 dict)."""
    try:
        with FileConn(path) as conn:
            return dict_info(conn)
    except sqlite3.DatabaseError:
        return {}


def dict_label(info: dict) -> str:
    """'2026-10-29 · 공통표준 8차 2025.11' (화면·리포트에 찍는 사전 버전)."""
    if not info:
        return ""
    parts = [info.get("created_at", "")[:10], info.get("common_round") and f"공통표준 {info['common_round']}"]
    return " · ".join(p for p in parts if p)


def newer_dict(folder, current: dict):
    """공유 폴더에서 지금 사전보다 나중에 만든 사전 파일. 반환: (경로, dict_info) 또는 None."""
    folder = Path(folder) if folder else None
    if not folder or not folder.is_dir():
        return None
    best = None
    for path in folder.glob("*.sqlite"):
        info = read_dict_info(path)
        if info.get("created_at", "") > current.get("created_at", "") and (
                best is None or info["created_at"] > best[1]["created_at"]):
            best = (path, info)
    return best


def install_dict(source, target) -> dict:
    """사전 파일을 사용 위치로 복사 (읽히는 사전 파일인지 먼저 확인). 반환: 새 dict_info."""
    source, target = Path(source), Path(target)
    info = read_dict_info(source)
    if not info:
        raise DbError(f"사전 파일이 아닙니다 (dict_info 없음): {source}")
    with FileConn(source) as conn:
        load_dicts(conn)
    if source.resolve() == target.resolve():
        return info
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    shutil.copyfile(source, temp)
    os.replace(temp, target)
    return info
