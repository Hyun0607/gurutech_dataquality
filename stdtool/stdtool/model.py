"""시트 열 구성과 변경 이력. 행은 매크로와 같이 열 순서 리스트로 다룬다."""
from dataclasses import dataclass, field


def col(letter: str) -> int:
    """열 문자 → 0부터 시작하는 인덱스 (A=0, Z=25, AA=26)."""
    index = 0
    for ch in letter.upper():
        index = index * 26 + (ord(ch) - 64)
    return index - 1


# RAW: A 한글테이블명, B 영문테이블명, C 한글컬럼명, D 영문컬럼명, E 타입, F 길이
# G는 고도화 모드 전용 소수점 길이 (매크로 RAW에는 없음)
RAW_COLS = 7
META_COLS = 46          # 메타 시트 A~AT, 4행부터 데이터
MANUAL_COLS = 37        # 수동등록 시트 A~AK, 4행부터 데이터
DOMAIN_COLS = 13        # 1_도메인 A~M
TERM_COLS = 10          # 2_용어 A~J
WORD_COLS = 10          # 3_단어 A~J
TABLE_DEF_COLS = 7      # 테이블정의서 A~G
COLUMN_DEF_COLS = 18    # 컬럼정의서 A~R
REMOVED_COLS = 6        # 제거된 항목 A~F (F는 RAW 행 번호)


def blank_row(width: int) -> list:
    return [None] * width


@dataclass
class Change:
    step: str
    sheet: str
    row: str
    action: str          # 변경 / 삭제 / 추가 / 경고
    target: str = ""
    before: object = None
    after: object = None
    reason: str = ""


@dataclass
class ChangeLog:
    items: list = field(default_factory=list)

    def add(self, step, sheet, row, action, target="", before=None, after=None, reason=""):
        self.items.append(Change(step, sheet, str(row), action, target, before, after, reason))

    def changed(self, step, sheet, row, target, before, after, reason=""):
        if before != after:
            self.add(step, sheet, row, "변경", target, before, after, reason)
