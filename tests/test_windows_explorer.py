import json
import subprocess
from types import SimpleNamespace

import pytest

from citrica.windows.explorer import preview_files


def test_explorer_preview_is_an_isolated_bounded_worker(tmp_path, monkeypatch):
    source = tmp_path/'document.docx'
    source.write_bytes(b'locator test')
    monkeypatch.setattr('citrica.windows.explorer.explorer_window', lambda hwnd: True)
    calls = []
    def worker(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps([str(source)]), stderr='')
    monkeypatch.setattr('citrica.runtime.run_external', worker)
    assert preview_files(123) == [source]
    assert calls[0][0][-2:] == ['--internal-explorer-selection', '123']
    assert calls[0][1]['timeout'] == 2.5
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 2.5)
    monkeypatch.setattr('citrica.runtime.run_external', timeout)
    with pytest.raises(RuntimeError, match='2,5 segundos'):
        preview_files(123)
