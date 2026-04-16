"""
SegmentTable — QTableWidget for segment metadata editing.

Columns: #, Task, Start, End, Duration, Prompt, Output Directory
Double-click Prompt → inline editor
Double-click Dir    → folder browser
Right-click row     → context menu (delete / assign task / set dir / clear dir)
"""
from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore    import Qt, pyqtSignal
from PyQt6.QtGui     import QBrush, QColor
from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QMenu,
)

from .dialogs  import qinput_text
from .timeline import SEG_COLORS


class SegmentTable(QTableWidget):
    prompt_changed           = pyqtSignal(int, str)
    row_selected             = pyqtSignal(int)
    segment_delete_requested = pyqtSignal(int)
    out_dir_changed          = pyqtSignal(int, str)
    # emitted when user requests "assign task" from context menu
    # MainWindow opens the task picker and calls assign_task(row, task)
    task_assign_requested    = pyqtSignal(int)

    _last_task_dir: str = ""

    COLS       = ["#", "Task", "Start", "End", "Duration",
                  "Task Prompt / Description", "📁 任务目录"]
    COL_TASK   = 1
    COL_PROMPT = 5
    COL_DIR    = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.COLS))
        self.setHorizontalHeaderLabels(self.COLS)
        hdr   = self.horizontalHeader()
        # #=fixed, Task=fixed, Start/End/Dur=fixed, Prompt=stretch, Dir=stretch
        fixed_widths = [32, 90, 100, 100, 80]
        for c, w in enumerate(fixed_widths):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(c, w)
        hdr.setSectionResizeMode(self.COL_PROMPT, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(self.COL_DIR,    QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._lock = False
        self.itemSelectionChanged.connect(self._sel_changed)
        self.cellDoubleClicked.connect(self._dbl_click)

    # ── public API ─────────────────────────────────────────────────────────────

    def populate(self, segments):
        self._lock = True; sel = self.currentRow()
        self.setRowCount(len(segments))
        for i, s in enumerate(segments):
            self._set(i, 0, str(i+1), center=True)
            # COL_TASK: filled by assign_task() — show placeholder if empty
            if not self.item(i, self.COL_TASK):
                self._set_task_cell(i, "", QColor(88, 91, 112))
            self._set(i, 2, s.start_str())
            self._set(i, 3, s.end_str())
            self._set(i, 4, s.duration_str())
            self._set(i, self.COL_PROMPT, s.prompt)
            self._set_dir_cell(i, s.out_dir)
            item = self.item(i, 0)
            if item:
                item.setBackground(QBrush(SEG_COLORS[i % len(SEG_COLORS)]))
                item.setForeground(QBrush(QColor(24, 24, 37)))
        self._lock = False
        if 0 <= sel < self.rowCount(): self.selectRow(sel)

    def assign_task(self, row: int, task):
        """Apply a Task's name, prompt, and out_dir to the given row."""
        if not (0 <= row < self.rowCount()):
            return
        from .task_library import _TASK_COLORS   # avoid circular at module level
        col = _TASK_COLORS[row % len(_TASK_COLORS)]
        self._set_task_cell(row, task.name, col)
        # prompt
        if self.item(row, self.COL_PROMPT):
            self.item(row, self.COL_PROMPT).setText(task.prompt)
        else:
            self._set(row, self.COL_PROMPT, task.prompt)
        self.prompt_changed.emit(row, task.prompt)
        # out_dir
        self._set_dir_cell(row, task.out_dir)
        self.out_dir_changed.emit(row, task.out_dir)

    def select_row(self, idx: int):
        self._lock = True; self.selectRow(idx); self._lock = False
        item = self.item(idx, 0)
        if item: self.scrollToItem(item)

    def get_prompts(self):
        return [(self.item(r, self.COL_PROMPT).text()
                 if self.item(r, self.COL_PROMPT) else "")
                for r in range(self.rowCount())]

    def get_out_dirs(self):
        return [(self.item(r, self.COL_DIR).toolTip()
                 if self.item(r, self.COL_DIR) else "")
                for r in range(self.rowCount())]

    def set_prompt_text(self, row: int, text: str):
        if 0 <= row < self.rowCount() and self.item(row, self.COL_PROMPT):
            self.item(row, self.COL_PROMPT).setText(text)

    # ── events ─────────────────────────────────────────────────────────────────

    def contextMenuEvent(self, ev):
        row = self.rowAt(ev.pos().y())
        if row < 0: return
        menu      = QMenu(self)
        act_task  = menu.addAction(f"📚  从任务库分配  →  Segment {row+1}")
        menu.addSeparator()
        act_del   = menu.addAction(f"🗑  删除分段 {row+1}（与相邻段合并）")
        act_dir   = menu.addAction("📁  手动设置输出目录…")
        act_clr   = menu.addAction("✕  清除任务目录")
        res = menu.exec(ev.globalPos())
        if   res == act_task: self.task_assign_requested.emit(row)
        elif res == act_del:  self.segment_delete_requested.emit(row)
        elif res == act_dir:  self._browse_out_dir(row)
        elif res == act_clr:
            self._set_dir_cell(row, ""); self.out_dir_changed.emit(row, "")

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Delete:
            row = self.currentRow()
            if row >= 0: self.segment_delete_requested.emit(row)
        else:
            super().keyPressEvent(ev)

    # ── internal ───────────────────────────────────────────────────────────────

    def _set(self, row, col, text, center=False):
        item = QTableWidgetItem(text)
        if center: item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, col, item)

    def _set_task_cell(self, row: int, name: str, color: QColor):
        label = name if name else "—"
        item  = QTableWidgetItem(label)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QBrush(color))
        item.setToolTip(name or "右键 → 从任务库分配")
        self.setItem(row, self.COL_TASK, item)

    def _set_dir_cell(self, row: int, path: str):
        short = Path(path).name if path else "(未设置)"
        item  = QTableWidgetItem(short)
        item.setToolTip(path or "")
        item.setForeground(QBrush(
            QColor(137, 220, 235) if path else QColor(88, 91, 112)))
        self.setItem(row, self.COL_DIR, item)

    def _browse_out_dir(self, row: int):
        d = QFileDialog.getExistingDirectory(
            self, f"选择分段 {row+1} 的任务输出目录",
            SegmentTable._last_task_dir)
        if d:
            SegmentTable._last_task_dir = str(Path(d).parent)
            self._set_dir_cell(row, d)
            self.out_dir_changed.emit(row, d)

    def _sel_changed(self):
        if self._lock: return
        rows = self.selectedItems()
        if rows: self.row_selected.emit(rows[0].row())

    def _dbl_click(self, row: int, col: int):
        if col == self.COL_TASK:
            # double-click on Task column → trigger task assignment via MainWindow
            self.task_assign_requested.emit(row)
        elif col == self.COL_PROMPT:
            cur  = (self.item(row, self.COL_PROMPT).text()
                    if self.item(row, self.COL_PROMPT) else "")
            text, ok = qinput_text(
                self, f"Edit Prompt — Segment {row+1}", "Task description:", cur)
            if ok:
                if self.item(row, self.COL_PROMPT):
                    self.item(row, self.COL_PROMPT).setText(text)
                self.prompt_changed.emit(row, text)
        elif col == self.COL_DIR:
            self._browse_out_dir(row)
