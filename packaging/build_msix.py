"""Stage an unchanged PyInstaller tree and package it with Windows SDK MakeAppx.

Store packages are unsigned inputs for Partner Center, never verified releases.
The separate OID-marked QA package has a different name, publisher and identity.
This builder never signs, downloads engines, installs packages or changes policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ROOT / 'packaging/windows-store-identity.json'
UNSIGNED_OID = 'OID.2.25.311729368913984317654407730594956997722=1'
NS = {
    '': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
    'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10',
    'desktop': 'http://schemas.microsoft.com/appx/manifest/desktop/windows10',
    'uap10': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/10',
    'rescap': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities',
}
FIELDS = {'schema', 'name', 'publisher', 'publisher_display_name', 'display_name', 'store_id',
          'package_family_name', 'store_version', 'architecture', 'min_os_version',
          'max_tested_os_version', 'startup_task_id'}
ENGINE_REQUIRED = {
    '_internal/engines.json',
    '_internal/engine-sources.zip', '_internal/tools/ffmpeg/bin/ffmpeg.exe',
    '_internal/tools/ffmpeg/bin/ffprobe.exe', '_internal/tools/libreoffice/program/soffice.com',
    '_internal/tools/libreoffice/program/soffice.exe', '_internal/ocr/tesseract.exe',
    '_internal/ocr/tessdata/eng.traineddata',
}
REQUIRED = ENGINE_REQUIRED | {
    'Citrica.exe', 'citrica-cli.exe', 'citrica-package.exe', 'LICENSE', 'THIRD_PARTY.md',
    'requirements.lock', '_internal/engine-files.sha256.json',
    '_internal/docx/templates/default.docx',
}
SOURCE_TEMPLATE = '_internal/docx/templates/default-docx-template/'
_qt_app = None


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('Version must contain four decimal components without leading zeros.')
    result = tuple(map(int, value.split('.')))
    if max(result) > 65535:
        raise ValueError('Version components must not exceed 65535.')
    return result


def load_identity(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != FIELDS or data['schema'] != 1:
        raise ValueError('Identity must contain only the documented public fields (schema 1).')
    for key in FIELDS - {'schema'}:
        if (not isinstance(data[key], str) or not data[key].strip() or
                any(ord(char) < 32 for char in data[key])):
            raise ValueError(f'Invalid identity field: {key}')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{2,49}', data['name']):
        raise ValueError('Invalid package name.')
    if not re.fullmatch(r'CN=[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}', data['publisher']):
        raise ValueError('Use the exact public Partner Center CN publisher, without an unsigned OID.')
    if not re.fullmatch(re.escape(data['name']) + r'_[a-z0-9]{13}', data['package_family_name']):
        raise ValueError('The public package family must match the package name.')
    if not re.fullmatch(r'[A-Z0-9]{12}', data['store_id']):
        raise ValueError('Invalid Store ID.')
    number = version(data['store_version'])
    if number[0] == 0 or number[3] != 0:
        raise ValueError('Store version must start above zero and reserve the fourth component as zero.')
    minimum, maximum = version(data['min_os_version']), version(data['max_tested_os_version'])
    if minimum < (10, 0, 19041, 0) or maximum < minimum:
        raise ValueError('This manifest requires Windows 19041 or later and a coherent maximum version.')
    if data['architecture'] != 'x64' or data['startup_task_id'] != 'CitricaStartup':
        raise ValueError('The current runtime requires x64 and StartupTask CitricaStartup.')
    if len(data['name'] + '.UnsignedQA') > 50:
        raise ValueError('Package name is too long for the distinct unsigned QA name.')
    if len(data['display_name'] + ' · QA unsigned') > 256 or len(data['publisher_display_name']) > 256:
        raise ValueError('Package display names must fit the manifest length limit.')
    return data


def variant_identity(identity, mode):
    if mode not in {'store', 'qa'}:
        raise ValueError('Variant must be store or qa.')
    data = dict(identity)
    if mode == 'qa':
        data.update(name=identity['name'] + '.UnsignedQA',
                    publisher=identity['publisher'] + ', ' + UNSIGNED_OID,
                    display_name=identity['display_name'] + ' · QA unsigned',
                    package_family_name=None, store_id=None)
    return data


def safe_name(name):
    if (not name or '\\' in name or ':' in name or name.startswith('/') or
            any(ord(char) < 32 or char in '<>"|?*' for char in name)):
        raise ValueError(f'Unsafe Windows payload path: {name!r}')
    for part in name.split('/'):
        stem = part.split('.', 1)[0].upper()
        if (not part or part in {'.', '..'} or part.endswith((' ', '.')) or
                stem in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} or
                re.fullmatch(r'(COM|LPT)[1-9]', stem)):
            raise ValueError(f'Unsafe Windows payload path: {name!r}')
    return name


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def snapshot(payload):
    files, names = {}, set()
    def visit(folder):
        for path in sorted(folder.iterdir()):
            name = safe_name(path.relative_to(payload).as_posix())
            info = path.lstat()
            if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError(f'Payload links/reparse points are forbidden: {name}')
            if name.casefold() in names:
                raise ValueError(f'Windows path collision: {name}')
            names.add(name.casefold())
            if stat.S_ISDIR(info.st_mode):
                if path.name.casefold() in {'.git', '.svn'}:
                    raise ValueError('Use a built runtime, not a source checkout.')
                visit(path)
            elif stat.S_ISREG(info.st_mode):
                if (path.suffix.casefold() in {'.pfx', '.p12', '.jks'} or
                        path.name.casefold() == '.env' or path.name.casefold().startswith('.env.')):
                    raise ValueError(f'Credentials/private key container must not enter an MSIX: {name}')
                if path.suffix.casefold() in {'.pem', '.key', '.crt', '.cer'}:
                    if b'PRIVATE KEY-----' in path.read_bytes():
                        raise ValueError(f'Private key must not enter an MSIX: {name}')
                files[name] = {'size': info.st_size, 'sha256': digest(path)}
            else:
                raise ValueError(f'Payload contains a special file: {name}')
    visit(payload)
    return files


def pe_x64(path):
    with path.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise ValueError(f'Not a Windows PE runtime: {path.name}')
        stream.seek(struct.unpack_from('<I', header, 60)[0])
        signature = stream.read(6)
    if len(signature) != 6 or signature[:4] != b'PE\0\0' or struct.unpack_from('<H', signature, 4)[0] != 0x8664:
        raise ValueError(f'Runtime must be Windows x64: {path.name}')


def package_inventory(files):
    """Keep runtime data; omit python-docx's unused, unpacked source template.

    python-docx 1.2.0 opens templates/default.docx. Its separate development
    tree contains OPC _rels/*.rels names that MSIX forbids as payload files.
    The input stays intact and every omission is recorded by name and hash.
    """
    packaged, exclusions = {}, []
    for name, metadata in files.items():
        if name.casefold().startswith(SOURCE_TEMPLATE):
            exclusions.append(dict(path=name, **metadata,
                reason='Unused python-docx source template; runtime uses templates/default.docx.'))
            continue
        parts = name.casefold().split('/')
        if '_rels' in parts[:-1] and parts[-1].endswith('.rels'):
            raise ValueError('MSIX reserves OPC relationship payload names: ' + name)
        packaged[name] = metadata
    return packaged, exclusions


def validate_payload(payload, files):
    missing = REQUIRED - files.keys()
    if missing:
        raise ValueError('Incomplete PyInstaller/engine payload: ' + ', '.join(sorted(missing)))
    python = [name for name in files if re.fullmatch(r'_internal/python3\d{1,2}\.dll', name)]
    if len(python) != 1:
        raise ValueError('Exactly one versioned PyInstaller Python DLL is required.')
    runtime = list(python)
    for library in ['Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'Qt6Network.dll']:
        candidates = [name for name in files if name in {
            '_internal/PySide6/' + library, '_internal/PySide6/Qt/bin/' + library}]
        if len(candidates) != 1:
            raise ValueError(f'Missing or ambiguous PySide6 runtime: {library}')
        runtime += candidates
    platforms = [name for name in files if name in {
        '_internal/PySide6/plugins/platforms/qwindows.dll',
        '_internal/PySide6/Qt/plugins/platforms/qwindows.dll'}]
    if len(platforms) != 1:
        raise ValueError('The Windows Qt platform plugin is required.')
    runtime += platforms
    for name in sorted(REQUIRED | set(runtime)):
        if Path(name).suffix.lower() in {'.exe', '.com', '.dll'}:
            pe_x64(payload / name)
    metadata = json.loads((payload / '_internal/engines.json').read_text(encoding='utf-8'))
    if not isinstance(metadata, dict) or metadata.get('provenance') != 'compiled-from-pinned-sources':
        raise ValueError('Store staging requires the validated source-built offline engines.')
    inventory = json.loads((payload / '_internal/engine-files.sha256.json').read_text(encoding='utf-8'))
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError('Missing engine integrity inventory.')
    for name, checksum in inventory.items():
        safe_name(name)
        actual = files.get('_internal/' + name)
        if not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum) or not actual:
            raise ValueError(f'Invalid engine inventory entry: {name}')
        if actual['sha256'] != checksum:
            raise ValueError(f'Engine inventory SHA-256 mismatch: {name}')
    engine_required = {name.removeprefix('_internal/') for name in ENGINE_REQUIRED}
    if not engine_required.issubset(inventory):
        raise ValueError('Engine inventory does not cover the required engines and corresponding sources.')


def output_paths(payload, staging, output):
    raw = [Path(path) for path in [payload, staging, output]]
    for path in raw:
        if path.is_symlink() or (path.exists() and
                getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Payload, staging and output endpoints must not be links/reparse points.')
    payload, staging, output = (path.resolve() for path in raw)
    if not payload.is_dir():
        raise ValueError('Payload must be an existing PyInstaller onedir directory.')
    for path in [staging, output]:
        if path.exists() or path.is_symlink():
            raise ValueError('Staging and output must be new; existing files are never replaced.')
        if path.is_relative_to(payload) or payload.is_relative_to(path):
            raise ValueError('Staging/output must not contain or be inside the input payload.')
    if staging.is_relative_to(output) or output.is_relative_to(staging):
        raise ValueError('Staging and output must be independent, non-overlapping directories.')
    return payload, staging, output


def manifest(identity, mode):
    data = variant_identity(identity, mode)
    for prefix, uri in NS.items():
        ET.register_namespace(prefix, uri)
    def tag(name, prefix=''):
        return '{' + NS[prefix] + '}' + name
    package = ET.Element(tag('Package'), {'IgnorableNamespaces': 'uap desktop uap10 rescap'})
    ET.SubElement(package, tag('Identity'), Name=data['name'], Publisher=data['publisher'],
                  Version=data['store_version'], ProcessorArchitecture='x64')
    properties = ET.SubElement(package, tag('Properties'))
    for key, value in [('DisplayName', data['display_name']), ('PublisherDisplayName', data['publisher_display_name']),
                       ('Description', 'Conversão local de arquivos com roda global.'), ('Logo', r'Assets\StoreLogo.png')]:
        ET.SubElement(properties, tag(key)).text = value
    dependencies = ET.SubElement(package, tag('Dependencies'))
    ET.SubElement(dependencies, tag('TargetDeviceFamily'), Name='Windows.Desktop',
                  MinVersion=data['min_os_version'], MaxVersionTested=data['max_tested_os_version'])
    resources = ET.SubElement(package, tag('Resources'))
    # The current UI is Portuguese; Store displays these declared languages.
    ET.SubElement(resources, tag('Resource'), Language='pt-br')
    app = ET.SubElement(ET.SubElement(package, tag('Applications')), tag('Application'), {
        'Id': 'Citrica', 'Executable': r'Citrica\Citrica.exe',
        tag('RuntimeBehavior', 'uap10'): 'packagedClassicApp', tag('TrustLevel', 'uap10'): 'mediumIL',
    })
    ET.SubElement(app, tag('VisualElements', 'uap'), DisplayName=data['display_name'],
                  Description='Conversão local de arquivos com roda global.', BackgroundColor='transparent',
                  Square150x150Logo=r'Assets\Square150x150Logo.png', Square44x44Logo=r'Assets\Square44x44Logo.png')
    startup = ET.SubElement(ET.SubElement(app, tag('Extensions')), tag('Extension', 'desktop'), {
        # Inherit the application's executable and modern activation attributes.
        # An explicit Executable here requires a separate legacy EntryPoint.
        'Category': 'windows.startupTask',
        tag('Parameters', 'uap10'): '--background',
    })
    ET.SubElement(startup, tag('StartupTask', 'desktop'), TaskId='CitricaStartup', Enabled='false',
                  DisplayName=data['display_name'])
    ET.SubElement(ET.SubElement(package, tag('Capabilities')), tag('Capability', 'rescap'), Name='runFullTrust')
    ET.indent(package, space='  ')
    return ET.ElementTree(package)


def logos(folder):
    global _qt_app
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication
    _qt_app = QApplication.instance() or QApplication([])
    renderer = QSvgRenderer(str(ROOT / 'citrica/assets/citrica.svg'))
    if not renderer.isValid():
        raise ValueError('The original Cítrica SVG logo is invalid.')
    folder.mkdir()
    for name, size in [('StoreLogo', 50), ('Square44x44Logo', 44), ('Square150x150Logo', 150)]:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        if not image.save(str(folder / (name + '.png'))):
            raise RuntimeError('Could not save the package logo: ' + name)
    _qt_app.processEvents()


def makeappx_path(explicit=None):
    if sys.platform != 'win32':
        raise RuntimeError('Compile MSIX on Windows with the official Windows SDK MakeAppx.exe; use --stage-only elsewhere.')
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    else:
        root = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Windows Kits/10/bin'
        candidates += sorted(root.glob('*/x64/makeappx.exe'),
                             key=lambda path: tuple(int(v) for v in path.parts[-3].split('.')), reverse=True)
        found = shutil.which('makeappx.exe')
        if found:
            candidates.append(Path(found))
    for path in candidates:
        if path.is_file() and path.name.lower() == 'makeappx.exe':
            return path.resolve()
    raise FileNotFoundError('Windows SDK MakeAppx.exe was not found; specify --makeappx explicitly.')


def build(payload, staging, output, *, identity_path=IDENTITY, mode='both', makeappx=None, stage_only=False):
    if mode not in {'both', 'store', 'qa'}:
        raise ValueError('Mode must be store, qa or both.')
    identity = load_identity(identity_path)
    payload, staging, output = output_paths(payload, staging, output)
    tool = None if stage_only else makeappx_path(makeappx)
    files = snapshot(payload)
    validate_payload(payload, files)
    packaged_files, exclusions = package_inventory(files)
    staging.mkdir(parents=True)
    output.mkdir(parents=True)
    report = {'schema': 1, 'mode': mode, 'stage_only': stage_only, 'makeappx_ran': False,
              'authenticode_signed': False, 'store_certified': False, 'vm_validated': False,
              'input_payload_modified': False, 'input_payload_unchanged_verified': False,
              'input_inventory': files, 'excluded_input_files': exclusions, 'variants': []}
    try:
        for variant in (['store', 'qa'] if mode == 'both' else [mode]):
            data = variant_identity(identity, variant)
            stage = staging / ('store' if variant == 'store' else 'qa-unsigned-NOT-FOR-STORE')
            destination = stage / 'Citrica'
            destination.mkdir(parents=True)
            for name, expected in packaged_files.items():
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with (payload / name).open('rb') as source, target.open('xb') as target_file:
                    shutil.copyfileobj(source, target_file, 1024 * 1024)
                if digest(target) != expected['sha256']:
                    raise ValueError('Payload changed while staging: ' + name)
            manifest(identity, variant).write(stage / 'AppxManifest.xml', encoding='utf-8', xml_declaration=True)
            logos(stage / 'Assets')
            label = 'store-unsigned' if variant == 'store' else 'qa-unsigned-NOT-FOR-STORE'
            basename = f'Citrica_{identity["store_version"]}_x64_{label}'
            variant_report = {'variant': variant, 'identity': data, 'stage_name': stage.name,
                              'store_identity': variant == 'store', 'unsigned_test_oid': variant == 'qa',
                              'store_submission_candidate': False, 'makeappx_validation': 'not_run',
                              'signed': False, 'vm_validated': False, 'store_certified': False}
            report['variants'].append(variant_report)
            if snapshot(payload) != files:
                raise ValueError('Input payload changed during staging; compilation was stopped.')
            if tool:
                package = output / (basename + '.msix')
                command = [str(tool), 'pack', '/v', '/d', str(stage), '/p', str(package)]
                result = subprocess.run(command, check=False, capture_output=True, text=True,
                                        encoding='utf-8', errors='replace')
                (output / (basename + '.makeappx.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
                report['makeappx_ran'] = True
                variant_report.update(makeappx_validation='failed', makeappx_returncode=result.returncode,
                                      makeappx_log=basename + '.makeappx.log')
                if result.returncode or not package.is_file():
                    raise RuntimeError(f'MakeAppx failed for {variant} (exit {result.returncode}); inspect its log.')
                variant_report.update(makeappx_validation='passed', package=package.name,
                                      package_sha256=digest(package), store_submission_candidate=variant == 'store')
            (output / (basename + '.json')).write_text(json.dumps(variant_report, indent=2, ensure_ascii=False), encoding='utf-8')
        if snapshot(payload) != files:
            raise ValueError('Input payload changed during compilation.')
        report['input_payload_unchanged_verified'] = True
        report['result'] = 'staged-only-not-msix-validated' if stage_only else 'packaged-not-vm-validated'
        return report
    except Exception as error:
        report.update(result='failed', error=str(error))
        raise
    finally:
        (output / 'build-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--identity', type=Path, default=IDENTITY)
    parser.add_argument('--staging', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['store', 'qa', 'both'], default='both')
    parser.add_argument('--makeappx', type=Path)
    parser.add_argument('--stage-only', action='store_true', help='inspect staging only; never claims MSIX validation')
    args = parser.parse_args(argv)
    report = build(args.payload, args.staging, args.output, identity_path=args.identity,
                   mode=args.mode, makeappx=args.makeappx, stage_only=args.stage_only)
    print(json.dumps({'result': report['result'], 'variants': len(report['variants'])}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
