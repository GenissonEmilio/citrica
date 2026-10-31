"""Exercise standalone QApplication teardown in a separate interpreter.

Keeping pytest's shared QApplication alive hides ordering failures at process
exit, including a SIGBUS in PySide's cleanup of the PDF editor widget tree.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import wave

import pytest


DRIVER = r'''
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication
from citrica import companion, editors

mode, source, output = sys.argv[1:]
output = Path(output)
events = {'finished': 0, 'destroyed': 0}
entered = threading.Event()

def record(key):
    events[key] += 1

if mode == 'quit-export':
    def cancelled_tool(tool, paths, params, cancel):
        entered.set()
        if not cancel.wait(10):
            raise RuntimeError('Worker was not cancelled before teardown')
        (output / 'cancelled').touch()
        return {}
    companion.execute = cancelled_tool

if mode == 'screenshot-preview':
    class SlowPreview(QThread):
        ready = Signal(object)
        failed = Signal(str)
        def __init__(self, path, instant=None):
            super().__init__()
            self.cancel = threading.Event()
        def run(self):
            entered.set()
            self.cancel.wait(10)
            if self.cancel.is_set():
                (output / 'cancelled').touch()
    editors.PreviewWorker = SlowPreview

original = companion.ToolDialog
class ProbeDialog(original):
    def __init__(self, tool, paths):
        super().__init__(tool, paths)
        self.finished.connect(lambda _: record('finished'))
        self.destroyed.connect(lambda: record('destroyed'))
        if mode == 'close':
            QTimer.singleShot(100, self.close)
        elif mode in {'export', 'quit-export'}:
            self.fields['author'].setText('Citrica QA')
            self.fields['title'].setText('Lifecycle export')
            QTimer.singleShot(50, self.apply)
            QTimer.singleShot(80, self.check)
    def check(self):
        if mode == 'quit-export' and entered.is_set():
            # exit(), unlike quit(), stops the loop without letting a busy
            # window veto the Quit event. Teardown must still join its worker.
            QApplication.instance().exit(0)
        elif self.latest_output and not self.busy():
            events['output'] = str(self.latest_output)
            self.close()
        else:
            QTimer.singleShot(20, self.check)

companion.ToolDialog = ProbeDialog
app = QApplication([])
QTimer.singleShot(8000, lambda: app.exit(2))
args = SimpleNamespace(files=[Path(source)], pick=False,
    tool='trim' if mode == 'screenshot-preview' else 'edit_metadata',
    screenshot=output / 'screenshot.png' if mode == 'screenshot-preview' else None)
result = companion.launch_companion(args)
events['result'] = result
events['entered'] = entered.is_set()
(output / 'events.json').write_text(json.dumps(events))
sys.exit(result)
'''


@pytest.mark.parametrize('mode', ['close', 'export', 'quit-export', 'screenshot-preview'])
def test_standalone_editor_cleans_up_before_application_exit(tmp_path, mode):
    import pymupdf

    if mode == 'screenshot-preview':
        source = tmp_path / 'audio.wav'
        with wave.open(str(source), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b'\0\0' * 4000)
    else:
        source = tmp_path / 'pages.pdf'
        with pymupdf.open() as document:
            for number in range(3):
                document.new_page().insert_text((30, 30), f'Page {number + 1}')
            document.save(source)
    before = source.read_bytes()
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    run = subprocess.run([sys.executable, '-c', DRIVER, mode, str(source), str(tmp_path)],
                         env=env, cwd=Path(__file__).resolve().parents[1],
                         capture_output=True, text=True, timeout=18)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'shared QObject was deleted directly' not in run.stderr
    events = json.loads((tmp_path / 'events.json').read_text())
    assert events['result'] == 0
    assert events['destroyed'] == 1
    assert source.read_bytes() == before
    if mode in {'close', 'export'}:
        assert events['finished'] == 1
    if mode in {'quit-export', 'screenshot-preview'}:
        assert events['entered']
        assert (tmp_path / 'cancelled').exists()
    if mode == 'export':
        with pymupdf.open(events['output']) as result:
            assert result.page_count == 3
            assert result.metadata['author'] == 'Citrica QA'
    if mode == 'screenshot-preview':
        assert (tmp_path / 'screenshot.png').stat().st_size > 1000


FINISHING_PREVIEW_DRIVER = r'''
import json
import sys
import threading
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEvent, QThread, Qt, Signal
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid
from citrica import editors
from citrica.companion import ToolDialog

run_gate, finish_gate, finishing = threading.Event(), threading.Event(), threading.Event()
errors = []
sys.excepthook = lambda kind, error, stack: errors.append(str(error))

class FinishingPreview(QThread):
    ready = Signal(object)
    failed = Signal(str)
    def __init__(self, path, instant=None):
        super().__init__()
        self.cancel = threading.Event()
        # Real QThread reports isRunning=False before it finishes notifying
        # receivers. Hold this boundary to model a preemption deterministically.
        self.finished.connect(self.hold_finish, Qt.ConnectionType.DirectConnection)
    def hold_finish(self):
        finishing.set()
        finish_gate.wait(3)
        self.ready.emit({'late_preview': True})
        self.failed.emit('Late preview failure after the editor closed')
    def run(self):
        run_gate.wait(3)

editors.PreviewWorker = FinishingPreview
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
dialog = ToolDialog('trim', [Path(sys.argv[1])])
dialog.finished.connect(dialog.deleteLater)
dialog.show()
thread = dialog.preview_threads[0]
run_gate.set()
assert finishing.wait(3)
assert not thread.isRunning()
dialog.close()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
assert not isValid(dialog)
finish_gate.set()
assert thread.wait(3000)
app.processEvents()
cancelled = thread.cancel.is_set()
thread.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
print(json.dumps({'errors': errors, 'preview_cancelled': cancelled}))
'''


def test_finishing_preview_cannot_call_a_destroyed_editor(tmp_path):
    source = tmp_path / 'audio.wav'
    with wave.open(str(source), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b'\0\0' * 800)
    before = source.read_bytes()
    run = subprocess.run([sys.executable, '-c', FINISHING_PREVIEW_DRIVER, str(source)],
                         env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
                         cwd=Path(__file__).resolve().parents[1],
                         capture_output=True, text=True, timeout=12)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)
    assert result['errors'] == []
    assert result['preview_cancelled']
    assert source.read_bytes() == before
