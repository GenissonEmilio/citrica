"""Reusable wheel appearance picker for Linux and Windows settings."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from citrica.wheel_themes import DEFAULT_THEME, THEMES, get_theme, normalize_theme


def wheel_preview(theme_id):
    """Render the actual Qt wheel; do not approximate it with a decorative icon."""
    from citrica.windows.wheel import Wheel
    wheel = Wheel(animations=lambda: False)
    wheel.set_theme(theme_id)
    wheel.set_palette([], [{'kind': 'format', 'id': item.lower(), 'label': item}
                           for item in ('PNG', 'JPG', 'WEBP', 'PDF', 'AVIF')],
                      {'bytes': 148480, 'label': 'Imagem de exemplo'})
    wheel.select(1)
    snapshot = wheel.grab()
    wheel.deleteLater()
    return snapshot


class WheelAppearancePicker(QWidget):
    """Five exclusive styles, with an immediate preview and explicit identity.

    ``set_theme`` loads settings without emitting ``themeChanged``. User clicks
    emit the selected stable ID. The owner decides when to persist/apply it.
    """
    themeChanged = Signal(str)

    def __init__(self, theme=DEFAULT_THEME, parent=None):
        super().__init__(parent)
        self.setObjectName('WheelAppearancePicker')
        self._theme_id = normalize_theme(theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        title = QLabel('A roda, do seu jeito')
        title.setStyleSheet('font-size:19px;font-weight:700;')
        layout.addWidget(title)
        intro = QLabel('Escolha um estilo. A miniatura, os atalhos e os setores continuam no mesmo lugar.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        grid = QGridLayout()
        grid.setSpacing(9)
        self.buttons = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, item in enumerate(THEMES):
            button = QToolButton()
            button.setObjectName(f'wheel-theme-{item.id}')
            button.setText(item.name)
            button.setToolTip(item.description)
            button.setAccessibleName(f'Estilo {item.name}')
            button.setAccessibleDescription(item.description)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setIcon(QIcon(wheel_preview(item.id)))
            button.setIconSize(QSize(136, 149))
            button.setMinimumSize(158, 182)
            button.clicked.connect(lambda _checked=False, selected=item.id: self._chosen(selected))
            self.group.addButton(button)
            self.buttons[item.id] = button
            grid.addWidget(button, index // 3, index % 3)
        layout.addLayout(grid)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setMinimumHeight(38)
        layout.addWidget(self.description)
        note = QLabel('Aquarela e Vidro claro deixam o desktop aparecer. Os rótulos têm fundo próprio '
                      'para manter a leitura.')
        note.setWordWrap(True)
        note.setStyleSheet('font-size:11px;color:#6c7783;')
        layout.addWidget(note)
        layout.addStretch()
        self.setStyleSheet('''
            #WheelAppearancePicker QToolButton {
                background:#e6ebf0;color:#202b35;border:2px solid transparent;
                border-radius:12px;padding:4px;font-size:12px;font-weight:600;
            }
            #WheelAppearancePicker QToolButton:hover {border-color:#a8b7c5;}
            #WheelAppearancePicker QToolButton:checked {border-color:#ed713d;background:#fff0e7;}
            #WheelAppearancePicker QToolButton:focus {border-color:#126eab;}
        ''')
        self.set_theme(theme)

    def theme_id(self):
        return self._theme_id

    def set_theme(self, theme_id):
        self._theme_id = normalize_theme(theme_id)
        self.buttons[self._theme_id].setChecked(True)
        self.description.setText(get_theme(self._theme_id).description)

    def _chosen(self, theme_id):
        if theme_id == self._theme_id:
            return
        self.set_theme(theme_id)
        self.themeChanged.emit(theme_id)
