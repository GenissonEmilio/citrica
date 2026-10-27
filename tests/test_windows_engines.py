import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from citrica import vision

SPEC = importlib.util.spec_from_file_location(
    'prepare_windows_engines', Path(__file__).parents[1] / 'packaging/prepare_windows_engines.py')
engines = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engines)


def test_engine_artifacts_are_pinned_and_not_floating_latest():
    lock = json.loads(engines.LOCK.read_text(encoding='utf-8'))
    assert lock['schema'] == 1
    for name, entry in lock.items():
        if name == 'schema':
            continue
        assert entry['url'].startswith('https://')
        assert 'latest' not in entry['url']
        assert len(bytes.fromhex(entry['sha256'])) == 32
        assert entry['version'] and entry['license']


def test_download_refuses_tampered_cache_and_wrong_hash(tmp_path, monkeypatch):
    good = b'upstream artifact'
    entry = {'url': 'https://example.invalid/tool.zip', 'sha256': hashlib.sha256(good).hexdigest()}
    (tmp_path / 'tool.zip').write_bytes(b'tampered cache')
    monkeypatch.setattr(engines.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'bad upstream'))
    with pytest.raises(ValueError, match='SHA-256'):
        engines.download(entry, tmp_path)
    assert not (tmp_path / 'tool.zip.part').exists()
    monkeypatch.setattr(engines.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(good))
    assert engines.download(entry, tmp_path).read_bytes() == good
    monkeypatch.setattr(engines.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('verified cache redownloaded'))
    assert engines.download(entry, tmp_path).read_bytes() == good


@pytest.mark.parametrize('entry', ['../escape.exe', '/absolute.exe', 'C:/root.exe', r'..\escape.exe'])
def test_engine_archive_rejects_paths_outside_staging(tmp_path, entry):
    archive = tmp_path / 'engine.zip'
    with zipfile.ZipFile(archive, 'w') as content:
        content.writestr(entry, b'unused')
    with pytest.raises(ValueError, match='inseguro'):
        engines.extract_zip(archive, tmp_path / 'staging')


def test_ocr_uses_same_offline_tree_in_bundle_and_source(tmp_path, monkeypatch):
    bundled = tmp_path / 'bundle'
    prepared = tmp_path / 'prepared'
    monkeypatch.setattr(vision, 'sys', SimpleNamespace(platform='win32', _MEIPASS=str(bundled)))
    monkeypatch.setenv('CITRICA_WINDOWS_ENGINES', str(prepared))
    library = prepared / 'ocr/libtesseract-5.dll'
    model = prepared / 'ocr/tessdata/eng.traineddata'
    model.parent.mkdir(parents=True)
    library.write_bytes(b'locator fixture')
    model.write_bytes(b'locator fixture')
    assert vision.ocr_paths() == (str(library), model.parent)
    bundle_library = bundled / 'ocr/libtesseract-5.dll'
    bundle_model = bundled / 'ocr/tessdata/eng.traineddata'
    bundle_model.parent.mkdir(parents=True)
    bundle_library.write_bytes(b'locator fixture')
    bundle_model.write_bytes(b'locator fixture')
    assert vision.ocr_paths() == (str(bundle_library), bundle_model.parent)
