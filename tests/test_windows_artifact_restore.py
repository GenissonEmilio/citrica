import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def restorer(monkeypatch):
    folder = Path(__file__).resolve().parents[1] / 'packaging'
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location('artifact_restore', folder / 'restore_windows_qa_artifact.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def candidate(tmp_path):
    root, release = tmp_path / 'repo', tmp_path / 'artifact/release'
    release.mkdir(parents=True)
    (root / 'release').mkdir(parents=True)
    origin = root / 'release/citrica-windows-existing-build-origin.json'
    origin.write_text(json.dumps({'app_commit': 'a' * 40, 'artifact_name': 'citrica-windows-repack-unsigned-test'}))
    sources = b'exact corresponding source ZIP fixture'
    source_pin = hashlib.sha256(sources).hexdigest()
    metadata = {'provenance': 'compiled-from-pinned-sources', 'corresponding_source': {'sha256': source_pin}}
    reports = {
        'citrica-windows-validation.json': {'validation': {'packaged_engine_smoke': True,
            'conversion_matrix': 'citrica-windows-engine-parity.json', 'offline_engines': metadata}},
        'citrica-windows-engine-parity.json': {'conversions': 304, 'cases': [{'success': True}] * 304,
            'media_tools': [{'success': True}] * 23, 'originals_preserved': True, 'ocr_redaction': True},
        'citrica-windows-static-tools-parity.json': {'success': True, 'operations': 38,
            'cases': [{'success': True}] * 38, 'originals_preserved': True},
        'citrica-windows-signing.json': {'status': 'unsigned', 'authenticode_verified': False}}
    setup_name = 'citrica-0.6.0-windows-x86_64-setup-unsigned-test.exe'
    portable_name = 'citrica-0.6.0-windows-x86_64-portable-unsigned-test.zip'

    def make(*, report_change=None, zip_extra=None, payload_change=None, after_checksum=None):
        report_data = json.loads(json.dumps(reports))
        if report_change:
            report_change(report_data)
        for name, data in report_data.items():
            (release / name).write_text(json.dumps(data), encoding='utf-8')
        (release / setup_name).write_bytes(b'exact setup PE fixture')
        files = {'Citrica/Citrica.exe': b'exact GUI PE fixture', 'Citrica/citrica-cli.exe': b'exact CLI PE fixture',
                 'Citrica/_internal/engines.json': json.dumps(metadata).encode(),
                 'Citrica/_internal/engine-sources.zip': sources, 'Citrica/_internal/Qt6Core.dll': b'exact Qt fixture'}
        if payload_change:
            payload_change(files)
        with zipfile.ZipFile(release / portable_name, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            if zip_extra:
                raw = zipfile.ZipInfo('placeholder')
                raw.filename = raw.orig_filename = zip_extra
                archive.writestr(raw, b'unsafe fixture')
        (release / 'SHA256SUMS-windows.txt').write_text(''.join(
            f'{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.name}\n'
            for file in sorted(release.iterdir()) if file.name != 'SHA256SUMS-windows.txt'), encoding='utf-8')
        if after_checksum:
            after_checksum(release)
        return release.parent
    return make, root, origin, release


def test_restore_retests_exact_existing_pes_without_build_or_new_matrix(candidate, restorer):
    make, root, origin, release = candidate
    result = restorer.restore(make(), root=root, origin_path=origin)
    assert (root / 'dist/Citrica/Citrica.exe').read_bytes() == b'exact GUI PE fixture'
    assert (root / 'dist/Citrica/citrica-cli.exe').read_bytes() == b'exact CLI PE fixture'
    assert (root / 'build/existing-setup.exe').read_bytes() == b'exact setup PE fixture'
    assert result['restored'] and result['recompiled'] is False and result['new_full_matrix_executed'] is False
    assert result['app_commit'] == 'a' * 40 and result['gui_sha256'] and result['cli_sha256']
    assert result['prior_full_build']['prior_conversions'] == 304
    assert result['prior_full_build']['all_prior_cases_passed']
    assert (root / 'release/prior-build/citrica-windows-engine-parity.json').is_file()


@pytest.mark.parametrize('filename', ['citrica-0.6.0-windows-x86_64-setup-unsigned-test.exe',
    'citrica-0.6.0-windows-x86_64-portable-unsigned-test.zip', 'citrica-windows-engine-parity.json'])
def test_restore_never_accepts_modified_executable_archive_or_prior_evidence(candidate, restorer, filename):
    make, root, origin, release = candidate
    directory = make(after_checksum=lambda folder: (folder / filename).write_bytes(b'changed after inventory'))
    with pytest.raises(ValueError, match='SHA-256'):
        restorer.restore(directory, root=root, origin_path=origin)
    assert not (root / 'dist/Citrica').exists() and not (root / 'build/existing-setup.exe').exists()


@pytest.mark.parametrize('change', ['short_matrix', 'failed_conversion', 'failed_media', 'failed_static', 'ui_only', 'signed'])
def test_restore_requires_all_prior_full_build_checks_to_pass(candidate, restorer, change):
    make, root, origin, release = candidate

    def mutate(reports):
        matrix = reports['citrica-windows-engine-parity.json']
        if change == 'short_matrix':
            matrix['conversions'] = 0
        elif change == 'failed_conversion':
            matrix['cases'][0]['success'] = False
        elif change == 'failed_media':
            matrix['media_tools'][0]['success'] = False
        elif change == 'failed_static':
            reports['citrica-windows-static-tools-parity.json']['cases'][0]['success'] = False
        elif change == 'ui_only':
            reports['citrica-windows-validation.json']['validation']['ui_qa_only'] = True
        else:
            reports['citrica-windows-signing.json']['status'] = 'signed'
    with pytest.raises(ValueError):
        restorer.restore(make(report_change=mutate), root=root, origin_path=origin)
    assert not (root / 'dist/Citrica').exists()


@pytest.mark.parametrize('name', ['../outside.exe', 'Citrica/../outside.exe', 'Citrica\\outside.exe',
                                'Citrica/_internal/CON.dll', '/absolute.exe', 'other/app.exe'])
def test_restore_rejects_traversal_windows_aliases_and_files_outside_payload(candidate, restorer, name):
    make, root, origin, release = candidate
    with pytest.raises(ValueError):
        restorer.restore(make(zip_extra=name), root=root, origin_path=origin)
    assert not (root / 'dist/Citrica').exists()


@pytest.mark.parametrize('name', ['Citrica/Citrica.exe', 'Citrica/citrica-cli.exe',
                                'Citrica/_internal/engine-sources.zip'])
def test_restore_requires_both_pes_and_corresponding_source(candidate, restorer, name):
    make, root, origin, release = candidate
    with pytest.raises(ValueError):
        restorer.restore(make(payload_change=lambda files: files.pop(name)), root=root, origin_path=origin)
    assert not (root / 'dist/Citrica').exists()
