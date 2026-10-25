"""Fit under a requested size, publishing nothing if the limit cannot be met."""

from PIL import Image, ImageOps

from citrica.core import ConversionError, check_cancel, family, run_process


def fit(source, target, limit, cancel):
    kind = family(source)
    if limit < 256:
        raise ConversionError('O tamanho alvo precisa ser de pelo menos 256 bytes.')
    if kind == 'pdf':
        from pypdf import PdfReader, PdfWriter
        for quality in [90, 70, 50, 30, 10]:
            check_cancel(cancel)
            reader = PdfReader(source)
            if reader.is_encrypted:
                raise ConversionError('Desbloqueie uma cópia do PDF antes de comprimir.')
            writer = PdfWriter(clone_from=reader)
            for page in writer.pages:
                check_cancel(cancel)
                for entry in page.images:
                    entry.replace(entry.image, quality=quality, optimize=True)
                page.compress_content_streams()
            writer.write(target)
            if target.stat().st_size <= limit:
                return
        raise ConversionError('Não foi possível atingir o alvo sem rasterizar o PDF. Aumente o limite.')
    if kind == 'image':
        with Image.open(source) as raw:
            if getattr(raw, 'n_frames', 1) > 1:
                raise ConversionError('Imagens animadas não são suportadas nesta ferramenta.')
            image = ImageOps.exif_transpose(raw).convert('RGBA')
            # WebP is explicit in this tool's label and preserves transparency.
            for scale in [1, .85, .65, .45, .25]:
                check_cancel(cancel)
                current = image.resize((max(1, round(image.width*scale)), max(1, round(image.height*scale))))
                low, high, best = 1, 95, None
                while low <= high:
                    check_cancel(cancel)
                    quality = (low+high)//2
                    current.save(target, format='WEBP', quality=quality, method=4)
                    if target.stat().st_size <= limit:
                        best = target.read_bytes()
                        low = quality+1
                    else:
                        high = quality-1
                if best:
                    target.write_bytes(best)
                    return
        raise ConversionError('Não foi possível atingir o alvo preservando ao menos 25% da resolução.')
    from citrica.tools import media_info
    info = media_info(source)
    duration = float(info.get('format', {}).get('duration', 0))
    if duration <= 0:
        raise ConversionError('Não foi possível determinar a duração da mídia.')
    bitrate = int(limit * 8 / duration * .90)
    video = kind == 'video'
    has_audio = any(s['codec_type'] == 'audio' for s in info['streams'])
    audio_rate = 64000 if video and has_audio else 0
    for _ in range(4):
        check_cancel(cancel)
        args = ['ffmpeg', '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe', '-i', str(source)]
        if video:
            if bitrate-audio_rate < 10000:
                raise ConversionError('O alvo é pequeno demais para a duração do vídeo.')
            args += ['-c:v', 'libx264', '-b:v', str(bitrate-audio_rate), '-pix_fmt', 'yuv420p',
                     '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:a', 'aac', '-b:a', str(audio_rate or 64000)]
        else:
            rate = max(8, min(320, bitrate//1000))
            args += ['-vn', '-c:a', 'libmp3lame', '-b:a', str(rate)+'k']
        run_process(args + ['-map_metadata', '-1', str(target)], cancel)
        if target.stat().st_size <= limit:
            return
        bitrate = int(bitrate * limit / target.stat().st_size * .9)
    raise ConversionError('Não foi possível atingir o alvo. Aumente o tamanho permitido.')
