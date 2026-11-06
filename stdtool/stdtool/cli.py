"""명령줄 실행.

  stdtool run   --config config.toml [--meta 메타.xlsx] [--review 표준매핑_검토.xlsx] [--macro-mode]
  stdtool check --folder 산출물폴더 [--manual 수동등록.xlsx ...] [--config config.toml] [--out 리포트.xlsx]
  stdtool make-templates --macro 매크로.xlsm
  stdtool db export --config config.toml --out std_dict.sqlite
  stdtool db import --config config.toml [--macro 매크로.xlsm] [--common-dir 공통표준폴더] [--only macro|common] [--replace-codes] [--eval-list 평가대상DB리스트.xlsx]
  stdtool db status --config config.toml
"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import db
from .config import load_settings
from .core.precheck import CODES, code_label, run_precheck, severity
from .pipeline import build_matcher
from .workbook.reader import read_meta_columns, read_output_folder
from .workbook.writer import write_currency_report, write_precheck_report


def _print_precheck(result):
    print(f"  적용률 산정 기준 : {result.basis}")
    print(f"  전체/오류 컬럼   : {result.total} / {result.error_columns}")
    print(f"  예상 적용률      : {result.rate:.1f}%  (배점 {result.score})")
    for area, total, errors, _, verdict in result.completeness_rows():
        print(f"  {area} 완전성 : {total}건 중 오류 {errors}건 ({verdict})")
    for code in CODES:
        n = result.count(code)
        if n:
            print(f"    {code_label(code)} {CODES[code]}: {n}  [{severity(code)}]")


def _print_currency(result):
    from .core.currency import CODES as CURRENCY_CODES, code_label as currency_label
    for name, matched, total, rate in result.rates:
        print(f"  {name}: {matched} / {total}  ({rate:.1f}%)")
    print(f"  구조 산출물 현행화율 : {result.rate:.1f}%  (배점 {result.score})")
    for code, message in CURRENCY_CODES.items():
        if result.count(code):
            print(f"    {currency_label(code)} {message}: {result.count(code)}")


def cmd_run(args):
    from .service import RunError, execute
    settings = load_settings(Path(args.config))
    if args.meta:
        settings.meta = Path(args.meta)
    if args.macro_mode:
        settings.enhanced = False
    if args.review:
        settings.synonym_review = Path(args.review)
    started = time.time()
    try:
        out = execute(settings, print, Path(args.link_review) if args.link_review else None)
    except RunError as e:
        sys.exit(str(e))
    result = out.result
    for p in out.paths:
        print(f"  - {p}")
    if out.candidates and not (args.link_review or settings.link_review):
        print("      (연계는 추천대로 골랐습니다. 연계후보 파일의 선택을 고쳐 --link-review 로 다시 실행)")
    if out.fallback:
        print(f"Code_tail에 꼬리가 없어 '문자값'으로 분류된 컬럼: {sum(r[1] for r in out.fallback)}개 (꼬리 {len(out.fallback)}종)"
              f" → 변경이력 '문자값 분류' 시트")
        for r in out.fallback[:5]:
            print(f"    {r[0]}: {r[1]}개  예) {r[2][:30]}" + (f"  [공통표준단어 {r[4]}]" if r[4] else ""))
    if result.synonym_results:
        _print_mapping(result.synonym_results)
    print("사전점검 결과")
    _print_precheck(result.precheck)
    print("구조 현행화 검증 (정의서 ↔ 수동등록)")
    _print_currency(result.currency)
    print(f"완료 ({time.time() - started:.0f}초)")


def _connect(settings):
    try:
        return db.connect(settings.db)
    except db.DbError as e:
        sys.exit(str(e))


def _load_common(settings):
    from .service import load_common
    try:
        return load_common(settings)
    except db.DbError as e:
        sys.exit(str(e))


def _print_mapping(results):
    from collections import Counter
    counts = Counter(r.category for r in results)
    print("② 공통표준 매핑 (한글·영문 쌍 기준)")
    for category, n in counts.most_common():
        print(f"    {category}: {n}")
    print(f"    치환 적용: {sum(1 for r in results if r.confirmed)}  /  금칙어 사용: {sum(1 for r in results if r.forbidden)}")


def cmd_check(args):
    overrides = {"domains": args.domain, "terms": args.term, "words": args.word, "columns": args.column}
    data = read_output_folder(args.folder, overrides)
    missing = [k for k in ("domains", "terms", "columns") if k not in data]
    if missing:
        sys.exit(f"산출물 파일을 찾지 못했습니다: {missing}")
    for key, path in data["_files"].items():
        print(f"  {key}: {path.name}")
    meta = read_meta_columns([Path(p) for p in args.manual]) if args.manual else None
    settings = load_settings(Path(args.config)) if args.config else None
    required = settings.length_required_types if settings else None
    common = _load_common(settings) if settings else None
    matcher = build_matcher(common, settings) if settings else None
    result = run_precheck(data["domains"], data["terms"], data.get("words"), data["columns"], meta, required, matcher,
                          common.domains if common else None)
    out = Path(args.out) if args.out else Path(args.folder) / "사전점검.xlsx"
    write_precheck_report(result, out, f"{Path(args.folder).name} 사전점검",
                          (data["domains"], data["terms"], data.get("words") or []))
    _print_precheck(result)
    print(f"리포트: {out}")
    if meta is not None:
        from .core.currency import run_currency
        currency = run_currency(data.get("tables", []), data["columns"], meta)
        currency_out = out.with_name(f"구조현행화_{out.stem}.xlsx")
        write_currency_report(currency, currency_out, f"{Path(args.folder).name} 구조 현행화 검증")
        print("구조 현행화 검증 (정의서 ↔ 수동등록)")
        _print_currency(currency)
        print(f"리포트: {currency_out}")


def cmd_make_templates(args):
    from .workbook.templates import make_templates
    for p in make_templates(Path(args.macro)):
        print(f"  - {p}")


def cmd_db_import(args):
    settings = load_settings(Path(args.config))
    macro = Path(args.macro) if args.macro else settings.macro_workbook
    if args.common_dir:
        common = {t: Path(args.common_dir) / f for t, f in db.COMMON_FILES.items()}
    else:
        common = {"common_term": settings.common_term, "common_word": settings.common_word,
                  "common_domain": settings.common_domain}
    jobs = []
    if args.eval_list:
        path = Path(args.eval_list)
        jobs.append(("평가대상 DB 목록", path, lambda conn: {db.EVAL_TABLE: db.import_eval_list(conn, path)}))
        if args.only is None:
            args.only = "none"   # 목록만 지정하면 목록만 가져온다
    if args.only in (None, "macro"):
        if not macro:
            sys.exit("매크로 파일이 필요합니다 (--macro 또는 설정 source.macro_workbook).")
        jobs.append(("매크로 사전", macro, lambda conn: db.import_macro(conn, macro, args.replace_codes)))
    if args.only in (None, "common"):
        missing = [t for t, p in common.items() if not p or not Path(p).exists()]
        if missing:
            sys.exit(f"공통표준 원본 파일이 없습니다: {missing} (--common-dir 또는 설정 [common_standard])")
        jobs.append(("공통표준 원본", Path(common["common_term"]).parent, lambda conn: db.import_common(conn, common)))
    with _connect(settings) as conn:
        for title, source, job in jobs:
            print(f"{title} 가져오기: {source}")
            for table, n in job(conn).items():
                print(f"  {table}: {n}")
    print("완료")


def cmd_db_status(args):
    settings = load_settings(Path(args.config))
    with _connect(settings) as conn:
        for table, n in db.status(conn).items():
            print(f"  {table}: {n}")


def cmd_db_export(args):
    settings = load_settings(Path(args.config))
    if settings.db.file:
        sys.exit("설정 [db] file 이 사전 파일을 가리킵니다. 사전 파일은 MySQL에서 만듭니다 (file 을 비우세요).")
    with _connect(settings) as conn:
        d = settings.db
        info = db.export_file(conn, Path(args.out), f"MySQL {d.host}:{d.port}/{d.database}")
    print(f"사전 파일: {args.out}")
    print(f"  {db.dict_label(info)} · 만든 사람 {info['created_by']}")
    for table, n in json.loads(info["counts"]).items():
        print(f"  {table}: {n}")


def _read_insts(args):
    """기관표준 폴더들 → [InstStandard]. 기관명은 평가대상 목록의 이름으로 맞춘다 (예: 계룡시 → 충청남도 계룡시)."""
    from . import inst_db
    from .paths import BUNDLED_DICT
    from .workbook.inst_reader import read_inst
    entries = []
    source = Path(args.dict) if getattr(args, "dict", None) else BUNDLED_DICT
    if source.exists():
        with db.FileConn(source) as conn:
            entries = db.load_eval_list(conn)
    insts = []
    for folder in args.folders:
        inst = read_inst([folder], args.org if len(args.folders) == 1 and args.org else "")
        match = next((e["org"] for e in entries if e["org"] == inst.org), None) or next(
            (e["org"] for e in entries if inst_db.same_org(e["org"], inst.org)), None)
        if match and match != inst.org:
            print(f"  기관명 {inst.org} → 평가대상 목록의 '{match}'")
            inst.org = match
        elif not match:
            print(f"  [주의] '{inst.org}'은(는) 평가대상 목록에 없습니다. --org 로 목록의 기관명을 주세요.")
        print(f"  {inst.org} · {inst.source} · " + " · ".join(f"{a} {n:,}" for a, n in inst.counts.items()))
        insts.append(inst)
    return insts


def cmd_db_inst_sql(args):
    from . import inst_db
    insts = _read_insts(args)
    out = Path(args.out)
    out.write_text(inst_db.inst_sql(insts, with_ddl=not args.no_ddl), encoding="utf-8")
    print(f"DBeaver 스크립트: {out}")


def cmd_db_inst_import(args):
    from . import inst_db
    insts = _read_insts(args)
    if args.file:
        conn = db.FileConn(args.file)
    else:
        conn = _connect(load_settings(Path(args.config)))
    with conn:
        for inst in insts:
            inst_db.import_inst(conn, inst)
        if args.file:
            inst_db.touch_file_info(conn, f"기관표준 {', '.join(i.org for i in insts)}")
    print("완료")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="stdtool", description="표준화 점검 프로그램")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("run", help="메타 → DB표준·정의서·수동등록 + 사전점검")
    p.add_argument("--config", required=True)
    p.add_argument("--meta", help="메타 양식 파일 (설정 source.meta 대신)")
    p.add_argument("--macro-mode", action="store_true", help="고도화 없이 매크로와 같게 실행")
    p.add_argument("--review", help="확정(Y/N)을 고친 표준매핑 검토 파일")
    p.add_argument("--link-review", help="선택(Y/N)을 고친 연계후보 파일")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("check", help="이미 만든 산출물 폴더를 사전점검")
    p.add_argument("--folder", required=True)
    p.add_argument("--manual", nargs="*", default=[], help="수동등록(또는 메타 양식) 파일. 있으면 메타 기준 적용률")
    p.add_argument("--domain", help="도메인 파일 직접 지정 (예: 수정_DB표준도메인_...xlsx)")
    p.add_argument("--term")
    p.add_argument("--word")
    p.add_argument("--column")
    p.add_argument("--config")
    p.add_argument("--out")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("make-templates", help="매크로 파일에서 산출물 양식 추출 (1회)")
    p.add_argument("--macro", required=True)
    p.set_defaults(func=cmd_make_templates)

    p = sub.add_parser("db", help="표준 사전 DB (MySQL)")
    dbsub = p.add_subparsers(required=True)
    q = dbsub.add_parser("import", help="매크로 사전 시트·공통표준 원본을 DB에 넣기 (기존 내용은 바꿈)")
    q.add_argument("--config", required=True)
    q.add_argument("--macro", help="매크로 파일 (설정 source.macro_workbook 대신)")
    q.add_argument("--common-dir", help="공통표준용어·단어·도메인.xlsx 가 있는 폴더 (설정 [common_standard] 대신)")
    q.add_argument("--only", choices=["macro", "common"], help="한쪽만 가져오기")
    q.add_argument("--eval-list", help="전체 평가대상 DB리스트.xlsx (기관·시스템 목록, 이것만 지정하면 목록만 가져옴)")
    q.add_argument("--replace-codes", action="store_true",
                   help="Code_type·Code_tail의 매크로 행도 다시 넣기 (직접 추가한 행은 그대로 둠)")
    q.set_defaults(func=cmd_db_import)
    q = dbsub.add_parser("status", help="DB 테이블별 행 수")
    q.add_argument("--config", required=True)
    q.set_defaults(func=cmd_db_status)
    q = dbsub.add_parser("export", help="MySQL 사전을 사전 파일(팀원 배포용 SQLite) 하나로 만들기")
    q.add_argument("--config", required=True)
    q.add_argument("--out", required=True, help="만들 사전 파일 (예: std_dict.sqlite)")
    q.set_defaults(func=cmd_db_export)

    for name, helptext, func in (("inst-sql", "기관표준 폴더 → DBeaver에서 실행할 MySQL 스크립트", cmd_db_inst_sql),
                                 ("inst-import", "기관표준 폴더 → DB(MySQL 또는 --file 사전 파일)에 넣기 (그 기관만 바꿈)",
                                  cmd_db_inst_import)):
        q = dbsub.add_parser(name, help=helptext)
        q.add_argument("folders", nargs="+", help="기관표준 용어·단어·도메인·코드 xlsx가 있는 폴더 (기관마다 하나)")
        q.add_argument("--org", help="기관명 (폴더가 하나일 때, 평가대상 목록의 기관명)")
        q.add_argument("--dict", help="기관명을 맞출 평가대상 목록이 든 사전 파일 (기본: 프로그램에 넣은 사전)")
        if name == "inst-sql":
            q.add_argument("--out", required=True, help="만들 .sql 파일")
            q.add_argument("--no-ddl", action="store_true", help="테이블 만들기(CREATE TABLE) 없이 데이터만")
        else:
            q.add_argument("--config", help="MySQL 설정 (--file 이 없을 때)")
            q.add_argument("--file", help="사전 파일(SQLite)에 넣기")
        q.set_defaults(func=func)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
