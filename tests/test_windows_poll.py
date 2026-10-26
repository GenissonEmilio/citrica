"""Exercise modifier edges without depending on the physical user's input."""
from types import SimpleNamespace

from PySide6.QtCore import QObject, QPoint, Signal

from citrica.windows.native import NativeDesktop


class Poller(QObject):
    mode = Signal(str)
    dragStarted = Signal(object)
    released = Signal()
    key = Signal(str)

    def __init__(self):
        super().__init__()
        self.settings = {'drag_key': 'Shift'}
        self._left, self._suppressed, self._drag_started = False, False, False
        self._mode, self._anchor, self._keys = None, QPoint(), set()
        self.visible, self.left, self.keys = False, False, set()
        self.user = SimpleNamespace(GetForegroundWindow=lambda: 123)

    def left_down(self):
        return self.left

    def down(self, key):
        return key in self.keys


def test_repressing_ctrl_retries_and_all_modes_use_same_drag(monkeypatch):
    poller = Poller()
    point = QPoint(200, 200)
    monkeypatch.setattr('citrica.windows.native.QCursor.pos', lambda: QPoint(point))
    modes, starts = [], []
    poller.mode.connect(modes.append)
    poller.dragStarted.connect(starts.append)
    poller.left = True
    NativeDesktop.poll(poller)
    point.setX(250)
    for key in [0x11, None, 0x11, 0x12, 0x10]:
        poller.keys = {key} if key else set()
        NativeDesktop.poll(poller)
    assert starts == [123]
    assert modes == ['actions', 'actions', 'tools', 'convert']
