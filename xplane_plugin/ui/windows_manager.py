from typing import Dict, Optional, Any
from XPPython3 import xp, xp_imgui
from XPPython3.xp_typing import XPLMCommandRef

from .screens.welcome_screen import WelcomeScreen
from .screens.register import RegisterScreen
from .screens.login_screen import LoginScreen
from .screens.session_configuration_screen import SessionConfigurationScreen
from ..utils.constants import MAIN_WINDOW_CONFIG
from ..services.airport_service import AirportService


class WindowManager:
    """Gestiona ventanas ImGui y navegación entre pantallas"""

    def __init__(self):
        self.windows: Dict[str, Dict] = {}
        self.current_screen: str = 'welcome'
        self.cmd: Optional[XPLMCommandRef] = None
        self.cmdRef = None

        self.screens = {
            'welcome': WelcomeScreen(self),
            'register': RegisterScreen(self),
            'login': LoginScreen(self),
            'sessionConfiguration': SessionConfigurationScreen(self)
        }

    def register_plugin(self) -> tuple[str, str, str]:
        """Registra solo comandos y menú en X-Plane"""
        self.cmd = xp.createCommand(
            'xppython3/airport/openUI', # Nombre comando
            'Open AIrport Interface'    # Descripción
        )
        xp.registerCommandHandler(self.cmd, self._commandHandler, 1, self.cmdRef)
        xp.appendMenuItemWithCommand(xp.findPluginsMenu(), 'AIrport', self.cmd)

        return 'PI_AIrport_v1.0', 'com.airport.atc', 'AIrport ATC Simulator'

    def createWindow(self, title: str = 'AIrport'):
        """Crea ventana ImGui"""
        if title in self.windows:
            return None

        left, top, right, bottom = MAIN_WINDOW_CONFIG.get_centered_bounds()
        self.windows[title] = {
            'instance': xp_imgui.Window(
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                visible=1,
                draw=self._draw,
                refCon={'title': title}
            ),
            'title': title
        }
        self.windows[title]['instance'].setTitle(title)

    def _draw(self, windowID: int, refCon: Any):
        """Callback de dibujo"""
        screen = self.screens.get(self.current_screen)
        if screen:
            screen.draw()

    def switchScreen(self, screen_name: str):
        """Cambia entre pantallas"""
        if screen_name in self.screens:
            self.current_screen = screen_name
            xp.systemLog(f'AIrport: Switched to {screen_name}')

    def _commandHandler(self, cmdRef: XPLMCommandRef, phase: int, refCon: Any) -> int:
        """Maneja comando de menú"""
        if phase == xp.CommandBegin:
            self.createWindow('AIrport')
        return 1

    def close_all_windows(self):
        """Cierra todas las ventanas"""
        for window_data in list(self.windows.values()):
            window_data['instance'].delete()
        self.windows.clear()

    def cleanup(self):
        """Limpieza al detener"""
        if self.cmd:
            xp.unregisterCommandHandler(self.cmd, self._commandHandler, 1, self.cmdRef)
        xp.clearAllMenuItems(xp.findPluginsMenu())
        self.close_all_windows()
        AirportService.reset()
