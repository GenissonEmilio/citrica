"""Actual Win32 input and cross-process OLE drag against the packaged GUI.

Only runs on a dedicated Windows CI desktop. Explorer validation on the user's
Windows remains a separate manual check; this source is a real Qt/OLE client.
"""
import ctypes
import json
import math
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication
from citrica.windows.ipc import send

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'build/windows-native'
STATE.mkdir(parents=True, exist_ok=True)
os.environ['APPDATA'] = str(STATE / 'config')
os.environ['LOCALAPPDATA'] = str(STATE / 'local')
os.environ.pop('QT_QPA_PLATFORM', None)

class Mouse(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]


class Keyboard(ctypes.Structure):
    _fields_ = [('vk', wintypes.WORD), ('scan', wintypes.WORD), ('flags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]


class InputUnion(ctypes.Union):
    _fields_ = [('mouse', Mouse), ('keyboard', Keyboard)]


class Input(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('data', InputUnion)]


def main():
    app = QApplication([])
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user.SendInput.restype = wintypes.UINT
    user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user.OpenInputDesktop.restype = wintypes.HANDLE
    user.SwitchDesktop.argtypes = [wintypes.HANDLE]
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    report_file = ROOT / 'release/citrica-windows-native-validation.json'
    report_file.parent.mkdir(exist_ok=True)
    desktop = user.OpenInputDesktop(0, False, 0x101)
    visible = bool(desktop and user.SwitchDesktop(desktop))
    if desktop:
        user.CloseDesktop(desktop)
    if not visible:
        report_file.write_text(json.dumps({'native_input_test': 'not available',
            'reason': 'CI has no visible input desktop', 'manual_explorer': 'pending external tester'}, indent=2))
        print('CI sem desktop de entrada visível; teste nativo explicitamente pendente.')
        return
    def inject(event):
        assert user.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input)) == 1, ctypes.get_last_error()
    def key(vk, down):
        inject(Input(1, InputUnion(keyboard=Keyboard(vk, 0, 0 if down else 2, 0, 0))))
    def button(down):
        inject(Input(0, InputUnion(mouse=Mouse(0, 0, 0, 2 if down else 4, 0, 0))))
    def pause(seconds=.12):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.01)
    def state():
        return send({'op': 'status'}, timeout=100)
    def wait(predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = state()
            if current and predicate(current):
                return current
            pause(.05)
        raise AssertionError(state())
    source_file = STATE / 'fóto com espaços.png'
    Image.new('RGB', (320, 200), 'orange').save(source_file)
    original = source_file.read_bytes()
    gui = Path(sys.argv[1]).resolve()
    resident = subprocess.Popen([str(gui), '--background'])
    source = None
    try:
        wait(lambda s: s['hotkey_active'])
        source = subprocess.Popen([sys.executable, str(ROOT / 'tests/desktop/drag_source.py'), str(source_file)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user.FindWindowW.restype = wintypes.HWND
        user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT]
        deadline = time.monotonic() + 10
        hwnd = None
        while not hwnd and time.monotonic() < deadline:
            hwnd = user.FindWindowW(None, 'Citrica · arquivo de teste')
            pause(.1)
        assert hwnd
        user.SetWindowPos(hwnd, None, 60, 60, 620, 560, 0x40)
        pause(.3)
        QCursor.setPos(QPoint(240, 260))
        pause()
        button(True)
        pause()
        QCursor.setPos(QPoint(310, 260))
        pause(.3)
        assert not state()['visible']
        key(0x10, True)  # Shift observed globally while another process owns OLE.
        pause(.2)
        # Ensure OLE observes a mouse move over the newly exposed drop target.
        QCursor.setPos(QPoint(314, 264))
        wheel = wait(lambda s: any(i['id'] == 'jpg' for i in s['items']))
        index = next(i for i, item in enumerate(wheel['items']) if item['id'] == 'jpg')
        angle = -math.pi / 2 + index * math.tau / len(wheel['items'])
        x, y = wheel['origin']
        target = QPoint(int(x+190+122*math.cos(angle)), int(y+190+122*math.sin(angle)))
        QCursor.setPos(target)
        pause(.3)
        app.primaryScreen().grabWindow(0, x-12, y-12, 404, 440).save(
            str(ROOT / 'release/citrica-windows-wheel.png'))
        key(0x10, False)
        pause(.1)
        button(False)
        done = wait(lambda s: not s['busy'] and s['counts']['converted'] == 1)
        assert not done['visible'] and done['paths'] == [] and done['selection'] is None
        assert source_file.read_bytes() == original
        assert Image.open(next(STATE.glob('*.jpg'))).size == (320, 200)
        for vk in [0x11, 0x12, ord('C')]:
            key(vk, True)
            pause(.06)
        for vk in [ord('C'), 0x12, 0x11]:
            key(vk, False)
            pause(.06)
        empty = wait(lambda s: s['visible'])
        assert empty['paths'] == [] and empty['items'] == [] and empty['selection'] is None
        key(0x1b, True)
        pause()
        key(0x1b, False)
        wait(lambda s: not s['visible'])
        result = {'native_input_test': 'passed', 'cross_process_qt_ole_drag': True,
                  'global_shift': True, 'real_conversion': True, 'original_preserved': True,
                  'global_hotkey': True, 'reopened_empty': True, 'global_escape': True,
                  'manual_explorer': 'pending external tester'}
        report_file.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print('Windows nativo: OLE entre processos, Shift, conversão, atalho e reabertura vazia passaram.')
    except Exception:
        app.primaryScreen().grabWindow(0).save(str(ROOT / 'release/citrica-windows-failure.png'))
        (STATE / 'failed-state.json').write_text(json.dumps(state(), indent=2), encoding='utf-8')
        raise
    finally:
        for vk in [0x10, 0x11, 0x12, ord('C'), 0x1b]:
            key(vk, False)
        button(False)
        if source:
            source.terminate()
            source.wait(timeout=5)
        try:
            send({'op': 'quit'})
            resident.wait(timeout=15)
        finally:
            if resident.poll() is None:
                resident.terminate()


if __name__ == '__main__':
    main()
