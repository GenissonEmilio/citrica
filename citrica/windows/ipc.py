"""Current-user named pipe; subsequent launches talk to the resident app."""
import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket

MAX_REQUEST = 1024 * 1024
_core_app = None


def server_name():
    return 'citrica-' + hashlib.sha256(str(Path.home()).encode()).hexdigest()[:20]


def send(payload, timeout=500):
    global _core_app
    if not QCoreApplication.instance():
        _core_app = QCoreApplication([])
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') + b'\n'
    if len(data) > MAX_REQUEST:
        raise ValueError('Seleção muito grande para enviar à roda.')
    socket = QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(timeout):
        return None
    socket.write(data)
    socket.waitForBytesWritten(1000)
    received = bytearray()
    while b'\n' not in received:
        if not socket.bytesAvailable() and not socket.waitForReadyRead(3000):
            raise RuntimeError('O Cítrica não respondeu. Verifique o diagnóstico.')
        received.extend(bytes(socket.readAll()))
        if len(received) > MAX_REQUEST:
            raise RuntimeError('Resposta inválida do Cítrica.')
    socket.disconnectFromServer()
    return json.loads(received.split(b'\n', 1)[0])
