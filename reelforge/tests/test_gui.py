"""Offscreen smoke test for the minimal GUI (skipped when PyQt5 isn't installed)."""

import os

import pytest

pytest.importorskip("PyQt5")
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def test_gui_shows_jobs_and_state_actions(settings, script_file, monkeypatch):
    from PyQt5.QtWidgets import QApplication, QPushButton

    from reelforge.gui import app as gui
    from reelforge.jobs.orchestrator import Pipeline
    from reelforge.schemas import JobConfig

    monkeypatch.setattr(gui, "load_settings", lambda: settings)
    p = Pipeline(settings, log=lambda m: None)
    job = p.create_from_script(script_file, JobConfig(voice_mode="ask", fetch_sources=False))

    qapp = QApplication.instance() or QApplication([])
    w = gui.MainWindow()
    w.refresh()
    assert w.jobs.count() == 1
    w.jobs.setCurrentRow(0)
    qapp.processEvents()
    labels = [b.text() for b in w.findChildren(QPushButton) if b.isVisibleTo(w)]
    assert "Record Voice" in labels and "Use AI voice" in labels and "Use an audio file…" in labels
    assert "Approve Script" not in labels
    assert "Choose the voice" in w.state.text() and job.id in w.state.text()
    assert w.stepper.current == 1 and not w.stepper.failed  # script done, voice is the current step
    assert "HOOK" in w.script_view.toPlainText()
    dlg = gui.NewJobDialog(w)
    dlg.topic.setText("Why AI struggles with hands")
    assert dlg.args()[:3] == ["create", "--topic", "Why AI struggles with hands"] and "ask" in dlg.args()
    dlg._pick("script")
    assert dlg.args()[:2] == ["create", "--script-file"]
    w.close()


def test_gui_draft_and_voice_buttons_send_the_right_commands(settings, monkeypatch):
    from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton

    from reelforge.gui import app as gui
    from reelforge.jobs.orchestrator import Pipeline
    from reelforge.providers import FallbackLLM
    from reelforge.schemas import JobConfig
    from reelforge.tests.test_jobs import FakeLLM

    monkeypatch.setattr(gui, "load_settings", lambda: settings)
    p = Pipeline(settings, log=lambda m: None, llm_factory=lambda pref: FallbackLLM([FakeLLM()]))
    job = p.create_from_topic("Tiny models", JobConfig(voice_mode="ask", research=False, drafts=3))
    qapp = QApplication.instance() or QApplication([])
    w = gui.MainWindow()
    sent: list[list[str]] = []
    monkeypatch.setattr(w, "run", lambda args, on_done=None: sent.append(args))
    w.refresh()
    w.select(job.id)
    qapp.processEvents()

    def click(text: str) -> None:
        [b for b in w.findChildren(QPushButton) if b.text() == text and b.isVisibleTo(w)][0].click()

    assert "Pick a script" in w.state.text()
    click("Use Draft 2")  # Qt passes `checked` to the slot; it must not replace the draft number
    assert sent[-1] == ["pick", job.id, "2", "--no-interactive"]
    p.pick_script(job.id, 2)
    w.select(job.id)
    qapp.processEvents()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    click("Use AI voice")
    assert sent[-1][0] == "pick"  # declined: nothing runs
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    click("Use AI voice")
    assert sent[-1] == ["voice", job.id, "--ai", "--yes"]
    w.close()
