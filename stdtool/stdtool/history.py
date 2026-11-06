"""회차 기록: 실행할 때마다 결과 요약과 오류 목록을 사용자 폴더의 history.sqlite에 남기고, 두 회차를 비교한다.

오류 한 건은 (점검 화면, 이름, 영문약어명, 오류명)으로 남긴다. 행 번호는 보완하면 바뀌므로 비교에 쓰지 않는다.
메타 파일 내용(개인정보)은 남기지 않고 파일 이름만 남긴다.
"""
import getpass
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .core.currency import GROUPS as CURRENCY_GROUPS
from .core.precheck import group
from .model import col
from .paths import HISTORY_NAME, user_dir
from .vba import s

PROGRAM = "프로그램"
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS run (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, at TEXT, user TEXT, org TEXT, system TEXT, db_name TEXT,
        dict_version TEXT, source TEXT, folder TEXT, rate REAL, score REAL, basis TEXT, currency_rate REAL,
        summary TEXT)""",
    "CREATE TABLE IF NOT EXISTS issue (run_id INTEGER, screen TEXT, name TEXT, abbr TEXT, message TEXT)",
    "CREATE INDEX IF NOT EXISTS ix_issue_run ON issue (run_id)",
    "CREATE INDEX IF NOT EXISTS ix_run_target ON run (org, db_name)",
]


@dataclass
class Run:
    id: int
    kind: str
    at: str
    user: str
    org: str
    system: str
    db_name: str
    dict_version: str = ""
    source: str = ""                  # 메타 파일 이름 또는 통합시스템 결과 파일 이름
    folder: str = ""
    rate: float | None = None         # 표준 적용률
    score: float | None = None
    basis: str = ""
    currency_rate: float | None = None
    summary: dict = field(default_factory=dict)   # counts {점검 화면: 건수}, completeness {영역: [전체, 오류]} 등

    @property
    def counts(self) -> dict:
        return self.summary.get("counts", {})

    def total(self, kind: str) -> int:
        """화면 이름에 kind('완전성'·'준용'·'적용'·'현행화')가 든 점검의 오류 합계."""
        return sum(n for screen, n in self.counts.items() if kind in screen)


def history_path() -> Path:
    return user_dir() / HISTORY_NAME


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or history_path())
    for sql in SCHEMA:
        conn.execute(sql)
    return conn


# ---------------------------------------------------------------------------
# 실행 결과 → 오류 목록·요약
# ---------------------------------------------------------------------------

def issue_items(outcome) -> list:
    """[(점검 화면, 이름, 영문약어명, 오류명)] — 사전점검·현행화 오류 전부."""
    r = outcome.result
    out = precheck_items(r.precheck, r.domains, r.terms, r.words)
    for c in r.currency.rows:
        if c.code:
            out.append((CURRENCY_GROUPS[c.source], c.table, c.column, c.message))
    return out


def precheck_items(pre, domains, terms, words) -> list:
    """사전점검 오류 → [(점검 화면, 이름, 영문약어명, 오류명)]. 컬럼 오류는 (테이블, 영문컬럼명)."""
    sheets = {"용어": (terms, "A", "C"), "단어": (words, "A", "B"), "도메인": (domains, "C", None)}
    out = []
    for i in pre.issues:
        screen = group(i.code)
        sheet = sheets.get(i.area)
        if sheet and screen != "프로그램 추가 점검" and 0 <= i.row - 2 < len(sheet[0] or []):
            row = sheet[0][i.row - 2]
            name, abbr = s(row[col(sheet[1])]), s(row[col(sheet[2])]) if sheet[2] else ""
        elif "." in i.key and i.area in ("컬럼정의서", "메타"):
            name, abbr = i.key.split(".", 1)
        else:
            name, abbr = i.area, i.key
        out.append((screen, name, abbr, i.message))
    return out


def summary(outcome) -> dict:
    r = outcome.result
    pre, cur = r.precheck, r.currency
    return {
        "counts": dict(Counter(screen for screen, *_ in issue_items(outcome))),
        "completeness": {area: [total, errors] for area, total, errors, *_ in pre.completeness_rows()},
        "apply": [pre.total, pre.error_columns],
        "currency": [list(x) for x in cur.rates],
        "relations": sum(1 for x in outcome.relations if x.use),
        "link": len(outcome.link_list),
        "tables": len(r.definitions.tables),
        "columns": len(r.definitions.columns),
    }


def record(outcome, settings, path: Path | None = None, user: str | None = None) -> int:
    """프로그램 실행 한 번을 회차로 남긴다. 반환: 회차 id."""
    pre, cur = outcome.result.precheck, outcome.result.currency
    with connect(path) as conn:
        run_id = conn.execute(
            "INSERT INTO run (kind, at, user, org, system, db_name, dict_version, source, folder, rate, score, basis,"
            " currency_rate, summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (PROGRAM, _now(), user or getpass.getuser(), settings.org_name, settings.system_name or settings.db_name,
             settings.db_name, outcome.dict_version, Path(settings.meta).name if settings.meta else "",
             str(outcome.folder), pre.rate, pre.score, pre.basis, cur.rate,
             json.dumps(summary(outcome), ensure_ascii=False))).lastrowid
        conn.executemany("INSERT INTO issue VALUES (?, ?, ?, ?, ?)", [(run_id, *x) for x in issue_items(outcome)])
    return run_id


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# 읽기·비교
# ---------------------------------------------------------------------------

_RUN_COLUMNS = ["id", "kind", "at", "user", "org", "system", "db_name", "dict_version", "source", "folder", "rate",
                "score", "basis", "currency_rate", "summary"]


def runs(org: str, db_name: str, path: Path | None = None, kind: str | None = None) -> list:
    """그 시스템의 회차들, 최근 것부터."""
    sql = f"SELECT {', '.join(_RUN_COLUMNS)} FROM run WHERE org = ? AND db_name = ?"
    params = [org, db_name]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    with connect(path) as conn:
        rows = conn.execute(sql + " ORDER BY id DESC", params).fetchall()
    out = []
    for r in rows:
        data = dict(zip(_RUN_COLUMNS, r))
        data["summary"] = json.loads(data["summary"] or "{}")
        out.append(Run(**data))
    return out


def items(run_id: int, path: Path | None = None) -> list:
    with connect(path) as conn:
        return [tuple(r) for r in conn.execute("SELECT screen, name, abbr, message FROM issue WHERE run_id = ?"
                                               " ORDER BY rowid", (run_id,))]


def delete(run_id: int, path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.execute("DELETE FROM issue WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM run WHERE id = ?", (run_id,))


def _key(item) -> tuple:
    screen, name, abbr, message = item
    return screen, s(name).upper(), s(abbr).upper(), message


def compare(old: list, new: list) -> tuple:
    """(고쳐진 오류, 새로 생긴 오류, 그대로인 오류). 같은 오류가 여러 건이면 건수만큼 맞춘다."""
    before, after = Counter(map(_key, old)), Counter(map(_key, new))
    fixed, added, kept = [], [], []
    seen_old, seen_new = Counter(), Counter()
    for item in old:
        k = _key(item)
        seen_old[k] += 1
        (kept if seen_old[k] <= after[k] else fixed).append(item)
    for item in new:
        k = _key(item)
        seen_new[k] += 1
        if seen_new[k] > before[k]:
            added.append(item)
    return fixed, added, kept


def change_text(old: Run, new: Run) -> list:
    """두 회차 지표 변화 한 줄씩: [(지표, 이전, 이후)]."""
    def pct(v):
        return "" if v is None else f"{v:.1f}%"
    rows = [("표준 적용률", pct(old.rate), pct(new.rate)), ("구조 현행화율", pct(old.currency_rate), pct(new.currency_rate))]
    for kind in ("완전성", "준용", "적용", "현행화"):
        rows.append((f"{kind} 오류", f"{old.total(kind):,}", f"{new.total(kind):,}"))
    return rows


def write_log(folder: Path, org: str, db_name: str, run_id: int, path: Path | None = None) -> Path:
    """산출물 폴더에 실행기록.xlsx: '회차' 시트(그 시스템의 모든 회차), '오류' 시트(이번 회차 오류 목록)."""
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "회차"
    ws.append(["회차", "구분", "일시", "실행자", "표준 사전", "입력 파일", "표준 적용률", "점수", "구조 현행화율",
               "완전성 오류", "준용 오류", "적용 오류", "현행화 오류", "산출물 폴더"])
    for r in runs(org, db_name, path):
        ws.append([r.id, r.kind, r.at, r.user, r.dict_version, r.source,
                   None if r.rate is None else round(r.rate, 1), r.score,
                   None if r.currency_rate is None else round(r.currency_rate, 1),
                   r.total("완전성"), r.total("준용"), r.total("적용"), r.total("현행화"), r.folder])
    errors = wb.create_sheet("오류")
    errors.append(["점검 화면", "이름", "영문약어명", "오류명"])
    for item in items(run_id, path):
        errors.append(list(item))
    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
    out = Path(folder) / "실행기록.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
