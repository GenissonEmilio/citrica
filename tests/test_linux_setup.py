import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from citrica import desktop


@pytest.mark.parametrize('version,session,supported', [
    ('46.0', 'wayland', True), ('50.5', 'wayland', True), ('51.0', 'wayland', True),
    ('42.9', 'wayland', False), ('46.0', 'x11', False),
])
def test_gnome_environment_checks_real_version_and_session(monkeypatch, version, session, supported):
    monkeypatch.setenv('XDG_SESSION_TYPE', session)
    result = subprocess.CompletedProcess([], 0, f'GNOME Shell {version}\n', '')
    with patch('citrica.desktop.subprocess.run', return_value=result):
        assert desktop.gnome_environment()['supported'] is supported


def test_first_menu_launch_is_idempotent_and_retries_missing_extension(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'extension.js').write_text('test extension')
    destination = tmp_path / 'installed'
    environment = {'shell': 46, 'wayland': True, 'supported': True}
    def install_extension():
        destination.mkdir(exist_ok=True)
    with patch('citrica.desktop.gnome_environment', return_value=environment), \
         patch('citrica.desktop.extension_source', return_value=source), \
         patch('citrica.desktop.extension_dir', return_value=destination), \
         patch('citrica.integration.install') as integrate, \
         patch('citrica.desktop.install_gnome', side_effect=install_extension) as install:
        desktop.setup_desktop()
        desktop.setup_desktop()
        assert install.call_count == integrate.call_count == 1
        destination.rmdir()
        desktop.setup_desktop()
        assert install.call_count == 2
        (source / 'extension.js').write_text('updated extension')
        desktop.setup_desktop()
        assert install.call_count == 3
    marker = json.loads((tmp_path / 'config/citrica/setup.json').read_text())
    assert marker['environment']['shell'] == 46


def test_unsupported_desktop_never_enables_incompatible_extension(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    environment = {'shell': 42, 'wayland': True, 'supported': False}
    with patch('citrica.desktop.gnome_environment', return_value=environment), \
         patch('citrica.desktop.extension_source', return_value=Path('/nonexistent-extension')), \
         patch('citrica.integration.install') as integrate, \
         patch('citrica.desktop.install_gnome') as install:
        desktop.setup_desktop()
        assert integrate.call_count == 1
        install.assert_not_called()
    with patch('citrica.desktop.gnome_environment', return_value=environment):
        with pytest.raises(RuntimeError, match='GNOME atual: 42'):
            desktop.install_gnome()
