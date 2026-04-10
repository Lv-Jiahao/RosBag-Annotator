"""
Image preview widgets.

SingleStreamPanel   — one image topic, bisect-based frame lookup
MultiStreamPreviewWidget — N panels side-by-side, shared timeline
"""
from __future__ import annotations
import bisect
from typing import List, Optional, Tuple

from PyQt6.QtCore    import Qt, QTimer, pyqtSignal
from PyQt6.QtGui     import QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar,
)

from .models    import BagMeta
from .extractor import FullFrameExtractor

_DEBUG = True


class SingleStreamPanel(QWidget):
    """
    Displays the frame sequence of one image topic.
    - No topic combo: managed by MultiStreamPreviewWidget
    - O(log n) bisect_right lookup on header.stamp for cross-topic alignment
    - 33 ms throttle timer (~30 fps) prevents flicker during bulk frame arrival
    """
    PW = 320; PH = 220

    def __init__(self, topic_name: str, parent=None):
        super().__init__(parent)
        self._topic_name = topic_name
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2); lay.setSpacing(3)

        # header
        hdr = QLabel(topic_name.split("/")[-1])
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.setToolTip(topic_name)
        hdr.setStyleSheet("color:#89b4fa;font-size:10px;font-weight:bold;")
        lay.addWidget(hdr)

        # image + info
        mid = QHBoxLayout(); mid.setSpacing(6)

        self.img_label = QLabel()
        self.img_label.setFixedSize(self.PW, self.PH)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet(
            "background:#0d0d1a;border:1px solid #313244;border-radius:6px;")
        self.img_label.setText(
            '<span style="color:#585b70;font-size:11px;">Loading…</span>')
        mid.addWidget(self.img_label)

        info = QVBoxLayout(); info.setSpacing(4)
        info.addWidget(QLabel("📡 话题"))

        lbl_topic = QLabel(topic_name)
        lbl_topic.setWordWrap(True)
        lbl_topic.setStyleSheet(
            "color:#a6adc8;font-size:9px;background:#1e1e2e;"
            "border:1px solid #313244;border-radius:3px;padding:3px;")
        lbl_topic.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        info.addWidget(lbl_topic)

        self.ts_label   = QLabel("—")
        self.stat_label = QLabel("")
        self.ts_label.setStyleSheet("color:#a6adc8;font-size:10px;margin-top:8px;")
        self.stat_label.setWordWrap(True)
        self.stat_label.setStyleSheet("color:#6c7086;font-size:9px;")
        info.addWidget(self.ts_label)
        info.addWidget(self.stat_label)
        info.addStretch()
        mid.addLayout(info)
        lay.addLayout(mid)

        self.load_bar = QProgressBar()
        self.load_bar.setMaximumHeight(4)
        self.load_bar.setTextVisible(False)
        self.load_bar.setVisible(False)
        lay.addWidget(self.load_bar)

        # frame storage
        self._frames:           List[Tuple[int, QPixmap]] = []
        self._ts_arr:           List[int] = []
        self._last_cursor_ns:   int = -1
        self._last_display_idx: int = -1

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(33)
        self._refresh_timer.timeout.connect(self._throttled_refresh)

        self._extractor: Optional[FullFrameExtractor] = None

    # ── public API ─────────────────────────────────────────────────────────────

    def start_load(self, meta: BagMeta, topic: dict):
        self._stop_extractor()
        self._frames.clear(); self._ts_arr.clear()
        self._last_display_idx = -1
        self.load_bar.setVisible(True); self.load_bar.setMaximum(0)
        self.stat_label.setText("Loading…")
        self.img_label.setPixmap(QPixmap())
        self.img_label.setText(
            '<span style="color:#585b70;font-size:11px;">Loading…</span>')

        w = FullFrameExtractor(
            meta.bag_path, topic["name"], topic["type"],
            meta.start_time_ns, meta.end_time_ns, meta.storage_id, self)
        w.frame_ready.connect(self.add_frame)
        w.progress.connect(self._on_progress)
        w.finished.connect(self._on_finished)
        self._extractor = w; w.start()

    def add_frame(self, ts_ns, qimage: QImage):
        """Called in the main thread (Qt queued connection). QImage → QPixmap here."""
        ts_ns = int(ts_ns)
        px    = QPixmap.fromImage(qimage)
        if self._ts_arr and ts_ns >= self._ts_arr[-1]:
            self._ts_arr.append(ts_ns)
            self._frames.append((ts_ns, px))
        else:
            idx = bisect.bisect_left(self._ts_arr, ts_ns)
            self._ts_arr.insert(idx, ts_ns)
            self._frames.insert(idx, (ts_ns, px))
        if self._last_cursor_ns >= 0 and not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def show_at(self, cursor_ns: int):
        self._last_cursor_ns = cursor_ns
        self._display_at(cursor_ns)

    def clear(self):
        self._stop_extractor()
        self._frames.clear(); self._ts_arr.clear()
        self._last_cursor_ns = -1; self._last_display_idx = -1
        self._refresh_timer.stop()
        self.img_label.setPixmap(QPixmap())
        self.img_label.setText('<span style="color:#585b70;font-size:11px;">—</span>')
        self.ts_label.setText("—"); self.stat_label.setText("")

    def get_topic_name(self) -> str:
        return self._topic_name

    # ── internal ───────────────────────────────────────────────────────────────

    def _throttled_refresh(self):
        if self._last_cursor_ns >= 0:
            self._display_at(self._last_cursor_ns)

    def _display_at(self, cursor_ns: int):
        if not self._ts_arr: return
        n   = len(self._ts_arr)
        idx = bisect.bisect_right(self._ts_arr, cursor_ns) - 1
        if idx < 0:  idx = 0
        if idx >= n: idx = n - 1
        if idx == self._last_display_idx: return
        ts, px = self._frames[idx]
        self.img_label.setPixmap(
            px.scaled(self.img_label.size(),
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation))
        rel_s = (ts - self._ts_arr[0]) / 1e9
        self.ts_label.setText(f"t+{rel_s:.3f}s  [{idx+1}/{n}]")
        self._last_display_idx = idx

    def _stop_extractor(self):
        if self._extractor and self._extractor.isRunning():
            self._extractor.stop(); self._extractor.wait(800)
        self._extractor = None

    def _on_progress(self, count: int):
        self.stat_label.setText(f"{count} frames…")
        if count > 0 and self.load_bar.maximum() == 0:
            self.load_bar.setMaximum(1000)
        self.load_bar.setValue(count % 1000)

    def _on_finished(self, count: int):
        self.load_bar.setVisible(False)
        self.stat_label.setText(f"✓ {len(self._frames)} frames")
        if self._last_cursor_ns >= 0:
            self._display_at(self._last_cursor_ns)


class MultiStreamPreviewWidget(QWidget):
    """
    Side-by-side panels for all image topics in a bag.
    All panels share the same timeline via show_at(cursor_ns).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._panels: List[SingleStreamPanel] = []
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0); self._lay.setSpacing(8)
        self._placeholder = QLabel("Load a bag to enable preview")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color:#585b70;font-size:11px;")
        self._lay.addWidget(self._placeholder)

    def set_bag(self, meta: BagMeta):
        self._clear_panels()
        topics = meta.image_topics
        if not topics:
            self._placeholder.setText("No image topics in this bag")
            self._placeholder.show(); return
        self._placeholder.hide()
        for t in topics:
            panel = SingleStreamPanel(t["name"], self)
            panel.start_load(meta, t)
            self._lay.addWidget(panel)
            self._panels.append(panel)

    def show_at(self, cursor_ns: int):
        for p in self._panels:
            p.show_at(cursor_ns)

    def clear(self):
        self._clear_panels()
        self._placeholder.setText("Load a bag to enable preview")
        self._placeholder.show()

    def _clear_panels(self):
        for p in self._panels:
            p.clear(); self._lay.removeWidget(p); p.deleteLater()
        self._panels.clear()
