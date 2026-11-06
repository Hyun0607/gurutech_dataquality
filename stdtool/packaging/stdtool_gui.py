"""exe 시작점 (PyInstaller): 패키지 밖에서 화면을 띄운다."""
import sys

from stdtool.ui.app import main

if __name__ == "__main__":
    sys.exit(main())
