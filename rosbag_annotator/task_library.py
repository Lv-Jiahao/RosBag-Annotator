"""
TaskLibraryWidget — create, edit, delete and assign pre-defined tasks.

A *Task* bundles (name, prompt, out_dir) so that annotators can fill
both fields of a segment with a single double-click / button press.

Public API
----------
get_tasks()               → List[Task]
set_tasks(tasks)          → replace the whole list (e.g. on JSON load)
task_assign_requested     → pyqtSignal(Task)   emitted when user assigns
"""
from __future__ import annotations
from typing import List, Optional

from PyQt6.QtCore    import Qt, pyqtSignal
from PyQt6.QtGui     import QBrush, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton,
    QDialog, QDialogButtonBox, QLabel,
    QLineEdit, QTextEdit, QFileDialog,
)

from .models import Task

# One colour per task (cycles for >8 tasks)
_TASK_COLORS = [
    QColor(137, 180, 250),   # blue
    QColor(166, 227, 161),   # green
    QColor(250, 179, 135),   # peach
    QColor(203, 166, 247),   # mauve
    QColor(243, 139, 168),   # red/pink
    QColor(137, 220, 235),   # teal
    QColor(249, 226, 175),   # yellow
    QColor(180, 190, 254),   # lavender
]


# ── Task editor dialog ─────────────────────────────────────────────────────────

class _TaskEditDialog(QDialog):
    """Add or edit a single Task (name + prompt + out_dir)."""

    _FIELD = (
        "background:#181825;color:#cdd6f4;border:1px solid #45475a;"
        "border-radius:4px;font-size:12px;padding:5px;"
    )
    _LBL   = "color:#a6adc8;font-size:11px;margin-top:4px;"

    def __init__(self, parent, task: Optional[Task] = None):
        super().__init__(parent)
        self.setWindowTitle("编辑任务" if task else "新建任务")
        self.setMinimumWidth(520)

        lay = QVBoxLayout(self)
        lay.setSpacing(6); lay.setContentsMargins(16, 14, 16, 12)

        # ── Name ──────────────────────────────────────────────────────────────
        lay.addWidget(self._lbl("任务名称 (Task Name) *"))
        self.name_edit = QLineEdit(task.name if task else "")
        self.name_edit.setPlaceholderText("e.g.  Pick apple  /  Place cup  /  Open door")
        self.name_edit.setStyleSheet(self._FIELD)
        self.name_edit.setMinimumHeight(32)
        lay.addWidget(self.name_edit)

        # ── Prompt ────────────────────────────────────────────────────────────
        lay.addWidget(self._lbl("Task Prompt / Description"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setAcceptRichText(False)   # paste strips source colour/formatting        self.prompt_edit.setPlainText(task.prompt if task else "")
        self.prompt_edit.setPlaceholderText("Task description written into metadata.yaml ...")
        self.prompt_edit.setStyleSheet(
            "QTextEdit { background:#181825; border:1px solid #45475a; "
            "border-radius:4px; font-size:13px; padding:5px; }")
        # QTextEdit renders inside a viewport child widget — colour must be
        # set there directly, not on the outer frame.
        from PyQt6.QtGui import QPalette as _P
        pal = self.prompt_edit.palette()
        pal.setColor(_P.ColorRole.Text, QColor("#e0e4f0"))
        pal.setColor(_P.ColorRole.Base, QColor("#181825"))
        self.prompt_edit.setPalette(pal)
        self.prompt_edit.viewport().setPalette(pal)
        self.prompt_edit.setFixedHeight(88)
        lay.addWidget(self.prompt_edit)

        # ── Output directory ──────────────────────────────────────────────────
        lay.addWidget(self._lbl("输出目录 (Output Directory)"))
        dir_row = QHBoxLayout(); dir_row.setSpacing(6)
        self.dir_edit = QLineEdit(task.out_dir if task else "")
        self.dir_edit.setPlaceholderText("(可选) /path/to/task/output/")
        self.dir_edit.setStyleSheet(self._FIELD)
        self.dir_edit.setMinimumHeight(32)
        btn_br = QPushButton("Browse…")
        btn_br.setFixedSize(76, 32)
        btn_br.clicked.connect(self._browse)
        dir_row.addWidget(self.dir_edit, stretch=1)
        dir_row.addWidget(btn_br)
        lay.addLayout(dir_row)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.setStyleSheet(
            "QPushButton{background:#313244;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:4px;padding:6px 22px;font-size:12px;}"
            "QPushButton:hover{background:#45475a;}")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._task: Optional[Task] = None

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _lbl(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("color:#a6adc8;font-size:11px;margin-top:4px;")
        return l

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setStyleSheet(
                self.name_edit.styleSheet() + "border-color:#f38ba8;")
            self.name_edit.setFocus()
            return
        self._task = Task(
            name=name,
            prompt=self.prompt_edit.toPlainText().strip(),
            out_dir=self.dir_edit.text().strip(),
        )
        self.accept()

    def get_task(self) -> Optional[Task]:
        return self._task


# ── Task library widget ────────────────────────────────────────────────────────

class TaskLibraryWidget(QWidget):
    """
    Compact left-panel widget that manages the task library.

    Signals
    -------
    task_assign_requested(Task)
        Emitted when the user double-clicks a task or presses "Assign".
        MainWindow should apply the task's prompt + out_dir to the
        currently selected segment.
    """

    task_assign_requested = pyqtSignal(object)   # Task

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: List[Task] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(4)

        # ── Task list ─────────────────────────────────────────────────────────
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setStyleSheet(
            "QListWidget{background:#181825;border:1px solid #313244;"
            "border-radius:4px;font-size:11px;}"
            "QListWidget::item{padding:5px 8px;}"
            "QListWidget::item:selected{background:#45475a;color:#cdd6f4;}"
            "QListWidget::item:alternate{background:#1e1e2e;}"
            "QListWidget::item:hover{background:#313244;}")
        self.list_widget.setToolTip("Double-click a task to assign it to the selected segment")
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        lay.addWidget(self.list_widget, stretch=1)

        # ── Add / Edit / Remove ───────────────────────────────────────────────
        r1 = QHBoxLayout(); r1.setSpacing(4); r1.setContentsMargins(0, 0, 0, 0)
        self.btn_add  = QPushButton("＋ Add")
        self.btn_edit = QPushButton("✎ Edit")
        self.btn_del  = QPushButton("✕ Del")
        for b in (self.btn_add, self.btn_edit, self.btn_del):
            b.setFixedHeight(24)
            b.setStyleSheet(
                "QPushButton{background:#313244;color:#cdd6f4;border:1px solid #45475a;"
                "border-radius:3px;padding:2px 6px;font-size:11px;}"
                "QPushButton:hover{background:#45475a;}")
        self.btn_add.clicked.connect(self._add_task)
        self.btn_edit.clicked.connect(self._edit_task)
        self.btn_del.clicked.connect(self._del_task)
        r1.addWidget(self.btn_add, stretch=1)
        r1.addWidget(self.btn_edit, stretch=1)
        r1.addWidget(self.btn_del, stretch=1)
        lay.addLayout(r1)

        # ── Assign button ─────────────────────────────────────────────────────
        self.btn_assign = QPushButton("▶  Assign to Selected Segment")
        self.btn_assign.setFixedHeight(28)
        self.btn_assign.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#89b4fa;font-weight:bold;"
            "border:1px solid #2563a8;border-radius:4px;font-size:11px;}"
            "QPushButton:hover{background:#1e4d78;color:#cdd6f4;}"
            "QPushButton:pressed{background:#2563a8;}")
        self.btn_assign.clicked.connect(self._assign_current)
        lay.addWidget(self.btn_assign)

    # ── public API ─────────────────────────────────────────────────────────────

    def get_tasks(self) -> List[Task]:
        return list(self._tasks)

    def set_tasks(self, tasks: List[Task]):
        self._tasks = list(tasks)
        self._refresh()

    def current_task(self) -> Optional[Task]:
        r = self.list_widget.currentRow()
        return self._tasks[r] if 0 <= r < len(self._tasks) else None

    # ── internal ───────────────────────────────────────────────────────────────

    def _refresh(self):
        cur = self.list_widget.currentRow()
        self.list_widget.clear()
        for i, t in enumerate(self._tasks):
            col  = _TASK_COLORS[i % len(_TASK_COLORS)]
            # show name; tooltip has full prompt + dir
            item = QListWidgetItem(f"  {t.name}")
            item.setForeground(QBrush(col))
            tip_parts = []
            if t.prompt:  tip_parts.append(f"📝 {t.prompt}")
            if t.out_dir: tip_parts.append(f"📁 {t.out_dir}")
            item.setToolTip("\n".join(tip_parts) if tip_parts else "(no details)")
            self.list_widget.addItem(item)
        # restore selection
        if 0 <= cur < self.list_widget.count():
            self.list_widget.setCurrentRow(cur)

    def _add_task(self):
        dlg = _TaskEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            t = dlg.get_task()
            if t:
                self._tasks.append(t)
                self._refresh()
                self.list_widget.setCurrentRow(len(self._tasks) - 1)

    def _edit_task(self):
        r = self.list_widget.currentRow()
        if not (0 <= r < len(self._tasks)):
            return
        dlg = _TaskEditDialog(self, self._tasks[r])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            t = dlg.get_task()
            if t:
                self._tasks[r] = t
                self._refresh()
                self.list_widget.setCurrentRow(r)

    def _del_task(self):
        r = self.list_widget.currentRow()
        if 0 <= r < len(self._tasks):
            self._tasks.pop(r)
            self._refresh()

    def _on_double_click(self, _item: QListWidgetItem):
        self._assign_current()

    def _assign_current(self):
        t = self.current_task()
        if t:
            self.task_assign_requested.emit(t)