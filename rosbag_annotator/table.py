"""
SegmentTable — QTableWidget for segment metadata editing.

Columns: #, Start, End, Duration, Prompt, Output Directory
Double-click Prompt → inline editor
Double-click Dir    → folder browser
Right-click row     → context menu (delete / set dir / clear dir)
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

    _last_task_dir: str = ""

    COLS       = ["#", "Start", "End", "Duration",
                  "Task Prompt / Description", "📁 任务目录"]
    COL_PROMPT = 4
    COL_DIR    = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.COLS))
        self.setHorizontalHeaderLabels(self.COLS)
        hdr   = self.horizontalHeader()
        modes = ([QHeaderView.ResizeMode.Fixed] * 4
                 + [QHeaderView.ResizeMode.Stretch] * 2)
        for c, m in enumerate(modes): hdr.setSectionResizeMode(c, m)
        self.setColumnWidth(0, 32); self.setColumnWidth(1, 100)
        self.setColumnWidth(2, 100); self.setColumnWidth(3, 80)
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
            self._set(i, 1, s.start_str())
            self._set(i, 2, s.end_str())
            self._set(i, 3, s.duration_str())
            self._set(i, self.COL_PROMPT, s.prompt)
            self._set_dir_cell(i, s.out_dir)
            item = self.item(i, 0)
            if item:
                item.setBackground(QBrush(SEG_COLORS[i % len(SEG_COLORS)]))
                item.setForeground(QBrush(QColor(24, 24, 37)))
        self._lock = False
        if 0 <= sel < self.rowCount(): self.selectRow(sel)

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
        menu    = QMenu(self)
        act_del = menu.addAction(f"🗑  删除分段 {row+1}  （与相邻段合并）")
        act_dir = menu.addAction("📁  设置任务目录…")
        act_clr = menu.addAction("✕  清除任务目录")
        res = menu.exec(ev.globalPos())
        if   res == act_del: self.segment_delete_requested.emit(row)
        elif res == act_dir: self._browse_out_dir(row)
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
        if col == self.COL_PROMPT:
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
