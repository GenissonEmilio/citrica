"""Integrity boundaries for reusing only engines from a previous QA archive."""
import hashlib
import importlib.util
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def reuse():
    spec = importlib.util.spec_from_file_location('engine_reuse', ROOT / 'packaging/reuse_windows_test_engines.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def package(tmp_path, reuse):
    root = tmp_path / 'repository'
    (root / 'packaging').mkdir(parents=True)
    for name in reuse.RECIPES:
        (root / name).write_bytes((ROOT / name).read_bytes())
    original_source, model, license_text = b'pinned source fixture', b'pinned model fixture', b'license fixture'
    def h(data):
        return hashlib.sha256(data).hexdigest()
    source_lock = {'schema': 1, 'sources': {'ffmpeg': {'version': 'test-source', 'sha256': h(original_source)}}}
    vendor_lock = {'schema': 1, 'libreoffice': {'version': 'test-office', 'sha256': h(b'office MSI')},
                   'ocr_eng': {'version': 'test-model', 'sha256': h(model)},
                   'ocr_license': {'version': 'test-license', 'sha256': h(license_text)}}
    for name, value in [('windows-sources.lock.json', source_lock), ('windows-engines.lock.json', vendor_lock)]:
        (root / 'packaging' / name).write_text(json.dumps(value), encoding='utf-8')
    source_files = {name: (root / name).read_bytes() for name in [*reuse.RECIPES,
        'packaging/windows-sources.lock.json', 'packaging/windows-engines.lock.json']}
    source_files |= {'downloads/sources/source.tar.gz': original_source, 'downloads/eng.traineddata': model,
                     'downloads/LICENSE': license_text}
    payload = {name: b'engine fixture' for name in reuse.REQUIRED - {'engines.json', 'engine-sources.zip'}}
    payload['ocr/tesseract55.dll'] = b'compiled OCR DLL fixture'
    payload['ocr/tessdata/eng.traineddata'] = model
    manifest = {'schema': 1, 'provenance': 'compiled-from-pinned-sources', 'sources': source_lock['sources'],
                'libreoffice': vendor_lock['libreoffice'], 'ocr_eng': vendor_lock['ocr_eng'],
                'ocr_library': 'tesseract55.dll'}

    def make(*, mutate_manifest=None, mutate_files=None, mutate_sources=None, inventory_change=None, extra=None):
        files, sources, metadata = dict(payload), dict(source_files), dict(manifest)
        if mutate_sources:
            mutate_sources(sources)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, data in sources.items():
                archive.writestr(name, data)
        files['engine-sources.zip'] = stream.getvalue()
        metadata['corresponding_source'] = {'file': 'engine-sources.zip', 'sha256': h(stream.getvalue())}
        if mutate_manifest:
            mutate_manifest(metadata)
        files['engines.json'] = json.dumps(metadata).encode()
        inventory = {name: h(data) for name, data in files.items()}
        if mutate_files:
            mutate_files(files)
        if inventory_change:
            inventory_change(inventory)
        path = tmp_path / 'portable.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in files.items():
                archive.writestr(reuse.PREFIX + name, data)
            archive.writestr(reuse.PREFIX + reuse.INVENTORY, json.dumps(inventory))
            archive.writestr('Citrica/Citrica.exe', b'previous application MUST NOT be copied')
            archive.writestr(reuse.PREFIX + 'Qt6Core.dll', b'previous Qt MUST NOT be copied')
            archive.writestr(reuse.PREFIX + 'tools/libreoffice/program/__pycache__/uno.pyc', b'cache MUST NOT be copied')
            if extra:
                archive.writestr(*extra)
        return path
    return make, root, tmp_path / 'engines', tmp_path / 'report.json'


def test_reuse_copies_only_verified_inventory_and_corresponding_sources(package, reuse):
    make, root, output, report = package
    result = reuse.restore(make(), output, report, root=root)
    assert result['success'] and result['current_locks_match'] and result['build_affecting_recipes_match']
    assert result['purpose'] == 'unsigned-test-only' and result['release_eligible'] is False
    assert result['application_runtime_reused'] is False
    assert result['unlisted_engine_files_ignored'] == 1
    expected = set(json.loads((output / reuse.INVENTORY).read_text())) | {reuse.INVENTORY}
    assert {file.relative_to(output).as_posix() for file in output.rglob('*') if file.is_file()} == expected
    assert not (output / 'Qt6Core.dll').exists() and not (output / 'Citrica.exe').exists()


@pytest.mark.parametrize('change', ['file_changed', 'file_missing', 'bad_hash', 'app_in_inventory',
                                    'provenance', 'source_lock', 'office_pin', 'ocr_pin', 'ocr_library',
                                    'source_zip_pin', 'inner_source', 'inner_lock', 'ffmpeg_recipe', 'cmake_recipe'])
def test_reuse_refuses_tampering_and_incompatible_builds(package, reuse, change):
    make, root, output, report = package
    kwargs = {}
    if change == 'file_changed':
        kwargs['mutate_files'] = lambda files: files.update({'tools/ffmpeg/bin/ffmpeg.exe': b'tampered'})
    elif change == 'file_missing':
        kwargs['mutate_files'] = lambda files: files.pop('tools/ffmpeg/bin/ffmpeg.exe')
    elif change == 'bad_hash':
        kwargs['inventory_change'] = lambda inventory: inventory.update({'engines.json': 'not-a-sha256'})
    elif change == 'app_in_inventory':
        kwargs['inventory_change'] = lambda inventory: inventory.update({'Qt6Core.dll': 'a' * 64})
    elif change in {'provenance', 'source_lock', 'office_pin', 'ocr_pin', 'ocr_library', 'source_zip_pin'}:
        key, value = {'provenance': ('provenance', 'vendor binaries'), 'source_lock': ('sources', {}),
            'office_pin': ('libreoffice', {}), 'ocr_pin': ('ocr_eng', {}),
            'ocr_library': ('ocr_library', '../old.dll'),
            'source_zip_pin': ('corresponding_source', {'file': 'engine-sources.zip', 'sha256': 'a' * 64})}[change]
        kwargs['mutate_manifest'] = lambda metadata: metadata.update({key: value})
    elif change == 'inner_source':
        kwargs['mutate_sources'] = lambda sources: sources.update({'downloads/sources/source.tar.gz': b'changed'})
    elif change == 'inner_lock':
        kwargs['mutate_sources'] = lambda sources: sources.update({'packaging/windows-sources.lock.json': b'{}'})
    elif change == 'ffmpeg_recipe':
        kwargs['mutate_sources'] = lambda sources: sources.update({reuse.RECIPES[0]: b'changed codec build'})
    else:
        name = reuse.RECIPES[1]
        kwargs['mutate_sources'] = lambda sources: sources.update({name: sources[name].replace(
            b'-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded', b'-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL')})
    with pytest.raises(ValueError):
        reuse.restore(make(**kwargs), output, report, root=root)
    assert not output.exists() and not report.exists()
    assert not list(output.parent.glob('citrica-reuse-*'))


@pytest.mark.parametrize('name', ['../outside.dll', '/absolute.dll', 'C:/drive.dll',
    'Citrica/_internal/../outside.dll', 'Citrica\\_internal\\outside.dll',
    'Citrica/_internal/tools/ocr:stream', 'Citrica/_internal/NUL.txt',
    'Citrica/_internal/name./test.dll', 'CITRICA/_INTERNAL/ENGINES.JSON'])
def test_reuse_rejects_zip_traversal_and_windows_aliases(package, reuse, name):
    make, root, output, report = package
    with pytest.raises(ValueError):
        reuse.restore(make(extra=(name, b'unsafe')), output, report, root=root)
    assert not output.exists()


def test_reuse_rejects_symlink_members(package, reuse):
    make, root, output, report = package
    link = zipfile.ZipInfo('Citrica/_internal/link')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match='Link/arquivo especial'):
        reuse.restore(make(extra=(link, b'../../outside')), output, report, root=root)
    assert not output.exists()


def test_reuse_never_merges_or_deletes_an_existing_runtime(package, reuse):
    make, root, output, report = package
    output.mkdir()
    marker = output / 'existing.txt'
    marker.write_text('keep me')
    with pytest.raises(ValueError, match='saída precisa ser nova'):
        reuse.restore(make(), output, report, root=root)
    assert marker.read_text() == 'keep me'
