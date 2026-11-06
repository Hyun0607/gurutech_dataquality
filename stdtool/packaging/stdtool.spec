# PyInstaller 설정: 폴더형 exe (dist/stdtool/stdtool.exe). 만들기는 packaging/build.py.
# 쓰는 Qt는 QtCore·QtGui·QtWidgets(+ 아이콘용 QtSvg)뿐이라 나머지 큰 모듈은 뺀다.
from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG = ROOT / "stdtool"

datas = [
    (str(PKG / "templates"), "stdtool/templates"),
    (str(PKG / "ui" / "assets"), "stdtool/ui/assets"),
    (str(PKG / "data" / "std_dict.sqlite"), "stdtool/data"),
]

EXCLUDES = [
    "tkinter", "unittest", "pydoc_data", "pandas", "numpy", "matplotlib", "IPython", "pytest",
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtUiTools", "PySide6.QtXml", "PySide6.QtSpatialAudio", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtHttpServer", "PySide6.QtNfc",
]

a = Analysis(
    [str(ROOT / "packaging" / "stdtool_gui.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["keyring.backends.Windows", "win32ctypes.pywin32.win32cred", "pymysql", "cryptography"],
    excludes=EXCLUDES,
    noarchive=False,
)

# Qt 번역 파일·쓰지 않는 플러그인 DLL도 뺀다 (이미지는 svg·png·ico만)
KEEP_IMAGE = ("qsvg", "qico", "qjpeg", "qgif")
def wanted(entry):
    name = entry[0].replace("\\", "/")
    if "/translations/" in name:
        return False
    if "/plugins/imageformats/" in name:
        return any(k in name for k in KEEP_IMAGE)
    for skip in ("/plugins/multimedia", "/plugins/position", "/plugins/sqldrivers", "/plugins/qmltooling",
                 "/plugins/networkinformation", "/plugins/tls", "/plugins/generic", "opengl32sw.dll",
                 "Qt6Network", "Qt6Qml", "Qt6Quick", "Qt6Pdf", "Qt6OpenGL", "Qt6VirtualKeyboard"):
        if skip in name:
            return False
    return True

a.binaries = [b for b in a.binaries if wanted(b)]
a.datas = [d for d in a.datas if wanted(d)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="stdtool",
    icon=str(PKG / "ui" / "assets" / "app.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="stdtool", upx=False)
