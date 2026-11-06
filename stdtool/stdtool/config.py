"""설정 파일(TOML). 매크로 RAW!H4~K4 고정 셀과 바탕화면 고정 경로를 대신한다."""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# 길이 누락을 도메인 완전성 오류로 보는 타입 (세부 안내서 p.76: DATE·BLOB·CLOB·LONGTEXT·POINT·MULTIPOINT·NUMERIC은 제외)
DEFAULT_LENGTH_REQUIRED = ["CHAR", "VARCHAR", "VARCHAR2", "NCHAR", "NVARCHAR", "NUMBER"]

# Code_type에서 약어가 겹치는 타입: NAME·NUMBER = NM, CHAR·CHARACTER = CH → 도메인명이 겹쳐 D03(도메인명 중복)
DEFAULT_TYPE_ABBR_OVERRIDE = {"NAME": "NAM", "CHARACTER": "CHR"}

DEFAULT_TYPE_ALIAS = {"POSTGRESQL": {"CHAR": "CHARACTER", "VARCHAR": "CHARACTER VARYING"}}

# 영문 접미어로 분류를 못 찾을 때 한글 컬럼명 끝말로 보조 판정 (분류명은 Code_tail 분류와 같게)
DEFAULT_KOREAN_SUFFIX = {
    "설명": "내용", "내용": "내용", "명칭": "명칭", "명": "명칭", "주소": "주소",
    "금액": "금액", "수수료": "수수료", "건수": "건수", "수량": "수량", "합계": "합계", "평균": "평균",
    "비율": "율", "율": "율", "면적": "면적", "길이": "길이", "크기": "크기",
    "코드": "코드", "유형": "유형", "여부": "여부", "등급": "등급", "구분": "구분",
    "일련번호": "순번", "순번": "순번", "우편번호": "우편번호", "번호": "번호", "아이디": "ID", "ID": "ID",
    "년월일": "년월일", "연월일": "년월일", "년월": "년월", "연월": "년월", "일자": "일자", "일시": "날짜", "시간": "시간",
}


@dataclass
class DbSettings:
    """표준 사전 DB: 사전 파일(SQLite) 또는 MySQL. MySQL 비밀번호는 설정 파일에 두지 않는다."""
    use: bool = False                  # true면 매크로 파일·공통표준 원본 대신 DB에서 사전을 읽는다
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    database: str = "std_dict"
    file: str = ""                     # 사전 파일 경로. 있으면 MySQL 대신 이 파일을 읽는다


@dataclass
class Settings:
    org_name: str = ""
    db_name: str = ""                  # 산출물 파일 이름에 쓰는 DB명 (매크로 RAW!K4)
    system_name: str = ""              # 평가대상 목록의 정보시스템명 (연계 관리현황의 연계시스템명 기본값)
    db_eng_name: str = ""              # 평가대상 목록의 영문 DB명 (연계 목록 정의서의 DB명 기본값)
    enact_date: object = None          # 제정일자 (RAW!H4)
    inst_std: str = "N"                # 기관표준여부 Y/N (RAW!I4)
    output_dir: Path = Path("output")
    macro_workbook: Path | None = None # 공통표준·기관표준·Code_type·Code_tail 시트를 읽을 매크로 파일
    meta: Path | None = None
    meta_sheet: str = ""
    db: DbSettings = field(default_factory=DbSettings)
    enhanced: bool = True
    # ① 도메인 사전
    parse_type_length: bool = True
    scale_separator: str = "_"
    length_policy: dict = field(default_factory=lambda: {"NUMBER": 38})
    type_extra: dict = field(default_factory=dict)       # {"타입": "약어"}
    # 같은 타입의 다른 표기 → DBMS 공식 표기 (DB 컬럼 목록이 보여 주는 이름). 메타 R열 DBMS 종류로 고른다
    type_alias: dict = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_TYPE_ALIAS.items()})
    # NM은 NUMBER, CH는 CHAR가 쓴다 (NAME→NAM, CHARACTER→CHR)
    type_abbr_override: dict = field(default_factory=lambda: dict(DEFAULT_TYPE_ABBR_OVERRIDE))
    korean_class: bool = True
    korean_suffix: dict = field(default_factory=lambda: dict(DEFAULT_KOREAN_SUFFIX))
    domain_pool: list = field(default_factory=list)      # 재사용할 DB표준도메인/공통표준도메인 파일
    ensure_term_domains: bool = True
    # ② 공통표준 유의어·금칙어 (공통표준 원본 파일)
    common_term: Path | None = None
    common_word: Path | None = None
    common_domain: Path | None = None
    # 치환 권고를 검토 파일 없이도 적용할지. 끄면 ②는 사전점검(기준1)에서 알려 주기만 한다.
    # 기본 끔: 치환하면 실제 DB 컬럼명·타입과 정의서가 달라진다 (목재정보서비스 시스템 등록본과 대조, 98개 컬럼)
    synonym_auto_apply: bool = False
    synonym_top: int = 3
    synonym_min_score: float = 0.5
    synonym_review: Path | None = None  # 사람이 고친 검토 파일 (표준매핑_*.xlsx)
    fill_words_from_common: bool = True
    # ③ 사전점검
    length_required_types: list = field(default_factory=lambda: list(DEFAULT_LENGTH_REQUIRED))
    manual_chunk_size: int = 5000
    # 연계 (2-1-5-1 목록 정의서, 2-1-5-2 관리현황)
    link_enabled: bool = True
    link_direction: str = "송신"
    link_cycle: str = "실시간"
    link_user_org: str = ""            # 활용기관 (비우면 기관명)
    link_result: str = "오류 없음"
    link_action: str = "수시 점검 기조 유지"
    link_method: str = ""              # 점검 방법 (비우면 빈칸)
    link_start: str = "06-01"          # 점검 일시 시작 (올해 MM-DD) ~ 실행한 날
    link_review: Path | None = None    # 선택(Y/N)을 고친 연계후보 파일


def load_settings(path: Path | None) -> Settings:
    settings = Settings()
    if path is None:
        return settings
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    base = Path(path).resolve().parent

    def as_path(value):
        if not value:
            return None
        p = Path(value)
        return p if p.is_absolute() else base / p

    project = data.get("project", {})
    settings.org_name = project.get("org_name", settings.org_name)
    settings.db_name = project.get("db_name", settings.db_name)
    settings.enact_date = project.get("enact_date", settings.enact_date)
    settings.inst_std = str(project.get("inst_std", settings.inst_std)).upper()
    settings.output_dir = as_path(project.get("output_dir")) or base / "output"

    source = data.get("source", {})
    settings.macro_workbook = as_path(source.get("macro_workbook"))
    settings.meta = as_path(source.get("meta"))
    settings.meta_sheet = source.get("meta_sheet", "")

    db = data.get("db", {})
    settings.db = DbSettings(use=db.get("use", False), host=db.get("host", "localhost"), port=int(db.get("port", 3306)),
                             user=db.get("user", "root"), database=db.get("database", "std_dict"),
                             file=str(as_path(db.get("file")) or ""))

    settings.enhanced = data.get("mode", {}).get("enhanced", settings.enhanced)

    domain = data.get("domain", {})
    settings.parse_type_length = domain.get("parse_type_length", settings.parse_type_length)
    settings.scale_separator = domain.get("scale_separator", settings.scale_separator)
    settings.length_policy = {k.upper(): v for k, v in domain.get("length_policy", settings.length_policy).items()}
    settings.type_extra = {k.upper(): v for k, v in domain.get("type_extra", {}).items()}
    settings.type_abbr_override.update({k.upper(): v for k, v in domain.get("type_abbr_override", {}).items()})
    for dbms, table in domain.get("type_alias", {}).items():     # [domain.type_alias.POSTGRESQL] CHAR = "CHARACTER"
        settings.type_alias.setdefault(dbms.upper(), {}).update({k.upper(): v.upper() for k, v in table.items()})
    settings.korean_class = domain.get("korean_class", settings.korean_class)
    settings.korean_suffix.update(domain.get("korean_suffix", {}))
    settings.domain_pool = [as_path(p) for p in domain.get("pool", [])]
    settings.ensure_term_domains = domain.get("ensure_term_domains", settings.ensure_term_domains)

    common = data.get("common_standard", {})
    settings.common_term = as_path(common.get("term"))
    settings.common_word = as_path(common.get("word"))
    settings.common_domain = as_path(common.get("domain"))
    synonym = data.get("synonym", {})
    settings.synonym_auto_apply = synonym.get("auto_apply", settings.synonym_auto_apply)
    settings.synonym_top = synonym.get("top", settings.synonym_top)
    settings.synonym_min_score = synonym.get("min_score", settings.synonym_min_score)
    settings.synonym_review = as_path(synonym.get("review"))
    settings.fill_words_from_common = synonym.get("fill_words", settings.fill_words_from_common)

    precheck = data.get("precheck", {})
    settings.length_required_types = [t.upper() for t in precheck.get("length_required_types", settings.length_required_types)]
    settings.manual_chunk_size = data.get("manual", {}).get("chunk_size", settings.manual_chunk_size)

    link = data.get("link", {})
    settings.link_enabled = link.get("enabled", settings.link_enabled)
    settings.link_direction = link.get("direction", settings.link_direction)
    settings.link_cycle = link.get("cycle", settings.link_cycle)
    settings.link_user_org = link.get("user_org", settings.link_user_org)
    settings.link_result = link.get("result", settings.link_result)
    settings.link_action = link.get("action", settings.link_action)
    settings.link_method = link.get("method", settings.link_method)
    settings.link_start = link.get("start", settings.link_start)
    settings.link_review = as_path(link.get("review"))
    return settings
