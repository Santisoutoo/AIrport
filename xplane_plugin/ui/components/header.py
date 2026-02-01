import imgui
from datetime import datetime, timezone

from ...utils.constants import Color, FontScale, Padding


class Header:

    def __init__(self, title: str = "AIrport"):
        self.title = title

    def draw(self):
        """Dibuja el header."""
        window_width = imgui.get_window_width()

        # Fondo del header
        draw_list = imgui.get_window_draw_list()
        pos = imgui.get_cursor_screen_pos()
        header_height = 50

        # Color de fondo del header
        draw_list.add_rect_filled(
            pos.x, pos.y,
            pos.x + window_width - 16, pos.y + header_height,
            imgui.get_color_u32_rgba(*Color.BACKGROUND.value)
        )

        # Título a la izquierda
        imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 12)
        imgui.set_cursor_pos_x(Padding.MEDIUM.value)
        imgui.set_window_font_scale(FontScale.LARGE.value)
        imgui.text_colored(self.title, *Color.PRIMARY_HOVER.value)
        imgui.set_window_font_scale(FontScale.NORMAL.value)

        # hora (Local + UTC)
        imgui.same_line()
        utc_time = datetime.now(timezone.utc).strftime("%H:%M:%S") + " Z"
        local_time = datetime.now().strftime("%H:%M:%S") + " LT"
        time_text = f"{local_time}  |  {utc_time}"
        time_width = imgui.calc_text_size(time_text).x
        imgui.set_cursor_pos_x(window_width - time_width - Padding.LARGE.value)
        imgui.text_colored(time_text, *Color.TEXT_SECONDARY.value)

        # Mover cursor después del header
        imgui.set_cursor_pos_y(header_height + Padding.SMALL.value)

        # Línea separadora
        imgui.separator()
        imgui.dummy(0, Padding.SMALL.value)
