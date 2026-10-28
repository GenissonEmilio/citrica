"""The installer's stop command must never initialize a GUI/OLE context."""
import builtins
import sys
from types import SimpleNamespace

import pytest

from citrica import __main__ as entry
from citrica.windows import ipc

REAL_SERVER_AVAILABLE = ipc.server_available


@pytest.fixture(autouse=True)
def no_real_service(monkeypatch):
    monkeypatch.setattr(ipc, 'server_available', lambda **kw: False)


@pytest.fixture
def fake_clock(monkeypatch):
    clock = SimpleNamespace(now=0.)
    def sleep(seconds):
        clock.now += seconds
    monkeypatch.setattr(ipc, 'time', SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep))
    return clock


@pytest.mark.parametrize('response', [None, {'ok': True}])
def test_headless_quit_accepts_absent_or_cleanly_stopped_resident(monkeypatch, response):
    calls = []
    def send(payload, timeout=500, **kwargs):
        calls.append(payload['op'])
        return response
    monkeypatch.setattr(ipc, 'send', send)
    assert ipc.quit_resident() == 0
    assert calls == ['quit']


def test_headless_quit_reports_rejected_request_without_gui(monkeypatch, capsys):
    monkeypatch.setattr(ipc, 'send', lambda *a, **kw: {'error': 'stop rejected'})
    assert ipc.quit_resident() == 1
    assert 'stop rejected' in capsys.readouterr().err


def test_headless_quit_reports_unresponsive_resident_without_gui(monkeypatch, capsys, fake_clock):
    def send(*args, **kwargs):
        raise RuntimeError('resident did not answer')
    monkeypatch.setattr(ipc, 'send', send)
    monkeypatch.setattr(ipc, 'server_available', lambda **kw: True)
    assert ipc.quit_resident() == 1
    assert fake_clock.now == pytest.approx(15)
    assert 'resident did not answer' in capsys.readouterr().err


def test_headless_quit_accepts_pipe_closed_before_ack_is_delivered(monkeypatch):
    calls = []
    def send(payload, **kwargs):
        calls.append(payload['op'])
        raise RuntimeError('O Cítrica não respondeu. Verifique o diagnóstico.')
    monkeypatch.setattr(ipc, 'send', send)
    assert ipc.quit_resident() == 0
    assert calls == ['quit']


def test_absent_response_is_not_success_when_pipe_remains_available(monkeypatch, capsys, fake_clock):
    monkeypatch.setattr(ipc, 'send', lambda *a, **kw: None)
    monkeypatch.setattr(ipc, 'server_available', lambda **kw: True)
    assert ipc.quit_resident() == 1
    assert fake_clock.now == pytest.approx(15)
    assert 'ativo' in capsys.readouterr().err


def test_headless_quit_stops_polling_at_deadline(monkeypatch, capsys, fake_clock):
    monkeypatch.setattr(ipc, 'send', lambda *a, **kw: {'ok': True})
    monkeypatch.setattr(ipc, 'server_available', lambda **kw: True)
    assert ipc.quit_resident(timeout=1) == 1
    assert fake_clock.now == pytest.approx(1)
    assert 'após 1 segundos' in capsys.readouterr().err


@pytest.mark.parametrize('response', [None, {'ok': True}, RuntimeError('ack was closed')])
def test_quit_waits_for_transiently_available_pipe_to_disappear(monkeypatch, fake_clock, response):
    calls = []
    probes = iter([True, True, False])
    def send(payload, **kwargs):
        calls.append(payload['op'])
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(ipc, 'send', send)
    monkeypatch.setattr(ipc, 'server_available', lambda **kw: next(probes))
    assert ipc.quit_resident() == 0
    assert fake_clock.now == pytest.approx(.2)
    assert calls == ['quit'], 'Shutdown must never resend quit or request status from the departing GUI'


def test_windows_quit_routes_before_gui_or_engine_imports(monkeypatch):
    original_import = builtins.__import__
    def guard(name, *args, **kwargs):
        assert name not in {'citrica.windows.app', 'citrica.core', 'PySide6.QtWidgets'}
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guard)
    monkeypatch.setattr(entry, 'sys', SimpleNamespace(platform='win32', stdout=None, stderr=None))
    monkeypatch.setattr(sys, 'argv', ['citrica-cli.exe', '--quit'])
    monkeypatch.setattr(ipc, 'quit_resident', lambda: 23)
    assert entry.main() == 23


def test_linux_quit_flag_keeps_existing_companion_route(monkeypatch):
    monkeypatch.setattr(entry, 'sys', SimpleNamespace(platform='linux', stdout=None, stderr=None))
    monkeypatch.setattr(sys, 'argv', ['citrica', '--quit'])
    monkeypatch.setattr(ipc, 'quit_resident', lambda: pytest.fail('Linux must not use the Windows stop command'))
    monkeypatch.setitem(sys.modules, 'citrica.core', SimpleNamespace(
        Options=None, common_formats=None, convert=None, dependencies=None, merge_pdfs=None))
    monkeypatch.setitem(sys.modules, 'citrica.companion', SimpleNamespace(launch_companion=lambda args: 42))
    assert entry.main() == 42


def test_direct_windows_launch_quit_bypasses_qapplication(monkeypatch):
    from citrica.windows import app
    monkeypatch.setattr(app, 'QApplication', SimpleNamespace(
        instance=lambda: pytest.fail('The stop command constructed a GUI/OLE context')))
    monkeypatch.setattr(ipc, 'quit_resident', lambda: 23)
    assert app._launch(SimpleNamespace(quit=True)) == 23


def test_send_total_deadline_covers_fragmented_response_and_closes_socket(monkeypatch):
    clock = SimpleNamespace(now=0.)
    monkeypatch.setattr(ipc, 'time', SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(ipc, '_application', lambda: None)
    class Socket:
        aborted = False
        def connectToServer(self, name):
            pass
        def waitForConnected(self, milliseconds):
            assert milliseconds <= 50
            return True
        def write(self, data):
            return len(data)
        def waitForBytesWritten(self, milliseconds):
            assert milliseconds <= 50
            return True
        def bytesAvailable(self):
            return 1
        def readAll(self):
            clock.now += .06
            return b'{'  # Never complete a JSON line; the deadline cannot reset.
        def abort(self):
            self.aborted = True
    socket = Socket()
    monkeypatch.setattr(ipc, 'QLocalSocket', lambda: socket)
    with pytest.raises(TimeoutError, match='prazo'):
        ipc.send({'op': 'status'}, deadline=.05)
    assert socket.aborted


@pytest.mark.parametrize('error, available', [
    ('ServerNotFoundError', False), ('ConnectionRefusedError', False),
    ('SocketTimeoutError', True), ('SocketAccessError', True), ('ConnectionError', True),
])
def test_service_probe_only_accepts_explicit_absence(monkeypatch, error, available):
    errors = ipc.QLocalSocket.LocalSocketError
    instances = []
    class Socket:
        LocalSocketError = errors
        aborted = False
        def __init__(self):
            instances.append(self)
        def connectToServer(self, name):
            pass
        def waitForConnected(self, timeout):
            return False
        def error(self):
            return getattr(errors, error)
        def abort(self):
            self.aborted = True
    monkeypatch.setattr(ipc, '_application', lambda: None)
    monkeypatch.setattr(ipc, 'QLocalSocket', Socket)
    assert REAL_SERVER_AVAILABLE() is available
    assert len(instances) == 1 and instances[0].aborted
