"""ReelForge desktop app — minimal, Apple-inspired.

Layout: a sidebar of reels; for the selected reel a big title, a 4-step progress tracker
(Script → Voice → Preview → Final), one "next step" card with a single primary button, and the
script / frames / checks behind a segmented control. Technical output stays in a collapsible
Activity drawer.

Every action runs the existing CLI (`python -m reelforge.main ...`) in a QProcess, so the app
shares the CLI's behaviour, SQLite state, resumability and logs.

    python -m reelforge.gui.app        (or: reelforge-gui)
"""

from __future__ import annotations

import contextlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QProcess, QProcessEnvironment, QRectF, QSize, Qt, QTimer, QUrl
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from reelforge.config import PROJECT_ROOT, load_settings
from reelforge.database import Database, JobRecord
from reelforge.gui import theme
from reelforge.jobs.state import JobState

RUNNING_STATES = {
    JobState.RESEARCHING,
    JobState.GENERATING_VOICE,
    JobState.ALIGNING_CAPTIONS,
    JobState.PLANNING_SCENES,
    JobState.PREVIEWING,
    JobState.RENDERING,
}
STEPS = ["Script", "Voice", "Preview", "Final"]
STEP_OF_STATE = {
    JobState.CREATED: 0,
    JobState.RESEARCHING: 0,
    JobState.AWAITING_SCRIPT_APPROVAL: 0,
    JobState.GENERATING_VOICE: 1,
    JobState.ALIGNING_CAPTIONS: 1,
    JobState.PLANNING_SCENES: 1,
    JobState.PREVIEWING: 2,
    JobState.AWAITING_PREVIEW_APPROVAL: 2,
    JobState.RENDERING: 3,
    JobState.AWAITING_VIDEO_APPROVAL: 3,
    JobState.COMPLETED: 4,
}
WORKING_TEXT = {
    JobState.RESEARCHING: "Researching and writing the script",
    JobState.GENERATING_VOICE: "Processing your voice and transcribing it",
    JobState.ALIGNING_CAPTIONS: "Timing the captions to your voice",
    JobState.PLANNING_SCENES: "Planning scenes on the beats of your voice",
    JobState.PREVIEWING: "Rendering a quick preview",
    JobState.RENDERING: "Rendering the full-quality video",
}


def open_path(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def needs_recording(j: JobRecord) -> bool:
    return j.config.get("voice_mode") == "file" and not j.config.get("narration_file")


def status_of(j: JobRecord) -> tuple[str, str]:
    """Short human status and its dot colour."""
    st = j.state
    if st == JobState.FAILED:
        return "Needs attention", theme.RED
    if st == JobState.COMPLETED:
        return "Ready to post", theme.GREEN
    if st == JobState.AWAITING_SCRIPT_APPROVAL:
        return ("Waiting for your voice" if needs_recording(j) else "Review the script"), theme.ORANGE
    if st == JobState.AWAITING_PREVIEW_APPROVAL:
        return "Preview ready", theme.ORANGE
    if st == JobState.AWAITING_VIDEO_APPROVAL:
        return "Final video ready", theme.ORANGE
    return "Working…", theme.BLUE


def nice_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%-d %b, %H:%M")
    except ValueError:
        return iso[:16]


# --------------------------------------------------------------------------- small widgets


class Dot(QWidget):
    def __init__(self, color: str, size: int = 8, parent: QWidget | None = None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(size, size)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(self.color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, self.width(), self.height())


class ReelRow(QWidget):
    def __init__(self, j: JobRecord):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 9, 12, 9)
        v.setSpacing(3)
        title = QLabel(j.title.replace(" (voice-over demo)", ""))
        title.setObjectName("RowTitle")
        title.setWordWrap(True)
        v.addWidget(title)
        text, color = status_of(j)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(Dot(color, 7))
        sub = QLabel(f"{text}  ·  {nice_time(j.created_at)}")
        sub.setObjectName("RowSub")
        row.addWidget(sub, 1)
        v.addLayout(row)


class Stepper(QWidget):
    """Four circles joined by a line: done (blue ✓), current (blue ring), upcoming (grey)."""

    def __init__(self) -> None:
        super().__init__()
        self.current = 0
        self.failed = False
        self.setFixedHeight(64)

    def set(self, current: int, failed: bool = False) -> None:
        self.current, self.failed = current, failed
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(STEPS)
        w = self.width()
        margin = 40
        xs = [margin + i * (w - 2 * margin) / (n - 1) for i in range(n)]
        cy, r = 20, 11
        blue, grey, red = QColor(theme.BLUE), QColor("#D1D1D6"), QColor(theme.RED)
        for i in range(n - 1):
            p.setPen(QPen(blue if i < self.current else grey, 2))
            p.drawLine(int(xs[i] + r + 4), cy, int(xs[i + 1] - r - 4), cy)
        label_font = theme.ui_font(9.5)
        for i, x in enumerate(xs):
            rect = QRectF(x - r, cy - r, 2 * r, 2 * r)
            done = i < self.current
            here = i == self.current
            if done:
                p.setPen(Qt.NoPen)
                p.setBrush(blue)
                p.drawEllipse(rect)
                p.setPen(QPen(QColor("white"), 2.2))
                p.drawLine(int(x - 5), cy, int(x - 1), cy + 4)
                p.drawLine(int(x - 1), cy + 4, int(x + 6), cy - 4)
            elif here:
                color = red if self.failed else blue
                p.setPen(QPen(color, 2.4))
                p.setBrush(QColor("white"))
                p.drawEllipse(rect)
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawEllipse(QRectF(x - 4.5, cy - 4.5, 9, 9))
            else:
                p.setPen(QPen(grey, 2))
                p.setBrush(QColor("white"))
                p.drawEllipse(rect)
            label_font.setWeight(QFont.DemiBold if here else QFont.Normal)
            p.setFont(label_font)
            p.setPen(QColor(theme.TEXT if (done or here) else theme.TEXT_2))
            p.drawText(QRectF(x - 50, cy + r + 6, 100, 20), Qt.AlignHCenter | Qt.AlignTop, STEPS[i])


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


def button(text: str, kind: str = "", fn=None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    if fn:
        b.clicked.connect(fn)
    return b


def label(text: str, obj: str = "", wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    lab.setWordWrap(wrap)
    return lab


# --------------------------------------------------------------------------- dialogs


class OptionTile(QFrame):
    """A large selectable choice (instead of a tiny radio button)."""

    def __init__(self, title: str, body: str, on_click):
        super().__init__()
        self.setObjectName("Option")
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(2)
        v.addWidget(label(title, "OptionTitle"))
        v.addWidget(label(body, "OptionBody"))
        self._cb = on_click
        self.set_selected(False)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", "true" if on else "false")
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def mousePressEvent(self, _e) -> None:  # noqa: N802
        self._cb()


class NewJobDialog(QDialog):
    VOICES = [
        ("later", "Record my voice next", "Recommended. You'll read the script aloud right after this."),
        ("file", "Use a recording I already have", "Pick an audio file of you reading the script."),
        ("stock", "Use a stock voice", "A built-in synthetic voice — clearly labelled as not you."),
    ]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("New Reel")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 20)
        v.setSpacing(10)
        v.addWidget(label("New Reel", "Title"))
        v.addWidget(label("Choose a script and how it will be narrated.", "Subtitle"))
        v.addSpacing(6)

        v.addWidget(label("Script", "OptionTitle"))
        row = QHBoxLayout()
        self.script = QLineEdit(str(PROJECT_ROOT / "examples" / "voiceover_demo_script.txt"))
        row.addWidget(self.script, 1)
        row.addWidget(button("Choose…", "", lambda: self._browse(self.script, "Text (*.txt *.md);;All files (*)")))
        v.addLayout(row)
        v.addSpacing(4)

        v.addWidget(label("Voice", "OptionTitle"))
        self.voice = "later"
        self.tiles: dict[str, OptionTile] = {}
        for key, title, body in self.VOICES:
            tile = OptionTile(title, body, lambda k=key: self._pick(k))
            self.tiles[key] = tile
            v.addWidget(tile)
        self.narration_row = QWidget()
        nr = QHBoxLayout(self.narration_row)
        nr.setContentsMargins(0, 0, 0, 0)
        self.narration = QLineEdit()
        self.narration.setPlaceholderText("Your recording (.wav, .m4a, .mp3, .flac, .ogg)")
        nr.addWidget(self.narration, 1)
        nr.addWidget(
            button("Choose…", "", lambda: self._browse(self.narration, "Audio (*.wav *.flac *.m4a *.mp3 *.ogg *.opus)"))
        )
        v.addWidget(self.narration_row)

        v.addSpacing(4)
        self.handle = QLineEdit(load_settings().handle)
        self.handle.setPlaceholderText("Your @handle on the video (optional)")
        v.addWidget(self.handle)
        self.preview_gate = QCheckBox("Show me a quick preview before the full render")
        self.preview_gate.setChecked(True)
        v.addWidget(self.preview_gate)

        v.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(button("Cancel", "", self.reject))
        create = button("Create Reel", "Primary", self._accept)
        create.setDefault(True)
        buttons.addWidget(create)
        v.addLayout(buttons)
        self._pick("later")

    # compatibility with earlier callers/tests
    @property
    def voice_later(self) -> _Flag:
        return _Flag(self.voice == "later")

    @property
    def voice_file(self) -> _Flag:
        return _Flag(self.voice == "file")

    def _pick(self, key: str) -> None:
        self.voice = key
        for k, t in self.tiles.items():
            t.set_selected(k == key)
        self.narration_row.setVisible(key == "file")
        self.adjustSize()

    def _browse(self, edit: QLineEdit, filt: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose file", str(PROJECT_ROOT), filt)
        if path:
            edit.setText(path)

    def _accept(self) -> None:
        if not Path(self.script.text()).is_file():
            QMessageBox.warning(self, "Script", "Choose an existing script file.")
            return
        if self.voice == "file" and not Path(self.narration.text()).is_file():
            QMessageBox.warning(self, "Recording", "Choose your recording, or pick “Record my voice next”.")
            return
        self.accept()

    def args(self) -> list[str]:
        a = ["create", "--script-file", self.script.text()]
        if self.voice == "file":
            a += ["--voice", "file", "--narration", self.narration.text()]
        elif self.voice == "later":
            a += ["--voice", "file"]  # the reel waits for a recording before it continues
        if self.handle.text().strip():
            a += ["--handle", self.handle.text().strip()]
        if not self.preview_gate.isChecked():
            a.append("--no-preview-gate")
        return a


class _Flag:
    def __init__(self, on: bool):
        self._on = on

    def isChecked(self) -> bool:  # noqa: N802 - mimics the Qt API
        return self._on


class RecordDialog(QDialog):
    """Read-and-record: the script in large type, one big record button, a timer, then a check."""

    def __init__(self, script_text: str, out: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Record Voice")
        self.resize(680, 640)
        self.out = out
        self.proc: QProcess | None = None
        self.started = 0.0
        self.ok = False
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 20)
        v.setSpacing(10)
        v.addWidget(label("Record Your Voice", "Title"))
        v.addWidget(label("Read naturally — pauses are fine. Quiet room, phone-length from the mic.", "Subtitle"))
        script_card = card()
        sc = QVBoxLayout(script_card)
        sc.setContentsMargins(18, 14, 18, 14)
        text = QTextBrowser()
        text.setObjectName("Script")
        text.setHtml(
            "".join(
                f"<p style='font-size:16px; line-height:150%; margin:0 0 12px 0'>{html.escape(p)}</p>"
                for p in script_text.split("\n\n")
            )
        )
        sc.addWidget(text)
        v.addWidget(script_card, 1)

        center = QHBoxLayout()
        center.addStretch(1)
        col = QVBoxLayout()
        col.setAlignment(Qt.AlignHCenter)
        self.rec_btn = button("REC", "Record", self._toggle)
        self.rec_btn.setCheckable(True)
        self.rec_btn.setFixedSize(72, 72)
        col.addWidget(self.rec_btn, 0, Qt.AlignHCenter)
        self.timer_label = label("0:00", "NextHeading", wrap=False)
        self.timer_label.setAlignment(Qt.AlignHCenter)
        col.addWidget(self.timer_label)
        self.status = label("Press REC when you're ready.", "Muted", wrap=False)
        self.status.setAlignment(Qt.AlignHCenter)
        col.addWidget(self.status)
        center.addLayout(col)
        center.addStretch(1)
        v.addLayout(center)

        self.check_box = label("", "Muted")
        self.check_box.hide()
        v.addWidget(self.check_box)
        row = QHBoxLayout()
        self.play_btn = button("Listen", "Link", lambda: open_path(self.out))
        self.play_btn.setEnabled(False)
        row.addWidget(self.play_btn)
        row.addStretch(1)
        row.addWidget(button("Cancel", "", self.reject))
        self.use_btn = button("Use This Take", "Primary", self.accept)
        self.use_btn.setEnabled(False)
        row.addWidget(self.use_btn)
        v.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def _toggle(self) -> None:
        if self.proc is None:
            self._start()
        else:
            self._stop()

    def _start(self) -> None:
        from reelforge.voice.voiceover import build_record_command

        self.out.parent.mkdir(parents=True, exist_ok=True)
        cmd = build_record_command(self.out, max_seconds=180)
        self.proc = QProcess(self)
        self.proc.finished.connect(self._finished)
        self.proc.start(cmd[0], cmd[1:])
        self.started = time.time()
        self.timer.start(200)
        self.rec_btn.setText("STOP")
        self.rec_btn.setChecked(True)
        self.status.setText("Recording — press STOP when you finish.")
        self.use_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.check_box.hide()

    def _stop(self) -> None:
        if self.proc is not None:
            self.proc.write(b"q")  # FFmpeg finishes the WAV cleanly
            self.proc.closeWriteChannel()

    def _tick(self) -> None:
        s = int(time.time() - self.started)
        self.timer_label.setText(f"{s // 60}:{s % 60:02d}")

    def _finished(self) -> None:
        from reelforge.voice.voiceover import check_voiceover

        self.timer.stop()
        err = bytes(self.proc.readAllStandardError()).decode(errors="replace") if self.proc else ""
        self.proc = None
        self.rec_btn.setText("REC")
        self.rec_btn.setChecked(False)
        if not self.out.exists():
            self.status.setText("Recording failed: " + (err.strip()[:160] or "no file was written"))
            return
        chk = check_voiceover(self.out)
        self.ok = chk.ok
        if chk.ok:
            self.status.setText("Sounds good. Listen to it, then use this take — or record again.")
        else:
            self.status.setText("This take can't be used — see below and record again.")
        details = [f"{chk.duration:.0f} s · background noise {'low' if chk.snr_estimate_db >= 25 else 'noticeable'}"]
        details += [f"✕ {e}" for e in chk.errors] + [f"• {w}" for w in chk.warnings]
        self.check_box.setText("\n".join(details))
        self.check_box.show()
        self.play_btn.setEnabled(True)
        self.use_btn.setEnabled(chk.ok)

    def reject(self) -> None:
        if self.proc is not None:
            self._stop()
            self.proc.waitForFinished(5000)
        super().reject()


# --------------------------------------------------------------------------- main window


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.settings.ensure_dirs()
        self.db = Database(self.settings.db_path)
        self.proc: QProcess | None = None
        self.current: str | None = None
        self.progress_text = ""
        self.setWindowTitle("ReelForge")
        self.resize(1200, 820)

        # sidebar
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(280)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(10, 18, 10, 12)
        head = QHBoxLayout()
        head.setContentsMargins(10, 0, 4, 6)
        head.addWidget(label("Reels", "SidebarTitle", wrap=False))
        head.addStretch(1)
        plus = button("+", "Round", self.new_job)
        plus.setToolTip("New Reel")
        head.addWidget(plus)
        sv.addLayout(head)
        self.jobs = QListWidget()
        self.jobs.setObjectName("ReelList")
        self.jobs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.jobs.currentItemChanged.connect(lambda cur, _p: self.select(cur.data(Qt.UserRole) if cur else None))
        sv.addWidget(self.jobs, 1)

        # main column
        self.stack = QStackedWidget()
        self.stack.addWidget(self._empty_state())
        self.stack.addWidget(self._detail())

        canvas = QWidget()
        canvas.setObjectName("Canvas")
        h = QHBoxLayout(canvas)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(canvas)

        self.poll = QTimer(self)
        self.poll.timeout.connect(self.refresh)
        self.poll.start(4000)
        self.refresh()

    # ---------------------------------------------------------------- layout

    def _empty_state(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch(1)
        t = label("Make your first reel", "EmptyTitle")
        t.setAlignment(Qt.AlignHCenter)
        v.addWidget(t)
        s = label("Pick a script, record your voice, and ReelForge builds the video around it.", "Subtitle")
        s.setAlignment(Qt.AlignHCenter)
        v.addWidget(s)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("New Reel", "Primary", self.new_job))
        row.addStretch(1)
        v.addSpacing(12)
        v.addLayout(row)
        v.addStretch(2)
        return w

    def _detail(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(32, 26, 32, 18)
        v.setSpacing(14)
        self.title = label("", "Title")
        self.state = label("", "Subtitle")
        self.state.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.title)
        v.addWidget(self.state)
        self.stepper = Stepper()
        v.addWidget(self.stepper)

        # next-step card
        nc = card()
        nl = QVBoxLayout(nc)
        nl.setContentsMargins(22, 18, 22, 18)
        nl.setSpacing(6)
        self.next_heading = label("", "NextHeading")
        self.next_body = label("", "NextBody")
        nl.addWidget(self.next_heading)
        nl.addWidget(self.next_body)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        nl.addWidget(self.progress)
        self.action_row = QHBoxLayout()
        self.action_row.setSpacing(6)
        nl.addSpacing(6)
        nl.addLayout(self.action_row)
        v.addWidget(nc)

        # content card with segmented control
        cc = card()
        cl = QVBoxLayout(cc)
        cl.setContentsMargins(18, 14, 18, 14)
        seg = QFrame()
        seg.setObjectName("Segmented")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(2, 2, 2, 2)
        sl.setSpacing(0)
        self.seg_group = QButtonGroup(self)
        self.pages = QStackedWidget()
        self.script_view = QTextBrowser()
        self.script_view.setObjectName("Script")
        self.image = QLabel("")
        self.image.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        scroll = QScrollArea()
        scroll.setWidget(self.image)
        scroll.setWidgetResizable(True)
        self.checks_view = QTextBrowser()
        self.checks_view.setObjectName("Script")
        for i, (name, page) in enumerate(
            (("Script", self.script_view), ("Frames", scroll), ("Checks", self.checks_view))
        ):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.seg_group.addButton(b, i)
            sl.addWidget(b)
            self.pages.addWidget(page)
        self.seg_group.buttonClicked[int].connect(self.pages.setCurrentIndex)
        self._check_segment(0)
        top = QHBoxLayout()
        top.addWidget(seg)
        top.addStretch(1)
        cl.addLayout(top)
        cl.addWidget(self.pages, 1)
        v.addWidget(cc, 1)

        # activity drawer
        drawer = QHBoxLayout()
        self.activity_btn = button("Show activity", "Link", self._toggle_log)
        drawer.addWidget(self.activity_btn)
        drawer.addStretch(1)
        self.folder_btn = button("Show in Folder", "Link", self._open_folder)
        drawer.addWidget(self.folder_btn)
        v.addLayout(drawer)
        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        self.log.setFixedHeight(170)
        self.log.hide()
        v.addWidget(self.log)
        return w

    def _check_segment(self, index: int) -> None:
        b = self.seg_group.button(index)
        if b is not None:
            b.setChecked(True)

    def _open_folder(self) -> None:
        j = self.job()
        if j is not None:
            open_path(j.output_dir)

    def _toggle_log(self) -> None:
        self.log.setVisible(not self.log.isVisible())
        self.activity_btn.setText("Hide activity" if self.log.isVisible() else "Show activity")

    # ---------------------------------------------------------------- data

    def refresh(self) -> None:
        jobs = self.db.list_jobs()
        selected = self.current or (jobs[0].id if jobs else None)
        self.jobs.blockSignals(True)
        self.jobs.clear()
        for j in jobs:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, j.id)
            row = ReelRow(j)
            row.setFixedWidth(248)
            row.adjustSize()
            item.setSizeHint(
                QSize(248, row.heightForWidth(248) if row.hasHeightForWidth() else row.sizeHint().height())
            )
            self.jobs.addItem(item)
            self.jobs.setItemWidget(item, row)
            if j.id == selected:
                self.jobs.setCurrentItem(item)
        self.jobs.blockSignals(False)
        self.stack.setCurrentIndex(1 if jobs else 0)
        if selected:
            self.select(selected, keep_tab=True)

    def job(self) -> JobRecord | None:
        if not self.current:
            return None
        try:
            return self.db.get_job(self.current)
        except KeyError:
            return None

    def select(self, job_id: str | None, keep_tab: bool = False) -> None:
        self.current = job_id
        j = self.job()
        self._clear_actions()
        if j is None:
            return
        self.title.setText(j.title.replace(" (voice-over demo)", ""))
        text, _ = status_of(j)
        self.state.setText(f"{text}  ·  created {nice_time(j.created_at)}  ·  {j.id}")
        step = STEP_OF_STATE.get(j.state, STEP_OF_STATE.get(j.failed_stage or JobState.CREATED, 0))
        if j.state == JobState.AWAITING_SCRIPT_APPROVAL and needs_recording(j):
            step = 1
        self.stepper.set(step, failed=j.state == JobState.FAILED)
        self._fill_script(j)
        self._fill_frames(j)
        self._fill_checks(j)
        self._build_next(j)
        if not keep_tab:
            page = (
                1
                if j.state in (JobState.AWAITING_PREVIEW_APPROVAL, JobState.AWAITING_VIDEO_APPROVAL, JobState.COMPLETED)
                else 0
            )
            self._check_segment(page)
            self.pages.setCurrentIndex(page)

    def _fill_script(self, j: JobRecord) -> None:
        rows = self.db.script_versions(j.id)
        if not rows:
            self.script_view.setHtml(f"<p style='color:{theme.TEXT_2}'>No script yet.</p>")
            return
        data = json.loads(Path(rows[-1]["path"]).read_text())
        parts = []
        for s in data["script"]["sections"]:
            parts.append(
                f"<p style='margin:0 0 2px 0; font-size:10px; letter-spacing:1px; color:{theme.TEXT_3}'>"
                f"{html.escape(s['role'].upper())}</p>"
                f"<p style='margin:0 0 14px 0; font-size:14px; line-height:145%'>{html.escape(s['text'])}</p>"
            )
        claims = data.get("research", {}).get("claims", [])
        if claims:
            ok = sum(1 for c in claims if c["status"] in ("auto_supported", "human_verified"))
            parts.append(
                f"<p style='color:{theme.TEXT_2}; font-size:12px'>Facts: {ok} of {len(claims)} matched in their "
                "sources (automatic check — review before posting).</p>"
            )
        self.script_view.setHtml("".join(parts))

    def _fill_frames(self, j: JobRecord) -> None:
        out = j.output_dir
        existing = [p for p in (out / "contact_sheet.jpg", out / "preview_contact_sheet.jpg") if p.exists()]
        if not existing:
            self.image.setPixmap(QPixmap())
            self.image.setText("Frames appear here after the preview is rendered.")
            return
        newest = max(existing, key=lambda p: p.stat().st_mtime)
        pix = QPixmap(str(newest))
        width = max(320, self.pages.width() - 30)
        self.image.setPixmap(pix.scaledToWidth(min(pix.width(), width), Qt.SmoothTransformation))

    def _fill_checks(self, j: JobRecord) -> None:
        out = j.output_dir
        rows: list[str] = []

        def item(ok: bool | None, text: str) -> None:
            mark, color = {True: ("✓", theme.GREEN), False: ("✕", theme.RED), None: ("•", theme.ORANGE)}[ok]
            rows.append(
                f"<p style='margin:0 0 6px 0; font-size:13px'><span style='color:{color}'>{mark}</span>"
                f"&nbsp;&nbsp;{html.escape(text)}</p>"
            )

        for name, title in (("validation_report.json", "Final video"), ("preview_report.json", "Preview")):
            p = out / name
            if not p.exists():
                continue
            rep = json.loads(p.read_text())
            video = rep.get("video", rep)
            s = video.get("summary", {})
            rows.append(f"<p style='margin:10px 0 6px 0; font-weight:600; font-size:14px'>{title}</p>")
            sound = "with sound" if s.get("audio_codec") else "no sound"
            item(
                video.get("ok"),
                f"{s.get('width')}×{s.get('height')}, {s.get('fps')} fps, {s.get('duration')} s, {sound}",
            )
            rc = video.get("render_completion") or {}
            if rc:
                item(
                    rc.get("frames") == rc.get("expected"),
                    f"All frames rendered ({rc.get('frames')}/{rc.get('expected')})",
                )
            ct = video.get("caption_timing") or {}
            if ct.get("first_word_offset_s") is not None:
                off = abs(ct["first_word_offset_s"])
                item(off <= 0.3, f"Captions in sync with your voice (first word off by {off:.2f} s)")
            for e in video.get("errors", []):
                item(False, e)
            for w in video.get("warnings", []):
                item(None, w)
        takes = out / "work" / "takes" / "takes_report.json"
        if takes.exists():
            rows.append("<p style='margin:10px 0 6px 0; font-weight:600; font-size:14px'>Voice</p>")
            for t in json.loads(takes.read_text()):
                item(
                    t["wer"] < 0.05,
                    f"Take {t['index']}: {t['duration']:.0f} s, {100 - t['wer'] * 100:.0f}% of the script heard",
                )
                for i in t["issues"][:3]:
                    item(None, i)
        self.checks_view.setHtml(
            "".join(rows) or f"<p style='color:{theme.TEXT_2}'>Checks appear after the preview.</p>"
        )

    # ---------------------------------------------------------------- next step

    def _clear_actions(self) -> None:
        while self.action_row.count():
            it = self.action_row.takeAt(0)
            w = it.widget() if it is not None else None
            if w is not None:
                w.hide()  # deleteLater is deferred; hide now so old buttons never overlap new ones
                w.setParent(None)
                w.deleteLater()

    def _add(self, text: str, fn, primary: bool = False) -> None:
        b = button(text, "Primary" if primary else "Link", fn)
        b.setEnabled(self.proc is None)
        self.action_row.addWidget(b)

    def _next(self, heading: str, body: str) -> None:
        self.next_heading.setText(heading)
        self.next_body.setText(body)

    def _build_next(self, j: JobRecord) -> None:
        out, jid, st = j.output_dir, j.id, j.state
        self.progress.setVisible(self.proc is not None)
        if self.proc is not None:
            self._next(
                WORKING_TEXT.get(st, "Working…") + "…",
                self.progress_text or "You can keep using your computer. This window updates by itself.",
            )
            self._add("Stop", self.stop_process)
        elif st == JobState.AWAITING_SCRIPT_APPROVAL and needs_recording(j):
            self._next(
                "Record your voice-over",
                "Read the script aloud. We'll check the take, time everything to your voice, "
                "and build a quick preview.",
            )
            self._add("Record Voice", lambda: self.record(j), primary=True)
            self._add("Use an audio file instead…", lambda: self.attach_file(j))
        elif st == JobState.AWAITING_SCRIPT_APPROVAL:
            self._next("Approve the script", "Read it below. Approving starts the voice, captions and a quick preview.")
            self._add("Approve Script", lambda: self.run(["approve-script", jid, "--yes"]), primary=True)
            if j.config.get("voice_mode") == "file":
                self._add("Re-record voice", lambda: self.record(j))
        elif st == JobState.AWAITING_PREVIEW_APPROVAL:
            self._next(
                "Check the preview",
                "Watch the quick, low-resolution preview. If it looks right, render the full-quality "
                "video (about 5–10 minutes).",
            )
            self._add("Render Full Video", lambda: self.run(["approve-preview", jid, "--yes"]), primary=True)
            self._add("Play Preview", lambda: open_path(out / "preview.mp4"))
            self._add("Re-record voice", lambda: self.record(j))
        elif st == JobState.AWAITING_VIDEO_APPROVAL:
            self._next(
                "Review the final video",
                "Watch it once more, then approve it for posting. Nothing is posted automatically.",
            )
            self._add("Approve", lambda: self.run(["approve-video", jid, "--yes"]), primary=True)
            self._add("Play Video", lambda: open_path(out / "final_reel.mp4"))
        elif st == JobState.COMPLETED:
            self._next(
                "Ready to post", "Your reel, cover, caption and hashtags are in the folder. Upload them yourself."
            )
            self._add("Show in Folder", lambda: open_path(out), primary=True)
            self._add("Play Video", lambda: open_path(out / "final_reel.mp4"))
        elif st == JobState.FAILED:
            msg = (j.last_error or "").split(":", 1)[-1].strip()
            self._next("Something went wrong", (msg[:220] + "…") if len(msg) > 220 else msg)
            self._add("Try Again", lambda: self.run(["resume", jid]), primary=True)
            self._add("Show details", self._show_log)
        else:  # interrupted while working
            self._next("Paused", "This step was interrupted. Continue from where it stopped.")
            self._add("Continue", lambda: self.run(["resume", jid]), primary=True)
        self.action_row.addStretch(1)

    def _show_log(self) -> None:
        if not self.log.isVisible():
            self._toggle_log()

    # ---------------------------------------------------------------- actions

    def new_job(self) -> None:
        dlg = NewJobDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        record_next = dlg.voice == "later"
        self.run(dlg.args(), on_done=lambda ok: self._after_create(ok, record_next))

    def _after_create(self, ok: bool, record_next: bool) -> None:
        jobs = self.db.list_jobs()
        if not ok or not jobs:
            self._show_log()
            return
        self.current = jobs[0].id
        self.refresh()
        self.select(jobs[0].id)
        if record_next:
            self.record(jobs[0])

    def record(self, j: JobRecord) -> None:
        rows = self.db.script_versions(j.id)
        data = json.loads(Path(rows[-1]["path"]).read_text())
        text = "\n\n".join(s["text"] for s in data["script"]["sections"])
        out = self.settings.voice_dir / "recordings" / f"{time.strftime('%Y%m%d-%H%M%S')}.wav"
        dlg = RecordDialog(text, out, self)
        if dlg.exec_() == QDialog.Accepted and dlg.ok:
            self.attach(j, out)

    def attach_file(self, j: JobRecord) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Your recording", str(self.settings.voice_dir), "Audio (*.wav *.flac *.m4a *.mp3 *.ogg *.opus)"
        )
        if path:
            self.attach(j, Path(path))

    def attach(self, j: JobRecord, path: Path) -> None:
        args = ["voiceover", j.id, "--file", str(path)]
        if j.state == JobState.AWAITING_SCRIPT_APPROVAL:

            def then_approve(ok: bool) -> None:  # attach, then run straight through to the preview
                if ok:
                    self.run(["approve-script", j.id, "--yes"])

            self.run(args, on_done=then_approve)
        else:
            self.run(args)

    # ---------------------------------------------------------------- process

    def run(self, args: list[str], on_done=None) -> None:
        if self.proc is not None:
            QMessageBox.information(self, "Busy", "Please wait for the current step to finish.")
            return
        self.log.appendPlainText(f"\n$ reelforge {' '.join(args)}")
        p = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("COLUMNS", "110")
        env.insert("PYTHONUNBUFFERED", "1")
        p.setProcessEnvironment(env)
        p.setWorkingDirectory(str(PROJECT_ROOT))
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self._read)
        p.finished.connect(lambda code, _status: self._done(code, on_done))
        self.proc = p
        self.progress.setRange(0, 0)  # indeterminate until a percentage is reported
        self.progress_text = ""
        self.select(self.current, keep_tab=True)
        p.start(sys.executable, ["-m", "reelforge.main", *args])

    _PCT = re.compile(r"rendered (\d+)/(\d+) frames \((\d+)%\)")

    def _read(self) -> None:
        if self.proc is None:
            return
        text = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        for line in text.splitlines():
            if not line.strip():
                continue
            self.log.appendPlainText(line.rstrip())
            m = self._PCT.search(line)
            if m:
                self.progress.setRange(0, 100)
                self.progress.setValue(int(m.group(3)))
                self.progress_text = f"{m.group(3)}% — frame {m.group(1)} of {m.group(2)}"
                self.next_body.setText(self.progress_text)
            elif line.startswith("== "):
                self.progress.setRange(0, 0)
                stage = line.strip("= ").strip()
                with contextlib.suppress(ValueError):
                    self.next_heading.setText(WORKING_TEXT.get(JobState(stage), "Working") + "…")

    def _done(self, code: int, on_done) -> None:
        self._read()
        self.proc = None
        self.log.appendPlainText("✓ done" if code == 0 else f"✕ exited with code {code}")
        self.refresh()
        if code != 0:
            self._show_log()
        if on_done:
            on_done(code == 0)

    def stop_process(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            if not self.proc.waitForFinished(5000):
                self.proc.kill()
            self.log.appendPlainText("Stopped. Use Continue to pick up from the last finished step.")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.proc is not None:
            r = QMessageBox.question(self, "Still working", "A step is still running. Stop it and quit?")
            if r != QMessageBox.Yes:
                event.ignore()
                return
            self.stop_process()
        event.accept()


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")  # PyQt5 wheels ship the X11 plugin; runs via XWayland
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("ReelForge")
    app.setStyle("Fusion")
    app.setFont(theme.ui_font(10.5))
    app.setStyleSheet(theme.STYLESHEET)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
