import imgui

from ...utils.constants import Color, Padding


class Footer:

    def __init__(self, version: str = "v1.0.0"):
        self.version = version

    def draw(self):
        """Dibuja el footer en la parte inferior de la ventana."""
        window_width = imgui.get_window_width()
        window_height = imgui.get_window_height()

        footer_height = 40
        footer_y = window_height - footer_height - Padding.SMALL.value

        # Posicionar el footer abajo
        imgui.set_cursor_pos_y(footer_y)

        # Línea separadora
        imgui.separator()
        imgui.dummy(0, 5)

        # Fondo del footer
        draw_list = imgui.get_window_draw_list()
        pos = imgui.get_cursor_screen_pos()

        draw_list.add_rect_filled(
            pos.x, pos.y,
            pos.x + window_width - 16, pos.y + 25,
            imgui.get_color_u32_rgba(*Color.BACKGROUND.value)
        )

        # Versión a la izquierda
        imgui.set_cursor_pos_x(Padding.MEDIUM.value)
        imgui.text_colored(self.version, *Color.TEXT_SECONDARY.value)

        # Créditos a la derecha
        imgui.same_line()
        credits = "AIrport ATC Simulator"
        credits_width = imgui.calc_text_size(credits).x
        imgui.set_cursor_pos_x(window_width - credits_width - Padding.LARGE.value)
        imgui.text_colored(credits, *Color.TEXT_SECONDARY.value)
