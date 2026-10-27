"""Release signing policy and command wiring; no test certificate is trusted."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


_SCRIPT = Path(__file__).resolve().parents[1] / 'packaging/sign_windows.py'
_SPEC = importlib.util.spec_from_file_location('citrica_sign_windows', _SCRIPT)
signing = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = signing
_SPEC.loader.exec_module(signing)

THUMBPRINT = 'A1' * 20


def test_signing_configuration_is_explicit_and_never_fakes_trust():
    assert signing.SigningConfig.from_environment({}) is None
    with pytest.raises(ValueError, match='obrigatória'):
        signing.SigningConfig.from_environment({'CITRICA_SIGNING_REQUIRED': '1'})
    with pytest.raises(ValueError, match='hexadecimais'):
        signing.SigningConfig.from_environment({'CITRICA_SIGN_CERT_SHA1': 'fake'})
    with pytest.raises(ValueError, match='0 ou 1'):
        signing.SigningConfig.from_environment({'CITRICA_SIGNING_REQUIRED': 'yes'})
    with pytest.raises(ValueError, match='sem credenciais'):
        signing.SigningConfig.from_environment({'CITRICA_SIGN_CERT_SHA1': THUMBPRINT,
                                               'CITRICA_SIGN_TIMESTAMP_URL': 'https://user:secret@example.org'})
    config = signing.SigningConfig.from_environment({'CITRICA_SIGN_CERT_SHA1': 'a1 ' * 20,
                                                     'CITRICA_SIGN_MACHINE_STORE': '1'})
    assert config.thumbprint == THUMBPRINT and config.machine_store


def test_payload_selection_includes_native_dependencies_and_rejects_bad_inputs(tmp_path):
    (tmp_path / 'nested').mkdir()
    for filename in ['Citrica.exe', 'citrica-cli.exe', 'nested/library.DLL', 'nested/module.pyd', 'readme.md']:
        (tmp_path / filename).write_bytes(b'controlled fixture')
    assert len(signing.pe_files(tmp_path)) == 4
    with pytest.raises(ValueError, match='Nenhum'):
        signing._paths([])
    with pytest.raises(ValueError, match='existentes'):
        signing._paths([tmp_path / 'readme.md'])


def test_unsigned_payload_gets_pinned_certificate_sha256_timestamp_and_trust_check(tmp_path, monkeypatch):
    source = tmp_path / 'Cítrica com espaço.exe'
    source.write_bytes(b'controlled fixture')
    calls, states = [], iter([{'status': 'NotSigned'},
                             {'status': 'Valid', 'thumbprint': THUMBPRINT, 'timestamp_thumbprint': 'TSA'}])
    monkeypatch.setattr(signing, 'find_signtool', lambda configured=None: 'signtool.exe')
    monkeypatch.setattr(signing, 'inspect_signature', lambda path: next(states))
    monkeypatch.setattr(signing, '_run', lambda args, **kwargs: calls.append(args))
    receipts = signing.sign_files(signing.SigningConfig(THUMBPRINT, machine_store=True), [source])
    assert calls[0][0:4] == ['signtool.exe', 'sign', '/sha1', THUMBPRINT]
    assert calls[0][calls[0].index('/fd') + 1] == 'SHA256'
    assert calls[0][calls[0].index('/td') + 1] == 'SHA256'
    assert '/tr' in calls[0] and '/sm' in calls[0]
    assert '/p' not in calls[0] and '/f' not in calls[0]  # no passwords or exported keys
    assert calls[0][-1] == str(source)
    assert calls[1] == ['signtool.exe', 'verify', '/pa', '/all', '/tw', str(source)]
    assert receipts[0]['status'] == 'Valid' and not receipts[0]['preserved_vendor_signature']


def test_valid_vendor_signature_is_preserved_and_invalid_one_rejected(tmp_path, monkeypatch):
    source = tmp_path / 'vendor.dll'
    source.write_bytes(b'controlled fixture')
    calls = []
    monkeypatch.setattr(signing, 'find_signtool', lambda configured=None: 'signtool.exe')
    monkeypatch.setattr(signing, '_run', lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(signing, 'inspect_signature', lambda path: {'status': 'Valid', 'thumbprint': 'VENDOR',
                                                                   'timestamp_thumbprint': 'TSA'})
    assert signing.sign_files(signing.SigningConfig(THUMBPRINT), [source])[0]['preserved_vendor_signature']
    assert all(command[1] == 'verify' for command in calls)
    calls.clear()
    monkeypatch.setattr(signing, 'inspect_signature', lambda path: {'status': 'HashMismatch'})
    with pytest.raises(RuntimeError, match='rejeitado'):
        signing.sign_files(signing.SigningConfig(THUMBPRINT), [source])
    assert calls == []


def test_timestamp_and_selected_signing_identity_are_required(tmp_path, monkeypatch):
    source = tmp_path / 'Citrica.exe'
    source.write_bytes(b'controlled fixture')
    monkeypatch.setattr(signing, 'find_signtool', lambda configured=None: 'signtool.exe')
    monkeypatch.setattr(signing, '_run', lambda args, **kwargs: None)
    monkeypatch.setattr(signing, 'inspect_signature', lambda path: {'status': 'Valid', 'thumbprint': THUMBPRINT})
    with pytest.raises(RuntimeError, match='timestamp'):
        signing.verify_files([source])
    states = iter([{'status': 'NotSigned'},
                   {'status': 'Valid', 'thumbprint': 'WRONG', 'timestamp_thumbprint': 'TSA'}])
    monkeypatch.setattr(signing, 'inspect_signature', lambda path: next(states))
    with pytest.raises(RuntimeError, match='não corresponde'):
        signing.sign_files(signing.SigningConfig(THUMBPRINT), [source])


def test_inspection_passes_filename_as_environment_data(tmp_path, monkeypatch):
    source = tmp_path / "área $() 'arquivo.exe"
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, '\ufeff{"status":"NotSigned"}')
    monkeypatch.setattr(signing, '_run', run)
    assert signing.inspect_signature(source)['status'] == 'NotSigned'
    assert str(source) not in calls[0][0][-1]
    assert calls[0][1]['env']['CITRICA_SIGNING_FILE'] == str(source)
    assert '-ExecutionPolicy' not in calls[0][0]


def test_inno_signs_setup_and_uninstaller_with_same_checked_callback(tmp_path, monkeypatch):
    tool = tmp_path / 'Windows SDK' / 'signtool.exe'
    tool.parent.mkdir()
    tool.write_bytes(b'controlled fixture')
    for name in ['CITRICA_SIGN_CERT_SHA1', 'CITRICA_SIGN_TIMESTAMP_URL', 'CITRICA_SIGNTOOL',
                 'CITRICA_SIGN_MACHINE_STORE', 'CITRICA_SIGNING_REQUIRED']:
        monkeypatch.setenv(name, '')
    config = signing.SigningConfig(THUMBPRINT, signtool=str(tool))
    arguments = signing.inno_signing_arguments(config)
    assert arguments[0] == '/DSigningEnabled=1'
    assert arguments[1].startswith('/Scitrica=$q') and arguments[1].endswith('--sign $f')
    assert signing.SigningConfig.from_environment() == config
    script = (_SCRIPT.parent / 'windows.iss').read_text()
    assert '#ifdef SigningEnabled\nSignTool=citrica\nSignedUninstaller=yes' in script


def test_signtool_warnings_fail_build(monkeypatch):
    def run(args, **kwargs):
        assert kwargs['check'] and kwargs['timeout'] == 180
        raise subprocess.CalledProcessError(2, args, stderr='timestamp missing')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        signing._run(['signtool.exe', 'verify'])


def test_cli_does_not_claim_authenticode_verification_on_linux(monkeypatch):
    monkeypatch.setattr(signing.sys, 'platform', 'linux')
    with pytest.raises(SystemExit) as error:
        signing.main(['--verify', 'Citrica.exe'])
    assert error.value.code == 2


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows Authenticode and PowerShell')
def test_real_windows_authenticode_inspection_and_tamper_detection(tmp_path):
    # Do not install a root certificate or trust anything for this test. Official
    # python.org CPython may already be signed; embeddable/custom builds may not.
    source = tmp_path / 'assinatura com espaços e ação.exe'
    shutil.copy2(sys.executable, source)
    original = signing.inspect_signature(source)
    assert original['status'] in {'Valid', 'NotSigned'}
    if original['status'] == 'Valid':
        assert original['thumbprint'] and original['subject']
        content = bytearray(source.read_bytes())
        content[64] ^= 1  # change a byte in the hashed DOS stub, without executing
        source.write_bytes(content)
        assert signing.inspect_signature(source)['status'] == 'HashMismatch'
    else:
        assert original['thumbprint'] is None
