"""A real Wayland drag source for compositor tests, using Qt's OS drag protocol."""
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDrag, QPixmap
from PySide6.QtWidgets import QApplication, QLabel


class Source(QLabel):
    def mousePressEvent(self, event):
        print('press', event.position(), event.buttons(), flush=True)
        self.origin = event.position().toPoint()

    def mouseMoveEvent(self, event):
        print('motion', event.position(), event.buttons(), flush=True)
        if event.buttons() & Qt.MouseButton.LeftButton and (event.position().toPoint() - self.origin).manhattanLength() > 10:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(Path(sys.argv[1]).resolve()))])
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.setPixmap(QPixmap(str(Path(sys.argv[1]).resolve())).scaled(
                72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            drag.setHotSpot(QPoint(8, 8))
            drag.exec(Qt.DropAction.CopyAction)
            print('drag-ended', flush=True)


app = QApplication([])
window = Source('Arquivo de teste\n\nArraste e pressione Shift')
window.setWindowTitle('Citrica · arquivo de teste')
window.setStyleSheet('background:#f2eee6;color:#333;padding:30px;font-size:22px;')
window.resize(390, 240)
window.show()
app.exec()
