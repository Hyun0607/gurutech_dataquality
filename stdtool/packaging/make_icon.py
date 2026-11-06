"""프로그램 아이콘 만들기 (한 번): 파란 둥근 사각형에 흰 체크 표시 → ui/assets/app.png, app.ico."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "stdtool" / "ui" / "assets"


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2563EB"))
    m = size * 0.06
    p.drawRoundedRect(QRectF(m, m, size - 2 * m, size - 2 * m), size * 0.22, size * 0.22)
    # 표 줄 세 개 + 체크 표시
    p.setBrush(QColor(255, 255, 255, 110))
    for i in range(3):
        y = size * (0.30 + 0.15 * i)
        p.drawRoundedRect(QRectF(size * 0.24, y, size * 0.30, size * 0.07), size * 0.03, size * 0.03)
    pen = QPen(QColor("#FFFFFF"), size * 0.09, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(size * 0.52, size * 0.58))
    path.lineTo(QPointF(size * 0.62, size * 0.69))
    path.lineTo(QPointF(size * 0.79, size * 0.44))
    p.drawPath(path)
    p.end()
    return image


def save_ico(path: Path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    """PNG를 담은 ICO (Windows Vista 이상)."""
    import struct
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    blobs = []
    for s in sizes:
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        draw(s).save(buf, "PNG")
        blobs.append((s, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, body = b"", b""
    for s, blob in blobs:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(blob), offset + len(body))
        body += blob
    path.write_bytes(header + entries + body)


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    draw(256).save(str(ASSETS / "app.png"))
    save_ico(ASSETS / "app.ico")
    print(ASSETS / "app.png", ASSETS / "app.ico")
