"""Original outline icons: no font lookup while Explorer owns an OLE drag."""
from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen


def _path(*commands):
    path = QPainterPath()
    for command, *values in commands:
        if command == 'M':
            path.moveTo(*values)
        elif command == 'L':
            path.lineTo(*values)
        elif command == 'C':
            path.cubicTo(*values)
        elif command == 'R':
            path.addRoundedRect(QRectF(*values), 1, 1)
        elif command == 'E':
            path.addEllipse(QRectF(*values))
        elif command == 'Z':
            path.closeSubpath()
    return path


# Coordinates use a 24px viewbox; paths remain vector at every desktop scale.
_SHAPES = {
    'document': [('M', 6, 3), ('L', 14, 3), ('L', 19, 8), ('L', 19, 21),
                 ('L', 6, 21), ('Z',), ('M', 14, 3), ('L', 14, 8), ('L', 19, 8),
                 ('M', 9, 12), ('L', 16, 12), ('M', 9, 16), ('L', 16, 16)],
    'add': [('M', 5, 12), ('L', 19, 12), ('M', 12, 5), ('L', 12, 19)],
    'page': [('E', 4, 11, 2, 2), ('E', 11, 11, 2, 2), ('E', 18, 11, 2, 2)],
    'compress': [('M', 3, 3), ('L', 9, 9), ('M', 4, 9), ('L', 9, 9), ('L', 9, 4),
                 ('M', 21, 21), ('L', 15, 15), ('M', 20, 15), ('L', 15, 15), ('L', 15, 20)],
    'target_size': [('R', 3, 3, 18, 18), ('M', 7, 12), ('L', 17, 12),
                    ('M', 10, 9), ('L', 7, 12), ('L', 10, 15),
                    ('M', 14, 9), ('L', 17, 12), ('L', 14, 15)],
    'crop': [('M', 7, 2), ('L', 7, 17), ('L', 22, 17),
             ('M', 2, 7), ('L', 17, 7), ('L', 17, 22)],
    'adjust': [('M', 5, 3), ('L', 5, 21), ('M', 12, 3), ('L', 12, 21),
               ('M', 19, 3), ('L', 19, 21), ('R', 2, 7, 6, 4),
               ('R', 9, 14, 6, 4), ('R', 16, 6, 6, 4)],
    'annotate': [('M', 4, 16), ('L', 16, 4), ('L', 20, 8), ('L', 8, 20), ('L', 3, 21),
                 ('Z',), ('M', 13, 7), ('L', 17, 11)],
    'background': [('R', 3, 4, 18, 16), ('E', 6, 7, 4, 4),
                   ('M', 4, 19), ('L', 11, 12), ('L', 15, 16), ('L', 18, 13), ('L', 21, 16)],
    'redact': [('R', 3, 4, 18, 16), ('R', 6, 9, 12, 6),
               ('M', 7, 12), ('L', 17, 12)],
    'metadata': [('E', 3, 3, 18, 18), ('E', 11.5, 6.5, 1, 1),
                 ('M', 10, 11), ('L', 12, 11), ('L', 12, 17), ('M', 10, 17), ('L', 14, 17)],
    'strip': [('M', 3, 14), ('L', 13, 4), ('L', 21, 12), ('L', 12, 21),
              ('L', 9, 21), ('Z',), ('M', 7, 10), ('L', 15, 18), ('M', 12, 21), ('L', 22, 21)],
    'collage': [('R', 3, 3, 7, 7), ('R', 14, 3, 7, 7),
                ('R', 3, 14, 7, 7), ('R', 14, 14, 7, 7)],
    'qr': [('R', 3, 3, 6, 6), ('R', 15, 3, 6, 6), ('R', 3, 15, 6, 6),
           ('M', 15, 15), ('L', 18, 15), ('L', 18, 18), ('L', 21, 18),
           ('M', 15, 18), ('L', 15, 21), ('M', 18, 21), ('L', 21, 21)],
    'redact_faces': [('E', 7, 2, 10, 11), ('R', 7, 6, 10, 3),
                     ('M', 3, 22), ('C', 3, 12, 21, 12, 21, 22)],
    'redact_text': [('M', 4, 5), ('L', 20, 5), ('M', 12, 5), ('L', 12, 18),
                    ('M', 7, 18), ('L', 17, 18), ('M', 3, 21), ('L', 21, 3)],
    'trim': [('E', 2, 3, 6, 6), ('E', 2, 15, 6, 6),
             ('M', 7, 8), ('L', 21, 21), ('M', 7, 16), ('L', 21, 3)],
    'speed': [('E', 3, 3, 18, 18), ('M', 12, 6), ('L', 12, 12), ('L', 17, 9)],
    'split_media': [('R', 3, 4, 7, 16), ('R', 14, 4, 7, 16)],
    'join_media': [('R', 2, 7, 9, 10), ('R', 13, 7, 9, 10),
                   ('M', 8, 12), ('L', 16, 12)],
    'snapshot': [('M', 3, 7), ('L', 7, 7), ('L', 9, 4), ('L', 15, 4), ('L', 17, 7),
                 ('L', 21, 7), ('L', 21, 20), ('L', 3, 20), ('Z',), ('E', 8, 9, 8, 8)],
    'normalize': [('M', 4, 9), ('L', 4, 15), ('M', 8, 5), ('L', 8, 19),
                  ('M', 12, 2), ('L', 12, 22), ('M', 16, 5), ('L', 16, 19),
                  ('M', 20, 9), ('L', 20, 15)],
    'bleep': [('M', 3, 9), ('L', 7, 9), ('L', 12, 5), ('L', 12, 19), ('L', 7, 15),
              ('L', 3, 15), ('Z',), ('M', 16, 9), ('L', 22, 15),
              ('M', 16, 15), ('L', 22, 9)],
    'channels': [('R', 2, 3, 8, 18), ('R', 14, 3, 8, 18),
                 ('E', 4, 11, 4, 5), ('E', 16, 11, 4, 5)],
    'merge_pdf': [('R', 2, 3, 8, 12), ('R', 14, 3, 8, 12),
                  ('M', 6, 17), ('L', 12, 22), ('L', 18, 17)],
    'split_pdf': [('R', 2, 8, 8, 13), ('R', 14, 8, 8, 13),
                  ('M', 6, 5), ('L', 12, 1), ('L', 18, 5)],
    'reorder_pdf': [('M', 7, 3), ('L', 7, 21), ('M', 3, 7), ('L', 7, 3), ('L', 11, 7),
                    ('M', 17, 3), ('L', 17, 21), ('M', 13, 17), ('L', 17, 21), ('L', 21, 17)],
    'copy': [('R', 3, 3, 12, 14), ('R', 8, 7, 13, 14)],
    'move': [('M', 3, 7), ('L', 3, 20), ('L', 21, 20), ('L', 21, 7), ('L', 11, 7),
             ('L', 9, 4), ('L', 3, 4), ('Z',), ('M', 7, 13), ('L', 17, 13),
             ('M', 14, 10), ('L', 17, 13), ('L', 14, 16)],
    'terminal': [('R', 2, 4, 20, 16), ('M', 6, 9), ('L', 10, 12), ('L', 6, 15),
                 ('M', 13, 16), ('L', 18, 16)],
    'float': [('R', 2, 3, 15, 13), ('R', 8, 9, 14, 12)],
    'share': [('M', 5, 19), ('L', 20, 4), ('M', 10, 4), ('L', 20, 4), ('L', 20, 14)],
}
_ALIASES = {'edit_metadata': 'annotate', 'images_pdf': 'document', 'copy_path': 'join_media'}
ICON_NAMES = frozenset(_SHAPES) | frozenset(_ALIASES)


@lru_cache(maxsize=None)
def icon_path(name):
    return _path(*_SHAPES.get(_ALIASES.get(name, name), _SHAPES['document']))


def draw_icon(painter, name, rect, color='#251e1a'):
    painter.save()
    painter.translate(rect.left(), rect.top())
    painter.scale(rect.width() / 24, rect.height() / 24)
    pen = QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(icon_path(name))
    painter.restore()
