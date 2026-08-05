from typing import Tuple
from XPPython3 import xp

from ..ui.windows_manager import WindowManager

_window_manager = WindowManager()


class PythonInterface:
    def XPluginStart(self) -> Tuple[str, str, str]:
        return _window_manager.register_plugin()

    def XPluginEnable(self) -> int:
        return 1

    def XPluginDisable(self) -> None:
        pass

    def XPluginStop(self) -> None:
        _window_manager.cleanup()
