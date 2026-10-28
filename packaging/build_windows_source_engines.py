"""Compile minimal Windows engines from pinned sources with corresponding source.

Requires MSYS2 MINGW64 (gcc, make, nasm, pkgconf, meson, ninja), CMake and
Visual Studio2022 C++ build tools. No compiler/tool downloads happen here.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from prepare_windows_engines import LOCK as VENDOR_LOCK
from prepare_windows_engines import ROOT, digest, download, extract_office, require_file

LOCK = Path(__file__).with_name('windows-sources.lock.json')
OUTPUT = ROOT / 'build/windows-source-engines'
CACHE = ROOT / 'build/windows-engine-cache'
WORK = ROOT / 'build/windows-source-build'


def run(*args, **kwargs):
    print(' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def unpack(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as source:
        source.extractall(destination, filter='data')
    folders = list(destination.iterdir())
    if len(folders) != 1 or not folders[0].is_dir():
        raise RuntimeError(f'Layout de fontes inesperado: {archive}')
    return folders[0]


def cmake_build(source, build, prefix, *options):
    run('cmake', '-S', source, '-B', build, '-G', 'Visual Studio 17 2022', '-A', 'x64',
        f'-DCMAKE_INSTALL_PREFIX={prefix}', '-DCMAKE_POLICY_DEFAULT_CMP0091=NEW',
        '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded', *options, timeout=180)
    run('cmake', '--build', build, '--config', 'Release', '--parallel',
        os.environ.get('CITRICA_BUILD_JOBS', '2'), timeout=1800)
    run('cmake', '--install', build, '--config', 'Release', timeout=120)


def copy_notices(sources, target):
    target.mkdir(parents=True, exist_ok=True)
    for name, folder in sources.items():
        destination = target / name
        destination.mkdir()
        for file in folder.iterdir():
            if file.is_file() and file.name.upper().startswith(('COPYING', 'LICENSE', 'NOTICE', 'PATENTS', 'AUTHORS')):
                shutil.copy2(file, destination / file.name)
        # Leptonica's primary notice is named after the project.
        for file in folder.glob('*license*'):
            if file.is_file():
                shutil.copy2(file, destination / file.name)


def prepare(output=OUTPUT, cache=CACHE, work=WORK, msys_bash=None, office_from=None):
    if sys.platform != 'win32':
        raise RuntimeError('A compilação usa os toolchains Windows MSYS2 e Visual Studio2022.')
    output, cache, work = (Path(p).resolve() for p in [output, cache, work])
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    vendors = json.loads(VENDOR_LOCK.read_text(encoding='utf-8'))
    archives = {name: download(entry, cache / 'sources') for name, entry in lock['sources'].items()}
    source_root = work / 'source'
    sources = {}
    for name, archive in archives.items():
        source = unpack(archive, work / 'unpack' / name)
        destination = source_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), destination)
        sources[name] = destination

    bash = Path(msys_bash or os.environ.get('CITRICA_MSYS_BASH', 'C:/msys64/usr/bin/bash.exe'))
    require_file(bash)
    ffmpeg_prefix = work / 'ffmpeg-prefix'
    run(bash, '--login', (ROOT / 'packaging/build_ffmpeg_windows.sh').as_posix(), source_root.as_posix(),
        ffmpeg_prefix.as_posix(), (work / 'ffmpeg-build').as_posix(),
        env=dict(os.environ, MSYSTEM='MINGW64', CHERE_INVOKING='1'), timeout=3600)
    ffmpeg = output / 'tools/ffmpeg/bin'
    ffmpeg.mkdir(parents=True)
    for name in ['ffmpeg.exe', 'ffprobe.exe']:
        require_file(ffmpeg_prefix / 'bin' / name)
        shutil.copy2(ffmpeg_prefix / 'bin' / name, ffmpeg / name)

    ocr_prefix = work / 'ocr-prefix'
    cmake_build(sources['leptonica'], work / 'leptonica-build', ocr_prefix,
                '-DSW_BUILD=OFF', '-DBUILD_SHARED_LIBS=OFF', '-DBUILD_PROG=OFF',
                *[f'-DENABLE_{name}=OFF' for name in ['ZLIB', 'PNG', 'JPEG', 'TIFF', 'GIF', 'WEBP', 'OPENJPEG']])
    cmake_build(sources['tesseract'], work / 'tesseract-build', ocr_prefix,
                '-DBUILD_SHARED_LIBS=ON', '-DBUILD_TRAINING_TOOLS=OFF', '-DBUILD_TESTS=OFF',
                '-DOPENMP_BUILD=OFF', '-DENABLE_NATIVE=OFF', '-DGRAPHICS_DISABLED=ON',
                '-DDISABLE_TIFF=ON', '-DDISABLE_ARCHIVE=ON', '-DDISABLE_CURL=ON',
                f'-DCMAKE_PREFIX_PATH={ocr_prefix}')
    ocr = output / 'ocr'
    ocr.mkdir()
    dlls = list((ocr_prefix / 'bin').glob('*tesseract*.dll'))
    if len(dlls) != 1:
        raise RuntimeError(f'DLL Tesseract inesperada: {dlls}')
    for file in [*dlls, ocr_prefix / 'bin/tesseract.exe']:
        require_file(file)
        shutil.copy2(file, ocr / file.name)
    data = ocr / 'tessdata'
    data.mkdir()
    models = {name: download(vendors[name], cache) for name in ['ocr_eng', 'ocr_license']}
    for name, file in [('ocr_eng', 'eng.traineddata'), ('ocr_license', 'LICENSE')]:
        shutil.copy2(models[name], data / file)
    copy_notices({name: sources[name] for name in ['leptonica', 'tesseract']}, ocr / 'licenses')
    copy_notices({name: source for name, source in sources.items() if name not in ['leptonica', 'tesseract']},
                 output / 'tools/ffmpeg/licenses')
    toolchain_licenses = work / 'ffmpeg-build/toolchain-licenses'
    if toolchain_licenses.is_dir():
        shutil.copytree(toolchain_licenses, output / 'tools/ffmpeg/licenses/toolchain')

    if office_from:
        office = Path(office_from).resolve()
        require_file(office / 'program/soffice.com')
    else:
        archive = download(vendors['libreoffice'], cache)
        office = extract_office(archive, work / 'office-extract', cache / 'libreoffice-source-engine-extract.log')
    shutil.copytree(office, output / 'tools/libreoffice')

    # Include the original archives and the actual recipe/configuration used in
    # every bundle. A user can obtain the corresponding GPL sources offline,
    # without relying on the continued availability of an external download URL.
    bundle = output / 'engine-sources.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as target:
        for name, archive in archives.items():
            target.write(archive, 'downloads/sources/' + archive.name)
        for model in models.values():
            target.write(model, 'downloads/' + model.name)
        for file in [LOCK, VENDOR_LOCK, ROOT / 'packaging/prepare_windows_engines.py', Path(__file__),
                     ROOT / 'packaging/build_ffmpeg_windows.sh']:
            target.write(file, 'packaging/' + file.name)
        target.write(ROOT / 'docs/WINDOWS-ENGINES.md', 'docs/WINDOWS-ENGINES.md')
        target.writestr('README-SOURCES.txt',
                        'Corresponding FFmpeg/codecs/Tesseract/Leptonica source for this binary build.\n'
                        'See docs/WINDOWS-ENGINES.md for toolchain prerequisites.\n'
                        'Extract this ZIP and run, from its root:\n'
                        'python packaging/build_windows_source_engines.py --cache downloads '
                        '--office-from "C:/path/to/Citrica/_internal/tools/libreoffice"\n'
                        'The provided archive/model cache is verified by SHA-256 before compilation.\n'
                        'Without --office-from, the script explicitly downloads the pinned Office MSI.\n'
                        'Sources are unmodified; build configuration and toolchain records are included.\n')
        for file in (work / 'ffmpeg-build').rglob('*'):
            if file.is_file() and file.name in ['config.log', 'config.h', 'config_components.h', 'config.mak',
                                               'msys2-packages.txt', 'gcc-version.txt', 'nasm-version.txt',
                                               'ffmpeg-version.txt', 'ffmpeg-buildconf.txt', 'ffprobe-version.txt']:
                target.write(file, 'build-configuration/' + str(file.relative_to(work)))
        for name in ['leptonica', 'tesseract']:
            target.write(work / f'{name}-build/CMakeCache.txt', f'build-configuration/{name}/CMakeCache.txt')
        if toolchain_licenses.is_dir():
            for file in toolchain_licenses.rglob('*'):
                if file.is_file():
                    target.write(file, 'toolchain-licenses/' + str(file.relative_to(toolchain_licenses)))
    metadata = {'schema': 1, 'provenance': 'compiled-from-pinned-sources', 'sources': lock['sources'],
                'ocr_library': dlls[0].name,
                'libreoffice': vendors['libreoffice'], 'ocr_eng': vendors['ocr_eng'],
                'corresponding_source': {'file': bundle.name, 'sha256': digest(bundle),
                                         'scope': ['ffmpeg', 'linked-codec-libraries', 'tesseract', 'leptonica']},
                'reproducible_bit_for_bit_verified': False}
    (output / 'engines.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    inventory = {str(p.relative_to(output)).replace('\\', '/'): digest(p)
                 for p in sorted(output.rglob('*')) if p.is_file()}
    (output / 'engine-files.sha256.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
    print(f'Motores próprios e fontes correspondentes: {output}', flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--cache', type=Path, default=CACHE)
    parser.add_argument('--work', type=Path, default=WORK)
    parser.add_argument('--msys-bash', type=Path)
    parser.add_argument('--office-from', type=Path,
                        help='reusar a pasta LibreOffice do pacote original, sem baixar o MSI novamente')
    args = parser.parse_args()
    prepare(args.output, args.cache, args.work, args.msys_bash, args.office_from)
