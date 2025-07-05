# rpg/world_map_window.py
from PyQt5 import QtWidgets, QtCore, QtGui
from typing import Dict, List, Tuple

from .models import Character
from .world.world_state import WorldState, PointOfInterest
from .rules import RulesEngine
from .world.nomenclator import Nomenclator

from .constants import *
FOG_COLOR = QtGui.QColor("#1a1a1a") 
class WorldMapScene(QtWidgets.QGraphicsScene):
    def __init__(self, character: Character, world: WorldState, rules_engine: RulesEngine, nomenclator: Nomenclator, all_players: Dict[str, Character], parent=None):
        super().__init__(parent)
        self.character = character
        self.world = world
        self.rules_engine = rules_engine
        self.nomenclator = nomenclator
        self.all_players = all_players

        self.color_cache = {name: QtGui.QColor(data[0]) for name, data in BIOME_COLORS.items()}
        
        self.initial_scale = 1.0 # Базовый масштаб
        self.set_initial_scene_rect() # Устанавливаем размер сцены

    def set_initial_scene_rect(self):
        # Размер карты в "пикселях" при масштабе 1:1
        map_width_pixels = self.world.map_size[0] * 16 # Например, 16 пикселей на клетку
        map_height_pixels = self.world.map_size[1] * 16
        self.setSceneRect(0, 0, map_width_pixels, map_height_pixels)

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF):
        # Отрисовка клеток карты
        cell_size_on_screen = self.views()[0].transform().m11() * 16 

        start_x = int(rect.left() / 16)
        end_x = int(rect.right() / 16) + 1
        start_y = int(rect.top() / 16)
        end_y = int(rect.bottom() / 16) + 1

        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                if not (0 <= x < self.world.map_size[0] and 0 <= y < self.world.map_size[1]):
                    continue

                map_rect = QtCore.QRectF(x * 16, y * 16, 16, 16)

                # --- Туман войны ---
                if (x, y) not in self.character.discovered_cells:
                    painter.fillRect(map_rect, FOG_COLOR)
                    painter.setPen(QtGui.QColor("#555555"))
                    font = painter.font(); font.setPixelSize(int(cell_size_on_screen * 0.7)); painter.setFont(font)
                    painter.drawText(map_rect, QtCore.Qt.AlignCenter, "?")
                    continue
                # --- Конец тумана войны ---

                biome = self.world.biome_map[y][x]
                color = self.color_cache.get(biome, self.color_cache['default'])
                painter.fillRect(map_rect, color)
        
        # Отрисовка POI поверх биомов
        poi_font = painter.font(); poi_font.setPixelSize(int(cell_size_on_screen * 0.7)); painter.setFont(poi_font)
        for poi in self.world.points_of_interest:
            if tuple(poi.position) in self.character.discovered_cells:
                poi_rect = QtCore.QRectF(poi.position[0] * 16, poi.position[1] * 16, 16, 16)
                painter.setPen(QtGui.QColor("#ffffff"))
                painter.drawText(poi_rect, QtCore.Qt.AlignCenter, POI_ICONS.get(poi.type, "?"))

        # --- НОВОЕ: Отрисовка всех игроков ---
        player_font = painter.font(); player_font.setPixelSize(int(cell_size_on_screen * 0.9)); painter.setFont(player_font)
        other_player_font = painter.font(); other_player_font.setPixelSize(int(cell_size_on_screen * 0.7)); painter.setFont(other_player_font)

        for p_id, p_char in self.all_players.items():
            # Отрисовываем только если клетка игрока открыта
            if tuple(p_char.position) in self.character.discovered_cells:
                player_map_rect = QtCore.QRectF(p_char.position[0] * 16, p_char.position[1] * 16, 16, 16)
                
                if p_char.name == self.character.name: # Наш игрок
                    painter.setPen(QtGui.QColor("#ff0000")) # Красный
                    painter.setFont(player_font)
                    painter.drawText(player_map_rect, QtCore.Qt.AlignCenter, PLAYER_ICON)
                else: # Другой игрок
                    painter.setPen(QtGui.QColor("#00ff00")) # Зеленый
                    painter.setFont(other_player_font)
                    painter.drawText(player_map_rect, QtCore.Qt.AlignCenter, OTHER_PLAYER_ICON)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            self._last_mouse_pos = event.screenPos()
            event.accept()

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        if event.buttons() == QtCore.Qt.LeftButton and self._last_mouse_pos:
            delta = event.screenPos() - self._last_mouse_pos
            self.views()[0].translate(delta.x(), delta.y())
            self._last_mouse_pos = event.screenPos()
            event.accept()

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            self._last_mouse_pos = None
            event.accept()

    def wheelEvent(self, event: QtWidgets.QGraphicsSceneWheelEvent):
        # Масштабирование
        zoom_factor = 1.15
        if event.delta() > 0: # Вращение колеса вверх (увеличить)
            self.views()[0].scale(zoom_factor, zoom_factor)
        else: # Вращение колеса вниз (уменьшить)
            self.views()[0].scale(1 / zoom_factor, 1 / zoom_factor)
        event.accept()


class WorldMapWindow(QtWidgets.QDialog):
    closed = QtCore.pyqtSignal() # Сигнал, который будет испускаться при закрытии окна

    def __init__(self, character: Character, world: WorldState, rules_engine: RulesEngine, nomenclator: Nomenclator, all_players: Dict[str, Character], parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.character = character
        self.world = world
        self.rules_engine = rules_engine
        self.nomenclator = nomenclator
        self.all_players = all_players

        self.setWindowTitle(f"Карта мира: {self.world.world_name}")
        self.setMinimumSize(800, 700)
        
        self.setup_ui()
        self.center_view_on_player()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        self.scene = WorldMapScene(self.character, self.world, self.rules_engine, self.nomenclator, self.all_players, self)
        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setRenderHint(QtGui.QPainter.Antialiasing)
        self.view.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.view.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse) # Масштабирование к курсору
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        main_layout.addWidget(self.view)

        # Добавим кнопки для масштабирования/панорамирования (опционально, т.к. есть мышь)
        control_layout = QtWidgets.QHBoxLayout()
        zoom_in_button = QtWidgets.QPushButton("+"); zoom_in_button.clicked.connect(lambda: self.view.scale(1.2, 1.2))
        zoom_out_button = QtWidgets.QPushButton("-"); zoom_out_button.clicked.connect(lambda: self.view.scale(1/1.2, 1/1.2))
        reset_zoom_button = QtWidgets.QPushButton("Сброс масштаба"); reset_zoom_button.clicked.connect(self.reset_zoom)
        center_player_button = QtWidgets.QPushButton("К игроку"); center_player_button.clicked.connect(self.center_view_on_player)
        
        control_layout.addWidget(zoom_in_button)
        control_layout.addWidget(zoom_out_button)
        control_layout.addWidget(reset_zoom_button)
        control_layout.addWidget(center_player_button)
        control_layout.addStretch()

        close_button = QtWidgets.QPushButton("Закрыть"); close_button.clicked.connect(self.accept)
        control_layout.addWidget(close_button)

        main_layout.addLayout(control_layout)
    
    def center_view_on_player(self):
        # Центрируем вид на игроке
        player_x_scene = self.character.position[0] * 16 + 8 # +8 для центра ячейки
        player_y_scene = self.character.position[1] * 16 + 8
        self.view.centerOn(player_x_scene, player_y_scene)

    def reset_zoom(self):
        # Сброс масштаба до дефолтного (1:1)
        self.view.setTransform(QtGui.QTransform())
        self.center_view_on_player() # После сброса масштаба перецентрировать на игроке
        
    def keyPressEvent(self, event: QtGui.QKeyEvent):
        # Быстрые клавиши для перемещения/масштабирования на карте
        scale_factor = 1.15
        move_pixels = 50 # Величина смещения в пикселях сцены
        
        if event.key() == QtCore.Qt.Key_Plus or event.key() == QtCore.Qt.Key_Equal:
            self.view.scale(scale_factor, scale_factor)
        elif event.key() == QtCore.Qt.Key_Minus:
            self.view.scale(1 / scale_factor, 1 / scale_factor)
        elif event.key() == QtCore.Qt.Key_W:
            self.view.translate(0, -move_pixels)
        elif event.key() == QtCore.Qt.Key_S:
            self.view.translate(0, move_pixels)
        elif event.key() == QtCore.Qt.Key_A:
            self.view.translate(-move_pixels, 0)
        elif event.key() == QtCore.Qt.Key_D:
            self.view.translate(move_pixels, 0)
        else:
            super().keyPressEvent(event) # Передаем событие дальше
    
    def closeEvent(self, event: QtGui.QCloseEvent):
        # При закрытии окна, отправляем сигнал
        self.closed.emit()
        super().closeEvent(event)