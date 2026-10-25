"""Start and clean up an isolated GNOME 50/Wayland integration test session.

Requires a local GNOME 50 installation. Never installs the harness on the user's
desktop, sends input to that desktop or changes Shell security settings.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'build/desktop-test'
UUID = 'citrica@genissonemilio.github.io'
HARNESS = 'citrica-test-harness@local'


def main():
    from PIL import Image
    STATE.mkdir(parents=True, exist_ok=True)
    for name, source in [(UUID, ROOT / 'gnome' / UUID), (HARNESS, ROOT / 'tests/desktop/harness')]:
        target = STATE / 'data/gnome-shell/extensions' / name
        shutil.copytree(source, target, dirs_exist_ok=True)
    subprocess.run(['glib-compile-schemas', str(STATE / 'data/gnome-shell/extensions' / UUID / 'schemas')],
                   check=True)
    config = STATE / 'config/citrica/desktop.json'
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({'command': [sys.executable, '-m', 'citrica']}))
    Image.new('RGB', (320, 200), '#ed713d').save(STATE / 'sample.png')
    bus = STATE / 'bus'
    bus.unlink(missing_ok=True)
    env = dict(os.environ, XDG_DATA_HOME=str(STATE / 'data'), XDG_CONFIG_HOME=str(STATE / 'config'),
               XDG_CACHE_HOME=str(STATE / 'cache'), GSETTINGS_BACKEND='memory')
    shell_log = (STATE / 'shell.log').open('w')
    server = subprocess.Popen(['dbus-run-session', '--', 'sh', '-c',
        'printf "%s" "$DBUS_SESSION_BUS_ADDRESS" > "$1"; shift; exec "$@"', 'sh', str(bus),
        'gnome-shell', '--headless', '--wayland', '--no-x11', '--wayland-display', 'citrica-validation',
        '--virtual-monitor', '1280x800'], cwd=ROOT, env=env, stdout=shell_log, stderr=subprocess.STDOUT)
    source = None
    try:
        deadline = time.monotonic() + 30
        while not bus.exists() and time.monotonic() < deadline:
            time.sleep(.1)
        env['DBUS_SESSION_BUS_ADDRESS'] = bus.read_text()
        env['WAYLAND_DISPLAY'] = 'citrica-validation'
        # Wait for Shell's initial extension discovery to finish before enabling.
        # Enabling during startup can race its async _loadExtensions in GNOME 50.
        while time.monotonic() < deadline:
            if 'GNOME Shell started at' in (STATE / 'shell.log').read_text():
                break
            time.sleep(.2)
        while time.monotonic() < deadline:
            ready = subprocess.run(['gnome-extensions', 'list'], env=env, capture_output=True)
            if ready.returncode == 0 and UUID.encode() in ready.stdout:
                break
            time.sleep(.3)
        for uuid in [UUID, HARNESS]:
            subprocess.run(['gnome-extensions', 'enable', uuid], env=env, check=True)
        time.sleep(1)
        source_log = (STATE / 'source.log').open('w')
        source = subprocess.Popen([sys.executable, str(ROOT / 'tests/desktop/drag_source.py'),
                                   str(STATE / 'sample.png')], env=env, cwd=ROOT,
                                  stdout=source_log, stderr=subprocess.STDOUT)
        time.sleep(1)
        flow = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'tests/desktop/run_flow.py'
        subprocess.run([sys.executable, str(flow)], env=env, cwd=ROOT, check=True)
        subprocess.run([sys.executable, '-m', 'citrica', '--settings', '--screenshot',
                        str(STATE / 'settings.png')], env=dict(env, QT_QPA_PLATFORM='offscreen'),
                       cwd=ROOT, check=True)
    finally:
        if source is not None:
            source.terminate()
            source.wait(timeout=5)
        if 'DBUS_SESSION_BUS_ADDRESS' in env:
            subprocess.run(['gdbus', 'call', '--session', '--dest', 'io.github.GenissonEmilio.Citrica.Test',
                '--object-path', '/io/github/GenissonEmilio/Citrica/Test',
                '--method', 'io.github.GenissonEmilio.Citrica.Test.Quit'], env=env, capture_output=True)
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.terminate()
        shell_log.close()


if __name__ == '__main__':
    main()
