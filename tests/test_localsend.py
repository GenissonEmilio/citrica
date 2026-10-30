"""LocalSend availability and safe argv construction across Linux installs."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from citrica import runtime


@pytest.fixture
def linux_install(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / '.local/share'))
    monkeypatch.setenv('XDG_DATA_DIRS', str(tmp_path / 'system/share'))
    monkeypatch.setattr(runtime.shutil, 'which', lambda name: None)
    return tmp_path


def executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'locator fixture; never run')
    path.chmod(0o755)
    return path


@pytest.mark.parametrize('name', ['localsend', 'localsend_app'])
def test_native_aliases_keep_unicode_files_as_individual_arguments(linux_install, monkeypatch, name):
    binary = executable(linux_install / 'Aplicativos João' / name)
    source = linux_install / 'Fotos ç' / 'foto $(não executar).png'
    monkeypatch.setattr(runtime.shutil, 'which', lambda candidate: str(binary) if candidate == name else None)
    monkeypatch.setattr(runtime, 'run_external', lambda *a, **kw: pytest.fail('native install needs no probe'))
    assert runtime.localsend_command([source]) == [str(binary), str(source)]


@pytest.mark.parametrize('installation', ['--user', '--system'])
def test_flatpak_forwards_paths_and_selects_installed_scope(linux_install, monkeypatch, installation):
    calls = []
    monkeypatch.setattr(runtime.shutil, 'which', lambda name: '/usr/bin/flatpak' if name == 'flatpak' else None)

    def info(args, **kwargs):
        calls.append(args)
        assert kwargs['timeout'] == 2
        assert args[:2] == ['/usr/bin/flatpak', 'info']
        assert args[-2:] == ['--show-ref', 'org.localsend.localsend_app']
        success = args[2] == installation
        return SimpleNamespace(returncode=0 if success else 1,
                               stdout='app/org.localsend.localsend_app/x86_64/stable\n' if success else '')

    monkeypatch.setattr(runtime, 'run_external', info)
    sources = [linux_install / 'João ç' / 'Foto 01.png', linux_install / '@@']
    command = runtime.localsend_command(sources)
    assert command == ['/usr/bin/flatpak', 'run', installation, '--file-forwarding',
                       'org.localsend.localsend_app', '@@', *map(str, sources), '@@']
    assert [args[2] for args in calls] == (['--user'] if installation == '--user' else ['--user', '--system'])
    assert runtime.program('localsend') is None  # It must never return a shell command string.


def test_missing_flatpak_app_and_timeout_do_not_offer_share(linux_install, monkeypatch):
    monkeypatch.setattr(runtime.shutil, 'which', lambda name: '/usr/bin/flatpak' if name == 'flatpak' else None)

    def info(args, **kwargs):
        if '--user' in args:
            raise subprocess.TimeoutExpired(args, 2)
        return SimpleNamespace(returncode=1, stdout='')

    monkeypatch.setattr(runtime, 'run_external', info)
    assert runtime.localsend_command() is None


def test_flatpak_uninstalled_is_detected_without_stale_availability(linux_install, monkeypatch):
    monkeypatch.setattr(runtime.shutil, 'which', lambda name: '/usr/bin/flatpak' if name == 'flatpak' else None)
    result = SimpleNamespace(returncode=0, stdout='app/org.localsend.localsend_app/x86_64/stable')
    monkeypatch.setattr(runtime, 'run_external', lambda *a, **kw: result)
    assert runtime.localsend_command()
    result.returncode = 1
    assert runtime.localsend_command() is None


def test_downloaded_appimage_requires_executable_permission(linux_install):
    appimage = executable(linux_install / 'Downloads' / 'LocalSend-1.18.2-linux-x86-64.AppImage')
    source = linux_install / 'Apresentação final.pdf'
    assert runtime.localsend_command([source]) == [str(appimage), str(source)]
    appimage.chmod(0o644)
    assert runtime.localsend_command() is None


def test_appimage_discovery_does_not_recurse_into_user_folders(linux_install):
    executable(linux_install / 'Downloads' / 'backup' / 'LocalSend.AppImage')
    assert runtime.localsend_command() is None


def test_desktop_entry_supports_custom_appimage_path_with_spaces(linux_install):
    appimage = executable(linux_install / 'Meus apps ç' / 'LocalSend.AppImage')
    desktop = linux_install / '.local/share/applications/appimagekit-localsend.desktop'
    desktop.parent.mkdir(parents=True)
    desktop.write_text(f'[Desktop Entry]\nType=Application\nName=LocalSend\nExec="{appimage}" %F\n',
                       encoding='utf-8')
    assert runtime.localsend_command() == [str(appimage)]


@pytest.mark.parametrize('exec_line', ['sh -c "localsend %F"', '/bin/sh -c "localsend %F"',
                                     'env APP=localsend localsend %F', 'localsend %F ; touch /tmp/unsafe'])
def test_desktop_wrappers_and_shell_syntax_are_not_executed(linux_install, exec_line):
    desktop = linux_install / '.local/share/applications/localsend.desktop'
    desktop.parent.mkdir(parents=True)
    desktop.write_text(f'[Desktop Entry]\nType=Application\nExec={exec_line}\n', encoding='utf-8')
    assert runtime.localsend_command() is None


def test_windows_preserves_existing_program_detection_and_argv(monkeypatch):
    monkeypatch.setattr(runtime, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(runtime, 'program', lambda name: 'C:\\Program Files\\LocalSend\\localsend_app.exe')
    source = 'C:\\Users\\João ç\\Foto 01.png'
    assert runtime.localsend_command([source]) == ['C:\\Program Files\\LocalSend\\localsend_app.exe', source]


@pytest.mark.parametrize('installed', [False, True])
def test_actions_palette_uses_launchable_share_capability(monkeypatch, installed):
    from citrica import tools
    monkeypatch.setattr(tools, 'localsend_command', lambda: ['flatpak', 'run', 'app'] if installed else None)
    items = tools.available_tools([Path('documento.docx')], actions=True)
    assert ('share' in {item['id'] for item in items}) is installed
    assert {'copy', 'copy_path', 'move', 'terminal', 'float'}.issubset({item['id'] for item in items})


def test_doctor_reports_the_same_share_capability(monkeypatch, capsys):
    from citrica import __main__, core, desktop, vision
    monkeypatch.setattr(__main__.sys, 'argv', ['citrica', '--doctor'])
    if __main__.sys.platform == 'win32':
        from citrica.windows import ipc
        monkeypatch.setattr(ipc, 'send', lambda payload: {})
    monkeypatch.setattr(runtime, 'localsend_command', lambda: ['flatpak', 'run', 'org.localsend.localsend_app'])
    monkeypatch.setattr(core, 'dependencies', lambda: {})
    monkeypatch.setattr(desktop, 'extension_status', lambda: {})
    monkeypatch.setattr(vision, 'text_available', lambda: False)
    assert __main__.main() == 0
    assert json.loads(capsys.readouterr().out)['tools']['share'] is True
