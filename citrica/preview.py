"""Small local previews for the Shell. Large originals never enter Shell's image loader."""
import hashlib
import os
import tempfile
from pathlib import Path

from citrica.core import family


def selection_info(paths):
    if not paths:
        return {'count': 0, 'label': '', 'bytes': 0, 'preview': None, 'icon': 'document-open-symbolic'}
    kind = family(paths[0])
    icons = {'image': 'image-x-generic', 'pdf': 'application-pdf', 'video': 'video-x-generic',
             'audio': 'audio-x-generic', 'archive': 'package-x-generic'}
    result = {'count': len(paths), 'label': paths[0].name if len(paths) == 1 else f'{len(paths)} arquivos',
              'bytes': sum(p.stat().st_size for p in paths if p.is_file()), 'preview': None,
              'icon': icons.get(kind, 'text-x-generic') if len(paths) == 1 else 'edit-copy-symbolic'}
    if len(paths) != 1 or not paths[0].is_file():
        return result
    source = paths[0]
    cache = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache'))
    candidate = source if kind == 'image' else None
    if candidate is None:
        thumb_name = hashlib.md5(source.as_uri().encode(), usedforsecurity=False).hexdigest() + '.png'
        candidate = next((p for level in ['large', 'normal', 'x-large']
                          if (p := cache / 'thumbnails' / level / thumb_name).is_file() and
                          p.stat().st_mtime >= source.stat().st_mtime), None)
    if candidate is None:
        return result
    try:
        from PIL import Image, ImageDraw, ImageOps
        stat = source.stat()
        key = hashlib.sha256(f'v2:{source}:{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()[:32]
        folder = cache / 'citrica/previews'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        output = folder / (key + '.png')
        if not output.is_file():
            with Image.open(candidate) as raw:
                if raw.width * raw.height > 100_000_000 or getattr(raw, 'n_frames', 1) > 1:
                    return result
                image = ImageOps.exif_transpose(raw).convert('RGBA')
                image.thumbnail((128, 128), Image.Resampling.LANCZOS)
                mask = Image.new('L', image.size)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1),
                                                       radius=8, fill=255)
                # FileIcon has a square allocation. Pad transparently instead of
                # stretching a landscape/portrait thumbnail into that square.
                from PIL import ImageChops
                image.putalpha(ImageChops.multiply(image.getchannel('A'), mask))
                square = Image.new('RGBA', (128, 128))
                square.paste(image, ((128 - image.width) // 2, (128 - image.height) // 2))
                with tempfile.NamedTemporaryFile(dir=folder, suffix='.png', delete=False) as temp:
                    staging = Path(temp.name)
                try:
                    square.save(staging, format='PNG')
                    staging.replace(output)
                finally:
                    staging.unlink(missing_ok=True)
        result['preview'] = str(output)
        for stale in sorted(folder.glob('*.png'), key=lambda p: p.stat().st_mtime, reverse=True)[64:]:
            stale.unlink(missing_ok=True)
    except (OSError, ValueError, Image.DecompressionBombError):
        pass  # A preview failure must never hide valid conversion options.
    return result
