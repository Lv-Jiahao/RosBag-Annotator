"""
Reusable dialog helpers: qmsg, qinput_text, qinput_item
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QMessageBox, QDialog, QDialogButtonBox,
    QVBoxLayout, QLabel, QLineEdit, QListWidget,
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


def _center_on_top(dlg: QDialog, parent):
    """Center dialog over the topmost visible ancestor."""
    top = parent
    while top is not None and top.parent() is not None:
        top = top.parent()
    if top and top.isVisible():
        pg = top.geometry()
        dlg.move(pg.x() + (pg.width()  - dlg.width())  // 2,
                 pg.y() + (pg.height() - dlg.height()) // 2)
