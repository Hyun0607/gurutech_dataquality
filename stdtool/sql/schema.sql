-- stdtool 표준 사전 DB (MySQL 5.7 / 8.0)
-- DBeaver: 이 파일을 SQL 편집기로 열고 '스크립트 실행'(Alt+X)
--
-- 글자 비교는 utf8mb4_bin: 대소문자를 구분해야 매크로와 같은 결과가 나온다 (예: NM 과 nm 을 다르게).
-- 버전 관리는 하지 않는다: 새 공통표준·매크로 사전이 나오면 프로그램이 테이블 내용을 통째로 바꾼다.
-- 기관표준은 맨 아래 inst_* 테이블 (한 DB 안에 기관명 열로 나눔). 데이터는 stdtool db inst-sql 로 만든 스크립트로 넣는다.

CREATE DATABASE IF NOT EXISTS std_dict CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
-- 아래 테이블은 모두 std_dict. 를 붙여 만들므로 USE 없이도 된다

-- ---------------------------------------------------------------------------
-- 매크로 방식에 쓰는 사전 (매크로 파일 시트를 행 순서까지 그대로)
-- ---------------------------------------------------------------------------

-- 매크로 '공통표준' 시트. 같은 이름이 여러 번이면 매크로는 마지막 행을 쓰므로 row_no 순서가 중요하다.
CREATE TABLE IF NOT EXISTS std_dict.macro_common (
  row_no      INT          NOT NULL PRIMARY KEY COMMENT '시트 행 번호',
  kor_name    VARCHAR(200) COMMENT '한글 컬럼명',
  eng_name    VARCHAR(200) COMMENT '영문 컬럼명',
  data_type   VARCHAR(50)  COMMENT '데이터 타입',
  data_length VARCHAR(20)  COMMENT '데이터 길이 (시트 값 그대로)',
  KEY ix_macro_kor (kor_name),
  KEY ix_macro_eng (eng_name)
) COMMENT '매크로 공통표준 시트';

-- 매크로 Code_type. seq 순서가 찾는 순서(위에서부터 처음 맞는 행).
CREATE TABLE IF NOT EXISTS std_dict.code_type (
  seq        INT          NOT NULL PRIMARY KEY COMMENT '순번',
  type_name  VARCHAR(100) NOT NULL COMMENT '데이터 타입',
  type_abbr  VARCHAR(20)  NOT NULL COMMENT '데이터 약어',
  type_class VARCHAR(50)           COMMENT '데이터 분류',
  added_by   VARCHAR(50)           COMMENT '추가한 사람 (매크로에서 가져온 행은 MACRO)',
  added_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  note       VARCHAR(200),
  KEY ix_type_name (type_name)
) COMMENT '매크로 Code_type: 타입 → 약어';

-- 매크로 Code_tail. seq 순서가 찾는 순서.
CREATE TABLE IF NOT EXISTS std_dict.code_tail (
  seq              INT         NOT NULL PRIMARY KEY COMMENT '순번',
  tail             VARCHAR(50) NOT NULL COMMENT '도메인자르기 (영문컬럼명 마지막 _ 뒤)',
  domain_class     VARCHAR(50) NOT NULL COMMENT '도메인분류',
  domain_mid_class VARCHAR(50)          COMMENT '도메인중분류',
  added_by         VARCHAR(50)          COMMENT '추가한 사람 (매크로에서 가져온 행은 MACRO)',
  added_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  note             VARCHAR(200),
  KEY ix_tail (tail)
) COMMENT '매크로 Code_tail: 영문 접미어 → 도메인 분류';

-- ---------------------------------------------------------------------------
-- 고도화 방식에 쓰는 공통표준 원본 (행정안전부 배포 파일 열 그대로, 최신 차수만)
-- 이음동의어·금칙어 목록은 원본처럼 쉼표로 이어진 문자열로 둔다.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS std_dict.common_term (
  row_no         INT          NOT NULL PRIMARY KEY COMMENT '원본 행 번호',
  enact_round    VARCHAR(50)  COMMENT '제정차수',
  term_name      VARCHAR(200) NOT NULL COMMENT '공통표준용어명',
  description    TEXT         COMMENT '공통표준용어 설명',
  term_abbr      VARCHAR(200) NOT NULL COMMENT '공통표준용어영문약어명',
  domain_name    VARCHAR(100) COMMENT '공통표준도메인명',
  allowed_value  TEXT         COMMENT '허용값',
  storage_format VARCHAR(500) COMMENT '저장형식',
  display_format VARCHAR(500) COMMENT '표현형식',
  code_name      VARCHAR(200) COMMENT '행정표준코드명',
  owner_org      VARCHAR(200) COMMENT '소관 기관명',
  synonyms       TEXT         COMMENT '용어 이음동의어 목록 (쉼표 구분)',
  use_yn         CHAR(1)      COMMENT '사용여부',
  revision_type  VARCHAR(50)  COMMENT '개정구분명 (변경, 폐기)',
  revision_item  VARCHAR(200) COMMENT '개정항목',
  revision_note  TEXT         COMMENT '개정사유',
  category_path  VARCHAR(500) COMMENT '1순위분류 경로',
  KEY ix_term_name (term_name),
  KEY ix_term_abbr (term_abbr)
) COMMENT '공통표준용어 원본';

CREATE TABLE IF NOT EXISTS std_dict.common_word (
  row_no        INT          NOT NULL PRIMARY KEY COMMENT '원본 행 번호',
  enact_round   VARCHAR(50)  COMMENT '제정차수',
  word_name     VARCHAR(100) NOT NULL COMMENT '공통표준단어명',
  word_abbr     VARCHAR(100) NOT NULL COMMENT '공통표준단어영문약어명',
  word_eng      VARCHAR(300) COMMENT '공통표준단어영문명',
  description   TEXT         COMMENT '공통표준단어설명',
  is_format     CHAR(1)      COMMENT '형식단어여부',
  domain_class  VARCHAR(50)  COMMENT '공통표준도메인 분류명',
  synonyms      TEXT         COMMENT '이음동의어 목록 (쉼표 구분)',
  forbidden     TEXT         COMMENT '금칙어 목록 (쉼표 구분)',
  use_yn        CHAR(1)      COMMENT '사용여부',
  revision_type VARCHAR(50)  COMMENT '개정구분명 (변경, 폐기)',
  revision_item VARCHAR(200) COMMENT '개정항목',
  revision_note TEXT         COMMENT '개정사유',
  KEY ix_word_name (word_name),
  KEY ix_word_abbr (word_abbr)
) COMMENT '공통표준단어 원본';

CREATE TABLE IF NOT EXISTS std_dict.common_domain (
  row_no         INT          NOT NULL PRIMARY KEY COMMENT '원본 행 번호',
  enact_round    VARCHAR(50)  COMMENT '제정차수',
  group_name     VARCHAR(50)  COMMENT '공통표준도메인 그룹명',
  domain_class   VARCHAR(50)  COMMENT '공통표준도메인 분류명',
  domain_name    VARCHAR(100) NOT NULL COMMENT '공통표준도메인명',
  description    TEXT         COMMENT '공통표준도메인 설명',
  data_type      VARCHAR(50)  COMMENT '데이터 타입',
  data_length    VARCHAR(20)  COMMENT '데이터 길이',
  data_scale     VARCHAR(20)  COMMENT '소수점 길이',
  storage_format VARCHAR(500) COMMENT '저장형식',
  display_format VARCHAR(500) COMMENT '표현형식',
  unit           VARCHAR(50)  COMMENT '단위',
  allowed_value  TEXT         COMMENT '허용값',
  use_yn         CHAR(1)      COMMENT '사용여부',
  revision_type  VARCHAR(50)  COMMENT '개정구분명 (변경, 폐기)',
  revision_item  VARCHAR(200) COMMENT '개정항목',
  revision_note  TEXT         COMMENT '개정사유',
  KEY ix_domain_name (domain_name)
) COMMENT '공통표준도메인 원본';

-- 프로그램이 읽는 형태: 사용 중인 용어 + 도메인 타입·길이
CREATE OR REPLACE VIEW std_dict.v_common_term AS
SELECT t.row_no, t.term_name, t.term_abbr, t.domain_name, t.synonyms,
       d.data_type, d.data_length, d.data_scale
FROM std_dict.common_term t
LEFT JOIN std_dict.common_domain d ON d.domain_name = t.domain_name AND COALESCE(d.use_yn, 'Y') <> 'N'
WHERE COALESCE(t.use_yn, 'Y') <> 'N';

-- ---------------------------------------------------------------------------
-- 전체 평가대상 DB 목록 (화면에서 기관·시스템을 고를 때 씀). 화면 설정의 '목록 가져오기'가 자동으로 만들고 채운다.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS std_dict.eval_db (
  row_no      INT          NOT NULL PRIMARY KEY COMMENT '목록 행 번호',
  org_name    VARCHAR(100) NOT NULL COMMENT '기관명',
  org_seq     INT          COMMENT '기관 안 순번',
  system_name VARCHAR(200) NOT NULL COMMENT '정보시스템명',
  db_kor_name VARCHAR(200) COMMENT '한글 DB명',
  db_eng_name VARCHAR(100) COMMENT '영문 DB명',
  KEY ix_eval_org (org_name)
) COMMENT '전체 평가대상 DB 목록';

-- ---------------------------------------------------------------------------
-- 기관표준 (기관명 열로 나눈다: 기관이 늘어도 테이블은 그대로). 한 기관을 다시 넣으면 그 기관 행만 바뀐다.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS std_dict.inst_std (
  org_name     VARCHAR(100) NOT NULL PRIMARY KEY COMMENT '기관명 (평가대상 목록의 기관명)',
  std_name     VARCHAR(200) COMMENT '기관표준명',
  source       VARCHAR(30)  COMMENT '가져온 형식 (등록 양식 / 통합시스템 점검결과)',
  file_names   TEXT         COMMENT '가져온 파일',
  imported_at  VARCHAR(20)  COMMENT '가져온 날짜',
  term_count   INT, word_count INT, domain_count INT, code_count INT
) COMMENT '기관별 기관표준 목록';

CREATE TABLE IF NOT EXISTS std_dict.inst_term (
  org_name        VARCHAR(100) NOT NULL COMMENT '기관명 (평가대상 목록의 기관명)',
  row_no          INT NOT NULL COMMENT '원본 행 순서',
  term_name       VARCHAR(200) COMMENT '표준용어명',
  term_eng        VARCHAR(300) COMMENT '영문명',
  term_abbr       VARCHAR(200) COMMENT '영문약어명',
  description     TEXT COMMENT '용어설명',
  domain_name     VARCHAR(100) COMMENT '표준도메인명',
  dept_name       VARCHAR(100) COMMENT '관리부서명',
  code_name       VARCHAR(100) COMMENT '표준코드명',
  biz_area        VARCHAR(100) COMMENT '업무분야',
  enact_date      VARCHAR(50) COMMENT '제정일자',
  note            TEXT COMMENT '비고',
  comp_result     VARCHAR(50) COMMENT '완전성점검결과',
  comp_detail     TEXT COMMENT '완전성점검결과내용',
  conf_result     VARCHAR(50) COMMENT '공통표준준용결과',
  conf_detail     TEXT COMMENT '공통표준준용결과내용',
  PRIMARY KEY (org_name, row_no),
  KEY ix_inst_term_term_name (org_name, term_name),
  KEY ix_inst_term_term_abbr (org_name, term_abbr)
) COMMENT '기관표준용어';

CREATE TABLE IF NOT EXISTS std_dict.inst_word (
  org_name        VARCHAR(100) NOT NULL COMMENT '기관명 (평가대상 목록의 기관명)',
  row_no          INT NOT NULL COMMENT '원본 행 순서',
  word_name       VARCHAR(100) COMMENT '표준단어명',
  word_abbr       VARCHAR(100) COMMENT '단어영문약어명',
  word_eng        VARCHAR(200) COMMENT '단어영문명',
  description     TEXT COMMENT '단어설명',
  is_format       VARCHAR(50) COMMENT '형식단어여부',
  domain_class    VARCHAR(100) COMMENT '도메인분류명',
  synonyms        TEXT COMMENT '이음동의어목록',
  forbidden       TEXT COMMENT '금칙어목록',
  enact_date      VARCHAR(50) COMMENT '제정일자',
  note            TEXT COMMENT '비고',
  comp_result     VARCHAR(50) COMMENT '완전성점검결과',
  comp_detail     TEXT COMMENT '완전성점검결과내용',
  conf_result     VARCHAR(50) COMMENT '공통표준준용결과',
  conf_detail     TEXT COMMENT '공통표준준용결과내용',
  PRIMARY KEY (org_name, row_no),
  KEY ix_inst_word_word_name (org_name, word_name),
  KEY ix_inst_word_word_abbr (org_name, word_abbr)
) COMMENT '기관표준단어';

CREATE TABLE IF NOT EXISTS std_dict.inst_domain (
  org_name        VARCHAR(100) NOT NULL COMMENT '기관명 (평가대상 목록의 기관명)',
  row_no          INT NOT NULL COMMENT '원본 행 순서',
  group_name      VARCHAR(100) COMMENT '표준도메인그룹명',
  domain_class    VARCHAR(100) COMMENT '도메인분류명',
  domain_name     VARCHAR(100) COMMENT '도메인명',
  description     TEXT COMMENT '도메인설명',
  data_type       VARCHAR(100) COMMENT '데이터타입',
  data_length     VARCHAR(100) COMMENT '데이터길이',
  data_scale      VARCHAR(100) COMMENT '소수점길이',
  storage_format  VARCHAR(100) COMMENT '저장형식',
  display_format  VARCHAR(100) COMMENT '표현형식',
  unit            VARCHAR(100) COMMENT '단위',
  allowed_value   TEXT COMMENT '허용값',
  enact_date      VARCHAR(50) COMMENT '제정일자',
  note            TEXT COMMENT '비고',
  comp_result     VARCHAR(50) COMMENT '완전성점검결과',
  comp_detail     TEXT COMMENT '완전성점검결과내용',
  conf_result     VARCHAR(50) COMMENT '공통표준준용결과',
  conf_detail     TEXT COMMENT '공통표준준용결과내용',
  PRIMARY KEY (org_name, row_no),
  KEY ix_inst_domain_domain_name (org_name, domain_name)
) COMMENT '기관표준도메인';

CREATE TABLE IF NOT EXISTS std_dict.inst_code (
  org_name        VARCHAR(100) NOT NULL COMMENT '기관명 (평가대상 목록의 기관명)',
  row_no          INT NOT NULL COMMENT '원본 행 순서',
  dept_name       VARCHAR(100) COMMENT '관리부서명',
  code_kor        VARCHAR(200) COMMENT '한글코드명',
  code_eng        VARCHAR(200) COMMENT '영문코드명',
  description     TEXT COMMENT '코드설명',
  data_type       VARCHAR(100) COMMENT '데이터타입',
  data_length     VARCHAR(100) COMMENT '데이터길이',
  code_value      VARCHAR(200) COMMENT '코드값',
  code_meaning    TEXT COMMENT '코드값의미',
  enact_date      VARCHAR(50) COMMENT '제정일자',
  note            TEXT COMMENT '비고',
  comp_result     VARCHAR(50) COMMENT '완전성점검결과',
  comp_detail     TEXT COMMENT '완전성점검결과내용',
  conf_result     VARCHAR(50) COMMENT '공통표준준용결과',
  conf_detail     TEXT COMMENT '공통표준준용결과내용',
  PRIMARY KEY (org_name, row_no),
  KEY ix_inst_code_code_kor (org_name, code_kor)
) COMMENT '기관표준코드';
