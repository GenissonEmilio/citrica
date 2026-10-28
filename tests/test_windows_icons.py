"""All radial actions render as bounded vectors, without system symbol fonts."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter

from citrica.tools import TOOLS
from citrica.windows.icons import ICON_NAMES, draw_icon, icon_path


def test_every_action_has_an_explicit_vector_icon():
    assert set(TOOLS) <= ICON_NAMES


def test_icons_render_at_normal_and_high_dpi_without_text():
    for scale in [1, 1.5, 2]:
        for name in ICON_NAMES:
            image = QImage(int(32*scale), int(32*scale), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.scale(scale, scale)
            draw_icon(painter, name, QRectF(4, 4, 24, 24))
            painter.end()
            pixels = [(x, y) for x in range(image.width()) for y in range(image.height())
                      if image.pixelColor(x, y).alpha()]
            assert len(pixels) > 10, name
            assert all(1 <= x < image.width()-1 and 1 <= y < image.height()-1 for x, y in pixels), name
            assert QRectF(0, 0, 24, 24).contains(icon_path(name).boundingRect()), name


def test_unknown_icon_uses_vector_document_fallback():
    assert icon_path('unknown-future-action') == icon_path('document')
