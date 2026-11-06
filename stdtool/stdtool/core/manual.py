"""메타_작업_전체: 컬럼정의서 → 메타, 수동등록 양식 값 수정."""
from ..model import MANUAL_COLS, META_COLS, blank_row, col
from ..vba import last_row, s

PUBLIC_CODES = {"공개": "01", "비공개": "02", "부분공개": "03"}
REASON_CODES = {
    "제 1 호 (법령상의 비밀·비공개 정보)": "01",
    "제 2 호 (안보·국방·통일·외교 관련 정보)": "02",
    "제 3 호 (국민의 생명·신체·재산 보호 침해 관련 정보)": "03",
    "제 4 호 (재판·수사 등 관련 정보)": "04",
    "제 5 호 (감사·감독·계약·의사결정 관련 정보 등)": "05",
    "제 6 호 (이름·주민등록번호 등 개인정보)": "06",
    "제 7 호 (법인의 경영·영업비밀 정보)": "07",
    "제 8 호 (부동산 투기·매점매석 등 관련 정보)": "08",
    "기타(로그 및 임시백업 등)": "09",
}
# 수동등록에서 텍스트 서식(@)으로 두는 열
MANUAL_TEXT_COLS = {col(x) for x in ("B", "E", "S", "T", "AC")}


def copy_definitions_to_meta(meta: list, columns_def: list) -> list:
    """컬럼정의서_메타_시트_복사: 컬럼정의서 B:C → 메타 AI:AJ, G:H → AO:AP (행 순서대로)."""
    count = last_row(columns_def, col("B"))
    if count < 1:
        raise ValueError("컬럼정의서에 2행 이상의 데이터가 없습니다.")
    meta = [list(r) for r in meta]
    while len(meta) < count:
        meta.append(blank_row(META_COLS))
    for k in range(count):
        c = columns_def[k]
        meta[k][col("AI")], meta[k][col("AJ")] = c[col("B")], c[col("C")]
        meta[k][col("AO")], meta[k][col("AP")] = c[col("G")], c[col("H")]
    return meta


def build_manual(meta: list) -> list:
    """수동등록_값_수정: 메타 → 수동등록 양식 열 배치와 코드값 치환."""
    count = last_row(meta, col("B"))
    if count < 1:
        raise ValueError("메타 시트에 4행 이상의 데이터가 없습니다.")
    rows = []
    for m in meta[:count]:
        r = blank_row(MANUAL_COLS)
        r[col("C")], r[col("D")] = m[col("B")], m[col("C")]
        r[col("G")], r[col("H")] = m[col("O")], m[col("P")]
        src = m[col("R"): col("AT") + 1]
        r[col("I"): col("I") + len(src)] = src
        r[col("B")] = "F"
        r[col("E")] = "01"
        r[col("S")] = PUBLIC_CODES.get(s(r[col("S")]), r[col("S")])
        r[col("T")] = REASON_CODES.get(s(r[col("T")]), r[col("T")])
        r[col("AC")] = REASON_CODES.get(s(r[col("AC")]), r[col("AC")])
        r[col("X")] = None
        rows.append(r[:MANUAL_COLS])
    return rows
