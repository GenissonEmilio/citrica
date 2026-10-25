"""Per-user preferences and hotkey parsing without importing Win32 on Linux."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULTS = {'shortcut': 'Ctrl+Alt+C', 'drag_key': 'Shift', 'animations': True}
MODIFIERS = {'alt': 1, 'ctrl': 2, 'control': 2, 'shift': 4, 'win': 8, 'super': 8}
KEYS = {'space': 0x20, 'esc': 0x1b, 'escape': 0x1b, 'enter': 0x0d, 'return': 0x0d,
        'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28, 'home': 0x24,
        'end': 0x23, 'pgup': 0x21, 'pgdown': 0x22, 'insert': 0x2d, 'delete': 0x2e}


def parse_shortcut(text):
    if not isinstance(text, str):
        raise ValueError('Atalho inválido.')
    parts = [p.strip().lower() for p in text.split('+')]
    if len(parts) < 2 or not all(p in MODIFIERS for p in parts[:-1]):
        raise ValueError('Use Ctrl, Alt ou Win e uma tecla. Exemplo: Ctrl+Alt+C.')
    bits = [MODIFIERS[p] for p in parts[:-1]]
    if len(set(bits)) != len(bits) or not any(b in {1, 2, 8} for b in bits):
        raise ValueError('Não repita modificadores nem use somente Shift.')
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith('f') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key in KEYS:
        vk = KEYS[key]
    else:
        raise ValueError('Use A–Z, 0–9, F1–F24 ou uma tecla de navegação.')
    return sum(bits), vk


def config_dir():
    return Path(os.environ.get('APPDATA', Path.home() / '.config')) / 'Citrica'


def load():
    result = dict(DEFAULTS)
    try:
        stored = json.loads((config_dir() / 'settings.json').read_text(encoding='utf-8'))
        if not isinstance(stored, dict):
            raise ValueError('Preferências inválidas')
        parse_shortcut(stored.get('shortcut', DEFAULTS['shortcut']))
        if stored.get('drag_key', 'Shift') not in {'Shift', 'Win'}:
            raise ValueError('Invalid drag key')
        result.update({key: stored[key] for key in DEFAULTS if key in stored})
        result['animations'] = bool(result['animations'])
    except (OSError, ValueError, TypeError):
        pass
    return result


def save(settings):
    parse_shortcut(settings['shortcut'])
    folder = config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, delete=False) as stream:
        temp = Path(stream.name)
        json.dump(settings, stream, ensure_ascii=False, indent=2)
    try:
        temp.replace(folder / 'settings.json')
    finally:
        temp.unlink(missing_ok=True)


def gui_command():
    if getattr(sys, 'frozen', False):
        gui = Path(sys.executable).with_name('Citrica.exe')
        return [str(gui if gui.is_file() else Path(sys.executable))]
    return [sys.executable, '-m', 'citrica']


def startup_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            winreg.QueryValueEx(key, 'Citrica')
        return True
    except OSError:
        return False


def set_startup(enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:
            winreg.SetValueEx(key, 'Citrica', 0, winreg.REG_SZ,
                             subprocess.list2cmdline([*gui_command(), '--background']))
        else:
            try:
                winreg.DeleteValue(key, 'Citrica')
            except FileNotFoundError:
                pass
