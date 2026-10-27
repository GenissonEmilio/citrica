"""GNOME integration installer and the JSON protocol used by the Shell wheel."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from citrica.core import Options, common_formats, convert
from citrica.runtime import external_environment

UUID = "citrica@genissonemilio.github.io"
SHELL_VERSION = 3
SHELL_REVISION = 3
DESKTOP_PATH = "/io/github/GenissonEmilio/Citrica/Desktop"
DESKTOP_NAME = "io.github.GenissonEmilio.Citrica.Desktop"
SUPPORTED_SHELLS = {46, 50, 51}


def gnome_environment():
    try:
        result = subprocess.run(['gnome-shell', '--version'], capture_output=True, text=True,
                                timeout=5, env=external_environment())
        match = re.search(r'GNOME Shell (\d+)', result.stdout)
        major = int(match[1]) if match else None
    except (OSError, subprocess.TimeoutExpired):
        major = None
    session = os.environ.get('XDG_SESSION_TYPE', '').lower()
    wayland = session == 'wayland' or (not session and bool(os.environ.get('WAYLAND_DISPLAY')))
    return {'shell': major, 'wayland': wayland, 'supported': major in SUPPORTED_SHELLS and wayland}


def extension_source():
    root = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent.parent
    return root / 'gnome' / UUID


def setup_desktop():
    """First menu launch configures only the current user, once per payload."""
    from citrica import __version__
    from citrica.integration import install
    environment = gnome_environment()
    source = extension_source()
    fingerprint = hashlib.sha256()
    for path in sorted(source.rglob('*')):
        if path.is_file() and path.name != 'gschemas.compiled':
            fingerprint.update(str(path.relative_to(source)).encode())
            fingerprint.update(path.read_bytes())
    expected = {'version': __version__, 'command': backend_command(), 'extension': fingerprint.hexdigest(),
                'environment': environment}
    marker = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'citrica/setup.json'
    try:
        previous = json.loads(marker.read_text())
    except (OSError, ValueError):
        previous = None
    if previous == expected and (not environment['supported'] or extension_dir().is_dir()):
        return
    # The native package owns its menu launcher/icon. Avoid a user copy that
    # would shadow package updates and remain visible after uninstalling it.
    install(include_application=False)
    if environment['supported']:
        install_gnome()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(expected, ensure_ascii=False, indent=2))


def backend_command():
    if getattr(sys, 'frozen', False):
        executable = Path(sys.executable)
        cli = executable.with_name('citrica-cli.exe')
        if sys.platform == 'win32' and cli.is_file():
            executable = cli  # GUI launchers have no stdout/stderr for worker diagnostics.
        return [str(executable)]
    return [sys.executable, '-m', 'citrica']


def desktop_call(method, *args):
    return subprocess.run(["gdbus", "call", "--session", "--dest", DESKTOP_NAME,
                           "--object-path", DESKTOP_PATH, "--method", DESKTOP_NAME + "." + method,
                           *args], capture_output=True, text=True, timeout=5, env=external_environment())


def extension_status():
    try:
        result = desktop_call("Status")
        if result.returncode == 0:
            import ast
            return json.loads(ast.literal_eval(result.stdout)[0])
    except (ValueError, OSError, subprocess.TimeoutExpired):
        pass
    return {"installed": extension_dir().is_dir(), "active": False}


def extension_dir():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "gnome-shell/extensions" / UUID


def install_gnome():
    environment = gnome_environment()
    if environment['shell'] not in SUPPORTED_SHELLS:
        found = str(environment['shell']) if environment['shell'] else 'não encontrado'
        raise RuntimeError(f'A roda global requer GNOME 46, 50 ou 51. GNOME atual: {found}. '
                           'O conversor pela linha de comando continua disponível.')
    if not environment['wayland']:
        raise RuntimeError('Entre na sessão GNOME com Wayland para configurar a roda global. '
                           'A sessão X11 não é compatível com a integração de arraste.')
    source = extension_source()
    if not source.is_dir():
        raise RuntimeError("Os arquivos da extensão GNOME não foram encontrados neste pacote.")
    destination = extension_dir()
    shutil.copytree(source, destination, dirs_exist_ok=True)
    subprocess.run(["glib-compile-schemas", str(destination / "schemas")], check=True, env=external_environment())
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "citrica/desktop.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"command": backend_command()}, ensure_ascii=False, indent=2))
    # A new extension is discovered by Shell at session startup. Enabling an unknown
    # UUID is intentionally not reported as successful on a running GNOME session.
    result = subprocess.run(["gnome-extensions", "enable", UUID], capture_output=True, text=True,
                            env=external_environment())
    if result.returncode:
        # Preserve all existing extension preferences and stage ours for the next login.
        script = """import gi,json
from gi.repository import Gio
s=Gio.Settings.new('org.gnome.shell')
v=s.get_strv('enabled-extensions')
u=json.loads(__import__('sys').argv[1])
if u not in v: s.set_strv('enabled-extensions',v+[u]); Gio.Settings.sync()
"""
        subprocess.run(["/usr/bin/python3", "-c", script, json.dumps(UUID)], check=True,
                       env=external_environment())
    state = extension_status()
    active = state.get('version') == SHELL_VERSION and state.get('revision') == SHELL_REVISION
    return {"path": str(destination), "active": active,
            "requires_login": result.returncode != 0 or not active}


def request(payload):
    paths = [Path(p).expanduser().resolve() for p in payload.get("paths", [])]
    if len(paths) > 1000:
        raise ValueError("Limite de 1000 arquivos por seleção.")
    if payload["op"] in {"capabilities", "palette"}:
        from citrica.preview import selection_info
        from citrica.tools import available_tools
        def entries(mode):
            if mode == 'convert':
                return [{"id": f, "label": f.upper(), "kind": "format"} for f in common_formats(paths)]
            return [{"id": t["id"], "label": t["label"], "kind": "tool"}
                    for t in available_tools(paths, actions=mode == 'actions')]
        if payload['op'] == 'palette':
            return {'modes': {mode: entries(mode) for mode in ['convert', 'tools', 'actions']},
                    'selection': selection_info(paths)}
        mode = payload.get("mode", "convert")
        return {"items": entries(mode), "selection": selection_info(paths)}
    if payload["op"] == "convert":
        outputs, errors = [], []
        for path in paths:
            try:
                outputs.extend(str(p) for p in convert(path, payload["format"], opts=Options()))
            except Exception as e:
                errors.append(f"{path.name}: {e}")
        return {"outputs": outputs, "errors": errors}
    if payload['op'] == 'tool':
        from citrica.tools import execute
        result = execute(payload['tool'], paths, payload.get('params', {}))
        if 'outputs' in result:
            result['outputs'] = [str(p) for p in result['outputs']]
        return result
    raise ValueError("Operação desconhecida.")
