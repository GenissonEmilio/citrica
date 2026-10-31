"""Appearance persists across upgrades and never changes the wheel interaction."""
import json
import math
import os
import re
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from citrica.appearance import WheelAppearancePicker
from citrica.wheel_themes import DEFAULT_THEME, THEMES, get_theme, normalize_theme, theme_catalogue
from citrica.windows import config, package
from citrica.windows.wheel import CENTER, LABEL_RADIUS, Wheel, hit_test

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_gnome_and_qt_share_the_entire_appearance_contract():
    script = (ROOT / 'gnome/citrica@genissonemilio.github.io/themes.js').read_text()
    data = json.loads(re.search(r'export const THEMES = (\[.*?\]);', script, re.S).group(1))
    assert data == theme_catalogue()
    schema = (ROOT / 'gnome/citrica@genissonemilio.github.io/schemas/'
              'org.gnome.shell.extensions.citrica.gschema.xml').read_text()
    for theme in THEMES:
        assert f'<choice value="{theme.id}"/>' in schema
    assert len({theme.id for theme in THEMES}) >= 5


@pytest.mark.parametrize('stored', [None, [], {}, 15, 'unknown-future-style'])
def test_unknown_appearance_falls_back_without_resetting_shortcuts(tmp_path, monkeypatch, stored):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setattr(package, 'package_family_name', lambda: None)
    folder = config.config_dir()
    folder.mkdir()
    (folder / 'settings.json').write_text(json.dumps({'shortcut': 'Win+F8', 'drag_key': 'Win',
                                                    'animations': False, 'wheel_theme': stored}))
    assert normalize_theme(stored) == DEFAULT_THEME
    assert config.load() == {'shortcut': 'Win+F8', 'drag_key': 'Win',
                             'animations': False, 'wheel_theme': DEFAULT_THEME}


@pytest.mark.parametrize('theme', THEMES, ids=lambda item: item.id)
def test_style_roundtrip_and_invalid_save_preserves_previous_settings(tmp_path, monkeypatch, theme):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setattr(package, 'package_family_name', lambda: None)
    wanted = dict(config.DEFAULTS, wheel_theme=theme.id, shortcut='Win+F8')
    config.save(wanted)
    assert config.load() == wanted
    before = (config.config_dir() / 'settings.json').read_bytes()
    with pytest.raises(ValueError, match='estilos'):
        config.save(dict(wanted, wheel_theme=['not-a-theme']))
    assert (config.config_dir() / 'settings.json').read_bytes() == before


def test_appearance_picker_programmatic_loading_does_not_signal_a_user_edit(app):
    picker = WheelAppearancePicker('watercolor')
    changes = QSignalSpy(picker.themeChanged)
    picker.set_theme('graphite')
    assert changes.count() == 0 and picker.theme_id() == 'graphite'
    assert picker.buttons['graphite'].isChecked()
    QTest.mouseClick(picker.buttons['contrast'], Qt.MouseButton.LeftButton)
    assert changes.count() == 1 and changes.at(0) == ['contrast']
    assert picker.theme_id() == 'contrast'
    assert sum(button.isChecked() for button in picker.buttons.values()) == 1
    picker.deleteLater()


def test_all_styles_keep_selection_geometry_and_transparent_window(app):
    wheel = Wheel(animations=lambda: False)
    items = [{'kind': 'format', 'id': item, 'label': item} for item in ('png', 'jpg', 'webp', 'pdf', 'avif')]
    wheel.set_palette([Path('example.png')], items, {'bytes': 2048, 'label': 'example.png'})
    wheel.select(1)
    geometries = tuple(wheel._geometry)
    alpha = {}
    rendered = set()
    for theme in THEMES:
        wheel.set_theme(theme.id)
        assert wheel.selected == 1 and wheel.items == items and wheel.paths == [Path('example.png')]
        assert tuple(wheel._geometry) == geometries
        for index in range(len(items)):
            angle = -math.pi / 2 + index * math.tau / len(items)
            x, y = CENTER + LABEL_RADIUS * math.cos(angle), CENTER + LABEL_RADIUS * math.sin(angle)
            assert hit_test(x, y, len(items)) == index
            assert wheel._geometry[index].contains(QPointF(x, y))
        snapshot = wheel.grab().toImage()
        assert snapshot.pixelColor(1, 1).alpha() <= 2
        alpha[theme.id] = snapshot.pixelColor(CENTER, CENTER - 152).alpha()
        rendered.add(bytes(snapshot.bits()))
    assert len(rendered) == len(THEMES)
    assert alpha['glass'] < alpha['watercolor'] < alpha['classic']
    assert alpha['contrast'] == 255
    wheel.clear()
    assert wheel.theme.id == 'contrast'
    assert wheel.selected == -1 and wheel.paths == []
    wheel.deleteLater()


def test_text_surfaces_have_readable_contrast():
    def luminance(color):
        rgb = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
               for value in color[:3]]
        return sum(value * weight for value, weight in zip(rgb, (.2126, .7152, .0722)))

    def contrast(a, b):
        values = sorted((luminance(a), luminance(b)))
        return (values[1] + .05) / (values[0] + .05)

    for theme in THEMES:
        assert contrast(theme.pill_text, theme.pill) >= 4.5, theme.id
        if theme.label_chip:
            assert theme.label_chip[3] >= .90
            surfaces = (theme.label_chip,)
        else:
            surfaces = (theme.start, theme.end)
        for surface in surfaces:
            assert contrast(theme.text, surface) >= 4.5, theme.id
        if not theme.label_chip:
            assert contrast(theme.active_text, theme.selected_end) >= 4.5, theme.id
    assert get_theme('contrast').border_width >= 2
