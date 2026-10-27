"""Prepare pinned offline Windows engines. Downloads happen only at build time.

The final application uses ordinary sibling executables/DLLs, does not modify
PATH or register Office, and never runs another installer on the user's PC.
Run on Windows: python packaging/prepare_windows_engines.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import struct
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = Path(__file__).with_name('windows-engines.lock.json')
DEFAULT_OUTPUT = ROOT / 'build/windows-engines'
DEFAULT_CACHE = ROOT / 'build/windows-engine-cache'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(entry, cache):
    """Reuse only verified artifacts, and reject incomplete/replaced downloads."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    name = Path(urllib.parse.urlsplit(entry['url']).path).name
    target = cache / name
    if target.is_file() and digest(target) == entry['sha256']:
        return target
    temporary = target.with_name(target.name + '.part')
    urls = [entry['url']]
    if entry.get('fallback_url'):
        urls.append(entry['fallback_url'])
    last_error = None
    for url in urls:
        if urllib.parse.urlsplit(url).scheme != 'https':
            raise ValueError('A origem dos motores precisa usar HTTPS.')
        try:
            print(f"Baixando motor para o build: {name}", flush=True)
            request = urllib.request.Request(url, headers={'User-Agent': 'Citrica-build/1'})
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open('wb') as output:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 1024**3:
                        raise ValueError('Download do motor ultrapassou 1 GiB.')
                    output.write(chunk)
            actual = digest(temporary)
            if actual != entry['sha256']:
                raise ValueError(f"SHA-256 inválido para {name}: {actual}")
            temporary.replace(target)
            return target
        except (urllib.error.URLError, OSError) as error:
            last_error = error
        finally:
            temporary.unlink(missing_ok=True)
    raise RuntimeError(f'Não foi possível baixar {name}: {last_error}') from last_error


def extract_zip(archive, destination):
    # This archive is checksum-pinned, but the extraction boundary stays explicit
    # so an accidental lock update cannot write outside the staging directory.
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            parts = Path(item.filename.replace('\\', '/')).parts
            if not parts or item.filename.startswith(('/', '\\')) or '..' in parts or ':' in item.filename:
                raise ValueError('Caminho inseguro no motor compactado.')
        source.extractall(destination)


def seven_zip():
    found = shutil.which('7z') or shutil.which('7zz')
    standard = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / '7-Zip/7z.exe'
    if found:
        return found
    if standard.is_file():
        return str(standard)
    raise RuntimeError('Instale 7-Zip no ambiente de build para extrair o Tesseract, sem executar seu instalador.')


def require_file(path):
    if not path.is_file():
        raise RuntimeError(f'Motor incompleto: {path}')


def extract_office(archive, destination, log):
    subprocess.run(['msiexec.exe', '/a', str(archive), '/qn', '/norestart',
                    f'TARGETDIR={destination}', '/l*v', str(log)], check=True, timeout=600)
    office = list(Path(destination).glob('**/program/soffice.exe'))
    if len(office) != 1:
        raise RuntimeError(f'Extração LibreOffice inesperada; consulte {log}.')
    require_file(office[0].parent / 'soffice.com')
    preserve_office_crt(office[0].parent, Path(destination))
    return office[0].parent.parent


def preserve_office_crt(program_folder, extraction):
    """Keep x64 CRT merge-module files from this same MSI beside soffice.

    An administrative MSI image may place VC runtime files outside the Office
    folder. A regular installation registers those globally, while our offline
    engine must work without that system mutation or a preinstalled VC redist.
    """
    for name in ['vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll', 'msvcp140_1.dll',
                 'msvcp140_2.dll', 'msvcp140_atomic_wait.dll', 'msvcp140_codecvt_ids.dll', 'concrt140.dll']:
        if (program_folder / name).is_file():
            continue
        candidates = []
        for file in extraction.rglob(name):
            with file.open('rb') as stream:
                header = stream.read(64)
                if len(header) != 64 or header[:2] != b'MZ':
                    continue
                offset = struct.unpack_from('<I', header, 60)[0]
                if offset > 1024**2:
                    continue
                stream.seek(offset)
                pe = stream.read(6)
                if pe[:4] == b'PE\x00\x00' and len(pe) == 6 and struct.unpack('<H', pe[4:])[0] == 0x8664:
                    candidates.append(file)
        if candidates:
            if len({digest(file) for file in candidates}) != 1:
                raise RuntimeError(f'Runtime VC x64 ambíguo no MSI: {name}')
            shutil.copy2(candidates[0], program_folder / name)


def prepare(output=DEFAULT_OUTPUT, cache=DEFAULT_CACHE):
    if sys.platform != 'win32':
        raise RuntimeError('A extração administrativa do LibreOffice precisa ser executada no Windows.')
    output = Path(output).resolve()
    cache = Path(cache).resolve()
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    artifacts = {name: download(entry, cache) for name, entry in lock.items() if name != 'schema'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='engines-', dir=output.parent) as folder:
        staging = Path(folder)
        ffmpeg_extract = staging / 'ffmpeg-extract'
        extract_zip(artifacts['ffmpeg'], ffmpeg_extract)
        executable = next(ffmpeg_extract.glob('*/bin/ffmpeg.exe'), None)
        if executable is None:
            raise RuntimeError('O arquivo FFmpeg não contém bin/ffmpeg.exe.')
        payload = staging / 'payload'
        shutil.copytree(executable.parent.parent, payload / 'tools/ffmpeg')
        require_file(payload / 'tools/ffmpeg/bin/ffprobe.exe')

        # /a unpacks the MSI without installing Office, writing associations or
        # requiring Office to exist on the build machine. Preserve the complete
        # program/share/presets/resources tree and upstream notices.
        office_extract = staging / 'office-extract'
        log = cache / 'libreoffice-extract.log'
        office = extract_office(artifacts['libreoffice'], office_extract, log)
        shutil.copytree(office, payload / 'tools/libreoffice')

        ocr_extract = staging / 'ocr-extract'
        subprocess.run([seven_zip(), 'x', str(artifacts['tesseract']), f'-o{ocr_extract}', '-y'],
                       check=True, stdout=subprocess.DEVNULL, timeout=120)
        ocr = payload / 'ocr'
        ocr.mkdir()
        # Training tools and NSIS plugins are not part of the runtime. Keep every
        # DLL so Leptonica and its codec dependencies remain alongside Tesseract.
        for file in [*ocr_extract.glob('*.dll'), ocr_extract / 'tesseract.exe']:
            require_file(file)
            shutil.copy2(file, ocr / file.name)
        shutil.copytree(ocr_extract / 'doc', ocr / 'doc')
        require_file(ocr / 'libtesseract-5.dll')
        (ocr / 'tessdata').mkdir()
        shutil.copy2(artifacts['ocr_eng'], ocr / 'tessdata/eng.traineddata')
        shutil.copy2(artifacts['ocr_license'], ocr / 'tessdata/LICENSE')

        lock['provenance'] = 'provisional-vendor-binaries; complete corresponding-source bundle not established'
        (payload / 'engines.json').write_text(json.dumps(lock, indent=2, ensure_ascii=False) + '\n',
                                             encoding='utf-8')
        # Deterministic file inventory is copied into the installer's validation
        # report and makes the included binaries auditable after installation.
        inventory = {str(p.relative_to(payload)).replace('\\', '/'): digest(p)
                     for p in sorted(payload.rglob('*')) if p.is_file()}
        (payload / 'engine-files.sha256.json').write_text(json.dumps(inventory, indent=2) + '\n',
                                                       encoding='utf-8')
        if output.exists():
            shutil.rmtree(output)
        shutil.move(str(payload), output)
    print(f'Motores offline preparados: {output}', flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    prepare(args.output, args.cache)
