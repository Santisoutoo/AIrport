import imgui

from ...utils.constants import Color, ButtonSize, Spacing, FontScale
from ..components.header import Header
from ..components.footer import Footer


class LoginScreen:
    """Pantalla de login de usuario."""

    def __init__(self, window_manager):
        self.window_manager = window_manager
        self.is_visible = True

        # formulario
        self.username = ""
        self.password = ""

        self.error_message = ""
        self.is_loading = False

        self.header = Header("AIrport")
        self.footer = Footer("v1.0.0")

    def draw(self):
        if not self.is_visible:
            return None

        self.header.draw()
        self._draw_content()
        self.footer.draw()

    def _draw_content(self):
        """COntenido página"""
        window_width = imgui.get_window_width()

        imgui.dummy(0, Spacing.LARGE.value)

        # Título
        imgui.set_window_font_scale(FontScale.TITLE.value)
        title = "Welcome Back"
        text_width = imgui.calc_text_size(title).x
        imgui.set_cursor_pos_x((window_width - text_width) / 2)
        imgui.text_colored(title, *Color.TEXT_TITLE.value)
        imgui.set_window_font_scale(FontScale.NORMAL.value)

        imgui.dummy(0, Spacing.LARGE.value)

        # Subtítulo
        imgui.set_window_font_scale(FontScale.SMALL.value)
        subtitle = "Sign in to continue"
        text_width = imgui.calc_text_size(subtitle).x
        imgui.set_cursor_pos_x((window_width - text_width) / 2)
        imgui.text_colored(subtitle, *Color.TEXT_MUTED.value)
        imgui.set_window_font_scale(FontScale.NORMAL.value)

        imgui.dummy(0, Spacing.SEPARATOR.value)

        # Formulario
        form_width = ButtonSize.WIDTH_LARGE.value
        imgui.set_cursor_pos_x((window_width - form_width) / 2)

        imgui.begin_group()

        # Input username
        imgui.text_colored("Username", *Color.TEXT_MUTED.value)
        imgui.set_next_item_width(form_width)
        _, self.username = imgui.input_text("##username", self.username, 64)

        imgui.dummy(0, Spacing.SMALL.value)

        # Campo Password
        imgui.text_colored("Password", *Color.TEXT_MUTED.value)
        imgui.set_next_item_width(form_width)
        _, self.password = imgui.input_text(
            "##password", self.password, 64, imgui.INPUT_TEXT_PASSWORD
        )

        imgui.dummy(0, Spacing.ELEMENTS.value)

        # Mensaje de error
        if self.error_message:
            imgui.text_colored(self.error_message, *Color.DANGER.value)
            imgui.dummy(0, Spacing.SMALL.value)

        # Botón Login
        imgui.push_style_color(imgui.COLOR_BUTTON, *Color.PRIMARY.value)
        imgui.push_style_color(imgui.COLOR_BUTTON_HOVERED, *Color.PRIMARY_HOVER.value)
        imgui.push_style_color(imgui.COLOR_BUTTON_ACTIVE, *Color.PRIMARY_ACTIVE.value)

        button_label = "Signing in..." if self.is_loading else "Sign In"
        if imgui.button(button_label, form_width, ButtonSize.HEIGHT.value + 5):
            if not self.is_loading:
                self._on_login_clicked()

        imgui.pop_style_color(3)

        imgui.dummy(0, Spacing.ELEMENTS.value)

        # Link para ir a registro
        register_text = "Don't have an account? Register"
        text_width = imgui.calc_text_size(register_text).x
        imgui.set_cursor_pos_x((window_width - text_width) / 2)

        imgui.push_style_color(imgui.COLOR_TEXT, *Color.PRIMARY_HOVER.value)
        if imgui.selectable(register_text, False, width=text_width)[0]:
            self._on_go_to_register()
        imgui.pop_style_color(1)

        imgui.dummy(0, Spacing.SMALL.value)

        # volver página principal
        back_text = "Back to home"
        text_width = imgui.calc_text_size(back_text).x
        imgui.set_cursor_pos_x((window_width - text_width) / 2)

        imgui.push_style_color(imgui.COLOR_TEXT, *Color.TEXT_MUTED.value)
        if imgui.selectable(back_text, False, width=text_width)[0]:
            self._on_back_to_welcome()
        imgui.pop_style_color(1)

        imgui.end_group()

    def _on_login_clicked(self):
        """Maneja el evento botón de login."""
        if not self.username or not self.password:
            self.error_message = "All fields are required"
            return None

        self.error_message = ""
        self.is_loading = True
        # TODO: Implementar lógica de login real
        # Por ahora navegar a session configuration
        self.is_loading = False
        self.window_manager.switchScreen('sessionConfiguration')

    def _on_go_to_register(self):
        """Navega a la pantalla de registro."""
        self.reset()
        self.window_manager.switchScreen('register')

    def _on_back_to_welcome(self):
        """Navega de vuelta a la pantalla de bienvenida."""
        self.reset()
        self.window_manager.switchScreen('welcome')

    def show(self):
        """Muestra la pantalla."""
        self.is_visible = True

    def hide(self):
        """Oculta la pantalla."""
        self.is_visible = False

    def reset(self):
        """Resetea el formulario."""
        self.username = ""
        self.password = ""
        self.error_message = ""
        self.is_loading = False
