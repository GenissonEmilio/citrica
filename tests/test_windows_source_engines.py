import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def source_builder(monkeypatch):
    folder = Path(__file__).parents[1] / 'packaging'
    spec = importlib.util.spec_from_file_location('prepare_windows_engines', folder / 'prepare_windows_engines.py')
    dependency = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dependency)
    monkeypatch.setitem(sys.modules, 'prepare_windows_engines', dependency)
    spec = importlib.util.spec_from_file_location('windows_source_builder', folder / 'build_windows_source_engines.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def packaged_office(tmp_path):
    office = tmp_path / 'tools/libreoffice'
    inventory = {}
    for relative, content in [('program/soffice.com', b'office fixture'),
                              ('program/msvcp140.dll', b'x64 CRT fixture'),
                              ('LICENSE', b'original notice fixture')]:
        file = office / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
        inventory[f'tools/libreoffice/{relative}'] = hashlib.sha256(content).hexdigest()
    pinned = {'version': '26.2.6', 'sha256': 'a' * 64}
    (tmp_path / 'engines.json').write_text(json.dumps({'libreoffice': pinned}), encoding='utf-8')
    (tmp_path / 'engine-files.sha256.json').write_text(json.dumps(inventory), encoding='utf-8')
    return office, pinned


def test_office_reuse_requires_same_pin_and_intact_tree(source_builder, packaged_office):
    office, pinned = packaged_office
    assert source_builder.verified_office_reuse(office, pinned) == office.resolve()
    with pytest.raises(RuntimeError, match='versão LibreOffice diferente'):
        source_builder.verified_office_reuse(office, pinned | {'sha256': 'b' * 64})
    with pytest.raises(RuntimeError, match='versão LibreOffice diferente'):
        source_builder.verified_office_reuse(office, pinned | {'version': 'older version'})
    (office / 'program/msvcp140.dll').write_bytes(b'changed CRT')
    with pytest.raises(RuntimeError, match='SHA-256 diferente'):
        source_builder.verified_office_reuse(office, pinned)


@pytest.mark.parametrize('change', ['extra', 'missing', 'missing_manifest', 'invalid_inventory'])
def test_office_reuse_refuses_partial_or_modified_package(source_builder, packaged_office, change):
    office, pinned = packaged_office
    package = office.parent.parent
    if change == 'extra':
        (office / 'program/unexpected.dll').write_bytes(b'not part of the original package')
    elif change == 'missing':
        (office / 'LICENSE').unlink()
    elif change == 'missing_manifest':
        (package / 'engines.json').unlink()
    else:
        (package / 'engine-files.sha256.json').write_text('[]', encoding='utf-8')
    with pytest.raises(RuntimeError):
        source_builder.verified_office_reuse(office, pinned)


def test_office_reuse_is_checked_before_destructive_build_cleanup(source_builder, packaged_office, monkeypatch):
    office, pinned = packaged_office
    package = office.parent.parent
    vendors = package / 'vendor-lock.json'
    vendors.write_text(json.dumps({'libreoffice': pinned}), encoding='utf-8')
    monkeypatch.setattr(source_builder, 'VENDOR_LOCK', vendors)
    monkeypatch.setattr(source_builder, 'sys', SimpleNamespace(platform='win32'))
    with pytest.raises(RuntimeError, match='fora das pastas de saída e trabalho'):
        source_builder.prepare(output=package, cache=package / 'cache', work=package / 'work', office_from=office)
    assert (office / 'program/soffice.com').is_file()
    assert (package / 'engines.json').is_file()
