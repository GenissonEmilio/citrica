import os
import subprocess
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from citrica.companion import ImageSelection, ToolDialog, file_action, validate_shortcut
from citrica.desktop import request


def test_shortcut_validation_and_conflict():
    listing = subprocess.CompletedProcess([], 0, '', '')
    with patch('citrica.companion.subprocess.run', return_value=listing):
        assert validate_shortcut('Super+Shift+C') == '<Super><Shift>c'
        for key in ['Shift+C', 'C', 'Super+Super+C', 'Super+UnrecognizedKeyName', 'Super+Alt']:
            with pytest.raises(ValueError):
                validate_shortcut(key)
    listing.stdout = "org.gnome.desktop.wm.keybindings test ['<Shift><Super>c']"
    with patch('citrica.companion.subprocess.run', return_value=listing):
        with pytest.raises(ValueError, match='já é usado'):
            validate_shortcut('Super+Shift+C')


@pytest.mark.parametrize('extension,expected', [('heic', (320, 200)), ('jpg', (200, 320))])
def test_preview_codec_and_exif_orientation(tmp_path, extension, expected):
    app = QApplication.instance() or QApplication([])
    image = Image.new('RGB', (320, 200), 'orange')
    source = tmp_path / ('photo.' + extension)
    exif = image.getexif()
    if extension == 'jpg':
        exif[274] = 6
    image.save(source, exif=exif)
    canvas = ImageSelection(source)
    assert canvas.source_size == expected
    assert not canvas.pixmap_source.isNull()
    canvas.close()
    app.processEvents()


def test_visual_crop_to_saved_output(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'photo.png'
    Image.new('RGB', (320, 200), 'orange').save(source)
    dialog = ToolDialog('crop', [source])
    dialog.show()
    app.processEvents()
    QTest.mousePress(dialog.canvas, Qt.MouseButton.LeftButton, pos=QPoint(30, 30))
    QTest.mouseMove(dialog.canvas, QPoint(160, 100))
    QTest.mouseRelease(dialog.canvas, Qt.MouseButton.LeftButton, pos=QPoint(160, 100))
    rect = list(map(int, dialog.fields['rect'].text().split(',')))
    assert rect[2] > 0 and rect[3] > 0
    QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Apply), Qt.MouseButton.LeftButton)
    for _ in range(150):
        app.processEvents()
        QTest.qWait(20)
        if dialog.worker and dialog.worker.isFinished():
            break
    app.processEvents()
    result = next(tmp_path.glob('photo-crop*.png'))
    assert Image.open(result).size == tuple(rect[2:])
    dialog.close()


def test_desktop_protocol_uses_real_engine(tmp_path):
    source = tmp_path / 'file.png'
    Image.new('RGB', (20, 20), 'red').save(source)
    capabilities = request({'op': 'capabilities', 'paths': [str(source)], 'mode': 'convert'})
    assert any(x['id'] == 'jpg' for x in capabilities['items'])
    result = request({'op': 'convert', 'paths': [str(source)], 'format': 'jpg'})
    assert not result['errors']
    assert Path(result['outputs'][0]).is_file()


def test_move_action_preserves_existing_destination(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'file.txt'
    source.write_text('moving data')
    target = tmp_path / 'destination'
    target.mkdir()
    existing = target / source.name
    existing.write_text('existing data')
    with patch('citrica.companion.QFileDialog.getExistingDirectory', return_value=str(target)):
        file_action('move', [source])
    assert not source.exists()
    assert existing.read_text() == 'existing data'
    assert any(p.read_text() == 'moving data' for p in target.iterdir())
    app.processEvents()


def test_escape_during_tool_work_requests_cancel_without_destroying_thread(tmp_path):
    import threading
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'photo.png'
    Image.new('RGB', (40, 40), 'orange').save(source)
    entered = threading.Event()
    def controlled_work(_tool, _paths, _params, cancel):
        entered.set()
        cancel.wait(5)
        return {'outputs': []}
    with patch('citrica.companion.execute', side_effect=controlled_work):
        dialog = ToolDialog('compress', [source])
        dialog.show()
        dialog.apply()
        assert entered.wait(2)
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        assert dialog.worker.cancel.is_set()
        assert dialog.isVisible()
        assert dialog.worker.wait(2000)
        app.processEvents()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        assert not dialog.isVisible()
