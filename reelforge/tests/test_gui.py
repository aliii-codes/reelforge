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
    job = p.create_from_script(script_file, JobConfig(voice_mode="file", takes=1, fetch_sources=False))

    qapp = QApplication.instance() or QApplication([])
    w = gui.MainWindow()
    w.refresh()
    assert w.jobs.count() == 1
    w.jobs.setCurrentRow(0)
    qapp.processEvents()
    labels = [b.text() for b in w.findChildren(QPushButton) if b.isVisibleTo(w)]
    assert "Record Voice" in labels and "Use an audio file instead…" in labels  # no voice-over yet
    assert "Approve Script" not in labels
    assert "Waiting for your voice" in w.state.text() and job.id in w.state.text()
    assert w.stepper.current == 1 and not w.stepper.failed  # script done, voice is the current step
    assert "HOOK" in w.script_view.toPlainText()
    dlg = gui.NewJobDialog(w)
    assert dlg.args()[:2] == ["create", "--script-file"] and dlg.args()[-2:] == ["--voice", "file"]
    dlg._pick("stock")
    assert "--voice" not in dlg.args()
    w.close()
