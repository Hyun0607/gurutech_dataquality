# stdtool — 공공데이터 품질관리 수준평가 표준화 점검 프로그램

공공데이터 품질관리 수준평가의 **데이터 표준·구조·연계 지표(2-1-2 ~ 2-1-5)** 산출물을 만들고 미리 점검하는 Windows 데스크톱 프로그램입니다.
기존 엑셀 VBA 매크로(표준구조 매크로)를 Python으로 옮기고, 매크로로는 사람이 손으로 하던 일을 자동화했습니다.

> 이 저장소에는 **코드만** 있습니다. 매크로 파일, 공통표준 원본, 기관 메타 파일, 기관표준, 표준 사전(`std_dict.sqlite`), 산출물 양식(xlsx), 참고 자료는 올리지 않습니다 ([아래](#저장소에-없는-파일) 참고).

## 무엇을 하나

| 메뉴 | 지표 | 하는 일 |
|---|---|---|
| 예방적 품질관리 | 2-1-2 | 이행점검 대상 사업 분류·다음 회차 예측(IRM 사전협의 목록), 발주단계 RFP의 DAR 반영 점검, 완료·감리보고서의 세부 기준 18개 Y/N/- 판정, 사업단 양식 결과 엑셀·보완 가이드 폴더 |
| 표준 | 2-1-3 | 메타 파일 → DB표준 도메인·용어·단어 정의서, 공통표준 유의어·금칙어 매핑, 품질·표준관리 통합시스템과 같은 기준의 사전점검(오류 묶음·오류명·건수), 예상 적용률, **기관표준 점검·A값 자가진단** |
| 구조 | 2-1-4 | 테이블·컬럼정의서, 물리 ERD 대체 테이블관계정의서, 구조 현행화 점검 |
| 연계 | 2-1-5 | 연계데이터 목록 정의서(2-1-5-1)·관리현황 자료(2-1-5-2) |
| 요약 | — | 시스템 정보, 회차별 실행 기록 비교 |

매크로 대비 고도화:

1. **도메인 사전**: 타입·길이 파싱, 소수점 보존, 한글 끝말로 분류해 도메인을 따로 추가하는 일을 없앱니다.
2. **공통표준 유의어·금칙어 대응**: 이음동의어·금칙어로 쓴 컬럼을 찾아 알려 줍니다 (정의서는 실제 DB 컬럼 그대로).
3. **DB표준적용 사전점검**: 점검요청 전에 통합시스템과 같은 오류 목록과 예상 적용률을 보여 줍니다.

## 기술 스택

- Python 3.11 · [uv](https://docs.astral.sh/uv/)
- 화면: PySide6 (Qt) · 글꼴 Pretendard (OFL)
- 엑셀: openpyxl · 문서 읽기: pypdf, olefile (hwp), hwpx(zip/xml)
- 표준 사전: MySQL(관리자 원본, pymysql) 또는 SQLite 사전 파일(팀 배포용)
- 비밀번호: 환경변수 `STDTOOL_DB_PASSWORD` 또는 Windows 자격 증명 관리자(keyring). 코드·설정 파일에 넣지 않습니다.
- 배포: PyInstaller → 폴더형 exe + zip

## 폴더 구조

```
stdtool/                    프로젝트 (pyproject.toml, uv.lock)
  stdtool/                  패키지
    core/                   단계별 로직 (화면 코드 없음): 정제·매핑·생성·사전점검·구조·연계·예방적 품질관리·기관표준
    workbook/               엑셀·문서 읽기/쓰기, 결과 보고서
    ui/                     PySide6 화면 (assets: 아이콘·글꼴)
    db.py, inst_db.py       표준 사전 DB (공통표준·Code_type/tail·평가대상 목록·기관표준)
    pipeline.py, service.py 전체 흐름 (명령줄·화면 공용)
    cli.py                  명령줄
    templates/              산출물 양식 xlsx (저장소에 없음)
    data/std_dict.sqlite    배포용 표준 사전 (저장소에 없음)
  sql/schema.sql            MySQL std_dict 스키마 (DBeaver에서 실행)
  sql/code_additions.sql    Code_type·Code_tail 추가분
  packaging/                exe 빌드 (build.py, stdtool.spec, 설치 안내)
  tests/                    pytest
  config.example.toml       설정 예시
```

자세한 사용법(화면·명령줄·산출물·사전 DB·배포)은 [stdtool/README.md](stdtool/README.md)를 보세요.

## 시작하기

```powershell
git clone <저장소 주소>
cd <저장소>/stdtool
uv sync
```

1. [저장소에 없는 파일](#저장소에-없는-파일)을 제자리에 넣습니다. 적어도 `stdtool/templates/`의 양식과 표준 사전이 있어야 합니다.
2. 표준 사전을 준비합니다. 다음 둘 중 하나입니다.
   - **사전 파일**: 받은 `std_dict.sqlite`를 `stdtool/stdtool/data/`에 넣습니다.
   - **MySQL**: DBeaver에서 [sql/schema.sql](stdtool/sql/schema.sql)을 실행하고 `uv run stdtool db import --config config.toml`로 채웁니다.
3. 설정: `config.example.toml`을 `config.toml`로 복사해 내 PC 경로와 DB 접속 정보를 적습니다. `config.toml`은 git에 올라가지 않습니다.
4. 실행:

```powershell
uv run stdtool-gui                                  # 화면
uv run stdtool run --config config.toml --meta 메타.xlsx   # 명령줄
uv run pytest                                       # 테스트 (원본 자료가 없으면 해당 테스트는 건너뜀)
uv run python packaging/build.py --skip-dict        # 팀 배포용 exe·zip (dist/)
```

## 저장소에 없는 파일

`.gitignore`로 제외합니다. 기관 자료와 개인정보가 섞일 수 있고 용량도 커서, 따로 보관하고 필요할 때 복사해 넣습니다.

| 무엇 | 위치 | 왜 |
|---|---|---|
| 산출물 양식 (`*.xlsx`) | `stdtool/stdtool/templates/` | 매크로에서 뽑은 양식 (`stdtool make-templates --macro 매크로.xlsm`로 다시 만들 수 있음) |
| 예방적 품질관리 자료 (가이드·산출물 예시, 약 57MB) | `stdtool/stdtool/templates/예방적품질관리_자료/` | 사업단 배포 자료 |
| 표준 사전 | `stdtool/stdtool/data/std_dict.sqlite` | 공통표준·기관표준 데이터 (`stdtool db export`로 MySQL에서 만듦) |
| 기관표준 넣기 SQL | `stdtool/sql/기관표준_*.sql` | 기관 데이터 (`stdtool db inst-sql`로 만듦) |
| 테스트 자료 (`*.csv`) | `stdtool/tests/fixtures/` | 실제 시스템 구조 정보 |
| 개인 설정 | `stdtool/config.toml` | 내 PC 경로·DB 접속 정보 |
| 참고 자료 | `공공데이터 품질관리 메뉴얼 및 참고 파일/` | 매뉴얼·기관 원본 |
| 빌드 결과 | `stdtool/build/`, `stdtool/dist/` | exe·zip |

메타 파일, RFP, 보고서 같은 원본은 프로그램이 읽기만 합니다. 회차 기록(`%APPDATA%\stdtool\history.sqlite`)에는 메타 파일 내용 없이 파일 이름과 결과 요약만 남습니다.

## 버전

현재 **1.2.0** (`stdtool/stdtool/__init__.py`). 주요 변경:

- 1.2.0: 기관표준 점검·A값 자가진단(2-1-3-1), 기관표준 DB 테이블(`inst_*`), 기관표준 준용 사전점검. 값진단 기능 제거.
- 1.1.0: 예방적 품질관리(2-1-2) 대상 사업·발주·완료 점검.
- 1.0.x: 매크로 이식, 고도화 3종, 팀 배포 exe.
