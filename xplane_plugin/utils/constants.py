# Screen dimensions (standard 1920x1080)
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# Main window dimensions
MAIN_WINDOW_WIDTH = 900
MAIN_WINDOW_HEIGHT = 700
MAIN_WINDOW_MIN_WIDTH = 800
MAIN_WINDOW_MIN_HEIGHT = 600

# Window offsets from screen edges
WINDOW_TOP_OFFSET = 100
WINDOW_LEFT_OFFSET = (SCREEN_WIDTH - MAIN_WINDOW_WIDTH) // 2  # Center horizontally

# Session setup window
SETUP_WINDOW_WIDTH = 1000
SETUP_WINDOW_HEIGHT = 750

# Controller tools window (training mode)
TOOLS_WINDOW_WIDTH = 1400
TOOLS_WINDOW_HEIGHT = 900
TOOLS_PANEL_WIDTH = 350  # Side panels width

# UI Elements
BUTTON_HEIGHT = 50
BUTTON_HEIGHT_LARGE = 80
BUTTON_WIDTH_SMALL = 120
BUTTON_WIDTH_MEDIUM = 200
BUTTON_WIDTH_LARGE = 300

# Padding and spacing
PADDING_SMALL = 10
PADDING_MEDIUM = 20
PADDING_LARGE = 30
SPACING_ELEMENTS = 15
SEPARATOR_SPACING = 20

# Colors (RGBA normalized 0-1)
COLOR_PRIMARY = (0.2, 0.4, 0.8, 1.0)  # Blue
COLOR_PRIMARY_HOVER = (0.3, 0.5, 0.9, 1.0)
COLOR_PRIMARY_ACTIVE = (0.1, 0.3, 0.7, 1.0)

COLOR_SUCCESS = (0.1, 0.6, 0.3, 1.0)  # Green
COLOR_SUCCESS_HOVER = (0.2, 0.7, 0.4, 1.0)

COLOR_WARNING = (0.9, 0.6, 0.1, 1.0)  # Orange
COLOR_DANGER = (0.8, 0.2, 0.2, 1.0)   # Red

COLOR_TEXT_PRIMARY = (1.0, 1.0, 1.0, 1.0)
COLOR_TEXT_SECONDARY = (0.7, 0.7, 0.7, 1.0)
COLOR_BACKGROUND = (0.15, 0.15, 0.15, 1.0)

# Font scales
FONT_SCALE_SMALL = 0.9
FONT_SCALE_NORMAL = 1.0
FONT_SCALE_MEDIUM = 1.2
FONT_SCALE_LARGE = 1.5
FONT_SCALE_XLARGE = 2.0
FONT_SCALE_TITLE = 2.5

# Session configuration defaults
DEFAULT_AIRCRAFT_COUNT = 5
MIN_AIRCRAFT = 1
MAX_AIRCRAFT = 20

# Complexity levels
COMPLEXITY_LEVELS = ['Beginner', 'Intermediate', 'Advanced', 'Expert']

# Weather options
WEATHER_OPTIONS = ['Clear', 'Few Clouds', 'Scattered', 'Broken', 'Overcast', 'Rain', 'Thunderstorm']

# Time options
TIME_OPTIONS = ['Dawn', 'Morning', 'Noon', 'Afternoon', 'Dusk', 'Night']

# Airport ICAO codes (common training airports)
TRAINING_AIRPORTS = {
    'LEBL': 'Aeropuerto Josep Tarradellas Barcelona-El Prat'
}

# Plugin info
PLUGIN_NAME = "AIrport ATC Trainer"
PLUGIN_SIG = "com.airport.atc"
PLUGIN_DESC = "AI-Powered ATC Training Simulator"
PLUGIN_VERSION = "1.0.0"