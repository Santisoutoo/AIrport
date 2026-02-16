import imgui
from pathlib import Path

from ...utils.texture_loader import TextureLoader
from ..components.header import Header
from ..components.footer import Footer
from ...utils.constants import Color, ButtonSize, Spacing, FontScale
from ...services.airport_service import AirportService


class WelcomeScreen:
    """Pantalla de bienvenida del plugin."""

    def __init__(self, window_manager):
        self.window_manager = window_manager
        self.is_visible = True
        self.current_icao = ""
        self.current_airport_name = ""

        #cargar img
        self.image_path = str(Path(__file__).parent.parent.parent / "images" / "LEST.png")
        self.texture_loaded = False
        self.texture_id = None
        self.img_width = 0
        self.img_height = 0

        # Componentes
        self.header = Header("AIrport")
        self.footer = Footer("v1.0.0")

    def draw(self):
        """Método principal que dibuja toda la pantalla."""
        if not self.is_visible:
            return

        self.header.draw()
        self._draw_content()
        self.footer.draw()

    def _update_airport(self):
        """Actualiza el aeropuerto actual desde X-Plane."""
        airport = AirportService.get_current_airport()
        if airport:
            self.current_icao = airport.icao
            self.current_airport_name = airport.name

    def _draw_content(self):
        """Dibuja el contenido principal de la pantalla."""
        self._update_airport()
        window_width = imgui.get_window_width()
        draw_list = imgui.get_window_draw_list()

        if not self.texture_loaded:
            self.texture_id, self.img_width, self.img_height = TextureLoader.load(self.image_path)
            self.texture_loaded = True

        imgui.dummy(0, Spacing.LARGE.value)
        imgui.set_window_font_scale(FontScale.TITLE.value)
        title = "Welcome to AIrport"
        text_width = imgui.calc_text_size(title).x
        imgui.set_cursor_pos_x((window_width - text_width) / 2)
        imgui.text_colored(title, *Color.TEXT_TITLE.value)
        imgui.set_window_font_scale(FontScale.NORMAL.value)

        imgui.dummy(0, Spacing.LARGE.value)

        imgui.set_window_font_scale(FontScale.SMALL.value)
        location_text = f"You are currently in: {self.current_icao} - {self.current_airport_name}"
        text_width = imgui.calc_text_size(location_text).x
        imgui.set_cursor_pos_x((window_width - text_width) / 2)
        imgui.text_colored(location_text, *Color.TEXT_MUTED.value)
        imgui.set_window_font_scale(FontScale.NORMAL.value)

        imgui.same_line(spacing=10)
        status_pos = imgui.get_cursor_screen_pos()
        draw_list.add_circle_filled(
            status_pos.x + 5, status_pos.y + 6, 4,
            imgui.get_color_u32_rgba(*Color.STATUS_ONLINE.value)
        )

        imgui.dummy(0, Spacing.SEPARATOR.value)

        if self.texture_id:
            img_size = 140
            img_x = (window_width - img_size) / 2
            imgui.set_cursor_pos_x(img_x)

            # Obtener posición para dibujar borde
            pos = imgui.get_cursor_screen_pos()

            # Borde alrededor de la imagen
            draw_list.add_rect(
                pos.x - 2, pos.y - 2,
                pos.x + img_size + 2, pos.y + img_size + 2,
                imgui.get_color_u32_rgba(*Color.BORDER.value),
                rounding=4.0
            )

            imgui.image(self.texture_id, img_size, img_size)

            imgui.dummy(0, 8)
            badge_text = f"[ {self.current_icao} ]"
            imgui.set_window_font_scale(FontScale.MEDIUM.value)
            badge_width = imgui.calc_text_size(badge_text).x
            imgui.set_cursor_pos_x((window_width - badge_width) / 2)
            imgui.text_colored(badge_text, *Color.PRIMARY_HOVER.value)
            imgui.set_window_font_scale(FontScale.NORMAL.value)

        imgui.dummy(0, Spacing.LARGE.value)

        # Botones Login y Register
        button_width = ButtonSize.WIDTH_MEDIUM.value
        button_height = ButtonSize.HEIGHT.value + 5
        total_width = button_width * 2 + Spacing.SEPARATOR.value

        imgui.set_cursor_pos_x((window_width - total_width) / 2)

        imgui.push_style_color(imgui.COLOR_BUTTON, *Color.PRIMARY.value)
        imgui.push_style_color(imgui.COLOR_BUTTON_HOVERED, *Color.PRIMARY_HOVER.value)
        imgui.push_style_color(imgui.COLOR_BUTTON_ACTIVE, *Color.PRIMARY_ACTIVE.value)
        if imgui.button("Login", button_width, button_height):
            self._on_login_clicked()
        imgui.pop_style_color(3)

        imgui.same_line(spacing=Spacing.SEPARATOR.value)

        imgui.push_style_color(imgui.COLOR_BUTTON, *Color.SECONDARY.value)
        imgui.push_style_color(imgui.COLOR_BUTTON_HOVERED, *Color.SECONDARY_HOVER.value)
        imgui.push_style_color(imgui.COLOR_BUTTON_ACTIVE, *Color.SECONDARY_ACTIVE.value)
        if imgui.button("Register", button_width, button_height):
            self._on_register_clicked()
        imgui.pop_style_color(3)

    def _on_login_clicked(self):
        """Navega a la pantalla de login."""
        self.window_manager.switchScreen('login')

    def _on_register_clicked(self):
        """Navega a la pantalla de registro."""
        self.window_manager.switchScreen('register')

    def show(self):
        """Muestra la pantalla."""
        self.is_visible = True

    def hide(self):
        """Oculta la pantalla."""
        self.is_visible = False