"""실행 진행 패널: 표준구조 작업의 단계를 실시간으로 보여 준다 (대기 → 진행 중 → 완료, 단계별 결과와 걸린 시간)."""
import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QPlainTextEdit, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

from . import theme
from .widgets import label

WAIT, RUN, DONE, FAIL = "wait", "run", "done", "fail"
# 상태 표시: 글꼴에 ✓ 같은 기호가 없을 수 있어 동그라미를 스타일로 그린다
MARK = {
    WAIT: "border: 1.5px solid #D0D5DD; background: #FFFFFF;",
    RUN: f"border: 3px solid #D1E0FF; background: {theme.ACCENT};",
    DONE: f"border: 0; background: {theme.KINDS['success'][0]}; image: url({theme.asset('check.svg')});",
    FAIL: f"border: 0; background: {theme.KINDS['error'][0]};",
}


class _StepRow(QWidget):
    def __init__(self, number: int, name: str):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(8)
        self.mark = label("")
        self.mark.setFixedSize(14, 14)
        self.name = label(f"{number}. {name}")
        self.name.setMinimumWidth(190)
        self.detail = label("", "muted")
        self.detail.setMinimumWidth(0)
        self.elapsed = label("", "muted")
        self.elapsed.setFixedWidth(46)
        self.elapsed.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.mark)
        row.addWidget(self.name)
        row.addWidget(self.detail, 1)
        row.addWidget(self.elapsed)
        self.set(WAIT)

    def set(self, state: str, detail: str = "", seconds: float | None = None):
        self.mark.setStyleSheet(f"border-radius: 7px; {MARK[state]}")
        font = self.name.font()
        font.setBold(state == RUN)
        self.name.setFont(font)
        self.name.setStyleSheet(f"color: {theme.TEXT if state != WAIT else '#98A2B3'};")
        if detail:
            self.detail.setText(detail)
            self.detail.setToolTip(detail)
        self.elapsed.setText(f"{seconds:.1f}초" if seconds is not None else "")


class RunPanel(QFrame):
    """steps: [(키, 이름)] — service.STEPS."""

    def __init__(self, steps: list):
        super().__init__()
        self.setObjectName("card")
        self.steps = steps
        self.index = {key: i for i, (key, _) in enumerate(steps)}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        self.title = label("실행 준비", "sectionTitle")
        self.summary = label("", "muted")
        head.addWidget(self.title)
        head.addSpacing(8)
        head.addWidget(self.summary)
        head.addStretch(1)
        self.toggle_log = QPushButton("자세한 기록 보기")
        self.toggle_log.setObjectName("link")
        self.toggle_log.clicked.connect(self._toggle_log)
        self.collapse = QPushButton("접기")
        self.collapse.setObjectName("link")
        self.collapse.clicked.connect(self._toggle_steps)
        self.folder_button = QPushButton("폴더 열기")
        self.folder_button.setObjectName("link")
        self.folder_button.clicked.connect(lambda: self.folder and os.startfile(str(self.folder)))
        self.folder_button.setVisible(False)
        self.folder = None
        self.close_button = QPushButton("닫기")
        self.close_button.setObjectName("link")
        self.close_button.clicked.connect(self.hide)
        for b in (self.folder_button, self.toggle_log, self.collapse, self.close_button):
            head.addWidget(b)
        lay.addLayout(head)

        self.bar = QProgressBar()
        self.bar.setRange(0, len(steps))
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)

        self.grid_box = QWidget()
        grid = QGridLayout(self.grid_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(0)
        half = (len(steps) + 1) // 2
        self.rows = []
        for i, (_, name) in enumerate(steps):
            row = _StepRow(i + 1, name)
            grid.addWidget(row, i % half, i // half)
            self.rows.append(row)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addWidget(self.grid_box)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(160)
        self.log.setStyleSheet(f"QPlainTextEdit {{ background: {theme.SUBTLE}; border: 0; border-radius: 8px;"
                               f" font-family: {theme.MONO}; font-size: 12px; padding: 6px; }}")
        self.log.setVisible(False)
        lay.addWidget(self.log)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)
        self._started = self._step_started = 0.0
        self._current = -1

    # --- 실행 흐름 ----------------------------------------------------------

    def start(self):
        self._started = self._step_started = time.monotonic()
        self._current = 0
        for row in self.rows:
            row.set(WAIT)
            row.detail.setText("")
        self.rows[0].set(RUN)
        self.bar.setValue(0)
        self.log.clear()
        self.title.setText("실행 중")
        self.grid_box.setVisible(True)
        self.collapse.setText("접기")
        self.close_button.setVisible(False)
        self.folder_button.setVisible(False)
        self.show()
        self._timer.start()
        self._tick()

    def step_done(self, key: str, detail: str = ""):
        i = self.index.get(key)
        if i is None:
            return
        now = time.monotonic()
        for j in range(self._current, i):   # 건너뛴 단계는 완료로
            self.rows[j].set(DONE)
        self.rows[i].set(DONE, detail, now - self._step_started)
        self._step_started = now
        self._current = i + 1
        self.bar.setValue(i + 1)
        if self._current < len(self.rows):
            self.rows[self._current].set(RUN)
        self._tick()

    def add_log(self, line: str):
        self.log.appendPlainText(line.rstrip())

    def finish(self, ok: bool, message: str = "", folder=None):
        """끝나면 단계 목록은 한 줄로 접는다 (펼치기로 다시 볼 수 있음)."""
        self._timer.stop()
        total = time.monotonic() - self._started
        if ok:
            self.title.setText("완료")
            self.summary.setText(f"{len(self.rows)}단계 · {total:.1f}초" + (f" · {message}" if message else ""))
            self.folder = folder
            self.folder_button.setVisible(folder is not None)
            if folder is not None:
                self.folder_button.setToolTip(str(folder))
            self.grid_box.setVisible(False)
            self.collapse.setText("펼치기")
        else:
            if 0 <= self._current < len(self.rows):
                self.rows[self._current].set(FAIL, message.splitlines()[0] if message else "실패")
            self.title.setText("실패")
            self.summary.setText(f"{self._current + 1}단계에서 멈춤 · {total:.1f}초")
            self.add_log(message)
        self.close_button.setVisible(True)

    def _tick(self):
        if self._current < 0:
            return
        done = min(self._current, len(self.rows))
        name = self.steps[done][1] if done < len(self.steps) else ""
        elapsed = time.monotonic() - self._started
        self.summary.setText(f"{done} / {len(self.rows)}단계 · {elapsed:.1f}초" + (f" · {name}" if name else ""))

    def _toggle_log(self):
        show = not self.log.isVisible()
        self.log.setVisible(show)
        self.toggle_log.setText("자세한 기록 숨기기" if show else "자세한 기록 보기")

    def _toggle_steps(self):
        show = not self.grid_box.isVisible()
        self.grid_box.setVisible(show)
        self.collapse.setText("접기" if show else "펼치기")
