"""Current-user named pipe; subsequent launches talk to the resident app."""
import hashlib
import json
import math
import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket

from citrica.windows.package import package_family_name

MAX_REQUEST = 1024 * 1024
_core_app = None


def server_name():
    home = str(Path.home()).encode('utf-8')
    family = package_family_name()
    if family is not None:
        # MSIX named pipes use the documented LOCAL namespace. Package + user
        # identity keeps Store, Inno and distinct Store packages independent.
        identity = family.encode('utf-8') + b'\0' + home
        return 'LOCAL\\citrica-store-' + hashlib.sha256(identity).hexdigest()[:20]
    return 'citrica-' + hashlib.sha256(home).hexdigest()[:20]


def _application():
    global _core_app
    if not QCoreApplication.instance():
        _core_app = QCoreApplication([])


def _remaining(deadline, limit):
    if deadline is None:
        return limit
    milliseconds = math.ceil((deadline - time.monotonic()) * 1000)
    if milliseconds <= 0:
        raise TimeoutError('O prazo para encerrar o Cítrica foi excedido.')
    return min(limit, milliseconds)


def send(payload, timeout=500, *, deadline=None):
    _application()
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') + b'\n'
    if len(data) > MAX_REQUEST:
        raise ValueError('Seleção muito grande para enviar à roda.')
    socket = QLocalSocket()
    try:
        socket.connectToServer(server_name())
        if not socket.waitForConnected(_remaining(deadline, timeout)):
            return None
        socket.write(data)
        socket.waitForBytesWritten(_remaining(deadline, 1000))
        received = bytearray()
        while b'\n' not in received:
            wait = _remaining(deadline, 3000)
            if not socket.bytesAvailable() and not socket.waitForReadyRead(wait):
                raise RuntimeError('O Cítrica não respondeu. Verifique o diagnóstico.')
            received.extend(bytes(socket.readAll()))
            if len(received) > MAX_REQUEST:
                raise RuntimeError('Resposta inválida do Cítrica.')
        return json.loads(received.split(b'\n', 1)[0])
    finally:
        socket.abort()


def server_available(timeout=100, *, deadline=None):
    """Distinguish a removed pipe from a live, busy or inaccessible service."""
    _application()
    socket = QLocalSocket()
    try:
        socket.connectToServer(server_name())
        if socket.waitForConnected(_remaining(deadline, timeout)):
            return True
        # A timeout or access error does not prove that the resident stopped.
        return socket.error() not in {
            QLocalSocket.LocalSocketError.ServerNotFoundError,
            QLocalSocket.LocalSocketError.ConnectionRefusedError,
        }
    finally:
        socket.abort()


def quit_resident(timeout=15):
    """Stop the tray process without constructing a Windows GUI/OLE context."""
    deadline = time.monotonic() + timeout
    # Reserve a final bounded connection probe to disambiguate a pipe closing
    # before the quit acknowledgement reaches this client.
    request_deadline = deadline - min(.2, timeout / 10)
    last_error = ''
    try:
        try:
            result = send({'op': 'quit'}, deadline=request_deadline)
        except (RuntimeError, TimeoutError) as error:
            # Qt can close the connection while the shutdown acknowledgement
            # is in flight. Never repeat quit or query the departing GUI for
            # status: wait for its listening pipe to actually disappear.
            last_error, result = str(error), None
        if result is not None and (not isinstance(result, dict) or result.get('ok') is not True):
            raise RuntimeError(result.get('error', 'Resposta inválida do Cítrica.')
                               if isinstance(result, dict) else 'Resposta inválida do Cítrica.')
        while time.monotonic() < deadline:
            if not server_available(deadline=deadline):
                return 0
            time.sleep(min(.1, max(0, deadline - time.monotonic())))
        detail = f' Último erro de IPC: {last_error}' if last_error else ''
        raise RuntimeError(f'O Cítrica continua ativo ou indisponível após {timeout:g} segundos.{detail}')
    except Exception as error:
        print(f'Não foi possível encerrar o Cítrica: {error}', file=sys.stderr)
        return 1
