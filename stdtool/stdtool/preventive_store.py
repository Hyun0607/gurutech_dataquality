"""예방적 품질관리 기록: 읽은 사업단 대상 파일(회차별)과 사람이 고친 유형·금액·이관을 history.sqlite에 남긴다.

같은 평가연도·회차를 다시 읽으면 그 회차를 바꿔 쓴다. 고친 값은 사업(기관명·사업명) 기준이라 회차가 바뀌어도 이어진다.
"""
import json
import sqlite3
from datetime import date, datetime

from .core.preventive import DONE, Edit, Project
from .history import history_path

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS pqc_project (
        year INTEGER, round INTEGER, stage TEXT, org_type TEXT, org TEXT, code TEXT, name TEXT,
        start TEXT, end TEXT, applied TEXT, note TEXT, source TEXT, read_at TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_pqc_round ON pqc_project (year, round)",
    """CREATE TABLE IF NOT EXISTS pqc_check (
        org_key TEXT, name_key TEXT, kind TEXT, year INTEGER, round INTEGER, at TEXT, data TEXT,
        PRIMARY KEY (org_key, name_key, kind, year, round))""",
    "CREATE TABLE IF NOT EXISTS pqc_meta (key TEXT PRIMARY KEY, value TEXT)",
    """CREATE TABLE IF NOT EXISTS pqc_edit (
        org_key TEXT, name_key TEXT, types TEXT, amount INTEGER, transfer TEXT, at TEXT,
        PRIMARY KEY (org_key, name_key))""",
]


def connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or history_path())
    for sql in SCHEMA:
        conn.execute(sql)
    return conn


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _day(text) -> date | None:
    return date.fromisoformat(text) if text else None


def save_round(projects: list, source: str, path=None) -> None:
    """읽은 파일의 (평가연도, 회차)를 통째로 바꿔 쓴다."""
    now = date.today().isoformat()
    with connect(path) as conn:
        for year, no in {(p.year, p.round) for p in projects}:
            conn.execute("DELETE FROM pqc_project WHERE year = ? AND round = ?", (year, no))
        conn.executemany("INSERT INTO pqc_project VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         [(p.year, p.round, p.stage, p.org_type, p.org, p.code, p.name, _iso(p.start), _iso(p.end),
                           _iso(p.applied), p.note, source, now) for p in projects])


def rounds(path=None) -> list:
    """[(평가연도, 회차, 사업 수, 파일 이름)] 오래된 것부터."""
    with connect(path) as conn:
        return conn.execute("SELECT year, round, COUNT(*), MAX(source) FROM pqc_project GROUP BY year, round "
                            "ORDER BY year, round").fetchall()


def load_round(year: int, no: int, path=None) -> list:
    with connect(path) as conn:
        rows = conn.execute("SELECT year, round, stage, org_type, org, code, name, start, end, applied, note "
                            "FROM pqc_project WHERE year = ? AND round = ? ORDER BY rowid", (year, no)).fetchall()
    return [Project(r[0], r[1], r[2], r[3], r[4], r[5], r[6], _day(r[7]), _day(r[8]), _day(r[9]), r[10]) for r in rows]


def earlier(projects: list, path=None) -> tuple:
    """지금 읽은 회차보다 앞선 기록 → ({사업 키: 마지막으로 나온 단계 표시}, 완료단계 사업 키 집합)."""
    if not projects:
        return {}, set()
    now = max((p.year, p.round) for p in projects)
    previous, done = {}, set()
    for year, no, _, _ in rounds(path):
        if (year, no) >= now:
            continue
        for p in load_round(year, no, path):
            previous[p.key] = f"{p.year} {p.stage_label}"
            if p.stage == DONE:
                done.add(p.key)
    return previous, done


def load_edits(path=None) -> dict:
    with connect(path) as conn:
        rows = conn.execute("SELECT org_key, name_key, types, amount, transfer FROM pqc_edit").fetchall()
    return {(r[0], r[1]): Edit(r[2] or "", r[3], r[4] or "") for r in rows}


def save_edit(key: tuple, edit: Edit, path=None) -> None:
    with connect(path) as conn:
        if not (edit.types or edit.amount or edit.transfer):
            conn.execute("DELETE FROM pqc_edit WHERE org_key = ? AND name_key = ?", key)
            return
        conn.execute("INSERT OR REPLACE INTO pqc_edit VALUES (?,?,?,?,?,?)",
                     (*key, edit.types, edit.amount, edit.transfer, date.today().isoformat()))


def save_check(record: dict, path=None) -> None:
    """발주·완료단계 점검 한 건 (같은 사업·단계·회차는 바꿔 쓴다). record는 workbook.preventive_report.check_record."""
    key = (record["org_key"], record["name_key"], record["kind"], record["year"], record["round"])
    with connect(path) as conn:
        conn.execute("INSERT OR REPLACE INTO pqc_check VALUES (?,?,?,?,?,?,?)",
                     (*key, datetime.now().isoformat(timespec="seconds"), json.dumps(record, ensure_ascii=False)))


def load_checks(org_key: str, year: int, path=None) -> list:
    """한 기관의 그 평가연도 점검 기록 전부 — 발주·완료, 회차가 달라도 (사업별로 발주 → 완료, 회차 순)."""
    with connect(path) as conn:
        rows = conn.execute("SELECT data FROM pqc_check WHERE org_key = ? AND year = ? ORDER BY at",
                            (org_key, year)).fetchall()
    records = [json.loads(r[0]) for r in rows]
    first = {}
    for i, r in enumerate(records):   # 사업은 처음 점검한 순서, 한 사업 안에서는 발주 → 완료
        first.setdefault(r["name_key"], i)
    return sorted(records, key=lambda r: (first[r["name_key"]], r["kind"] != "발주", r["round"]))


def remember(key: str, value: str, path=None) -> None:
    """화면 상태 하나 (마지막으로 읽은 대상 파일 등)."""
    with connect(path) as conn:
        conn.execute("INSERT OR REPLACE INTO pqc_meta VALUES (?, ?)", (key, value))


def recall(key: str, path=None) -> str:
    with connect(path) as conn:
        row = conn.execute("SELECT value FROM pqc_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else ""
