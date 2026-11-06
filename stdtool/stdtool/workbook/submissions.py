"""완료단계 제출 파일 모으기: 완료·감리보고서 + IRM에 등록한 산출물 (여러 번 나눠 넣어도 쌓인다).

- 보고서·문서(pdf·hwp·hwpx)는 본문을 읽어 지표 수행 내역을 찾는다.
- 그 밖의 파일(xlsx·pptx·docx·그림 등)은 파일 이름으로 산출물을 알아본다.
- zip은 안의 파일 이름을 모두 보고, 안에 든 보고서·문서는 본문도 읽는다.
- 폴더는 안의 파일 전부.
"""
import hashlib
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .documents import SUFFIXES, DocumentError, read_document

REPORT = re.compile(r"완료\s*보고|감리|결과\s*보고")


@dataclass
class Submitted:
    path: str                                   # 넣은 파일 (zip이면 zip 파일)
    docs: list = field(default_factory=list)    # [(이름, [Para])] 본문을 읽은 문서
    names: list = field(default_factory=list)   # 산출물 이름으로 볼 파일 (zip 안 파일 포함)
    note: str = ""                              # 화면에 보일 구분
    digest: str = ""                            # 파일 내용 지문 (이름·위치가 달라도 같은 파일이면 같다)

    @property
    def name(self) -> str:
        return Path(self.path).name


def expand(paths) -> list:
    """넣은 경로들 → 파일 경로 (폴더는 안의 파일 전부, 엑셀 임시 파일 '~$'는 뺀다)."""
    out = []
    for p in map(Path, paths):
        items = sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
        out += [str(x) for x in items if not x.name.startswith("~$")]
    return list(dict.fromkeys(out))


def digest(path) -> str:
    """중복 판단 지문. 본문을 읽는 문서·zip은 내용만 (복사본·이름만 바꾼 보고서도 같은 파일),
    파일 이름으로 알아보는 산출물(xlsx 등)은 내용 + 이름 (이름이 다르면 다른 근거가 될 수 있다)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    path = Path(path)
    if path.suffix.lower() not in SUFFIXES + (".zip",):
        h.update(path.name.lower().encode("utf-8"))
    return h.hexdigest()


def new_files(paths, have: set) -> tuple:
    """넣은 경로들 중 아직 없는 파일 → ([(경로, 지문)], [건너뛴 파일 이름]).
    have = 이미 넣은 파일의 지문. 같은 번에 같은 파일이 두 번 와도 한 번만."""
    seen, fresh, skipped = set(have), [], []
    for f in expand(paths):
        d = digest(f)
        if d in seen:
            skipped.append(Path(f).name)
            continue
        seen.add(d)
        fresh.append((f, d))
    return fresh, skipped


def _member_name(info: zipfile.ZipInfo) -> str:
    """윈도우에서 만든 zip은 한글 이름이 cp949인데 표시(UTF-8 flag)가 없어 cp437로 읽힌다."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def _read_zip(path: Path) -> Submitted:
    sub = Submitted(str(path))
    unread = 0
    with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory() as tmp:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = _member_name(info)
            base = Path(name).name
            if base.startswith("~$"):
                continue
            sub.names.append(f"{path.name}/{name}")
            if Path(base).suffix.lower() in SUFFIXES:
                target = Path(tmp) / f"{len(sub.names)}{Path(base).suffix.lower()}"
                target.write_bytes(z.read(info))
                try:
                    sub.docs.append((base, read_document(target)))
                except DocumentError:
                    unread += 1
    sub.note = f"압축 파일 · 파일 {len(sub.names)}개 (본문 읽은 문서 {len(sub.docs)}개" + \
               (f", 못 읽은 문서 {unread}개" if unread else "") + ")"
    return sub


def read_submitted(path, file_digest: str = "") -> Submitted:
    """파일 하나 읽기. 본문을 못 읽는 문서(그림뿐인 pdf 등)는 파일 이름으로만 본다."""
    sub = _read(Path(path))
    sub.digest = file_digest or digest(path)
    return sub


def _read(path: Path) -> Submitted:
    kind = path.suffix.lower()
    if kind == ".zip":
        try:
            return _read_zip(path)
        except zipfile.BadZipFile:
            return Submitted(str(path), names=[str(path)], note="압축을 풀지 못함 · 파일 이름으로")
    sub = Submitted(str(path), names=[str(path)])
    if kind in SUFFIXES:
        try:
            paras = read_document(path)
            sub.docs.append((path.name, paras))
            sub.note = f"본문 읽음 · {len(paras):,}문단"
        except DocumentError:
            sub.note = "본문을 못 읽음 (그림·암호) · 파일 이름으로"
    else:
        sub.note = "IRM 산출물 · 파일 이름으로"
    return sub


def combine(subs: list) -> tuple:
    """판정에 넘길 (docs, files). 완료·감리보고서를 앞에 두어 근거가 보고서 쪽 번호로 먼저 나오게 한다."""
    docs = [d for s in subs for d in s.docs]
    docs.sort(key=lambda d: not REPORT.search(d[0]))
    files = [n for s in subs for n in s.names]
    return docs, files


def summary(subs: list) -> str:
    docs, files = combine(subs)
    return f"제출 파일 {len(subs)}개 (본문 읽은 문서 {len(docs)}개 · 산출물 이름 {len(files)}개)"
