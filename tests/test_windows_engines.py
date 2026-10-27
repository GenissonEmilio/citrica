import hashlib
import importlib.util
import io
import json
import struct
import shutil
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


def test_office_keeps_only_original_x64_crt_from_its_msi(tmp_path):
    office = tmp_path / 'Office/program'
    office.mkdir(parents=True)

    def binary(path, architecture, content):
        header = bytearray(128)
        header[:2] = b'MZ'
        struct.pack_into('<I', header, 60, 64)
        header[64:68] = b'PE\x00\x00'
        struct.pack_into('<H', header, 68, architecture)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(header + content)
        return path

    x86 = binary(tmp_path / 'System32/msvcp140.dll', 0x14c, b'x86 fixture')
    x64 = binary(tmp_path / 'System64/msvcp140.dll', 0x8664, b'x64 fixture')
    engines.preserve_office_crt(office, tmp_path)
    assert (office / 'msvcp140.dll').read_bytes() == x64.read_bytes()
    assert (office / 'msvcp140.dll').read_bytes() != x86.read_bytes()
    # Preserve a runtime already included beside Office instead of replacing it
    # with a different build from another merge module.
    x64.write_bytes(x64.read_bytes() + b'updated fixture')
    engines.preserve_office_crt(office, tmp_path)
    assert (office / 'msvcp140.dll').read_bytes() != x64.read_bytes()


def test_windows_ocr_reads_model_with_unicode_profile_path(tmp_path, monkeypatch):
    from PIL import Image, ImageDraw, ImageFont
    library, model = vision.ocr_paths()
    if not library or not model:
        pytest.skip('Motor OCR local indisponível')
    unicode_model = tmp_path / 'João e ação/tessdata'
    unicode_model.mkdir(parents=True)
    shutil.copy2(model / 'eng.traineddata', unicode_model / 'eng.traineddata')
    monkeypatch.setattr(vision, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(vision, 'ocr_paths', lambda: (library, unicode_model))
    image = Image.new('RGB', (800, 180), 'white')
    ImageDraw.Draw(image).text((30, 40), 'PRIVATE TEST 1234', font=ImageFont.load_default(size=48), fill='black')
    assert vision.text_boxes(image)
