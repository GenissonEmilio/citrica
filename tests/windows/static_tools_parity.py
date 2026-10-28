"""Check packaged image/PDF tools through the same JSON API as the wheel.

Usage: python tests/windows/static_tools_parity.py path/to/citrica-cli.exe --report result.json
Only the executable performs application operations. Python dependencies below
create synthetic fixtures and independently inspect outputs; no application
modules are imported. Windows application calls receive a system-only PATH.
The astronaut fixture is public-domain NASA imagery; see tests/fixtures/README.md.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

if os.name == 'nt':
    # Load oracle runtime DLLs from Qt before PyMuPDF without installing a
    # system C++ runtime that could conceal a missing packaged dependency.
    __import__('PySide6.QtCore')

import pymupdf
import qrcode
from PIL import Image, ImageChops, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo
from pypdf import PdfReader

IMAGE_TOOLS = {'compress', 'crop', 'adjust', 'annotate', 'background', 'redact', 'metadata',
               'edit_metadata', 'strip', 'images_pdf', 'collage', 'qr', 'redact_faces',
               'redact_text', 'target_size'}
PDF_TOOLS = {'compress', 'metadata', 'edit_metadata', 'strip', 'target_size', 'split_pdf', 'reorder_pdf'}
IMAGE_FORMATS = {'png', 'jpg', 'webp', 'avif', 'heic', 'tiff', 'bmp', 'gif', 'pdf'}
PDF_FORMATS = {'png', 'jpg', 'docx', 'txt', 'pdf'}
PAGE_MARKERS = ['CITRICA PAGE ONE 1234', 'CITRICA PAGE TWO 5678', 'CITRICA PAGE THREE 9012']
QR_MARKER = 'https://github.com/GenissonEmilio/citrica?qa=unicode-João'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rgb(path):
    with Image.open(path) as image:
        return image.convert('RGB')


def pdf_contents(path):
    reader = PdfReader(path)
    return reader, [(page.extract_text() or '').strip() for page in reader.pages]


def fixtures(root):
    paths = {}
    image = Image.new('RGB', (320, 200), '#c85028')
    draw = ImageDraw.Draw(image)
    for row in range(0, 200, 8):
        for column in range(0, 320, 8):
            if (row + column) % 16 == 0:
                draw.rectangle((column, row, column + 7, row + 7), fill='#1464dc')
    tags = PngInfo()
    tags.add_itxt('Author', 'Origem João')
    exif = Image.Exif()
    exif[315] = 'ORIGINAL AUTHOR'
    exif[270] = 'ORIGINAL TITLE'
    paths['image'] = root / 'fotografia com acentuação.png'
    image.save(paths['image'], pnginfo=tags, exif=exif)
    paths['second'] = root / 'segunda imagem azul.png'
    Image.new('RGB', (320, 200), '#0000ff').save(paths['second'])
    paths['noise'] = root / 'ruído para tamanho alvo.png'
    Image.effect_noise((400, 300), 100).convert('RGB').save(paths['noise'])
    paths['face'] = root / 'rosto da astronauta.png'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'fixtures/astronaut.png', paths['face'])
    paths['text'] = root / 'texto confidencial João.png'
    text_image = Image.new('RGB', (800, 180), 'white')
    ImageDraw.Draw(text_image).text((30, 40), 'PRIVATE TEST 1234', fill='black',
                                   font=ImageFont.load_default(size=48))
    text_image.save(paths['text'])
    paths['qr'] = root / 'código QR Unicode.png'
    qrcode.make(QR_MARKER).save(paths['qr'])
    paths['pdf'] = root / 'páginas com conteúdo.pdf'
    buffer = io.BytesIO()
    Image.effect_noise((600, 400), 100).convert('RGB').save(buffer, format='JPEG', quality=100)
    with pymupdf.open() as document:
        for index, marker in enumerate(PAGE_MARKERS):
            page = document.new_page(width=300 + 40 * index, height=420 + 40 * index)
            page.insert_text((25, 35), marker, fontsize=10)
            if index == 0:
                page.insert_image(pymupdf.Rect(25, 70, 275, 240), stream=buffer.getvalue())
        document.set_metadata({'author': 'Origem João', 'title': 'Documento de validação'})
        document.save(paths['pdf'])
    paths['pdf_second'] = root / 'segundo documento.pdf'
    with pymupdf.open() as document:
        document.new_page(width=200, height=300).insert_text((20, 40), 'CITRICA SECOND DOCUMENT')
        document.save(paths['pdf_second'])
    paths['animated'] = root / 'animação recusada.gif'
    Image.new('RGB', (30, 30), 'orange').save(paths['animated'], save_all=True,
        append_images=[Image.new('RGB', (30, 30), 'blue')], duration=100, loop=0)
    return paths


class Check:
    def __init__(self, executable):
        self.executable = executable
        self.env = os.environ.copy()
        for key in ['CITRICA_WINDOWS_ENGINES', 'CITRICA_TOOL_DIR', 'CITRICA_OFFICE_ENGINE', 'CITRICA_OCR_DIR']:
            self.env.pop(key, None)
        if os.name == 'nt':
            self.env['PATH'] = str(Path(self.env.get('SystemRoot', 'C:/Windows')) / 'System32')
        self.cases = []
        self.palettes = []
        self.originals = {}

    def unchanged(self):
        assert all(digest(path) == before for path, before in self.originals.items()), 'Original foi modificado.'

    def call(self, payload, *, failure=False):
        proc = subprocess.run([str(self.executable), '--desktop-request', json.dumps(payload, ensure_ascii=False)],
            check=False, capture_output=True, text=True, encoding='utf-8', errors='replace',
            env=self.env, timeout=120)
        try:
            result = json.loads(proc.stdout)
        except ValueError as exc:
            raise AssertionError(f'JSON inválido: {proc.stdout[-1000:]}\n{proc.stderr[-2000:]}') from exc
        if failure:
            assert proc.returncode != 0 and result.get('error'), (payload, proc.returncode, result, proc.stderr)
        else:
            assert proc.returncode == 0 and not result.get('error'), (payload, proc.returncode, result, proc.stderr)
        self.unchanged()
        return result

    def palette(self, label, paths, tools, formats):
        result = self.call({'op': 'palette', 'paths': list(map(str, paths))})
        actual_tools = [item['id'] for item in result['modes']['tools']]
        actual_formats = [item['id'] for item in result['modes']['convert']]
        assert len(actual_tools) == len(set(actual_tools)) and set(actual_tools) == tools, (label, actual_tools, tools)
        assert len(actual_formats) == len(set(actual_formats)) and set(actual_formats) == formats, (label, actual_formats)
        self.palettes.append({'selection': label, 'tools': actual_tools, 'formats': actual_formats, 'success': True})
        print(f'Paleta {label}: {len(tools)} ferramentas verificadas.', flush=True)

    def tool(self, family, tool, paths, params=None, *, variant=None, failure=False):
        result = self.call({'op': 'tool', 'tool': tool, 'paths': list(map(str, paths)), 'params': params or {}},
                           failure=failure)
        entry = {'family': family, 'tool': tool, 'variant': variant or tool,
                 'expected_rejection': failure, 'success': False}
        self.cases.append(entry)
        if failure:
            entry['success'] = True
            return result
        if tool not in {'metadata', 'qr'}:
            outputs = [Path(path) for path in result.get('outputs', [])]
            assert outputs and all(path.is_file() and path.stat().st_size > 0 for path in outputs), result
            assert not any(path in self.originals for path in outputs), 'Saída sobrescreveu original.'
            result['outputs'] = outputs
        return result

    def passed(self):
        self.cases[-1]['success'] = True
        entry = self.cases[-1]
        print(f"Ferramenta {entry['family']}/{entry['variant']}: validada.", flush=True)


def image_cases(check, paths):
    source = paths['image']
    original = rgb(source)
    for tool in ['compress', 'strip']:
        output = check.tool('image', tool, [source])['outputs'][0]
        assert rgb(output).size == original.size
        assert rgb(output).tobytes() == original.tobytes()
        with Image.open(output) as image:
            assert not image.getexif() and 'Author' not in image.info
        check.passed()
    output = check.tool('image', 'crop', [source], {'rect': '10,20,100,80'})['outputs'][0]
    assert rgb(output).size == (100, 80) and rgb(output).tobytes() == original.crop((10, 20, 110, 100)).tobytes()
    check.passed()
    output = check.tool('image', 'adjust', [source], {'brightness': 0.5})['outputs'][0]
    assert rgb(output).size == original.size
    assert rgb(output).getpixel((4, 4)) == tuple(value // 2 for value in original.getpixel((4, 4)))
    check.passed()
    for shape in ['text', 'arrow', 'rectangle', 'ellipse', 'number']:
        output = check.tool('image', 'annotate', [source],
            {'shape': shape, 'text': 'Cítrica 1', 'position': '20,20', 'rect': '20,20,100,80', 'color': '#ff0000'},
            variant='annotate_' + shape)['outputs'][0]
        assert rgb(output).size == original.size and ImageChops.difference(rgb(output), original).getbbox()
        check.passed()
    output = check.tool('image', 'background', [source], {'padding': 20, 'color': '#ffff00'},
                        variant='background_solid')['outputs'][0]
    assert rgb(output).size == (360, 240) and rgb(output).getpixel((0, 0)) == (255, 255, 0)
    assert rgb(output).crop((20, 20, 340, 220)).tobytes() == original.tobytes()
    check.passed()
    output = check.tool('image', 'background', [source],
        {'color': '#ff0000', 'color2': '#0000ff', 'aspect': '16:9', 'radius': 30},
        variant='background_gradient_aspect_radius')['outputs'][0]
    image = rgb(output)
    assert abs(image.width / image.height - 16 / 9) < 0.01
    assert image.getpixel((0, 0)) == (255, 0, 0) and image.getpixel((0, image.height - 1)) == (0, 0, 255)
    assert image.getpixel(((image.width - 320) // 2, (image.height - 200) // 2)) != original.getpixel((0, 0))
    check.passed()
    output = check.tool('image', 'background', [source], {'background_image': str(paths['second'])},
                        variant='background_image')['outputs'][0]
    assert rgb(output).getpixel((0, 0)) == (0, 0, 255)
    check.passed()
    for style in ['solid', 'blur']:
        output = check.tool('image', 'redact', [source], {'rect': '20,20,60,60', 'style': style},
                            variant='redact_' + style)['outputs'][0]
        image = rgb(output)
        assert image.size == original.size and image.getpixel((0, 0)) == original.getpixel((0, 0))
        if style == 'solid':
            assert image.getpixel((45, 45)) == (0, 0, 0)
        else:
            assert ImageChops.difference(image.crop((20, 20, 80, 80)),
                                         original.crop((20, 20, 80, 80))).getbbox()
        check.passed()
    metadata = json.loads(check.tool('image', 'metadata', [source])['text'])[source.name]
    assert metadata['size'] == [320, 200] and metadata['exif']['315'] == 'ORIGINAL AUTHOR'
    assert metadata['text']['Author'] == 'Origem João'
    check.passed()
    output = check.tool('image', 'edit_metadata', [source], {'author': 'João Cítrica', 'title': 'Título ç 123'})['outputs'][0]
    with Image.open(output) as image:
        assert image.info['Author'] == 'João Cítrica' and image.info['Title'] == 'Título ç 123'
    check.passed()
    output = check.tool('image', 'images_pdf', [source, paths['second']])['outputs'][0]
    reader = PdfReader(output)
    assert len(reader.pages) == 2 and all(float(page.mediabox.width) == 320 for page in reader.pages)
    check.passed()
    output = check.tool('image', 'collage', [source, paths['second']],
                        {'columns': 2, 'cell_width': 100, 'spacing': 10})['outputs'][0]
    assert rgb(output).size == (230, 120) and rgb(output).getpixel((170, 60)) == (0, 0, 255)
    check.passed()
    assert check.tool('image', 'qr', [paths['qr']])['text'] == QR_MARKER
    check.passed()
    for tool, path in [('redact_faces', paths['face']), ('redact_text', paths['text'])]:
        for style in ['solid', 'blur']:
            output = check.tool('image', tool, [path], {'style': style}, variant=f'{tool}_{style}')['outputs'][0]
            before, after = rgb(path), rgb(output)
            assert before.size == after.size and ImageChops.difference(before, after).getbbox(), tool
            if tool == 'redact_faces' and style == 'solid':
                assert before.getpixel((226, 113)) != (0, 0, 0) and after.getpixel((226, 113)) == (0, 0, 0)
            if tool == 'redact_text' and style == 'solid':
                assert sum(old != (0, 0, 0) and new == (0, 0, 0)
                           for old, new in zip(before.get_flattened_data(), after.get_flattened_data())) > 100
            check.passed()
    output = check.tool('image', 'target_size', [paths['noise']], {'target_kb': 4})['outputs'][0]
    assert 0 < output.stat().st_size <= 4096 and rgb(output).width > 0
    check.passed()


def pdf_cases(check, paths):
    source = paths['pdf']
    metadata = json.loads(check.tool('pdf', 'metadata', [source])['text'])[source.name]
    assert metadata['pages'] == 3 and metadata['metadata']['/Author'] == 'Origem João'
    check.passed()
    for tool in ['compress', 'strip', 'edit_metadata', 'target_size']:
        params = {'author': 'João Cítrica', 'title': 'Título PDF'} if tool == 'edit_metadata' else (
            {'target_kb': 100} if tool == 'target_size' else {})
        output = check.tool('pdf', tool, [source], params)['outputs'][0]
        reader, texts = pdf_contents(output)
        assert len(reader.pages) == 3 and all(marker in text for marker, text in zip(PAGE_MARKERS, texts))
        if tool == 'edit_metadata':
            assert reader.metadata.author == 'João Cítrica' and reader.metadata.title == 'Título PDF'
        elif tool == 'target_size':
            assert 0 < output.stat().st_size <= 100 * 1024
        else:
            assert not reader.metadata.get('/Author') and not reader.metadata.get('/Title')
        check.passed()
    outputs = check.tool('pdf', 'split_pdf', [source])['outputs']
    assert len(outputs) == 3
    for marker, output in zip(PAGE_MARKERS, outputs):
        reader, texts = pdf_contents(output)
        assert len(reader.pages) == 1 and marker in texts[0]
    check.passed()
    output = check.tool('pdf', 'reorder_pdf', [source], {'pages': '3,1,2'})['outputs'][0]
    reader, texts = pdf_contents(output)
    assert [float(page.mediabox.width) for page in reader.pages] == [380, 300, 340]
    assert all(PAGE_MARKERS[index] in text for index, text in zip([2, 0, 1], texts))
    check.passed()
    output = check.tool('pdf', 'merge_pdf', [source, paths['pdf_second']])['outputs'][0]
    reader, texts = pdf_contents(output)
    assert len(reader.pages) == 4 and 'CITRICA SECOND DOCUMENT' in texts[-1]
    assert all(marker in text for marker, text in zip(PAGE_MARKERS, texts[:3]))
    check.passed()


def rejection_cases(check, paths):
    cases = [('image', 'crop', [paths['image']], {'rect': '-1,0,50,50'}, 'negative_crop'),
             ('image', 'adjust', [paths['image']], {'brightness': 'nan'}, 'nonfinite_brightness'),
             ('pdf', 'reorder_pdf', [paths['pdf']], {'pages': '1,1,2'}, 'duplicate_page_order'),
             ('image', 'images_pdf', [paths['animated']], {}, 'animation_refused'),
             ('image', 'redact_faces', [paths['second']], {}, 'no_face_explained'),
             ('image', 'qr', [paths['second']], {}, 'no_qr_explained')]
    for family, tool, selected, params, variant in cases:
        check.tool(family, tool, selected, params, variant=variant, failure=True)
        print(f'Validação de entrada {variant}: recusa explicativa confirmada.', flush=True)


def verify(executable, report):
    executable, report = Path(executable).resolve(), Path(report)
    assert executable.is_file(), executable
    started = time.monotonic()
    check = Check(executable)
    data = {'executable': str(executable), 'platform': platform.platform(),
            'application_api': '--desktop-request', 'source_application_imports': False,
            'windows_system_only_path': os.name == 'nt', 'success': False}
    try:
        with tempfile.TemporaryDirectory(prefix='citrica-static-', ignore_cleanup_errors=os.name == 'nt') as directory:
            root = Path(directory) / 'Aplicação João - arquivos com acentuação'
            root.mkdir()
            paths = fixtures(root)
            check.originals = {path: digest(path) for path in paths.values()}
            check.palette('image', [paths['image']], IMAGE_TOOLS, IMAGE_FORMATS)
            check.palette('image_batch', [paths['image'], paths['second']], IMAGE_TOOLS, IMAGE_FORMATS)
            check.palette('pdf', [paths['pdf']], PDF_TOOLS, PDF_FORMATS)
            check.palette('pdf_batch', [paths['pdf'], paths['pdf_second']], PDF_TOOLS | {'merge_pdf'}, PDF_FORMATS)
            check.palette('mixed_image_pdf', [paths['image'], paths['pdf']],
                          {'compress', 'strip', 'metadata', 'target_size'}, {'png', 'jpg', 'pdf'})
            image_cases(check, paths)
            pdf_cases(check, paths)
            rejection_cases(check, paths)
            check.unchanged()
            assert not list(root.glob('.citrica-*')), 'Staging de ferramenta não foi limpo.'
            data['originals_sha256'] = {path.name: value for path, value in check.originals.items()}
            data['originals_preserved'] = True
            data['success'] = True
    except Exception as exc:
        data['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        data.update({'palettes': check.palettes, 'cases': check.cases, 'operations': len(check.cases),
                     'positive_operations': sum(not entry['expected_rejection'] for entry in check.cases),
                     'negative_operations': sum(entry['expected_rejection'] for entry in check.cases),
                     'duration_seconds': round(time.monotonic() - started, 2)})
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"{data['operations']} operações imagem/PDF verificadas; relatório: {report}", flush=True)
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--report', type=Path, default=Path('release/citrica-windows-static-tools-parity.json'))
    args = parser.parse_args()
    verify(args.executable, args.report)
