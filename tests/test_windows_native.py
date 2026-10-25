"""Actual RegisterHotKey conflict/cleanup test on the Windows CI runner."""
import sys
import threading

import pytest
from PySide6.QtWidgets import QApplication

from citrica.windows.native import NativeDesktop

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Win32 integration runs on Windows CI')


def test_win32_registration_conflict_preserves_previous_binding():
    import ctypes
    app = QApplication.instance() or QApplication([])
    native = NativeDesktop(app, {'drag_key': 'Shift'})
    native.timer.stop()
    ready, stop = threading.Event(), threading.Event()
    result = []
    def claim_other_thread():
        user = ctypes.WinDLL('user32', use_last_error=True)
        result.append(bool(user.RegisterHotKey(None, 123, 7 | 0x4000, 0x86)))  # Ctrl+Alt+Shift+F23
        ready.set()
        stop.wait(10)
        user.UnregisterHotKey(None, 123)
    thread = threading.Thread(target=claim_other_thread)
    try:
        native.register('Ctrl+Alt+Shift+F22')
        original = native.hotkey_id
        native.register('Ctrl+Alt+Shift+F22')
        assert native.hotkey_id == original
        thread.start()
        assert ready.wait(5) and result == [True]
        with pytest.raises(ValueError, match='já usa'):
            native.register('Ctrl+Alt+Shift+F23')
        assert native.hotkey_id == original
    finally:
        native.close()
        stop.set()
        if thread.ident:
            thread.join(timeout=5)
    assert native.hotkey_id == 0
