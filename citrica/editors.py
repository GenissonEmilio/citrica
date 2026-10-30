"""Visual, non-destructive workspaces for the wheel's existing local tools.

The tool engine remains the authority for exports. Previews are deliberately
bounded and never write alongside the source. Qt Multimedia is optional at
import time so a missing playback backend cannot hide otherwise usable tools.
"""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from citrica.core import Cancelled, ConversionError, check_cancel, family
from citrica.runtime import popen_external, program
from citrica.tools import TOOLS, oriented_video_size

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
except ImportError:
    QAudioOutput = QMediaPlayer = QVideoWidget = None


EDITOR_STYLE = """
QDialog#CitricaEditor { background: #15171b; color: #eff1f5; }
QDialog#CitricaEditor QWidget { color: #e5e8ee; font-size: 13px; }
QDialog#CitricaEditor QLabel { background: transparent; }
QDialog#CitricaEditor QLabel#EditorTitle { font-size: 23px; font-weight: 700; color: #fff; }
QDialog#CitricaEditor QLabel#EditorMuted { color: #9aa3b2; }
QDialog#CitricaEditor QFrame#EditorPanel { background: #202329; border: 1px solid #30353e;
    border-radius: 12px; }
QDialog#CitricaEditor QScrollArea { border: 0; background: transparent; }
QDialog#CitricaEditor QScrollArea > QWidget > QWidget { background: #202329; }
QDialog#CitricaEditor QLineEdit, QDialog#CitricaEditor QSpinBox,
QDialog#CitricaEditor QDoubleSpinBox, QDialog#CitricaEditor QComboBox,
QDialog#CitricaEditor QPlainTextEdit, QDialog#CitricaEditor QListWidget {
    background: #14171c; border: 1px solid #3b424e; border-radius: 6px;
    padding: 7px; color: #eef1f6; selection-background-color: #397f86; }
QDialog#CitricaEditor QComboBox QAbstractItemView { background: #202329; color: #fff; }
QDialog#CitricaEditor QPushButton { background: #2b3039; border: 1px solid #3b424e;
    border-radius: 7px; padding: 8px 12px; color: #f1f3f8; }
QDialog#CitricaEditor QPushButton:hover { background: #39404b; }
QDialog#CitricaEditor QPushButton#EditorPrimary { background: #53ded0; color: #102c2a;
    border-color: #53ded0; font-weight: 700; padding: 10px 23px; }
QDialog#CitricaEditor QPushButton:disabled { color: #7d8695; background: #262b32; }
QDialog#CitricaEditor QSlider::groove:horizontal { height: 4px; background: #424a57;
    border-radius: 2px; }
QDialog#CitricaEditor QSlider::sub-page:horizontal { background: #53ded0; }
QDialog#CitricaEditor QSlider::handle:horizontal { width: 14px; margin: -5px 0;
    border-radius: 7px; background: #b7fff7; }
QDialog#CitricaEditor QProgressBar { background: #14171c; border: 0; border-radius: 3px; height: 5px; }
QDialog#CitricaEditor QProgressBar::chunk { background: #53ded0; border-radius: 3px; }
QDialog#CitricaEditor QCheckBox { spacing: 8px; }
QDialog#CitricaEditor QSplitter::handle { background: #15171b; }
"""


def timestamp(seconds):
    milliseconds = round(max(0, seconds) * 1000)
    minutes, seconds = divmod(milliseconds // 1000, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}.{milliseconds % 1000:03}'


def panel():
    widget = QFrame()
    widget.setObjectName('EditorPanel')
    return widget


def muted(text):
    label = QLabel(text)
    label.setObjectName('EditorMuted')
    label.setWordWrap(True)
    return label


class ImageSelection(QWidget):
    """Fit-to-view canvas; selection coordinates always use oriented source pixels."""
    selected = Signal(str)

    def __init__(self, path=None, *, image=None, selectable=True):
        super().__init__()
        if image is None:
            with Image.open(path) as raw:
                if raw.width * raw.height > 100_000_000:
                    raise ConversionError('A prévia aceita imagens de até 100 megapixels.')
                oriented = ImageOps.exif_transpose(raw)
                source_size = oriented.size
                oriented.thumbnail((1600, 1200), Image.Resampling.LANCZOS)
                image = oriented.convert('RGBA')
        else:
            source_size = image.size
        self.source_size = source_size
        self.preview_source = image.copy()
        self.preview_source.thumbnail((1600, 1200), Image.Resampling.LANCZOS)
        self.pixmap_source = QPixmap.fromImage(ImageQt(self.preview_source))
        self.display = self.pixmap_source
        self.selectable = selectable
        self.selection = QRectF(0, 0, *self.source_size)
        self.drag_kind = None
        self.press_position = None
        self.press_selection = None
        self.setMinimumSize(260, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Prévia da imagem e seleção em pixels')
        self.setToolTip('Arraste uma área; mova pelo centro ou ajuste pelas alças. O original será preservado.')

    def sizeHint(self):
        return QSize(700, 420)

    def image_rect(self):
        width, height = self.source_size if self.selectable else (self.display.width(), self.display.height())
        scale = min(max(1, self.width() - 24) / width, max(1, self.height() - 24) / height)
        return QRectF((self.width() - width * scale) / 2, (self.height() - height * scale) / 2,
                      width * scale, height * scale)

    def to_source(self, point):
        rect = self.image_rect()
        return QPointF(min(self.source_size[0], max(0, (point.x() - rect.x()) / rect.width() * self.source_size[0])),
                       min(self.source_size[1], max(0, (point.y() - rect.y()) / rect.height() * self.source_size[1])))

    def selection_rect(self):
        image = self.image_rect()
        sx, sy = image.width() / self.source_size[0], image.height() / self.source_size[1]
        return QRectF(image.x() + self.selection.x() * sx, image.y() + self.selection.y() * sy,
                      self.selection.width() * sx, self.selection.height() * sy)

    def set_selection(self, text, *, emit=False):
        try:
            x, y, width, height = map(int, text.split(','))
        except ValueError:
            return
        sw, sh = self.source_size
        x, y = min(max(0, x), sw - 1), min(max(0, y), sh - 1)
        self.selection = QRectF(x, y, min(max(1, width), sw - x), min(max(1, height), sh - y))
        self.update()
        if emit:
            self.emit_selection()

    def emit_selection(self):
        rect = self.selection.normalized()
        sw, sh = self.source_size
        x, y = min(sw - 1, max(0, round(rect.x()))), min(sh - 1, max(0, round(rect.y())))
        width, height = min(sw - x, max(1, round(rect.width()))), min(sh - y, max(1, round(rect.height())))
        self.selection = QRectF(x, y, width, height)
        self.selected.emit(f'{x},{y},{width},{height}')

    def set_preview(self, image=None):
        self.display = self.pixmap_source if image is None else QPixmap.fromImage(ImageQt(image))
        self.update()

    def handles(self):
        rect = self.selection_rect()
        return {'nw': rect.topLeft(), 'ne': rect.topRight(), 'sw': rect.bottomLeft(), 'se': rect.bottomRight(),
                'n': QPointF(rect.center().x(), rect.top()), 's': QPointF(rect.center().x(), rect.bottom()),
                'w': QPointF(rect.left(), rect.center().y()), 'e': QPointF(rect.right(), rect.center().y())}

    def mousePressEvent(self, event):
        if not self.selectable or event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        point = event.position()
        self.press_position = self.to_source(point)
        self.press_selection = QRectF(self.selection)
        self.drag_kind = next((name for name, handle in self.handles().items()
                               if (handle - point).manhattanLength() < 14), None)
        if self.drag_kind is None:
            # A full-image selection starts a new region anywhere inside it.
            full = self.selection.width() == self.source_size[0] and self.selection.height() == self.source_size[1]
            self.drag_kind = 'move' if self.selection_rect().contains(point) and not full else 'new'

    def mouseMoveEvent(self, event):
        if self.press_position is None:
            return
        point = self.to_source(event.position())
        original = self.press_selection
        if self.drag_kind == 'new':
            self.selection = QRectF(self.press_position, point).normalized()
        elif self.drag_kind == 'move':
            delta = point - self.press_position
            self.selection = QRectF(min(max(0, original.x() + delta.x()), self.source_size[0] - original.width()),
                                    min(max(0, original.y() + delta.y()), self.source_size[1] - original.height()),
                                    original.width(), original.height())
        else:
            rect = QRectF(original)
            if 'w' in self.drag_kind:
                rect.setLeft(min(point.x(), rect.right() - 1))
            if 'e' in self.drag_kind:
                rect.setRight(max(point.x(), rect.left() + 1))
            if 'n' in self.drag_kind:
                rect.setTop(min(point.y(), rect.bottom() - 1))
            if 's' in self.drag_kind:
                rect.setBottom(max(point.y(), rect.top() + 1))
            self.selection = rect
        self.emit_selection()
        self.update()

    def mouseReleaseEvent(self, event):
        if self.press_position is None:
            return
        self.mouseMoveEvent(event)
        self.press_position = None
        self.emit_selection()

    def keyPressEvent(self, event):
        moves = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                 Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if self.selectable and event.key() in moves:
            x, y = moves[event.key()]
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            self.set_selection(f'{round(self.selection.x()) + x * step},{round(self.selection.y()) + y * step},'
                               f'{round(self.selection.width())},{round(self.selection.height())}', emit=True)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#101216'))
        rect = self.image_rect()
        painter.drawPixmap(rect, self.display, QRectF(self.display.rect()))
        if self.selectable:
            selected = self.selection_rect()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 125))
            for area in [QRectF(rect.left(), rect.top(), rect.width(), selected.top() - rect.top()),
                         QRectF(rect.left(), selected.bottom(), rect.width(), rect.bottom() - selected.bottom()),
                         QRectF(rect.left(), selected.top(), selected.left() - rect.left(), selected.height()),
                         QRectF(selected.right(), selected.top(), rect.right() - selected.right(), selected.height())]:
                painter.drawRect(area)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor('#f8d54a'), 2))
            painter.drawRect(selected)
            painter.setPen(QPen(QColor(255, 255, 255, 85), 1))
            for fraction in (1 / 3, 2 / 3):
                painter.drawLine(QPointF(selected.left() + selected.width() * fraction, selected.top()),
                                 QPointF(selected.left() + selected.width() * fraction, selected.bottom()))
                painter.drawLine(QPointF(selected.left(), selected.top() + selected.height() * fraction),
                                 QPointF(selected.right(), selected.top() + selected.height() * fraction))
            painter.setBrush(QColor('#f8d54a'))
            painter.setPen(Qt.PenStyle.NoPen)
            for point in self.handles().values():
                painter.drawRoundedRect(QRectF(point.x() - 4, point.y() - 4, 8, 8), 2, 2)


class Timeline(QWidget):
    rangeChanged = Signal(float, float)
    seek = Signal(float)

    def __init__(self, selection=False):
        super().__init__()
        self.duration, self.start, self.end, self.position = 1., 0., 1., 0.
        self.selection_enabled = selection
        self.frames = []
        self.waveform = QPixmap()
        self.drag_kind = None
        self.setMinimumHeight(116)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Linha do tempo; arraste as alças amarelas para selecionar o trecho')
        self.setToolTip('Clique para buscar um instante. Arraste as alças amarelas para selecionar início e fim.')

    def x(self, seconds):
        return 14 + min(1, max(0, seconds / max(.001, self.duration))) * max(1, self.width() - 28)

    def seconds(self, x):
        return min(self.duration, max(0, (x - 14) / max(1, self.width() - 28) * self.duration))

    def set_range(self, start, end, *, emit=False):
        self.start = min(max(0, start), max(0, self.duration - .01))
        self.end = min(self.duration, max(self.start + .01, end))
        self.update()
        if emit:
            self.rangeChanged.emit(self.start, self.end)

    def set_position(self, seconds):
        self.position = min(self.duration, max(0, seconds))
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        x = event.position().x()
        self.drag_kind = 'start' if self.selection_enabled and abs(x - self.x(self.start)) < 12 else (
            'end' if self.selection_enabled and abs(x - self.x(self.end)) < 12 else 'seek')
        self.mouseMoveEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_kind is None:
            return
        value = self.seconds(event.position().x())
        if self.drag_kind == 'start':
            self.set_range(min(value, self.end - .01), self.end, emit=True)
        elif self.drag_kind == 'end':
            self.set_range(self.start, max(value, self.start + .01), emit=True)
        self.seek.emit(value)

    def mouseReleaseEvent(self, event):
        self.mouseMoveEvent(event)
        self.drag_kind = None

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key.Key_Left, Qt.Key.Key_Right}:
            delta = -.1 if event.key() == Qt.Key.Key_Left else .1
            self.seek.emit(min(self.duration, max(0, self.position + delta)))
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(14, 14, max(1, self.width() - 28), 66)
        painter.fillRect(track, QColor('#303741'))
        if not self.waveform.isNull():
            painter.drawPixmap(track, self.waveform, QRectF(self.waveform.rect()))
        elif self.frames:
            width = track.width() / len(self.frames)
            for i, frame in enumerate(self.frames):
                painter.drawPixmap(QRectF(track.left() + i * width, track.top(), width + 1, track.height()),
                                   frame, QRectF(frame.rect()))
        else:
            painter.setPen(QColor('#9aa3b2'))
            painter.drawText(track, Qt.AlignmentFlag.AlignCenter, 'Preparando a prévia local…')
        if self.selection_enabled:
            left, right = self.x(self.start), self.x(self.end)
            painter.fillRect(QRectF(track.left(), track.top(), left - track.left(), track.height()), QColor(0, 0, 0, 155))
            painter.fillRect(QRectF(right, track.top(), track.right() - right, track.height()), QColor(0, 0, 0, 155))
            painter.fillRect(QRectF(left, track.top(), right - left, track.height()), QColor(248, 213, 74, 28))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor('#f8d54a'), 3))
            painter.drawRect(QRectF(left, track.top(), right - left, track.height()))
            for x in (left, right):
                painter.fillRect(QRectF(x - 5, track.top(), 10, track.height()), QColor('#f8d54a'))
                painter.setPen(QPen(QColor('#493c11'), 2))
                painter.drawLine(QPointF(x, track.center().y() - 8), QPointF(x, track.center().y() + 8))
        painter.setPen(QPen(QColor('#fff'), 2))
        painter.drawLine(QPointF(self.x(self.position), track.top() - 5), QPointF(self.x(self.position), track.bottom() + 5))
        painter.setPen(QColor('#abb4c2'))
        painter.drawText(QRectF(14, 90, 110, 20), timestamp(0))
        painter.drawText(QRectF(self.width() - 125, 90, 110, 20), Qt.AlignmentFlag.AlignRight, timestamp(self.duration))
        if self.selection_enabled:
            painter.setPen(QColor('#f8d54a'))
            painter.drawText(QRectF(120, 90, max(1, self.width() - 240), 20), Qt.AlignmentFlag.AlignCenter,
                             f'{timestamp(self.start)} — {timestamp(self.end)}  ·  {self.end - self.start:.2f} s')


class AudioOverview(QWidget):
    def __init__(self, name):
        super().__init__()
        self.name, self.details = name, 'Preparando forma de onda local…'
        self.waveform = QPixmap()
        self.setAccessibleName('Prévia da forma de onda do áudio original')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#101216'))
        center = self.height() / 2
        painter.setPen(QColor('#53ded0'))
        painter.drawText(QRectF(20, max(12, center - 140), self.width() - 40, 24),
                         Qt.AlignmentFlag.AlignCenter, 'ÁUDIO  /  PRÉVIA DO ORIGINAL')
        painter.setPen(QColor('#f1f4f8'))
        painter.drawText(QRectF(20, max(40, center - 110), self.width() - 40, 26),
                         Qt.AlignmentFlag.AlignCenter, self.name)
        if not self.waveform.isNull():
            painter.drawPixmap(QRectF(24, center - 65, self.width() - 48, 150),
                               self.waveform, QRectF(self.waveform.rect()))
        painter.setPen(QColor('#9aa3b2'))
        painter.drawText(QRectF(20, center + 102, self.width() - 40, 26),
                         Qt.AlignmentFlag.AlignCenter, self.details)


def capture(args, cancel, timeout=20, limit=8_000_000):
    """Bounded, cancellable subprocess output, without PIPE deadlocks or a console."""
    check_cancel(cancel)
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        with popen_external(args, stdin=subprocess.DEVNULL, stdout=output, stderr=error) as process:
            deadline = time.monotonic() + timeout
            try:
                while process.poll() is None:
                    check_cancel(cancel)
                    if time.monotonic() > deadline:
                        raise ConversionError('A prévia excedeu o tempo limite. O arquivo ainda pode ser exportado.')
                    cancel.wait(.05)
            except BaseException:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise
            check_cancel(cancel)
            if process.returncode:
                error.seek(0)
                raise ConversionError(error.read(1500).decode(errors='replace').strip() or 'Prévia indisponível.')
            output.seek(0)
            result = output.read(limit + 1)
            if len(result) > limit:
                raise ConversionError('A prévia excedeu o tamanho seguro.')
            return result


def media_frame(path, instant, cancel, width=960):
    ffmpeg = program('ffmpeg')
    if not ffmpeg:
        raise ConversionError('FFmpeg não encontrado para gerar a prévia.')
    return capture([ffmpeg, '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                    '-ss', str(max(0, instant)), '-i', str(path), '-frames:v', '1', '-an',
                    '-vf', f'scale={width}:-2:force_original_aspect_ratio=decrease',
                    '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'], cancel)


WAVEFORM_SAMPLE_LIMIT = 2_000_000
WAVEFORM_RATE = 48_000
WAVEFORM_BLOCK = 1024


def waveform_filter(duration):
    # showwavespic buffers its complete input. Keep regularly spaced short
    # blocks, rather than low-pass resampling the entire signal to a few Hz,
    # which would erase speech and high-frequency tones. Only the visual
    # overview is sampled; seeking, playback and export use the full original.
    blocks = math.ceil(duration * WAVEFORM_RATE / WAVEFORM_BLOCK)
    stride = max(1, math.ceil(blocks / (WAVEFORM_SAMPLE_LIMIT // WAVEFORM_BLOCK)))
    filters = (f'aresample={WAVEFORM_RATE},aformat=channel_layouts=mono,'
               f'asetnsamples=n={WAVEFORM_BLOCK}:p=0,aselect=not(mod(n\\,{stride})),asetpts=N/SR/TB,'
               'showwavespic=s=1024x160:colors=0x53ded0:scale=sqrt:filter=peak')
    return filters, stride > 1


class PreviewWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, path, instant=None):
        super().__init__()
        self.path, self.instant = path, instant
        self.cancel = threading.Event()

    def run(self):
        try:
            if self.instant is not None:
                self.ready.emit({'frame': media_frame(self.path, self.instant, self.cancel), 'instant': self.instant})
                return
            ffprobe = program('ffprobe')
            if not ffprobe:
                raise ConversionError('FFprobe não encontrado para ler a duração.')
            raw = capture([ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_format',
                           '-show_streams', '-of', 'json', str(self.path)], self.cancel)
            info = json.loads(raw)
            duration = float(info.get('format', {}).get('duration', 0))
            if not math.isfinite(duration) or duration < .01:
                raise ConversionError('Não foi possível obter uma duração válida para a mídia.')
            self.ready.emit({'info': info, 'duration': duration})
            if family(self.path) == 'video':
                frames = []
                for i in range(8):
                    check_cancel(self.cancel)
                    instant = min(max(0, duration - .05), duration * i / 8)
                    frames.append(media_frame(self.path, instant, self.cancel, width=320))
                self.ready.emit({'frames': frames})
            else:
                ffmpeg = program('ffmpeg')
                if ffmpeg:
                    filters, sampled = waveform_filter(duration)
                    waveform = capture([ffmpeg, '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                                        '-t', str(duration), '-i', str(self.path), '-filter_complex', filters,
                                        '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'], self.cancel)
                    self.ready.emit({'waveform': waveform, 'waveform_sampled': sampled})
        except Cancelled:
            pass
        except Exception as error:
            self.failed.emit(str(error))


class NumberField(QDoubleSpinBox):
    def __init__(self, default, lower=0, upper=100_000, decimals=2, suffix=''):
        super().__init__()
        self.setDecimals(decimals)
        self.setRange(lower, upper)
        self.setSingleStep(1 if decimals == 0 else .1)
        self.setSuffix(suffix)
        self.setValue(float(default))
        self.setKeyboardTracking(False)

    def text(self):
        return format(self.value(), '.9g')

    def setText(self, value):
        self.setValue(float(value))


class ChoiceField(QComboBox):
    def __init__(self, choices, default):
        super().__init__()
        for title, value in choices:
            self.addItem(title, value)
        self.setText(default)

    def text(self):
        return str(self.currentData())

    def setText(self, value):
        index = self.findData(value)
        if index >= 0:
            self.setCurrentIndex(index)


class ColorField(QPushButton):
    changed = Signal()

    def __init__(self, value, *, optional=False):
        super().__init__()
        self.value, self.optional = value, optional
        self.refresh()
        self.clicked.connect(self.choose)

    def refresh(self):
        self.setText(self.value)

    def text(self):
        return self.value

    def setText(self, value):
        self.value = value
        super().setText(value or 'Sem segunda cor')
        self.setStyleSheet(f'border-left: 16px solid {value or "#444b57"};')

    def choose(self):
        color = QColorDialog.getColor(QColor(self.value or '#ffffff'), self, 'Escolher cor')
        if color.isValid():
            self.setText(color.name())
            self.changed.emit()


class GeometryField(QWidget):
    changed = Signal()

    def __init__(self, value, count=4):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.boxes = []
        labels = ['X', 'Y', 'Largura', 'Altura'][:count]
        for index in range(0, count, 2):
            row = QHBoxLayout()
            for title in labels[index:index + 2]:
                column = QVBoxLayout()
                column.addWidget(muted(title))
                box = QSpinBox()
                box.setRange(0 if title in {'X', 'Y'} else 1, 100_000)
                box.setKeyboardTracking(False)
                column.addWidget(box)
                row.addLayout(column)
                self.boxes.append(box)
                box.valueChanged.connect(self.changed)
            layout.addLayout(row)
        self.setText(value)

    def text(self):
        return ','.join(str(box.value()) for box in self.boxes)

    def setText(self, value):
        try:
            values = list(map(int, value.split(',')))
        except ValueError:
            return
        if len(values) == len(self.boxes):
            for box, number in zip(self.boxes, values):
                previous = box.blockSignals(True)
                box.setValue(number)
                box.blockSignals(previous)


class FileField(QWidget):
    changed = Signal()

    def __init__(self, value):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.input = QLineEdit(value)
        self.input.setPlaceholderText('Opcional')
        self.input.textChanged.connect(self.changed)
        button = QPushButton('…')
        button.setFixedWidth(36)
        button.clicked.connect(self.browse)
        layout.addWidget(self.input, 1)
        layout.addWidget(button)

    def text(self):
        return self.input.text()

    def setText(self, text):
        self.input.setText(text)

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Escolher imagem de fundo', '', 'Imagens (*.png *.jpg *.webp *.heic);;Todos (*)')
        if path:
            self.input.setText(path)


NUMBER_FIELDS = {
    'quality': (1, 100, 0, '%'), 'brightness': (0, 5, 2, ' ×'), 'contrast': (0, 5, 2, ' ×'),
    'saturation': (0, 5, 2, ' ×'), 'sharpness': (0, 5, 2, ' ×'), 'font_size': (6, 500, 0, ' px'),
    'padding': (0, 2000, 0, ' px'), 'radius': (0, 100_000, 0, ' px'), 'columns': (1, 20, 0, ''),
    'cell_width': (16, 4096, 0, ' px'), 'spacing': (0, 500, 0, ' px'), 'target_kb': (0, 1024 ** 3, 0, ' KB'),
    'percent': (1, 99, 0, '%'), 'factor': (.25, 4, 2, ' ×'), 'seconds': (.1, 86400, 2, ' s'),
    'start': (0, 86400 * 365, 3, ' s'), 'duration': (.01, 86400 * 365, 3, ' s'),
    'time': (0, 86400 * 365, 3, ' s'),
}
SHORT_LABELS = {'rect': 'Área selecionada · pixels', 'position': 'Posição do texto · pixels',
                'quality': 'Qualidade', 'brightness': 'Brilho', 'font_size': 'Tamanho do texto',
                'shape': 'Tipo de anotação', 'style': 'Ocultar com', 'factor': 'Velocidade',
                'target_kb': 'Tamanho máximo', 'percent': 'Redução se o limite for zero',
                'start': 'Início', 'duration': 'Duração', 'time': 'Instante', 'seconds': 'Cada parte',
                'aspect': 'Proporção do fundo', 'background_image': 'Imagem de fundo',
                'color2': 'Gradiente · segunda cor', 'channels': 'Canais de áudio'}


class EditorDialog(QDialog):
    def __init__(self, tool, paths, *, worker_factory):
        super().__init__()
        self.tool, self.paths = tool, list(map(Path, paths))
        self.worker_factory, self.worker = worker_factory, None
        self.fields, self.preview_threads = {}, []
        self.latest_output = None
        self.player = self.audio_output = self.video_widget = None
        self.canvas = self.timeline = self.pdf_order = None
        self.pdf = None
        self.media_duration = None
        self._field_guard = False
        self._close_pending = False
        self._seek_pending = 0.
        self._frame_thread = None
        self.kind = family(self.paths[0]) if self.paths else 'unknown'
        self.setObjectName('CitricaEditor')
        self.setStyleSheet(EDITOR_STYLE)
        self.setWindowTitle('Cítrica · ' + TOOLS[tool]['label'])
        self.resize(1120, 760)
        self.setMinimumSize(760, 570)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)
        header = QHBoxLayout()
        title_column = QVBoxLayout()
        title = QLabel(TOOLS[tool]['label'])
        title.setObjectName('EditorTitle')
        title_column.addWidget(title)
        title_column.addWidget(muted(self.paths[0].name if len(self.paths) == 1 else f'{len(self.paths)} arquivos selecionados'))
        header.addLayout(title_column, 1)
        brand = muted('CÍTRICA  /  ESTÚDIO LOCAL')
        brand.setWordWrap(False)
        header.addWidget(brand)
        outer.addLayout(header)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(14)
        preview = panel()
        self.preview_layout = QVBoxLayout(preview)
        self.preview_layout.setContentsMargins(14, 14, 14, 14)
        self.preview_layout.addWidget(muted('PRÉVIA'))
        self.preview_stack = QStackedWidget()
        self.placeholder = QLabel('Preparando prévia…')
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.preview_stack.addWidget(self.placeholder)
        self.preview_layout.addWidget(self.preview_stack, 1)
        self.preview_note = muted('')
        self.preview_layout.addWidget(self.preview_note)
        self.splitter.addWidget(preview)
        inspector = panel()
        inspector.setMinimumWidth(270)
        inspector.setMaximumWidth(370)
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(16, 16, 16, 16)
        inspector_layout.addWidget(muted('AJUSTES'))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        self.form = QFormLayout(form_widget)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.form.setVerticalSpacing(12)
        self.build_fields()
        scroll.setWidget(form_widget)
        inspector_layout.addWidget(scroll, 1)
        self.inspector_bottom = QVBoxLayout()
        inspector_layout.addLayout(self.inspector_bottom)
        inspector_layout.addWidget(muted('Uma nova cópia será salva ao lado do original. Nenhum arquivo será substituído.'))
        self.splitter.addWidget(inspector)
        self.splitter.setSizes([740, 300])
        outer.addWidget(self.splitter, 1)
        self.message = QLabel('Ajuste a prévia e salve uma cópia quando estiver pronto.')
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        outer.addWidget(self.progress)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(180)
        self.output.hide()
        outer.addWidget(self.output)
        bottom = QHBoxLayout()
        self.open_output = QPushButton('Abrir resultado')
        self.open_output.clicked.connect(self.open_result)
        self.open_output.hide()
        bottom.addWidget(self.open_output)
        bottom.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        self.apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText('Ler conteúdo' if tool in {'metadata', 'qr'} else 'Salvar cópia')
        self.apply_button.setObjectName('EditorPrimary')
        self.apply_button.clicked.connect(self.apply)
        self.close_button = self.buttons.button(QDialogButtonBox.StandardButton.Close)
        self.close_button.setText('Fechar')
        self.buttons.rejected.connect(self.close_or_cancel)
        bottom.addWidget(self.buttons)
        outer.addLayout(bottom)
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(100)
        self.update_timer.timeout.connect(self.update_image_preview)
        self.seek_timer = QTimer(self)
        self.seek_timer.setSingleShot(True)
        self.seek_timer.setInterval(100)
        self.seek_timer.timeout.connect(self.load_seek_frame)
        try:
            self.build_preview()
        except Exception as error:
            self.placeholder.setText('Não foi possível preparar a prévia.\n' + str(error))
            self.preview_stack.setCurrentWidget(self.placeholder)
            self.preview_note.setText('A exportação continua disponível; o motor validará o arquivo antes de salvar.')
        if tool == 'target_size':
            self.message.setText('Saída: WebP para imagens, MP3 para áudio, MP4 para vídeo. A resolução pode ser reduzida para caber no limite.')
        elif tool in {'redact_faces', 'redact_text'}:
            self.message.setText('Detecção automática local. Revise a cópia antes de compartilhar: algumas áreas podem não ser identificadas.')

    def build_fields(self):
        for key, title, default in TOOLS[self.tool]['fields']:
            if key in NUMBER_FIELDS:
                field = NumberField(default, *NUMBER_FIELDS[key])
                field.valueChanged.connect(self.fields_changed)
            elif key in {'rect', 'position'}:
                field = GeometryField(default, 4 if key == 'rect' else 2)
                field.changed.connect(self.fields_changed)
            elif key == 'shape':
                field = ChoiceField([('Texto', 'text'), ('Seta', 'arrow'), ('Retângulo', 'rectangle'),
                                     ('Elipse', 'ellipse'), ('Número', 'number')], default)
                field.currentIndexChanged.connect(self.fields_changed)
            elif key == 'style':
                field = ChoiceField([('Preto sólido', 'solid'), ('Desfoque', 'blur')], default)
                field.currentIndexChanged.connect(self.fields_changed)
            elif key == 'channels':
                field = ChoiceField([('Mono · 1 canal', '1'), ('Estéreo · 2 canais', '2')], default)
            elif key in {'color', 'color2'}:
                field = ColorField(default, optional=key == 'color2')
                field.changed.connect(self.fields_changed)
            elif key == 'background_image':
                field = FileField(default)
                field.changed.connect(self.fields_changed)
            elif key == 'aspect':
                field = ChoiceField([('Automática', ''), ('Quadrado · 1:1', '1:1'), ('Horizontal · 16:9', '16:9'),
                                     ('Vertical · 9:16', '9:16'), ('Fotografia · 4:3', '4:3')], default)
                field.currentIndexChanged.connect(self.fields_changed)
            else:
                field = QLineEdit(default)
                field.textChanged.connect(self.fields_changed)
            label = SHORT_LABELS.get(key, title)
            field.setAccessibleName(label)
            if isinstance(field, GeometryField):
                for name, box in zip(('X', 'Y', 'Largura', 'Altura'), field.boxes):
                    box.setAccessibleName(label + ' · ' + name)
            self.fields[key] = field
            self.form.addRow(label, field)
            if key in {'brightness', 'contrast', 'saturation', 'sharpness', 'quality'}:
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(1 if key == 'quality' else 0, 100 if key == 'quality' else 500)
                scale = 1 if key == 'quality' else 100
                slider.setValue(round(field.value() * scale))
                slider.setAccessibleName(label + ' · controle deslizante')
                slider.valueChanged.connect(lambda value, f=field, s=scale: f.setValue(value / s))
                field.valueChanged.connect(lambda value, s=slider, factor=scale: s.setValue(round(value * factor)))
                self.form.addRow(slider)
            if key == 'color2':
                clear = QPushButton('Remover gradiente')
                clear.clicked.connect(lambda: (self.fields['color2'].setText(''), self.fields_changed()))
                self.form.addRow(clear)
        if self.tool == 'bleep':
            self.form.addRow(muted('O trecho selecionado será substituído por um tom de 1000 Hz. A duração total será preservada.'))
        if self.tool == 'compress':
            self.form.addRow(muted('Qualidade menor reduz o tamanho. Para um limite exato, use Tamanho alvo.'))

    def build_preview(self):
        if self.kind == 'image':
            selectable = self.tool in {'crop', 'redact', 'annotate'}
            self.canvas = ImageSelection(self.paths[0], selectable=selectable)
            self.preview_stack.addWidget(self.canvas)
            self.preview_stack.setCurrentWidget(self.canvas)
            self.canvas.selected.connect(self.canvas_selected)
            if selectable:
                width, height = self.canvas.source_size
                self.fields['rect'].setText(f'0,0,{width},{height}')
                self.preview_note.setText('Arraste para selecionar • mova pelo centro • ajuste pelas alças amarelas • setas para mover')
                if self.tool == 'crop':
                    self.add_crop_presets()
            else:
                self.preview_note.setText(f'{self.canvas.source_size[0]} × {self.canvas.source_size[1]} pixels · '
                                          + ('prévia dos ajustes' if self.tool in {'adjust', 'background', 'collage'} else 'prévia do original'))
            if self.tool == 'edit_metadata':
                with Image.open(self.paths[0]) as raw:
                    exif = raw.getexif()
                    self.fill_metadata({'author': raw.info.get('Author', exif.get(315, '')),
                                        'title': raw.info.get('Title', exif.get(270, ''))})
            compare = QCheckBox('Ver original')
            compare.toggled.connect(lambda original: self.canvas.set_preview() if original else self.update_image_preview())
            self.compare = compare
            self.preview_layout.addWidget(compare)
            self.update_image_preview()
        elif self.kind in {'audio', 'video'}:
            self.build_media_preview()
        elif self.kind == 'pdf':
            self.build_pdf_preview()
        else:
            self.placeholder.setText('Selecione uma ferramenta compatível para editar este tipo de arquivo.\n'
                                     'Documentos de Office podem ser convertidos pela roda.')
            self.preview_note.setText('O Cítrica não substitui um editor de documentos, planilhas ou apresentações.')
        if len(self.paths) > 1:
            self.build_file_order()
            if self.tool != 'collage':
                self.preview_note.setText(f'Prévia: {self.paths[0].name} • os ajustes serão aplicados aos {len(self.paths)} arquivos na ordem da lista')

    def add_crop_presets(self):
        presets = ChoiceField([('Seleção livre', ''), ('Quadrado · 1:1', '1:1'), ('Horizontal · 16:9', '16:9'),
                               ('Vertical · 9:16', '9:16'), ('Fotografia · 4:3', '4:3')], '')
        presets.currentIndexChanged.connect(lambda: self.crop_aspect(presets.text()))
        self.form.insertRow(0, 'Proporção da seleção', presets)
        reset = QPushButton('Selecionar imagem inteira')
        reset.clicked.connect(lambda: self.canvas.set_selection(f'0,0,{self.canvas.source_size[0]},{self.canvas.source_size[1]}', emit=True))
        self.inspector_bottom.addWidget(reset)

    def crop_aspect(self, value):
        if not value or self.canvas is None:
            return
        a, b = map(float, value.split(':'))
        width, height = self.canvas.source_size
        cw, ch = min(width, height * a / b), min(height, width * b / a)
        self.canvas.set_selection(f'{round((width - cw) / 2)},{round((height - ch) / 2)},{round(cw)},{round(ch)}', emit=True)

    def canvas_selected(self, rect):
        self._field_guard = True
        if 'rect' in self.fields:
            if self.kind == 'video':
                values = list(map(int, rect.split(',')))
                sw, sh = self.canvas.source_size
                values[0], values[1] = min(values[0], sw - 2), min(values[1], sh - 2)
                values[2:] = [min(max(2, value - value % 2), available - available % 2)
                              for value, available in zip(values[2:], (sw - values[0], sh - values[1]))]
                rect = ','.join(map(str, values))
            self.fields['rect'].setText(rect)
        if 'position' in self.fields:
            self.fields['position'].setText(','.join(rect.split(',')[:2]))
        self._field_guard = False
        self.update_timer.start()

    def fields_changed(self, *args):
        if self._field_guard or not hasattr(self, 'update_timer'):
            return
        if self.canvas is not None and 'rect' in self.fields:
            self.canvas.set_selection(self.fields['rect'].text())
        if self.timeline is not None and 'start' in self.fields:
            self.timeline.set_range(float(self.fields['start'].text()),
                                    float(self.fields['start'].text()) + float(self.fields['duration'].text()))
            self.timeline_changed(self.timeline.start, self.timeline.end)
        if self.timeline is not None and 'time' in self.fields:
            self.seek_media(float(self.fields['time'].text()))
        self.update_timer.start()

    def update_image_preview(self):
        if self.canvas is None or self.kind != 'image' or getattr(self, 'compare', None) and self.compare.isChecked():
            return
        image = self.canvas.preview_source.copy()
        params = {key: field.text() for key, field in self.fields.items()}
        sx, sy = image.width / self.canvas.source_size[0], image.height / self.canvas.source_size[1]
        try:
            if self.tool == 'adjust':
                for key, enhancer in [('brightness', ImageEnhance.Brightness), ('contrast', ImageEnhance.Contrast),
                                      ('saturation', ImageEnhance.Color), ('sharpness', ImageEnhance.Sharpness)]:
                    image = enhancer(image).enhance(float(params[key]))
            elif self.tool == 'redact':
                from PIL import ImageDraw, ImageFilter
                x, y, width, height = map(int, params['rect'].split(','))
                box = (round(x * sx), round(y * sy), round((x + width) * sx), round((y + height) * sy))
                if params['style'] == 'blur':
                    image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(max(2, min(width * sx, height * sy) / 5))), box)
                else:
                    ImageDraw.Draw(image).rectangle(box, fill='black')
            elif self.tool in {'annotate', 'background'}:
                # Reuse the engine's drawing code on a bounded, correctly scaled
                # temporary image, including its platform-specific font fallback.
                from citrica.tools import _image_tool
                if self.tool == 'annotate':
                    params['font_size'] = str(max(6, round(float(params['font_size']) * sx)))
                    params['position'] = ','.join(str(round(int(v) * factor)) for v, factor in zip(params['position'].split(','), (sx, sy)))
                    params['rect'] = ','.join(str(max(1 if i > 1 else 0, round(int(v) * factor))) for i, (v, factor)
                                              in enumerate(zip(params['rect'].split(','), (sx, sy, sx, sy))))
                else:
                    for key in ('padding', 'radius'):
                        params[key] = str(round(float(params[key]) * sx))
                with tempfile.TemporaryDirectory(prefix='citrica-preview-') as temp:
                    source, output = Path(temp) / 'source.png', Path(temp) / 'preview.png'
                    image.save(source)
                    _image_tool(self.tool, source, params, output)
                    with Image.open(output) as result:
                        image = result.copy()
            elif self.tool == 'collage':
                columns = min(int(params['columns']), len(self.paths))
                width, gap = min(200, int(params['cell_width'])), round(int(params['spacing']) * min(1, 200 / int(params['cell_width'])))
                paths = self.paths[:64]
                rows = math.ceil(len(paths) / columns)
                image = Image.new('RGB', (columns * width + (columns + 1) * gap,
                                         rows * width + (rows + 1) * gap), params['color'])
                for index, path in enumerate(paths):
                    with Image.open(path) as raw:
                        tile = ImageOps.exif_transpose(raw).convert('RGBA')
                        tile.thumbnail((width, width), Image.Resampling.LANCZOS)
                        x = gap + index % columns * (width + gap) + (width - tile.width) // 2
                        y = gap + index // columns * (width + gap) + (width - tile.height) // 2
                        image.paste(tile, (x, y), tile)
                self.preview_note.setText('Prévia da composição' + (' · primeiros 64 arquivos' if len(self.paths) > 64 else ' · arraste a lista para mudar a ordem'))
            self.canvas.set_preview(image)
        except (ValueError, OSError, ConversionError):
            # Invalid intermediate input remains visible in the inspector. The
            # export validates the exact source parameters before producing data.
            self.canvas.set_preview()

    def build_media_preview(self):
        self.timeline = Timeline(self.tool in {'trim', 'bleep'})
        self.timeline.setEnabled(False)
        self.timeline.rangeChanged.connect(self.timeline_changed)
        self.timeline.seek.connect(self.seek_media)
        self.preview_layout.addWidget(self.timeline)
        transport = QHBoxLayout()
        self.play_button = QPushButton('▶ Reproduzir')
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle_playback)
        transport.addWidget(self.play_button)
        self.position_label = muted('00:00:00.000 / —')
        transport.addWidget(self.position_label, 1)
        external = QPushButton('Abrir no reprodutor')
        external.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths[0]))))
        transport.addWidget(external)
        self.preview_layout.addLayout(transport)
        self.preview_note.setText('Prévia do original • clique na faixa para buscar • Espaço: reproduzir/pausar')
        if QMediaPlayer is not None:
            self.player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.audio_output.setVolume(.7)
            self.player.setAudioOutput(self.audio_output)
            self.player.positionChanged.connect(self.playback_position)
            self.player.playbackStateChanged.connect(self.playback_state)
            self.player.errorOccurred.connect(self.playback_error)
            if self.kind == 'video':
                self.video_widget = QVideoWidget()
                self.preview_stack.addWidget(self.video_widget)
                self.player.setVideoOutput(self.video_widget)
            self.player.setSource(QUrl.fromLocalFile(str(self.paths[0])))
            self.play_button.setEnabled(True)
            volume = QSlider(Qt.Orientation.Horizontal)
            volume.setRange(0, 100)
            volume.setValue(70)
            volume.valueChanged.connect(lambda value: self.audio_output.setVolume(value / 100))
            self.form.addRow('Volume da prévia', volume)
        else:
            self.preview_note.setText('Reprodução interna indisponível. A faixa e a busca por quadro continuam disponíveis; use o reprodutor para ouvir.')
        if self.kind == 'audio':
            self.audio_overview = AudioOverview(self.paths[0].name)
            self.preview_stack.addWidget(self.audio_overview)
            self.preview_stack.setCurrentWidget(self.audio_overview)
        self.start_preview(PreviewWorker(self.paths[0]))

    def fill_metadata(self, tags):
        if self.tool != 'edit_metadata':
            return
        for field, keys in [('author', ('author', 'artist', 'AUTHOR', 'ARTIST')),
                            ('title', ('title', 'TITLE'))]:
            value = next((tags[key] for key in keys if tags.get(key)), '')
            self.fields[field].setText(str(value))

    def start_preview(self, thread):
        self.preview_threads.append(thread)
        thread.ready.connect(self.preview_ready)
        thread.failed.connect(lambda error: self.preview_note.setText('Prévia parcial: ' + error))
        thread.finished.connect(lambda: self.preview_finished(thread))
        thread.start()

    def preview_finished(self, thread):
        if thread in self.preview_threads:
            self.preview_threads.remove(thread)
        if thread is self._frame_thread:
            self._frame_thread = None
            if not self._close_pending and abs(getattr(thread, 'instant', 0) - self._seek_pending) > .05:
                self.seek_timer.start()
        if self._close_pending and not self.busy():
            self.close()

    def preview_ready(self, result):
        if self._close_pending:
            return
        if 'duration' in result:
            self.media_duration = result['duration']
            self.media_info = result['info']
            self.fill_metadata(result['info'].get('format', {}).get('tags', {}))
            self.timeline.duration = self.media_duration
            initial = float(self.fields['duration'].text()) if 'duration' in self.fields else self.media_duration
            self.timeline.set_range(0, min(initial, self.media_duration))
            self.timeline.setEnabled(True)
            self.position_label.setText(f'{timestamp(0)} / {timestamp(self.media_duration)}')
            if 'duration' in self.fields:
                self.fields['duration'].setMaximum(self.media_duration)
                self.fields['duration'].setValue(self.timeline.end)
                self.fields['start'].setMaximum(max(0, self.media_duration - .01))
                end = NumberField(self.timeline.end, .01, self.media_duration, 3, ' s')
                end.valueChanged.connect(self.end_changed)
                end.setAccessibleName('Fim')
                self.end_field = end
                self.form.insertRow(2, 'Fim', end)
            if self.kind == 'audio':
                stream = next((item for item in result['info']['streams'] if item['codec_type'] == 'audio'), {})
                channels = stream.get('channels', '?')
                rate = float(stream.get('sample_rate', 0)) / 1000
                self.audio_overview.details = f'{timestamp(self.media_duration)}  ·  {rate:g} kHz  ·  {channels} canal(is)'
                self.audio_overview.update()
            if 'time' in self.fields:
                self.fields['time'].setMaximum(max(0, self.media_duration - .001))
            if self.kind == 'video':
                stream = next((item for item in result['info']['streams'] if item['codec_type'] == 'video'), None)
                if stream:
                    self.source_video_size = oriented_video_size(stream)
                    if self.tool == 'crop':
                        width, height = self.source_video_size
                        self.fields['rect'].setText(f'0,0,{width - width % 2},{height - height % 2}')
                self._seek_pending = 0.
                self.load_seek_frame()
        if 'frames' in result:
            self.timeline.frames = [QPixmap.fromImage(QImage.fromData(frame)) for frame in result['frames']]
            self.timeline.update()
        if 'waveform' in result:
            self.timeline.waveform = QPixmap.fromImage(QImage.fromData(result['waveform']))
            self.timeline.update()
            if hasattr(self, 'audio_overview'):
                self.audio_overview.waveform = self.timeline.waveform
                if result.get('waveform_sampled'):
                    self.audio_overview.details += '  ·  forma de onda amostrada'
                    self.preview_note.setText('Forma de onda amostrada • reprodução e exportação usam o arquivo integral • clique na faixa para buscar')
                self.audio_overview.update()
        if 'frame' in result and self.kind == 'video':
            from io import BytesIO
            try:
                with Image.open(BytesIO(result['frame'])) as raw:
                    image = raw.convert('RGBA')
            except OSError:
                self.preview_note.setText('Este instante não possui quadro decodificável. Escolha um instante anterior.')
                return
            if self.canvas is None:
                self.canvas = ImageSelection(image=image, selectable=self.tool == 'crop')
                # FFmpeg previews are scaled; geometry must refer to the source.
                self.canvas.source_size = getattr(self, 'source_video_size', image.size)
                self.canvas.selection = QRectF(0, 0, *self.canvas.source_size)
                self.canvas.selected.connect(self.canvas_selected)
                self.preview_stack.addWidget(self.canvas)
                if self.tool == 'crop':
                    self.canvas.set_selection(self.fields['rect'].text())
                    self.add_crop_presets()
            else:
                self.canvas.display = QPixmap.fromImage(ImageQt(image))
                self.canvas.update()
            if self.player is None or self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.preview_stack.setCurrentWidget(self.canvas)

    def timeline_changed(self, start, end):
        if 'start' not in self.fields:
            return
        self._field_guard = True
        self.fields['start'].setValue(start)
        self.fields['duration'].setValue(end - start)
        if hasattr(self, 'end_field'):
            blocked = self.end_field.blockSignals(True)
            self.end_field.setValue(end)
            self.end_field.blockSignals(blocked)
        self._field_guard = False

    def end_changed(self, end):
        self.timeline.set_range(self.timeline.start, end, emit=True)

    def seek_media(self, seconds):
        if self.media_duration is None:
            return
        seconds = min(max(0, seconds), max(0, self.media_duration - .001))
        self.timeline.set_position(seconds)
        self.position_label.setText(f'{timestamp(seconds)} / {timestamp(self.media_duration)}')
        if self.tool == 'snapshot':
            blocked = self.fields['time'].blockSignals(True)
            self.fields['time'].setValue(seconds)
            self.fields['time'].blockSignals(blocked)
        self._seek_pending = seconds
        if self.player is not None:
            self.player.setPosition(round(seconds * 1000))
        if self.kind == 'video' and (self.player is None or self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState):
            self.seek_timer.start()

    def load_seek_frame(self):
        if self.media_duration is None or self._close_pending or self.kind != 'video':
            return
        if self._frame_thread is not None and self._frame_thread.isRunning():
            self._frame_thread.cancel.set()
            return
        self._frame_thread = PreviewWorker(self.paths[0], self._seek_pending)
        self.start_preview(self._frame_thread)

    def toggle_playback(self):
        if self.player is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.timeline.selection_enabled and not self.timeline.start <= self.player.position() / 1000 < self.timeline.end:
                self.player.setPosition(round(self.timeline.start * 1000))
            if self.video_widget is not None:
                self.preview_stack.setCurrentWidget(self.video_widget)
            self.player.play()

    def playback_position(self, position):
        if self.media_duration is None:
            return
        self.timeline.set_position(position / 1000)
        self.position_label.setText(f'{timestamp(position / 1000)} / {timestamp(self.media_duration)}')
        if self.timeline.selection_enabled and position / 1000 >= self.timeline.end and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()

    def playback_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText('Ⅱ Pausar' if playing else '▶ Reproduzir')
        if not playing and self.kind == 'video' and self.media_duration is not None:
            self._seek_pending = self.player.position() / 1000
            self.seek_timer.start()

    def playback_error(self, error, detail):
        if QMediaPlayer is None or error == QMediaPlayer.Error.NoError:
            return
        self.play_button.setEnabled(False)
        self.preview_note.setText('O reprodutor interno não abriu este codec. A prévia por quadro e a exportação continuam disponíveis. ' + detail)
        if self.canvas is not None:
            self.preview_stack.setCurrentWidget(self.canvas)

    def build_pdf_preview(self):
        import pymupdf
        self.pdf = pymupdf.open(self.paths[0])
        if self.pdf.needs_pass:
            raise ConversionError('PDF protegido: desbloqueie uma cópia antes de editar.')
        if not self.pdf.page_count:
            raise ConversionError('O PDF não contém páginas.')
        self.fill_metadata(self.pdf.metadata or {})
        self.pdf_image = QLabel()
        self.pdf_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pdf_image.setMinimumSize(240, 200)
        self.pdf_image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview_stack.addWidget(self.pdf_image)
        self.preview_stack.setCurrentWidget(self.pdf_image)
        navigation = QHBoxLayout()
        previous, following = QPushButton('← Anterior'), QPushButton('Próxima →')
        self.pdf_page = QSpinBox()
        self.pdf_page.setAccessibleName('Página do PDF na prévia')
        self.pdf_page.setRange(1, self.pdf.page_count)
        self.pdf_page.setPrefix('Página ')
        self.pdf_page.setSuffix(f' de {self.pdf.page_count}')
        previous.clicked.connect(lambda: self.pdf_page.setValue(max(1, self.pdf_page.value() - 1)))
        following.clicked.connect(lambda: self.pdf_page.setValue(min(self.pdf.page_count, self.pdf_page.value() + 1)))
        self.pdf_page.valueChanged.connect(self.render_pdf_page)
        navigation.addWidget(previous)
        navigation.addWidget(self.pdf_page, 1)
        navigation.addWidget(following)
        self.preview_layout.addLayout(navigation)
        self.preview_note.setText(f'{self.pdf.page_count} página(s) • prévia do original • a exportação cria uma nova cópia')
        self.render_pdf_page(1)
        if self.tool == 'reorder_pdf':
            self.pdf_order = QListWidget()
            self.pdf_order.setAccessibleName('Ordem das páginas')
            self.pdf_order.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            self.pdf_order.setDefaultDropAction(Qt.DropAction.MoveAction)
            for number in range(1, self.pdf.page_count + 1):
                item = QListWidgetItem(f'Página {number}')
                item.setData(Qt.ItemDataRole.UserRole, number)
                self.pdf_order.addItem(item)
            self.pdf_order.currentItemChanged.connect(lambda item, _: self.pdf_page.setValue(item.data(Qt.ItemDataRole.UserRole)) if item else None)
            self.pdf_order.model().rowsMoved.connect(self.sync_pdf_order)
            self.form.addRow(muted('Arraste as páginas para reorganizar. Clique para conferir a prévia.'))
            self.form.addRow(self.pdf_order)
            controls = QHBoxLayout()
            for title, step in [('↑ Subir', -1), ('↓ Descer', 1)]:
                button = QPushButton(title)
                button.clicked.connect(lambda checked=False, delta=step: self.move_pdf_page(delta))
                controls.addWidget(button)
            self.form.addRow(controls)
            self.sync_pdf_order()
        elif self.tool == 'split_pdf':
            self.form.addRow(muted(f'Serão criados {self.pdf.page_count} PDFs, um por página.'))

    def render_pdf_page(self, number):
        page = self.pdf.load_page(number - 1)
        scale = min(1.7, 950 / max(1, page.rect.width), 650 / max(1, page.rect.height))
        pixmap = page.get_pixmap(matrix=__import__('pymupdf').Matrix(scale, scale), alpha=False)
        image = QImage(pixmap.samples, pixmap.width, pixmap.height, pixmap.stride, QImage.Format.Format_RGB888).copy()
        self.pdf_image.setPixmap(QPixmap.fromImage(image).scaled(690, 490, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def sync_pdf_order(self, *args):
        self.fields['pages'].setText(','.join(str(self.pdf_order.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.pdf_order.count())))

    def move_pdf_page(self, delta):
        row = self.pdf_order.currentRow()
        if row >= 0 and 0 <= row + delta < self.pdf_order.count():
            item = self.pdf_order.takeItem(row)
            self.pdf_order.insertItem(row + delta, item)
            self.pdf_order.setCurrentRow(row + delta)
            self.sync_pdf_order()

    def build_file_order(self):
        files = QListWidget()
        files.setMaximumHeight(130)
        files.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        files.setDefaultDropAction(Qt.DropAction.MoveAction)
        for path in self.paths:
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            files.addItem(item)
        def reorder_files(*args):
            self.paths = [Path(files.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(files.count())]
            self.update_timer.start()
        files.model().rowsMoved.connect(reorder_files)
        self.form.addRow('Arquivos · arraste para ordenar', files)

    def validate_params(self):
        params = {key: field.text() for key, field in self.fields.items()}
        if self.kind in {'audio', 'video'} and self.tool in {'trim', 'bleep', 'snapshot'}:
            if self.media_duration is None:
                raise ConversionError('Aguarde a leitura da duração antes de salvar o trecho.')
            if 'start' in params:
                start, duration = float(params['start']), float(params['duration'])
                if start + duration > self.media_duration + .0005:
                    raise ConversionError('O fim do trecho precisa estar dentro da duração do arquivo.')
            elif float(params['time']) >= self.media_duration:
                raise ConversionError('Escolha um instante anterior ao fim do arquivo.')
        if self.canvas is not None and 'rect' in params:
            from citrica.tools import rectangle
            rectangle(params, *self.canvas.source_size)
        if self.tool == 'reorder_pdf' and self.pdf is not None:
            try:
                pages = [int(value) for value in params['pages'].split(',')]
            except ValueError:
                raise ConversionError('Use números de páginas separados por vírgula.') from None
            if sorted(pages) != list(range(1, self.pdf.page_count + 1)):
                raise ConversionError('Inclua cada página uma única vez na nova ordem.')
        return params

    def apply(self):
        if self.worker and self.worker.isRunning():
            return
        try:
            params = self.validate_params()
        except (ValueError, ConversionError) as error:
            self.message.setText('Verifique os ajustes: ' + str(error))
            return
        if self.player is not None:
            self.player.pause()
        self.latest_output = None
        self.open_output.hide()
        self.output.hide()
        self.worker = self.worker_factory(self.tool, self.paths, params)
        self.worker.done.connect(self.tool_done)
        self.worker.failed.connect(self.tool_failed)
        self.worker.finished.connect(self.tool_finished)
        self.apply_button.setEnabled(False)
        self.close_button.setText('Cancelar operação')
        self.progress.show()
        self.message.setText('Processando localmente… O original está preservado.')
        self.worker.start()

    def tool_done(self, result):
        if self.worker.cancel.is_set() and not result.get('outputs'):
            self.message.setText('Operação cancelada. O original foi preservado.')
            return
        if 'text' in result:
            self.output.setPlainText(result['text'])
            self.output.show()
            self.message.setText('Leitura concluída. Selecione e copie o conteúdo abaixo.')
        else:
            outputs = result.get('outputs', [])
            self.message.setText(f'{len(outputs)} cópia(s) salva(s). O original foi preservado.' if outputs else 'Nenhum arquivo foi alterado.')
            if outputs:
                if self.worker.cancel.is_set():
                    self.message.setText(f'{len(outputs)} cópia(s) concluída(s) antes do cancelamento. O original foi preservado.')
                self.latest_output = Path(outputs[0])
                self.open_output.show()
                self.output.setPlainText('\n'.join(str(path) for path in outputs))
                self.output.show()

    def tool_failed(self, error):
        if self.worker.cancel.is_set():
            self.message.setText('Operação cancelada. O original foi preservado.')
        else:
            self.message.setText('Não foi possível salvar: ' + error)

    def tool_finished(self):
        self.progress.hide()
        self.apply_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.close_button.setText('Fechar')

    def open_result(self):
        if self.latest_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.latest_output)))

    def busy(self):
        return bool(self.worker and self.worker.isRunning() or any(thread.isRunning() for thread in self.preview_threads))

    def cancel_export(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.message.setText('Cancelando… Aguarde a limpeza dos arquivos temporários.')
            self.close_button.setEnabled(False)
            return True
        return False

    def close_or_cancel(self):
        if not self.cancel_export():
            self.close()

    def closeEvent(self, event):
        if self.cancel_export():
            event.ignore()
            return
        self._close_pending = True
        self.seek_timer.stop()
        self.update_timer.stop()
        if self.player is not None:
            self.player.stop()
            self.player.setSource(QUrl())
        for thread in self.preview_threads:
            thread.cancel.set()
        if any(thread.isRunning() for thread in self.preview_threads):
            event.ignore()
        else:
            if self.pdf is not None:
                self.pdf.close()
                self.pdf = None
            event.accept()

    def reject(self):
        if not self.cancel_export():
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and self.player is not None and not isinstance(self.focusWidget(), (QLineEdit, QPlainTextEdit)):
            self.toggle_playback()
            event.accept()
        else:
            super().keyPressEvent(event)
