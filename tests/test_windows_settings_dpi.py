"""Scaled settings must keep save controls and every theme reachable."""
import json
import os
from pathlib import Path
import subprocess
import sys


DRIVER = r'''
import json
import os
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QFontInfo
from PySide6.QtWidgets import QApplication, QFormLayout, QPushButton, QScrollArea, QStyle, QWidget
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_windows import FakeNative
from citrica.gui import STYLE
from citrica.windows.app import Desktop, Settings

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
# The generic Windows offscreen backend has no system font database: it sizes
# every missing glyph as a square. Use the native Windows renderer below so
# this check measures the same fonts, decorations and DPI as the application.
assert QFontDatabase.families(), 'The DPI test requires a working font renderer'
if sys.platform == 'win32':
    assert 'Segoe UI' in QFontDatabase.families()
desktop = Desktop(app, FakeNative, listen=False)
window = Settings(desktop)
desktop.keep_window(window)
app.processEvents()
available = window.screen().availableGeometry()

def geometry_diagnostics():
    def size(value):
        return [value.width(), value.height()]
    def layout_details(layout):
        result = {'type': type(layout).__name__, 'minimum': size(layout.minimumSize()),
            'hint': size(layout.sizeHint()), 'constraint': layout.sizeConstraint().name,
            'margins': list(layout.getContentsMargins()), 'spacing': layout.spacing(), 'items': []}
        if isinstance(layout, QFormLayout):
            result.update(row_wrap=layout.rowWrapPolicy().name,
                          field_growth=layout.fieldGrowthPolicy().name,
                          horizontal_spacing=layout.horizontalSpacing())
        for index in range(layout.count()):
            child = layout.itemAt(index)
            nested = child.layout()
            widget = child.widget()
            item = {'minimum': size(child.minimumSize()), 'hint': size(child.sizeHint()),
                    'geometry': child.geometry().getRect()}
            if nested:
                item['layout'] = layout_details(nested)
            if widget:
                item.update(widget=type(widget).__name__, name=widget.objectName())
                if callable(getattr(widget, 'text', None)):
                    item['text'] = widget.text()
            result['items'].append(item)
        return result
    widgets = [window, *window.findChildren(QWidget)]
    measured = []
    for widget in widgets:
        font = widget.font()
        info = QFontInfo(font)
        metrics = widget.fontMetrics()
        text = widget.text() if callable(getattr(widget, 'text', None)) else ''
        item = {'type': type(widget).__name__, 'name': widget.objectName(),
            'text': text, 'size': size(widget.size()), 'minimum': size(widget.minimumSize()),
            'minimum_hint': size(widget.minimumSizeHint()), 'hint': size(widget.sizeHint()),
            'maximum': size(widget.maximumSize()), 'geometry': widget.geometry().getRect(),
            'visible': widget.isVisible(), 'font': font.toString(),
            'resolved_family': info.family(), 'resolved_pixel_size': info.pixelSize(),
            'resolved_point_size': info.pointSizeF(),
            'font_metrics': {'height': metrics.height(), 'average_width': metrics.averageCharWidth(),
                             'text_width': metrics.horizontalAdvance(text)}}
        if callable(getattr(widget, 'wordWrap', None)):
            item['word_wrap'] = widget.wordWrap()
        layout = widget.layout()
        if layout:
            item['layout'] = layout_details(layout)
        measured.append(item)
    screen = window.screen()
    return {'available': available.getRect(), 'frame': window.frameGeometry().getRect(),
        'device_pixel_ratio': screen.devicePixelRatio(), 'logical_dpi': screen.logicalDotsPerInch(),
        'physical_dpi': screen.physicalDotsPerInch(), 'application_font': app.font().toString(),
        'font_database_count': len(QFontDatabase.families()),
        'segoe_ui_available': 'Segoe UI' in QFontDatabase.families(),
        'style': app.style().metaObject().className(),
        'style_metrics': {name: app.style().pixelMetric(getattr(QStyle.PixelMetric, name))
                          for name in ['PM_IndicatorWidth', 'PM_CheckBoxLabelSpacing',
                                       'PM_LayoutHorizontalSpacing']},
        'qt_environment': {key: value for key, value in os.environ.items()
                           if key.startswith('QT_') and any(part in key for part in
                               ['DPI', 'SCALE', 'FONT', 'PLATFORM'])},
        'widgets': measured}

assert available.contains(window.frameGeometry()), json.dumps(geometry_diagnostics(), ensure_ascii=False)
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
          'all_styles_reachable': selected, 'save_controls_on_screen': True,
          'platform': app.platformName(), 'font': QFontInfo(window.font()).family()}
assert result['font'], 'The settings font did not resolve'
desktop.prepare_shutdown()
desktop.native.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
print(json.dumps(result))
'''


def test_windows_settings_fit_and_scroll_at_150_percent(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM='windows' if sys.platform == 'win32' else 'offscreen',
               QT_SCALE_FACTOR='1.5',
               APPDATA=str(tmp_path / 'settings'), LOCALAPPDATA=str(tmp_path / 'local'))
    run = subprocess.run([sys.executable, '-c', DRIVER], capture_output=True, text=True,
                         env=env, cwd=Path(__file__).resolve().parents[1], timeout=15)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)
    assert len(result['all_styles_reachable']) == 5
    assert result['save_controls_on_screen']
    assert 'shared QObject was deleted directly' not in run.stderr
