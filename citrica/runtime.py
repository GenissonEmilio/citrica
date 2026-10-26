"""Environment for system programs called by the portable application."""
import os
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

_spawn_lock = threading.RLock()


def program(name):
    """Locate bundled tools, PATH programs and standard Windows installations."""
    if name == 'libreoffice' and os.environ.get('CITRICA_OFFICE_ENGINE') == 'builtin':
        return None
    if sys.platform != 'win32':
        return shutil.which(name)
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent))
    for folder in [root / 'bin', Path(os.environ.get('CITRICA_TOOL_DIR', root / 'bin'))]:
        candidate = folder / (name + '.exe')
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    relative = {'libreoffice': ['LibreOffice/program/soffice.com', 'LibreOffice/program/soffice.exe'],
                'localsend': ['LocalSend/localsend_app.exe', 'LocalSend/localsend.exe']}
    for env in ['ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA']:
        if not os.environ.get(env):
            continue
        for suffix in relative.get(name, []):
            candidate = Path(os.environ[env]) / suffix
            if candidate.is_file():
                return str(candidate)
    return None


def external_environment():
    env = os.environ.copy()
    # PyInstaller and Qt prepend bundled libraries/plugins. System programs must
    # use their own libraries, especially across Ubuntu-build/Fedora-runtime.
    original = env.get('LD_LIBRARY_PATH_ORIG')
    if original is not None:
        env['LD_LIBRARY_PATH'] = original
    else:
        env.pop('LD_LIBRARY_PATH', None)
    env.pop('QT_PLUGIN_PATH', None)
    env.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
    if sys.platform == 'win32' and getattr(sys, 'frozen', False):
        bundled = Path(sys._MEIPASS).resolve()
        env['PATH'] = os.pathsep.join(part for part in env.get('PATH', '').split(os.pathsep)
                                    if part and not Path(part).resolve().is_relative_to(bundled))
    return env


@contextmanager
def system_dll_search():
    """Do not pass PyInstaller's DLL search directory to external Windows apps."""
    with _spawn_lock:
        kernel = None
        if sys.platform == 'win32' and getattr(sys, 'frozen', False):
            import ctypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
            kernel.SetDllDirectoryW(None)
        try:
            yield
        finally:
            if kernel:
                kernel.SetDllDirectoryW(sys._MEIPASS)


def popen_external(args, **kwargs):
    kwargs.setdefault('env', external_environment())
    if sys.platform == 'win32':
        kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    with system_dll_search():
        return subprocess.Popen(args, **kwargs)


def run_external(args, **kwargs):
    kwargs.setdefault('env', external_environment())
    if sys.platform == 'win32':
        kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    with system_dll_search():
        return subprocess.run(args, **kwargs)
