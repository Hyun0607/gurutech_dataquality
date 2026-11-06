"""③ DB표준적용 사전점검: 완전성 점검 → DB표준 ↔ 컬럼정의서·메타 대조 → 예상 적용률.

근거: 세부 안내서 표준 완전성(p.74~76), DB표준 적용(메타) 점검(p.100~102),
컬럼정의서 DB표준적용점검(p.180), 적용률 = (전체 컬럼 수 − 메타 기준 오류 건수) ÷ 전체 컬럼 수(p.104).
"""
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from ..config import DEFAULT_LENGTH_REQUIRED
from ..dictionary import split_list
from ..model import col
from ..vba import s, val

# 오류명은 품질·표준관리 통합시스템 점검 결과의 '오류명'과 같다 (세부 안내서 p.74~80, p.102, p.180).
# 통합시스템에 없는 프로그램 추가 점검(누락 등)은 GROUPS에서 '프로그램 추가 점검'으로 따로 묶는다.
CODES = {
    "D01": "누락(도메인명)", "D02": "누락(데이터타입)", "D03": "중복(도메인명)", "D04": "누락(데이터길이)",
    "D05": "형식 오류(제정일자)",
    "T01": "누락(용어명)", "T02": "누락(영문약어명)", "T03": "누락(표준도메인명)", "T04": "중복(용어명)",
    "T05": "중복(영문약어명)", "T06": "점검 불가능(연관된 표준도메인 미존재)",
    "T07": "점검 불가능(연관된 표준도메인 완전성점검 오류)", "T08": "구성 단어가 DB표준단어에 없음",
    "T11": "형식 오류(용어명)", "T12": "형식 오류(영문약어명)", "T13": "형식 오류(제정일자)",
    "W01": "누락(단어명)", "W02": "누락(영문약어명)", "W03": "중복(영문약어명)", "W04": "중복(단어명)",
    "W07": "형식 오류(단어명)", "W08": "형식 오류(영문약어명)", "W09": "형식 오류(형식단어여부)", "W10": "형식 오류(제정일자)",
    "C00": "점검 불가능(연관된 표준용어 완전성점검 오류)", "C01": "점검 불가능(연관된 표준용어 미존재)",
    "C02": "불일치(한글컬럼명)", "C03": "불일치(데이터타입)", "C04": "불일치(데이터길이)", "C05": "불일치(영문컬럼명)",
    "M00": "점검 불가능(연관된 표준용어 완전성점검 오류)", "M01": "점검 불가능(연관된 표준용어 미존재)",
    "M03": "불일치(데이터타입)", "M04": "불일치(데이터길이)",
    # 기준1 공통표준 준용 점검 (공통표준 원본이 있을 때, p.77~78)
    "T14": "불일치(용어명)", "T10": "불일치(영문약어명)", "T15": "불일치(데이터타입)", "T16": "불일치(데이터길이)",
    "T17": "점검 불가능(연관된 표준도메인 미존재)", "T18": "점검 불가능(연관된 표준도메인 완전성점검 오류)",
    "T09": "금칙어 사용(용어명)",
    "W11": "불일치(단어명)", "W06": "불일치(영문약어명)", "W05": "금칙어 사용(단어명)",
    "D06": "불일치(데이터타입)", "D07": "불일치(데이터길이)",
    # DB표준용어의 기관표준 준용 점검 (그 기관의 기관표준이 사전에 있을 때, p.79)
    "I01": "불일치(용어명)", "I02": "불일치(영문약어명)", "I03": "불일치(데이터타입)", "I04": "불일치(데이터길이)",
}
# 통합시스템 점검에 없는 프로그램 추가 점검.
# 영문약어명 형식(T12·W08)은 안내서에 있지만 통합시스템은 'LOT(랏)'·'EDITION(에디션)' 같은 약어도 오류로 내지 않았다
# (예술경영지원센터 한국 미술시장 정보시스템: 용어 완전성 오류 0건, 단어 완전성 오류 53건 = 중복(단어명) 53건).
EXTRA = {"D01", "D02", "T01", "T02", "T03", "T08", "T12", "W01", "W02", "W08"}
_GROUP_OF = [
    ({"D03", "D04", "D05"}, "[ DB표준도메인 ] 완전성 점검"),
    ({"T04", "T05", "T06", "T07", "T11", "T13"}, "[ DB표준용어 ] 완전성 점검"),
    ({"W03", "W04", "W07", "W09", "W10"}, "[ DB표준단어 ] 완전성 점검"),
    ({"T09", "T10", "T14", "T15", "T16", "T17", "T18"}, "[ DB표준용어 ] 공통표준용어 준용 점검"),
    ({"W05", "W06", "W11"}, "[ DB표준단어 ] 공통표준단어 준용 점검"),
    ({"D06", "D07"}, "[ DB표준도메인 ] 공통표준도메인 준용 점검"),
    ({"I01", "I02", "I03", "I04"}, "[ DB표준용어 ] 기관표준용어 준용 점검"),
    ({"C00", "C01", "C02", "C03", "C04", "C05"}, "[ 컬럼정의서 ] DB표준 적용 점검"),
    ({"M00", "M01", "M03", "M04"}, "[ 메타 ] DB표준 적용(메타) 점검"),
    (EXTRA, "프로그램 추가 점검"),
]
GROUPS = {code: name for codes, name in _GROUP_OF for code in codes}
STANDARD_GROUPS = [name for _, name in _GROUP_OF[:7]] + [_GROUP_OF[-1][1]]   # 표준 정의 화면 탭 순서

# 오류상세내용: 통합시스템 문구 (안내서 설명, 준용 점검은 실제 결과 화면의 문장 형식)
DETAILS = {
    "D01": "표준도메인명이 비어 있는 경우", "D02": "데이터타입이 비어 있는 경우",
    "D03": "도메인명에 중복이 존재하는 경우",
    "D04": "CHAR, VARCHAR, NCHAR, NVARCHAR, VARCHAR2, NUMBER 타입인데 길이가 없는 경우",
    "D05": "YYYYMMDD 형식 아닌 경우",
    "T01": "표준용어명이 비어 있는 경우", "T02": "영문약어명이 비어 있는 경우", "T03": "표준도메인명이 비어 있는 경우",
    "T04": "표준용어명이 중복 존재하는 경우", "T05": "영문약어명이 중복 존재하는 경우",
    "T06": "표준도메인에 동일한 표준도메인명이 존재하지 않는 경우",
    "T07": "매핑한 표준도메인이 완전성 점검 결과 \"오류\"인 경우",
    "T08": "영문약어명을 _로 나눈 조각이 DB표준단어 영문약어명에 없는 경우",
    "T11": "표준용어명은 한글, 영문대문자, 숫자와 특정 특수문자(/ - . % & _)만 입력 가능",
    "T12": "영문약어명은 영문대문자, 숫자, 특수문자는 \"_\" 만 입력 가능", "T13": "YYYYMMDD 형식 아닌 경우",
    "W01": "표준단어명이 비어 있는 경우", "W02": "영문약어명이 비어 있는 경우",
    "W03": "영문약어명이 중복 존재하는 경우", "W04": "동일한 단어명이 중복되는 경우 (이음동의어, 금칙어 포함)",
    "W07": "표준단어명은 한글, 영문, 숫자, 일부 특수문자(- _ . / % &)만 입력 가능",
    "W08": "단어 영문약어명은 영문, 숫자, 일부 특수문자(- _)만 입력 가능",
    "W09": "Y, N이 아닌 경우", "W10": "YYYYMMDD 형식 아닌 경우",
    "T14": "공통표준용어 준용 대상이지만 용어명이 불일치하는 경우",
    "T10": "공통표준용어 준용 대상이지만 영문약어명이 불일치하는 경우",
    "T15": "공통표준용어 준용 대상이지만 데이터타입이 불일치하는 경우",
    "T16": "공통표준용어 준용 대상이지만 데이터길이가 불일치하는 경우",
    "T17": "표준도메인에 동일한 표준도메인명이 존재하지 않는 경우",
    "T18": "해당 표준도메인이 완전성 점검 결과 \"오류\"이기 때문에 데이터타입, 데이터길이 점검이 불가능한 경우",
    "T09": "표준용어명이 공통표준단어의 금칙어 조합으로 구성되는 경우",
    "W11": "공통표준단어 준용 대상이지만 단어명이 불일치하는 경우",
    "W06": "공통표준단어 준용 대상이지만 영문약어명이 불일치하는 경우",
    "W05": "공통표준단어의 금칙어 중 일치하는 단어명을 사용한 경우",
    "D06": "공통표준도메인 준용 대상이지만 데이터타입이 불일치하는 경우",
    "D07": "공통표준도메인 준용 대상이지만 데이터길이가 불일치하는 경우",
    "I01": "표준용어명이 기관표준 용어명과 불일치하는 경우", "I02": "영문약어명이 기관표준 영문약어명과 불일치하는 경우",
    "I03": "DB표준용어의 데이터타입이 기관표준용어와 불일치하는 경우",
    "I04": "DB표준용어의 데이터길이가 기관표준용어와 불일치하는 경우",
    "C00": "해당 표준용어가 완전성 점검 결과 \"오류\"이기 때문에 DB표준 적용 점검이 불가능한 경우",
    "C01": "표준용어에 동일한 용어명 또는 영문약어명이 존재하지 않아 DB표준 적용 점검이 불가능한 경우",
    "C02": "표준용어명과 컬럼정의서의 한글컬럼명이 불일치하는 경우",
    "C03": "표준용어의 영문약어명과 컬럼정의서의 영문테이블명, 영문컬럼명은 일치하지만 데이터타입이 불일치하는 경우",
    "C04": "표준용어의 영문약어명과 컬럼정의서의 영문테이블명, 영문컬럼명은 일치하지만 데이터길이가 불일치하는 경우",
    "C05": "표준용어의 영문약어명과 컬럼정의서의 영문컬럼명이 불일치하는 경우",
    "M00": "해당 표준용어가 완전성 점검 결과 \"오류\"이기 때문에 DB표준 적용 점검이 불가능한 경우",
    "M01": "표준용어에 동일한 영문약어명이 존재하지 않아 DB표준 적용 점검이 불가능한 경우",
    "M03": "DB표준과 데이터타입이 불일치하는 경우", "M04": "DB표준과 데이터길이가 불일치하는 경우",
}

# 공통표준과 데이터타입을 비교할 때 바꾸는 표기 (안내서 p.78: STRING → VARCHAR, NUMBER → NUMERIC).
# DATE ↔ DATETIME 도 통합시스템은 불일치로 보지 않았다 (예술경영지원센터 운영시스템 '종료일시' 점검 결과).
TYPE_EQUIV = {"STRING": "VARCHAR", "VARCHAR2": "VARCHAR", "NUMBER": "NUMERIC", "DATE": "DATETIME"}


def same_type(a, b) -> bool:
    a, b = s(a).upper(), s(b).upper()
    return TYPE_EQUIV.get(a, a) == TYPE_EQUIV.get(b, b)


def same_length(a, b) -> bool:
    """길이는 둘 다 있을 때만 비교 (0·빈 값은 길이 없음)."""
    if s(a) in ("", "0") or s(b) in ("", "0"):
        return True
    return val(a) == val(b)
# 완전성 오류로 보는 코드 (세부 안내서 p.74~76. 안내서에 없는 T08, 통합시스템이 잡지 않는 T12·W08은 경고)
TERM_BLOCKING = {"T01", "T02", "T03", "T04", "T05", "T06", "T07", "T11", "T13"}
DOMAIN_BLOCKING = {"D01", "D02", "D03", "D04", "D05"}
WORD_BLOCKING = {"W01", "W02", "W03", "W04", "W07", "W09", "W10"}

# 형식 규칙 (p.74 용어, p.75 단어). 한글 필수·띄어쓰기 불가·숫자만 불가는 따로 본다.
_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
_LETTER = re.compile(r"[A-Za-z]")
TERM_NAME_CHARS = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣA-Z0-9/\-.%&_]")     # 한글, 영문대문자, 숫자, / - . % & _
TERM_ABBR_CHARS = re.compile(r"[A-Z0-9_]")                          # 영문대문자, 숫자, _
WORD_NAME_CHARS = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣA-Za-z0-9\-_./%&]")   # 한글, 영문, 숫자, - _ . / % &
WORD_ABBR_CHARS = re.compile(r"[A-Za-z0-9\-_]")                      # 영문, 숫자, - _
# 적용률 산정에 들어가는 적용 점검 오류
COUNTED = {"C00", "C01", "C03", "C04", "M00", "M01", "M03", "M04"}
STANDARD1 = {"T09", "T10", "T14", "T15", "T16", "T17", "T18", "W05", "W06", "W11", "D06", "D07"}
INST_CONFORM = {"I01", "I02", "I03", "I04"}


# 화면·리포트에 보이는 코드: 알파벳 대신 영역 이름 (T01 → 용어-01)
CODE_AREAS = {"D": "도메인", "T": "용어", "W": "단어", "C": "컬럼정의서", "M": "메타"}


def code_label(code: str) -> str:
    return f"{CODE_AREAS[code[0]]}-{code[1:]}" if code[:1] in CODE_AREAS else code


def group(code: str) -> str:
    """통합시스템 점검 화면 이름 (예: '[ DB표준용어 ] 공통표준용어 준용 점검')."""
    return GROUPS[code]


# 오류 상세내역 표의 앞 세 칸 (통합시스템 표와 같은 순서). 뒤에 오류명·오류상세내용·참고(프로그램이 찾은 근거)
ITEM_HEADERS = {"용어": ["표준용어명", "영문약어명", "표준도메인명"], "단어": ["표준단어명", "단어영문약어명", "형식단어여부"],
                "도메인": ["표준도메인명", "데이터타입", "데이터길이"]}
EXTRA_HEADERS = ["영역", "이름", ""]


def short_group(name: str) -> str:
    """'[ DB표준용어 ] 공통표준용어 준용 점검' → '용어 · 공통표준 준용' (탭·시트 이름)."""
    if not name.startswith("["):
        return name
    area, rest = name[1:].split("]", 1)
    area = area.strip().replace("DB표준", "")
    kind = ("완전성" if "완전성" in rest else "기관표준 준용" if "기관표준" in rest else "공통표준 준용" if "준용" in rest
            else rest.strip().replace(" 점검", ""))
    return f"{area} · {kind}"


def group_headers(name: str) -> list:
    area = next((a for a in ITEM_HEADERS if f"DB표준{a}" in name), None)
    return ["행"] + (ITEM_HEADERS[area] if area else EXTRA_HEADERS) + ["오류명", "오류상세내용", "참고"]


def issue_row(issue, domains, terms, words, extra: bool = False) -> tuple:
    """오류 하나를 통합시스템 상세내역 표처럼: 행, 이름 세 칸, 오류명, 오류상세내용, 참고."""
    sheets = {"용어": (terms, ("A", "C", "E")), "단어": (words, ("A", "B", "E")), "도메인": (domains, ("C", "E", "F"))}
    sheet, letters = sheets.get(issue.area, (None, ()))
    if extra or sheet is None or not 0 <= issue.row - 2 < len(sheet):
        items = (issue.area, issue.key, "")
    else:
        r = sheet[issue.row - 2]
        items = tuple(r[col(x)] for x in letters)
    return (issue.row, *items, issue.message, issue.description, issue.detail)


def severity(code: str) -> str:
    """리포트 '구분' 칸: 완전성 오류 / 적용 오류 / 공통표준 준용 / 경고."""
    if code in DOMAIN_BLOCKING | TERM_BLOCKING | WORD_BLOCKING:
        return "완전성 오류"
    if code in COUNTED:
        return "적용 오류"
    if code in STANDARD1:
        return "공통표준 준용"
    if code in INST_CONFORM:
        return "기관표준 준용"
    return "경고"


@dataclass
class Issue:
    area: str        # 도메인 / 용어 / 단어 / 컬럼정의서 / 메타
    row: int         # 시트 행 번호
    key: str
    code: str
    detail: str = ""

    @property
    def message(self) -> str:
        return CODES[self.code]

    @property
    def description(self) -> str:
        """오류상세내용 (통합시스템 문구)."""
        return DETAILS[self.code]


@dataclass
class ColumnRow:
    """컬럼 하나와 매칭된 표준용어·도메인을 나란히 본 결과."""
    source: str
    row: int
    table: str
    kor: str
    eng: str
    data_type: str
    length: object
    term: str = ""
    term_kor: str = ""
    domain: str = ""
    domain_type: str = ""
    domain_length: object = None
    codes: list = field(default_factory=list)


@dataclass
class PrecheckResult:
    issues: list
    columns: list
    meta: list
    basis: str           # 적용률 산정 기준: '메타' 또는 '컬럼정의서(추정)'
    total: int
    error_columns: int
    completeness: dict = field(default_factory=dict)   # 영역 → (전체 건수, 완전성 오류 건수)

    def completeness_rows(self) -> list:
        """(영역, 전체, 오류, 성공, 결과). 전체가 오류면 해당 표준 정의 점수가 0점 (p.76)."""
        out = []
        for area, (total, errors) in self.completeness.items():
            if total == 0:
                verdict = "대상 없음"
            elif errors == total:
                verdict = "전체 오류 → 표준 정의 0점"
            else:
                verdict = "성공" if errors == 0 else "일부 오류"
            out.append((area, total, errors, total - errors, verdict))
        return out

    @property
    def rate(self) -> float:
        return 100.0 * (self.total - self.error_columns) / self.total if self.total else 0.0

    @property
    def score(self) -> float:
        rate = self.rate
        return 3 if rate >= 90 else 2 if rate >= 80 else 1 if rate >= 70 else 0.5

    def count(self, code: str) -> int:
        return sum(1 for i in self.issues if i.code == code)


def _dups(values):
    counts = Counter(v.upper() for v in values if v)
    return {v for v, n in counts.items() if n > 1}


def name_format_error(name: str, allowed: re.Pattern) -> str:
    """표준용어명·표준단어명 형식 오류 사유 (없으면 ''). 빈 값은 누락 코드가 따로 잡는다."""
    if name == "":
        return ""
    if re.search(r"\s", name):
        return "띄어쓰기 포함"
    if not _HANGUL.search(name):
        return "한글 없음"
    bad = sorted({ch for ch in name if not allowed.fullmatch(ch)})
    return f"허용되지 않는 글자 {' '.join(bad)}" if bad else ""


def abbr_format_error(abbr: str, allowed: re.Pattern) -> str:
    """영문약어명 형식 오류 사유 (없으면 '')."""
    if abbr == "":
        return ""
    if not _LETTER.search(abbr):
        return "영문 없음"
    bad = sorted({ch for ch in abbr if not allowed.fullmatch(ch)})
    return f"허용되지 않는 글자 {' '.join(bad)}" if bad else ""


def date_format_error(value) -> str:
    """제정일자는 YYYYMMDD (셀 서식 '일반'의 숫자 또는 문자)."""
    if isinstance(value, date):
        return "날짜 서식 셀 (YYYYMMDD 숫자로)"
    text = s(value)
    if text.endswith(".0"):
        text = text[:-2]
    if not re.fullmatch(r"\d{8}", text):
        return f"YYYYMMDD 아님 ({text or '빈 값'})"
    try:
        date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError:
        return f"없는 날짜 ({text})"
    return ""


# 완전성 점검도 통합시스템은 한 건에 오류 하나만 보여 준다 (안내서에 적힌 순서로 첫 오류).
# 프로그램 추가 점검(EXTRA: 빈 값, 영문약어명 형식 등)은 따로 둔다.
DOMAIN_ORDER = ["D04", "D03", "D05"]
TERM_ORDER = ["T04", "T05", "T11", "T06", "T07", "T13"]
WORD_ORDER = ["W04", "W03", "W07", "W09", "W10"]


def first_per_row(issues: list, order: list) -> list:
    rank = {code: n for n, code in enumerate(order)}
    best = {}
    for i in issues:
        if i.code in rank and (i.row not in best or rank[i.code] < rank[best[i.row].code]):
            best[i.row] = i
    return [i for i in issues if i.code not in rank or best[i.row] is i]


def check_domains(domains: list, length_required: list) -> list:
    issues = []
    names = [s(d[col("C")]) for d in domains]
    dup = _dups(names)
    required = {t.upper() for t in length_required}
    for i, d in enumerate(domains):
        name, data_type, length = names[i], s(d[col("E")]), d[col("F")]
        row = i + 2
        if name == "":
            issues.append(Issue("도메인", row, name, "D01"))
        if data_type == "":
            issues.append(Issue("도메인", row, name, "D02"))
        if name and name.upper() in dup:
            issues.append(Issue("도메인", row, name, "D03"))
        if data_type.upper() in required and (s(length) == "" or val(length) == 0):
            issues.append(Issue("도메인", row, name, "D04", f"{data_type} 길이 {s(length) or '없음'}"))
        if reason := date_format_error(d[col("L")]):
            issues.append(Issue("도메인", row, name, "D05", reason))
    return first_per_row(issues, DOMAIN_ORDER)


def check_terms(terms: list, domains: list, words: list | None, domain_issues: list) -> list:
    issues = []
    domain_names = {s(d[col("C")]).upper() for d in domains}
    bad_domains = {i.key.upper() for i in domain_issues if i.code in DOMAIN_BLOCKING}
    word_abbrs = {s(w[col("B")]).upper() for w in words} if words else None
    kor = [s(t[col("A")]) for t in terms]
    eng = [s(t[col("C")]) for t in terms]
    dup_kor, dup_eng = _dups(kor), _dups(eng)
    for i, t in enumerate(terms):
        row, name, domain = i + 2, kor[i], s(t[col("E")])
        key = eng[i] or name
        if name == "":
            issues.append(Issue("용어", row, key, "T01"))
        if eng[i] == "":
            issues.append(Issue("용어", row, key, "T02"))
        if domain == "":
            issues.append(Issue("용어", row, key, "T03"))
        if name and name.upper() in dup_kor:
            issues.append(Issue("용어", row, key, "T04", name))
        if eng[i] and eng[i].upper() in dup_eng:
            issues.append(Issue("용어", row, key, "T05"))
        if domain and domain.upper() not in domain_names:
            issues.append(Issue("용어", row, key, "T06", domain))
        elif domain and domain.upper() in bad_domains:
            issues.append(Issue("용어", row, key, "T07", domain))
        if reason := name_format_error(name, TERM_NAME_CHARS):
            issues.append(Issue("용어", row, key, "T11", reason))
        if reason := abbr_format_error(eng[i], TERM_ABBR_CHARS):
            issues.append(Issue("용어", row, key, "T12", reason))
        if reason := date_format_error(t[col("I")]):
            issues.append(Issue("용어", row, key, "T13", reason))
        if word_abbrs is not None and eng[i]:
            missing = [p for p in eng[i].split("_") if p and p.upper() not in word_abbrs]
            if missing:
                issues.append(Issue("용어", row, key, "T08", ", ".join(missing)))
    return first_per_row(issues, TERM_ORDER)


def check_words(words: list, official_names: set | None = None) -> list:
    """official_names: 공통표준단어명(대문자). API·CCTV·URL처럼 공통표준에도 한글 없이 있는 단어는 '한글 없음'으로 잡지 않는다."""
    issues = []
    official_names = official_names or set()
    kor = [s(w[col("A")]) for w in words]
    eng = [s(w[col("B")]) for w in words]
    # 단어명 중복은 표준단어명·이음동의어·금칙어 전체를 대상으로 본다 (p.75)
    names = [[kor[i]] + split_list(w[col("G")]) + split_list(w[col("H")]) for i, w in enumerate(words)]
    dup_kor = _dups([n for row_names in names for n in dict.fromkeys(row_names)])
    dup_eng = _dups(eng)
    for i, w in enumerate(words):
        row, key = i + 2, eng[i] or kor[i]
        if kor[i] == "":
            issues.append(Issue("단어", row, key, "W01"))
        if eng[i] == "":
            issues.append(Issue("단어", row, key, "W02"))
        if eng[i] and eng[i].upper() in dup_eng:
            issues.append(Issue("단어", row, key, "W03"))
        dup = [n for n in dict.fromkeys(names[i]) if n and n.upper() in dup_kor]
        if dup:
            issues.append(Issue("단어", row, key, "W04", ", ".join(dup)))
        reason = name_format_error(kor[i], WORD_NAME_CHARS)
        if reason and not (reason == "한글 없음" and kor[i].upper() in official_names):
            issues.append(Issue("단어", row, key, "W07", reason))
        if reason := abbr_format_error(eng[i], WORD_ABBR_CHARS):
            issues.append(Issue("단어", row, key, "W08", reason))
        if s(w[col("E")]).upper() not in ("Y", "N"):
            issues.append(Issue("단어", row, key, "W09", s(w[col("E")]) or "빈 값"))
        if reason := date_format_error(w[col("I")]):
            issues.append(Issue("단어", row, key, "W10", reason))
    return first_per_row(issues, WORD_ORDER)


def check_common(terms: list, words: list | None, matcher, domains: list | None = None,
                 domain_issues: list | None = None, common_domains: dict | None = None,
                 targets: dict | None = None) -> list:
    """기준1 공통표준 준용 점검 (안내서 p.77~78). 통합시스템과 같게
    - 준용 대상만 본다: 용어는 ①용어명 ②영문약어명 ③공통표준 이음동의어가 같은 것,
      단어는 ①단어명 ②영문약어명 ③이음동의어 ④금칙어가 같은 것, 도메인은 도메인명이 같은 것.
    - 한 건에 오류 하나만 낸다 (용어명 → 영문약어명 → 도메인 → 데이터타입 → 데이터길이 → 금칙어 순서).
      통합시스템은 이음동의어로 찾은 '파일이름(FILENAME)'의 타입·길이도 달랐지만 불일치(영문약어명) 하나만 냈다.
    matcher는 core.synonym.SynonymMatcher, common_domains는 {공통표준 도메인명: (타입, 길이, 소수점)}.
    targets: 주면 영역별 준용 대상 행 번호를 담는다 ({'용어': set, '단어': set, '도메인': set}) — A값의 '준용 점검 대상 건수'."""
    targets = targets if targets is not None else {}
    for area in ("용어", "단어", "도메인"):
        targets.setdefault(area, set())
    from .synonym import norm
    issues = []
    domain_rows = {}
    for d in domains or []:
        domain_rows.setdefault(s(d[col("C")]).upper(), d)
    bad_domains = {i.key.upper() for i in domain_issues or [] if i.code in DOMAIN_BLOCKING}
    for i, t in enumerate(terms):
        name, abbr, domain = s(t[col("A")]), s(t[col("C")]), s(t[col("E")])
        key, row = abbr or name, i + 2
        common, by_abbr = matcher.by_name.get(name) or matcher.by_norm.get(norm(name)), False
        if common is None:
            found = matcher.by_synonym.get(norm(name), [])
            common = found[0] if len(found) == 1 else None
        if common is None and abbr.upper() in matcher.by_abbr:
            common, by_abbr = matcher.by_abbr[abbr.upper()], True
        if common is None:
            continue
        targets["용어"].add(row)
        target = f"공통표준 {common.name}({common.abbr})"
        d = domain_rows.get(domain.upper())
        if by_abbr and name != common.name:
            issues.append(Issue("용어", row, key, "T14", target))
        elif common.abbr.upper() != abbr.upper():
            issues.append(Issue("용어", row, key, "T10", target))
        elif d is None:
            issues.append(Issue("용어", row, key, "T17", domain))
        elif domain.upper() in bad_domains:
            issues.append(Issue("용어", row, key, "T18", domain))
        elif not same_type(d[col("E")], common.data_type):
            issues.append(Issue("용어", row, key, "T15", f"{s(d[col('E')])} ↔ {target} {s(common.data_type)}"))
        elif not same_length(d[col("F")], common.length):
            issues.append(Issue("용어", row, key, "T16", f"{s(d[col('F')])} ↔ {target} {s(common.length)}"))
        elif bad := matcher.forbidden_in(name):
            issues.append(Issue("용어", row, key, "T09", ", ".join(f"{x} → {y}" for x, y in bad)))
    if words:
        by_word_abbr = {}
        for w, _ in matcher.words.values():
            by_word_abbr.setdefault(w.abbr.upper(), w)
        for i, w in enumerate(words):
            name, abbr = s(w[col("A")]), s(w[col("B")])
            key, row = abbr or name, i + 2
            entry = matcher.words.get(norm(name))
            if entry or abbr.upper() in by_word_abbr:
                targets["단어"].add(row)
            if entry and entry[1]:
                issues.append(Issue("단어", row, key, "W05", f"{name} → {entry[0].name}"))
            elif entry:
                if entry[0].abbr.upper() != abbr.upper():
                    issues.append(Issue("단어", row, key, "W06", f"공통표준 {entry[0].name}({entry[0].abbr})"))
            elif abbr.upper() in by_word_abbr and by_word_abbr[abbr.upper()].name != name:
                common = by_word_abbr[abbr.upper()]
                issues.append(Issue("단어", row, key, "W11", f"공통표준 {common.name}({common.abbr})"))
    for i, d in enumerate(domains or []):
        name = s(d[col("C")])
        common = (common_domains or {}).get(name)
        if common is None:
            continue
        targets["도메인"].add(i + 2)
        if not same_type(d[col("E")], common[0]):
            issues.append(Issue("도메인", i + 2, name, "D06", f"{s(d[col('E')])} ↔ 공통표준 {s(common[0])}"))
        elif not same_length(d[col("F")], common[1]):
            issues.append(Issue("도메인", i + 2, name, "D07", f"{s(d[col('F')])} ↔ 공통표준 {s(common[1])}"))
    return issues


def check_inst_terms(terms: list, domains: list, inst_rows: list, domain_issues: list | None = None) -> list:
    """DB표준용어의 기관표준 준용 점검 (안내서 p.79). inst_rows: 매크로 '기관표준' 시트 행 [한글명, 영문약어명, 타입, 길이].
    준용 대상: ①기관표준용어의 용어명과 같거나 ②영문약어명이 같은 DB표준용어. 한 건에 오류 하나 (용어명 → 약어 → 타입 → 길이)."""
    by_name, by_abbr = {}, {}
    for r in inst_rows:
        by_name.setdefault(s(r[0]), r)
        by_abbr.setdefault(s(r[1]).upper(), r)
    domain_rows = {}
    for d in domains:
        domain_rows.setdefault(s(d[col("C")]).upper(), d)
    bad_domains = {i.key.upper() for i in domain_issues or [] if i.code in DOMAIN_BLOCKING}
    issues = []
    for i, t in enumerate(terms):
        name, abbr, domain = s(t[col("A")]), s(t[col("C")]), s(t[col("E")])
        key, row = abbr or name, i + 2
        inst, by_eng = by_name.get(name), False
        if inst is None and abbr.upper() in by_abbr:
            inst, by_eng = by_abbr[abbr.upper()], True
        if inst is None:
            continue
        target = f"기관표준 {s(inst[0])}({s(inst[1])})"
        d = domain_rows.get(domain.upper())
        inst_length = s(inst[3]).split(",")[0]
        if by_eng and name != s(inst[0]):
            issues.append(Issue("용어", row, key, "I01", target))
        elif s(inst[1]).upper() != abbr.upper():
            issues.append(Issue("용어", row, key, "I02", target))
        elif d is None or domain.upper() in bad_domains or not s(inst[2]):
            continue   # 도메인을 못 보면 타입·길이는 보지 않는다 (완전성 점검에서 이미 오류)
        elif not same_type(d[col("E")], inst[2]):
            issues.append(Issue("용어", row, key, "I03", f"{s(d[col('E')])} ↔ {target} {s(inst[2])}"))
        elif not same_length(d[col("F")], inst_length):
            issues.append(Issue("용어", row, key, "I04", f"{s(d[col('F')])} ↔ {target} {inst_length}"))
    return issues


class _Standard:
    def __init__(self, terms, domains, term_issues):
        self.by_eng, self.by_kor = {}, {}
        for t in terms:
            self.by_eng.setdefault(s(t[col("C")]).upper(), t)
            self.by_kor.setdefault(s(t[col("A")]).upper(), t)
        self.domains = {}
        for d in domains:
            self.domains.setdefault(s(d[col("C")]).upper(), d)
        self.blocked = {i.key.upper() for i in term_issues if i.code in TERM_BLOCKING}

    def compare(self, c: ColumnRow, prefix: str, allow_kor_match: bool, check_kor: bool, length_if_present: bool):
        term = self.by_eng.get(c.eng.upper())
        if term is None and allow_kor_match and c.kor:
            term = self.by_kor.get(c.kor.upper())
        if term is None:
            c.codes.append(f"{prefix}01")
            return
        c.term, c.term_kor, c.domain = s(term[col("C")]), s(term[col("A")]), s(term[col("E")])
        if (c.term or c.term_kor).upper() in self.blocked:
            c.codes.append(f"{prefix}00")
            return
        domain = self.domains.get(c.domain.upper())
        c.domain_type, c.domain_length = s(domain[col("E")]), domain[col("F")]
        if check_kor and c.kor != c.term_kor:
            c.codes.append(f"{prefix}02")
        if allow_kor_match and c.eng.upper() != c.term.upper():
            c.codes.append(f"{prefix}05")   # 한글컬럼명으로 찾았는데 영문컬럼명이 영문약어명과 다름 (p.180)
        if c.data_type.upper() != c.domain_type.upper():
            c.codes.append(f"{prefix}03")
        if not (length_if_present and s(c.length) == "") and val(c.length) != val(c.domain_length):
            c.codes.append(f"{prefix}04")


def run_precheck(domains, terms, words, columns_def, meta_columns=None, length_required=None,
                 matcher=None, common_domains: dict | None = None, inst_rows: list | None = None) -> PrecheckResult:
    """meta_columns: [{'row', 'table', 'kor', 'eng', 'type', 'length'}] (수동등록/기관메타). 없으면 컬럼정의서로 추정.
    matcher: 공통표준 원본이 있으면 기준1(금칙어·준용) 점검도 한다."""
    issues = check_domains(domains, length_required or DEFAULT_LENGTH_REQUIRED)
    issues += check_terms(terms, domains, words, issues)
    if words is not None:
        official = {w.name.upper() for w, forbidden in matcher.words.values() if not forbidden} if matcher else None
        issues += check_words(words, official)
    if matcher is not None:
        issues += check_common(terms, words, matcher, domains, issues, common_domains)
    if inst_rows:   # 그 기관의 기관표준이 있을 때만
        issues += check_inst_terms(terms, domains, inst_rows, issues)
    std = _Standard(terms, domains, [i for i in issues if i.area == "용어"])

    rows = []
    for i, c in enumerate(columns_def):
        r = ColumnRow("컬럼정의서", i + 2, s(c[col("A")]), s(c[col("B")]), s(c[col("C")]), s(c[col("G")]), c[col("H")])
        std.compare(r, "C", allow_kor_match=True, check_kor=True, length_if_present=False)
        rows.append(r)
    meta_rows = []
    for m in meta_columns or []:
        r = ColumnRow("메타", m["row"], s(m["table"]), s(m["kor"]), s(m["eng"]), s(m["type"]), m["length"])
        std.compare(r, "M", allow_kor_match=False, check_kor=False, length_if_present=True)
        meta_rows.append(r)
    for r in rows + meta_rows:
        for code in r.codes:
            issues.append(Issue(r.source, r.row, f"{r.table}.{r.eng}", code))

    basis_rows, basis = (meta_rows, "메타") if meta_columns else (rows, "컬럼정의서(추정)")
    errors = sum(1 for r in basis_rows if any(code in COUNTED for code in r.codes))
    blocking = DOMAIN_BLOCKING | TERM_BLOCKING | WORD_BLOCKING
    completeness = {}
    for area, data in (("도메인", domains), ("용어", terms), ("단어", words)):
        if data is not None:
            bad_rows = {i.row for i in issues if i.area == area and i.code in blocking}
            completeness[area] = (len(data), len(bad_rows))
    return PrecheckResult(issues, rows, meta_rows, basis, len(basis_rows), errors, completeness)
