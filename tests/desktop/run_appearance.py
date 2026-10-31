"""Validate live styles during a real drag in the isolated GNOME compositor."""
import hashlib
import json
import subprocess
import time

from run_flow import ENV, STATE, call, point_at, start_drag, status, step, wait_for


def main():
    settings_env = dict(ENV, GSETTINGS_SCHEMA_DIR=str(STATE /
                        'data/gnome-shell/extensions/citrica@genissonemilio.github.io/schemas'))
    sample = STATE / 'sample.png'
    original = hashlib.sha256(sample.read_bytes()).hexdigest()
    result = []
    call('Desktop', 'Hide')
    step('Prepare')
    start_drag()
    call('Test', 'ObserveMotion')
    step('Key', 65505, 'true')
    wheel = wait_for(lambda s: s['visible'] and s['items'] and (s.get('motion') or {}).get('settled'))
    point_at(wheel, 'jpg')
    initial = status()
    assert initial['revision'] >= 4
    assert initial['motion']['preview']
    for theme in ('classic', 'watercolor', 'glass', 'graphite', 'contrast'):
        subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'wheel-theme', theme],
                       env=settings_env, check=True)
        state = wait_for(lambda s: s['wheelTheme'] == theme and s['motion']['theme'] == theme)
        assert state['visible'] and state['dragging']
        assert state['paths'] == initial['paths'] and state['items'] == initial['items']
        assert state['selected'] == initial['selected']
        assert state['origin'] == initial['origin'] and state['motion']['preview']
        time.sleep(.10)
        capture = STATE / f'appearance-{theme}.png'
        assert call('Test', 'Screenshot', str(capture))[0]
        result.append({'theme': theme, 'live_update': True, 'selection_preserved': True,
                       'thumbnail_preserved': True, 'capture': capture.name,
                       'sha256': hashlib.sha256(capture.read_bytes()).hexdigest()})
    step('Key', 65505, 'false')
    step('Button', 'false')
    wait_for(lambda s: not s['visible'] and not s['busy'] and
             s['counts']['converted'] == initial['counts']['converted'] + 1)
    assert hashlib.sha256(sample.read_bytes()).hexdigest() == original
    assert list(STATE.glob('sample*.jpg'))
    call('Desktop', 'Show', '[]', 'convert')
    empty = wait_for(lambda s: s['visible'] and (s.get('motion') or {}).get('settled'))
    assert empty['wheelTheme'] == 'contrast'
    assert empty['paths'] == [] and empty['items'] == [] and not empty['motion']['preview']
    frames = json.loads(call('Test', 'Motion')[0])
    intermediate = [state for state in frames if state.get('animation') and
                    0 < state['animation']['opacity'] < 255]
    assert intermediate, 'Native wheel opening did not produce intermediate frames.'
    call('Desktop', 'Hide')
    (STATE / 'appearance-result.json').write_text(json.dumps({'styles': result,
        'conversion_after_live_theme_changes': True, 'reopen_empty': True,
        'original_preserved': True, 'native_intermediate_frames': len(intermediate)}, indent=2))
    print('GNOME: cinco temas ao vivo, miniatura/seleção preservadas, animação e conversão reais validadas.')


if __name__ == '__main__':
    try:
        main()
    finally:
        settings_env = dict(ENV, GSETTINGS_SCHEMA_DIR=str(STATE /
                            'data/gnome-shell/extensions/citrica@genissonemilio.github.io/schemas'))
        subprocess.run(['gsettings', 'reset', 'org.gnome.shell.extensions.citrica', 'wheel-theme'],
                       env=settings_env, check=True)
        call('Desktop', 'Hide')
        call('Test', 'Key', 65505, 'false')
        call('Test', 'Button', 'false')
