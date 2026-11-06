"""화면 실행: stdtool-gui (또는 python -m stdtool.ui.app)."""
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import theme
from .main_window import MainWindow


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("stdtool")
    app.setOrganizationName("stdtool")
    theme.apply(app)
    app.setWindowIcon(QIcon(theme.asset("app.png")))
    window = MainWindow()
    window.show()
    QTimer.singleShot(300, window.check_dict_update)   # 창이 뜬 뒤 공유 폴더의 새 사전 확인
    if shot := os.environ.get("STDTOOL_SELFTEST"):      # 배포본 확인: 화면을 그림으로 남기고 닫는다
        if out := os.environ.get("STDTOOL_SELFTEST_OUT"):   # 실행까지: 산출물은 이 폴더로, 설정은 저장하지 않음
            window.cfg.output_dir, window.cfg.save = out, lambda: None
            QTimer.singleShot(1500, window.run)
            _wait_run(app, window, shot)
        else:
            QTimer.singleShot(2500, lambda: (_selftest(window, shot), app.quit()))
    return app.exec()


def _wait_run(app, window, shot: str, tries: int = 600):
    if window.outcome is None and window._thread is None or window._thread and window._thread.isRunning():
        if tries:
            QTimer.singleShot(1000, lambda: _wait_run(app, window, shot, tries - 1))
            return
    window.go("history")
    _selftest(window, shot)
    app.quit()


def _selftest(window, path: str):
    from .. import db
    window.grab().save(path)
    cfg = window.cfg
    from ..paths import BUNDLED_DICT
    lines = [f"bundled={db.dict_label(db.read_dict_info(BUNDLED_DICT)) if BUNDLED_DICT.exists() else None}",
             f"dict_source={cfg.dict_source}", f"dict={cfg.dict_text()}", f"entries={len(window.entries)}",
             f"keyring_ok={db.saved_password(cfg.db_settings_mysql()) is not None}"]
    try:
        import cryptography  # noqa: F401
        lines.append("cryptography=ok")
    except ImportError:
        lines.append("cryptography=missing")
    if window.outcome is not None:
        lines += [f"outcome_folder={window.outcome.folder}", *(f"file={p}" for p in window.outcome.paths)]
    lines.append(f"status={window.status.currentMessage()}")
    with open(path + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
