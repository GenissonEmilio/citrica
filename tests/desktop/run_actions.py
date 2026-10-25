"""Terminal and shelf actions in the isolated test compositor only."""
import json
import tempfile
import time
from pathlib import Path

from run_flow import STATE, call, point_at, step, wait_for


def windows():
    return json.loads(call('Test', 'Windows')[0])


def wait_window(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        match = next((w for w in windows() if predicate(w)), None)
        if match:
            return match
        time.sleep(.1)
    raise AssertionError(windows())


def action(name):
    call('Desktop', 'Show', json.dumps([str(STATE / 'sample.png')]), 'actions')
    wheel = wait_for(lambda s: s['visible'] and s['mode'] == 'actions' and
                     any(i['id'] == name for i in s.get('items', [])))
    point_at(wheel, name)
    step('Button', 'true')
    step('Button', 'false')
    wait_for(lambda s: not s['visible'])


def main():
    step('Prepare')
    before = {w['title'] for w in windows()}
    action('terminal')
    terminal = wait_window(lambda w: w['title'] not in before)
    step('PlaceWindow', terminal['title'], 100, 100)
    time.sleep(1)
    # Type a command only into this new terminal in the test compositor.
    with tempfile.TemporaryDirectory(prefix='citrica-terminal-') as directory:
        output = Path(directory) / 'cwd.txt'
        for char in f'pwd > {output}':
            call('Test', 'Key', ord(char), 'true')
            call('Test', 'Key', ord(char), 'false')
        step('Key', 65293, 'true')
        step('Key', 65293, 'false')
        deadline = time.monotonic() + 5
        while not output.exists() and time.monotonic() < deadline:
            time.sleep(.1)
        assert output.read_text().strip() == str(STATE)
    step('Key', 65507, 'true')
    step('Key', 100, 'true')  # Ctrl+D closes only this test shell.
    step('Key', 100, 'false')
    step('Key', 65507, 'false')
    action('float')
    shelf = wait_window(lambda w: w['title'] == 'Cítrica · prateleira')
    step('PlaceWindow', shelf['title'], 600, 200)
    shelf = wait_window(lambda w: w['title'] == shelf['title'])
    x, y, width, height = shelf['rect']
    step('Pointer', x+width//2, y+height-25)
    step('Button', 'true')
    step('Pointer', x+width//2+50, y+height-25)
    drag = wait_for(lambda s: s['dragging'] and s['paths'])
    assert drag['paths'] == [str(STATE / 'sample.png')]
    step('Key', 65505, 'true')
    wait_for(lambda s: s['visible'] and s.get('items'))
    call('Test', 'Screenshot', str(STATE / 'shelf-drag.png'))
    step('Key', 65307, 'true')
    step('Key', 65307, 'false')
    step('Key', 65505, 'false')
    step('Button', 'false')
    step('PlaceWindow', shelf['title'], 600, 200)
    step('Key', 65307, 'true')
    step('Key', 65307, 'false')
    (STATE / 'actions-result.json').write_text(json.dumps({'terminal_cwd': True, 'shelf_drag': True}))
    print('Ações: terminal na pasta correta e prateleira com arraste Wayland validados.')


if __name__ == '__main__':
    try:
        main()
    finally:
        for key in [65505, 65507, 65307]:
            call('Test', 'Key', key, 'false')
        call('Test', 'Button', 'false')
