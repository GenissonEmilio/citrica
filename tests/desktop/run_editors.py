"""Exercise real editor controls and playback in the isolated Wayland session.

The backend may be a frozen binary (CITRICA_TEST_EXECUTABLE); assertions inspect
its public AT-SPI UI and resulting files, never its Python objects.
"""
import atexit
import hashlib
import json
import re
import subprocess
import time

import pymupdf
from PIL import Image

from run_flow import ENV, ROOT, STATE, call, step

HELPER = ROOT / 'tests/desktop/atspi_controls.py'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def until(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.15)
    raise AssertionError('Editor UI condition timed out.')


def controls(pid, operation='dump', name=None, role=None, value=None):
    args = ['/usr/bin/python3', str(HELPER), '--pid', str(pid), '--operation', operation]
    for key, item in [('name', name), ('role', role), ('value', value)]:
        if item is not None:
            args += ['--' + key, str(item)]
    result = subprocess.run(args, env=ENV, capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 0, (result.stdout, result.stderr)
    return json.loads(result.stdout)


def match(pid, name):
    return next((item for item in controls(pid) if item['name'] == name and item['showing']), None)


def position(pid):
    for item in controls(pid):
        value = item.get('text') or item['name']
        found = re.fullmatch(r'(\d\d):(\d\d):(\d\d\.\d\d\d) / .+', value)
        if found:
            hours, minutes, seconds = map(float, found.groups())
            return hours * 3600 + minutes * 60 + seconds
    return None


def main(groups=('image', 'pdf', 'video')):
    step('Prepare')
    call('Desktop', 'Hide')
    backend = json.loads((STATE / 'config/citrica/desktop.json').read_text())['command']
    # Launch on this private session explicitly: Fedora SELinux can deny
    # dbus-daemon auto-activation of the accessibility launcher in nested tests.
    launcher = subprocess.Popen(['/usr/libexec/at-spi-bus-launcher', '--launch-immediately'],
                                env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def stop_accessibility():
        if launcher.poll() is None:
            launcher.terminate()
            launcher.wait(timeout=5)
    atexit.register(stop_accessibility)
    until(lambda: subprocess.check_output(['gdbus', 'call', '--session', '--dest',
        'org.freedesktop.DBus', '--object-path', '/org/freedesktop/DBus', '--method',
        'org.freedesktop.DBus.NameHasOwner', 'org.a11y.Bus'], env=ENV, text=True).strip() == '(true,)')
    accessibility = subprocess.check_output(['gdbus', 'call', '--session', '--dest', 'org.a11y.Bus',
        '--object-path', '/org/a11y/bus', '--method', 'org.a11y.Bus.GetAddress'], env=ENV, text=True)
    address = __import__('ast').literal_eval(accessibility)[0]
    ENV['AT_SPI_BUS_ADDRESS'] = address
    registry = subprocess.Popen(['/usr/libexec/at-spi2-registryd'], env=ENV,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def stop_registry():
        if registry.poll() is None:
            registry.terminate()
            registry.wait(timeout=5)
    atexit.register(stop_registry)
    until(lambda: subprocess.check_output(['gdbus', 'call', '--address', address, '--dest',
        'org.freedesktop.DBus', '--object-path', '/org/freedesktop/DBus', '--method',
        'org.freedesktop.DBus.NameHasOwner', 'org.a11y.atspi.Registry'], env=ENV, text=True).strip() == '(true,)')
    gui_env = dict(ENV, QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1', AT_SPI_BUS_ADDRESS=address)
    fixtures = STATE / 'editor-fixtures'
    fixtures.mkdir(exist_ok=True)
    image = fixtures / 'foto João.png'
    gradient = Image.new('RGB', (320, 200))
    gradient.putdata([(x % 256, y % 256, 80) for y in range(200) for x in range(320)])
    gradient.save(image)
    pdf = fixtures / 'páginas João.pdf'
    with pymupdf.open() as document:
        for index in range(1, 4):
            document.new_page().insert_text((50, 70), f'Citrica QA page {index}')
        document.save(pdf)
    video = fixtures / 'vídeo João.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc2=size=320x180:rate=12', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
        '-t', '4', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
        str(video)], check=True, capture_output=True)
    sources = {path: digest(path) for path in [image, pdf, video]}
    processes = []
    logs = []
    result = {}

    def launch(tool, source, name):
        log = (STATE / f'editor-{name}.log').open('w')
        logs.append(log)
        proc = subprocess.Popen([*backend, '--tool', tool, str(source)], env=gui_env,
                                stdout=log, stderr=subprocess.STDOUT)
        processes.append(proc)
        until(lambda: controls(proc.pid))
        until(lambda: match(proc.pid, 'Salvar cópia'))
        return proc

    def save(proc, source, suffix):
        before = set(fixtures.glob('*'))
        controls(proc.pid, 'invoke', 'Salvar cópia')
        def output_ready():
            candidates = [path for path in set(fixtures.glob('*')) - before
                          if path.suffix.lower() == suffix and path.is_file() and path.stat().st_size]
            return candidates[0] if len(candidates) == 1 and match(proc.pid, 'Abrir resultado') else None
        output = until(output_ready, timeout=30)
        assert digest(source) == sources[source]
        return output

    def close(proc):
        window = next(item for item in json.loads(call('Test', 'Windows')[0])
                      if item['title'].startswith('Cítrica ·'))
        step('PlaceWindow', window['title'], 60, 35)
        step('Key', 65307, 'true')
        step('Key', 65307, 'false')
        code = proc.wait(timeout=10)
        assert code == 0, code

    try:
        if 'image' in groups:
            proc = launch('crop', image, 'image')
            for label, value in [('X', 10), ('Y', 20), ('Largura', 160), ('Altura', 90)]:
                controls(proc.pid, 'setvalue', f'Área selecionada · pixels · {label}', value=value)
            call('Test', 'Screenshot', str(STATE / 'editor-image.png'))
            output = save(proc, image, '.png')
            with Image.open(output) as cropped:
                assert cropped.size == (160, 90), cropped.size
                assert cropped.getpixel((0, 0))[:3] == (10, 20, 80)
                assert cropped.getpixel((159, 89))[:3] == (169, 109, 80)
            result['image_crop_ui_export'] = {'size': [160, 90], 'original_preserved': True}
            close(proc)

        if 'pdf' in groups:
            proc = launch('edit_metadata', pdf, 'pdf')
            controls(proc.pid, 'setvalue', 'Página do PDF na prévia', value=3)
            controls(proc.pid, 'settext', 'Autor', value='Citrica QA')
            controls(proc.pid, 'settext', 'Título', value='Metadados pela interface')
            call('Test', 'Screenshot', str(STATE / 'editor-pdf.png'))
            output = save(proc, pdf, '.pdf')
            with pymupdf.open(output) as edited:
                assert edited.page_count == 3 and edited.metadata['author'] == 'Citrica QA'
                assert edited.metadata['title'] == 'Metadados pela interface'
            result['pdf_preview_and_metadata_ui_export'] = {'pages': 3, 'original_preserved': True}
            close(proc)

        if 'video' in groups:
            proc = launch('trim', video, 'video')
            until(lambda: match(proc.pid, 'Fim'))
            until(lambda: position(proc.pid) is not None)
            controls(proc.pid, 'setvalue', role='slider', value=0)  # Keep synthetic audio silent.
            controls(proc.pid, 'invoke', '▶ Reproduzir')
            until(lambda: match(proc.pid, 'Ⅱ Pausar'))
            advanced = until(lambda: value if (value := position(proc.pid)) is not None and value > .4 else None)
            call('Test', 'Screenshot', str(STATE / 'editor-video-playing.png'))
            controls(proc.pid, 'invoke', 'Ⅱ Pausar')
            until(lambda: match(proc.pid, '▶ Reproduzir'))
            paused = position(proc.pid)
            time.sleep(.4)
            assert abs(position(proc.pid) - paused) < .15
            controls(proc.pid, 'focus', 'Linha do tempo; arraste as alças amarelas para selecionar o trecho')
            window = next(item for item in json.loads(call('Test', 'Windows')[0])
                          if item['title'] == 'Cítrica · Cortar tempo')
            step('PlaceWindow', window['title'], 60, 35)
            for _ in range(10):
                call('Test', 'Key', 65363, 'true')
                call('Test', 'Key', 65363, 'false')
                time.sleep(.03)
            sought = until(lambda: value if (value := position(proc.pid)) is not None and value > paused + .7 else None)
            controls(proc.pid, 'setvalue', 'Início', value=.5)
            controls(proc.pid, 'setvalue', 'Duração', value=1.25)
            call('Test', 'Screenshot', str(STATE / 'editor-video.png'))
            output = save(proc, video, '.mp4')
            info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format',
                                                      '-of', 'json', str(output)], text=True))
            duration = float(info['format']['duration'])
            assert abs(duration - 1.25) < .15, duration
            result['video_player_and_trim_ui_export'] = {'position_advanced_seconds': advanced,
                'pause_held_position': True, 'timeline_seek_seconds': sought,
                'export_duration': duration, 'original_preserved': True}
            close(proc)
        (STATE / 'editors-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print('Editores reais Wayland validados: ' + ', '.join(groups) + '.')
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
