"""Shared, dependency-free appearance contract for the Qt and GNOME wheels.

Colours use straight RGBA components in the range 0..1. Keep the generated
GNOME catalogue in sync; tests compare the entire catalogue, not just its IDs.
Appearance never changes the wheel's hit regions or its file actions.
"""
from dataclasses import asdict, dataclass

DEFAULT_THEME = 'classic'


@dataclass(frozen=True)
class WheelTheme:
    id: str
    name: str
    description: str
    start: tuple
    end: tuple
    selected_start: tuple
    selected_end: tuple
    text: tuple
    active_text: tuple
    pill: tuple
    pill_text: tuple
    icon: tuple
    halo: tuple
    border: tuple
    border_width: float = 1.
    label_chip: tuple | None = None
    gloss: float = 0.


THEMES = (
    WheelTheme('classic', 'Cítrica', 'Pêssego e laranja, com o visual original da roda.',
               (1, .94, .80, .94), (1, .85, .80, .94),
               (1, .65, .30, 1), (.98, .30, .10, 1),
               (.145, .118, .102, 1), (.145, .118, .102, 1),
               (1, .965, .906, .96), (.161, .122, .102, 1), (.286, .216, .165, 1),
               (1, .89, .76, .24), (1, 1, 1, .16)),
    WheelTheme('watercolor', 'Aquarela', 'Lavanda e água-marinha translúcidas, com brilho suave.',
               (.69, .90, .96, .57), (.83, .76, .96, .67),
               (.30, .91, .84, .94), (.45, .64, .97, .96),
               (.067, .145, .196, 1), (.047, .114, .149, 1),
               (.94, .99, 1, .97), (.067, .145, .196, 1), (.10, .25, .33, 1),
               (.72, .90, .99, .12), (.89, 1, 1, .72), 1.2, (.95, .99, 1, .94), .19),
    WheelTheme('glass', 'Vidro claro', 'Setores cristalinos, contornos claros e rótulos protegidos.',
               (.96, .98, 1, .31), (.78, .88, .98, .43),
               (.82, .94, 1, .94), (.47, .76, 1, .97),
               (.086, .145, .22, 1), (.055, .118, .188, 1),
               (.97, .99, 1, .97), (.086, .145, .22, 1), (.16, .25, .35, 1),
               (.88, .96, 1, .08), (1, 1, 1, .90), 1.4, (.97, .99, 1, .95), .28),
    WheelTheme('graphite', 'Grafite', 'Superfície escura, acabamento fosco e seleção em menta.',
               (.15, .18, .21, .98), (.075, .094, .118, .98),
               (.47, .92, .76, 1), (.20, .71, .61, 1),
               (.94, .97, .98, 1), (.035, .122, .106, 1),
               (.10, .13, .16, .99), (.94, .97, .98, 1), (.83, .91, .94, 1),
               (.045, .067, .09, .28), (.50, .60, .65, .46), 1.1),
    WheelTheme('contrast', 'Alto contraste', 'Preto e branco opacos, bordas fortes e seleção amarela.',
               (.015, .015, .015, 1), (.015, .015, .015, 1),
               (1, .87, .16, 1), (1, .87, .16, 1),
               (1, 1, 1, 1), (.015, .015, .015, 1),
               (.015, .015, .015, 1), (1, 1, 1, 1), (1, 1, 1, 1),
               (0, 0, 0, .20), (1, 1, 1, 1), 2.2),
)
THEME_IDS = frozenset(theme.id for theme in THEMES)


def normalize_theme(value):
    """Fall back for old preferences and unknown future theme IDs."""
    return value if isinstance(value, str) and value in THEME_IDS else DEFAULT_THEME


def get_theme(value=DEFAULT_THEME):
    selected = normalize_theme(value)
    return next(theme for theme in THEMES if theme.id == selected)


def theme_catalogue():
    """Return JSON-compatible data for the matching GNOME catalogue."""
    import json
    return json.loads(json.dumps([asdict(theme) for theme in THEMES]))
