"""프로그램이 쓰는 위치: 사용자 폴더(%APPDATA%\\stdtool)와 프로그램에 같이 넣은 파일.

exe(PyInstaller)로 묶여도 패키지 파일은 __file__ 기준 같은 상대 위치에 있다.
"""
import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BUNDLED_DICT = PACKAGE_DIR / "data" / "std_dict.sqlite"   # 배포할 때 같이 넣는 사전 파일
DICT_NAME = "std_dict.sqlite"
HISTORY_NAME = "history.sqlite"


def user_dir() -> Path:
    """설정·사전 파일·회차 기록을 두는 사용자 폴더. STDTOOL_HOME으로 바꿀 수 있다 (테스트)."""
    base = os.environ.get("STDTOOL_HOME") or os.path.join(os.environ.get("APPDATA") or Path.home(), "stdtool")
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def frozen() -> bool:
    """exe로 실행 중인지."""
    return getattr(sys, "frozen", False)
