"""Environment for system programs called by the portable application."""
import configparser
import os
import shlex
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

_spawn_lock = threading.RLock()
_LOCALSEND_FLATPAK = 'org.localsend.localsend_app'


def program(name):
    """Locate bundled tools, PATH programs and standard Windows installations."""
    if name == 'libreoffice' and os.environ.get('CITRICA_OFFICE_ENGINE') == 'builtin':
        return None
    if sys.platform != 'win32':
        return shutil.which(name)
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent))
    bundled = {'ffmpeg': ['tools/ffmpeg/bin/ffmpeg.exe'],
               'ffprobe': ['tools/ffmpeg/bin/ffprobe.exe'],
               'libreoffice': ['tools/libreoffice/program/soffice.com',
                              'tools/libreoffice/program/soffice.exe'],
               'tesseract': ['ocr/tesseract.exe']}
    for relative in bundled.get(name, []):
        candidate = root / relative
        if candidate.is_file():
            return str(candidate)
    # The override is useful to test source builds with the exact same engines
    # as the packaged app; installed bundles always prefer their own versions.
    engine_root = os.environ.get('CITRICA_WINDOWS_ENGINES')
    if engine_root:
        for relative in bundled.get(name, []):
            candidate = Path(engine_root) / relative
            if candidate.is_file():
                return str(candidate)
    for folder in [root / 'bin', Path(os.environ.get('CITRICA_TOOL_DIR', root / 'bin'))]:
        candidate = folder / (name + '.exe')
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    relative = {'libreoffice': ['LibreOffice/program/soffice.com', 'LibreOffice/program/soffice.exe'],
                'tesseract': ['Tesseract-OCR/tesseract.exe'],
                'localsend': ['LocalSend/localsend_app.exe', 'LocalSend/localsend.exe']}
    for env in ['ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA']:
        if not os.environ.get(env):
            continue
        for suffix in relative.get(name, []):
            candidate = Path(os.environ[env]) / suffix
            if candidate.is_file():
                return str(candidate)
    return None


def _localsend_executable(path):
    """Accept a LocalSend binary/AppImage, never a shell or desktop wrapper."""
    path = Path(path).expanduser()
    name = path.name.casefold()
    is_appimage = (name == 'localsend.appimage' or name.startswith(('localsend-', 'localsend_')))
    is_appimage = is_appimage and name.endswith('.appimage')
    return (path.is_absolute() and (name in {'localsend', 'localsend_app'} or is_appimage)
            and path.is_file() and os.access(path, os.X_OK))


def _localsend_desktop_executable():
    """Read bounded desktop entries without executing or trusting their Exec line."""
    home = Path.home()
    data_home = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share'))
    data_dirs = os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(os.pathsep)
    for root in [data_home, *map(Path, filter(None, data_dirs))]:
        folder = root / 'applications'
        try:
            candidates = sorted(path for path in folder.iterdir()
                                if 'localsend' in path.name.casefold() and path.suffix == '.desktop')
        except OSError:
            continue
        for entry in candidates:
            try:
                if entry.stat().st_size > 65536:
                    continue
                config = configparser.ConfigParser(interpolation=None, strict=False)
                config.read_string(entry.read_text(encoding='utf-8'))
                desktop = config['Desktop Entry']
                if desktop.get('Type') != 'Application' or desktop.get('Hidden', '').lower() == 'true':
                    continue
                args = shlex.split(desktop.get('Exec', ''))
                # Only use the application path. Placeholders, shell operators,
                # launch wrappers and unexpected arguments are never evaluated.
                if not args or any(arg not in {'%f', '%F', '%u', '%U'} for arg in args[1:]):
                    continue
                executable = args[0]
                if not Path(executable).is_absolute():
                    executable = shutil.which(executable)
                if executable and _localsend_executable(executable):
                    return str(Path(executable).expanduser())
            except (OSError, UnicodeError, configparser.Error, KeyError, ValueError):
                continue
    return None


def _localsend_appimage():
    home = Path.home()
    # Immediate children only: do not traverse a user's downloads or documents.
    for name in ['Applications', 'Aplicativos', 'Downloads', 'Baixados', 'Desktop',
                 'Área de Trabalho', '.local/bin']:
        try:
            candidates = sorted((home / name).iterdir(), key=lambda path: path.name.casefold(), reverse=True)
        except OSError:
            continue
        for candidate in candidates:
            if candidate.name.casefold().endswith('.appimage') and _localsend_executable(candidate):
                return str(candidate)
    return None


def localsend_command(paths=()):
    """Build an argv for the installed LocalSend GUI; do not launch or transfer.

    Linux Flatpak installations are not normally on PATH. Forward selected paths
    through its document portal so files outside Downloads remain accessible.
    program() keeps its path-only contract for other external tools and Windows.
    """
    if sys.platform == 'win32':
        executable = program('localsend')
        return [executable, *map(str, paths)] if executable else None
    selected = [str(Path(path).expanduser().absolute()) for path in paths]
    for name in ['localsend', 'localsend_app']:
        executable = shutil.which(name)
        if executable:
            return [executable, *selected]
    if sys.platform.startswith('linux'):
        flatpak = shutil.which('flatpak')
        if flatpak:
            for installation in ['--user', '--system']:
                try:
                    result = run_external([flatpak, 'info', installation, '--show-ref', _LOCALSEND_FLATPAK],
                                          capture_output=True, text=True, encoding='utf-8', timeout=2)
                    if result.returncode == 0 and result.stdout.strip().startswith(
                            f'app/{_LOCALSEND_FLATPAK}/'):
                        command = [flatpak, 'run', installation, '--file-forwarding', _LOCALSEND_FLATPAK]
                        return command + ['@@', *selected, '@@'] if selected else command
                except (OSError, subprocess.SubprocessError, UnicodeError):
                    continue
        executable = _localsend_desktop_executable() or _localsend_appimage()
        if executable:
            return [executable, *selected]
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
