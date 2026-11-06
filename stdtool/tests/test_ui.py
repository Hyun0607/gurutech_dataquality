"""화면: 실제 BRIS 실행 결과로 모든 화면을 그려 본다 (창은 띄우지 않음)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from conftest import COMMON_DIR, MACRO_XLSM  # noqa: E402
from test_parity_bris_real import META  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    from stdtool.ui import theme
    instance = QApplication.instance() or QApplication([])
    theme.apply(instance)
    return instance


@pytest.fixture(scope="module")
def window(app, tmp_path_factory):
    if not (MACRO_XLSM.exists() and META.exists()):
        pytest.skip("매크로 파일 또는 BRIS 메타 없음")
    from stdtool.service import execute
    from stdtool.ui.main_window import MainWindow
    from stdtool.ui.settings import AppConfig
    cfg = AppConfig(org_name="한국농업기술진흥원", db_name="(농진원)생명자원정보서비스(BRIS)", enact_date="20170715",
                    output_dir=str(tmp_path_factory.mktemp("out")), source="macro", macro_workbook=str(MACRO_XLSM),
                    common_dir=str(COMMON_DIR), meta=str(META), config_path="")
    w = MainWindow(cfg)
    settings = cfg.build()
    outcome = execute(settings, lambda _: None)
    w.show_outcome(outcome, settings)
    return w, outcome


def test_every_page_renders(window):
    w, _ = window
    for key in w.pages:
        w.go(key)
        assert w.stack.currentWidget() is w.pages[key]
        assert not w.pages[key].empty.isVisible()


def test_numbers_on_pages(window):
    w, outcome = window
    pages = w.pages
    assert pages["summary"].apply_num.value.text() == f"{outcome.result.precheck.rate:.1f}"
    assert pages["apply"].meta.model.rowCount() == len(outcome.result.precheck.meta)
    assert pages["currency"].table.model.rowCount() == len(outcome.result.currency.rows)
    assert pages["dict"].fallback.model.rowCount() == len(outcome.fallback)
    assert pages["link"].table.model.rowCount() == len(outcome.candidates)


def test_link_checkbox_updates_candidates(window):
    from PySide6.QtCore import Qt
    w, outcome = window
    page = w.pages["link"]
    model = page.table.model
    first = outcome.candidates[0].selected
    model.setData(model.index(0, 0), (Qt.Unchecked if first else Qt.Checked).value, Qt.CheckStateRole)
    assert outcome.candidates[0].selected is (not first)
    page._reset()
    assert outcome.candidates[0].selected is first


def test_settings_build_always_enhanced():
    from stdtool.ui.settings import AppConfig
    cfg = AppConfig(org_name="기관", db_name="DB", enact_date="20170715", source="macro", macro_workbook="m.xlsm",
                    config_path="")
    s = cfg.build()
    assert s.enhanced is True and s.db.use is False and s.enact_date == 20170715
    assert AppConfig(source="db").missing() == ["기관", "시스템"]


EVAL_FILE = __import__("pathlib").Path(__file__).resolve().parents[2] / "전체 평가대상 DB리스트.xlsx"


def test_eval_list_parsing_and_labels():
    from stdtool import db
    if not EVAL_FILE.exists():
        pytest.skip("평가대상 DB 목록 없음")
    rows = db.read_eval_list(EVAL_FILE)
    assert len(rows) == 170
    assert all("​" not in (v or "") for r in rows for v in r if isinstance(v, str))
    entries = [dict(zip(("org", "seq", "system", "db_kor", "db_eng"), r[1:])) for r in rows]
    bris = next(e for e in entries if "BRIS" in e["system"])
    assert (bris["org"], bris["db_eng"]) == ("한국농업기술진흥원", "brisopen")
    assert db.db_label(bris, entries) == "(농진원)생명자원정보서비스(BRIS)"      # 시스템에 DB 하나: 시스템명 그대로
    petro = [e for e in entries if e["system"] == "페트로넷"]
    assert len(petro) == 6 and len({db.db_label(e, entries) for e in petro}) == 6   # 여러 DB: 시스템명_한글DB명


def test_org_and_system_dropdown(window):
    """기관에 올리면 그 기관의 시스템이 옆에 펼쳐지는 드롭다운. 시스템을 누르면 기관·시스템이 함께 정해진다."""
    w, _ = window
    entries = [{"org": "한국농업기술진흥원", "seq": 10, "system": "(농진원)생명자원정보서비스(BRIS)", "db_kor": "공객용BRISDB",
                "db_eng": "brisopen"},
               {"org": "한국농업기술진흥원", "seq": 11, "system": "(농진원)온-나라 문서1.0", "db_kor": "온나라2.0시스템DB",
                "db_eng": "ONNARA_DB"},
               {"org": "한국석유공사", "seq": 1, "system": "페트로넷", "db_kor": "A DB", "db_eng": "A"},
               {"org": "한국석유공사", "seq": 2, "system": "페트로넷", "db_kor": "B DB", "db_eng": "B"}]
    w.cfg.org_name, w.cfg.system_name, w.cfg.db_kor_name = "한국농업기술진흥원", "(농진원)생명자원정보서비스(BRIS)", "공객용BRISDB"
    w.fill_eval(entries)
    orgs = w.target_menu.actions()
    assert [a.text() for a in orgs] == ["한국농업기술진흥원   (2)", "한국석유공사   (2)"]
    systems = orgs[1].menu().actions()
    assert [a.text() for a in systems] == ["페트로넷  ·  A DB", "페트로넷  ·  B DB"]
    assert w.cfg.db_eng_name == "brisopen" and orgs[0].menu().actions()[0].isChecked()
    systems[1].trigger()
    assert (w.cfg.org_name, w.cfg.db_name, w.cfg.db_eng_name) == ("한국석유공사", "페트로넷_B DB", "B")
    assert systems[1].isChecked() and not orgs[0].menu().actions()[0].isChecked()
    assert w.target.text().strip() == "한국석유공사   ›   페트로넷  ·  B DB"
    assert w.cfg.build().db_eng_name == "B"


def test_enact_date_calendar(app):
    from stdtool.ui.settings import AppConfig, SettingsDialog
    cfg = AppConfig(enact_date="20170715", config_path="")
    d = SettingsDialog(cfg)
    assert d.enact.calendarPopup() and d.enact.date().toString("yyyyMMdd") == "20170715"
    d.enact.setDate(d.enact.date().addDays(1))
    d._apply()
    assert cfg.enact_date == "20170716"
    d.enact.setDate(d.enact.minimumDate())
    d._apply()
    assert cfg.enact_date == ""


def test_run_panel_steps(window):
    from stdtool.service import STEPS
    w, _ = window
    panel = w.run_panel
    panel.start()
    assert panel.bar.maximum() == len(STEPS) and panel.close_button.isHidden()   # 창을 띄우지 않으므로 isHidden으로 본다
    panel.step_done("dict", "사전")
    panel.step_done("raw", "89행")          # 건너뛴 '메타 읽기'도 완료로
    assert panel.bar.value() == 3 and panel._current == 3
    assert panel.rows[2].detail.text() == "89행"
    panel.finish(True, "산출물 14개", w.outcome.folder if w.outcome else None)
    assert panel.title.text() == "완료" and not panel.close_button.isHidden() and panel.grid_box.isHidden()


def test_default_output_is_desktop():
    from stdtool.ui.settings import AppConfig, desktop_dir
    assert AppConfig().output_dir == desktop_dir()
    assert "Desktop" in desktop_dir() or "바탕 화면" in desktop_dir()
