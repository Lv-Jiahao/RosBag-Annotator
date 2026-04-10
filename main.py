#!/usr/bin/env python3
"""Entry point — python -m rosbag_annotator  or  rosbag-annotator"""
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui     import QPalette, QColor
from rosbag_annotator.main_window import MainWindow, STYLE


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RosBag Annotator")
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor(30,  30,  46))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor(205, 214, 244))
    pal.setColor(QPalette.ColorRole.Base,            QColor(24,  24,  37))
    pal.setColor(QPalette.ColorRole.AlternateBase,   QColor(30,  30,  46))
    pal.setColor(QPalette.ColorRole.Text,            QColor(205, 214, 244))
    pal.setColor(QPalette.ColorRole.Button,          QColor(49,  50,  68))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor(205, 214, 244))
    pal.setColor(QPalette.ColorRole.Highlight,       QColor(69,  71,  90))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(205, 214, 244))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
