"""Store/unsigned-QA identity and immutable-input boundaries; no MSIX claims on Linux."""
import importlib.util
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def builder():
    spec = importlib.util.spec_from_file_location('msix_builder', ROOT / 'packaging/build_msix.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pe(machine=0x8664):
    header = bytearray(64)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 60, 64)
    return header + b'PE\0\0' + struct.pack('<H', machine)


@pytest.fixture
def payload(tmp_path, builder):
    path = tmp_path / 'PyInstaller Aplicação João'
    files = {name: b'public runtime fixture' for name in builder.REQUIRED}
    files |= {f'_internal/PySide6/{library}.dll': pe()
              for library in ['Qt6Core', 'Qt6Gui', 'Qt6Widgets', 'Qt6Network']}
    files |= {'_internal/python312.dll': pe(), '_internal/PySide6/plugins/platforms/qwindows.dll': pe()}
    files['_internal/engines.json'] = json.dumps({'provenance': 'compiled-from-pinned-sources'}).encode()
    for name in files:
        if name.endswith(('.exe', '.com')):
            files[name] = pe()
    for name, data in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    inventory = {name.removeprefix('_internal/'): builder.digest(path / name)
                 for name in builder.REQUIRED if name.startswith('_internal/')
                 and not name.endswith('engine-files.sha256.json')}
    (path / '_internal/engine-files.sha256.json').write_text(json.dumps(inventory))
    return path


def test_public_identity_and_qa_are_separate_without_secret_fields(builder):
    identity = builder.load_identity(builder.IDENTITY)
    assert identity['name'] == 'Emilians.Ctrica' and identity['store_version'] == '1.6.0.0'
    assert identity['package_family_name'] == 'Emilians.Ctrica_dtz50gxq3qxna'
    qa = builder.variant_identity(identity, 'qa')
    assert qa['name'] != identity['name'] and qa['name'].endswith('.UnsignedQA')
    assert qa['publisher'] == identity['publisher'] + ', ' + builder.UNSIGNED_OID
    assert qa['package_family_name'] is None and 'QA unsigned' in qa['display_name']
    assert builder.UNSIGNED_OID not in identity['publisher']


@pytest.mark.parametrize('key,value', [
    ('store_version', '0.6.0.0'), ('store_version', '1.6.0.1'), ('store_version', '1.06.0.0'),
    ('store_version', '1.65536.0.0'), ('publisher', 'CN=Test, OID.bad=1'),
    ('min_os_version', '10.0.18362.0'), ('startup_task_id', 'AnotherTask'),
    ('architecture', 'arm64'), ('certificate_password', 'must never be accepted'),
])
def test_identity_rejects_invalid_versions_publishers_and_private_fields(builder, tmp_path, key, value):
    data = json.loads(builder.IDENTITY.read_text())
    data[key] = value
    path = tmp_path / 'identity.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        builder.load_identity(path)


@pytest.mark.parametrize('mode', ['store', 'qa'])
def test_manifest_uses_full_trust_startup_and_safe_xml(builder, mode):
    data = builder.load_identity(builder.IDENTITY)
    data['display_name'] = 'Cítrica & <conversão>'
    tree = builder.manifest(data, mode)
    raw = ET.tostring(tree.getroot())
    assert b'&amp;' in raw and b'&lt;convers' in raw
    root = ET.fromstring(raw)
    namespaces = dict(builder.NS, f=builder.NS[''])
    app = root.find('f:Applications/f:Application', namespaces)
    assert app.get('Executable') == r'Citrica\Citrica.exe'
    assert app.get('{' + builder.NS['uap10'] + '}RuntimeBehavior') == 'packagedClassicApp'
    assert app.get('{' + builder.NS['uap10'] + '}TrustLevel') == 'mediumIL'
    assert app.get('EntryPoint') is None, 'Modern activation attributes do not need a redundant legacy entry point'
    startup = app.find('f:Extensions/desktop:Extension', namespaces)
    assert startup.get('Category') == 'windows.startupTask'
    assert startup.get('Executable') is None, 'StartupTask must inherit the modern application activation'
    assert startup.get('{' + builder.NS['uap10'] + '}Parameters') == '--background'
    task = startup.find('desktop:StartupTask', namespaces)
    assert task.attrib == {'TaskId': 'CitricaStartup', 'Enabled': 'false',
                           'DisplayName': builder.variant_identity(data, mode)['display_name']}
    capabilities = root.findall('f:Capabilities/rescap:Capability', namespaces)
    assert [item.get('Name') for item in capabilities] == ['runFullTrust']
    assert [item.get('Language') for item in root.findall('f:Resources/f:Resource', namespaces)] == ['pt-br']
    assert [element.tag.rsplit('}', 1)[-1] for element in root] == [
        'Identity', 'Properties', 'Dependencies', 'Resources', 'Applications', 'Capabilities']


def test_stage_only_copies_complete_payload_without_modifying_it(builder, payload, tmp_path, monkeypatch):
    original = builder.snapshot(payload)
    monkeypatch.setattr(builder, 'makeappx_path', lambda *a: pytest.fail('Stage-only invoked a compiler'))
    monkeypatch.setattr(builder, 'logos', lambda path: path.mkdir())
    staging, output = tmp_path / 'new staging', tmp_path / 'new output'
    report = builder.build(payload, staging, output, stage_only=True)
    assert builder.snapshot(payload) == original and report['input_payload_unchanged_verified']
    assert report['result'] == 'staged-only-not-msix-validated' and not report['makeappx_ran']
    assert not list(output.glob('*.msix'))
    assert [item['store_identity'] for item in report['variants']] == [True, False]
    for stage in staging.iterdir():
        assert builder.snapshot(stage / 'Citrica') == original
    for entry in report['variants']:
        assert not entry['store_submission_candidate'] and not entry['signed'] and not entry['vm_validated']


@pytest.mark.parametrize('kind', ['existing', 'inside', 'ancestor', 'overlap'])
def test_never_overwrites_or_nests_output_in_payload(builder, payload, tmp_path, kind):
    staging, output = tmp_path / 'staging', tmp_path / 'output'
    if kind == 'existing':
        staging.mkdir()
    elif kind == 'inside':
        staging = payload / 'staging'
    elif kind == 'ancestor':
        output = payload.parent
    else:
        output = staging / 'output'
    with pytest.raises(ValueError):
        builder.output_paths(payload, staging, output)
    assert (payload / 'Citrica.exe').read_bytes() == pe()


def test_rejects_payload_symlinks(builder, payload):
    link = payload / 'linked.exe'
    try:
        link.symlink_to(payload / 'Citrica.exe')
    except OSError as error:
        pytest.skip(f'This Windows user cannot create a symlink: {error}')
    with pytest.raises(ValueError, match='links/reparse'):
        builder.snapshot(payload)


def test_rejects_dangling_output_symlink(builder, payload, tmp_path):
    link = tmp_path / 'stage-link'
    try:
        link.symlink_to(tmp_path / 'does-not-exist', target_is_directory=True)
    except OSError as error:
        pytest.skip(f'This Windows user cannot create a symlink: {error}')
    with pytest.raises(ValueError, match='endpoints'):
        builder.output_paths(payload, link, tmp_path / 'output')
    assert not (tmp_path / 'does-not-exist').exists()


def test_rejects_windows_case_collisions(builder, payload):
    # A Linux staging host must reject names that collide on Windows.
    collision = payload / 'CITRICA.EXE'
    collision.write_bytes(pe())
    if collision.samefile(payload / 'Citrica.exe'):
        pytest.skip('The filesystem is already case-insensitive')
    with pytest.raises(ValueError, match='collision'):
        builder.snapshot(payload)


def test_rejects_private_keys(builder, payload):
    (payload / 'private.pem').write_text('-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----')
    with pytest.raises(ValueError, match='Private key'):
        builder.snapshot(payload)


def test_rejects_missing_adapter_wrong_architecture_and_tampered_engine(builder, payload):
    helper = payload / 'citrica-package.exe'
    helper.unlink()
    with pytest.raises(ValueError, match='Incomplete'):
        builder.validate_payload(payload, builder.snapshot(payload))
    helper.write_bytes(pe(0x14c))
    with pytest.raises(ValueError, match='x64'):
        builder.validate_payload(payload, builder.snapshot(payload))
    helper.write_bytes(pe())
    (payload / '_internal/ocr/tessdata/eng.traineddata').write_bytes(b'tampered model')
    with pytest.raises(ValueError, match='SHA-256'):
        builder.validate_payload(payload, builder.snapshot(payload))


def test_makeappx_command_validates_both_variants_and_keeps_reports_honest(builder, payload, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(builder, 'makeappx_path', lambda explicit: Path('official-sdk/makeappx.exe'))
    monkeypatch.setattr(builder, 'logos', lambda path: path.mkdir())
    def run(command, **options):
        calls.append(command)
        assert command[1] == 'pack' and '/v' in command and '/nv' not in command and '/o' not in command
        Path(command[command.index('/p') + 1]).write_bytes(b'fixture MSIX; no actual compilation in this unit test')
        return SimpleNamespace(returncode=0, stdout='MakeAppx fixture', stderr='')
    monkeypatch.setattr(builder.subprocess, 'run', run)
    report = builder.build(payload, tmp_path / 'stage', tmp_path / 'output')
    assert len(calls) == 2 and report['makeappx_ran']
    assert report['result'] == 'packaged-not-vm-validated'
    assert [item['store_submission_candidate'] for item in report['variants']] == [True, False]
    assert all(not item['vm_validated'] and not item['store_certified'] for item in report['variants'])
    assert 'NOT-FOR-STORE' in report['variants'][1]['package']


def test_makeappx_failure_is_not_reported_as_a_package_success(builder, payload, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, 'makeappx_path', lambda explicit: Path('sdk/makeappx.exe'))
    monkeypatch.setattr(builder, 'logos', lambda path: path.mkdir())
    monkeypatch.setattr(builder.subprocess, 'run', lambda *a, **kw:
                        SimpleNamespace(returncode=7, stdout='', stderr='schema error'))
    with pytest.raises(RuntimeError, match='MakeAppx failed'):
        builder.build(payload, tmp_path / 'stage', tmp_path / 'output', mode='store')
    report = json.loads((tmp_path / 'output/build-report.json').read_text())
    assert report['result'] == 'failed' and report['variants'][0]['makeappx_validation'] == 'failed'
    assert report['variants'][0]['makeappx_returncode'] == 7
    assert report['variants'][0]['makeappx_log'].endswith('.makeappx.log')
    assert 'schema error' in next((tmp_path / 'output').glob('*.makeappx.log')).read_text()


def test_qt_logos_are_real_pngs_from_the_original_svg(builder, tmp_path):
    from PIL import Image
    builder.logos(tmp_path / 'Assets')
    for name, size in [('StoreLogo', 50), ('Square44x44Logo', 44), ('Square150x150Logo', 150)]:
        with Image.open(tmp_path / f'Assets/{name}.png') as image:
            assert image.size == (size, size) and image.format == 'PNG'
            assert image.getbbox() is not None
