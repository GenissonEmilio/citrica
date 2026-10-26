"""Read only the initiating Explorer window's selected filesystem files.

This is a preview fallback while OLE is still negotiating. It never authorizes
an operation: the drop target must independently receive the actual file offer.
"""
import sys
from pathlib import Path


def selected_files(hwnd):
    if sys.platform != 'win32' or not hwnd:
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
