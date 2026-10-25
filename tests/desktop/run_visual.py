"""Record the actual isolated GNOME output and observe compositor paint states."""
import json
import subprocess
import time

from run_flow import ENV, STATE, call, point_at, start_drag, status, step, wait_for


def main():
    step('Prepare')
    call('Desktop', 'Hide')
    start_drag()
    wait_for(lambda s: s['cachedSelection'])
    recording = call('Test', 'StartRecording', str(STATE / 'wheel-capture'))[0]
    call('Test', 'ObserveMotion')
    call('Test', 'Key', 65505, 'true')
    wheel = wait_for(lambda s: (s.get('motion') or {}).get('settled') and s['items'])
    call('Test', 'Screenshot', str(STATE / 'visual-open.png'))
    point_at(wheel, 'jpg')
    time.sleep(.3)
    call('Test', 'Screenshot', str(STATE / 'visual-selected.png'))
    point_at(wheel, 'webp')
    time.sleep(.3)
    call('Desktop', 'Hide')
    time.sleep(.25)
    step('Key', 65505, 'false')
    step('Button', 'false')
    assert call('Test', 'StopRecording')[0]
    samples = json.loads(call('Test', 'Motion')[0])
    opening = [s for s in samples if s['animation'] and 0 < s['animation']['opacity'] < 255]
    assert len(opening) >= 4, opening
    assert len({round(s['animation']['scale'], 4) for s in opening}) >= 4
    assert status()['paths'] == [] and status()['items'] == []
    (STATE / 'motion-result.json').write_text(json.dumps({'actual_paint_frames': len(samples),
        'intermediate_opening_frames': len(opening), 'opening_ms': 240,
        'sector_stagger_ms': 8, 'hover_ms': 140, 'closing_ms': 130,
        'intermediate_states_observed': True, 'samples': samples}, indent=2))
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', recording,
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
        str(STATE / 'wheel-native.mp4')], env=ENV, check=True)
    print(f'Captura nativa salva; {len(opening)} quadros intermediários reais na abertura.')


if __name__ == '__main__':
    try:
        main()
    finally:
        for key in [65505, 65515, 65507, 65513]:
            call('Test', 'Key', key, 'false')
        call('Test', 'Button', 'false')
