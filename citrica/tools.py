"""File tools shared by the desktop wheel, compact dialogs and integration tests."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from citrica.core import ConversionError, Options, check_cancel, convert, family, merge_pdfs, publish, run_process

# All geometry is explicit in source pixels; all times are seconds. No destructive
# edits are performed: even metadata edits and compression publish a new copy.
TOOLS = {
    'compress': {'label': 'Comprimir', 'families': ['image', 'video', 'audio', 'pdf'],
                 'fields': [('quality', 'Qualidade (1–100)', '70')]},
    'crop': {'label': 'Recortar', 'families': ['image', 'video'],
             'fields': [('rect', 'Área x,y,largura,altura em pixels', '0,0,200,200')]},
    'adjust': {'label': 'Ajustar foto', 'families': ['image'],
               'fields': [('brightness', 'Brilho (1 = original)', '1.1'), ('contrast', 'Contraste', '1.1'),
                          ('saturation', 'Saturação', '1'), ('sharpness', 'Nitidez', '1')]},
    'annotate': {'label': 'Anotar foto', 'families': ['image'],
                 'fields': [('text', 'Texto da anotação', 'Anotação'), ('position', 'Posição x,y', '20,20'),
                            ('color', 'Cor', '#ed713d'), ('font_size', 'Tamanho da letra', '28'),
                            ('shape', 'Forma: text, arrow, rectangle, ellipse ou number', 'text'),
                            ('rect', 'Área da forma x,y,largura,altura', '20,20,100,60')]},
    'background': {'label': 'Fundo', 'families': ['image'],
                   'fields': [('color', 'Cor do fundo', '#f4e9da'), ('padding', 'Margem em pixels', '40'),
                              ('color2', 'Segunda cor para gradiente (opcional)', ''),
                              ('background_image', 'Imagem de fundo (caminho opcional)', ''),
                              ('aspect', 'Proporção do fundo (opcional, ex.: 16:9)', ''),
                              ('radius', 'Arredondar cantos da foto em pixels', '0')]},
    'redact': {'label': 'Ocultar área', 'families': ['image'],
               'fields': [('rect', 'Área x,y,largura,altura', '0,0,100,100'),
                          ('style', 'Estilo: solid ou blur', 'solid')]},
    'metadata': {'label': 'Metadados', 'families': ['image', 'video', 'audio', 'pdf'], 'fields': []},
    'edit_metadata': {'label': 'Editar tags', 'families': ['image', 'pdf', 'audio', 'video'],
                      'fields': [('author', 'Autor', ''), ('title', 'Título', '')]},
    'strip': {'label': 'Limpar tags', 'families': ['image', 'video', 'audio', 'pdf'], 'fields': []},
    'images_pdf': {'label': 'Criar PDF', 'families': ['image'], 'fields': []},
    'collage': {'label': 'Colagem', 'families': ['image'],
                'fields': [('columns', 'Colunas', '2'), ('cell_width', 'Largura de cada célula', '600'),
                           ('spacing', 'Espaçamento', '20'), ('color', 'Fundo', '#ffffff')]},
    'qr': {'label': 'Ler QR code', 'families': ['image'], 'fields': []},
    'redact_faces': {'label': 'Ocultar rostos', 'families': ['image'],
                     'fields': [('style', 'Estilo: solid ou blur', 'solid')]},
    'redact_text': {'label': 'Ocultar texto', 'families': ['image'],
                    'fields': [('style', 'Estilo: solid ou blur', 'solid')]},
    'target_size': {'label': 'Tamanho alvo', 'families': ['image', 'audio', 'video', 'pdf'],
                    'fields': [('target_kb', 'Limite em KB (0 = usar redução percentual)', '100'),
                               ('percent', 'Redução percentual (1–99)', '50')]},
    'trim': {'label': 'Cortar tempo', 'families': ['video', 'audio'],
             'fields': [('start', 'Início em segundos', '0'), ('duration', 'Duração em segundos', '5')]},
    'speed': {'label': 'Velocidade', 'families': ['video', 'audio'],
              'fields': [('factor', 'Fator (0.25 a 4)', '1.5')]},
    'split_media': {'label': 'Dividir mídia', 'families': ['video', 'audio'],
                    'fields': [('seconds', 'Duração de cada parte em segundos', '10')]},
    'join_media': {'label': 'Unir mídia', 'families': ['video', 'audio'], 'minimum': 2, 'fields': []},
    'snapshot': {'label': 'Capturar quadro', 'families': ['video'],
                 'fields': [('time', 'Instante em segundos', '0')]},
    'normalize': {'label': 'Normalizar', 'families': ['audio'], 'fields': []},
    'bleep': {'label': 'Censurar áudio', 'families': ['audio'],
              'fields': [('start', 'Início em segundos', '0'), ('duration', 'Duração em segundos', '1')]},
    'channels': {'label': 'Canais', 'families': ['audio'],
                 'fields': [('channels', 'Canais: 1 mono ou 2 estéreo', '1')]},
    'merge_pdf': {'label': 'Unir PDFs', 'families': ['pdf'], 'minimum': 2, 'fields': []},
    'split_pdf': {'label': 'Dividir PDF', 'families': ['pdf'], 'fields': []},
    'reorder_pdf': {'label': 'Ordenar PDF', 'families': ['pdf'],
                    'fields': [('pages', 'Páginas na nova ordem (ex.: 3,1,2)', '2,1')]},
    'copy': {'label': 'Copiar', 'actions': True, 'fields': []},
    'move': {'label': 'Mover', 'actions': True, 'fields': [('destination', 'Pasta de destino', '')]},
    'copy_path': {'label': 'Copiar caminho', 'actions': True, 'fields': []},
    'terminal': {'label': 'Terminal', 'actions': True, 'fields': []},
    'float': {'label': 'Prateleira', 'actions': True, 'fields': []},
    'share': {'label': 'Compartilhar', 'actions': True, 'fields': []},
}


def available_tools(paths, actions=False):
    import importlib.util
    if not paths:
        return []
    kinds = {family(p) for p in paths}
    result = []
    for name, tool in TOOLS.items():
        if bool(tool.get('actions')) != actions or len(paths) < tool.get('minimum', 1):
            continue
        if not actions and not kinds.issubset(tool['families']):
            continue
        if kinds & {'video', 'audio'} and not actions and not shutil.which('ffmpeg'):
            continue
        if name == 'qr' and importlib.util.find_spec('zxingcpp') is None:
            continue
        if name == 'redact_faces' and importlib.util.find_spec('cv2') is None:
            continue
        if name == 'redact_text':
            from citrica.vision import text_available
            if not text_available():
                continue
        if name == 'share' and not shutil.which('localsend'):
            continue
        if name == 'join_media' and len(kinds) != 1:
            continue
        result.append({'id': name, **tool})
    return result


def number(params, key, default, lower, upper):
    try:
        value = float(params.get(key, default))
    except (ValueError, TypeError):
        raise ConversionError(f'{key}: informe um número válido.') from None
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ConversionError(f'{key}: use um valor entre {lower} e {upper}.')
    return value


def rectangle(params, width, height):
    try:
        x, y, w, h = map(int, str(params['rect']).split(','))
    except (KeyError, ValueError):
        raise ConversionError('Área inválida. Use x,y,largura,altura.') from None
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > width or y+h > height:
        raise ConversionError(f'A área precisa estar dentro de {width} × {height} pixels.')
    return x, y, w, h


def media_info(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                            check=True, capture_output=True, text=True, timeout=30)
    return json.loads(result.stdout)


def _image_tool(tool, path, params, target):
    with Image.open(path) as raw:
        if getattr(raw, 'n_frames', 1) > 1:
            raise ConversionError('A ferramenta preserva apenas imagens estáticas; animações são recusadas.')
        im = ImageOps.exif_transpose(raw).convert('RGBA')
        if tool in {'crop', 'redact'}:
            x, y, w, h = rectangle(params, *im.size)
            area = (x, y, x+w, y+h)
            if tool == 'crop':
                im = im.crop(area)
            elif params.get('style', 'solid') == 'blur':
                im.paste(im.crop(area).filter(ImageFilter.GaussianBlur(max(12, min(w, h)/5))), area)
            elif params.get('style', 'solid') == 'solid':
                ImageDraw.Draw(im).rectangle((x, y, x+w-1, y+h-1), fill='black')
            else:
                raise ConversionError('Use solid ou blur.')
        elif tool == 'adjust':
            for key, enhancer in [('brightness', ImageEnhance.Brightness), ('contrast', ImageEnhance.Contrast),
                                  ('saturation', ImageEnhance.Color), ('sharpness', ImageEnhance.Sharpness)]:
                im = enhancer(im).enhance(number(params, key, 1, 0, 5))
        elif tool == 'annotate':
            try:
                x, y = map(int, params.get('position', '20,20').split(','))
            except ValueError:
                raise ConversionError('Posição: use x,y.') from None
            if not 0 <= x < im.width or not 0 <= y < im.height:
                raise ConversionError('A posição precisa estar dentro da imagem.')
            size = int(number(params, 'font_size', 28, 6, 500))
            font_file = Path('/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf')
            if not font_file.exists():
                font_file = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
            font = ImageFont.truetype(str(font_file), size) if font_file.exists() else ImageFont.load_default(size=size)
            draw = ImageDraw.Draw(im)
            color = params.get('color', '#ed713d')
            shape = params.get('shape', 'text')
            if shape in {'text', 'number'}:
                if shape == 'number':
                    draw.ellipse((x, y, min(im.width-1, x+size*2), min(im.height-1, y+size*2)), fill=color)
                    color = 'white'
                    x, y = x+size//2, y+size//2
                draw.text((x, y), params.get('text', ''), font=font, fill=color)
            elif shape in {'arrow', 'rectangle', 'ellipse'}:
                x, y, w, h = rectangle(params, *im.size)
                box = (x, y, x+w-1, y+h-1)
                line = max(2, size//8)
                if shape == 'arrow':
                    draw.line(box, fill=color, width=line)
                    angle = math.atan2(h, w)
                    tip = (x+w-1, y+h-1)
                    for delta in [-.5, .5]:
                        end = (tip[0]-size*math.cos(angle+delta), tip[1]-size*math.sin(angle+delta))
                        draw.line((tip, end), fill=color, width=line)
                elif shape == 'rectangle':
                    draw.rectangle(box, outline=color, width=line)
                else:
                    draw.ellipse(box, outline=color, width=line)
            else:
                raise ConversionError('Forma inválida.')
        elif tool == 'background':
            from PIL import ImageColor
            pad = int(number(params, 'padding', 40, 0, 2000))
            width, height = im.width+2*pad, im.height+2*pad
            if params.get('aspect'):
                try:
                    a, b = map(float, params['aspect'].split(':'))
                    if not (math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0):
                        raise ValueError()
                    ratio = a/b
                except ValueError:
                    raise ConversionError('Proporção inválida. Use, por exemplo, 16:9.') from None
                width, height = max(width, math.ceil(height*ratio)), max(height, math.ceil(width/ratio))
            if width*height > 100_000_000:
                raise ConversionError('Fundo excede 100 megapixels.')
            canvas = Image.new('RGBA', (width, height), params.get('color', '#ffffff'))
            if params.get('background_image'):
                with Image.open(Path(params['background_image']).expanduser()) as bg:
                    canvas = ImageOps.fit(bg.convert('RGBA'), (width, height))
            elif params.get('color2'):
                top, bottom = ImageColor.getrgb(params.get('color', '#ffffff')), ImageColor.getrgb(params['color2'])
                draw = ImageDraw.Draw(canvas)
                for row in range(height):
                    factor = row/max(1, height-1)
                    color = tuple(round(a*(1-factor)+b*factor) for a, b in zip(top, bottom))
                    draw.line((0, row, width, row), fill=color)
            radius = int(number(params, 'radius', 0, 0, min(im.size)//2))
            if radius:
                mask = Image.new('L', im.size)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width-1, im.height-1), radius, fill=255)
                from PIL import ImageChops
                im.putalpha(ImageChops.multiply(im.getchannel('A'), mask))
            canvas.alpha_composite(im, ((width-im.width)//2, (height-im.height)//2))
            im = canvas
        elif tool in {'redact_faces', 'redact_text'}:
            from citrica.vision import face_boxes, text_boxes
            boxes = face_boxes(im) if tool == 'redact_faces' else text_boxes(im)
            if not boxes:
                raise ConversionError('Nenhuma área detectada. Use a seleção manual em Ocultar área.')
            for area in boxes:
                if params.get('style', 'solid') == 'blur':
                    im.paste(im.crop(area).filter(ImageFilter.GaussianBlur(25)), area)
                elif params.get('style', 'solid') == 'solid':
                    ImageDraw.Draw(im).rectangle(area, fill='black')
                else:
                    raise ConversionError('Use solid ou blur.')
        elif tool == 'edit_metadata':
            from PIL.PngImagePlugin import PngInfo
            exif = raw.getexif()
            tags = PngInfo()
            for key, tag, name in [('author', 315, 'Author'), ('title', 270, 'Title')]:
                value = params.get(key, '')
                tags.add_itxt(name, value)
                if value.isascii():
                    exif[tag] = value
                else:
                    exif.pop(tag, None)  # EXIF ASCII fields cannot encode Unicode.
            im.save(target, exif=exif, pnginfo=tags)
            return
        im.save(target)


def _media_tool(tool, paths, params, folder, cancel):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ConversionError('FFmpeg não instalado.')
    source = paths[0]
    video = family(source) == 'video'
    ext = '.mp4' if video else '.wav'
    target = folder / (source.stem + '-' + tool + ext)
    args = [ffmpeg, '-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-i', str(source)]
    info = media_info(source)
    total = float(info.get('format', {}).get('duration', 0))
    if tool == 'trim':
        start = number(params, 'start', 0, 0, max(0, total-0.001))
        duration = number(params, 'duration', 5, 0.01, max(0.01, total-start))
        args += ['-ss', str(start), '-t', str(duration)]
    elif tool == 'crop':
        stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
        if not stream:
            raise ConversionError('Nenhuma faixa de vídeo encontrada.')
        x, y, w, h = rectangle(params, stream['width'], stream['height'])
        if w % 2 or h % 2:
            raise ConversionError('Para vídeo, largura e altura devem ser pares.')
        args += ['-vf', f'crop={w}:{h}:{x}:{y}']
    elif tool == 'speed':
        factor = number(params, 'factor', 1.5, 0.25, 4)
        audio = any(s['codec_type'] == 'audio' for s in info['streams'])
        chain, remaining = [], factor
        while remaining < 0.5:
            chain.append('atempo=0.5')
            remaining /= 0.5
        while remaining > 2:
            chain.append('atempo=2')
            remaining /= 2
        chain.append(f'atempo={remaining}')
        if video:
            args += ['-vf', f'setpts=PTS/{factor}']
        if audio:
            args += ['-af', ','.join(chain)]
    elif tool == 'normalize':
        args += ['-af', 'loudnorm=I=-16:TP=-1.5:LRA=11']
    elif tool == 'edit_metadata':
        # Remux to a broadly writable container, preserving media streams.
        target = target.with_suffix('.mkv' if video else '.mka')
        run_process(args + ['-map', '0', '-c', 'copy', '-metadata', 'artist=' + params.get('author', ''),
                            '-metadata', 'title=' + params.get('title', ''), str(target)], cancel)
        return [target]
    elif tool == 'channels':
        args += ['-ac', str(int(number(params, 'channels', 1, 1, 2)))]
    elif tool == 'bleep':
        start = number(params, 'start', 0, 0, max(0, total-0.001))
        duration = number(params, 'duration', 1, 0.01, max(0.01, total-start))
        # Tone is generated and gated in one filter graph; timing and total duration
        # are preserved. No original speech is mixed into the censored interval.
        graph = (f'[0:a]volume=0:enable=between(t\\,{start}\\,{start+duration})[muted];'
                 f'sine=frequency=1000:duration={total},volume=0.20,'
                 f"volume=0:enable='not(between(t,{start},{start+duration}))'[tone];"
                 '[muted][tone]amix=inputs=2:duration=first:normalize=0[out]')
        args += ['-filter_complex', graph, '-map', '[out]']
    elif tool == 'snapshot':
        instant = number(params, 'time', 0, 0, max(0, total-0.001))
        target = target.with_suffix('.png')
        args += ['-ss', str(instant), '-frames:v', '1', '-an']
    elif tool == 'split_media':
        seconds = number(params, 'seconds', 10, 0.1, 86400)
        if total / seconds > 1000:
            raise ConversionError('Limite de 1000 partes por operação.')
        args += ['-f', 'segment', '-segment_time', str(seconds), '-reset_timestamps', '1']
        if video:
            args += ['-c:v', 'libx264', '-force_key_frames', f'expr:gte(t,n_forced*{seconds})', '-c:a', 'aac']
        target = folder / (source.stem + '-parte-%03d' + ext)
        run_process(args + [str(target)], cancel)
        return sorted(folder.glob(source.stem + '-parte-*' + ext))
    elif tool == 'join_media':
        reference = info['streams']
        for path in paths[1:]:
            streams = media_info(path)['streams']
            def signature(ss):
                return [(s.get('codec_type'), s.get('codec_name'), s.get('width'), s.get('height'),
                         s.get('sample_rate'), s.get('channels')) for s in ss]
            if signature(streams) != signature(reference):
                raise ConversionError('Para unir, selecione mídias com os mesmos codecs, dimensões e canais.')
        manifest = folder / 'concat.txt'
        # FFmpeg concat quoting uses single-quote escape, not shell interpolation.
        manifest.write_text(''.join("file '" + str(p).replace("'", "'\\''") + "'\n" for p in paths))
        args = [ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '0',
                '-protocol_whitelist', 'file,pipe', '-i', str(manifest)]
    if tool != 'snapshot' and video:
        args += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac']
    args += ['-map_metadata', '-1', str(target)]
    run_process(args, cancel)
    return [target]


def execute(tool, paths, params=None, output_dir=None, cancel=None):
    params, cancel = params or {}, cancel or threading.Event()
    paths = [Path(p).resolve() for p in paths]
    check_cancel(cancel)
    if tool not in {t['id'] for t in available_tools(paths, actions=TOOLS.get(tool, {}).get('actions', False))}:
        raise ConversionError('Ferramenta indisponível para esta seleção ou dependências ausentes.')
    if any(not p.is_file() for p in paths):
        raise ConversionError('Selecione arquivos locais existentes.')
    if tool == 'merge_pdf':
        return {'outputs': merge_pdfs(paths, output_dir, cancel)}
    if tool in {'compress', 'strip'}:
        outputs = []
        quality = int(number(params, 'quality', 70 if tool == 'compress' else 95, 1, 100))
        for path in paths:
            kind = family(path)
            fmt = {'video': 'mp4', 'audio': 'mp3'}.get(kind, path.suffix.lstrip('.').lower())
            fmt = {'jpeg': 'jpg', 'tif': 'tiff', 'heif': 'heic'}.get(fmt, fmt)
            outputs += convert(path, fmt, output_dir, Options(quality=quality), cancel)
        return {'outputs': outputs}
    if tool == 'metadata':
        result = {}
        for path in paths:
            kind = family(path)
            if kind == 'image':
                with Image.open(path) as im:
                    result[path.name] = {'size': im.size, 'format': im.format, 'mode': im.mode,
                                         'exif': {str(k): str(v) for k, v in im.getexif().items()},
                                         'text': {k: v for k, v in im.info.items() if isinstance(v, str)}}
            elif kind == 'pdf':
                from pypdf import PdfReader
                reader = PdfReader(path)
                result[path.name] = {'pages': len(reader.pages), 'metadata': dict(reader.metadata or {})}
            else:
                result[path.name] = media_info(path)
        return {'text': json.dumps(result, ensure_ascii=False, indent=2, default=str)}
    if tool == 'qr':
        import zxingcpp
        texts = []
        for path in paths:
            with Image.open(path) as im:
                texts.extend(r.text for r in zxingcpp.read_barcodes(im))
        if not texts:
            raise ConversionError('Nenhum QR code ou código de barras legível foi encontrado.')
        return {'text': '\n'.join(texts)}
    if TOOLS[tool].get('actions'):
        raise ConversionError('Esta ação precisa da interface do desktop.')
    folder = (output_dir or paths[0].parent).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.citrica-', dir=folder) as temp:
        staging = Path(temp)
        staged = []
        if tool in {'images_pdf', 'collage'}:
            images = []
            for path in paths:
                check_cancel(cancel)
                with Image.open(path) as raw:
                    image = ImageOps.exif_transpose(raw).convert('RGBA')
                    bg = Image.new('RGB', image.size, 'white')
                    bg.paste(image, mask=image.getchannel('A'))
                    images.append(bg)
            target = staging / ('imagens.pdf' if tool == 'images_pdf' else 'colagem.png')
            if tool == 'images_pdf':
                images[0].save(target, save_all=True, append_images=images[1:])
            else:
                columns = int(number(params, 'columns', 2, 1, min(20, len(images))))
                width = int(number(params, 'cell_width', 600, 16, 4096))
                gap = int(number(params, 'spacing', 20, 0, 500))
                rows = math.ceil(len(images)/columns)
                size = (columns*width+(columns+1)*gap, rows*width+(rows+1)*gap)
                if size[0]*size[1] > 100_000_000:
                    raise ConversionError('Colagem excede o limite de 100 megapixels.')
                canvas = Image.new('RGB', size, params.get('color', '#ffffff'))
                for i, image in enumerate(images):
                    tile = ImageOps.contain(image, (width, width))
                    canvas.paste(tile, (gap+(i%columns)*(width+gap)+(width-tile.width)//2,
                                        gap+(i//columns)*(width+gap)+(width-tile.height)//2))
                canvas.save(target)
            staged.append(target)
        elif tool == 'target_size':
            from citrica.size_target import fit
            for index, path in enumerate(paths):
                kb = number(params, 'target_kb', 100, 0, 1024**3)
                percent = number(params, 'percent', 50, 1, 99)
                limit = int(kb*1024) if kb else int(path.stat().st_size*(1-percent/100))
                ext = {'image': '.webp', 'audio': '.mp3', 'video': '.mp4', 'pdf': '.pdf'}[family(path)]
                target = staging / f'{path.stem}-alvo-{index+1}{ext}'
                fit(path, target, limit, cancel)
                staged.append(target)
        elif family(paths[0]) in {'video', 'audio'}:
            staged = _media_tool(tool, paths, params, staging, cancel)
        elif family(paths[0]) == 'pdf':
            from pypdf import PdfReader, PdfWriter
            for path in paths:
                reader = PdfReader(path)
                if reader.is_encrypted:
                    raise ConversionError('Desbloqueie uma cópia do PDF antes de usar esta ferramenta.')
                if tool == 'split_pdf':
                    orders = [[i] for i in range(len(reader.pages))]
                elif tool == 'reorder_pdf':
                    try:
                        order = [int(v.strip())-1 for v in params['pages'].split(',')]
                    except (KeyError, ValueError):
                        raise ConversionError('Informe páginas separadas por vírgulas.') from None
                    if sorted(order) != list(range(len(reader.pages))):
                        raise ConversionError('Liste cada página exatamente uma vez, sem omissões ou repetições.')
                    orders = [order]
                else:
                    orders = [list(range(len(reader.pages)))]
                for i, order in enumerate(orders):
                    check_cancel(cancel)
                    writer = PdfWriter()
                    for index in order:
                        writer.add_page(reader.pages[index])
                    if tool == 'edit_metadata':
                        writer.add_metadata({'/Author': params.get('author', ''), '/Title': params.get('title', '')})
                    target = staging / f'{path.stem}-{tool}-{i+1}.pdf'
                    writer.write(target)
                    staged.append(target)
        else:
            for i, path in enumerate(paths):
                target = staging / f'{path.stem}-{tool}-{i+1}.png'
                _image_tool(tool, path, params, target)
                staged.append(target)
        check_cancel(cancel)
        if not staged or any(not p.is_file() or p.stat().st_size == 0 for p in staged):
            raise ConversionError('A ferramenta não produziu um arquivo válido.')
        outputs = []
        try:
            for path in staged:
                outputs.append(publish(path, folder / path.name))
        except BaseException:
            for output in outputs:
                output.unlink(missing_ok=True)
            raise
        return {'outputs': outputs}
