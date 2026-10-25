import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from citrica.gui import STYLE, MainWindow
from citrica.integration import install


def test_gui_wheel_to_real_output(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    path = tmp_path / "imagem.png"
    Image.new("RGB", (50, 40), "orange").save(path)
    window = MainWindow()
    window.show()
    window.set_files([path])
    assert window.convert_button.isEnabled()
    assert "jpg" in window.wheel.formats
    wheel_button = window.wheel.buttons[window.wheel.formats.index("jpg")]
    QTest.mouseClick(wheel_button, Qt.MouseButton.LeftButton)
    spy = QSignalSpy(window.worker.finished)
    for _ in range(100):
        app.processEvents()
        QTest.qWait(20)
        if spy.count():
            break
    app.processEvents()
    assert (tmp_path / "imagem.jpg").exists()
    assert window.outputs
    assert window.convert_button.isEnabled()
    window.close()


def test_drop_on_radial_format(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "drop.png"
    Image.new("RGB", (20, 20), "blue").save(path)
    window = MainWindow()
    window.show_dock()
    wheel = window.dock.wheel
    app.processEvents()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    enter = QDragEnterEvent(QPoint(150, 150), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(wheel, enter)
    assert enter.isAccepted()
    index = wheel.formats.index("webp")
    position = wheel.buttons[index].geometry().center()
    drop = QDropEvent(QPointF(position), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(wheel, drop)
    for _ in range(100):
        app.processEvents()
        QTest.qWait(20)
        if window.worker and window.worker.isFinished():
            break
    app.processEvents()
    assert (tmp_path / "drop.webp").is_file()
    window.close()


def test_integrations_are_user_scoped(tmp_path):
    paths = install(tmp_path)
    assert len(paths) == 6
    assert all(p.is_relative_to(tmp_path) for p in paths)
    extension = tmp_path / "nautilus-python/extensions/citrica.py"
    compile(extension.read_text(), str(extension), "exec")
    assert "--wheel" in extension.read_text()
