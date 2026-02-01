from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from XPPython3 import xp

@dataclass
class WindowConfig:
    """Configuració de dimensions de finestra"""
    width: int = 800
    height: int = 600
    min_width: int = 700
    min_height: int = 500

    def get_centered_bounds(self) -> Tuple[int, int, int, int]:
        """Calcula les coordenades per centrar la finestra a la pantalla.

        Returns:
            Tuple (left, top, right, bottom) per a X-Plane
        """
        left, top, right, bottom = xp.getScreenBoundsGlobal()
        screen_width = right - left
        screen_height = top - bottom

        win_left = left + (screen_width - self.width) // 2
        win_top = top - (screen_height - self.height) // 2
        win_right = win_left + self.width
        win_bottom = win_top - self.height

        return win_left, win_top, win_right, win_bottom


MAIN_WINDOW_CONFIG = WindowConfig()

class ButtonSize(Enum):
    HEIGHT = 45
    HEIGHT_LARGE = 70
    WIDTH_SMALL = 110
    WIDTH_MEDIUM = 180
    WIDTH_LARGE = 280

class Padding(Enum):
    SMALL = 8
    MEDIUM = 16
    LARGE = 26

class Spacing(Enum):
    SMALL = 10
    ELEMENTS = 16
    SEPARATOR = 22
    LARGE = 30

class Color(Enum):
    # Primary colors (Login button)
    PRIMARY = (0.2, 0.45, 0.85, 1.0)
    PRIMARY_HOVER = (0.3, 0.55, 0.95, 1.0)
    PRIMARY_ACTIVE = (0.15, 0.35, 0.75, 1.0)

    # Secondary colors (Register button - muted)
    SECONDARY = (0.3, 0.35, 0.4, 1.0)
    SECONDARY_HOVER = (0.4, 0.45, 0.5, 1.0)
    SECONDARY_ACTIVE = (0.25, 0.3, 0.35, 1.0)

    # State colors
    SUCCESS = (0.15, 0.65, 0.35, 1.0)
    SUCCESS_HOVER = (0.25, 0.75, 0.45, 1.0)
    WARNING = (0.9, 0.6, 0.1, 1.0)
    DANGER = (0.8, 0.2, 0.2, 1.0)

    # Status indicator
    STATUS_ONLINE = (0.2, 0.85, 0.4, 1.0)
    STATUS_OFFLINE = (0.5, 0.5, 0.5, 1.0)

    # Text colors
    TEXT_PRIMARY = (1.0, 1.0, 1.0, 1.0)
    TEXT_TITLE = (0.95, 0.97, 1.0, 1.0)
    TEXT_SECONDARY = (0.5, 0.52, 0.55, 0.85)
    TEXT_MUTED = (0.4, 0.42, 0.45, 0.7)

    # Background & Borders
    BACKGROUND = (0.12, 0.12, 0.14, 1.0)
    BACKGROUND_LIGHT = (0.18, 0.18, 0.2, 1.0)
    BORDER = (0.3, 0.3, 0.35, 0.8)
    BORDER_LIGHT = (0.4, 0.4, 0.45, 0.5)

class FontScale(Enum):
    SMALL = 0.9
    NORMAL = 1.0
    MEDIUM = 1.2
    LARGE = 1.5
    XLARGE = 2.0
    TITLE = 2.4
