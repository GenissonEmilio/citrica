"""Win32 global hotkey and physical drag/modifier observation on the Qt thread.

No keys are intercepted or injected. A Shift+mouse drag exposes a drop target;
Qt's OLE data offer, not the mouse heuristic, supplies the actual file paths.
"""
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal
from PySide6.QtGui import QCursor

from citrica.windows.config import parse_shortcut


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, native):
        super().__init__()
        self.native = native

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in {b'windows_generic_MSG', b'windows_dispatcher_MSG'}:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.native.hotkey_id:  # WM_HOTKEY
                self.native.toggle.emit()
                return True, 0
        return False, 0


class NativeDesktop(QObject):
    toggle = Signal()
    mode = Signal(str)
    released = Signal()
    key = Signal(str)
    dragStarted = Signal(object)

    def __init__(self, app, settings):
        super().__init__()
        if sys.platform != 'win32':
            raise RuntimeError('Esta integração requer Windows.')
        self.app, self.settings = app, settings
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.user.RegisterHotKey.restype = wintypes.BOOL
        self.user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
        self.user.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.user.GetSystemMetrics.restype = ctypes.c_int
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.elevated = bool(ctypes.WinDLL('shell32').IsUserAnAdmin())
        self.hotkey_id = 0
        self.shortcut = None
        self._next_id = 0x4c00
        self.filter = HotkeyFilter(self)
        app.installNativeEventFilter(self.filter)
        self.visible = False
        self._left = False
        self._anchor = QCursor.pos()
        self._mode = None
        self._suppressed = False
        self._keys = set()
        self._drag_started, self._source_window = False, 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(20)

    def register(self, shortcut):
        mods, key = parse_shortcut(shortcut)
        if self.hotkey_id and self.shortcut == (mods, key):
            return
        candidate = self._next_id
        self._next_id += 1
        if not self.user.RegisterHotKey(None, candidate, mods | 0x4000, key):
            raise ValueError('O Windows ou outro aplicativo já usa este atalho. Escolha outra combinação.')
        previous, self.hotkey_id = self.hotkey_id, candidate
        self.shortcut = (mods, key)
        if previous:
            self.user.UnregisterHotKey(None, previous)

    def down(self, key):
        return bool(self.user.GetAsyncKeyState(key) & 0x8000)

    def left_down(self):
        return self.down(2 if self.user.GetSystemMetrics(23) else 1)

    def reset_drag(self):
        self._mode = None
        self._suppressed = self.left_down()

    def poll(self):
        left, point = self.left_down(), QCursor.pos()
        if left and not self._left:
            self._anchor, self._mode, self._suppressed = point, None, False
            self._drag_started = False
            self._source_window = self.user.GetForegroundWindow()
            # Prefetch on press, before Explorer enters its modal OLE loop.
            self.dragStarted.emit(self._source_window)
        moved = abs(point.x() - self._anchor.x()) >= 6 or abs(point.y() - self._anchor.y()) >= 6
        if left and moved and not self._suppressed:
            if not self._drag_started:
                self._drag_started = True
                foreground = self.user.GetForegroundWindow()
                if foreground != self._source_window:
                    self._source_window = foreground
                    self.dragStarted.emit(foreground)
            trigger = self.down(0x10) if self.settings['drag_key'] == 'Shift' else self.down(0x5b) or self.down(0x5c)
            mode = 'actions' if self.down(0x11) else 'tools' if self.down(0x12) else 'convert' if trigger else None
            if mode and mode != self._mode:
                self._mode = mode
                self.mode.emit(mode)
            elif mode is None:
                self._mode = None  # Releasing/repressing the same modifier can retry an offer.
        if self.visible:
            keys = {name for vk, name in [(0x1b, 'Escape'), (0x25, 'Left'), (0x27, 'Right'), (0x0d, 'Return')]
                    if self.down(vk)}
            for key in keys - self._keys:
                self.key.emit(key)
            self._keys = keys
        else:
            self._keys.clear()
        if self._left and not left:
            self._suppressed, self._mode = False, None
            self.released.emit()
        self._left = left

    def close(self):
        self.timer.stop()
        if self.hotkey_id:
            self.user.UnregisterHotKey(None, self.hotkey_id)
            self.hotkey_id = 0
        self.app.removeNativeEventFilter(self.filter)
