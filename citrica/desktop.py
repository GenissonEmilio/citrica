"""GNOME integration installer and the JSON protocol used by the Shell wheel."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from citrica.core import Options, common_formats, convert
from citrica.runtime import external_environment

UUID = "citrica@genissonemilio.github.io"
SHELL_VERSION = 3
SHELL_REVISION = 2
DESKTOP_PATH = "/io/github/GenissonEmilio/Citrica/Desktop"
DESKTOP_NAME = "io.github.GenissonEmilio.Citrica.Desktop"


def backend_command():
    return [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "citrica"]


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
    root = Path(__file__).parent.parent
    source = root / "gnome" / UUID
    if getattr(sys, "frozen", False):
        source = Path(sys._MEIPASS) / "gnome" / UUID
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
