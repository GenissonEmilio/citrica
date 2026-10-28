"""Restore verified source-built engines from one prior portable QA artifact.

This is an unsigned-test optimization, not a release/reproducibility claim.
Only engine inventory members are copied; no previous application launcher,
Python runtime or Qt DLL is reused. The caller verifies GitHub run/artifact
ownership before downloading the portable archive.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import stat
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'Citrica/_internal/'
INVENTORY = 'engine-files.sha256.json'
RECIPES = ['packaging/build_ffmpeg_windows.sh', 'packaging/build_windows_source_engines.py',
           'packaging/prepare_windows_engines.py']
REQUIRED = {'engines.json', 'engine-sources.zip', 'tools/ffmpeg/bin/ffmpeg.exe',
            'tools/ffmpeg/bin/ffprobe.exe', 'tools/libreoffice/program/soffice.com',
            'ocr/tessdata/eng.traineddata', 'ocr/tesseract.exe'}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name or
            name.startswith('/') or any(ord(char) < 32 or char in '<>"|?*' for char in name)):
        raise ValueError(f'Caminho de arquivo inseguro: {name!r}')
    parts = name.removesuffix('/').split('/')
    for part in parts:
        stem = part.split('.', 1)[0].upper()
        if (not part or part in {'.', '..'} or part.endswith((' ', '.')) or
                stem in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} or
                re.fullmatch(r'(COM|LPT)[1-9]', stem)):
            raise ValueError(f'Caminho de arquivo inseguro: {name!r}')
    return name


def members(archive):
    result, seen = {}, set()
    for item in archive.infolist():
        if item.orig_filename != item.filename:
            raise ValueError('Nome ZIP contém caractere NUL.')
        name = safe_name(item.filename)
        folded = name.removesuffix('/').casefold()
        if folded in seen:
            raise ValueError(f'Arquivo ZIP duplicado ou com colisão Windows: {name}')
        seen.add(folded)
        mode = item.external_attr >> 16
        if mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise ValueError(f'Link/arquivo especial proibido no ZIP: {name}')
        if not item.is_dir():
            result[name] = item
    return result


def load_json(archive, index, name):
    item = index.get(name)
    if not item or item.file_size > 8 * 1024 * 1024:
        raise ValueError(f'Manifesto ausente ou grande demais: {name}')
    return json.loads(archive.read(item))


def normalized(data):
    return data.decode('utf-8').replace('\r\n', '\n')


def recipe_checks(sources, index, root):
    """Build-affecting commands must match; cache validation changes may differ."""
    previous = {name: sources.read(index[name]) for name in RECIPES}
    current = {name: (root / name).read_bytes() for name in RECIPES}
    shell = RECIPES[0]
    if normalized(previous[shell]) != normalized(current[shell]):
        raise ValueError('Receita de compilação FFmpeg mudou; compile os motores novamente.')
    for recipe, function in [(RECIPES[1], 'cmake_build'), (RECIPES[2], 'extract_office')]:
        signatures = []
        for data in [previous[recipe], current[recipe]]:
            tree = ast.parse(normalized(data))
            definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function]
            if len(definitions) != 1:
                raise ValueError(f'Receita sem função {function}: {recipe}')
            # Include both the toolchain implementation (/MT flags, generator)
            # and the concrete Tesseract/Leptonica build configurations.
            nodes = definitions + ([node for node in ast.walk(tree) if isinstance(node, ast.Call) and
                isinstance(node.func, ast.Name) and node.func.id == 'cmake_build'] if function == 'cmake_build' else [])
            signatures.append([ast.dump(node, include_attributes=False) for node in nodes])
        if signatures[0] != signatures[1]:
            raise ValueError(f'Receita {function} mudou; compile os motores novamente.')
    return {name: {'artifact_sha256': sha256(previous[name]), 'current_sha256': sha256(current[name]),
                   'whole_file_equal_after_newlines': normalized(previous[name]) == normalized(current[name])}
            for name in RECIPES}


def validate_sources(path, source_lock, vendor_lock, root):
    with zipfile.ZipFile(path) as sources:
        index = members(sources)
        for filename, expected in [('windows-sources.lock.json', source_lock), ('windows-engines.lock.json', vendor_lock)]:
            if load_json(sources, index, 'packaging/' + filename) != expected:
                raise ValueError(f'Lock correspondente incompatível: {filename}')
        if not all(name in index for name in RECIPES):
            raise ValueError('Pacote de fontes sem receitas de compilação.')
        recipes = recipe_checks(sources, index, root)
        # Do not merely trust the lock embedded in the source ZIP: hash the
        # actual original source archives and OCR model shipped alongside it.
        downloads = [sha256(sources.read(item)) for name, item in index.items() if name.startswith('downloads/')]
        for entry in [*source_lock['sources'].values(), vendor_lock['ocr_eng'], vendor_lock['ocr_license']]:
            if downloads.count(entry['sha256']) != 1:
                raise ValueError(f'Fonte/modelo correspondente ausente ou alterado: {entry["version"]}')
    return recipes


def restore(portable, output, report, *, root=ROOT):
    portable, output, report, root = (Path(path).resolve() for path in [portable, output, report, root])
    if output.exists():
        raise ValueError('A saída precisa ser nova; nenhum runtime existente será mesclado ou apagado.')
    source_lock = json.loads((root / 'packaging/windows-sources.lock.json').read_text(encoding='utf-8'))
    vendor_lock = json.loads((root / 'packaging/windows-engines.lock.json').read_text(encoding='utf-8'))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(portable) as archive:
        index = members(archive)
        inventory = load_json(archive, index, PREFIX + INVENTORY)
        if not isinstance(inventory, dict) or not REQUIRED.issubset(inventory):
            raise ValueError('Inventário de motores inválido ou incompleto.')
        for name, checksum in inventory.items():
            safe_name(name)
            if name.endswith('/') or not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum):
                raise ValueError(f'Entrada de inventário inválida: {name!r}')
            if name not in {'engines.json', 'engine-sources.zip'} and not name.startswith(
                    ('tools/ffmpeg/', 'tools/libreoffice/', 'ocr/')):
                raise ValueError(f'Inventário tentou reutilizar arquivo de aplicativo: {name}')
            if PREFIX + name not in index:
                raise ValueError(f'Arquivo de motor ausente: {name}')
        engine_members = {name[len(PREFIX):] for name in index if name.startswith(
            (PREFIX + 'tools/ffmpeg/', PREFIX + 'tools/libreoffice/', PREFIX + 'ocr/'))}
        # Office creates __pycache__ during package smoke tests, after the
        # original engine inventory was written. Never copy unlisted files.
        ignored = engine_members - set(inventory)
        metadata = load_json(archive, index, PREFIX + 'engines.json')
        if (not isinstance(metadata, dict) or metadata.get('schema') != 1 or
                metadata.get('provenance') != 'compiled-from-pinned-sources' or
                metadata.get('sources') != source_lock['sources']):
            raise ValueError('Proveniência/fontes dos motores incompatíveis com o lock atual.')
        for name in ['libreoffice', 'ocr_eng']:
            if metadata.get(name) != vendor_lock[name]:
                raise ValueError(f'Pin incompatível de {name}.')
        if inventory['ocr/tessdata/eng.traineddata'] != vendor_lock['ocr_eng']['sha256']:
            raise ValueError('Modelo OCR real incompatível com o pin atual.')
        library = metadata.get('ocr_library', '')
        if (not isinstance(library, str) or '/' in library or '\\' in library or
                not library.lower().endswith('.dll') or 'tesseract' not in library.lower() or
                'ocr/' + library not in inventory):
            raise ValueError('Biblioteca OCR declarada ausente ou inválida.')
        source = metadata.get('corresponding_source', {})
        if (source.get('file') != 'engine-sources.zip' or
                source.get('sha256') != inventory['engine-sources.zip']):
            raise ValueError('Hash do pacote de fontes correspondente incompatível.')
        with tempfile.TemporaryDirectory(prefix='citrica-reuse-', dir=output.parent) as directory:
            staging = Path(directory) / 'engines'
            staging.mkdir()
            for name, checksum in inventory.items():
                target = staging.joinpath(*name.split('/'))
                target.parent.mkdir(parents=True, exist_ok=True)
                hasher = hashlib.sha256()
                with archive.open(index[PREFIX + name]) as src, target.open('wb') as dst:
                    while chunk := src.read(1024 * 1024):
                        hasher.update(chunk)
                        dst.write(chunk)
                if hasher.hexdigest() != checksum:
                    raise ValueError(f'SHA-256 diferente no motor: {name}')
            recipes = validate_sources(staging / 'engine-sources.zip', source_lock, vendor_lock, root)
            (staging / INVENTORY).write_bytes(archive.read(index[PREFIX + INVENTORY]))
            staging.rename(output)
    data = {'purpose': 'unsigned-test-only', 'release_eligible': False, 'success': True,
            'portable_archive': portable.name, 'engine_files_verified': len(inventory),
            'inventory_sha256': sha256((output / INVENTORY).read_bytes()),
            'corresponding_source_sha256': inventory['engine-sources.zip'],
            'provenance': metadata['provenance'], 'current_locks_match': True,
            'build_affecting_recipes_match': True, 'recipes': recipes,
            'application_runtime_reused': False, 'unlisted_engine_files_ignored': len(ignored),
            'reproducible_bit_for_bit_verified': False}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Reuso QA: {len(inventory)} arquivos de motores verificados; aplicativo será recompilado.")
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('portable', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/windows-reused-engines')
    parser.add_argument('--report', type=Path, default=ROOT / 'release/citrica-windows-engine-reuse.json')
    args = parser.parse_args()
    restore(args.portable, args.output, args.report)
