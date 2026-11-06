"""3) 기관표준 매핑, 4) 공통표준 매핑, 7) DB표준 적용."""
from ..dictionary import Sheet
from ..model import ChangeLog
from ..vba import TextDict, clean, clean_text, last_row
from .cleanse import C, D, E, F, G, parse_scale

_A, _B, _C, _D = range(4)


def _build(std: Sheet, normalize):
    kor_to_eng, eng_to_kor, eng_to_type = TextDict(), TextDict(), TextDict()
    for row in std.rows[: last_row(std.rows, _A)]:
        k, e = normalize(row[_A]), normalize(row[_B])
        if len(k) > 0:
            kor_to_eng[k] = e
        if len(e) > 0:
            eng_to_kor[e] = k
            eng_to_type[e] = (row[_C], row[_D])
    return kor_to_eng, eng_to_kor, eng_to_type


def _apply(raw, std, normalize, step, log, update_eng_after_write):
    kor_to_eng, eng_to_kor, eng_to_type = _build(std, normalize)
    for i, row in enumerate(raw[: last_row(raw, C)]):
        raw_k, raw_e = normalize(row[C]), normalize(row[D])
        flag_kor, flag_eng = raw_k in kor_to_eng, raw_e in eng_to_kor
        if flag_eng and not flag_kor:
            new = eng_to_kor[raw_e]
            log.changed(step, "RAW", i + 2, "한글 컬럼명", row[C], new, "영문명 일치 → 표준 한글명")
            row[C] = new
        elif flag_kor and not flag_eng:
            new = kor_to_eng[raw_k]
            log.changed(step, "RAW", i + 2, "영문 컬럼명", row[D], new, "한글명 일치 → 표준 영문명")
            row[D] = new
            if update_eng_after_write:
                raw_e = new
        elif flag_kor and flag_eng:
            new = eng_to_kor[raw_e]
            log.changed(step, "RAW", i + 2, "한글 컬럼명", row[C], new, "영문명 일치 → 표준 한글명")
            row[C] = new

        if raw_e in eng_to_type:
            data_type, length = eng_to_type[raw_e]
            log.changed(step, "RAW", i + 2, "데이터 타입", row[E], data_type, "표준 타입 적용")
            log.changed(step, "RAW", i + 2, "데이터 길이", row[F], length, "표준 길이 적용")
            row[E], row[F] = data_type, length
            row[G] = parse_scale(length)


def inst_mapping(raw: list, inst: Sheet, inst_std: str, log: ChangeLog) -> None:
    """기관표준_매핑: 기관표준여부가 Y일 때만 실행 (N이면 건너뜀)."""
    flag = clean_text(inst_std)
    if flag == "N":
        return
    if flag != "Y":
        raise ValueError("기관표준여부 값을 확인해주세요.(Y or N)")
    if last_row(inst.rows, _A) < 1:
        return
    _apply(raw, inst, clean_text, "기관표준 매핑", log, update_eng_after_write=False)


def common_mapping(raw: list, common: Sheet, log: ChangeLog) -> None:
    """공통표준_매핑: 기관표준 매핑 뒤에 실행되어 같은 컬럼을 다시 덮어쓸 수 있다."""
    _apply(raw, common, clean, "공통표준 매핑", log, update_eng_after_write=True)


def apply_dbstd(raw: list, terms: list, log: ChangeLog) -> None:
    """DB표준_적용: 2_용어의 한글명 → 영문명, 이어서 영문명 → 한글명을 RAW에 반영."""
    TA, TC = 0, 2
    kor_to_eng, eng_to_kor = TextDict(), TextDict()
    for row in terms[: last_row(terms, TA)]:
        k, e = clean(row[TA]), clean(row[TC])
        if k != "":
            kor_to_eng[k] = e
        if e != "":
            eng_to_kor[e] = k

    count = last_row(raw, C)
    for i, row in enumerate(raw[:count]):
        k = clean(row[C])
        if k in kor_to_eng:
            new = kor_to_eng[k]
            log.changed("DB표준 적용", "RAW", i + 2, "영문 컬럼명", row[D], new, "DB표준용어 한글명 일치")
            row[D] = new
    for i, row in enumerate(raw[:count]):
        e = clean(row[D])
        if e in eng_to_kor:
            new = eng_to_kor[e]
            log.changed("DB표준 적용", "RAW", i + 2, "한글 컬럼명", row[C], new, "DB표준용어 영문명 일치")
            row[C] = new
