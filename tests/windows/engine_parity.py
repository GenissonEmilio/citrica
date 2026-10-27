"""Convert every supported input extension with the packaged offline engines.

Run in the clean Windows VM as well as CI:
    python tests/windows/engine_parity.py path/to/citrica-cli.exe
PATH is reduced to Windows itself for every application call; preinstalled
Office/FFmpeg/Tesseract and source-tree overrides cannot satisfy this check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import time
import wave
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw
from pillow_heif import register_heif_opener

register_heif_opener()

FORMATS = {
    'image': ['png', 'jpg', 'webp', 'avif', 'heic', 'tiff', 'bmp', 'gif', 'pdf'],
    'video': ['mp4', 'webm', 'mkv', 'mov', 'gif', 'mp3', 'wav'],
    'audio': ['mp3', 'wav', 'flac', 'ogg', 'opus', 'm4a', 'aiff'],
    'document': ['pdf', 'docx', 'odt', 'txt'],
    'sheet': ['pdf', 'xlsx', 'ods', 'csv'],
    'slides': ['pdf', 'pptx', 'odp'],
    'pdf': ['png', 'jpg', 'docx', 'txt', 'pdf'],
    'subtitle': ['srt', 'vtt', 'txt'],
    'archive': ['zip', 'tar', 'tar.gz'],
}
INPUTS = {
    'image': ['jpg', 'jpeg', 'png', 'webp', 'tif', 'tiff', 'bmp', 'gif', 'avif', 'heic', 'heif'],
    'video': ['mp4', 'mov', 'mkv', 'avi', 'webm', 'wmv', 'm4v', 'mpeg', 'mpg'],
    'audio': ['mp3', 'wav', 'flac', 'ogg', 'opus', 'm4a', 'aac', 'aiff', 'wma', 'mka'],
    'document': ['doc', 'docx', 'odt', 'rtf', 'txt'],
    'sheet': ['xls', 'xlsx', 'ods', 'csv', 'tsv'],
    'slides': ['ppt', 'pptx', 'odp'],
    'pdf': ['pdf'], 'subtitle': ['srt', 'vtt'], 'archive': ['zip', 'tar', 'tar.gz', 'tgz'],
}
MARKER = 'Citrica offline conversion matrix 1234'


def run(args, env, timeout=120):
    result = subprocess.run(list(map(str, args)), check=False, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', env=env, timeout=timeout)
    if result.returncode:
        raise AssertionError(f'{args!r}\n{result.stdout[-2000:]}\n{result.stderr[-3000:]}')
    return result.stdout.strip()


def office_export(office, source, fmt, destination, env):
    profile = destination / 'profile'
    destination.mkdir(parents=True, exist_ok=True)
    run([office, f'-env:UserInstallation={profile.as_uri()}', '--headless', '--convert-to', fmt,
         '--outdir', destination, source], env)
    output = destination / f'{source.stem}.{fmt}'
    assert output.is_file() and output.stat().st_size > 0, output
    return output


def office_seeds(root):
    """Small standards-based flat ODF seeds; no test-only Office library needed."""
    namespaces = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                  'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
                  'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
                  'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
                  'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
                  'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"')
    sheet = root / 'spreadsheet.fods'
    sheet.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document {namespaces} office:version="1.3"
office:mimetype="application/vnd.oasis.opendocument.spreadsheet">
<office:body><office:spreadsheet><table:table table:name="Matrix"><table:table-row>
<table:table-cell office:value-type="string"><text:p>{MARKER}</text:p></table:table-cell>
<table:table-cell office:value-type="float" office:value="42"><text:p>42</text:p></table:table-cell>
</table:table-row></table:table></office:spreadsheet></office:body></office:document>''', encoding='utf-8')
    slides = root / 'presentation.fodp'
    slides.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document {namespaces} office:version="1.3"
office:mimetype="application/vnd.oasis.opendocument.presentation">
<office:automatic-styles><style:page-layout style:name="page"><style:page-layout-properties
svg:width="28cm" svg:height="21cm"/></style:page-layout></office:automatic-styles>
<office:master-styles><style:master-page style:name="Default" style:page-layout-name="page"/>
</office:master-styles><office:body><office:presentation>
<draw:page draw:name="page1" draw:master-page-name="Default">
<draw:frame svg:x="2cm" svg:y="2cm" svg:width="24cm" svg:height="8cm">
<draw:text-box><text:p>{MARKER}</text:p></draw:text-box></draw:frame>
</draw:page></office:presentation></office:body></office:document>''', encoding='utf-8')
    return sheet, slides


def fixtures(root, ffmpeg, office, env):
    result = []
    image = Image.new('RGB', (320, 240), '#ed713d')
    ImageDraw.Draw(image).text((15, 20), MARKER, fill='black')
    for ext in INPUTS['image']:
        path = root / f'image.{ext}'
        image.save(path)
        result.append(('image', path))
    audio = root / 'tone.wav'
    with wave.open(str(audio), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        import math
        import struct
        stream.writeframes(b''.join(struct.pack('<h', int(10000*math.sin(index*math.tau*440/16000)))
                                   for index in range(8000)))
    video = root / 'seed.mp4'
    run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=orange:s=160x120:r=25:d=0.5',
         '-i', audio, '-c:v', 'libx264', '-c:a', 'aac', '-shortest', video], env)
    for kind, source in [('video', video), ('audio', audio)]:
        for ext in INPUTS[kind]:
            path = root / f'{kind}.{ext}'
            codecs = []
            if kind == 'video':
                codecs = {'webm': ['-c:v', 'libvpx-vp9', '-c:a', 'libopus'],
                          'm4v': ['-c:v', 'libx264', '-c:a', 'aac', '-f', 'mp4'],
                          'wmv': ['-c:v', 'wmv2', '-c:a', 'wmav2'],
                          'mpeg': ['-c:v', 'mpeg2video', '-c:a', 'mp2', '-ar', '44100'],
                          'mpg': ['-c:v', 'mpeg2video', '-c:a', 'mp2', '-ar', '44100']}.get(
                              ext, ['-c:v', 'libx264', '-c:a', 'aac'])
            else:
                codecs = {'wma': ['-c:a', 'wmav2'], 'mka': ['-c:a', 'flac']}.get(ext, [])
            run([ffmpeg, '-v', 'error', '-i', source, *codecs, path], env)
            result.append((kind, path))
    document = root / 'document.txt'
    document.write_text(MARKER, encoding='utf-8')
    result.append(('document', document))
    sheet, slides = office_seeds(root)
    for kind, source in [('document', document), ('sheet', sheet), ('slides', slides)]:
        for ext in INPUTS[kind]:
            if kind == 'document' and ext == 'txt':
                continue
            if ext in ['csv', 'tsv']:
                path = root / f'spreadsheet.{ext}'
                path.write_text(f'{MARKER}{"," if ext == "csv" else chr(9)}42\n', encoding='utf-8')
            else:
                path = office_export(office, source, ext, root / f'seed-{kind}-{ext}', env)
            result.append((kind, path))
    import pymupdf
    pdf = root / 'pages.pdf'
    with pymupdf.open() as content:
        content.new_page().insert_text((40, 60), MARKER)
        content.save(pdf)
    result.append(('pdf', pdf))
    for ext in INPUTS['subtitle']:
        path = root / f'captions.{ext}'
        path.write_text((f'1\n00:00:00,000 --> 00:00:00,500\n{MARKER}\n' if ext == 'srt' else
                         f'WEBVTT\n\n00:00:00.000 --> 00:00:00.500\n{MARKER}\n'), encoding='utf-8')
        result.append(('subtitle', path))
    for ext in INPUTS['archive']:
        path = root / f'archive.{ext}'
        if ext == 'zip':
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('document.txt', MARKER)
        else:
            with tarfile.open(path, 'w:gz' if ext in ['tar.gz', 'tgz'] else 'w') as archive:
                archive.add(document, arcname='document.txt')
        result.append(('archive', path))
    return result


def verify(executable, report, *, require_bundle=True):
    executable = Path(executable).resolve()
    assert executable.is_file(), executable
    env = os.environ.copy()
    for key in ['CITRICA_WINDOWS_ENGINES', 'CITRICA_TOOL_DIR', 'CITRICA_OFFICE_ENGINE', 'CITRICA_OCR_DIR']:
        env.pop(key, None)
    if require_bundle:
        env['PATH'] = str(Path(env.get('SystemRoot', 'C:/Windows')) / 'System32')
    doctor = json.loads(run([executable, '--doctor'], env))
    internal = executable.parent / '_internal'
    for name in ['ffmpeg', 'libreoffice']:
        assert doctor['dependencies'].get(name), (name, doctor)
        if require_bundle:
            assert Path(doctor['dependencies'][name]).resolve().is_relative_to(internal), doctor
    assert doctor['tools']['text'], doctor
    ffmpeg, office = (doctor['dependencies'][key] for key in ['ffmpeg', 'libreoffice'])
    cases = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='citrica-parity-') as directory:
        root = Path(directory)
        for kind, source in fixtures(root, ffmpeg, office, env):
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            advertised = json.loads(run([executable, source, '--formats'], env))
            assert advertised == FORMATS[kind], (source.name, advertised, FORMATS[kind])
            for fmt in advertised:
                destination = root / 'outputs' / source.name / fmt
                result = run([executable, source, '--to', fmt, '--output', destination], env)
                outputs = [Path(line) for line in result.splitlines()]
                assert outputs and all(p.is_file() and p.stat().st_size > 0 for p in outputs), result
                if fmt == 'pdf':
                    from pypdf import PdfReader
                    assert len(PdfReader(outputs[0]).pages) > 0
                elif fmt in ['docx', 'xlsx', 'pptx', 'odt', 'ods', 'odp']:
                    with zipfile.ZipFile(outputs[0]) as content:
                        assert content.testzip() is None
                elif fmt in ['png', 'jpg', 'webp', 'avif', 'heic', 'tiff', 'bmp', 'gif']:
                    with Image.open(outputs[0]) as content:
                        content.verify()
                cases.append({'input': source.suffix.lstrip('.'), 'family': kind, 'output': fmt,
                              'files': len(outputs), 'success': True})
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before, source
            print(f'Paridade offline: {source.name} → {", ".join(advertised)}', flush=True)
        # OCR uses the bundled DLL, Leptonica/codec dependencies and traineddata;
        # a boolean doctor probe alone cannot establish that its DLL loads.
        image = Image.new('RGB', (1000, 200), 'white')
        from PIL import ImageFont
        ImageDraw.Draw(image).text((25, 40), MARKER, fill='black', font=ImageFont.load_default(size=42))
        source = root / 'ocr.png'
        image.save(source)
        payload = json.dumps({'op': 'tool', 'tool': 'redact_text', 'paths': [str(source)]})
        ocr = json.loads(run([executable, '--desktop-request', payload], env))
        assert ocr.get('outputs') and all(Path(p).is_file() for p in ocr['outputs']), ocr
        with Image.open(ocr['outputs'][0]) as redacted:
            assert redacted.convert('RGB').tobytes() != image.tobytes(), 'OCR não encontrou o texto do fixture.'
    data = {'version': doctor['version'], 'offline': True, 'path_isolated': require_bundle,
            'input_extensions': sum(map(len, INPUTS.values())), 'conversions': len(cases),
            'duration_seconds': round(time.monotonic() - started, 2),
            'ocr_redaction': True, 'originals_preserved': True, 'cases': cases}
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(cases)} conversões offline verificadas; relatório: {report}', flush=True)
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--report', type=Path, default=Path('release/citrica-windows-engine-parity.json'))
    parser.add_argument('--system-engines', action='store_true',
                        help='comparar a mesma matriz no Linux com os motores instalados no sistema')
    args = parser.parse_args()
    verify(args.executable, args.report, require_bundle=not args.system_engines)
