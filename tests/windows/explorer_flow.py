"""Real Explorer drag/drop regression against the packaged Windows resident.

Runs only on the CI's input desktop. No input is sent to a user's computer.
"""
import argparse
import ctypes
import faulthandler
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import unicodedata
from ctypes import wintypes
from pathlib import Path

from docx import Document
from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

# The clean VM has no system MSVC redistributable. Qt loads its own runtime
# for the source test's PDF oracle; the frozen child uses its separate bundle.
import pymupdf

from native_flow import Input, InputUnion, Keyboard, Mouse
from citrica.windows.ipc import send

ROOT = Path(__file__).resolve().parents[2]
SCALE = os.environ.get('QT_SCALE_FACTOR', '1')
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', help='Packaged executable or --source')
    parser.add_argument('--same-folder', action='store_true')
    parser.add_argument('--bundled-engines', action='store_true',
                        help='also drag examples of every conversion family using the bundled engines')
    # Keep the existing --source invocation accepted as a positional value.
    arguments = parser.parse_args(['source' if arg == '--source' else arg for arg in sys.argv[1:]])
    run_id = SCALE + ('-same-folder' if arguments.same_folder else '') + ('-bundled' if arguments.bundled_engines else '')
    STATE = ROOT / f'build/windows-explorer-{run_id}'
    STATE.mkdir(parents=True, exist_ok=True)
    (ROOT/'release').mkdir(exist_ok=True)
    os.environ['APPDATA'] = str(STATE/'config')
    os.environ['LOCALAPPDATA'] = str(STATE/'local')
    if arguments.bundled_engines:
        assert arguments.executable != 'source', 'This test requires the packaged engines'
        for name in ['CITRICA_OFFICE_ENGINE', 'CITRICA_WINDOWS_ENGINES', 'CITRICA_TOOL_DIR', 'CITRICA_OCR_DIR']:
            os.environ.pop(name, None)
        os.environ['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    else:
        os.environ['CITRICA_OFFICE_ENGINE'] = 'builtin'
    faulthandler.dump_traceback_later(600 if arguments.bundled_engines else 100, exit=True)
    app = QApplication([])
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user.SendInput.restype = wintypes.UINT
    user.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user.GetAsyncKeyState.restype = ctypes.c_short
    def inject(event):
        assert user.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input)) == 1
    def key(vk, down):
        inject(Input(1, InputUnion(keyboard=Keyboard(vk, 0, 0 if down else 2, 0, 0))))
    def button(down):
        inject(Input(0, InputUnion(mouse=Mouse(0, 0, 0, 2 if down else 4, 0, 0))))
    def pause(seconds=.15):
        until = time.monotonic()+seconds
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.01)
    last_status, stage = None, 'resident-start'
    def wait(predicate, timeout=30):
        nonlocal last_status
        until = time.monotonic()+timeout
        current = None
        while time.monotonic() < until:
            current = send({'op': 'status'}, timeout=200)
            if current:
                last_status = current
            if current and predicate(current):
                return current
            pause(.05)
        raise AssertionError(current)
    folder = (STATE/'Citrica-explorer-validation').resolve()
    # Every run owns these synthetic fixtures. Previous outputs must not be
    # accepted as this run's conversion result or confuse hidden extensions.
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(exist_ok=True)
    def fixture(case, name):
        parent = folder if arguments.same_folder else folder/case
        parent.mkdir(exist_ok=True)
        return parent/name
    source_docx = fixture('document', 'Citrica-document.docx')
    doc = Document()
    doc.add_paragraph('Citrica real Explorer without LibreOffice')
    doc.save(source_docx)
    source_pdf = fixture('pdf', 'Citrica-page.pdf')
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((50, 60), 'Citrica Explorer PDF to editable DOCX')
        pdf.save(source_pdf)
    source_tools = fixture('tools', 'Citrica-tool.pdf')
    source_tools.write_bytes(source_pdf.read_bytes())
    source_image = fixture('image', 'Citrica-image.png')
    Image.new('RGB', (320, 200), 'orange').save(source_image)
    originals = {p: hashlib.sha256(p.read_bytes()).digest()
                 for p in [source_docx, source_pdf, source_image, source_tools]}
    engine_examples = []
    if arguments.bundled_engines:
        from engine_parity import FORMATS, fixtures, run
        cli = Path(arguments.executable).resolve().with_name('citrica-cli.exe')
        doctor = json.loads(run([cli, '--doctor'], os.environ.copy()))
        seed_dir = folder / 'engine-seeds'
        seed_dir.mkdir(exist_ok=True)
        examples = {'image': ('.png', 'jpg'), 'document': ('.odt', 'pdf'),
                    'sheet': ('.xlsx', 'pdf'), 'slides': ('.pptx', 'pdf'),
                    'video': ('.mp4', 'webm'), 'audio': ('.wav', 'mp3'),
                    'subtitle': ('.srt', 'vtt'), 'archive': ('.zip', 'tar')}
        for family, source in fixtures(seed_dir, doctor['dependencies']['ffmpeg'],
                                       doctor['dependencies']['libreoffice'], os.environ.copy()):
            if family in examples and source.suffix == examples[family][0]:
                path = fixture('bundled-' + family, 'Citrica-' + family + source.suffix)
                path.write_bytes(source.read_bytes())
                engine_examples.append((family, path, examples[family][1], FORMATS[family]))
                originals[path] = hashlib.sha256(path.read_bytes()).digest()
        assert len(engine_examples) == len(examples)
    command = ([sys.executable, '-m', 'citrica'] if arguments.executable == 'source' else
               [str(Path(arguments.executable).resolve())])
    resident_log = (STATE/'resident.log').open('w', encoding='utf-8')
    resident = subprocess.Popen([*command, '--background'], stdout=resident_log, stderr=subprocess.STDOUT,
                               env=dict(os.environ, CITRICA_QA_TRACEBACK_LOG=str(STATE/'resident-stacks.log')))
    hwnd = None
    report = {'real_explorer': True, 'qt_scale_factor': SCALE,
              'office_engine': 'bundled' if arguments.bundled_engines else 'builtin',
              'same_folder': arguments.same_folder, 'cases': {}}
    try:
        wait(lambda s: s['hotkey_active'])
        print('Explorer: aplicativo residente pronto.', flush=True)
        subprocess.Popen(['explorer.exe', str(folder)])
        import pythoncom
        from win32com.client.dynamic import Dispatch
        pythoncom.CoInitialize()
        shell = Dispatch('Shell.Application')
        window = None
        until = time.monotonic()+20
        while time.monotonic() < until and window is None:
            for candidate in shell.Windows():
                try:
                    if Path(candidate.Document.Folder.Self.Path) == folder:
                        window = candidate
                        break
                except (AttributeError, pythoncom.com_error):
                    continue
            pause(.2)
        assert window is not None, 'Explorer não abriu a pasta de teste'
        print('Explorer: pasta de teste localizada.', flush=True)
        hwnd = int(window.HWND)
        user.SetWindowPos(hwnd, None, 40, 40, 1050, 720, 0x40)
        user.SetForegroundWindow(hwnd)
        pause(.5)

        def drag(path, mode, vk, target, formats=None):
            nonlocal stage
            stage = f'select:{path.suffix}:{mode}'
            print(f'Explorer: selecionar {path.name}; modo {mode}.', flush=True)
            # In the shared-folder regression, stay in the same view while
            # conversion outputs arrive and Explorer asynchronously sorts them.
            if Path(window.Document.Folder.Self.Path) != path.parent:
                window.Navigate(str(path.parent))
            until = time.monotonic()+10
            while time.monotonic() < until:
                try:
                    if Path(window.Document.Folder.Self.Path) == path.parent:
                        break
                except (AttributeError, pythoncom.com_error):
                    pass
                pause(.1)
            else:
                raise AssertionError('Explorer não navegou para a pasta do arquivo de teste')
            pause(.4)
            # Select through Explorer's own view, then perform a physical drag
            # starting at the file's actual UI Automation rectangle.
            for attempt in range(6):
                window.Document.SelectItem(window.Document.Folder.ParseName(path.name), 1|4|8|16)
                pause(.3)
                powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
                info = subprocess.run([str(powershell), '-NoProfile', '-File',
                    str(ROOT/'tests/windows/explorer_item.ps1'), str(hwnd), path.name, path.stem],
                    capture_output=True, text=True, timeout=20)
                if info.returncode:
                    print('Explorer: aguardando a visualização de arquivos terminar de atualizar.', flush=True)
                    pause(.5)
                    continue
                rect = json.loads(info.stdout)
                print(f'Explorer: ícone localizado: {rect}.', flush=True)
                x = round(rect['x']+min(rect['width']/2, 30))
                y = round(rect['y']+rect['height']/2)
                user.SetForegroundWindow(hwnd)
                user.SetCursorPos(x, y)
                pause()
                button(True)
                pause()
                # New conversion outputs can asynchronously reorder Details
                # rows after UI Automation returns a rectangle. Confirm the
                # actual item under the click before initiating OLE.
                selected = [Path(item.Path) for item in window.Document.SelectedItems()]
                if selected == [path]:
                    break
                button(False)
                print(f'Explorer: linhas reordenadas; repetindo seleção ({attempt+1}).', flush=True)
                pause(.6)
            else:
                raise AssertionError('O Explorer não selecionou o arquivo solicitado')
            user.SetCursorPos(x+55, y+12)
            pause(.3)
            key(vk, True)
            stage = f'activate:{path.suffix}:{mode}'
            # Deliberately no pointer movement after pressing the modifier.
            wheel = wait(lambda s: s['visible'] and s['mode'] == mode and
                         any(i['id'] == target for i in s['items']))
            assert wheel['paths'] == [str(path)]
            if formats is not None:
                actual = [item['id'] for item in wheel['items'] if item['kind'] != 'page']
                expected = formats[:7] if len(formats) > 7 else formats
                assert actual == expected, (path, actual, expected)
            print(f'Explorer: roda {mode} carregada sem novo movimento.', flush=True)
            stage = f'offer:{path.suffix}:{mode}'
            index = next(i for i, item in enumerate(wheel['items']) if item['id'] == target)
            angle = -math.pi/2 + index*math.tau/len(wheel['items'])
            ox, oy = wheel['origin']
            QCursor.setPos(QPoint(round(ox+190+122*math.cos(angle)), round(oy+190+122*math.sin(angle))))
            verified = wait(lambda s: s['offer_verified'])
            print('Explorer: oferta OLE confirmada.', flush=True)
            pause(.3)
            app.primaryScreen().grabWindow(0, ox-10, oy-10, 400, 435).save(
                str(ROOT/f'release/citrica-windows-explorer-{mode}-{path.suffix[1:]}-{run_id}.png'))
            key(vk, False)
            button(False)
            stage = f'drop:{path.suffix}:{mode}'
            print('Explorer: botão liberado.', flush=True)
            return verified

        drag(source_image, 'actions', 0x11, 'copy_path')
        wait(lambda s: not s['visible'])
        pause(.2)
        assert app.clipboard().text() == str(source_image)
        report['cases']['ctrl_actions_stationary_activation'] = True
        drag(source_docx, 'convert', 0x10, 'pdf')
        wait(lambda s: not s['busy'] and s['counts']['converted'] == 1)
        with pymupdf.open(source_docx.with_suffix('.pdf')) as output:
            assert 'Citrica real Explorer without LibreOffice' in unicodedata.normalize('NFKC', output[0].get_text())
        report['cases']['docx_pdf_without_office'] = True
        drag(source_pdf, 'convert', 0x10, 'docx')
        wait(lambda s: not s['busy'] and s['counts']['converted'] == 2)
        assert any('Citrica Explorer PDF to editable DOCX' in p.text
                   for p in Document(source_pdf.with_suffix('.docx')).paragraphs)
        report['cases']['pdf_docx_editable'] = True
        drag(source_tools, 'tools', 0x12, 'metadata')
        # The metadata tool opens a dialog; close it through normal Escape.
        wait(lambda s: not s['visible'])
        pause(.5)
        key(0x1b, True)
        key(0x1b, False)
        report['cases']['alt_tools'] = True
        for family, path, target, formats in engine_examples:
            previous = send({'op': 'status'})['counts']['converted']
            drag(path, 'convert', 0x10, target, formats)
            wait(lambda s: not s['busy'] and s['counts']['converted'] == previous + 1, timeout=60)
            output = path.with_suffix('.' + target)
            assert output.is_file() and output.stat().st_size > 0, output
            report['cases']['bundled_' + family] = {'input': path.suffix, 'output': target,
                                                    'palette_verified': True, 'converted': True}
        for path, digest in originals.items():
            assert hashlib.sha256(path.read_bytes()).digest() == digest
        report['originals_preserved'] = True
        report['result'] = 'passed'
        (ROOT/f'release/citrica-windows-explorer-{run_id}-validation.json').write_text(
            json.dumps(report, indent=2), encoding='utf-8')
        print(f'Explorer real: Ctrl, Alt, Shift, DOCX/PDF e PDF→DOCX passaram ({run_id}).')
        faulthandler.cancel_dump_traceback_later()
    except Exception as failure:
        snapshot = {'stage': stage, 'error': str(failure), 'last_status': last_status,
                    'resident_pid': resident.pid, 'resident_exit_code': resident.poll(),
                    'foreground_hwnd': user.GetForegroundWindow(),
                    'input_down': {name: bool(user.GetAsyncKeyState(vk) & 0x8000)
                                   for name, vk in [('left', 1), ('shift', 0x10), ('ctrl', 0x11), ('alt', 0x12)]}}
        failure_file = STATE/'failed-state.json'
        failure_file.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
        app.primaryScreen().grabWindow(0).save(str(ROOT/f'release/citrica-windows-explorer-failure-{run_id}.png'))
        try:
            snapshot['status_before_cancel'] = send({'op': 'status'})
        except Exception as error:
            snapshot['ipc_error_before_cancel'] = str(error)
        # Diagnose whether cancelling Explorer's OLE operation unblocks the
        # resident. A recovery remains a failed test, never an automatic retry.
        key(0x1b, True)
        for vk in [0x10, 0x11, 0x12]:
            key(vk, False)
        button(False)
        key(0x1b, False)
        pause(.5)
        try:
            snapshot['status_after_cancel'] = send({'op': 'status'})
        except Exception as error:
            snapshot['ipc_error_after_cancel'] = str(error)
        snapshot['resident_exit_code_after_cancel'] = resident.poll()
        failure_file.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
        raise
    finally:
        for vk in [0x10, 0x11, 0x12, 0x1b]:
            key(vk, False)
        button(False)
        if hwnd:
            user.PostMessageW(hwnd, 0x10, 0, 0)  # Close only our controlled Explorer window.
        try:
            try:
                send({'op': 'quit'})
            except RuntimeError:
                pass
            resident.wait(timeout=15)
        except subprocess.TimeoutExpired:
            resident.terminate()
            resident.wait(timeout=5)
        finally:
            if resident.poll() is None:
                resident.terminate()
                resident.wait(timeout=5)
            resident_log.close()
            faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
