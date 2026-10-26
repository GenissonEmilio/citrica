"""Read only the initiating Explorer window's selected filesystem files.

This is a preview fallback while OLE is still negotiating. It never authorizes
an operation: the drop target must independently receive the actual file offer.
"""
import sys
import json
import subprocess
from pathlib import Path


def explorer_window(hwnd):
    if sys.platform != 'win32' or not hwnd:
        return False
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32')
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.restype = ctypes.c_int
    name = ctypes.create_unicode_buffer(256)
    user.GetClassNameW(hwnd, name, len(name))
    return name.value in {'CabinetWClass', 'ExploreWClass'}


def preview_files(hwnd):
    if not explorer_window(hwnd):
        return []
    # Never initialize Shell COM in the Qt process. During OLE, Explorer can
    # synchronously call our GUI while a COM call holds Python's GIL. A child
    # process breaks that cycle and has a strict, enforceable deadline.
    from citrica.desktop import backend_command
    from citrica.runtime import run_external
    try:
        result = run_external([*backend_command(), '--internal-explorer-selection', str(int(hwnd))],
                              capture_output=True, text=True, encoding='utf-8', timeout=2.5)
    except subprocess.TimeoutExpired:
        raise RuntimeError('A prévia do Explorer excedeu 2,5 segundos; aguardando a oferta OLE.') from None
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:] or 'Prévia do Explorer indisponível.')
    paths = json.loads(result.stdout)
    if not isinstance(paths, list) or len(paths) > 1000 or not all(isinstance(p, str) for p in paths):
        raise ValueError('Prévia de seleção inválida.')
    return [Path(p) for p in paths]


def selected_files(hwnd):
    if not explorer_window(hwnd):
        return []
    import pythoncom
    from win32com.client.dynamic import Dispatch
    pythoncom.CoInitialize()
    try:
        shell = Dispatch('Shell.Application')
        for window in shell.Windows():
            try:
                if int(window.HWND) != int(hwnd):
                    continue
                selected = window.Document.SelectedItems()
                if not 0 < selected.Count <= 1000:
                    return []
                paths = []
                for item in selected:
                    if not item.IsFileSystem:
                        return []
                    path = Path(item.Path).resolve()
                    if not path.is_file():
                        return []
                    if path not in paths:
                        paths.append(path)
                return paths
            except (AttributeError, OSError, pythoncom.com_error):
                continue
        return []
    finally:
        pythoncom.CoUninitialize()
