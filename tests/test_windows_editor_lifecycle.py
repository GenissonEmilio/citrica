"""Resident widget ownership and shutdown, with a real Qt process and FakeNative."""
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
import traceback
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid
from citrica import editors
from citrica.companion import ToolDialog
from citrica.windows import app as resident

mode, source, output = sys.argv[1:]
source, output = Path(source), Path(output)
events = {'finished': 0, 'destroyed': 0, 'retained_until_destroyed': [],
          'removed_after_destroyed': [], 'native_close': 0, 'shutdown': 0}
entered = threading.Event()

class FakeNative(QObject):
    toggle = Signal()
    mode = Signal(str)
    released = Signal()
    key = Signal(str)
    def __init__(self, app, settings):
        super().__init__()
        self.visible = False
    def register(self, shortcut):
        pass
    def left_down(self):
        return False
    def reset_drag(self):
        pass
    def close(self):
        events['native_close'] += 1

if mode in {'quit-preview', 'exit-preview'}:
    class SlowPreview(QThread):
        ready = Signal(object)
        failed = Signal(str)
        def __init__(self, path, instant=None):
            super().__init__()
            self.cancel = threading.Event()
        def run(self):
            entered.set()
            if self.cancel.wait(10):
                (output / 'preview-cancelled').touch()
    editors.PreviewWorker = SlowPreview

original = resident.Desktop
class ProbeDesktop(original):
    def __init__(self, app):
        super().__init__(app, FakeNative, listen=False)
        self.pointer_timer.stop()
        self.opened = 0
        def failed(kind, error, stack):
            traceback.print_exception(kind, error, stack)
            app.exit(3)
        sys.excepthook = failed
        QTimer.singleShot(50, self.open_editor)
        QTimer.singleShot(8000, lambda: app.exit(2))

    def open_editor(self):
        if mode == 'exit-job':
            def operation(cancel):
                entered.set()
                cancel.wait(10)
                events['job_cancelled'] = cancel.is_set()
                return {}
            self.job(operation, lambda result: events.update(job_result_delivered=True))
            job = next(iter(self.jobs))
            job.destroyed.connect(lambda: events.update(job_destroyed=True))
            QTimer.singleShot(20, self.wait_preview)
            return
        tool = 'trim' if mode in {'quit-preview', 'exit-preview'} else 'edit_metadata'
        window = ToolDialog(tool, [source])
        self.opened += 1
        self.keep_window(window)
        window.finished.connect(lambda _: self.finished_editor(window))
        window.destroyed.connect(lambda: self.destroyed_editor(window))
        self.current = window
        if mode == 'repeat-close':
            QTimer.singleShot(30, window.close)
        elif mode == 'export':
            window.fields['author'].setText('Resident QA')
            window.fields['title'].setText('Lifecycle export')
            window.apply()
            QTimer.singleShot(20, self.wait_export)
        else:
            QTimer.singleShot(20, self.wait_preview)

    def finished_editor(self, window):
        events['finished'] += 1
        events['retained_until_destroyed'].append(window in self.windows and isValid(window))

    def destroyed_editor(self, window):
        events['destroyed'] += 1
        events['removed_after_destroyed'].append(window not in self.windows)
        if mode == 'repeat-close' and self.opened < 5:
            QTimer.singleShot(10, self.open_editor)
        elif mode in {'repeat-close', 'export'}:
            QTimer.singleShot(10, self.quit)

    def wait_export(self):
        if self.current.latest_output and not self.current.busy():
            events['output'] = str(self.current.latest_output)
            self.current.close()
        else:
            QTimer.singleShot(20, self.wait_export)

    def wait_preview(self):
        if not entered.is_set():
            QTimer.singleShot(20, self.wait_preview)
        elif mode == 'exit-job':
            self.app.exit(0)
        elif mode == 'quit-preview':
            assert self.current.busy()
            self.quit()
        else:
            assert self.current.busy()
            self.app.exit(0)

    def prepare_shutdown(self):
        events['shutdown'] += 1
        events['windows_before_shutdown'] = len(self.windows)
        super().prepare_shutdown()
        events['windows_after_shutdown'] = len(self.windows)
        events['jobs_after_shutdown'] = len(self.jobs)

resident.Desktop = ProbeDesktop
resident.send = lambda payload: None
args = SimpleNamespace(quit=False, files=[], wheel=False, dock=False, pick=False,
                       background=True, screenshot=None)
result = resident._launch(args)
events['result'] = result
events['preview_entered'] = entered.is_set()
(output / 'events.json').write_text(json.dumps(events))
sys.exit(result)
'''


@pytest.mark.parametrize('mode', ['repeat-close', 'export', 'quit-preview', 'exit-preview', 'exit-job'])
def test_resident_editor_destruction_and_shutdown(tmp_path, mode):
    import pymupdf

    if mode in {'quit-preview', 'exit-preview'}:
        source = tmp_path / 'audio.wav'
        with wave.open(str(source), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b'\0\0' * 4000)
    else:
        source = tmp_path / 'pages.pdf'
        with pymupdf.open() as document:
            for index in range(3):
                document.new_page().insert_text((30, 30), f'Page {index + 1}')
            document.save(source)
    before = source.read_bytes()
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen',
               APPDATA=str(tmp_path / 'settings'), LOCALAPPDATA=str(tmp_path / 'local'),
               XDG_CACHE_HOME=str(tmp_path / 'cache'))
    run = subprocess.run([sys.executable, '-c', DRIVER, mode, str(source), str(tmp_path)],
                         env=env, cwd=Path(__file__).resolve().parents[1],
                         capture_output=True, text=True, timeout=18)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'shared QObject was deleted directly' not in run.stderr
    assert 'QThread: Destroyed while thread' not in run.stderr
    events = json.loads((tmp_path / 'events.json').read_text())
    assert events['result'] == 0 and events['shutdown'] == 1
    assert events['destroyed'] == (5 if mode == 'repeat-close' else 0 if mode == 'exit-job' else 1)
    assert events['windows_after_shutdown'] == 0
    assert events['jobs_after_shutdown'] == 0
    assert all(events['retained_until_destroyed'])
    assert all(events['removed_after_destroyed'])
    assert events['native_close'] >= 1
    assert source.read_bytes() == before
    if mode != 'exit-preview':
        assert events['finished'] == events['destroyed']
        assert events['windows_before_shutdown'] == 0
    else:
        assert events['windows_before_shutdown'] == 1
    if mode in {'quit-preview', 'exit-preview'}:
        assert events['preview_entered']
        assert (tmp_path / 'preview-cancelled').exists()
    if mode == 'exit-job':
        assert events['preview_entered']
        assert events['job_cancelled'] and events['job_destroyed']
        assert not events.get('job_result_delivered')
    if mode == 'export':
        with pymupdf.open(events['output']) as document:
            assert document.page_count == 3
            assert document.metadata['author'] == 'Resident QA'
