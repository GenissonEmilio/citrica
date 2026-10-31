"""Close a newly mapped editor through its own Wayland window-manager request.

Run through run_session.py with source or CITRICA_TEST_EXECUTABLE. The close is
addressed to both the owned process and window ID, independent of keyboard focus.
"""
import json
import subprocess
import time

from run_flow import ENV, STATE, call


def main():
    backend = json.loads((STATE / 'config/citrica/desktop.json').read_text())['command']
    fixtures = STATE / 'editor-fixtures'
    fixtures.mkdir(exist_ok=True)
    video = fixtures / 'vídeo João.mp4'
    if not video.exists():
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'testsrc2=size=320x180:rate=12', '-t', '4', '-c:v', 'libx264', '-preset',
            'ultrafast', '-pix_fmt', 'yuv420p', str(video)], check=True, capture_output=True)
    results = []
    for attempt in range(3):
        log_path = STATE / f'editor-early-close-{attempt}.log'
        with log_path.open('w') as log:
            proc = subprocess.Popen([*backend, '--tool', 'trim', str(video)], env=ENV,
                                    stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 15
                window = None
                while time.monotonic() < deadline:
                    window = next((item for item in json.loads(call('Test', 'Windows')[0])
                                   if item['title'] == 'Cítrica · Cortar tempo'
                                   and item.get('pid') == proc.pid), None)
                    if window:
                        break
                    assert proc.poll() is None, ('startup_exit', proc.returncode)
                    time.sleep(.02)
                assert window, 'Editor did not map'
                mapped = time.monotonic()
                call('Test', 'CloseWindow', proc.pid, window['id'])
                try:
                    code = proc.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    (STATE / f'editor-early-close-{attempt}-timeout.json').write_text(json.dumps({
                        'pid': proc.pid, 'window': window,
                        'windows': json.loads(call('Test', 'Windows')[0]),
                        'shell_state': json.loads(call('Test', 'State')[0]),
                    }, ensure_ascii=False, indent=2))
                    raise
                assert code == 0, ('early_close_exit', code)
                results.append({'attempt': attempt + 1, 'close_after_map': True,
                    'close_method': 'WM_DELETE addressed by PID and window ID', 'exit_code': code,
                    'seconds_after_map': round(time.monotonic() - mapped, 3)})
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=10)
        text = log_path.read_text(errors='replace')
        for marker in ['Internal C++ object', 'Traceback (most recent call last)',
                       'Error calling Python override', 'shared QObject was deleted directly']:
            assert marker not in text, (attempt, marker, text)
        results[-1]['unhandled_callback_errors'] = False
    (STATE / 'early-close-result.json').write_text(json.dumps({
        'frozen_preview_startup_close': results}, ensure_ascii=False, indent=2))
    print('Editor: três inicializações/fechamentos imediatos com exit 0.')


if __name__ == '__main__':
    main()
