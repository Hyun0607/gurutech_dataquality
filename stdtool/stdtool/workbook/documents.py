"""문서 글자 뽑기: RFP(hwpx·hwp), 완료·감리보고서(pdf). 본문은 화면·결과 판정에만 쓰고 저장하지 않는다.

반환은 문단 목록 [Para(글자, 위치)]. 위치는 pdf면 'p.27', 한글 파일이면 '문단 312'.
"""
import re
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

SUFFIXES = (".hwpx", ".hwp", ".pdf")


class DocumentError(Exception):
    pass


@dataclass
class Para:
    text: str
    where: str
    page: int | None = None


def read_document(path) -> list:
    path = Path(path)
    kind = path.suffix.lower()
    try:
        if kind == ".hwpx":
            paras = _hwpx(path)
        elif kind == ".hwp":
            paras = _hwp(path)
        elif kind == ".pdf":
            paras = _pdf(path)
        else:
            raise DocumentError(f"읽을 수 있는 문서는 hwpx·hwp·pdf입니다: {path.name}")
    except DocumentError:
        raise
    except Exception as e:
        raise DocumentError(f"문서를 읽지 못했습니다 ({path.name}): {e}") from e
    paras = [p for p in paras if p.text]
    if not paras:
        raise DocumentError(f"글자를 찾지 못했습니다 ({path.name}). 암호가 걸렸거나 그림으로만 된 문서일 수 있습니다.")
    return paras


def _clean(text: str) -> str:
    text = re.sub(r"[-]", "", text.replace(" ", " "))   # pdf·한글 글머리 기호(사용자 정의 영역 글자)는 지운다
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# hwpx (zip + OWPML)
# ---------------------------------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hwpx(path: Path) -> list:
    out = []
    with zipfile.ZipFile(path) as z:
        names = sorted((n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)),
                       key=lambda n: int(re.search(r"(\d+)", n).group(1)))
        for name in names:
            root = ElementTree.fromstring(z.read(name))
            for p in root.iter():
                if _local(p.tag) != "p":
                    continue
                # 문단 자신의 글자만 (표 안 문단은 따로 나온다): p > run > t
                parts = []
                for run in p:
                    if _local(run.tag) != "run":
                        continue
                    for t in run:
                        if _local(t.tag) == "t":
                            parts.append("".join(t.itertext()))
                text = _clean("".join(parts))
                if text:
                    out.append(Para(text, f"문단 {len(out) + 1}"))
    return out


# ---------------------------------------------------------------------------
# hwp (HWP 5.0: OLE + 압축된 BodyText/SectionN 레코드)
# ---------------------------------------------------------------------------

PARA_TEXT = 67                       # HWPTAG_BEGIN(16) + 51
WIDE_CONTROLS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}   # 8글자(16바이트) 차지


def _para_text(data: bytes) -> str:
    """UTF-16 글자는 바이트로 모아 한 번에 푼다 (한자·기호의 서로게이트 쌍이 깨지지 않게)."""
    buf, i = bytearray(), 0
    while i + 1 < len(data):
        code = struct.unpack_from("<H", data, i)[0]
        if code in WIDE_CONTROLS:
            i += 16
            continue
        if code in (10, 13):
            buf += b" \x00"
        elif code >= 32:
            buf += data[i:i + 2]
        i += 2
    return buf.decode("utf-16-le", errors="ignore")


def _hwp(path: Path) -> list:
    import olefile
    if not olefile.isOleFile(str(path)):
        raise DocumentError(f"한글(hwp) 5.0 파일이 아닙니다: {path.name}")
    out = []
    with olefile.OleFileIO(str(path)) as ole:
        header = ole.openstream("FileHeader").read()
        flags = struct.unpack_from("<I", header, 36)[0]
        if flags & 0x2:
            raise DocumentError(f"암호가 걸린 한글 파일입니다: {path.name}")
        if flags & 0x4:
            raise DocumentError(f"배포용(복사 방지) 한글 파일이라 글자를 읽을 수 없습니다: {path.name}. hwpx나 pdf로 저장해 주세요.")
        compressed = bool(flags & 0x1)
        sections = sorted((e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText"),
                          key=lambda e: int(re.search(r"(\d+)", e[1]).group(1)))
        for entry in sections:
            data = ole.openstream(entry).read()
            if compressed:
                data = zlib.decompress(data, -15)
            i = 0
            while i + 4 <= len(data):
                head = struct.unpack_from("<I", data, i)[0]
                tag, size = head & 0x3FF, (head >> 20) & 0xFFF
                i += 4
                if size == 0xFFF:
                    size = struct.unpack_from("<I", data, i)[0]
                    i += 4
                if tag == PARA_TEXT:
                    text = _clean(_para_text(data[i:i + size]))
                    if text:
                        out.append(Para(text, f"문단 {len(out) + 1}"))
                i += size
    return out


# ---------------------------------------------------------------------------
# pdf
# ---------------------------------------------------------------------------

def _pdf(path: Path) -> list:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise DocumentError(f"암호가 걸린 pdf입니다: {path.name}")
    out = []
    for n, page in enumerate(reader.pages, 1):
        for line in (page.extract_text() or "").splitlines():
            text = _clean(line)
            if text:
                out.append(Para(text, f"p.{n}", n))
    return out
