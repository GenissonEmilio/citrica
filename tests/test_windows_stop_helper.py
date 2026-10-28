"""Standalone helper tests; Windows cases use a renamed Python QCore fixture, no GUI."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import site
import subprocess
import sys
import time
from pathlib import Path, PureWindowsPath

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def helper():
    if sys.platform != 'win32':
        pytest.skip('Standalone stop helper executes only on Windows.')
    path = Path(os.environ.get('CITRICA_STOP_HELPER', ROOT / 'build/windows-package/citrica-stop.exe'))
    if not path.is_file():
        pytest.skip('Compile packaging/windows_stop.py before running native helper tests.')
    return path.resolve()


@pytest.mark.parametrize('profile', ['C:\\Users\\CitricaTester', 'C:\\Users\\João ç',
                                    'C:\\Users\\João ç\\', 'C:\\', '\\\\server\\share\\'])
def test_pipe_name_matches_python_home_utf8_and_qt_prefix(helper, profile):
    env = dict(os.environ, USERPROFILE=profile)
    result = subprocess.run([str(helper), '--pipe-name'], env=env, check=False,
                            capture_output=True, text=True, encoding='utf-8', timeout=2)
    expected = '\\\\.\\pipe\\citrica-' + hashlib.sha256(str(PureWindowsPath(profile)).encode()).hexdigest()[:20]
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_empty_install_does_not_invoke_an_old_cli(helper, tmp_path):
    # An invalid old executable would fail/hang if launched. The new helper
    # only inspects the GUI image path and must return without executing it.
    (tmp_path / 'citrica-cli.exe').write_bytes(b'never execute an installed CLI')
    result = subprocess.run([str(helper), '--install-dir', str(tmp_path)], timeout=2,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('arguments', [[], ['--timeout-ms', '15001'], ['--install-dir', 'x', '--timeout-ms', 'NaN']])
def test_invalid_arguments_fail_headlessly_and_immediately(helper, arguments):
    result = subprocess.run([str(helper), *arguments], timeout=2, capture_output=True, text=True)
    assert result.returncode == 1 and 'Citrica stop helper:' in result.stderr


SERVER = r'''
import hashlib,json,sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QTimer
from PySide6.QtNetwork import QLocalServer
app=QCoreApplication([])
mode,ready=sys.argv[1:]
server=QLocalServer()
name='citrica-'+hashlib.sha256(str(Path.home()).encode()).hexdigest()[:20]
assert server.listen(name),server.errorString()
connections=[]
def accept():
    connection=server.nextPendingConnection()
    connections.append(connection)
    received=bytearray()
    def respond():
        received.extend(bytes(connection.readAll()))
        if b'\n' in received:
            assert json.loads(received.split(b'\n',1)[0])=={'op':'quit'}
            if mode=='silent':return
            connection.write(b'{"ok": true}\n')
            connection.flush()
            if mode=='exit':QTimer.singleShot(50,app.quit)
            if mode=='close':QTimer.singleShot(0,app.quit)
    connection.readyRead.connect(respond)
    if connection.bytesAvailable():respond()
server.newConnection.connect(accept)
Path(ready).write_text(json.dumps({'pipe':server.fullServerName(),'pid':app.applicationPid()}))
app.exec()
'''


@pytest.fixture
def resident(tmp_path):
    processes = []

    def start(mode):
        import PySide6
        directory = tmp_path / 'Aplicação João' / mode
        directory.mkdir(parents=True)
        executable = directory / 'Citrica.exe'
        base = Path(getattr(sys, '_base_executable', sys.executable))
        shutil.copyfile(base, executable)
        profile = tmp_path / 'perfil João'
        profile.mkdir(exist_ok=True)
        script, ready = directory / 'fixture.py', directory / 'ready.json'
        script.write_text(SERVER, encoding='utf-8')
        env = dict(os.environ, USERPROFILE=str(profile), PYTHONHOME=sys.base_prefix,
                   PYTHONPATH=os.pathsep.join(site.getsitepackages()))
        env['PATH'] = os.pathsep.join([str(base.parent), str(Path(PySide6.__file__).parent), env.get('PATH', '')])
        process = subprocess.Popen([str(executable), str(script), mode, str(ready)], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(process)
        deadline = time.monotonic() + 10
        while not ready.is_file() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.025)
        assert ready.is_file(), f'Headless named-pipe fixture failed: {process.poll()}'
        return process, directory, env, json.loads(ready.read_text())
    yield start
    for process in processes:
        if process.poll() is None:
            process.terminate()  # Only the test's own explicitly created fixture.
        process.wait(timeout=5)


@pytest.mark.parametrize('mode', ['exit', 'close'])
def test_quit_uses_exact_qt_pipe_and_waits_for_matching_process_exit(helper, resident, mode):
    process, directory, env, ready = resident(mode)
    probe = subprocess.run([str(helper), '--pipe-name'], env=env, capture_output=True, text=True, timeout=2)
    assert probe.stdout.strip() == ready['pipe']
    result = subprocess.run([str(helper), '--install-dir', str(directory), '--timeout-ms', '3000'],
                            env=env, capture_output=True, text=True, timeout=4)
    assert result.returncode == 0, result.stderr
    assert process.wait(timeout=1) == 0


@pytest.mark.parametrize('mode', ['silent', 'stay'])
def test_no_ack_or_ack_without_exit_fails_within_budget_without_killing(helper, resident, mode):
    process, directory, env, ready = resident(mode)
    started = time.monotonic()
    result = subprocess.run([str(helper), '--install-dir', str(directory), '--timeout-ms', '700'],
                            env=env, capture_output=True, text=True, timeout=2)
    assert result.returncode == 1 and result.stderr
    assert time.monotonic() - started < 1.8
    assert process.poll() is None, 'The helper must never terminate a target process.'


def test_other_installation_is_neither_sent_quit_nor_waited_for(helper, resident, tmp_path):
    process, directory, env, ready = resident('stay')
    other = tmp_path / 'another installation'
    other.mkdir()
    shutil.copyfile(directory / 'Citrica.exe', other / 'Citrica.exe')
    result = subprocess.run([str(helper), '--install-dir', str(other), '--timeout-ms', '700'],
                            env=env, capture_output=True, text=True, timeout=2)
    assert result.returncode == 0, result.stderr
    assert process.poll() is None


def test_native_builder_requires_windows_without_invoking_toolchains(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('windows_stop_builder', ROOT / 'packaging/windows_stop.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, 'sys', type('Platform', (), {'platform': 'linux'})())
    monkeypatch.setattr(builder.subprocess, 'run', lambda *args, **kwargs: pytest.fail('Compiler unexpectedly invoked'))
    with pytest.raises(RuntimeError, match='MSVC 2022'):
        builder.build(tmp_path / 'stop.exe')
