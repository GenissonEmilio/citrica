"""Authenticode signing using a Windows certificate store / HSM provider.

No private key or password is read by this script. A CA-issued code-signing
certificate must already be available to SignTool on the build machine.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Mapping, Sequence
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SigningConfig:
    thumbprint: str
    timestamp_url: str = 'http://timestamp.digicert.com'
    signtool: str | None = None
    machine_store: bool = False

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None):
        env = os.environ if environ is None else environ
        thumbprint = re.sub(r'\s+', '', env.get('CITRICA_SIGN_CERT_SHA1', '')).upper()
        required = env.get('CITRICA_SIGNING_REQUIRED', '0')
        machine = env.get('CITRICA_SIGN_MACHINE_STORE', '0')
        if required not in {'0', '1'} or machine not in {'0', '1'}:
            raise ValueError('CITRICA_SIGNING_REQUIRED e CITRICA_SIGN_MACHINE_STORE devem ser 0 ou 1.')
        if not thumbprint:
            if required == '1':
                raise ValueError('Assinatura obrigatória: configure CITRICA_SIGN_CERT_SHA1.')
            return None
        if not re.fullmatch('[0-9A-F]{40}', thumbprint):
            raise ValueError('CITRICA_SIGN_CERT_SHA1 deve identificar um certificado por 40 dígitos hexadecimais.')
        timestamp = env.get('CITRICA_SIGN_TIMESTAMP_URL', cls.timestamp_url)
        url = urlsplit(timestamp)
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError('CITRICA_SIGN_TIMESTAMP_URL deve ser um servidor RFC 3161 HTTP(S), sem credenciais.')
        return cls(thumbprint, timestamp, env.get('CITRICA_SIGNTOOL') or None, machine == '1')


def find_signtool(configured: str | None = None) -> str:
    if configured:
        path = Path(configured)
        if not path.is_file():
            raise RuntimeError('CITRICA_SIGNTOOL não aponta para um arquivo existente.')
        return str(path.resolve())
    on_path = shutil.which('signtool.exe')
    if on_path:
        return on_path
    kits = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Windows Kits/10/bin'
    candidates = list(kits.glob('*/x64/signtool.exe'))
    if candidates:
        return str(max(candidates, key=lambda p: tuple(int(n) for n in p.parent.parent.name.split('.'))))
    raise RuntimeError('SignTool não encontrado. Instale o Windows SDK ou configure CITRICA_SIGNTOOL.')


def pe_files(payload: Path) -> list[Path]:
    if not payload.is_dir():
        raise ValueError('A pasta do pacote Windows não existe.')
    return sorted(p for p in payload.rglob('*') if p.is_file() and p.suffix.lower() in {'.exe', '.dll', '.pyd'})


def _inno_uninstaller(path: Path) -> bool:
    """Inno invokes SignTool on these PE temporaries before embedding them."""
    if path.name.lower() not in {'uninst.e32.tmp', 'uninst.e64.tmp'}:
        return False
    try:
        size = path.stat().st_size
        with path.open('rb') as content:
            dos = content.read(64)
            if len(dos) != 64 or dos[:2] != b'MZ':
                return False
            offset = int.from_bytes(dos[60:64], 'little')
            # Bound both the DOS stub and the complete PE signature/COFF header.
            if offset < 64 or offset > 1024 * 1024 or offset + 24 > size:
                return False
            content.seek(offset)
            return content.read(4) == b'PE\x00\x00'
    except OSError:
        return False


def _paths(paths: Sequence[Path]) -> list[Path]:
    result = list(dict.fromkeys(Path(path).resolve() for path in paths))
    if not result:
        raise ValueError('Nenhum executável ou biblioteca foi indicado para assinatura.')
    if any(not path.is_file() or (path.suffix.lower() not in {'.exe', '.dll', '.pyd'} and
                                 not _inno_uninstaller(path)) for path in result):
        raise ValueError('Assinatura aceita apenas arquivos existentes .exe/.dll/.pyd '
                         'ou os temporários PE oficiais do desinstalador Inno Setup.')
    return result


def _run(args, **kwargs):
    # SignTool code 2 is a warning (including absent timestamps), not success.
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=180, **kwargs)
    except subprocess.CalledProcessError as error:
        # CalledProcessError.__str__ omits captured streams. Preserve the actual
        # PowerShell / signing error in CI, without dumping the environment.
        print(f'Falha no comando de assinatura/verificação (código {error.returncode}).\n'
              f'stdout:\n{error.stdout or ""}\nstderr:\n{error.stderr or ""}', file=sys.stderr)
        raise


_INSPECT = r'''
$ErrorActionPreference = 'Stop'
foreach ($name in @('Microsoft.PowerShell.Utility', 'Microsoft.PowerShell.Security')) {
    $manifest = [IO.Path]::Combine($PSHOME, 'Modules', $name, $name + '.psd1')
    try {
        Import-Module -Name $manifest -ErrorAction Stop
    } catch {
        throw ('Falha ao importar módulo nativo ' + $manifest + ': ' + $_.Exception.ToString())
    }
}
$s = Microsoft.PowerShell.Security\Get-AuthenticodeSignature -LiteralPath $env:CITRICA_SIGNING_FILE
$result = @{ status = $s.Status.ToString(); subject = $null; thumbprint = $null;
             timestamp_subject = $null; timestamp_thumbprint = $null }
if ($null -ne $s.SignerCertificate) {
    $result.subject = $s.SignerCertificate.Subject
    $result.thumbprint = $s.SignerCertificate.Thumbprint
}
if ($null -ne $s.TimeStamperCertificate) {
    $result.timestamp_subject = $s.TimeStamperCertificate.Subject
    $result.timestamp_thumbprint = $s.TimeStamperCertificate.Thumbprint
}
$json = $result | ConvertTo-Json -Compress
Write-Output ([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
'''


def inspect_signature(path: Path) -> dict:
    # Windows PowerShell's redirected output uses the active code page. An ASCII
    # envelope keeps Unicode certificate names intact without touching console
    # handles (which need not exist for GUI/CREATE_NO_WINDOW processes).
    # pwsh 7 -> Python -> Windows PowerShell 5.1 otherwise inherits PS7 module
    # locations and tries to autoload incompatible Security/Utility assemblies.
    # Sanitize this child only, as documented by Microsoft's about_PSModulePath.
    env = {key: value for key, value in os.environ.items() if key.upper() != 'PSMODULEPATH'}
    env['CITRICA_SIGNING_FILE'] = str(path.resolve())
    windows = Path(env.get('SystemRoot', r'C:\Windows'))
    powershell = windows / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    response = _run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', _INSPECT],
                    env=env,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        encoded = response.stdout.strip().lstrip('\ufeff')
        result = json.loads(base64.b64decode(encoded, validate=True).decode('utf-8'))
    except (ValueError, UnicodeError) as error:
        raise RuntimeError('Resposta Authenticode inválida.\n'
                           f'stdout:\n{response.stdout}\nstderr:\n{response.stderr or ""}') from error
    if not isinstance(result, dict) or not isinstance(result.get('status'), str):
        raise RuntimeError('A verificação Authenticode não retornou um resultado válido.')
    return result


def verify_files(paths: Sequence[Path], *, signtool: str | None = None) -> list[dict]:
    tool = find_signtool(signtool)
    receipts = []
    for path in _paths(paths):
        _run([tool, 'verify', '/pa', '/all', '/tw', str(path)])
        signature = inspect_signature(path)
        if signature['status'] != 'Valid' or not signature.get('timestamp_thumbprint'):
            raise RuntimeError(f'Assinatura confiável com timestamp ausente ou inválida: {path.name}')
        with path.open('rb') as content:
            digest = hashlib.file_digest(content, 'sha256').hexdigest()
        receipts.append({'file': str(path), 'sha256': digest, **signature})
    return receipts


def sign_files(config: SigningConfig, paths: Sequence[Path]) -> list[dict]:
    """Sign unsigned files, preserve valid vendor signatures, reject invalid ones.

    Trusted third-party DLL signatures are retained. Unknown/invalid existing
    signatures fail the build, rather than hiding possible tampering by re-signing.
    """
    tool = find_signtool(config.signtool)
    receipts = []
    for path in _paths(paths):
        before = inspect_signature(path)
        if before['status'] == 'NotSigned':
            args = [tool, 'sign', '/sha1', config.thumbprint, '/s', 'My', '/fd', 'SHA256',
                    '/tr', config.timestamp_url, '/td', 'SHA256', '/d', 'Cítrica',
                    '/du', 'https://github.com/GenissonEmilio/citrica']
            if config.machine_store:
                args.append('/sm')
            _run([*args, str(path)])
        elif before['status'] != 'Valid':
            raise RuntimeError(f'Assinatura existente inválida; pacote rejeitado: {path.name}')
        verified = verify_files([path], signtool=tool)[0]
        if before['status'] == 'NotSigned' and str(verified.get('thumbprint') or '').upper() != config.thumbprint:
            raise RuntimeError(f'O certificado aplicado não corresponde ao configurado: {path.name}')
        receipts.append({**verified, 'preserved_vendor_signature': before['status'] == 'Valid'})
    return receipts


def inno_signing_arguments(config: SigningConfig) -> list[str]:
    """Configure Inno's signing callback for Setup and the embedded uninstaller.

    The child inherits only public certificate-selection settings. Inno replaces
    $f with its quoted path; $q is Inno's documented command-line quote escape.
    """
    def quote(value):
        value = str(value)
        if any(character in value for character in ['$', '"', '\n', '\r']):
            raise ValueError('O caminho de assinatura contém caracteres incompatíveis com Inno Setup.')
        return f'$q{value}$q'

    tool = find_signtool(config.signtool)
    # Carry every selection setting through the environment into Inno's callback.
    os.environ['CITRICA_SIGN_CERT_SHA1'] = config.thumbprint
    os.environ['CITRICA_SIGN_TIMESTAMP_URL'] = config.timestamp_url
    os.environ['CITRICA_SIGNTOOL'] = tool
    os.environ['CITRICA_SIGN_MACHINE_STORE'] = '1' if config.machine_store else '0'
    os.environ['CITRICA_SIGNING_REQUIRED'] = '1'
    callback = f'{quote(sys.executable)} {quote(Path(__file__).resolve())} --sign $f'
    return ['/DSigningEnabled=1', f'/Scitrica={callback}']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--sign', action='store_true')
    mode.add_argument('--verify', action='store_true')
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('files', nargs='*', type=Path)
    options = parser.parse_args(argv)
    if sys.platform != 'win32':
        parser.error('A assinatura e a validação de confiança Authenticode exigem Windows.')
    paths = options.files + (pe_files(options.payload) if options.payload else [])
    if options.sign:
        config = SigningConfig.from_environment()
        if config is None:
            parser.error('Configure CITRICA_SIGN_CERT_SHA1 com um certificado confiável disponível no Windows.')
        receipts = sign_files(config, paths)
    else:
        receipts = verify_files(paths, signtool=os.environ.get('CITRICA_SIGNTOOL'))
    report = {'authenticode_verified': True, 'timestamp_required': True, 'files': receipts,
              'smartscreen_reputation_verified': False}
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if options.report:
        options.report.write_text(serialized, encoding='utf-8')
    else:
        print(serialized, end='')


if __name__ == '__main__':
    main()
