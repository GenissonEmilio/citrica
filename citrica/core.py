"""Local conversion engine. No network, shell interpolation, or source mutation."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

IMAGE = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp", "gif", "avif", "heic", "heif"}
VIDEO = {"mp4", "mov", "mkv", "avi", "webm", "wmv", "m4v", "mpeg", "mpg"}
AUDIO = {"mp3", "wav", "flac", "ogg", "opus", "m4a", "aac", "aiff", "wma"}
DOC = {"doc", "docx", "odt", "rtf", "txt"}
SHEET = {"xls", "xlsx", "ods", "csv", "tsv"}
SLIDES = {"ppt", "pptx", "odp"}
LABELS = {"image": "Imagens", "video": "Vídeo", "audio": "Áudio", "pdf": "PDF",
          "document": "Documentos", "sheet": "Planilhas", "slides": "Apresentações",
          "subtitle": "Legendas", "archive": "Arquivos compactados", "unknown": "Não compatível"}


class ConversionError(Exception):
    """A conversion failed without changing the original."""


class Cancelled(ConversionError):
    pass


@dataclass(frozen=True)
class Options:
    quality: int = 85
    max_width: int = 0
    strip_metadata: bool = True

    def __post_init__(self):
        if not 1 <= self.quality <= 100 or self.max_width < 0:
            raise ValueError("Qualidade deve estar entre 1 e 100; largura não pode ser negativa.")


def family(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if path.name.lower().endswith((".tar.gz", ".tgz", ".tar", ".zip")):
        return "archive"
    for exts, name in [(IMAGE, "image"), (VIDEO, "video"), (AUDIO, "audio"),
                       (DOC, "document"), (SHEET, "sheet"), (SLIDES, "slides"),
                       ({"pdf"}, "pdf"), ({"srt", "vtt"}, "subtitle")]:
        if ext in exts:
            return name
    return "unknown"


def dependencies() -> dict[str, str | None]:
    return {name: shutil.which(name) for name in ("ffmpeg", "libreoffice")}


def formats(path: Path) -> list[str]:
    kind = family(path)
    if kind == "image":
        Image.init()
        available = Image.SAVE
        choices = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP", "avif": "AVIF", "heic": "HEIF",
                   "tiff": "TIFF", "bmp": "BMP", "gif": "GIF", "pdf": "PDF"}
        return [ext for ext, codec in choices.items() if codec in available]
    if kind == "pdf":
        return ["png", "jpg", "txt", "pdf"]
    if kind in {"video", "audio"}:
        if not dependencies()["ffmpeg"]:
            return []
        return (["mp4", "webm", "mkv", "mov", "gif", "mp3", "wav"] if kind == "video"
                else ["mp3", "wav", "flac", "ogg", "opus", "m4a", "aiff"])
    if kind == "subtitle":
        return ["srt", "vtt", "txt"]
    if kind == "archive":
        return ["zip", "tar", "tar.gz"]
    if kind in {"document", "sheet", "slides"}:
        if dependencies()["libreoffice"]:
            return {"document": ["pdf", "docx", "odt", "txt"], "sheet": ["pdf", "xlsx", "ods", "csv"],
                    "slides": ["pdf", "pptx", "odp"]}[kind]
        return ["pdf"] if path.suffix.lower() == ".txt" else []
    return []


def common_formats(paths: list[Path]) -> list[str]:
    if not paths:
        return []
    return [fmt for fmt in formats(paths[0]) if all(fmt in formats(path) for path in paths[1:])]


def check_cancel(cancel: threading.Event):
    if cancel.is_set():
        raise Cancelled("Conversão cancelada.")


def run_process(args: list[str], cancel: threading.Event, timeout: int = 1800):
    """Use a temporary log to avoid pipe deadlocks and unbounded log memory."""
    env = os.environ.copy()
    # Qt's bundled libraries must not leak into external system executables.
    original = env.get("LD_LIBRARY_PATH_ORIG")
    if original is not None:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)
    env.pop("QT_PLUGIN_PATH", None)
    env.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
    with tempfile.TemporaryFile() as log:
        with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env) as proc:
            deadline = time.monotonic() + timeout
            try:
                while proc.poll() is None:
                    check_cancel(cancel)
                    if time.monotonic() > deadline:
                        raise ConversionError("A operação excedeu o tempo limite.")
                    cancel.wait(0.1)
            except BaseException:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise
            if proc.returncode:
                log.seek(0, 2)
                log.seek(max(0, log.tell() - 3000))
                detail = log.read().decode(errors="replace").strip()
                raise ConversionError(detail or f"O processo terminou com código {proc.returncode}.")
    check_cancel(cancel)


def publish(staged: Path, destination: Path) -> Path:
    """An atomic, no-clobber commit on the same filesystem, including concurrent jobs."""
    base, suffix = destination.stem, destination.suffix
    if destination.name.endswith(".tar.gz"):
        base, suffix = destination.name[:-7], ".tar.gz"
    index = 0
    while True:
        candidate = destination if index == 0 else destination.with_name(f"{base} ({index}){suffix}")
        try:
            os.link(staged, candidate)
            return candidate
        except FileExistsError:
            index += 1


def _image(source: Path, target: Path, opts: Options, cancel: threading.Event):
    with Image.open(source) as raw:
        if getattr(raw, "n_frames", 1) > 1:
            raise ConversionError("Imagem animada ou multipágina: exportação não disponível nesta versão.")
        image = ImageOps.exif_transpose(raw)
        preserved_exif = image.getexif().tobytes()
        if opts.max_width and image.width > opts.max_width:
            image.thumbnail((opts.max_width, max(1, round(image.height * opts.max_width / image.width))),
                            Image.Resampling.LANCZOS)
        ext = target.suffix.lower()
        if ext in {".jpg", ".pdf", ".bmp"}:
            rgba = image.convert("RGBA")
            image = Image.new("RGB", rgba.size, "white")
            image.paste(rgba, mask=rgba.getchannel("A"))
        elif ext == ".gif":
            image = image.convert("RGBA")
        kwargs = {}
        if ext in {".jpg", ".webp", ".avif", ".heic"}:
            kwargs["quality"] = opts.quality
        if ext == ".png":
            kwargs["optimize"] = True
        if not opts.strip_metadata and raw.info.get("exif") and ext in {".jpg", ".png", ".webp", ".tiff"}:
            kwargs["exif"] = preserved_exif
        # PIL can implicitly copy EXIF/info. A fresh image ensures stripping is real.
        if opts.strip_metadata:
            clean = Image.new(image.mode, image.size)
            clean.paste(image)
            image = clean
        check_cancel(cancel)
        image.save(target, **kwargs)


def _media(source: Path, target: Path, opts: Options, cancel: threading.Event):
    executable = dependencies()["ffmpeg"]
    if not executable:
        raise ConversionError("Instale FFmpeg para converter áudio e vídeo.")
    ext = target.suffix.lower().lstrip(".")
    args = [executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-protocol_whitelist", "file,pipe", "-i", str(source)]
    if opts.strip_metadata:
        args += ["-map_metadata", "-1", "-map_chapters", "-1"]
    audio = {"mp3": ["-c:a", "libmp3lame", "-q:a", "2"], "wav": ["-c:a", "pcm_s16le"],
             "flac": ["-c:a", "flac"], "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
             "opus": ["-c:a", "libopus", "-b:a", "128k"],
             "m4a": ["-c:a", "aac", "-b:a", "192k"], "aiff": ["-c:a", "pcm_s16be"]}
    if ext in audio:
        args += ["-vn"] + audio[ext]
    elif ext == "gif":
        args += ["-an", "-vf", f"fps=12,scale={opts.max_width or 640}:-1:flags=lanczos"]
    else:
        crf = str(round(40 - opts.quality * 0.25))
        if ext == "webm":
            args += ["-c:v", "libvpx-vp9", "-crf", crf, "-b:v", "0", "-c:a", "libopus"]
        else:
            args += ["-c:v", "libx264", "-crf", crf, "-preset", "medium", "-c:a", "aac"]
        # yuv420p requires even dimensions, including odd-sized source frames.
        scale = f"scale={opts.max_width}:-2," if opts.max_width else ""
        args += ["-vf", scale + "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p"]
        if ext in {"mp4", "mov"}:
            args += ["-movflags", "+faststart"]
    run_process(args + [str(target)], cancel)


def _pdf(source: Path, target: Path, opts: Options, cancel: threading.Event) -> list[Path]:
    import pymupdf
    from pypdf import PdfReader, PdfWriter

    if target.suffix == ".pdf":
        reader = PdfReader(source)
        writer = PdfWriter()
        for page in reader.pages:
            check_cancel(cancel)
            writer.add_page(page)
            writer.pages[-1].compress_content_streams()
        if not opts.strip_metadata and reader.metadata:
            writer.add_metadata({k: str(v) for k, v in reader.metadata.items() if v is not None})
        writer.write(target)
        return [target]
    outputs = []
    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise ConversionError("PDF protegido por senha. Desbloqueie uma cópia antes de converter.")
        if target.suffix == ".txt":
            with target.open("w", encoding="utf-8") as stream:
                for page in document:
                    check_cancel(cancel)
                    stream.write(page.get_text() + "\n")
            return [target]
        for index, page in enumerate(document):
            check_cancel(cancel)
            output = target.with_stem(f"{target.stem}-p{index + 1:03}")
            pix = page.get_pixmap(dpi=150, alpha=False)
            if opts.max_width and pix.width > opts.max_width:
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                image.thumbnail((opts.max_width, image.height))
                image.save(output, quality=opts.quality)
            else:
                pix.save(output, jpg_quality=opts.quality)
            outputs.append(output)
    return outputs


def _document(source: Path, target: Path, cancel: threading.Event):
    if source.suffix.lower() == ".txt" and target.suffix == ".pdf":
        import pymupdf
        text = source.read_text(encoding="utf-8-sig")
        document = pymupdf.open()
        # Story lays out Unicode text across pages without truncating long files.
        import html
        story = pymupdf.Story(html="<pre>" + html.escape(text) + "</pre>", user_css="pre {white-space: pre-wrap;}")
        writer = pymupdf.DocumentWriter(str(target))
        try:
            more = True
            while more:
                check_cancel(cancel)
                device = writer.begin_page(pymupdf.Rect(0, 0, 595, 842))
                more, _ = story.place(pymupdf.Rect(40, 40, 555, 802))
                story.draw(device)
                writer.end_page()
        finally:
            writer.close()
            document.close()
        return
    executable = dependencies()["libreoffice"]
    if not executable:
        raise ConversionError("Instale LibreOffice para converter documentos de escritório.")
    with tempfile.TemporaryDirectory(prefix="citrica-office-") as folder:
        root = Path(folder)
        run_process([executable, f"-env:UserInstallation={(root / 'profile').as_uri()}", "--headless",
                     "--convert-to", target.suffix[1:], "--outdir", str(root), str(source)], cancel, 120)
        result = root / (source.stem + target.suffix)
        if not result.is_file():
            raise ConversionError("LibreOffice não produziu o formato solicitado para este documento.")
        shutil.copyfile(result, target)


TIMING = re.compile(r"(?m)^(\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})\s+-->\s+"
                    r"(\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})[^\n]*\n")


def _subtitle(source: Path, target: Path):
    text = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    matches = list(TIMING.finditer(text))
    if not matches:
        raise ConversionError("Nenhuma legenda com marcação de tempo foi encontrada.")
    cues = []
    for i, match in enumerate(matches):
        tail = text[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        body = tail.split("\n\n", 1)[0].strip()
        cues.append((match.group(1), match.group(2), body))
    ext = target.suffix
    if ext == ".txt":
        result = "\n\n".join(body for _, _, body in cues) + "\n"
    else:
        def stamp(value):
            value = value.replace(",", ".")
            if value.count(":") == 1:
                value = "00:" + value
            return value.replace(".", ",") if ext == ".srt" else value
        result = "WEBVTT\n\n" if ext == ".vtt" else ""
        result += "\n\n".join((f"{i}\n" if ext == ".srt" else "") +
                              f"{stamp(start)} --> {stamp(end)}\n{body}"
                              for i, (start, end, body) in enumerate(cues, 1)) + "\n"
    target.write_text(result, encoding="utf-8")


def _archive(source: Path, target: Path, cancel: threading.Event):
    """Repack regular entries by streaming; never extract paths onto the filesystem."""
    from contextlib import ExitStack
    with ExitStack() as stack:
        if zipfile.is_zipfile(source):
            archive = stack.enter_context(zipfile.ZipFile(source))
            entries = [(m.filename, m.file_size, m.is_dir(), ((m.external_attr >> 16) & 0o170000) == 0o120000,
                        lambda m=m: archive.open(m)) for m in archive.infolist()]
        else:
            archive = stack.enter_context(tarfile.open(source))
            entries = []
            for m in archive:
                entries.append((m.name, m.size, m.isdir(), not (m.isfile() or m.isdir()),
                                lambda m=m: archive.extractfile(m)))
                if len(entries) > 10000:
                    raise ConversionError("Limite de 10.000 entradas por arquivo compactado.")
        if len(entries) > 10000 or sum(e[1] for e in entries) > 2 * 1024**3:
            raise ConversionError("Limite de 10.000 entradas e 2 GiB descompactados.")
        seen = set()
        for name, _, _, special, _ in entries:
            parts = PurePosixPath(name).parts
            if not parts or name.startswith("/") or ".." in parts or "\\" in name or ":" in name or special:
                raise ConversionError("Arquivo compactado contém caminhos inseguros ou links.")
            normalized = str(PurePosixPath(name))
            if normalized in seen:
                raise ConversionError("Arquivo compactado contém nomes duplicados.")
            seen.add(normalized)
        if target.suffix == ".zip":
            output = stack.enter_context(zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED))
        else:
            output = stack.enter_context(tarfile.open(target, "w:gz" if target.suffix == ".gz" else "w"))
        for name, size, directory, _, opener in entries:
            check_cancel(cancel)
            if directory:
                if isinstance(output, zipfile.ZipFile):
                    output.writestr(name.rstrip("/") + "/", b"")
                else:
                    info = tarfile.TarInfo(name)
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    output.addfile(info)
                continue
            with opener() as stream:
                if isinstance(output, zipfile.ZipFile):
                    with output.open(name, "w") as dest:
                        while chunk := stream.read(1024 * 1024):
                            check_cancel(cancel)
                            dest.write(chunk)
                else:
                    info = tarfile.TarInfo(name)
                    info.size, info.mode = size, 0o644
                    output.addfile(info, stream)


def convert(source: Path, fmt: str, output_dir: Path | None = None, opts: Options | None = None,
            cancel: threading.Event | None = None) -> list[Path]:
    source = source.expanduser().resolve()
    opts, cancel = opts or Options(), cancel or threading.Event()
    check_cancel(cancel)
    if not source.is_file():
        raise ConversionError(f"Arquivo não encontrado: {source}")
    fmt = fmt.lower().lstrip(".")
    if fmt not in formats(source):
        raise ConversionError(f"Conversão para {fmt!r} não disponível para {source.name}.")
    destination = (output_dir or source.parent).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    stem = source.name[:-7] if source.name.lower().endswith(".tar.gz") else source.stem
    try:
        with tempfile.TemporaryDirectory(prefix=".citrica-", dir=destination) as directory:
            target = Path(directory) / f"{stem}.{fmt}"
            kind = family(source)
            staged = [target]
            if kind == "image":
                _image(source, target, opts, cancel)
            elif kind in {"video", "audio"}:
                _media(source, target, opts, cancel)
            elif kind == "pdf":
                staged = _pdf(source, target, opts, cancel)
            elif kind in {"document", "sheet", "slides"}:
                _document(source, target, cancel)
            elif kind == "subtitle":
                _subtitle(source, target)
            elif kind == "archive":
                _archive(source, target, cancel)
            check_cancel(cancel)
            if not staged or any(not item.is_file() or item.stat().st_size == 0 for item in staged):
                raise ConversionError("A conversão não produziu um arquivo válido.")
            committed = []
            try:
                for item in staged:
                    committed.append(publish(item, destination / item.name))
            except BaseException:
                for item in committed:
                    item.unlink(missing_ok=True)
                raise
            return committed
    except (Cancelled, ConversionError):
        raise
    except Exception as error:
        raise ConversionError(str(error)) from error


def merge_pdfs(sources: list[Path], output_dir: Path | None = None,
               cancel: threading.Event | None = None) -> list[Path]:
    from pypdf import PdfWriter
    cancel = cancel or threading.Event()
    if len(sources) < 2 or any(family(p) != "pdf" or not p.is_file() for p in sources):
        raise ConversionError("Selecione pelo menos dois PDFs para unir.")
    folder = (output_dir or sources[0].parent).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix=".citrica-", dir=folder) as directory:
            target = Path(directory) / "documentos-unidos.pdf"
            with PdfWriter() as writer:
                for source in sources:
                    check_cancel(cancel)
                    writer.append(source)
                writer.write(target)
            check_cancel(cancel)
            return [publish(target, folder / target.name)]
    except (Cancelled, ConversionError):
        raise
    except Exception as error:
        raise ConversionError(str(error)) from error


def batch(paths: list[Path], fmt: str, output_dir: Path | None, opts: Options,
          cancel: threading.Event, progress: Callable[[Path, list[Path], str], None]):
    for path in paths:
        if cancel.is_set():
            break
        try:
            result = convert(path, fmt, output_dir, opts, cancel)
            progress(path, result, "")
        except Cancelled:
            progress(path, [], "Cancelado")
            break
        except ConversionError as error:
            progress(path, [], str(error))
