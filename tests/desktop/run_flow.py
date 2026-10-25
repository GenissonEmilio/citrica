"""Real modifier + Wayland drag/drop test inside an isolated GNOME 50 compositor.

The test harness supplies native virtual input devices to this test compositor
only. No input is sent to the user's desktop and no Shell security flag is changed.
"""
import ast
import json
import math
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'build/desktop-test'
ENV = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=(STATE / 'bus').read_text().strip())


def call(service, method, *args):
    name = f'io.github.GenissonEmilio.Citrica.{service}'
    result = subprocess.run(['gdbus', 'call', '--session', '--dest', name,
                             '--object-path', '/io/github/GenissonEmilio/Citrica/' + service,
                             '--method', name + '.' + method, *map(str, args)],
                            env=ENV, capture_output=True, text=True, check=True)
    return ast.literal_eval(result.stdout.replace('(true,)', '(True,)').replace('(false,)', '(False,)'))


def step(method, *args):
    call('Test', method, *args)
    time.sleep(.3)
    if method == 'Pointer':
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            point = json.loads(call('Test', 'State')[0])['pointer']
            if point[:2] == list(args):
                break
            call('Test', method, *args)
            time.sleep(.1)


def status():
    return json.loads(call('Desktop', 'Status')[0])


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = status()
        if predicate(state):
            return state
        time.sleep(.05)
    raise AssertionError(status())


def start_drag():
    step('PlaceWindow', 'Citrica · arquivo de teste', 80, 140)
    step('Pointer', 600, 600)
    step('Pointer', 260, 260)
    step('Button', 'true')
    step('Button', 'false')
    step('Button', 'true')
    step('Pointer', 310, 260)
    return wait_for(lambda s: s['dragging'] and s['paths'])


def point_at(wheel, item_id):
    index = next(i for i, item in enumerate(wheel['items']) if item['id'] == item_id)
    angle = -math.pi/2 + index*2*math.pi/len(wheel['items'])
    x, y = wheel['origin']
    step('Pointer', int(x+190+132*math.cos(angle)), int(y+190+132*math.sin(angle)))


def main():
    call('Desktop', 'Hide')
    step('Prepare')
    time.sleep(.5)
    step('Key', 65307, 'true')
    step('Key', 65307, 'false')
    drag = start_drag()
    assert not drag['visible'], 'A roda não deve abrir antes da tecla de ativação.'
    step('Key', 65505, 'true')
    wheel = wait_for(lambda s: s['visible'] and s.get('items'))
    assert wheel['mode'] == 'convert'
    wait_for(lambda s: (s.get('motion') or {}).get('settled'))
    call('Test', 'Screenshot', str(STATE / 'shift-wheel.png'))
    assert any(i['id'] == 'jpg' for i in wheel['items'])
    point_at(wheel, 'jpg')
    step('Key', 65505, 'false')
    assert status()['visible'], 'Soltar Shift deve manter a roda aberta até o drop.'
    call('Test', 'Screenshot', str(STATE / 'selected-sector.png'))
    step('Button', 'false')
    done = wait_for(lambda s: not s['visible'] and not s['busy'] and s['counts']['converted'] > 0)
    assert not done['counts']['errors']
    assert list(STATE.glob('sample*.jpg'))
    call('Test', 'Screenshot', str(STATE / 'converted.png'))
    # Independent shortcut invocation while no drag is active.
    step('Key', 65515, 'true')  # Super
    step('Key', 65505, 'true')  # Shift
    step('Key', 99, 'true')
    step('Key', 99, 'false')
    step('Key', 65505, 'false')
    step('Key', 65515, 'false')
    empty = wait_for(lambda s: s['visible'] and (s.get('motion') or {}).get('settled'))
    assert empty['paths'] == [] and empty['items'] == [] and empty['selection'] is None
    assert empty['selected'] == -1 and not empty['cachedSelection']
    call('Test', 'Screenshot', str(STATE / 'reopened-empty.png'))
    step('Key', 65307, 'true')
    step('Key', 65307, 'false')
    wait_for(lambda s: not s['visible'])
    # Actual desktop animation values, not a simulated web preview.
    call('Desktop', 'Show', '[]', 'convert')
    early = status()['animation']
    assert early['opacity'] < 255 or early['scale'] != 1
    wait_for(lambda s: s['animation']['opacity'] == 255 and abs(s['animation']['scale']-1) < .001)
    call('Desktop', 'Hide')
    # Alt and Control work during the same real Wayland drag, without Shift.
    start_drag()
    step('Key', 65513, 'true')  # Alt
    tools = wait_for(lambda s: s['visible'] and s['mode'] == 'tools' and len(s.get('items', [])) > 1)
    assert any(i['id'] == 'crop' for i in tools['items'])
    wait_for(lambda s: (s.get('motion') or {}).get('settled'))
    call('Test', 'Screenshot', str(STATE / 'tools-wheel.png'))
    step('Key', 65513, 'false')
    step('Key', 65507, 'true')  # Ctrl
    actions = wait_for(lambda s: s['visible'] and s['mode'] == 'actions' and
                       any(i['id'] == 'copy_path' for i in s.get('items', [])))
    point_at(actions, 'copy_path')
    step('Key', 65507, 'false')
    step('Button', 'false')
    wait_for(lambda s: not s['visible'])
    assert call('Test', 'Clipboard')[0] == str(STATE / 'sample.png')
    # Pagination and launch of a compact tool dialog from the native wheel.
    call('Desktop', 'Show', json.dumps([str(STATE / 'sample.png')]), 'tools')
    tools = wait_for(lambda s: s['visible'] and any(i['kind'] == 'page' for i in s.get('items', [])))
    more = next(i for i in tools['items'] if i['kind'] == 'page')
    point_at(tools, more['id'])
    step('Button', 'true')
    step('Button', 'false')
    wait_for(lambda s: any(i['id'] == 'redact_faces' for i in s.get('items', [])))
    call('Desktop', 'Show', json.dumps([str(STATE / 'sample.png')]), 'tools')
    tools = wait_for(lambda s: any(i['id'] == 'crop' for i in s.get('items', [])))
    point_at(tools, 'crop')
    step('Button', 'true')
    step('Button', 'false')
    wait_for(lambda s: not s['visible'])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        windows = json.loads(call('Test', 'Windows')[0])
        if any(w['title'] == 'Cítrica · Recortar' for w in windows):
            break
        time.sleep(.1)
    assert any(w['title'] == 'Cítrica · Recortar' for w in windows)
    step('PlaceWindow', 'Cítrica · Recortar', 550, 220)
    call('Test', 'Screenshot', str(STATE / 'crop-dialog.png'))
    step('Key', 65307, 'true')
    step('Key', 65307, 'false')
    # Escape cancels a real drag without publishing another conversion.
    start_drag()
    step('Key', 65505, 'true')
    wait_for(lambda s: s['visible'] and s.get('items'))
    before = status()['counts']['converted']
    step('Key', 65307, 'true')
    step('Key', 65307, 'false')
    step('Key', 65505, 'false')
    step('Button', 'false')
    wait_for(lambda s: not s['visible'] and not s['dragging'])
    assert status()['counts']['converted'] == before
    # The optional Super drag trigger is configured through the real schema.
    settings_env = dict(ENV, GSETTINGS_SCHEMA_DIR=str(STATE /
                        'data/gnome-shell/extensions/citrica@genissonemilio.github.io/schemas'))
    subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'drag-key', 'super'],
                   env=settings_env, check=True)
    start_drag()
    step('Key', 65515, 'true')
    wheel = wait_for(lambda s: s['visible'] and s.get('items') and s['dragKey'] == 'super')
    point_at(wheel, 'jpg')
    step('Key', 65515, 'false')
    step('Button', 'false')
    wait_for(lambda s: not s['visible'] and not s['busy'] and s['counts']['converted'] == before+1)
    subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'drag-key', 'shift'],
                   env=settings_env, check=True)
    # Keyboard selection survives the pointer polling until the mouse moves.
    before = status()['counts']['converted']
    call('Desktop', 'Show', json.dumps([str(STATE / 'sample.png')]), 'convert')
    wait_for(lambda s: s['visible'] and s.get('items'))
    step('Key', 65363, 'true')  # Right
    step('Key', 65363, 'false')
    assert status()['selected'] == 0
    step('Key', 65293, 'true')  # Return
    step('Key', 65293, 'false')
    wait_for(lambda s: not s['visible'] and not s['busy'] and s['counts']['converted'] == before+1)
    # Apply a different global chord, then restore the default for subsequent runs.
    subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'toggle-wheel',
                    "['<Super><Shift>v']"], env=settings_env, check=True)
    time.sleep(.2)
    for key in [65515, 65505, 118]:
        step('Key', key, 'true')
    for key in [118, 65505, 65515]:
        step('Key', key, 'false')
    wait_for(lambda s: s['visible'] and s['shortcut'] == ['<Super><Shift>v'])
    call('Desktop', 'Hide')
    subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'toggle-wheel',
                    "['<Super><Shift>c']"], env=settings_env, check=True)
    subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'animations', 'false'],
                   env=settings_env, check=True)
    time.sleep(.1)
    call('Desktop', 'Show', '[]', 'convert')
    assert status()['animation'] == {'opacity': 255, 'scale': 1}
    call('Desktop', 'Hide')
    subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'animations', 'true'],
                   env=settings_env, check=True)
    (STATE / 'result.json').write_text(json.dumps({'shift_drag': True, 'drop_converts': True,
        'shortcut': True, 'escape': True, 'animation': True, 'alt_tools': True, 'ctrl_actions': True,
        'copy_path': True, 'pagination': True, 'tool_dialog': True, 'cancel_drag': True, 'super_drag_setting': True,
        'keyboard_navigation': True, 'custom_shortcut': True, 'disable_animation': True,
        'reopen_after_conversion_empty': True,
        'state': status()}, ensure_ascii=False, indent=2))
    print('GNOME 50 / Wayland: Shift, Alt, Ctrl, roda animada, conversão, atalho, Escape, '
          'clipboard, paginação e diálogo de recorte validados.')


if __name__ == '__main__':
    try:
        main()
    finally:
        for key in [65505, 65515, 65507, 65513]:
            call('Test', 'Key', key, 'false')
        call('Test', 'Button', 'false')
