"""The settings tabs persist appearance without losing existing user choices."""
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from citrica.companion import Settings, file_action
from citrica.desktop import SHELL_REVISION, SHELL_VERSION


@pytest.fixture
def linux_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    schema = tmp_path / 'schemas/gschemas.compiled'
    schema.parent.mkdir()
    schema.touch()
    values = {'toggle-wheel': ['<Super>F8'], 'drag-key': 'super',
              'animations': False, 'wheel-theme': 'watercolor'}
    writes = []

    def settings(key, value=None):
        if value is None:
            return values[key]
        writes.append((key, value))
        values[key] = value

    with (patch('citrica.companion.extension_dir', return_value=tmp_path),
          patch('citrica.companion.extension_status', return_value={
              'version': SHELL_VERSION, 'revision': SHELL_REVISION}),
          patch('citrica.companion.gnome_environment', return_value={'supported': True, 'shell': 50}),
          patch('citrica.companion.shell_settings', side_effect=settings),
          patch('citrica.companion.validate_shortcut', return_value='<Super>F8')):
        dialog = Settings()
        yield dialog, values, writes
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_linux_theme_tab_loads_and_saves_without_resetting_shortcut(linux_settings):
    dialog, values, _writes = linux_settings
    assert dialog.tabs.tabText(1) == 'Personalizar a roda'
    assert dialog.appearance.theme_id() == 'watercolor'
    dialog.appearance.set_theme('graphite')
    assert dialog.save()
    assert values == {'toggle-wheel': ['<Super>F8'], 'drag-key': 'super',
                      'animations': False, 'wheel-theme': 'graphite'}


def test_linux_old_schema_does_not_partially_overwrite_preferences(linux_settings):
    dialog, _values, writes = linux_settings
    def old_schema(key, value=None):
        if key == 'wheel-theme':
            raise subprocess.CalledProcessError(1, ['gsettings'])
        writes.append((key, value))
    with (patch('citrica.companion.shell_settings', side_effect=old_schema),
          patch('citrica.companion.QMessageBox.warning') as warning,
          patch('citrica.companion.show_wheel') as show):
        dialog.test()
    assert not writes
    warning.assert_called_once()
    show.assert_not_called()


def test_share_launches_complete_flatpak_argv_with_unicode_file(tmp_path):
    source = tmp_path / 'Documento João ç.docx'
    source.write_bytes(b'fixture')
    command = ['/usr/bin/flatpak', 'run', '--system', '--file-forwarding',
               'org.localsend.localsend_app', '@@', str(source), '@@']
    with (patch('citrica.runtime.localsend_command', return_value=command) as discover,
          patch('citrica.runtime.popen_external') as launch):
        file_action('share', [source])
    discover.assert_called_once_with([Path(source)])
    launch.assert_called_once_with(command)
