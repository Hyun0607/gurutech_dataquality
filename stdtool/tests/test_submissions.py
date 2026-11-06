"""완료단계 제출 파일: 보고서 + IRM 산출물(이름) + zip(윈도우 한글 이름) + 폴더, 판정에서 산출물로 인정."""
import zipfile

from stdtool.core import preventive_check as pc
from stdtool.workbook import preventive_report as report
from stdtool.workbook import submissions as sb


def _windows_zip(path, names):
    """윈도우 탐색기처럼 한글 이름을 cp949로, UTF-8 표시 없이 쓴 zip."""
    original = zipfile.ZipInfo._encodeFilenameFlags
    zipfile.ZipInfo._encodeFilenameFlags = lambda self: (self.filename.encode("cp949"), self.flag_bits & ~0x800)
    try:
        with zipfile.ZipFile(path, "w") as z:
            for n in names:
                z.writestr(n, b"x")
    finally:
        zipfile.ZipInfo._encodeFilenameFlags = original


def test_zip_member_names_are_korean(tmp_path):
    path = tmp_path / "IRM 산출물.zip"
    _windows_zip(path, ["산출물/OO시_DB표준용어.xlsx", "산출물/테이블정의서.xlsx"])
    sub = sb.read_submitted(path)
    assert [n.split("/")[-1] for n in sub.names] == ["OO시_DB표준용어.xlsx", "테이블정의서.xlsx"]
    assert "압축 파일 · 파일 2개" in sub.note and not sub.docs


def test_folder_expands_and_skips_temp_files(tmp_path):
    (tmp_path / "a").mkdir()
    for n in ("a/컬럼정의서.xlsx", "a/~$컬럼정의서.xlsx", "b.pptx"):
        (tmp_path / n).write_bytes(b"x")
    got = sb.expand([tmp_path / "a", tmp_path / "b.pptx", tmp_path / "a"])
    assert [p.split("\\")[-1].split("/")[-1] for p in got] == ["컬럼정의서.xlsx", "b.pptx"]
    sub = sb.read_submitted(got[0])
    assert sub.note.startswith("IRM 산출물") and sub.names == [got[0]]


def test_broken_document_falls_back_to_name(tmp_path):
    path = tmp_path / "품질진단 결과보고서.pdf"
    path.write_bytes(b"not a pdf")
    sub = sb.read_submitted(path)
    assert not sub.docs and sub.names == [str(path)] and "파일 이름으로" in sub.note


def test_reports_first_in_combine():
    a = sb.Submitted("x/산출물설명.pdf", docs=[("산출물설명.pdf", [])], names=["x/산출물설명.pdf"])
    b = sb.Submitted("x/사업 완료보고서.pdf", docs=[("사업 완료보고서.pdf", [])], names=["x/사업 완료보고서.pdf"])
    docs, files = sb.combine([a, b])
    assert [d[0] for d in docs] == ["사업 완료보고서.pdf", "산출물설명.pdf"] and len(files) == 2


def test_irm_output_counts_without_report(tmp_path):
    """완료보고서에 없어도 IRM 산출물 이름으로 지표를 인정한다 (1.1 표준용어 → 1.1(1) Y, 1.1(2)는 '-')."""
    criteria = report.load_criteria()
    _windows_zip(tmp_path / "irm.zip", ["OO시_DB표준용어.xlsx"])
    docs, files = sb.combine([sb.read_submitted(tmp_path / "irm.zip")])
    details = {d.code: d for d in pc.judge_details(docs, files, ["1.1", "2.1"], [], criteria)}
    assert details["1.1(1)"].status == "Y" and "OO시_DB표준용어.xlsx" in details["1.1(1)"].evidence
    assert details["1.1(2)"].status == "-" and details["1.1(2)"].covered_by == "1.1(1)"
    assert details["2.1(1)"].status == "N" and details["2.1(2)"].status == "N"


def test_same_content_is_added_once(tmp_path):
    """복사본·이름만 바꾼 파일·같은 번에 두 번 넣은 파일은 한 번만 (내용 지문으로 비교)."""
    (tmp_path / "a").mkdir()
    report_ = tmp_path / "사업 완료보고서.pdf"
    report_.write_bytes(b"same report")
    (tmp_path / "a" / "완료보고서_사본.pdf").write_bytes(b"same report")
    (tmp_path / "a" / "테이블정의서.xlsx").write_bytes(b"other")
    fresh, skipped = sb.new_files([report_, tmp_path / "a", report_], set())
    assert [p.split("\\")[-1].split("/")[-1] for p, _ in fresh] == ["사업 완료보고서.pdf", "테이블정의서.xlsx"]
    assert skipped == ["완료보고서_사본.pdf"]
    have = {d for _, d in fresh}
    again, skipped = sb.new_files([tmp_path / "a" / "완료보고서_사본.pdf"], have)
    assert again == [] and skipped == ["완료보고서_사본.pdf"]
    assert sb.read_submitted(report_).digest in have


def test_outputs_with_same_content_but_other_names_are_kept(tmp_path):
    """이름으로 알아보는 산출물은 내용이 같아도 이름이 다르면 따로 (같은 이름의 사본만 중복)."""
    (tmp_path / "copy").mkdir()
    for n in ("DB표준용어.xlsx", "테이블정의서.xlsx", "copy/테이블정의서.xlsx"):
        (tmp_path / n).write_bytes(b"x")
    fresh, skipped = sb.new_files([tmp_path / "DB표준용어.xlsx", tmp_path / "테이블정의서.xlsx", tmp_path / "copy"], set())
    assert len(fresh) == 2 and skipped == ["테이블정의서.xlsx"]
