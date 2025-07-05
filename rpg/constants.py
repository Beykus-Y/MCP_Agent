MAX_STAT_POINTS = 50
STARTING_TRAIT_POINTS = 5
DEFAULT_MAX_HP = 100
DEFAULT_STARTING_HP = 100
# --- Настройки визуализации ---
BIOME_COLORS = { # Название: [HEX-цвет, Проходимый?]
    "deep_ocean": ["#00005c", False], "ocean": ["#003088", False],
    "beach": ["#d2b48c", True], "grassland": ["#567d46", True],
    "forest": ["#224d18", True], "jungle": ["#003820", True],
    "mountains": ["#6b6b6b", True], "snowy_peak": ["#f0f0f0", True],
    "desert": ["#c2b280", True], "temperate_desert": ["#94846c", True],
    "scorched": ["#555555", True], "default": ["#333333", False]
}
POI_ICONS = {"capital": "🏰", "town": "🏠", "ruin": "🏛️", "dungeon": "☠️", "natural_wonder": "✨"}
PLAYER_ICON = "🙂" # Иконка для нашего игрока
OTHER_PLAYER_ICON = "👤" # Иконка для других игроков
VIEW_RADIUS = 10 # Радиус обзора миникарты (теперь 21x21 клеток)
CELL_SIZE = 32 # Базовый размер клетки (MinimapWidget масштабирует сам, WorldMapScene использует 16)
OTHER_PLAYER_ICON = "🙂✨"
from PyQt5 import QtCore, QtGui
# --- Настройки карты ---
MAP_WINDOW_KEY = QtCore.Qt.Key_M # Клавиша для открытия большой карты

# --- Настройки тумана войны ---
FOG_REVEAL_SIZE = 6 # Размер квадрата раскрытия тумана войны (например, 6x6 клеток)

# --- Цвет тумана войны ---
FOG_COLOR = QtGui.QColor("#1a1a1a") # Темно-серый или черный для неисследованных областей
# --- Настройки сервера ---
HOST = '127.0.0.1' # Loopback адрес, если играем на одной машине
PORT = 65432       # Порт для связи
BUFFER_SIZE = 4096 # Размер буфера для приема данных
