"""Restore exact verified application PEs from an existing full-build QA artifact.

The workflow authenticates the same-repository artifact/run first. No build or
new full conversion matrix runs here; previous complete matrix evidence is
required and identified separately from this desktop retest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from reuse_windows_test_engines import members, safe_name

ROOT = Path(__file__).resolve().parents[1]
PRIOR_REPORTS = ['citrica-windows-validation.json', 'citrica-windows-engine-parity.json',
                 'citrica-windows-static-tools-parity.json', 'citrica-windows-signing.json']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checksum_table(path):
    checksums, folded = {}, set()
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64})  (.+)', line)
        if not match:
            raise ValueError('SHA256SUMS Windows contém linha inválida.')
        checksum, name = match.groups()
        safe_name(name)
        if '/' in name or name.casefold() in folded:
            raise ValueError('SHA256SUMS contém caminho ou nome duplicado.')
        folded.add(name.casefold())
        checksums[name] = checksum.lower()
    return checksums


def prior_full_build(reports):
    validation, matrix, static, signing = (reports[name] for name in PRIOR_REPORTS)
    details = validation.get('validation', {})
    if (details.get('ui_qa_only') or details.get('packaged_engine_smoke') is not True or
            details.get('conversion_matrix') != 'citrica-windows-engine-parity.json'):
        raise ValueError('Artefato não comprova um build completo anterior.')
    if (matrix.get('conversions') != 304 or len(matrix.get('cases', [])) != 304 or
            not all(case.get('success') is True for case in matrix['cases']) or
            len(matrix.get('media_tools', [])) != 23 or
            not all(case.get('success') is True for case in matrix['media_tools']) or
            matrix.get('originals_preserved') is not True or matrix.get('ocr_redaction') is not True):
        raise ValueError('Matriz completa anterior não passou integralmente.')
    if (static.get('success') is not True or static.get('operations') != 38 or
            len(static.get('cases', [])) != 38 or not all(case.get('success') is True for case in static['cases']) or
            static.get('originals_preserved') is not True):
        raise ValueError('Ferramentas estáticas do build anterior não passaram integralmente.')
    if signing.get('status') != 'unsigned' or signing.get('authenticode_verified') is not False:
        raise ValueError('Reteste exige o artefato de diagnóstico explicitamente não assinado.')
    return {'status': 'prior-full-build-verified', 'new_full_matrix_executed': False,
            'prior_conversions': 304, 'prior_media_operations': 23, 'prior_static_operations': 38,
            'all_prior_cases_passed': True}


def restore(candidate, *, root=ROOT, origin_path=None):
    candidate, root = Path(candidate).resolve(), Path(root).resolve()
    origin_path = Path(origin_path or root / 'release/citrica-windows-existing-build-origin.json')
    origin = json.loads(origin_path.read_text(encoding='utf-8'))
    if (not re.fullmatch('[0-9a-f]{40}', origin.get('app_commit', '')) or
            origin.get('artifact_name') != 'citrica-windows-repack-unsigned-test'):
        raise ValueError('Relatório de origem autenticada incompleto.')
    tables = list(candidate.rglob('SHA256SUMS-windows.txt'))
    if len(tables) != 1:
        raise ValueError('Esperado um único SHA256SUMS do artefato completo.')
    release = tables[0].parent
    checksums = checksum_table(tables[0])

    def verified(name):
        path = release / name
        if name not in checksums or not path.is_file() or digest(path) != checksums[name]:
            raise ValueError(f'SHA-256 ausente ou diferente: {name}')
        return path

    setups = list(release.glob('citrica-*-windows-x86_64-setup-unsigned-test.exe'))
    portables = list(release.glob('citrica-*-windows-x86_64-portable-unsigned-test.zip'))
    if len(setups) != 1 or len(portables) != 1:
        raise ValueError('Esperado exatamente um setup e um portátil unsigned-test.')
    setup, portable = verified(setups[0].name), verified(portables[0].name)
    reports = {name: json.loads(verified(name).read_text(encoding='utf-8')) for name in PRIOR_REPORTS}
    full_build = prior_full_build(reports)
    target, installed_setup = root / 'dist/Citrica', root / 'build/existing-setup.exe'
    if target.exists() or installed_setup.exists():
        raise ValueError('Não mescle um runtime ou instalador de reteste existente.')
    target.parent.mkdir(parents=True, exist_ok=True)
    installed_setup.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(portable) as archive:
        index = members(archive)
        if any(not name.startswith('Citrica/') for name in index):
            raise ValueError('Portátil contém arquivo fora da raiz Citrica/.')
        for name in ['Citrica/Citrica.exe', 'Citrica/citrica-cli.exe', 'Citrica/_internal/engines.json']:
            if name not in index or not index[name].file_size:
                raise ValueError(f'Runtime portátil incompleto: {name}')
        metadata = json.loads(archive.read(index['Citrica/_internal/engines.json']))
        expected = reports['citrica-windows-validation.json']['validation'].get('offline_engines')
        if metadata != expected or metadata.get('provenance') != 'compiled-from-pinned-sources':
            raise ValueError('Motores do portátil divergem da evidência do build completo.')
        source_pin = metadata.get('corresponding_source', {}).get('sha256')
        source_name = 'Citrica/_internal/engine-sources.zip'
        if (not isinstance(source_pin, str) or source_name not in index or
                hashlib.sha256(archive.read(index[source_name])).hexdigest() != source_pin):
            raise ValueError('Fontes correspondentes do portátil ausentes ou alteradas.')
        with tempfile.TemporaryDirectory(prefix='citrica-existing-', dir=target.parent) as temporary:
            staging = Path(temporary) / 'Citrica'
            staging.mkdir()
            for name, member in index.items():
                destination = staging.joinpath(*name.split('/')[1:])
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open('wb') as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            staging.rename(target)
    shutil.copyfile(setup, installed_setup)
    if digest(installed_setup) != checksums[setup.name]:
        raise ValueError('SHA-256 do instalador restaurado divergiu.')
    output = root / 'release'
    output.mkdir(exist_ok=True)
    prior = output / 'prior-build'
    prior.mkdir(exist_ok=True)
    for name in PRIOR_REPORTS:
        shutil.copyfile(release / name, prior / name)
    (output / 'existing-full-build-required.json').write_text(json.dumps(full_build, indent=2) + '\n', encoding='utf-8')
    origin.update({'restored': True, 'recompiled': False, 'new_full_matrix_executed': False,
        'setup_sha256': checksums[setup.name], 'portable_sha256': checksums[portable.name],
        'gui_sha256': digest(target / 'Citrica.exe'), 'cli_sha256': digest(target / 'citrica-cli.exe'),
        'corresponding_engine_source_sha256': source_pin, 'prior_full_build': full_build,
        'purpose': 'exact-existing-build-desktop-retest', 'release_eligible': False})
    origin_path.write_text(json.dumps(origin, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Setup/portátil verificados; PEs exatos restaurados sem recompilar. Matriz completa anterior confirmada.')
    return origin


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--origin', type=Path)
    args = parser.parse_args()
    restore(args.candidate, origin_path=args.origin)
