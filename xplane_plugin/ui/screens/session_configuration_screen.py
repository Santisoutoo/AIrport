import imgui
from pathlib import Path

from ...utils.constants import Color, ButtonSize, Spacing, FontScale
from ...utils.texture_loader import TextureLoader
from ...services.airport_service import AirportService
from ...services.flight_plan_service import FlightPlanService
from ..components.header import Header
from ..components.footer import Footer


class SessionConfigurationScreen:
    """Pantalla de configuración de sesión."""

    def __init__(self, window_manager):
        self.window_manager = window_manager
        self.is_visible = True

        self.session_types = ["Delivery", "Ground", "Tower"]
        self.weather_options = ["CAVOK", "VMC", "IMC", "Stormy"]
        self.complexity_options = ["Easy", "Medium", "Hard", "Expert"]

        self.selected_session_type = 0
        self.selected_weather = 0
        self.selected_complexity = 1

        self.aircraft_number = "5"

        images_dir = Path(__file__).parent.parent.parent / "images"
        self.image_path = str(images_dir / "LEST_MAP.png")
        self.texture_loaded = False
        self.texture_id = None
        self.img_width = 0
        self.img_height = 0

        self.error_message = ""

        self.flight_plan_service = FlightPlanService()

        self.header = Header("AIrport")
        self.footer = Footer("v1.0.0")

    def draw(self):
        if not self.is_visible:
            return None

        self.header.draw()
        self._draw_content()
        self.footer.draw()

    def _draw_content(self):
        """Contenido de la página."""
        window_width = imgui.get_window_width()

        imgui.dummy(0, Spacing.SMALL.value)

        # Título
        imgui.set_window_font_scale(FontScale.TITLE.value)
        title = "Session Setup"
        text_width = imgui.calc_text_size(title).x
        imgui.set_cursor_pos_x((window_width - text_width) / 2)
        imgui.text_colored(title, *Color.TEXT_TITLE.value)
        imgui.set_window_font_scale(FontScale.NORMAL.value)

        imgui.dummy(0, Spacing.SEPARATOR.value)

        # Formulario izquierda - Imagen derecha
        form_width = 280
        image_area_width = 300
        total_width = form_width + image_area_width + Spacing.LARGE.value
        start_x = (window_width - total_width) / 2

        imgui.set_cursor_pos_x(start_x)
        imgui.begin_group()

        imgui.text_colored("Session Type", *Color.TEXT_MUTED.value)
        imgui.set_next_item_width(form_width)
        changed, self.selected_session_type = imgui.combo(
            "##session_type",
            self.selected_session_type,
            self.session_types
        )

        imgui.dummy(0, Spacing.SMALL.value)

        # Weather
        imgui.text_colored("Weather", *Color.TEXT_MUTED.value)
        imgui.set_next_item_width(form_width)
        changed, self.selected_weather = imgui.combo(
            "##weather",
            self.selected_weather,
            self.weather_options
        )

        imgui.dummy(0, Spacing.SMALL.value)

        # Aircraft Number
        imgui.text_colored("Aircraft Number", *Color.TEXT_MUTED.value)
        imgui.set_next_item_width(form_width)
        changed, self.aircraft_number = imgui.input_text(
            "##aircraft_number", self.aircraft_number, 8
        )

        imgui.dummy(0, Spacing.SMALL.value)

        # Complexity
        imgui.text_colored("Complexity", *Color.TEXT_MUTED.value)
        imgui.set_next_item_width(form_width)
        changed, self.selected_complexity = imgui.combo(
            "##complexity",
            self.selected_complexity,
            self.complexity_options
        )

        imgui.end_group()

        # Columna derecha - Imagen
        imgui.same_line(spacing=Spacing.LARGE.value)
        imgui.begin_group()

        # Área para imagen
        imgui.text_colored("Airport Chart", *Color.TEXT_MUTED.value)
        imgui.dummy(0, Spacing.SMALL.value)

        draw_list = imgui.get_window_draw_list()
        pos = imgui.get_cursor_screen_pos()
        img_display_size = 250

        # Borde del área de imagen
        draw_list.add_rect(
            pos.x, pos.y,
            pos.x + img_display_size, pos.y + img_display_size,
            imgui.get_color_u32_rgba(*Color.BORDER.value),
            rounding=4.0
        )

        # Cargar y mostrar imagen si existe
        if self.image_path and not self.texture_loaded:
            try:
                self.texture_id, self.img_width, self.img_height = TextureLoader.load(
                    self.image_path)
                self.texture_loaded = True
            except Exception:
                self.texture_loaded = False

        if self.texture_id:
            imgui.image(self.texture_id, img_display_size, img_display_size)
        else:
            # Placeholder si no hay imagen
            draw_list.add_rect_filled(
                pos.x + 1, pos.y + 1,
                pos.x + img_display_size - 1, pos.y + img_display_size - 1,
                imgui.get_color_u32_rgba(*Color.BACKGROUND_LIGHT.value),
                rounding=4.0
            )
            imgui.dummy(img_display_size, img_display_size)

            # Texto centrado en el placeholder
            placeholder_text = "No chart loaded"
            imgui.set_window_font_scale(FontScale.SMALL.value)
            ph_width = imgui.calc_text_size(placeholder_text).x
            imgui.set_cursor_screen_pos((
                pos.x + (img_display_size - ph_width) / 2,
                pos.y + img_display_size / 2 - 10
            ))
            imgui.text_colored(placeholder_text, *Color.TEXT_MUTED.value)
            imgui.set_window_font_scale(FontScale.NORMAL.value)

        imgui.end_group()

        imgui.dummy(0, Spacing.SEPARATOR.value)

        # Mensaje de error
        if self.error_message:
            error_width = imgui.calc_text_size(self.error_message).x
            imgui.set_cursor_pos_x((window_width - error_width) / 2)
            imgui.text_colored(self.error_message, *Color.DANGER.value)
            imgui.dummy(0, Spacing.SMALL.value)

        # Botón Start Session
        button_width = ButtonSize.WIDTH_LARGE.value
        imgui.set_cursor_pos_x((window_width - button_width) / 2)

        imgui.push_style_color(imgui.COLOR_BUTTON, *Color.SUCCESS.value)
        imgui.push_style_color(imgui.COLOR_BUTTON_HOVERED,
                               *Color.SUCCESS_HOVER.value)
        imgui.push_style_color(imgui.COLOR_BUTTON_ACTIVE, *Color.SUCCESS.value)

        if imgui.button("Start Session", button_width, ButtonSize.HEIGHT.value + 5):
            self._on_start_session()

        imgui.pop_style_color(3)

        imgui.dummy(0, Spacing.SMALL.value)

        # Link para volver
        back_text = "Back to home"
        text_width = imgui.calc_text_size(back_text).x
        imgui.set_cursor_pos_x((window_width - text_width) / 2)

        imgui.push_style_color(imgui.COLOR_TEXT, *Color.TEXT_MUTED.value)
        if imgui.selectable(back_text, False, width=text_width)[0]:
            self._on_back_to_welcome()
        imgui.pop_style_color(1)

        imgui.dummy(0, Spacing.LARGE.value)

    def set_chart_image(self, image_path: str):
        """Establece la imagen del chart/herramienta."""
        self.image_path = image_path
        self.texture_loaded = False
        self.texture_id = None

    def _on_start_session(self):
        """Inicia la sesión con la configuración actual."""
        # Validaciones
        try:
            aircraft_count = int(self.aircraft_number)
            if aircraft_count < 1 or aircraft_count > 50:
                self.error_message = "Aircraft number must be between 1 and 50"
                return
        except ValueError:
            self.error_message = "Invalid aircraft number"
            return

        self.error_message = ""

        # Load airport data into Redis
        icao = AirportService.get_icao()
        if not icao:
            self.error_message = "Could not detect current airport"
            return
        if not AirportService.load_airport_data(icao):
            self.error_message = f"Failed to load airport data for {icao}"
            return

        # Check service connection
        if not self.flight_plan_service.health_check():
            self.error_message = "Flight plan service unavailable"
            return None

        # Clear existing flight plans
        success, message = self.flight_plan_service.clear_all()
        if not success:
            self.error_message = f"Failed to clear flight plans: {message}"
            return None

        # Generate new flight plans
        success, result = self.flight_plan_service.generate_multiple(aircraft_count)
        if not success:
            self.error_message = f"Failed to generate flight plans: {result}"
            return None

        config = self.get_configuration()
        print(f"Starting session with config: {config}")
        print(f"Generated {len(result)} flight plans")

    def _on_back_to_welcome(self):
        """Vuelve a la pantalla principal."""
        self.reset()
        self.window_manager.switchScreen('welcome')

    def get_configuration(self) -> dict:
        """Retorna la configuración actual."""
        return {
            'session_type': self.session_types[self.selected_session_type],
            'weather': self.weather_options[self.selected_weather],
            'aircraft_number': int(self.aircraft_number),
            'complexity': self.complexity_options[self.selected_complexity]
        }

    def show(self):
        self.is_visible = True

    def hide(self):
        self.is_visible = False

    def reset(self):
        """Resetea la configuración."""
        self.selected_session_type = 0
        self.selected_weather = 0
        self.selected_complexity = 1
        self.aircraft_number = "5"
        self.error_message = ""
        self.texture_loaded = False
        self.texture_id = None
