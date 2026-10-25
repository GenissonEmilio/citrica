"""Exercise the packaged executable in a separate process, not the source imports."""

import subprocess
import json
import tempfile
import shutil
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from citrica.runtime import program


def verify(executable: Path):
    with tempfile.TemporaryDirectory(prefix="citrica-bundle-test-") as directory:
        root = Path(directory)
        source = root / "imagem com espaços.png"
        Image.new("RGBA", (80, 40), (230, 110, 50, 130)).save(source)
        for fmt in ["jpg", "heic", "avif", "pdf"]:
            result = subprocess.run([str(executable), str(source), "--to", fmt],
                                    check=True, capture_output=True, text=True)
            output = Path(result.stdout.strip())
            assert output.is_file(), result.stdout
            if fmt == "pdf":
                assert len(PdfReader(output).pages) == 1
            else:
                assert output.stat().st_size > 0
        source_pdf = root / "pages.pdf"
        with PdfWriter() as writer:
            writer.add_blank_page(200, 100)
            writer.add_blank_page(200, 100)
            writer.write(source_pdf)
        result = subprocess.run([str(executable), str(source_pdf), "--to", "png"],
                                check=True, capture_output=True, text=True)
        outputs = result.stdout.strip().splitlines()
        assert len(outputs) == 2
        for output in outputs:
            with Image.open(output) as image:
                assert image.width > 0
        face = root / 'face.png'
        fixture = Path(__file__).resolve().parents[1] / 'tests/fixtures/astronaut.png'
        face.write_bytes(fixture.read_bytes())
        from PIL import ImageDraw, ImageFont
        text_image = Image.new('RGB', (800, 180), 'white')
        ImageDraw.Draw(text_image).text((30, 40), 'PRIVATE TEST 1234', font=ImageFont.load_default(size=48), fill='black')
        text_file = root / 'private.png'
        text_image.save(text_file)
        for tool, path in [('redact_faces', face), ('redact_text', text_file), ('background', source)]:
            payload = json.dumps({'op': 'tool', 'tool': tool, 'paths': [str(path)]})
            proc = subprocess.run([str(executable), '--desktop-request', payload],
                                  check=True, capture_output=True, text=True)
            assert all(Path(p).is_file() for p in json.loads(proc.stdout)['outputs'])
        if shutil.which('ffmpeg'):
            video = root / 'video.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=orange:s=160x120:d=2',
                            '-c:v', 'libx264', str(video)], check=True)
            payload = json.dumps({'op': 'tool', 'tool': 'speed', 'paths': [str(video)], 'params': {'factor': 2}})
            proc = subprocess.run([str(executable), '--desktop-request', payload],
                                  check=True, capture_output=True, text=True)
            assert all(Path(p).is_file() for p in json.loads(proc.stdout)['outputs'])
        if program('libreoffice'):
            text = root / 'document.txt'
            text.write_text('Citrica packaged Office verification')
            proc = subprocess.run([str(executable), str(text), '--to', 'docx'],
                                  check=True, capture_output=True, text=True)
            docx = Path(proc.stdout.strip())
            proc = subprocess.run([str(executable), str(docx), '--to', 'pdf'],
                                  check=True, capture_output=True, text=True)
            assert 'Citrica' in PdfReader(proc.stdout.strip()).pages[0].extract_text()
        print('Binário empacotado: FFmpeg/ffprobe e LibreOffice externos verificados quando instalados.')
        print('Binário empacotado: detecção local de rostos/texto e ferramentas verificadas.')
        print("Binário empacotado: JPG, HEIC, AVIF, PDF e renderização multipágina verificados.")
