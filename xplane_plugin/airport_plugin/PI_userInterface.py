from typing import Any, Optional, Tuple

import os
from XPPython3 import xp
from XPPython3 import xp_imgui
from XPPython3.xp_typing import XPLMCommandRef
import imgui
from .ui_helpers import center_text

class UserInterface:
    
    def __init__(self):
        self.imgui_windows: dict = {}
        self.cmd: Optional[XPLMCommandRef] = None
        self.cmdRef = None
            
    def XPluginStart(self) -> Tuple[str, str, str]:
        self.cmd = xp.createCommand(
            f'xpppython3/{os.path.basename(__file__)}/createUserInterface',
            'Create a window'
        )
        
        xp.registerCommandHandler(self.cmd, self.commandHandler, 1, self.cmdRef)
        xp.appendMenuItemWithCommand(xp.findPluginsMenu(), 'User Interface', self.cmd)
        
        return 'PI_User_interface_v1.0', 'xppython3.user_interface', 'User Interface for Airport plugin'
    
    def XPluginEnable(self) -> int:
        return 1
    
    def XPluginStop(self) -> None:
        xp.unregisterCommandHandler(self.cmd, self.commandHandler, 1, self.cmdRef)
        xp.clearAllMenuItems(xp.findPluginsMenu())
        
    def XPluginDisable(self) -> None:
        for k in list(self.imgui_windows):
            self.imgui_windows[k]['instance'].delete()
            del self.imgui_windows[k]
            
    def commandHandler(self, _cmdRef: XPLMCommandRef, phase: int, _refCon: Any):
        if phase == xp.CommandBegin:
            self.createWindow(title='HELLO!')
        return 1
    
    def createWindow(self, title):
        
        self.imgui_windows[title] = {
            'instance': None,
            'title': title,
        }
        
        left, top, right, bottom = xp.getScreenBoundsGlobal()
        xp.systemLog(f"SCREEN SIZE {left}, {top}, {right}, {bottom}")
        width = 1200
        height = 600
        left_offset = 310
        top_offset = 10

        # Create the imgui Window, and save it.
        self.imgui_windows[title].update({'instance': xp_imgui.Window(
            left=left + left_offset,
            top=top - top_offset,
            right=left + left_offset + width,
            bottom=top - (top_offset + height),
            visible=1,
            draw=self.drawWelcome,
            refCon=self.imgui_windows[title]
        )})

        self.imgui_windows[title]['instance'].setTitle(title)
   
        
    def drawWelcome(self, _windowID, refCon):
        center_text('hello!')
        center_text('Welcome to AIrport')
        
        window_width = imgui.get_window_size()[0]
        window_height = imgui.get_window_size()[1]
        button_width = 300
        button_height = 125

        # Calcular posición centrada
        pos_x = (window_width - button_width) * 0.5
        pos_y = (window_height - button_height) * 0.5

        # Posicionar y crear botón
        imgui.set_cursor_pos((pos_x, pos_y))
        imgui.button('CONFIGURE SESSION', width=button_width, height=button_height)
