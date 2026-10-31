"""Scaled settings must keep save controls and every theme reachable."""
import json
import os
from pathlib import Path
import subprocess
import sys


DRIVER = r'''
import json
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_windows import FakeNative
from citrica.gui import STYLE
from citrica.windows.app import Desktop, Settings

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
desktop = Desktop(app, FakeNative, listen=False)
window = Settings(desktop)
desktop.keep_window(window)
app.processEvents()
available = window.screen().availableGeometry()
assert available.contains(window.frameGeometry()), (available, window.frameGeometry())
window.tabs.setCurrentIndex(1)
app.processEvents()
scroll = window.tabs.currentWidget()
assert isinstance(scroll, QScrollArea)
selected = []
for theme, button in window.appearance.buttons.items():
    scroll.ensureWidgetVisible(button)
    app.processEvents()
    position = button.mapTo(scroll.viewport(), QPoint(0, 0))
    assert scroll.viewport().rect().contains(QRect(position, button.size()))
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert window.appearance.theme_id() == theme
    selected.append(theme)
for name in ['SavePreferences', 'SaveAndTestWheel']:
    button = window.findChild(QPushButton, name)
    rect = QRect(button.mapToGlobal(QPoint(0, 0)), button.size())
    assert available.contains(rect), (name, available, rect)
result = {'screen': available.getRect(), 'window': window.frameGeometry().getRect(),
          'all_styles_reachable': selected, 'save_controls_on_screen': True}
desktop.prepare_shutdown()
desktop.native.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
print(json.dumps(result))
'''


def test_windows_settings_fit_and_scroll_at_150_percent(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR='1.5',
               APPDATA=str(tmp_path / 'settings'), LOCALAPPDATA=str(tmp_path / 'local'))
    run = subprocess.run([sys.executable, '-c', DRIVER], capture_output=True, text=True,
                         env=env, cwd=Path(__file__).resolve().parents[1], timeout=15)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)
    assert len(result['all_styles_reachable']) == 5
    assert result['save_controls_on_screen']
    assert 'shared QObject was deleted directly' not in run.stderr
