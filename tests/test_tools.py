import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from citrica.core import ConversionError
from citrica.tools import available_tools, execute, media_info


@pytest.fixture
def photos(tmp_path):
    paths = []
    for i, color in enumerate(['orange', 'blue']):
        p = tmp_path / f'foto-{i}.png'
        im = Image.new('RGBA', (320, 200), color)
        exif = Image.Exif()
        exif[315] = 'Original'
        im.save(p, exif=exif)
        paths.append(p)
    return paths


@pytest.mark.parametrize('tool,params', [
    ('compress', {'quality': 50}), ('strip', {}), ('crop', {'rect': '10,20,100,80'}),
    ('adjust', {'brightness': 0.8}), ('annotate', {'text': 'Cítrica', 'position': '20,20'}),
    ('background', {'padding': 10, 'color': '#ffff00'}),
    ('redact', {'rect': '10,10,50,50'}), ('redact', {'rect': '10,10,50,50', 'style': 'blur'}),
    ('edit_metadata', {'author': 'Cítrica', 'title': 'Teste'}), ('images_pdf', {}),
    ('collage', {'columns': 2, 'cell_width': 100}),
])
def test_image_tools_real_outputs(photos, tool, params):
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in photos]
    result = execute(tool, photos, params)
    assert result['outputs'] and all(p.is_file() for p in result['outputs'])
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in photos]
    output = result['outputs'][0]
    if tool == 'images_pdf':
        assert len(PdfReader(output).pages) == 2
    elif tool == 'crop':
        assert Image.open(output).size == (100, 80)
    elif tool == 'background':
        assert Image.open(output).size == (340, 220)
    elif tool == 'redact' and params.get('style') != 'blur':
        assert Image.open(output).getpixel((20, 20))[:3] == (0, 0, 0)
    elif tool == 'edit_metadata':
        assert Image.open(output).info['Author'] == 'Cítrica'


def test_metadata_and_qr(photos, tmp_path):
    import qrcode
    assert 'Original' in execute('metadata', photos)['text']
    qr = tmp_path / 'qr.png'
    qrcode.make('https://github.com/GenissonEmilio/citrica').save(qr)
    assert execute('qr', [qr])['text'] == 'https://github.com/GenissonEmilio/citrica'


def test_invalid_geometry_and_numbers(photos):
    for params in [{'rect': '-1,0,50,50'}, {'rect': '0,0,999,999'}, {'rect': 'oops'}]:
        with pytest.raises(ConversionError):
            execute('crop', photos, params)
    with pytest.raises(ConversionError):
        execute('adjust', photos, {'brightness': 'nan'})
    assert not list(photos[0].parent.glob('.citrica-*'))


def test_pdf_tools(tmp_path):
    source = tmp_path / 'pages.pdf'
    with PdfWriter() as writer:
        for width in [100, 200, 300]:
            writer.add_blank_page(width, 400)
        writer.write(source)
    assert len(execute('split_pdf', [source])['outputs']) == 3
    result = execute('reorder_pdf', [source], {'pages': '3,1,2'})['outputs'][0]
    assert [float(p.mediabox.width) for p in PdfReader(result).pages] == [300, 100, 200]
    output = execute('edit_metadata', [source], {'author': 'Cítrica'})['outputs'][0]
    assert PdfReader(output).metadata.author == 'Cítrica'
    assert len(PdfReader(execute('merge_pdf', [source, source])['outputs'][0]).pages) == 6
    with pytest.raises(ConversionError):
        execute('reorder_pdf', [source], {'pages': '1,1,2'})


@pytest.fixture
def media(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg não instalado')
    audio = tmp_path / 'tone.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
                    str(audio)], check=True)
    video = tmp_path / 'video.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=orange:s=160x120:d=2',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
                    '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(video)], check=True)
    return audio, video


@pytest.mark.parametrize('tool,params', [('normalize', {}), ('channels', {'channels': 2}),
    ('bleep', {'start': 0.4, 'duration': 0.5}), ('trim', {'start': 0.5, 'duration': 0.75}),
    ('speed', {'factor': 2}), ('split_media', {'seconds': 0.8}), ('join_media', {}),
    ('compress', {'quality': 50}), ('strip', {})])
def test_audio_tools(media, tool, params):
    audio, _ = media
    result = execute(tool, [audio, audio] if tool == 'join_media' else [audio], params)
    assert all(p.stat().st_size for p in result['outputs'])
    info = media_info(result['outputs'][0])
    duration = float(info['format']['duration'])
    if tool == 'trim':
        assert duration == pytest.approx(0.75, abs=0.1)
    if tool == 'speed':
        assert duration == pytest.approx(1, abs=0.1)
    if tool == 'join_media':
        assert duration == pytest.approx(4, abs=0.1)
    if tool == 'channels':
        assert info['streams'][0]['channels'] == 2
    if tool == 'split_media':
        assert len(result['outputs']) == 3


@pytest.mark.parametrize('tool,params', [('snapshot', {'time': 0.3}), ('crop', {'rect': '0,0,80,60'}),
    ('trim', {'start': 0.5, 'duration': 0.75}), ('speed', {'factor': 1.5}),
    ('split_media', {'seconds': 0.8}), ('join_media', {})])
def test_video_tools(media, tool, params):
    _, video = media
    result = execute(tool, [video, video] if tool == 'join_media' else [video], params)
    assert result['outputs']
    if tool == 'snapshot':
        assert Image.open(result['outputs'][0]).size == (160, 120)
    if tool == 'crop':
        info = media_info(result['outputs'][0])
        assert info['streams'][0]['width'] == 80


def test_tools_match_selection(photos, tmp_path):
    assert not any(t['id'] == 'merge_pdf' for t in available_tools(photos))
    assert any(t['id'] == 'qr' for t in available_tools(photos))
    with pytest.raises(ConversionError):
        execute('merge_pdf', photos)


@pytest.mark.parametrize('shape', ['arrow', 'rectangle', 'ellipse', 'number'])
def test_annotation_shapes(photos, shape):
    output = execute('annotate', [photos[0]], {'shape': shape, 'text': '1', 'rect': '20,20,100,80'})['outputs'][0]
    assert Image.open(output).tobytes() != Image.open(photos[0]).tobytes()


def test_background_gradient_aspect_and_radius(photos):
    output = execute('background', [photos[0]], {'color': '#ff0000', 'color2': '#0000ff',
        'aspect': '16:9', 'radius': 30})['outputs'][0]
    with Image.open(output) as im:
        assert im.width / im.height == pytest.approx(16/9, abs=.01)
        assert im.getpixel((0, 0)) != im.getpixel((0, im.height-1))
    output = execute('background', [photos[0]], {'background_image': str(photos[1])})['outputs'][0]
    assert Image.open(output).getpixel((0, 0))[:3] == (0, 0, 255)


def test_target_image_size(tmp_path):
    source = tmp_path / 'noise.png'
    Image.effect_noise((400, 300), 100).convert('RGB').save(source)
    output = execute('target_size', [source], {'target_kb': 4})['outputs'][0]
    assert 0 < output.stat().st_size <= 4*1024
    assert source.is_file()


@pytest.mark.parametrize('index,target', [(0, 12), (1, 32)])
def test_target_media_size(media, index, target):
    output = execute('target_size', [media[index]], {'target_kb': target})['outputs'][0]
    assert 0 < output.stat().st_size <= target*1024


@pytest.mark.parametrize('index', [0, 1])
def test_media_metadata_edit(media, index):
    output = execute('edit_metadata', [media[index]], {'author': 'Citrica', 'title': 'Test title'})['outputs'][0]
    tags = {k.lower(): v for k, v in media_info(output)['format']['tags'].items()}
    assert tags['artist'] == 'Citrica'
    assert tags['title'] == 'Test title'


def test_redact_faces_positive_fixture(tmp_path):
    source = tmp_path / 'face.png'
    shutil.copyfile(Path(__file__).parent / 'fixtures/astronaut.png', source)
    from citrica.vision import face_boxes
    boxes = face_boxes(Image.open(source))
    assert boxes
    output = execute('redact_faces', [source])['outputs'][0]
    with Image.open(output) as im:
        for left, top, right, bottom in boxes:
            assert im.getpixel(((left+right)//2, (top+bottom)//2))[:3] == (0, 0, 0)


def test_redact_text_positive_fixture(tmp_path):
    from PIL import ImageDraw, ImageFont
    from citrica.vision import text_available, text_boxes
    if not text_available():
        pytest.skip('Tesseract não instalado')
    source = tmp_path / 'private.png'
    image = Image.new('RGB', (800, 180), 'white')
    ImageDraw.Draw(image).text((30, 40), 'PRIVATE TEST 1234', font=ImageFont.load_default(size=48), fill='black')
    image.save(source)
    boxes = text_boxes(image)
    assert len(boxes) >= 3
    output = execute('redact_text', [source])['outputs'][0]
    with Image.open(output) as im:
        for left, top, right, bottom in boxes:
            assert im.getpixel(((left+right)//2, (top+bottom)//2))[:3] == (0, 0, 0)


def test_target_pdf_keeps_text(tmp_path):
    import io
    import pymupdf
    source = tmp_path / 'scan.pdf'
    image = Image.effect_noise((600, 400), 100).convert('RGB')
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=100)
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), 'CITRICA TEXT PRESERVED')
        page.insert_image(pymupdf.Rect(40, 80, 550, 420), stream=buffer.getvalue())
        doc.save(source)
    output = execute('target_size', [source], {'target_kb': 100})['outputs'][0]
    assert output.stat().st_size <= 100*1024
    assert 'CITRICA TEXT PRESERVED' in PdfReader(output).pages[0].extract_text()
