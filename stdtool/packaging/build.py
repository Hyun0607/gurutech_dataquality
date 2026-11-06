"""배포본 만들기: 사전 파일 → exe 폴더 → zip.

  uv run python packaging/build.py [--config config.toml] [--skip-dict]

1. MySQL 사전으로 stdtool/data/std_dict.sqlite 를 새로 만든다 (--skip-dict 이면 있는 파일 그대로).
2. PyInstaller로 dist/stdtool/ 폴더(stdtool.exe)를 만든다.
3. 설치 안내서를 넣고 dist/stdtool_v{버전}.zip 으로 묶는다.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stdtool import __version__, db  # noqa: E402
from stdtool.config import load_settings  # noqa: E402
from stdtool.paths import BUNDLED_DICT  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config.toml"))
    parser.add_argument("--skip-dict", action="store_true", help="사전 파일을 새로 만들지 않음")
    args = parser.parse_args()

    if not args.skip_dict:
        settings = load_settings(Path(args.config))
        with db.connect(settings.db) as conn:
            d = settings.db
            info = db.export_file(conn, BUNDLED_DICT, f"MySQL {d.host}:{d.port}/{d.database}")
        print(f"[1/3] 사전 파일: {db.dict_label(info)}")
    elif not BUNDLED_DICT.exists():
        sys.exit(f"사전 파일이 없습니다: {BUNDLED_DICT}")
    else:
        print(f"[1/3] 사전 파일 그대로: {db.dict_label(db.read_dict_info(BUNDLED_DICT))}")

    dist, work = ROOT / "dist", ROOT / "build"
    print("[2/3] exe 만들기 (PyInstaller)")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(dist),
                    "--workpath", str(work), str(ROOT / "packaging" / "stdtool.spec")], check=True)
    folder = dist / "stdtool"
    shutil.copyfile(ROOT / "packaging" / "설치 안내.txt", folder / "설치 안내.txt")

    archive = dist / f"stdtool_v{__version__}"
    print(f"[3/3] 묶기: {archive}.zip")
    shutil.make_archive(str(archive), "zip", dist, "stdtool")
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) / 1e6
    print(f"완료: {folder} ({size:.0f}MB), {archive}.zip ({Path(str(archive) + '.zip').stat().st_size / 1e6:.0f}MB)")


if __name__ == "__main__":
    main()
