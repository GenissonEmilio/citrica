"""Exercise the packaged executable in a separate process, not the source imports."""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter


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
        print("Binário empacotado: JPG, HEIC, AVIF, PDF e renderização multipágina verificados.")
