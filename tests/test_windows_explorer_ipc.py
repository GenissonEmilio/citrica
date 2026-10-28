"""QA controller IPC must leave its owning Qt/Explorer COM thread responsive."""
import importlib.util
import json
import os
from pathlib import Path
import threading
import time
import uuid

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

SPEC = importlib.util.spec_from_file_location(
    'explorer_qa', Path(__file__).parent / 'windows/explorer_flow.py')
explorer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(explorer)


@pytest.fixture
def qt_app():
    return QApplication.instance() or QApplication([])


def test_worker_requests_preserve_order_and_pump_controller(qt_app):
    main_thread = threading.get_ident()
    gate = threading.Event()
    writes, pump_calls = [], []

    def writer(payload, timeout, deadline):
        writes.append((payload, threading.get_ident()))
        assert gate.wait(1), 'The controller did not pump while waiting for its worker'
        return {'response': payload['number']}

    def pump():
        qt_app.processEvents()
        pump_calls.append(threading.get_ident())
        if len(pump_calls) >= 3:
            gate.set()

    client = explorer.PumpedIpcClient(pump, writer=writer)
    try:
        assert client.request({'number': 1}) == {'response': 1}
        assert client.request({'number': 2}) == {'response': 2}
    finally:
        client.close()
    assert [payload['number'] for payload, thread in writes] == [1, 2]
    assert len({thread for payload, thread in writes}) == 1
    assert writes[0][1] != main_thread
    assert len(pump_calls) >= 3 and set(pump_calls) == {main_thread}


def test_worker_error_propagates_without_retry(qt_app):
    writes = []
    failure = RuntimeError('explicit worker transport failure')

    def writer(payload, timeout, deadline):
        writes.append(payload)
        raise failure

    client = explorer.PumpedIpcClient(qt_app.processEvents, writer=writer)
    try:
        with pytest.raises(RuntimeError) as error:
            client.request({'op': 'status'})
        assert error.value is failure
        assert writes == [{'op': 'status'}]
    finally:
        client.close()


def test_outer_deadline_fails_explicitly_and_never_retries(qt_app):
    writes = []

    def writer(payload, timeout, deadline):
        writes.append(payload)
        time.sleep(.12)
        return {'late': True}

    client = explorer.PumpedIpcClient(qt_app.processEvents, writer=writer, request_timeout=.03)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match='no request was retried'):
            client.request({'op': 'status'})
        assert time.monotonic() - started < .1
        with pytest.raises(RuntimeError, match='previous request exceeded'):
            client.request({'op': 'status'})
    finally:
        client.close()
    assert writes == [{'op': 'status'}]
    assert client.worker.isFinished()
    client.close()
    with pytest.raises(RuntimeError, match='closed'):
        client.request({'op': 'status'})


def test_real_local_socket_response_requires_main_thread_event_pump(qt_app, monkeypatch):
    """Native QLocalSocket waits must not starve the server's main-thread slots."""
    name = 'citrica-qa-' + uuid.uuid4().hex
    monkeypatch.setattr(explorer, 'server_name', lambda: name)
    server = QLocalServer()
    assert server.listen(name), server.errorString()
    connections, callbacks = [], []
    main_thread = threading.get_ident()

    def accept():
        socket = server.nextPendingConnection()
        connections.append(socket)
        received = bytearray()

        def respond():
            received.extend(bytes(socket.readAll()))
            if b'\n' in received:
                callbacks.append(threading.get_ident())
                payload = json.loads(received.split(b'\n', 1)[0])
                socket.write(json.dumps({'echo': payload}).encode() + b'\n')
                socket.flush()

        socket.readyRead.connect(respond)
        if socket.bytesAvailable():
            respond()

    server.newConnection.connect(accept)
    client = explorer.PumpedIpcClient(qt_app.processEvents)
    try:
        for number in [1, 2]:
            assert client.request({'number': number}) == {'echo': {'number': number}}
        assert callbacks == [main_thread, main_thread]
    finally:
        client.close()
        for socket in connections:
            socket.abort()
        server.close()


def test_missing_server_returns_none_without_implicit_retry(qt_app, monkeypatch):
    monkeypatch.setattr(explorer, 'server_name', lambda: 'citrica-qa-missing-' + uuid.uuid4().hex)
    client = explorer.PumpedIpcClient(qt_app.processEvents)
    try:
        assert client.request({'op': 'status'}, timeout=20) is None
    finally:
        client.close()


def test_real_transport_rejects_expired_total_deadline(qt_app):
    with pytest.raises(TimeoutError, match='request deadline'):
        explorer._blocking_request({'op': 'status'}, 200, time.monotonic() - 1)
