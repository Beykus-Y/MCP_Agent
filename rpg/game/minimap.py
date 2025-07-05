# rpg/game/minimap.py
from PyQt5 import QtWidgets, QtCore, QtGui
from typing import Dict

# Относительные импорты, так как мы теперь в подпапке 'game'
from ..models import Character
from ..world.world_state import WorldState
from ..constants import BIOME_COLORS, POI_ICONS, PLAYER_ICON, OTHER_PLAYER_ICON, VIEW_RADIUS, CELL_SIZE, FOG_COLOR

class MinimapWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.character = None # Наш персонаж
        self.world = None
        self.all_players: Dict[str, Character] = {} # Все игроки на сервере

        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.color_cache = {name: QtGui.QColor(data[0]) for name, data in BIOME_COLORS.items()}
    
    def update_data(self, character: Character, world: WorldState, all_players: Dict[str, Character]):
        self.character = character
        self.world = world
        self.all_players = all_players
        self.update() # Запускает перерисовку
    
    def paintEvent(self, event: QtGui.QPaintEvent):
        if not self.character or not self.world: return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        grid_size = VIEW_RADIUS * 2 + 1
        cell_w = self.width() / grid_size
        cell_h = self.height() / grid_size
        cell_size = int(min(cell_w, cell_h))
        
        if cell_size == 0: return

        px, py = self.character.position
        
        poi_font = painter.font()
        poi_font.setPixelSize(int(cell_size * 0.6))
        player_font = painter.font()
        player_font.setPixelSize(int(cell_size * 0.8))
        other_player_font = painter.font()
        other_player_font.setPixelSize(int(cell_size * 0.7))

        for y_offset in range(-VIEW_RADIUS, VIEW_RADIUS + 1):
            for x_offset in range(-VIEW_RADIUS, VIEW_RADIUS + 1):
                map_x, map_y = px + x_offset, py + y_offset
                rect_x, rect_y = (x_offset + VIEW_RADIUS) * cell_size, (y_offset + VIEW_RADIUS) * cell_size
                cell_rect = QtCore.QRect(rect_x, rect_y, cell_size, cell_size)

                if (map_x, map_y) not in self.character.discovered_cells:
                    painter.fillRect(cell_rect, FOG_COLOR)
                    painter.setPen(QtGui.QColor("#555555"))
                    font = painter.font(); font.setPixelSize(int(cell_size * 0.7)); painter.setFont(font)
                    painter.drawText(cell_rect, QtCore.Qt.AlignCenter, "?")
                    continue

                if not (0 <= map_x < self.world.map_size[0] and 0 <= map_y < self.world.map_size[1]):
                    painter.fillRect(cell_rect, self.color_cache['default'])
                    painter.setPen(QtGui.QColor("#aaaaaa"))
                    painter.drawText(cell_rect, QtCore.Qt.AlignCenter, "~")
                    continue
                
                biome = self.world.biome_map[map_y][map_x]
                color = self.color_cache.get(biome, self.color_cache['default'])
                painter.fillRect(cell_rect, color)
                
                poi = self._get_poi_at_from_world(map_x, map_y)
                if poi:
                    painter.setPen(QtGui.QColor("#ffffff"))
                    painter.setFont(poi_font)
                    painter.drawText(cell_rect, QtCore.Qt.AlignCenter, POI_ICONS.get(poi.type, "?"))
                
                for other_player_id, other_char in self.all_players.items():
                    if other_char and other_char.position == (map_x, map_y) and other_char.name != self.character.name:
                        painter.setPen(QtGui.QColor("#00ff00"))
                        painter.setFont(other_player_font)
                        painter.drawText(cell_rect, QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft, OTHER_PLAYER_ICON)
                
                if x_offset == 0 and y_offset == 0:
                    painter.setPen(QtGui.QColor("#ff0000"))
                    painter.setFont(player_font)
                    painter.drawText(cell_rect, QtCore.Qt.AlignCenter, PLAYER_ICON)

    def _get_poi_at_from_world(self, x, y):
        if not self.world: return None
        return next((p for p in self.world.points_of_interest if tuple(p.position) == (x, y)), None)
    
    def sizeHint(self) -> QtCore.QSize: 
        return QtCore.QSize((VIEW_RADIUS * 2 + 1) * CELL_SIZE, (VIEW_RADIUS * 2 + 1) * CELL_SIZE)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if not self.character or not self.world: return
        grid_size = VIEW_RADIUS * 2 + 1; cell_w = self.width() / grid_size; cell_h = self.height() / grid_size; cell_size = int(min(cell_w, cell_h));
        if cell_size == 0: return
        label_x, label_y = event.x() // cell_size, event.y() // cell_size; x_offset, y_offset = label_x - VIEW_RADIUS, label_y - VIEW_RADIUS
        map_x, map_y = self.character.position[0] + x_offset, self.character.position[1] + y_offset
        
        tooltip_text = ""
        if (map_x, map_y) not in self.character.discovered_cells:
            tooltip_text = "Неизведанная область"
        elif not (0 <= map_x < self.world.map_size[0] and 0 <= map_y < self.world.map_size[1]): 
            tooltip_text = "Край мира"
        else:
            biome = self.world.biome_map[map_y][map_x]; tooltip_text = f"({map_x}, {map_y})\nБиом: {biome.replace('_', ' ').capitalize()}"
            poi = self._get_poi_at_from_world(map_x, map_y)
            if poi: tooltip_text += f"\nЛокация: {poi.name}"
        QtWidgets.QToolTip.showText(event.globalPos(), tooltip_text, self)