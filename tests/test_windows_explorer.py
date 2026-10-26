import json
import subprocess

import pytest

from citrica.windows.explorer import preview_files


def test_explorer_preview_is_an_isolated_bounded_worker(tmp_path, monkeypatch):
    source = tmp_path/'document.docx'
    source.write_bytes(b'locator test')
    monkeypatch.setattr('citrica.windows.explorer.explorer_window', lambda hwnd: True)
    calls = []
    class Process:
        returncode, timed_out, killed = 0, False, False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def communicate(self, timeout=None):
            calls.append(timeout)
            if self.timed_out and timeout is not None:
                raise subprocess.TimeoutExpired('selection worker', timeout)
            return json.dumps([str(source)]), ''
        def kill(self):
            self.killed = True
    process = Process()
    def worker(args, **kwargs):
        calls.append((args, kwargs))
        return process
    monkeypatch.setattr('citrica.runtime.popen_external', worker)
    assert preview_files(123) == [source]
    assert calls[0][0][-2:] == ['--internal-explorer-selection', '123']
    assert calls[1] == 2.5
    process.timed_out = True
    with pytest.raises(RuntimeError, match='2,5 segundos'):
        preview_files(123)
    assert process.killed
