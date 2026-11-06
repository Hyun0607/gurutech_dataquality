"""매크로와 같은 결과를 내기 위한 VBA 내장 함수·Excel 동작 재현."""
import fnmatch
import re

EXCEL_ERRORS = {"#N/A", "#VALUE!", "#REF!", "#DIV/0!", "#NUM!", "#NAME?", "#NULL!", "#GETTING_DATA"}


def cstr(value) -> str:
    """CStr: 빈 셀은 "", 정수형 실수는 소수점 없이."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def trim(text: str) -> str:
    """VBA Trim은 공백 문자(' ')만 제거한다."""
    return text.strip(" ")


def s(value) -> str:
    """Trim(CStr(x))."""
    return trim(cstr(value))


def ucase(text: str) -> str:
    return text.upper()


_VAL_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?")


def val(value):
    """VBA Val: 공백을 무시하고 앞쪽 숫자만 읽는다. 읽을 수 없으면 0."""
    if isinstance(value, bool):
        return -1 if value else 0
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = re.sub(r"[ \t\r\n]", "", cstr(value))
        match = _VAL_NUMBER.match(text)
        if not match:
            return 0
        number = float(match.group(0).replace("d", "e").replace("D", "e"))
    return int(number) if number.is_integer() else number


def is_empty(value) -> bool:
    """셀이 비었는지 (End(xlUp) 기준). VBA가 ""를 넣은 셀도 빈 셀이다."""
    return value is None or (isinstance(value, str) and value == "")


def clean_text(value) -> str:
    """매크로 CleanText: 한글(가~힣)·영문·숫자만 남기고 대문자로."""
    out = []
    for ch in cstr(value):
        if "가" <= ch <= "힣" or "A" <= ch <= "Z" or "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch.upper())
    return "".join(out)


def narrow(text: str) -> str:
    """StrConv(x, vbNarrow): 전각 ASCII·전각 공백을 반각으로."""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def clean(value) -> str:
    """매크로 Clean: 오류값은 "", 반각 변환·NBSP 치환 후 Trim."""
    if isinstance(value, str) and value in EXCEL_ERRORS:
        return ""
    return trim(narrow(cstr(value)).replace("\xa0", " "))


def norm_key(value) -> str:
    """vbTextCompare 딕셔너리 키 (대소문자 무시)."""
    return cstr(value).upper()


class TextDict:
    """CompareMode = vbTextCompare 인 Scripting.Dictionary."""

    def __init__(self):
        self._data = {}

    def __setitem__(self, key, value):
        self._data[norm_key(key)] = value

    def __getitem__(self, key):
        return self._data[norm_key(key)]

    def __contains__(self, key):
        return norm_key(key) in self._data

    def get(self, key, default=None):
        return self._data.get(norm_key(key), default)

    def items(self):
        return self._data.items()

    def __len__(self):
        return len(self._data)


def last_row(rows, col: int) -> int:
    """Cells(Rows.Count, col).End(xlUp): 해당 열에 값이 있는 마지막 행까지의 개수."""
    for i in range(len(rows) - 1, -1, -1):
        if not is_empty(rows[i][col]):
            return i + 1
    return 0


class ColumnFinder:
    """Columns("B").Find(What, LookIn:=xlValues, LookAt:=xlWhole) 후 Offset(0, n).Value.

    대소문자 무시, 와일드카드(*, ?) 허용, 빈 문자열은 첫 빈 셀을 찾는다(그 옆 값은 빈 값).
    검색은 2행부터 아래로, 머리글(1행)은 마지막에 본다.
    """

    def __init__(self, header, rows, key_col: int, value_col: int):
        self._entries = [(cstr(r[key_col]), r[value_col]) for r in rows]
        self._entries.append((cstr(header[key_col]), header[value_col]))
        self._exact = {}
        for key, value in self._entries:
            self._exact.setdefault(key.upper(), value)

    def find(self, what):
        """찾으면 (True, 값), 못 찾으면 (False, None)."""
        what = cstr(what)
        if what == "":
            return True, ""
        if "*" in what or "?" in what:
            pattern = what.upper()
            for key, value in self._entries:
                if fnmatch.fnmatchcase(key.upper(), pattern):
                    return True, value
            return False, None
        key = what.upper()
        if key in self._exact:
            return True, self._exact[key]
        return False, None
