"""Local face/text bounding boxes. No cloud API, identity recognition or uploads."""
import csv
import ctypes
import ctypes.util
import io
import json
import os
import sys
from pathlib import Path

from citrica.core import ConversionError


def ocr_paths():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    bundled = next(root.glob('libtesseract.so*'), None)
    declared_library = False
    if sys.platform == 'win32':
        folders = [root / 'ocr', Path(os.environ.get('CITRICA_OCR_DIR', root / 'ocr')),
                   Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR']
        if os.environ.get('CITRICA_WINDOWS_ENGINES'):
            folders.insert(1, Path(os.environ['CITRICA_WINDOWS_ENGINES']) / 'ocr')
        bundled = None
        for folder in folders:
            try:
                manifest = json.loads((folder.parent / 'engines.json').read_text(encoding='utf-8'))
                filename = manifest.get('ocr_library')
            except (OSError, ValueError, AttributeError):
                filename = None
            if (isinstance(filename, str) and filename.lower().endswith('.dll') and
                    not any(character in filename for character in ['/', '\\', ':'])):
                declared_library = True
                candidate = folder / filename
                bundled = candidate if candidate.is_file() else None
                # An incomplete update must not silently load an older leftover
                # DLL or a system installation in place of the declared engine.
                break
            bundled = next(folder.glob('*tesseract*.dll'), None)
            if bundled:
                break
    library = str(bundled) if bundled else (None if declared_library else ctypes.util.find_library('tesseract'))
    model_paths = [root / 'ocr-data', root / 'ocr/tessdata',
                              Path(os.environ.get('CITRICA_OCR_DIR', root / 'ocr')) / 'tessdata',
                              Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR/tessdata',
                              Path('/usr/share/tesseract/tessdata'),
                              Path('/usr/share/tesseract-ocr/5/tessdata')]
    if sys.platform == 'win32' and os.environ.get('CITRICA_WINDOWS_ENGINES'):
        model_paths.insert(2, Path(os.environ['CITRICA_WINDOWS_ENGINES']) / 'ocr/tessdata')
    if sys.platform == 'win32' and bundled:
        model_paths.insert(0, bundled.parent / 'tessdata')
    model = next((p for p in model_paths
                  if (p / 'eng.traineddata').is_file()), None)
    return library, model


def text_available():
    library, model = ocr_paths()
    return bool(library and model)


def text_boxes(image):
    library, model = ocr_paths()
    if not library:
        raise ConversionError('Instale Tesseract e o modelo eng para detectar texto localmente.')
    lib = ctypes.CDLL(library)
    ptr, integer, string = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p
    lib.TessBaseAPICreate.restype = ptr
    lib.TessBaseAPIInit3.argtypes = [ptr, string, string]
    lib.TessBaseAPIInit3.restype = integer
    lib.TessBaseAPISetImage.argtypes = [ptr, ptr, integer, integer, integer, integer]
    lib.TessBaseAPIRecognize.argtypes = [ptr, ptr]
    lib.TessBaseAPIGetTsvText.argtypes = [ptr, integer]
    lib.TessBaseAPIGetTsvText.restype = ptr
    lib.TessDeleteText.argtypes = [ptr]
    lib.TessBaseAPIDelete.argtypes = [ptr]
    handle = lib.TessBaseAPICreate()
    try:
        if sys.platform == 'win32' and model:
            # The upstream C++ loader uses a narrow fopen path. A UTF-8 model
            # path can fail for users such as C:\Users\João even though Python
            # successfully loads the DLL. Read the model with Unicode-aware
            # Python file APIs and use Tesseract's supported in-memory API.
            data = (model / 'eng.traineddata').read_bytes()
            model_data = ctypes.create_string_buffer(data)
            lib.TessBaseAPIInit5.argtypes = [ptr, ptr, integer, string, integer, ptr, integer,
                                            ptr, ptr, ctypes.c_size_t, integer]
            lib.TessBaseAPIInit5.restype = integer
            initialized = lib.TessBaseAPIInit5(handle, model_data, len(data), b'eng', 3,
                                               None, 0, None, None, 0, 0)
        else:
            initialized = lib.TessBaseAPIInit3(handle, str(model).encode() if model else None, b'eng')
        if initialized != 0:
            raise ConversionError('Não foi possível carregar o modelo de texto eng do Tesseract.')
        rgb = image.convert('RGB')
        raw = ctypes.create_string_buffer(rgb.tobytes())
        lib.TessBaseAPISetImage(handle, raw, rgb.width, rgb.height, 3, rgb.width*3)
        if lib.TessBaseAPIRecognize(handle, None) != 0:
            raise ConversionError('Falha ao reconhecer as áreas de texto.')
        result = lib.TessBaseAPIGetTsvText(handle, 0)
        if not result:
            return []
        try:
            text = ctypes.string_at(result).decode('utf-8')
        finally:
            lib.TessDeleteText(result)
        if not text.startswith('level\t'):
            text = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n' + text
        boxes = []
        for row in csv.DictReader(io.StringIO(text), delimiter='\t'):
            if row['text'].strip() and float(row['conf']) >= 0:
                x, y, w, h = (int(row[k]) for k in ['left', 'top', 'width', 'height'])
                pad = 4
                boxes.append((max(0, x-pad), max(0, y-pad), min(rgb.width, x+w+pad), min(rgb.height, y+h+pad)))
        return boxes
    finally:
        lib.TessBaseAPIDelete(handle)


def face_boxes(image):
    import cv2
    import numpy as np
    gray = cv2.cvtColor(np.array(image.convert('RGB')), cv2.COLOR_RGB2GRAY)
    detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / 'haarcascade_frontalface_default.xml'))
    if detector.empty():
        raise ConversionError('Modelo local de rostos não encontrado.')
    detections = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
    return [(int(x), int(y), int(x+w), int(y+h)) for x, y, w, h in detections]
