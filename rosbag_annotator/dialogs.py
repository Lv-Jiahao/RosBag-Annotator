"""
Reusable dialog helpers: qmsg, qinput_text, qinput_item, qpick_dirs
"""
from __future__ import annotations
from pathlib import Path
from typing import List

from PyQt6.QtCore    import Qt, QDir
from PyQt6.QtGui     import QFileSystemModel
from PyQt6.QtWidgets import (
    QMessageBox, QDialog, QDialogButtonBox,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QTreeView,
    QPushButton, QSplitter, QAbstractItemView,
    QWidget,
)


def qmsg(parent, kind: str, title: str, text: str, buttons=None):
    icons = {
        'info':     QMessageBox.Icon.Information,
        'warn':     QMessageBox.Icon.Warning,
        'error':    QMessageBox.Icon.Critical,
        'question': QMessageBox.Icon.Question,
    }
    btns = buttons or (
        (QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if kind == 'question' else QMessageBox.StandardButton.Ok)
    box = QMessageBox(parent)
    box.setWindowTitle(title); box.setText(text)
    box.setIcon(icons.get(kind, QMessageBox.Icon.NoIcon))
    box.setStandardButtons(btns)
    return box.exec()


def qinput_text(parent, title: str, label: str, default: str = ""):
    """Large centered text-input dialog. Returns (text, ok)."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(580)

    lay = QVBoxLayout(dlg)
    lay.setSpacing(8); lay.setContentsMargins(16, 16, 16, 12)

    lbl = QLabel(label)
    lbl.setStyleSheet("color:#cdd6f4; font-size:12px;")
    lay.addWidget(lbl)

    edit = QLineEdit(default)
    edit.setStyleSheet(
        "background:#181825; color:#cdd6f4; border:1px solid #45475a;"
        " border-radius:4px; font-size:13px; padding:6px;")
    edit.setMinimumHeight(36)
    lay.addWidget(edit)

    btns = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)

    dlg.adjustSize()
    _center_on_top(dlg, parent)
    edit.selectAll(); edit.setFocus()
    ok = dlg.exec() == QDialog.DialogCode.Accepted
    return edit.text(), ok


def qinput_item(parent, title: str, label: str, items, editable: bool = False):
    """Large centered list-selection dialog. Returns (text, ok)."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(560, 420)

    lay = QVBoxLayout(dlg)
    lay.setSpacing(10); lay.setContentsMargins(16, 16, 16, 16)

    lbl = QLabel(label)
    lbl.setStyleSheet("font-size:13px; color:#cdd6f4;")
    lay.addWidget(lbl)

    lst = QListWidget()
    lst.addItems(items)
    lst.setStyleSheet(
        "QListWidget{background:#181825;border:1px solid #45475a;"
        "border-radius:6px;font-size:13px;color:#cdd6f4;padding:4px;}"
        "QListWidget::item{padding:6px 10px;border-radius:4px;}"
        "QListWidget::item:selected{background:#45475a;color:#cdd6f4;}"
        "QListWidget::item:hover{background:#313244;}")
    if items: lst.setCurrentRow(0)
    lay.addWidget(lst, stretch=1)

    btn_box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    btn_box.setStyleSheet(
        "QPushButton{background:#313244;color:#cdd6f4;border:1px solid #45475a;"
        "border-radius:6px;padding:8px 28px;font-size:13px;font-weight:bold;min-width:90px;}"
        "QPushButton:hover{background:#45475a;}"
        "QPushButton:pressed{background:#585b70;}")
    btn_box.accepted.connect(dlg.accept)
    btn_box.rejected.connect(dlg.reject)
    lay.addWidget(btn_box)

    lst.itemDoubleClicked.connect(lambda _: dlg.accept())
    _center_on_top(dlg, parent)

    ok   = dlg.exec() == QDialog.DialogCode.Accepted
    text = lst.currentItem().text() if ok and lst.currentItem() else ""
    return text, ok


# ── Multi-directory picker ─────────────────────────────────────────────────────

_LIST_STYLE = (
    "QListWidget{background:#181825;border:1px solid #45475a;"
    "border-radius:4px;color:#cdd6f4;font-size:12px;padding:2px;}"
    "QListWidget::item{padding:5px 10px;border-radius:3px;}"
    "QListWidget::item:selected{background:#45475a;color:#cdd6f4;}"
    "QListWidget::item:hover{background:#313244;}"
)
_BTN_STYLE = (
    "QPushButton{background:#313244;color:#cdd6f4;border:1px solid #45475a;"
    "border-radius:4px;padding:5px 14px;font-size:12px;}"
    "QPushButton:hover{background:#45475a;}"
    "QPushButton:pressed{background:#585b70;}"
)


class _MultiDirDialog(QDialog):
    """
    Two-panel batch directory picker.

    Left : navigate to a parent folder (tree, single-select).
           Clicking a folder lists its immediate subdirs on the right browser.
    Middle: flat QListWidget of subdirs — ExtendedSelection so the user can
            Ctrl+click individual items or Shift+click a range, then press
            '＋ 添加选中' to stage them all at once.
    Right : staged list ready for import, with Remove / Clear.
    """

    def __init__(self, parent, start_dir: str = ""):
        super().__init__(parent)
        self.setWindowTitle("批量导入 Bag 文件夹")
        self.resize(1060, 600)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)

        # ── hint ──────────────────────────────────────────────────────────────
        hint = QLabel(
            "① 左侧点击父目录  →  中间列出所有子文件夹  "
            "② <b>Ctrl/Shift 多选</b> 或全选  "
            "③ 点 <b>＋ 添加选中</b>  →  右侧确认后 OK 导入")
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setStyleSheet("color:#a6adc8;font-size:11px;")
        lay.addWidget(hint)

        spl = QSplitter(Qt.Orientation.Horizontal)

        # ── LEFT: directory tree (navigate only) ──────────────────────────────
        left_w = QWidget()
        ll = QVBoxLayout(left_w); ll.setContentsMargins(0,0,0,0); ll.setSpacing(4)
        ll.addWidget(self._lbl("目录导航"))

        self._fs = QFileSystemModel()
        self._fs.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        root = start_dir if start_dir and Path(start_dir).is_dir() else str(Path.home())
        self._fs.setRootPath(root)

        self._tree = QTreeView()
        self._tree.setModel(self._fs)
        self._tree.setRootIndex(self._fs.index(root))
        for col in (1, 2, 3):
            self._tree.hideColumn(col)
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet(
            "QTreeView{background:#181825;border:1px solid #45475a;"
            "border-radius:4px;color:#cdd6f4;font-size:12px;}"
            "QTreeView::item:selected{background:#45475a;}"
            "QTreeView::item:hover{background:#313244;}")
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setAnimated(False)
        self._tree.clicked.connect(self._on_tree_click)
        ll.addWidget(self._tree, stretch=1)
        spl.addWidget(left_w)

        # ── MIDDLE: flat subdir browser (multi-select) ────────────────────────
        mid_w = QWidget()
        ml = QVBoxLayout(mid_w); ml.setContentsMargins(4,0,4,0); ml.setSpacing(4)

        self._cur_lbl = self._lbl("子文件夹  （点击左侧目录后显示）")
        ml.addWidget(self._cur_lbl)

        self._browser = QListWidget()
        self._browser.setStyleSheet(_LIST_STYLE)
        self._browser.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._browser.setToolTip(
            "单击选中  |  Ctrl+单击 追加/取消  |  Shift+单击 选区间\n"
            "Ctrl+A 全选  →  点 ＋ 添加选中")
        ml.addWidget(self._browser, stretch=1)

        mid_btn_row = QHBoxLayout(); mid_btn_row.setSpacing(6)
        btn_sel_all  = QPushButton("全选")
        btn_add_sel  = QPushButton("＋ 添加选中  →")
        btn_sel_all.setStyleSheet(_BTN_STYLE)
        btn_add_sel.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#89b4fa;font-weight:bold;"
            "border:1px solid #2563a8;border-radius:4px;padding:5px 14px;font-size:12px;}"
            "QPushButton:hover{background:#1e4d78;}"
            "QPushButton:pressed{background:#2563a8;}")
        btn_sel_all.clicked.connect(self._browser.selectAll)
        btn_add_sel.clicked.connect(self._add_selected)
        mid_btn_row.addWidget(btn_sel_all)
        mid_btn_row.addWidget(btn_add_sel, stretch=1)
        ml.addLayout(mid_btn_row)
        spl.addWidget(mid_w)

        # ── RIGHT: staged list ────────────────────────────────────────────────
        right_w = QWidget()
        rl = QVBoxLayout(right_w); rl.setContentsMargins(4,0,0,0); rl.setSpacing(4)
        self._count_lbl = self._lbl("待导入列表  （已选 0 个）")
        rl.addWidget(self._count_lbl)

        self._staged = QListWidget()
        self._staged.setStyleSheet(_LIST_STYLE)
        self._staged.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        rl.addWidget(self._staged, stretch=1)

        r_btn_row = QHBoxLayout(); r_btn_row.setSpacing(6)
        btn_rem = QPushButton("✕ 移除选中")
        btn_clr = QPushButton("清空")
        btn_rem.setStyleSheet(_BTN_STYLE)
        btn_clr.setStyleSheet(_BTN_STYLE)
        btn_rem.clicked.connect(self._remove)
        btn_clr.clicked.connect(lambda: (self._staged.clear(), self._upd()))
        r_btn_row.addWidget(btn_rem); r_btn_row.addWidget(btn_clr)
        rl.addLayout(r_btn_row)
        spl.addWidget(right_w)

        spl.setSizes([280, 440, 320])
        lay.addWidget(spl, stretch=1)

        # ── OK / Cancel ───────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.setStyleSheet(_BTN_STYLE)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # pre-populate browser if start_dir has subdirs
        if start_dir and Path(start_dir).is_dir():
            self._populate_browser(start_dir)

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _lbl(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("color:#a6adc8;font-size:11px;")
        return l

    def _on_tree_click(self, idx):
        path = self._fs.filePath(idx)
        if path:
            self._populate_browser(path)

    def _populate_browser(self, parent_path: str):
        self._browser.clear()
        p = Path(parent_path)
        subdirs = sorted([d for d in p.iterdir() if d.is_dir()],
                         key=lambda d: d.name.lower())
        for d in subdirs:
            item = QListWidgetItem(d.name)
            item.setToolTip(str(d))
            self._browser.addItem(item)
        short = p.name or str(p)
        self._cur_lbl.setText(
            f"子文件夹  —  {short}  （{len(subdirs)} 个）")

    def _add_selected(self):
        existing = {self._staged.item(i).toolTip()
                    for i in range(self._staged.count())}
        added = 0
        for item in self._browser.selectedItems():
            path = item.toolTip()
            if path and path not in existing:
                ni = QListWidgetItem(Path(path).name)
                ni.setToolTip(path)
                self._staged.addItem(ni)
                existing.add(path)
                added += 1
        self._upd()
        # deselect browser after adding
        self._browser.clearSelection()

    def _remove(self):
        for item in self._staged.selectedItems():
            self._staged.takeItem(self._staged.row(item))
        self._upd()

    def _upd(self):
        n = self._staged.count()
        self._count_lbl.setText(f"待导入列表  （已选 {n} 个）")

    def get_dirs(self) -> List[str]:
        return [self._staged.item(i).toolTip()
                for i in range(self._staged.count())]


def qpick_dirs(parent, start_dir: str = "") -> List[str]:
    """Open the multi-directory picker. Returns list of selected paths."""
    dlg = _MultiDirDialog(parent, start_dir)
    _center_on_top(dlg, parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.get_dirs()
    return []


def _center_on_top(dlg: QDialog, parent):
    """Center dialog over the topmost visible ancestor."""
    top = parent
    while top is not None and top.parent() is not None:
        top = top.parent()
    if top and top.isVisible():
        pg = top.geometry()
        dlg.move(pg.x() + (pg.width()  - dlg.width())  // 2,
                 pg.y() + (pg.height() - dlg.height()) // 2)
