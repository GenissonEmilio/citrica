"""File-manager interoperability in the isolated test compositor only."""
import json
import subprocess
import time

from PIL import Image

from run_flow import ENV, STATE, call, point_at, status, step, wait_for


def main():
    folder = STATE / 'files'
    folder.mkdir(exist_ok=True)
    for output in folder.glob('sample*.jpg'):
        output.unlink()
    Image.new('RGB', (320, 200), '#ed713d').save(folder / 'sample.png')
    step('Prepare')
    env = dict(ENV, GTK_A11Y='none', GDK_BACKEND='wayland', GSK_RENDERER='cairo')
    proc = subprocess.Popen(['nautilus', '--new-window', str(folder)], env=env,
                            stdout=(STATE / 'nautilus.log').open('w'), stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            windows = json.loads(call('Test', 'Windows')[0])
            if any(w['title'] in {'files', 'Arquivos', 'Files'} for w in windows):
                break
            time.sleep(.2)
        print(json.dumps(windows, ensure_ascii=False))
        title = next(w['title'] for w in windows if w['title'] in {'files', 'Arquivos', 'Files'})
        step('PlaceWindow', title, 100, 100)
        call('Test', 'Screenshot', str(STATE / 'nautilus-start.png'))
        step('Pointer', 380, 225)
        step('Button', 'true')
        step('Button', 'false')
        step('Button', 'true')
        step('Pointer', 430, 230)
        drag = wait_for(lambda s: s['dragging'] and s['paths'])
        assert drag['paths'] == [str(folder / 'sample.png')]
        step('Key', 65505, 'true')
        wheel = wait_for(lambda s: s['visible'] and s.get('items'))
        point_at(wheel, 'jpg')
        step('Key', 65505, 'false')
        call('Test', 'Screenshot', str(STATE / 'nautilus-wheel.png'))
        step('Button', 'false')
        wait_for(lambda s: not s['visible'] and not s['busy'] and s['counts']['converted'] == 1)
        outputs = list(folder.glob('sample*.jpg'))
        assert len(outputs) == 1 and Image.open(outputs[0]).size == (320, 200)
        assert not status()['counts']['errors']
        assert (folder / 'sample.png').is_file()
        call('Test', 'Screenshot', str(STATE / 'nautilus-result.png'))
        (STATE / 'nautilus-result.json').write_text(json.dumps({'nautilus_shift_drag': True,
            'drop_converts': True, 'original_preserved': True, 'output_dimensions': [320, 200]}))
        print('Nautilus / GNOME 50 / Wayland: arraste, Shift global, roda, drop e JPG validados.')
    finally:
        call('Test', 'Key', 65505, 'false')
        call('Test', 'Button', 'false')
        subprocess.run(['nautilus', '--quit'], env=ENV, capture_output=True)
        proc.wait(timeout=5)


if __name__ == '__main__':
    main()
