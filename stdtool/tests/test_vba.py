from stdtool.vba import ColumnFinder, TextDict, clean, clean_text, cstr, last_row, val


def test_val_reads_leading_number_and_ignores_spaces():
    assert val("128") == 128
    assert val(" 1 2 ") == 12
    assert val("10,2") == 10
    assert val("12abc") == 12
    assert val("abc") == 0
    assert val("") == 0
    assert val(None) == 0
    assert val("1.5") == 1.5
    assert val(38.0) == 38


def test_cstr_integral_float():
    assert cstr(100.0) == "100"
    assert cstr(None) == ""
    assert cstr(1.5) == "1.5"


def test_clean_text_keeps_hangul_alnum_upper():
    assert clean_text("생명자원 기관명(코드)_a1") == "생명자원기관명코드A1"
    assert clean_text("CT_NM") == "CTNM"
    assert clean_text("ㄱ자") == "자"


def test_clean_narrows_fullwidth_and_nbsp():
    assert clean("　ＡＢＣ\xa0") == "ABC"
    assert clean("#N/A") == ""
    assert clean(" 법원명 ") == "법원명"


def test_text_dict_is_case_insensitive():
    d = TextDict()
    d["abc"] = 1
    assert "ABC" in d and d["Abc"] == 1


def test_last_row_ignores_trailing_blanks():
    rows = [["a"], [None], ["b"], [""], [None]]
    assert last_row(rows, 0) == 3


def test_column_finder_whole_match_case_insensitive_and_blank():
    finder = ColumnFinder(["순번", "도메인자르기", "도메인분류"], [[1, "NM", "명칭"], [2, "CD", "코드"]], 1, 2)
    assert finder.find("nm") == (True, "명칭")
    assert finder.find("NMC") == (False, None)
    assert finder.find("") == (True, "")
    assert finder.find("C*") == (True, "코드")
