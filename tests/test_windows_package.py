"""MSIX identity isolation and preferences must leave the Inno installation intact."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from citrica.windows import config, ipc, package


@pytest.fixture(autouse=True)
def reset_package_caches():
    package.package_family_name.cache_clear()
    package.application_paths.cache_clear()
    yield
    package.package_family_name.cache_clear()
    package.application_paths.cache_clear()


def test_package_detection_is_guarded_on_nonwindows(monkeypatch):
    monkeypatch.setattr(package, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(package.ctypes, 'WinDLL', lambda *a, **kw: pytest.fail('Win32 imported on Linux'), raising=False)
    assert package.package_family_name() is None


@pytest.mark.parametrize('identity', [None, 'GenissonEmilio.Citrica_abcd123456789'])
def test_package_detection_uses_win32_two_call_protocol_and_caches(monkeypatch, identity):
    calls = []

    class Function:
        def __call__(self, count, buffer):
            calls.append(buffer is None)
            if identity is None:
                return package.NO_PACKAGE
            count._obj.value = len(identity) + 1
            if buffer is None:
                return package.INSUFFICIENT_BUFFER
            buffer.value = identity
            return 0
    monkeypatch.setattr(package, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(package.ctypes, 'WinDLL', lambda *a, **kw: SimpleNamespace(GetCurrentPackageFamilyName=Function()),
                        raising=False)
    assert package.package_family_name() == identity
    assert package.package_family_name() == identity
    assert calls == ([True] if identity is None else [True, False])


def test_identity_errors_never_silently_fall_back_to_inno(monkeypatch):
    function = type('Function', (), {'__call__': lambda *args: 5})()
    monkeypatch.setattr(package, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(package.ctypes, 'WinDLL', lambda *a, **kw: SimpleNamespace(GetCurrentPackageFamilyName=function),
                        raising=False)
    with pytest.raises(RuntimeError, match='identidade MSIX'):
        package.package_family_name()


def test_package_helper_requires_identity_and_checks_inherited_family(tmp_path, monkeypatch):
    helper = tmp_path / 'citrica-package.exe'
    helper.write_bytes(b'never actually executed by this test')
    monkeypatch.setattr(package, '_helper_path', lambda: helper)
    monkeypatch.setattr(package, 'package_family_name', lambda: None)
    monkeypatch.setattr(package.subprocess, 'run', lambda *a, **kw: pytest.fail('Helper launched without MSIX identity'))
    with pytest.raises(RuntimeError, match='requer a instalação MSIX'):
        package._request('--paths')
    monkeypatch.setattr(package, 'package_family_name', lambda: 'correct_family')
    monkeypatch.setattr(package.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0,
        stdout=json.dumps({'ok': True, 'package_family': 'wrong_family'})))
    with pytest.raises(RuntimeError, match='não herdou a identidade'):
        package._request('--paths')


def test_helper_calls_are_headless_utf8_bounded_and_preserve_parent_environment(tmp_path, monkeypatch):
    helper = tmp_path / 'citrica-package.exe'
    helper.write_bytes(b'fixture')
    monkeypatch.setattr(package, '_helper_path', lambda: helper)
    monkeypatch.setattr(package, 'package_family_name', lambda: 'family')
    monkeypatch.setattr(package, 'sys', SimpleNamespace(platform='win32'))
    calls = []
    environment = os.environ.copy()

    def run(arguments, **options):
        calls.append((arguments, options))
        return SimpleNamespace(returncode=0, stdout=json.dumps({'ok': True, 'package_family': 'family'}))
    monkeypatch.setattr(package.subprocess, 'run', run)
    package._request('--paths')
    arguments, options = calls[0]
    assert arguments == [str(helper), '--paths']
    assert options['timeout'] == 8 and options['encoding'] == 'utf-8'
    assert options['creationflags'] == 0x08000000 and 'env' not in options
    assert os.environ == environment


@pytest.mark.parametrize('response,code', [('not json', 0), ('[]', 0),
    ('{"ok":false,"error":"Startup task unavailable"}', 1)])
def test_invalid_helper_results_are_explained(tmp_path, monkeypatch, response, code):
    helper = tmp_path / 'citrica-package.exe'
    helper.touch()
    monkeypatch.setattr(package, '_helper_path', lambda: helper)
    monkeypatch.setattr(package, 'package_family_name', lambda: 'family')
    monkeypatch.setattr(package.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=code, stdout=response))
    with pytest.raises(RuntimeError):
        package._request('--paths')


def test_winrt_paths_are_validated_and_cached(tmp_path, monkeypatch):
    calls = []
    values = {key: str(tmp_path / key) for key in ['local_folder', 'local_cache', 'temporary_folder']}

    def request(*arguments):
        calls.append(arguments)
        return values
    monkeypatch.setattr(package, '_request', request)
    assert package.application_paths() == {key: Path(value) for key, value in values.items()}
    assert package.application_paths()['local_cache'] == tmp_path / 'local_cache'
    assert calls == [('--paths',)]
    package.application_paths.cache_clear()
    values['local_folder'] = 'relative/WindowsApps'
    with pytest.raises(RuntimeError, match='pasta de dados válida'):
        package.application_paths()


@pytest.fixture
def msix(tmp_path, monkeypatch):
    legacy, local = tmp_path / 'legacy-roaming', tmp_path / 'package-local-state'
    (legacy / 'Citrica').mkdir(parents=True)
    monkeypatch.setenv('APPDATA', str(legacy))
    monkeypatch.setattr(package, 'package_family_name', lambda: 'Citrica_store_family')
    monkeypatch.setattr(package, 'application_paths', lambda: {'local_folder': local,
        'local_cache': tmp_path / 'package-cache', 'temporary_folder': tmp_path / 'package-temp'})
    return legacy / 'Citrica/settings.json', local / 'Citrica/settings.json'


def test_first_msix_launch_migrates_only_valid_whitelisted_settings_once(msix):
    legacy, target = msix
    legacy.write_text(json.dumps({'shortcut': 'Win+Shift+F8', 'drag_key': 'Win', 'animations': False,
                                  'startup': 'must not migrate registry state'}))
    before = legacy.read_bytes()
    expected = {'shortcut': 'Win+Shift+F8', 'drag_key': 'Win', 'animations': False, 'wheel_theme': 'classic'}
    assert config.load() == expected and json.loads(target.read_text()) == expected
    assert legacy.read_bytes() == before
    legacy.write_text(json.dumps(config.DEFAULTS))
    assert config.load() == expected
    config.save(dict(expected, shortcut='Ctrl+Alt+F9'))
    assert json.loads(target.read_text())['shortcut'] == 'Ctrl+Alt+F9'
    assert json.loads(legacy.read_text()) == config.DEFAULTS


@pytest.mark.parametrize('stored', ['invalid json', '[]', '{"shortcut":"Shift+C"}',
    '{"drag_key":"Ctrl"}', '{"animations":"false"}'])
def test_invalid_legacy_settings_are_never_migrated_and_attempt_is_not_repeated(msix, stored):
    legacy, target = msix
    legacy.write_text(stored)
    assert config.load() == config.DEFAULTS
    assert json.loads(target.read_text()) == config.DEFAULTS
    legacy.write_text('{"shortcut":"Win+F8"}')
    assert config.load() == config.DEFAULTS


def test_msix_never_overwrites_an_existing_config_even_if_corrupt(msix):
    legacy, target = msix
    target.parent.mkdir(parents=True)
    target.write_text('keep corrupt new config for explicit user repair')
    legacy.write_text('{"shortcut":"Win+F8"}')
    assert config.load() == config.DEFAULTS
    assert target.read_text() == 'keep corrupt new config for explicit user repair'


def test_msix_save_rejects_invalid_values_without_creating_settings(msix):
    legacy, target = msix
    with pytest.raises(ValueError):
        config.save(dict(config.DEFAULTS, animations='false'))
    assert not target.exists()


@pytest.mark.parametrize('state,enabled,requested', [('DisabledByUser', False, True),
    ('DisabledByPolicy', False, True), ('EnabledByPolicy', True, False)])
def test_msix_startup_respects_user_policy_without_importing_registry(monkeypatch, state, enabled, requested):
    calls = []
    monkeypatch.setattr(package, 'package_family_name', lambda: 'family')
    monkeypatch.setitem(sys.modules, 'winreg', SimpleNamespace())
    monkeypatch.setattr(package, 'startup_task', lambda action='query': calls.append(action) or
                        {'state': state, 'enabled': enabled, 'blocked': True})
    assert config.startup_enabled() is enabled
    with pytest.raises(RuntimeError):
        config.set_startup(requested)
    config.set_startup(enabled)  # An already matching policy/user setting is not an error.
    assert calls == ['query', 'enable' if requested else 'disable', 'enable' if enabled else 'disable']


def test_inno_preferences_path_and_startup_registry_behavior_are_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setattr(package, 'package_family_name', lambda: None)
    monkeypatch.setattr(package, 'startup_task', lambda *a: pytest.fail('MSIX helper used by Inno'))
    monkeypatch.setattr(package, 'application_paths', lambda: pytest.fail('WinRT folders used by Inno'))
    assert config.config_dir() == tmp_path / 'Citrica'
    config.save(config.DEFAULTS)
    assert config.load() == config.DEFAULTS
    calls = []

    class Key:
        def __enter__(self):return self
        def __exit__(self, *args):return False
    registry = SimpleNamespace(HKEY_CURRENT_USER=1, REG_SZ=1,
        OpenKey=lambda *args: Key(), CreateKey=lambda *args: Key(),
        QueryValueEx=lambda *args: ('old value', 1),
        SetValueEx=lambda *args: calls.append(('set', args)), DeleteValue=lambda *args: calls.append(('delete', args)))
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    assert config.startup_enabled()
    config.set_startup(True)
    config.set_startup(False)
    assert [entry[0] for entry in calls] == ['set', 'delete']


def test_ipc_names_isolate_package_and_user_while_preserving_inno(monkeypatch):
    home = Path('C:/Users/João')
    monkeypatch.setattr(ipc.Path, 'home', lambda: home)
    monkeypatch.setattr(ipc, 'package_family_name', lambda: None)
    inno = ipc.server_name()
    assert inno == 'citrica-' + hashlib.sha256(str(home).encode()).hexdigest()[:20]
    monkeypatch.setattr(ipc, 'package_family_name', lambda: 'family_A')
    store_a = ipc.server_name()
    assert store_a == 'LOCAL\\citrica-store-' + hashlib.sha256(b'family_A\0' + str(home).encode()).hexdigest()[:20]
    monkeypatch.setattr(ipc, 'package_family_name', lambda: 'family_B')
    store_b = ipc.server_name()
    monkeypatch.setattr(ipc.Path, 'home', lambda: Path('C:/Users/another user'))
    assert len({inno, store_a, store_b, ipc.server_name()}) == 4


def test_package_native_builder_refuses_nonwindows_without_toolchain(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('package_builder', Path(__file__).parents[1] / 'packaging/windows_package.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(builder.subprocess, 'run', lambda *a, **kw: pytest.fail('Unexpected compiler'))
    with pytest.raises(RuntimeError, match='Windows SDK'):
        builder.build(tmp_path / 'citrica-package.exe')


def test_native_bridge_rejects_unpacked_context_headlessly():
    if sys.platform != 'win32':
        pytest.skip('Native Windows SDK helper executes only on Windows.')
    configured_helper = os.environ.get('CITRICA_PACKAGE_HELPER')
    helper = Path(configured_helper) if configured_helper else (
        Path(__file__).parents[1] / 'build/windows-package/citrica-package.exe')
    if configured_helper:
        assert helper.is_file(), f'Configured native helper is missing: {helper}'
    if not helper.is_file():
        pytest.skip('Compile windows_package.py before native bridge validation.')
    if package.package_family_name() is not None:
        pytest.skip('This guard test requires an unpackaged QA Python process.')
    result = subprocess.run([str(helper), '--paths'], check=False, capture_output=True, text=True,
                            encoding='utf-8', timeout=8, creationflags=0x08000000)
    error = json.loads(result.stdout)
    assert result.returncode == 1 and error['ok'] is False and error['error']
    assert error['hresult'].upper() == '0X80073D54'  # HRESULT_FROM_WIN32(APPMODEL_ERROR_NO_PACKAGE).
