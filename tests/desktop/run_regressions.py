"""Selection lifetime regressions on the real Shell actors and engine."""
import json
import sys
import time

from run_flow import ROOT, STATE, call, point_at, start_drag, status, step, wait_for


def assert_clean(state):
    assert state['paths'] == [] and state['items'] == [] and state['selection'] is None, state
    assert state['selected'] == -1 and not state['cachedSelection'], state


def reopen_empty():
    for key in [65515, 65505, 99]:
        step('Key', key, 'true')
    for key in [99, 65505, 65515]:
        step('Key', key, 'false')
    state = wait_for(lambda s: s['visible'] and (s.get('motion') or {}).get('settled'))
    assert_clean(state)
    assert not state['motion']['preview']
    call('Desktop', 'Hide')
    assert_clean(status())


def main():
    step('Prepare')
    call('Desktop', 'Hide')
    source = STATE / 'sample.png'
    # Repeated real success and a corrupt input failure both clear the selection.
    broken = STATE / 'broken.png'
    broken.write_bytes(b'not an image')
    for path in [source, source, broken]:
        before = status()['counts'].copy()
        call('Desktop', 'Show', json.dumps([str(path)]), 'convert')
        wheel = wait_for(lambda s: (s.get('motion') or {}).get('settled') and s['items'])
        point_at(wheel, 'jpg')
        step('Button', 'true')
        step('Button', 'false')
        done = wait_for(lambda s: not s['visible'] and not s['busy'])
        assert_clean(done)
        key = 'errors' if path == broken else 'converted'
        assert done['counts'][key] == before[key] + 1
        reopen_empty()
    # Escape clears a fully populated wheel, not just its visible actor.
    call('Desktop', 'Show', json.dumps([str(source)]), 'tools')
    wait_for(lambda s: (s.get('motion') or {}).get('settled') and s['items'])
    step('Key', 65307, 'true')
    step('Key', 65307, 'false')
    assert_clean(status())
    reopen_empty()
    # Delay the real backend to reproduce a late reply after close/new opening.
    config = STATE / 'config/citrica/desktop.json'
    original = config.read_text()
    marker = STATE / 'request-started'
    command = json.loads(original)['command']
    config.write_text(json.dumps({'command': [sys.executable,
        str(ROOT / 'tests/desktop/delayed_backend.py'), json.dumps(command), str(marker)]}))
    try:
        for close in [True, False]:
            marker.unlink(missing_ok=True)
            call('Desktop', 'Show', json.dumps([str(source)]), 'convert')
            deadline = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            assert marker.exists()
            if close:
                call('Desktop', 'Hide')
                assert_clean(status())
            call('Desktop', 'Show', '[]', 'convert')
            time.sleep(2)  # Deliberately outlive the pending engine response.
            assert_clean(status())
            assert status()['visible'] and not status()['motion']['preview']
            call('Desktop', 'Hide')
        marker.unlink(missing_ok=True)
        start_drag()  # The prefetched palette must also ignore a finished drag.
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.exists()
        call('Desktop', 'Hide')
        step('Button', 'false')
        call('Desktop', 'Show', '[]', 'convert')
        time.sleep(2)
        assert_clean(status())
        call('Desktop', 'Hide')
    finally:
        config.write_text(original)
    reopen_empty()
    result = {name: True for name in ['repeat_conversion_empty', 'failed_conversion_empty',
        'escape_empty', 'late_reply_after_hide_ignored', 'late_reply_after_replace_ignored',
        'late_drag_palette_ignored', 'shortcut_has_no_preview']}
    (STATE / 'regressions-result.json').write_text(json.dumps(result, indent=2))
    print('Regressões nativas: sucesso repetido, erro, Escape, respostas atrasadas e reabertura vazia passaram.')


if __name__ == '__main__':
    try:
        main()
    finally:
        for key in [65505, 65515, 65507, 65513]:
            call('Test', 'Key', key, 'false')
        call('Test', 'Button', 'false')
