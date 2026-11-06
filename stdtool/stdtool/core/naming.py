"""도메인명 = 분류(Code_tail) + 타입약어(Code_type) + 길이. 매크로 규칙에 ① 도메인 사전을 더한다."""
from collections import Counter
from dataclasses import dataclass, field

from ..config import Settings
from ..dictionary import StandardDict
from ..vba import cstr, s, val

DEFAULT_CLASS = "문자값"


@dataclass
class DomainNamer:
    dicts: StandardDict
    settings: Settings | None = None     # None 이면 매크로 방식
    pool: dict = field(default_factory=dict)  # (분류, 타입, 길이, 소수점) → 기존 도메인명
    unregistered_types: Counter = field(default_factory=Counter)
    korean_classified: Counter = field(default_factory=Counter)
    reused: Counter = field(default_factory=Counter)
    text_fallback: Counter = field(default_factory=Counter)  # (꼬리, 영문명, 한글명) → 꼬리를 못 찾아 문자값이 된 컬럼 수
    counting: bool = True   # 용어 생성 때는 같은 RAW 행을 다시 보므로 집계하지 않는다

    def __post_init__(self):
        self._tail = self.dicts.tail_finder()
        self._type = self.dicts.type_finder()
        self._suffixes = []
        if self.enhanced and self.settings.korean_class:
            classes = self.dicts.tail_classes() | {DEFAULT_CLASS}
            self._suffixes = sorted(
                ((k, v) for k, v in self.settings.korean_suffix.items() if v in classes),
                key=lambda kv: len(kv[0]), reverse=True,
            )

    @property
    def enhanced(self) -> bool:
        return self.settings is not None and self.settings.enhanced

    def classify(self, eng_name, kor_name=None) -> str:
        """영문컬럼명 마지막 '_' 뒤 토큰으로 분류. 못 찾으면 '문자값'."""
        name = cstr(eng_name)
        tail = name[name.rindex("_") + 1:] if "_" in name else name
        found, value = self._tail.find(tail)
        if found:
            return cstr(value)
        if self._suffixes and kor_name:
            kor = cstr(kor_name)
            for suffix, cls in self._suffixes:
                if kor.endswith(suffix):
                    if self.counting:
                        self.korean_classified[(kor, cls)] += 1
                    return cls
        if self.counting:
            self.text_fallback[(tail.upper(), name, cstr(kor_name))] += 1
        return DEFAULT_CLASS

    def type_abbr(self, raw_type) -> str:
        """Code_type에서 약어를 찾고, 없으면 타입명을 그대로 쓴다."""
        if self.enhanced:
            key = s(raw_type).upper()
            if key in self.settings.type_abbr_override:
                return self.settings.type_abbr_override[key]
            if key in self.settings.type_extra:
                return self.settings.type_extra[key]
        found, value = self._type.find(raw_type)
        if found:
            return cstr(value)
        if self.enhanced and self.counting and s(raw_type) != "":
            self.unregistered_types[s(raw_type).upper()] += 1
        return cstr(raw_type)

    def length_text(self, raw_len, scale=None) -> str:
        if s(raw_len) == "" or val(raw_len) == 0:
            return "0"
        text = s(raw_len)
        if self.enhanced and scale:
            text = f"{text}{self.settings.scale_separator}{scale}"
        return text

    def name(self, domain_class, raw_type, raw_len, scale=None) -> str:
        if self.enhanced and self.pool:
            key = pool_key(domain_class, s(raw_type) or "VARCHAR", raw_len, scale)
            if key in self.pool:
                if self.counting:
                    self.reused[self.pool[key]] += 1
                return self.pool[key]
        return f"{domain_class}{self.type_abbr(raw_type)}{self.length_text(raw_len, scale)}"


def pool_key(domain_class, data_type, length, scale) -> tuple:
    return (cstr(domain_class), s(data_type).upper(), val(length), int(val(scale)) if s(scale) else 0)
