"""
MainWindow — top-level application window.
"""
from __future__ import annotations
import json
from pathlib import Path

from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QBrush, QColor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox,
    QProgressBar, QFileDialog, QMessageBox,
)

from .models        import BagAnnotation
from .meta          import load_bag_meta
from .preview       import MultiStreamPreviewWidget
from .timeline      import TimelineWidget, SEG_COLORS
from .table         import SegmentTable
from .prompt_panel  import PromptPanel
from .export        import ExportWorker
from .dialogs       import qmsg
from .models        import _is_image_type

STYLE = """
QMainWindow,QWidget{background:#1e1e2e;color:#cdd6f4;}
QSplitter::handle{background:#313244;}
QGroupBox{border:1px solid #313244;border-radius:6px;margin-top:8px;font-weight:bold;}
QGroupBox::title{subcontrol-origin:margin;left:8px;color:#89b4fa;}
QListWidget{background:#181825;border:1px solid #313244;border-radius:4px;font-size:12px;}
QListWidget::item:selected{background:#45475a;}
QListWidget::item:alternate{background:#1e1e2e;}
QTableWidget{background:#181825;border:1px solid #313244;border-radius:4px;
  gridline-color:#313244;font-size:12px;}
QTableWidget::item:selected{background:#45475a;}
QHeaderView::section{background:#313244;color:#cdd6f4;padding:5px;
  border:1px solid #45475a;font-weight:bold;}
QPushButton{background:#313244;color:#cdd6f4;border:1px solid #45475a;
  border-radius:4px;padding:5px 12px;font-size:12px;}
QPushButton:hover{background:#45475a;}QPushButton:pressed{background:#585b70;}
QPushButton#export_btn{background:#1e4d78;font-weight:bold;font-size:13px;}
QPushButton#export_btn:hover{background:#2563a8;}
QProgressBar{border:1px solid #45475a;border-radius:3px;background:#181825;text-align:center;}
QProgressBar::chunk{background:#89b4fa;border-radius:2px;}
QComboBox{background:#313244;color:#cdd6f4;border:1px solid #45475a;
  border-radius:4px;padding:3px 8px;}
QComboBox::drop-down{border:none;}
QComboBox QAbstractItemView{background:#181825;color:#cdd6f4;
  selection-background-color:#45475a;}
QMenuBar{background:#181825;}QMenuBar::item:selected{background:#313244;}
QMenu{background:#181825;border:1px solid #313244;}
QMenu::item:selected{background:#313244;}
QStatusBar{background:#11111b;border-top:1px solid #313244;}
QScrollBar:vertical{background:#181825;width:8px;}
QScrollBar::handle:vertical{background:#45475a;border-radius:4px;}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RosBag Annotation Tool — VLA Multi-task")
        self.setMinimumSize(1280, 820)
        self.current_bag_path = None
        self.annotations: dict[str, BagAnnotation] = {}
        self.bag_metas   = {}
        self.prompt_history = []
        self._last_bag_dir  = ""
        self._export_worker = None
        self._build_ui()
        self.setStyleSheet(STYLE)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_menus()
        spl = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(spl)
        spl.addWidget(self._build_left())
        spl.addWidget(self._build_right())
        spl.setSizes([255, 1025]); spl.setStretchFactor(1, 1)

        self.sb_label = QLabel("Ready — add a bag folder to start")
        self.statusBar().addWidget(self.sb_label, 1)
        self.pbar = QProgressBar()
        self.pbar.setFixedWidth(220); self.pbar.setVisible(False)
        self.statusBar().addPermanentWidget(self.pbar)

        try:
            import rosbag2_py  # noqa
        except ImportError:
            self.statusBar().showMessage("⚠  rosbag2_py not found", 8000)

    def _build_menus(self):
        def act(menu, label, slot, sc=None):
            a = menu.addAction(label); a.triggered.connect(slot)
            if sc: a.setShortcut(sc)
        mb = self.menuBar()
        fm = mb.addMenu("File")
        act(fm, "Add Bag Folder…",   self._add_bags,    "Ctrl+O")
        fm.addSeparator()
        act(fm, "Save Annotations…", self._save_json,   "Ctrl+S")
        act(fm, "Load Annotations…", self._load_json,   "Ctrl+L")
        fm.addSeparator()
        act(fm, "Quit",              self.close,         "Ctrl+Q")
        em = mb.addMenu("Export")
        act(em, "🚀 Export Current Bag", self._export_current, "Ctrl+E")
        act(em, "📦 Export All Bags…",   self._export_all)

    def _build_left(self):
        w   = QWidget(); w.setFixedWidth(255)
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4)

        grp = QGroupBox("📦  Bag Files"); gl = QVBoxLayout(grp)
        self.bag_list = QListWidget()
        self.bag_list.setAlternatingRowColors(True)
        self.bag_list.currentRowChanged.connect(self._on_bag_selected)
        gl.addWidget(self.bag_list)
        row = QHBoxLayout()
        ba  = QPushButton("＋ Add"); br = QPushButton("✕ Remove")
        ba.clicked.connect(self._add_bags); br.clicked.connect(self._remove_bag)
        row.addWidget(ba); row.addWidget(br); gl.addLayout(row)
        lay.addWidget(grp)

        tgrp = QGroupBox("📡  Topics"); tl = QVBoxLayout(tgrp)
        self.topic_list = QListWidget()
        self.topic_list.setStyleSheet("font-size:11px;")
        self.topic_list.setMaximumHeight(160)
        tl.addWidget(self.topic_list); lay.addWidget(tgrp)

        self.info_label = QLabel("—")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color:#a6adc8;font-size:11px;padding:4px;")
        lay.addWidget(self.info_label)
        lay.addStretch()
        return w

    def _build_right(self):
        w   = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(4)

        # timeline header
        th  = QWidget(); thl = QHBoxLayout(th); thl.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("⏱  Timeline  —  <span style='color:#a6adc8'>"
                      "click: add cut  |  drag: move  |  right-click: remove</span>")
        hint.setTextFormat(Qt.TextFormat.RichText)
        thl.addWidget(hint); thl.addStretch()
        btn_clr = QPushButton("Clear All Cuts")
        btn_clr.clicked.connect(self._clear_cuts)
        thl.addWidget(btn_clr); lay.addWidget(th)

        self.timeline = TimelineWidget()
        self.timeline.cut_points_changed.connect(self._on_cuts_changed)
        self.timeline.segment_selected.connect(self._on_seg_from_timeline)
        self.timeline.cursor_moved.connect(self._on_cursor_moved)
        lay.addWidget(self.timeline)

        img_grp = QGroupBox("🖼  Image Preview  (全量预载 · 实时显示 · 时间戳对齐)")
        img_l   = QVBoxLayout(img_grp); img_l.setContentsMargins(4, 8, 4, 4)
        self.img_preview = MultiStreamPreviewWidget()
        img_l.addWidget(self.img_preview); lay.addWidget(img_grp)

        tbh = QWidget(); tbhl = QHBoxLayout(tbh); tbhl.setContentsMargins(0, 0, 0, 0)
        tbhl.addWidget(QLabel("📋  Segments  —  <span style='color:#a6adc8'>"
                               "double-click Prompt to edit</span>"))
        lay.addWidget(tbh)

        self.seg_table = SegmentTable()
        self.seg_table.prompt_changed.connect(self._on_table_prompt_changed)
        self.seg_table.row_selected.connect(self._on_seg_from_table)
        self.seg_table.segment_delete_requested.connect(self._on_delete_segment)
        self.seg_table.out_dir_changed.connect(self._on_seg_out_dir_changed)
        lay.addWidget(self.seg_table)

        pgrp = QGroupBox("✏️  Prompt Editor  (Ctrl+Enter to apply)")
        pl   = QVBoxLayout(pgrp); pl.setContentsMargins(4, 8, 4, 4)
        self.prompt_panel = PromptPanel()
        self.prompt_panel.prompt_committed.connect(self._on_prompt_committed)
        pl.addWidget(self.prompt_panel); lay.addWidget(pgrp)

        bar = QWidget(); bl = QHBoxLayout(bar); bl.setContentsMargins(0, 0, 0, 0)
        bs  = QPushButton("💾  Save JSON"); bl2 = QPushButton("📂  Load JSON")
        self.btn_export = QPushButton("🚀  Export Current Bag")
        self.btn_export.setObjectName("export_btn")
        bs.clicked.connect(self._save_json); bl2.clicked.connect(self._load_json)
        self.btn_export.clicked.connect(self._export_current)
        bl.addWidget(bs); bl.addWidget(bl2); bl.addStretch(); bl.addWidget(self.btn_export)
        lay.addWidget(bar)
        return w

    # ── bag management ─────────────────────────────────────────────────────────

    def _add_bags(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select RosBag directory", self._last_bag_dir)
        if not d: return
        self._last_bag_dir = str(Path(d).parent)
        p = Path(d)
        if not (p / "metadata.yaml").exists():
            if (p.parent / "metadata.yaml").exists(): p = p.parent
            else:
                qmsg(self, "warn", "Not a RosBag", f"No metadata.yaml:\n{p}"); return
        key = str(p)
        existing = [self.bag_list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.bag_list.count())]
        if key in existing: return
        meta = load_bag_meta(key)
        if not meta:
            qmsg(self, "warn", "Load Error", f"Cannot parse:\n{key}"); return
        self.bag_metas[key] = meta
        if key not in self.annotations:
            self.annotations[key] = BagAnnotation(
                bag_path=key, start_ns=meta.start_time_ns,
                end_ns=meta.end_time_ns, prompts=[""])
        item = QListWidgetItem(meta.name)
        item.setData(Qt.ItemDataRole.UserRole, key); item.setToolTip(key)
        self.bag_list.addItem(item)
        if self.bag_list.count() == 1: self.bag_list.setCurrentRow(0)

    def _remove_bag(self):
        row = self.bag_list.currentRow()
        if row >= 0:
            self.bag_list.takeItem(row)
            if self.bag_list.count() == 0:
                self.current_bag_path = None
                self.timeline.load(0, 0)
                self.seg_table.setRowCount(0)
                self.img_preview.clear()

    def _on_bag_selected(self, row: int):
        if row < 0: return
        item = self.bag_list.item(row)
        if not item: return
        key  = item.data(Qt.ItemDataRole.UserRole)
        meta = self.bag_metas.get(key) or load_bag_meta(key)
        if not meta: return
        self.bag_metas[key] = meta; self.current_bag_path = key
        self.topic_list.clear()
        for t in meta.topics:
            li = QListWidgetItem(f"{t['name']}  [{t['count']}]")
            li.setToolTip(t["type"])
            if _is_image_type(t["type"]):
                li.setForeground(QBrush(QColor(137, 220, 235)))
            self.topic_list.addItem(li)
        self.info_label.setText(
            f"Duration: {meta.duration_str}\nMessages: {meta.message_count:,}\n"
            f"Topics:   {len(meta.topics)}\nImage:    {len(meta.image_topics)} topic(s)")
        ann = self.annotations.get(key)
        self.timeline.load(meta.start_time_ns, meta.end_time_ns,
                           ann.cut_points_ns if ann else [])
        self._refresh_table()
        self.img_preview.set_bag(meta)
        self.sb_label.setText(
            f"Loaded: {meta.name}  —  {meta.duration_str}, "
            f"{len(meta.topics)} topics ({len(meta.image_topics)} image)")

    # ── cursor → preview ───────────────────────────────────────────────────────

    def _on_cursor_moved(self, ns: int):
        self.img_preview.show_at(ns)

    # ── timeline ↔ table ───────────────────────────────────────────────────────

    def _on_delete_segment(self, seg_idx: int):
        if not self.current_bag_path: return
        ann  = self.annotations.get(self.current_bag_path)
        if not ann: return
        cuts = sorted(ann.cut_points_ns)
        if len(cuts) + 1 <= 1:
            qmsg(self, "info", "提示", "只剩一段，无法再删除。"); return
        ann.prompts = self.seg_table.get_prompts(); ann._ensure_prompts()
        if seg_idx < len(cuts):
            ann.cut_points_ns.remove(cuts[seg_idx])
            if seg_idx + 1 < len(ann.prompts): ann.prompts.pop(seg_idx + 1)
        else:
            ann.cut_points_ns.remove(cuts[seg_idx - 1])
            if seg_idx < len(ann.prompts): ann.prompts.pop(seg_idx)
        ann._ensure_prompts()
        self.timeline.set_cut_points(ann.cut_points_ns)
        self._refresh_table()
        new_row = min(seg_idx, self.seg_table.rowCount() - 1)
        if new_row >= 0: self.seg_table.select_row(new_row)

    def _on_cuts_changed(self):
        if not self.current_bag_path: return
        ann = self.annotations.get(self.current_bag_path)
        if ann: ann.cut_points_ns = self.timeline.get_cut_points(); ann._ensure_prompts()
        self._refresh_table()

    def _refresh_table(self):
        ann = self.annotations.get(self.current_bag_path or "")
        if ann: self.seg_table.populate(ann.get_segments())

    def _on_seg_from_timeline(self, idx: int):
        self.seg_table.select_row(idx); self._update_prompt_panel(idx)

    def _on_seg_from_table(self, idx: int):
        self.timeline.select_segment(idx); self._update_prompt_panel(idx)

    def _update_prompt_panel(self, idx: int):
        ann = self.annotations.get(self.current_bag_path or "")
        if ann:
            segs = ann.get_segments()
            if 0 <= idx < len(segs):
                self.prompt_panel.set_history(self.prompt_history)
                self.prompt_panel.set_segment(idx, segs[idx])

    def _on_seg_out_dir_changed(self, row: int, path: str):
        ann = self.annotations.get(self.current_bag_path or "")
        if ann: ann.set_out_dir(row, path)

    def _on_table_prompt_changed(self, row: int, text: str):
        self._commit_prompt(row, text)

    def _on_prompt_committed(self, idx: int, text: str):
        self._commit_prompt(idx, text); self.seg_table.set_prompt_text(idx, text)

    def _commit_prompt(self, idx: int, text: str):
        ann = self.annotations.get(self.current_bag_path or "")
        if ann:
            ann.set_prompt(idx, text)
            if text.strip() and text.strip() not in self.prompt_history:
                self.prompt_history.append(text.strip())

    def _clear_cuts(self):
        if not self.current_bag_path: return
        if (qmsg(self, "question", "Clear Cuts", "Remove ALL cut points?")
                != QMessageBox.StandardButton.Yes): return
        ann = self.annotations.get(self.current_bag_path)
        if ann: ann.cut_points_ns = []; ann.prompts = [""]
        self.timeline.set_cut_points([]); self._refresh_table()

    # ── JSON ───────────────────────────────────────────────────────────────────

    def _sync_from_table(self):
        ann = self.annotations.get(self.current_bag_path or "")
        if ann:
            ann.prompts  = self.seg_table.get_prompts()
            ann.out_dirs = self.seg_table.get_out_dirs()

    def _save_json(self):
        self._sync_from_table()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Annotation", "", "JSON Files (*.json)")
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "prompt_history": self.prompt_history,
                       "annotations": {k: v.to_dict()
                                        for k, v in self.annotations.items()}},
                      f, indent=2, ensure_ascii=False)
        self.sb_label.setText(f"✓ Saved: {path}")

    def _load_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Annotation", "", "JSON Files (*.json)")
        if not path: return
        with open(path, encoding="utf-8") as f: data = json.load(f)
        self.prompt_history = data.get("prompt_history", [])
        for k, ad in data.get("annotations", {}).items():
            self.annotations[k] = BagAnnotation(
                bag_path=ad["bag_path"], start_ns=ad["start_ns"], end_ns=ad["end_ns"],
                cut_points_ns=ad.get("cut_points_ns", []),
                prompts=ad.get("prompts", []),
                out_dirs=ad.get("out_dirs", []))
        self._on_bag_selected(self.bag_list.currentRow())
        self.sb_label.setText(f"✓ Loaded: {path}")

    # ── export ─────────────────────────────────────────────────────────────────

    def _export_all(self):
        self._sync_from_table()
        n          = len(self.annotations)
        total_segs = sum(len(a.get_segments()) for a in self.annotations.values())
        if (qmsg(self, "question", "导出全部 Bag",
                 f"将导出 {n} 个 bag，共 {total_segs} 段。\n\n确认导出全部？")
                != QMessageBox.StandardButton.Yes): return
        self._do_export(list(self.annotations.values()))

    def _export_current(self):
        self._sync_from_table()
        if not self.current_bag_path:
            qmsg(self, "info", "No Bag", "Load a bag first."); return
        ann = self.annotations.get(self.current_bag_path)
        if ann: self._do_export([ann])

    def _do_export(self, anns):
        if not anns: return
        self._sync_from_table()
        missing = [f"  {Path(a.bag_path).name}  Seg {i+1}"
                   for a in anns
                   for i, s in enumerate(a.get_segments()) if not s.out_dir]
        if missing:
            qmsg(self, "warn", "未设置输出目录",
                 "以下分段尚未指定输出目录：\n\n"
                 + "\n".join(missing[:15]) + ("..." if len(missing) > 15 else ""))
            return
        empty = [f"  {Path(a.bag_path).name} Seg{i+1}"
                 for a in anns
                 for i, s in enumerate(a.get_segments()) if not s.prompt.strip()]
        if empty:
            msg = "以下分段 Prompt 为空：\n" + "\n".join(empty[:10])
            if (qmsg(self, "question", "Empty Prompts", msg + "\n\n仍然导出？")
                    != QMessageBox.StandardButton.Yes): return
        total = sum(len(a.get_segments()) for a in anns)
        self.pbar.setMaximum(total); self.pbar.setValue(0); self.pbar.setVisible(True)
        self.btn_export.setEnabled(False)
        self._export_worker = ExportWorker(anns, self)
        self._export_worker.progress.connect(
            lambda m, c, t: (self.sb_label.setText(m),
                              self.pbar.setMaximum(t), self.pbar.setValue(c)))
        self._export_worker.finished.connect(self._on_done)
        self._export_worker.start()

    def _on_done(self, ok: bool, msg: str):
        self.pbar.setVisible(False); self.btn_export.setEnabled(True)
        if ok:
            self.sb_label.setText(f"✓ {msg}"); qmsg(self, "info", "Done", msg)
        else:
            self.sb_label.setText("✗ Export failed"); qmsg(self, "error", "Failed", msg)

    def closeEvent(self, ev):
        self.img_preview.clear(); super().closeEvent(ev)
