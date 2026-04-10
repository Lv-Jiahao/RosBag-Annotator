"""
PromptPanel — compact prompt editor with history.
"""
from __future__ import annotations
from PyQt6.QtCore    import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QTextEdit, QPushButton,
)
from .dialogs import qmsg, qinput_item


class PromptPanel(QWidget):
    prompt_committed = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.seg_label = QLabel("Select a segment")
        self.seg_label.setFixedWidth(150)
        self.seg_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.seg_label.setStyleSheet("color:#a6adc8;font-size:11px;")
        lay.addWidget(self.seg_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.edit = QTextEdit()
        self.edit.setPlaceholderText("Task description…  (Ctrl+Enter to apply)")
        self.edit.setFixedHeight(62)
        self.edit.setStyleSheet(
            "background:#1e1e2e;color:#cdd6f4;border:1px solid #45475a;"
            " border-radius:4px;font-size:12px;padding:4px;")
        lay.addWidget(self.edit, stretch=1)

        right = QVBoxLayout(); right.setSpacing(6); right.setContentsMargins(0,0,0,0)
        self.btn_apply   = QPushButton("Apply ✓")
        self.btn_history = QPushButton("History ▾")
        for b in (self.btn_apply, self.btn_history):
            b.setFixedWidth(88); b.setFixedHeight(28)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_history.clicked.connect(self._show_history)
        right.addWidget(self.btn_apply); right.addWidget(self.btn_history)
        lay.addLayout(right)

        self._seg_idx = -1
        self._history = []

    # ── public API ─────────────────────────────────────────────────────────────

    def set_segment(self, idx: int, seg):
        self._seg_idx = idx
        self.seg_label.setText(
            f"Segment {idx+1}\n{seg.start_str()}\n→ {seg.end_str()}\n({seg.duration_str()})")
        self.edit.blockSignals(True)
        self.edit.setPlainText(seg.prompt)
        self.edit.blockSignals(False)

    def set_history(self, h): self._history = h

    # ── internal ───────────────────────────────────────────────────────────────

    def _apply(self):
        if self._seg_idx < 0: return
        text = self.edit.toPlainText().strip()
        if text and text not in self._history: self._history.append(text)
        self.prompt_committed.emit(self._seg_idx, text)

    def _show_history(self):
        if not self._history:
            qmsg(self, "info", "History", "No history yet."); return
        text, ok = qinput_item(
            self, "Prompt History", "Select:", list(reversed(self._history)))
        if ok and text:
            self.edit.setPlainText(text)
            if self._seg_idx >= 0:
                self.prompt_committed.emit(self._seg_idx, text)

    def keyPressEvent(self, ev):
        if (ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and ev.modifiers() == Qt.KeyboardModifier.ControlModifier):
            self._apply()
        else:
            super().keyPressEvent(ev)
