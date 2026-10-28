"""Transparent Qt/Win32 drop target with the same annular design as GNOME."""
import math
import logging
import struct
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

SIZE, CENTER, INNER, OUTER, LABEL_RADIUS = 380, 190, 66, 170, 122
TAU = math.tau
QA = logging.getLogger('citrica.qa')
GLYPHS = {'compress': '↙', 'crop': '✂', 'adjust': '◐', 'annotate': '✎', 'background': '▣',
          'redact': '◩', 'metadata': 'ⓘ', 'edit_metadata': '✎', 'strip': '⌫', 'images_pdf': '▧',
          'collage': '▦', 'qr': '▦', 'redact_faces': '◉', 'redact_text': 'T', 'target_size': '↔',
          'trim': '✂', 'speed': '»', 'split_media': 'Ⅱ', 'join_media': '⋈', 'snapshot': '▣',
          'normalize': '≋', 'bleep': '♪', 'channels': '♫', 'merge_pdf': '⋈', 'split_pdf': 'Ⅱ',
          'reorder_pdf': '↕', 'copy': '▧', 'move': '↗', 'copy_path': '↗', 'terminal': '>_',
          'float': '▣', 'share': '↗'}


def hit_test(x, y, count):
    if not count or not INNER < math.hypot(x - CENTER, y - CENTER) <= OUTER + 8:
        return -1
    angle = (math.atan2(y - CENTER, x - CENTER) + math.pi / 2) % TAU
    return math.floor(angle / TAU * count + .5) % count


def offered_paths(mime):
    QA.debug('ole.urls begin')
    urls = mime.urls() if mime.hasUrls() else []
    QA.debug('ole.urls end count=%s', len(urls))
    if not urls:
        # Explorer and shell extensions may expose CF_HDROP/FileNameW without
        # Qt synthesizing text/uri-list. Read only these filesystem formats.
        for name in mime.formats():
            if 'value="FileNameW"' in name:
                data = bytes(mime.data(name))
                if len(data) > 1024*1024 or len(data) % 2:
                    return []
                try:
                    names = [s for s in data.decode('utf-16-le').split('\0') if s]
                except UnicodeError:
                    return []
                from PySide6.QtCore import QUrl
                urls = [QUrl.fromLocalFile(s) for s in names]
                break
            if 'value="CF_HDROP"' in name:
                data = bytes(mime.data(name))
                if not 20 <= len(data) <= 1024*1024:
                    return []
                offset, _x, _y, _nonclient, wide = struct.unpack_from('<IiiII', data)
                if not wide or offset < 20 or offset > len(data) or (len(data)-offset) % 2:
                    return []
                try:
                    names = [s for s in data[offset:].decode('utf-16-le').split('\0') if s]
                except UnicodeError:
                    return []
                from PySide6.QtCore import QUrl
                urls = [QUrl.fromLocalFile(s) for s in names]
                break
    if not urls or len(urls) > 1000:
        return []
    paths = []
    for url in urls:
        if not url.isLocalFile():
            return []
        path = Path(url.toLocalFile()).resolve()
        if not path.is_file():
            return []
        if path not in paths:
            paths.append(path)
    return paths


def point(radius, angle):
    return QPointF(CENTER + radius * math.cos(angle), CENTER + radius * math.sin(angle))


def arc(path, radius, start, end):
    count = max(1, math.ceil(abs(end - start) / (math.pi / 2)))
    step = (end - start) / count
    for i in range(count):
        a, b = start + i * step, start + (i + 1) * step
        k = 4 / 3 * math.tan(step / 4)
        p, q = point(radius, a), point(radius, b)
        path.cubicTo(QPointF(p.x() - k * radius * math.sin(a), p.y() + k * radius * math.cos(a)),
                     QPointF(q.x() + k * radius * math.sin(b), q.y() - k * radius * math.cos(b)), q)


def sector_path(index, count):
    angle, half, gap, corner = -math.pi / 2 + index * TAU / count, math.pi / count, 3, 10
    oa, ob = angle - half + gap / OUTER, angle + half - gap / OUTER
    ia, ib = angle - half + gap / INNER, angle + half - gap / INNER
    od, inner_delta = corner / OUTER, corner / INNER
    path = QPainterPath(point(INNER + corner, ia))
    path.lineTo(point(OUTER - corner, oa))
    path.quadTo(point(OUTER, oa), point(OUTER, oa + od))
    arc(path, OUTER, oa + od, ob - od)
    path.quadTo(point(OUTER, ob), point(OUTER - corner, ob))
    path.lineTo(point(INNER + corner, ib))
    path.quadTo(point(INNER, ib), point(INNER, ib - inner_delta))
    arc(path, INNER, ib - inner_delta, ia + inner_delta)
    path.quadTo(point(INNER, ia), point(INNER + corner, ia))
    path.closeSubpath()
    return path


class Wheel(QWidget):
    filesOffered = Signal(object)
    chosen = Signal(object)
    cancelled = Signal()
    pickFiles = Signal()
    dropped = Signal(object, object)
    offerObserved = Signal(object)

    def __init__(self, animations=lambda: True):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFixedSize(SIZE, SIZE + 36)
        self.setWindowTitle('Cítrica · roda de arquivos')
        self.setAccessibleName('Cítrica · arraste e solte no formato desejado')
        self.animations = animations
        self.items, self.paths, self.info = [], [], None
        self.selected, self.progress, self._hover_value = -1, 1., {}
        self._closing, self._closing_frame = False, None
        self.probing = False
        self._geometry, self._keyboard_point = [], None
        self._empty_geometry = [sector_path(i, 8) for i in range(8)]
        self._preview = QPixmap()
        self._motion = QVariantAnimation(self)
        self._motion.valueChanged.connect(self._motion_value)
        self._motion.finished.connect(self._motion_finished)
        self._hover = QVariantAnimation(self)
        self._hover.setDuration(140)
        self._hover.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover.valueChanged.connect(self._hover_frame)
        self._hover_from, self._hover_to = {}, {}

    def _motion_value(self, value):
        self.progress = float(value)
        self.update()

    def _motion_finished(self):
        if self._closing:
            self.hide()
            self._closing_frame = None
            self._closing = False

    def present(self, position, probing=False):
        QA.debug('wheel.present begin probing=%s mapped=%s', probing, self.isVisible())
        self._motion.stop()
        self._closing, self._closing_frame = False, None
        self.probing = probing
        self.move(position)
        # Revealing an already mapped probe during DragEnter must not remap or
        # raise its HWND: that can invalidate Explorer's current OLE target.
        if not self.isVisible():
            QA.debug('wheel.show begin')
            self.show()
            QA.debug('wheel.show end; raise begin')
            self.raise_()
            QA.debug('wheel.raise end')
        if self.animations() and not probing:
            self._motion.setStartValue(0.)
            self._motion.setEndValue(1.)
            self._motion.setDuration(286)
            self._motion.setEasingCurve(QEasingCurve.Type.Linear)
            self._motion.start()
        else:
            self.progress = 1.
            self.update()
        QA.debug('wheel.present end')

    def clear(self):
        self._hover.stop()
        self.items, self.paths, self.info = [], [], None
        self._preview = QPixmap()
        self.selected, self._hover_value, self._geometry = -1, {}, []
        self._keyboard_point = None
        self.update()

    def dismiss(self):
        self._motion.stop()
        if self.probing:
            self.probing = False
            self.clear()
            self.hide()
            return
        self._closing_frame = self.grab() if self.isVisible() and self.animations() else None
        self.clear()
        if not self.isVisible() or not self.animations():
            self.hide()
            self._closing_frame = None
            return
        self._closing = True
        self._motion.setStartValue(1.)
        self._motion.setEndValue(0.)
        self._motion.setDuration(130)
        self._motion.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._motion.start()

    def set_palette(self, paths, items, info):
        self.paths, self.items, self.info = list(paths), list(items), info
        self._preview = QPixmap(info['preview']) if info and info.get('preview') else QPixmap()
        self.selected, self._hover_value = -1, {}
        self._geometry = [sector_path(i, len(items)) for i in range(len(items))]
        self._keyboard_point = None
        self.setAccessibleDescription(info.get('label', '') if info else 'Nenhum arquivo selecionado')
        self.update()

    def select(self, index):
        if self.selected == index:
            return
        self.selected = index
        self._hover.stop()
        self._hover_from = dict(self._hover_value)
        self._hover_to = {i: float(i == index) for i in range(len(self.items))}
        if self.animations():
            self._hover.setStartValue(0.)
            self._hover.setEndValue(1.)
            self._hover.start()
        else:
            self._hover_value = dict(self._hover_to)
            self.update()

    def _hover_frame(self, value):
        self._hover_value = {i: self._hover_from.get(i, 0) +
                             (target - self._hover_from.get(i, 0)) * float(value)
                             for i, target in self._hover_to.items()}
        self.update()

    def pointer(self, global_point):
        if self._closing or self._keyboard_point == global_point:
            return
        self._keyboard_point = None
        p = self.mapFromGlobal(global_point)
        self.select(hit_test(p.x(), p.y(), len(self.items)))

    def keyboard(self, key, global_point):
        if key == 'Escape':
            self.cancelled.emit()
        elif key == 'Return' and self.selected >= 0:
            self.chosen.emit(self.items[self.selected])
        elif self.items and key in {'Left', 'Right'}:
            n = len(self.items)
            index = ((n - 1 if key == 'Left' else 0) if self.selected < 0 else
                     (self.selected + (-1 if key == 'Left' else 1)) % n)
            self.select(index)
            self._keyboard_point = global_point

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # One alpha unit makes the otherwise transparent centre a real OLE drop
        # target on Windows layered windows. It does not obscure the desktop.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        if self.probing:
            return
        if self._closing_frame is not None:
            painter.setOpacity(self.progress)
            painter.drawPixmap(0, 0, self._closing_frame)
            return
        elapsed = self.progress * 286
        opening = QEasingCurve(QEasingCurve.Type.OutCubic).valueForProgress(min(1, elapsed / 240))
        painter.setOpacity(opening)
        painter.translate(CENTER, CENTER)
        scale = .88 + .12 * opening
        painter.scale(scale, scale)
        painter.translate(-CENTER, -CENTER)
        halo = QPainterPath()
        halo.addEllipse(QPointF(CENTER, CENTER), OUTER + 8, OUTER + 8)
        halo.addEllipse(QPointF(CENTER, CENTER), INNER - 6, INNER - 6)
        painter.fillPath(halo, QColor(255, 227, 194, 61))
        count = len(self.items) or 8
        for i in range(count):
            item = self.items[i] if self.items else None
            path = self._geometry[i] if item else self._empty_geometry[i]
            angle = -math.pi / 2 + i * TAU / count
            progress = min(1, max(0, (elapsed - i * 8) / 230)) if item else 1
            bounce = QEasingCurve(QEasingCurve.Type.OutBack).valueForProgress(progress)
            active = self._hover_value.get(i, 0)
            painter.save()
            painter.setOpacity(opening * min(1, progress * 2))
            offset = -12 * (1 - bounce) + active * 4
            painter.translate(math.cos(angle) * offset, math.sin(angle) * offset)
            painter.translate(CENTER, CENTER)
            painter.scale(.92 + .08 * bounce + .015 * active, .92 + .08 * bounce + .015 * active)
            painter.translate(-CENTER, -CENTER)
            gradient = QLinearGradient(0, 0, SIZE, SIZE)
            gradient.setColorAt(0, QColor(255, 240, 204, 240 if item else 72))
            gradient.setColorAt(1, QColor(255, 217, 204, 240 if item else 72))
            painter.fillPath(path, gradient)
            if active:
                painter.setOpacity(opening * active)
                selected = QLinearGradient(0, 0, SIZE, SIZE)
                selected.setColorAt(0, QColor('#ffa64c'))
                selected.setColorAt(1, QColor('#fa4d1a'))
                painter.fillPath(path, selected)
                painter.setOpacity(opening)
            if item:
                center = point(LABEL_RADIUS, angle)
                painter.setPen(QColor('#251e1a'))
                if item['kind'] != 'format':
                    painter.setFont(QFont('Segoe UI Symbol', 15))
                    painter.drawText(QRectF(center.x()-40, center.y()-25, 80, 26),
                                     Qt.AlignmentFlag.AlignCenter, '⋯' if item['kind'] == 'page' else GLYPHS.get(item['id'], '◇'))
                font = QFont('Segoe UI')
                font.setPixelSize(13 if item['kind'] == 'format' else 10)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(QRectF(center.x()-40, center.y()-(12 if item['kind'] == 'format' else -2), 80, 38),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, item['label'].upper())
            painter.restore()
        if self.info:
            preview = self._preview
            if not preview.isNull():
                painter.drawPixmap(QRectF(CENTER-32, CENTER-38, 64, 64), preview, QRectF(preview.rect()))
            else:
                painter.setPen(QColor('#49372a'))
                painter.setFont(QFont('Segoe UI Symbol', 26))
                painter.drawText(QRectF(CENTER-35, CENTER-45, 70, 65), Qt.AlignmentFlag.AlignCenter, '▧')
            size = self.info.get('bytes', 0)
            text = f'{size / 1024:.1f} KB' if size >= 1024 else f'{size} bytes'
        else:
            painter.setPen(QColor('#49372a'))
            painter.setFont(QFont('Segoe UI Symbol', 30))
            painter.drawText(QRectF(CENTER-35, CENTER-45, 70, 65), Qt.AlignmentFlag.AlignCenter, '+')
            text = 'Arraste um arquivo'
        if self.selected >= 0:
            text = self.items[self.selected]['label']
        pill = QRectF(CENTER-74, CENTER+24, 148, 30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 246, 231, 245))
        painter.drawRoundedRect(pill, 15, 15)
        painter.setPen(QColor('#291f1a'))
        font = QFont('Segoe UI')
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pill.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 132))
        if not self.paths:
            hint = QRectF(6, SIZE-4, SIZE-12, 28)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(hint, 14, 14)
            painter.setPen(QColor('#291f1a'))
            painter.drawText(hint, Qt.AlignmentFlag.AlignCenter, 'Solte um arquivo aqui · Esc para fechar')

    def dragEnterEvent(self, event):
        QA.debug('ole.drag_enter formats begin')
        self.offerObserved.emit(list(event.mimeData().formats()))
        QA.debug('ole.drag_enter formats end; paths begin')
        paths = offered_paths(event.mimeData())
        QA.debug('ole.drag_enter paths end files=%s', len(paths))
        if paths and not self._closing:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.filesOffered.emit(paths)
            QA.debug('ole.drag_enter accepted')
        else:
            event.ignore()
            if self.probing:
                self.cancelled.emit()

    def dragMoveEvent(self, event):
        paths = offered_paths(event.mimeData())
        if paths and not self._closing:
            if paths != self.paths:
                self.filesOffered.emit(paths)
            self.select(hit_test(event.position().x(), event.position().y(), len(self.items)))
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = offered_paths(event.mimeData())
        if paths and not self._closing:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.dropped.emit(paths, event.position().toPoint())
        else:
            event.ignore()
            self.cancelled.emit()

    def mouseMoveEvent(self, event):
        self.select(hit_test(event.position().x(), event.position().y(), len(self.items)))

    def mouseReleaseEvent(self, event):
        if self.probing:
            self.cancelled.emit()
            return
        if event.button() != Qt.MouseButton.LeftButton or self._closing:
            return
        p = event.position()
        if math.hypot(p.x()-CENTER, p.y()-CENTER) <= INNER:
            if not self.paths:
                self.pickFiles.emit()
            else:
                self.cancelled.emit()
            return
        self.select(hit_test(p.x(), p.y(), len(self.items)))
        if self.selected >= 0:
            self.chosen.emit(self.items[self.selected])
        else:
            self.cancelled.emit()
