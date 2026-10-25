import hashlib
import shutil
import subprocess
import tarfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from citrica.core import Cancelled, ConversionError, Options, common_formats, convert, merge_pdfs


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "foto com espaços.png"
    img = Image.new("RGBA", (160, 80), (240, 110, 40, 120))
    exif = Image.Exif()
    exif[315] = "Private Author"
    img.save(path, exif=exif)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("fmt", ["png", "jpg", "webp", "tiff", "bmp", "gif", "avif", "heic", "pdf"])
def test_image_formats_and_original_preserved(image, fmt):
    original = digest(image)
    output = convert(image, fmt, opts=Options(max_width=80))[0]
    assert output != image
    assert digest(image) == original
    if fmt == "pdf":
        assert len(PdfReader(output).pages) == 1
    else:
        with Image.open(output) as result:
            assert result.size == (80, 40)
            assert 315 not in result.getexif()
            assert 34853 not in result.getexif()


def test_keep_metadata(image):
    output = convert(image, "jpg", opts=Options(strip_metadata=False))[0]
    with Image.open(output) as result:
        assert result.getexif()[315] == "Private Author"


def test_concurrent_same_name_never_clobbers(image):
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(lambda _: convert(image, "jpg")[0], range(8)))
    assert len(set(outputs)) == 8
    assert all(p.is_file() for p in outputs)


def test_cancel_leaves_no_output(image):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        convert(image, "jpg", cancel=cancel)
    assert list(image.parent.glob("*.jpg")) == []


def test_corrupt_input_cleanup(tmp_path):
    source = tmp_path / "broken.png"
    source.write_bytes(b"not an image")
    with pytest.raises(ConversionError):
        convert(source, "jpg")
    assert not list(tmp_path.glob(".citrica-*"))
    assert not list(tmp_path.glob("*.jpg"))


def test_animated_image_rejected_without_silent_frame_loss(tmp_path):
    source = tmp_path / "animated.gif"
    Image.new("RGB", (20, 20), "red").save(source, save_all=True,
                                         append_images=[Image.new("RGB", (20, 20), "blue")], duration=200)
    with pytest.raises(ConversionError, match="animada"):
        convert(source, "png")


def make_pdf(path, pages=2):
    with PdfWriter() as writer:
        for _ in range(pages):
            writer.add_blank_page(width=200, height=100)
        writer.add_metadata({"/Author": "Private"})
        writer.write(path)
    return path


def test_pdf_all_pages_and_merge(tmp_path):
    source = make_pdf(tmp_path / "a.pdf")
    second = make_pdf(tmp_path / "b.pdf", 1)
    outputs = convert(source, "png")
    assert len(outputs) == 2
    assert outputs[0].name == "a-p001.png"
    result = merge_pdfs([source, second])[0]
    assert len(PdfReader(result).pages) == 3
    stripped = convert(source, "pdf")[0]
    assert "/Author" not in PdfReader(stripped).metadata


def test_encrypted_pdf(tmp_path):
    source = tmp_path / "secret.pdf"
    with PdfWriter() as writer:
        writer.add_blank_page(200, 100)
        writer.encrypt("secret")
        writer.write(source)
    with pytest.raises(ConversionError, match="senha"):
        convert(source, "png")


def test_subtitle_roundtrip(tmp_path):
    source = tmp_path / "legenda.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,500\nOlá Linux!\n\n2\n00:00:03,000 --> 00:00:04,000\nCítrica.\n")
    vtt = convert(source, "vtt")[0]
    assert vtt.read_text().startswith("WEBVTT\n\n00:00:01.000")
    srt = convert(vtt, "srt")[0]
    assert "2\n00:00:03,000 --> 00:00:04,000\nCítrica." in srt.read_text()
    assert convert(vtt, "txt")[0].read_text() == "Olá Linux!\n\nCítrica.\n"


def test_text_to_pdf_paginates(tmp_path):
    import pymupdf
    source = tmp_path / "long.txt"
    source.write_text("Olá Linux — ç ã é <script>\n" * 200, encoding="utf-8")
    output = convert(source, "pdf")[0]
    with pymupdf.open(output) as doc:
        assert len(doc) > 1
        text = "".join(page.get_text() for page in doc)
        assert text.count("Olá") == 200
        assert "<script>" in text


def test_archive_roundtrip(tmp_path):
    source = tmp_path / "a.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("pasta/", b"")
        archive.writestr("pasta/olá.txt", "olá linux")
    tgz = convert(source, "tar.gz")[0]
    output = convert(tgz, "zip")[0]
    with zipfile.ZipFile(output) as archive:
        assert archive.read("pasta/olá.txt").decode() == "olá linux"


@pytest.mark.parametrize("name", ["../escape.txt", "/tmp/escape.txt", "folder/../../escape", "C:\\escape"])
def test_archive_rejects_unsafe_paths(tmp_path, name):
    source = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(name, "evil")
    with pytest.raises(ConversionError, match="inseguros"):
        convert(source, "tar")


def test_archive_rejects_links(tmp_path):
    source = tmp_path / "links.tar"
    with tarfile.open(source, "w") as archive:
        info = tarfile.TarInfo("link")
        info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(ConversionError, match="links"):
        convert(source, "zip")


def test_unknown_format_and_invalid_options(image):
    with pytest.raises(ConversionError):
        convert(image, "../../oops")
    with pytest.raises(ValueError):
        Options(quality=101)
    assert common_formats([]) == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")
def test_real_audio_video_and_shell_metacharacters(tmp_path):
    audio = tmp_path / "$(touch SHOULD_NOT_EXIST); música.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.3",
                    str(audio)], check=True)
    output = convert(audio, "mp3")[0]
    assert output.stat().st_size > 100
    video = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=orange:s=64x48:d=0.3",
                    "-c:v", "libx264", str(video)], check=True)
    webm = convert(video, "webm")[0]
    assert webm.stat().st_size > 100
    assert not Path("SHOULD_NOT_EXIST").exists()


@pytest.mark.skipif(not shutil.which("libreoffice"), reason="LibreOffice not installed")
def test_office_real_roundtrip(tmp_path):
    source = tmp_path / "document.rtf"
    source.write_text(r"{\rtf1\ansi Hello Linux}")
    docx = convert(source, "docx")[0]
    assert zipfile.is_zipfile(docx)
    pdf = convert(docx, "pdf")[0]
    assert len(PdfReader(pdf).pages) == 1
