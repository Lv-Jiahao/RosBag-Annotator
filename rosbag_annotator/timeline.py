"""
TimelineWidget — interactive segment timeline.

Interactions:
  Left-click on track  → add cut point
  Drag diamond handle  → move cut point
  Right-click handle   → remove cut point
  Click on segment     → select segment
"""
from __future__ import annotations
from PyQt6.QtCore    import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui     import (QPainter, QPen, QColor, QBrush,
                              QPolygonF, QFont)
from PyQt6.QtWidgets import QWidget, QMenu

SEG_COLORS = [
    QColor(137,180,250,200), QColor(166,227,161,200),
    QColor(250,179,135,200), QColor(203,166,247,200),
    QColor(243,139,168,200), QColor(137,220,235,200),
    QColor(249,226,175,200), QColor(180,190,254,200),
]


def _nice_interval(total_s: float, width_px: float) -> float:
    raw = total_s / max(width_px / 90, 1)
    for n in [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800]:
        if n >= raw: return n
    return 3600


class TimelineWidget(QWidget):
    cut_points_changed = pyqtSignal()
    segment_selected   = pyqtSignal(int)
    cursor_moved       = pyqtSignal(object)   # int ns (Python, no truncation)

    RULER_H  = 26
    TRACK_H  = 64
    HANDLE_R = 7
    PAD      = 48

    def __init__(self, parent=None):
        super().__init__(parent)
        h = self.RULER_H + self.TRACK_H + 12
        self.setMinimumHeight(h); self.setMaximumHeight(h + 10)
        self.setMouseTracking(True)
        self.start_ns = 0; self.end_ns = 0; self.cut_points = []
        self.selected_seg = -1; self.hovered_cut = -1
        self.dragging_cut = -1; self._cursor_ns = -1
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)

    # ── public API ─────────────────────────────────────────────────────────────

    def load(self, start_ns: int, end_ns: int, cut_points=None):
        self.start_ns = start_ns; self.end_ns = end_ns
        self.cut_points = sorted(cut_points or [])
        self.selected_seg = -1; self.hovered_cut = -1
        self.dragging_cut = -1; self._cursor_ns = -1
        self.update()

    def get_cut_points(self): return sorted(self.cut_points)

    def set_cut_points(self, pts):
        self.cut_points = sorted(pts); self.update(); self.cut_points_changed.emit()

    def select_segment(self, idx: int):
        self.selected_seg = idx; self.update()

    # ── geometry helpers ───────────────────────────────────────────────────────

    def _track_rect(self):
        return QRectF(self.PAD, self.RULER_H,
                      self.width() - 2 * self.PAD, self.TRACK_H)

    def _ns_to_x(self, ns: int) -> float:
        r = self._track_rect()
        if self.end_ns == self.start_ns: return r.left()
        return r.left() + (ns - self.start_ns) / (self.end_ns - self.start_ns) * r.width()

    def _x_to_ns(self, x: float) -> int:
        r = self._track_rect()
        return self.start_ns + int(
            max(0., min(1., (x - r.left()) / r.width())) * (self.end_ns - self.start_ns))

    def _cut_at(self, x: float) -> int:
        for i, cp in enumerate(self.cut_points):
            if abs(self._ns_to_x(cp) - x) <= self.HANDLE_R + 4: return i
        return -1

    def _seg_at(self, x: float, y: float) -> int:
        r = self._track_rect()
        if not r.contains(x, y): return -1
        ns = self._x_to_ns(x)
        b  = [self.start_ns] + sorted(self.cut_points) + [self.end_ns]
        for i in range(len(b) - 1):
            if b[i] <= ns <= b[i+1]: return i
        return -1

    # ── paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.end_ns <= self.start_ns:
            p.fillRect(self.rect(), QColor(30, 30, 46))
            p.setPen(QColor(88, 91, 112))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "No bag loaded — add a bag folder to start")
            return

        r = self._track_rect()
        b = [self.start_ns] + sorted(self.cut_points) + [self.end_ns]

        # segments
        for i in range(len(b) - 1):
            x1, x2 = self._ns_to_x(b[i]), self._ns_to_x(b[i+1])
            sr  = QRectF(x1, r.top(), x2 - x1, r.height())
            col = SEG_COLORS[i % len(SEG_COLORS)]
            if i == self.selected_seg:
                bright = QColor(col); bright.setAlpha(240)
                p.fillRect(sr, bright); p.setPen(QPen(Qt.GlobalColor.white, 2))
            else:
                p.fillRect(sr, col); p.setPen(QPen(QColor(255, 255, 255, 50), 1))
            p.drawRect(sr)
            if x2 - x1 > 24:
                f = QFont(); f.setBold(True); f.setPointSize(12); p.setFont(f)
                p.setPen(QColor(24, 24, 37, 220))
                p.drawText(sr, Qt.AlignmentFlag.AlignCenter, str(i + 1))

        # ruler
        p.fillRect(QRectF(r.left(), 0, r.width(), self.RULER_H), QColor(24, 24, 37))
        total_s = (self.end_ns - self.start_ns) / 1e9
        iv = _nice_interval(total_s, r.width())
        f2 = QFont(); f2.setPointSize(8); p.setFont(f2)
        p.setPen(QColor(166, 173, 200))
        t = 0.
        while t <= total_s + 1e-9:
            x = self._ns_to_x(self.start_ns + int(t * 1e9))
            p.drawLine(QPointF(x, self.RULER_H - 6), QPointF(x, self.RULER_H))
            p.drawText(QRectF(x - 28, 2, 56, self.RULER_H - 8),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       f"{t:.0f}s" if iv >= 1 else f"{t:.1f}s")
            t += iv

        # cursor
        if self._cursor_ns >= 0:
            cx  = self._ns_to_x(self._cursor_ns)
            rel = (self._cursor_ns - self.start_ns) / 1e9
            p.setPen(QPen(QColor(255, 255, 255, 160), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(cx, r.top()), QPointF(cx, r.bottom()))
            bw = 52; bh = 16; bx = max(r.left(), min(cx - bw / 2, r.right() - bw))
            p.setBrush(QBrush(QColor(137, 180, 250, 220))); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(bx, 2, bw, bh), 3, 3)
            fb = QFont(); fb.setPointSize(8); fb.setBold(True); p.setFont(fb)
            p.setPen(QColor(24, 24, 37))
            p.drawText(QRectF(bx, 2, bw, bh), Qt.AlignmentFlag.AlignCenter, f"{rel:.2f}s")

        # cut handles
        mid_y = r.top() + r.height() / 2
        for i, cp in enumerate(self.cut_points):
            x   = self._ns_to_x(cp)
            hot = (i == self.hovered_cut or i == self.dragging_cut)
            col = QColor(250, 219, 20) if hot else QColor(243, 139, 168)
            p.setPen(QPen(col, 2 if hot else 1.5))
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            dia = QPolygonF([
                QPointF(x, mid_y - self.HANDLE_R * 1.4),
                QPointF(x + self.HANDLE_R, mid_y),
                QPointF(x, mid_y + self.HANDLE_R * 1.4),
                QPointF(x - self.HANDLE_R, mid_y),
            ])
            p.setPen(QPen(col.darker(120), 1.5)); p.setBrush(QBrush(col))
            p.drawPolygon(dia)
            if hot:
                rel = (cp - self.start_ns) / 1e9
                fb2 = QFont(); fb2.setPointSize(8); fb2.setBold(True); p.setFont(fb2)
                p.setPen(Qt.GlobalColor.white)
                p.drawText(QRectF(min(x + 6, r.right() - 52), r.top() + 2, 60, 16),
                           f"{rel:.3f}s")
        p.end()

    # ── mouse ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if self.end_ns <= self.start_ns: return
        x = ev.position().x(); y = ev.position().y(); r = self._track_rect()
        if ev.button() == Qt.MouseButton.LeftButton:
            ci = self._cut_at(x)
            if ci >= 0:
                self.dragging_cut = ci; self.hovered_cut = -1
            elif r.contains(x, y):
                ns  = self._x_to_ns(x)
                gap = (self.end_ns - self.start_ns) * 0.002
                if not any(abs(cp - ns) < gap for cp in self.cut_points):
                    self.cut_points.append(ns); self.cut_points.sort()
                    self.cut_points_changed.emit(); self.update()
                seg = self._seg_at(x, y)
                if seg >= 0 and seg != self.selected_seg:
                    self.selected_seg = seg; self.segment_selected.emit(seg); self.update()

    def mouseMoveEvent(self, ev):
        if self.end_ns <= self.start_ns: return
        x = ev.position().x()
        if self.dragging_cut >= 0:
            ns  = self._x_to_ns(x)
            ns  = max(self.start_ns + 1, min(self.end_ns - 1, ns))
            cps = sorted(self.cut_points); idx = self.dragging_cut
            if idx > 0:           ns = max(ns, cps[idx - 1] + 1)
            if idx < len(cps)-1:  ns = min(ns, cps[idx + 1] - 1)
            self.cut_points[idx] = ns
            self._cursor_ns = ns; self.update()
            self.cut_points_changed.emit(); self.cursor_moved.emit(ns)
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            old = self.hovered_cut; self.hovered_cut = self._cut_at(x)
            self.setCursor(Qt.CursorShape.SizeHorCursor
                           if self.hovered_cut >= 0 else Qt.CursorShape.CrossCursor)
            r  = self._track_rect(); ns = self._x_to_ns(x)
            if r.contains(x, ev.position().y()) or self.hovered_cut >= 0:
                if self._cursor_ns != ns:
                    self._cursor_ns = ns; self.update(); self.cursor_moved.emit(ns)
            else:
                if self._cursor_ns >= 0: self._cursor_ns = -1; self.update()
            if old != self.hovered_cut: self.update()

    def mouseReleaseEvent(self, ev):
        if self.dragging_cut >= 0:
            self.dragging_cut = -1; self.cut_points_changed.emit(); self.update()

    def leaveEvent(self, ev):
        self._cursor_ns = -1; self.update()

    def _ctx_menu(self, pos):
        idx = self._cut_at(float(pos.x()))
        if idx < 0: return
        rel  = (self.cut_points[idx] - self.start_ns) / 1e9
        menu = QMenu(self)
        act  = menu.addAction(f"🗑  Remove cut point @ {rel:.3f}s")
        if menu.exec(self.mapToGlobal(pos)) == act:
            self.cut_points.pop(idx); self.update(); self.cut_points_changed.emit()
