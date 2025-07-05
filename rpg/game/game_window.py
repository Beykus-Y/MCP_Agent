# rpg/game/game_window.py
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from typing import Optional

# Импортируем наш новый контроллер и виджеты
from .game_controller import GameController
from .minimap import MinimapWidget

# Импортируем только то, что нужно для UI
from ..models import Character
from ..world.world_state import PointOfInterest
from ..constants import MAP_WINDOW_KEY

class GameWindow(QtWidgets.QWidget):
    def __init__(self, world, character, save_id, is_online, network_worker, network_thread, 
                 initial_player_id, initial_player_data, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        
        # Создаем контроллер и передаем ему всю логику и данные
        self.controller = GameController(world, character, save_id, is_online, network_worker,
                                         initial_player_id, initial_player_data)
        
        # Сохраняем только поток, чтобы правильно его завершить
        self.network_thread = network_thread

        self.setup_ui()

        # --- Связываем сигналы от контроллера к слотам этого окна ---
        self.controller.state_updated.connect(self.on_state_updated)
        self.controller.log_message_sent.connect(self._log_message)
        self.controller.chat_message_sent.connect(self._log_chat_message)
        self.controller.poi_status_changed.connect(self.on_poi_status_changed)
        self.controller.game_over.connect(self.on_game_over)
        
        self.setWindowTitle(f"Игра за: {self.controller.character.name} | Мир: {self.controller.world.world_name}")
        self.setMinimumSize(800, 600)
        
        # Первый раз обновляем UI вручную
        self.on_state_updated()
        self._log_message(f"Добро пожаловать в мир {self.controller.world.world_name}, {self.controller.character.name}!")
        if self.controller.is_online:
             self._log_chat_message("[ЧАТ] Добро пожаловать в общий чат.")

    def setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        left_panel_layout = QtWidgets.QVBoxLayout()
        
        map_group = QtWidgets.QGroupBox("Миникарта")
        map_layout = QtWidgets.QVBoxLayout()
        self.minimap_widget = MinimapWidget(self) # <--- Используем виджет из нового файла
        map_layout.addWidget(self.minimap_widget)
        map_group.setLayout(map_layout)

        location_group = QtWidgets.QGroupBox("Текущее положение")
        location_layout = QtWidgets.QFormLayout(location_group)
        self.coords_label = QtWidgets.QLabel()
        self.biome_label = QtWidgets.QLabel()
        self.poi_label = QtWidgets.QLabel("Нет")
        location_layout.addRow("Координаты:", self.coords_label)
        location_layout.addRow("Биом:", self.biome_label)
        location_layout.addRow("Локация:", self.poi_label)

        stats_group = QtWidgets.QGroupBox("Характеристики")
        stats_layout = QtWidgets.QFormLayout()
        self.stat_labels = {'strength': QtWidgets.QLabel(), 'dexterity': QtWidgets.QLabel(), 'intelligence': QtWidgets.QLabel(), 'charisma': QtWidgets.QLabel()}
        for name, label in self.stat_labels.items(): stats_layout.addRow(f"{name.capitalize()}:", label)
        self.hp_label = QtWidgets.QLabel()
        stats_layout.addRow("HP:", self.hp_label)
        stats_group.setLayout(stats_layout)

        left_panel_layout.addWidget(map_group)
        left_panel_layout.addWidget(location_group)
        left_panel_layout.addWidget(stats_group)
        left_panel_layout.addStretch()

        right_panel_layout = QtWidgets.QVBoxLayout()
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)

        controls_group = QtWidgets.QGroupBox("Управление")
        controls_layout = QtWidgets.QGridLayout()
        # --- Связываем кнопки с методами контроллера ---
        north_btn = QtWidgets.QPushButton("Север (W)"); north_btn.clicked.connect(lambda: self.controller.move_character(0, -1))
        south_btn = QtWidgets.QPushButton("Юг (S)"); south_btn.clicked.connect(lambda: self.controller.move_character(0, 1))
        west_btn = QtWidgets.QPushButton("Запад (A)"); west_btn.clicked.connect(lambda: self.controller.move_character(-1, 0))
        east_btn = QtWidgets.QPushButton("Восток (D)"); east_btn.clicked.connect(lambda: self.controller.move_character(1, 0))
        quest_btn = QtWidgets.QPushButton("Журнал (J)"); quest_btn.clicked.connect(self.controller.open_quest_log)
        self.interact_button = QtWidgets.QPushButton("Взаимодействовать (E)"); self.interact_button.clicked.connect(self.controller.interact_with_location)
        self.inventory_button = QtWidgets.QPushButton("Инвентарь (I)"); self.inventory_button.clicked.connect(self.controller.open_inventory)
        self.open_map_button = QtWidgets.QPushButton(f"Карта мира ({chr(MAP_WINDOW_KEY)})"); self.open_map_button.clicked.connect(self.controller.open_world_map)
        
        controls_layout.addWidget(north_btn, 0, 1); controls_layout.addWidget(west_btn, 1, 0)
        controls_layout.addWidget(south_btn, 1, 1); controls_layout.addWidget(east_btn, 1, 2)
        controls_layout.addWidget(quest_btn, 0, 0); controls_layout.addWidget(self.interact_button, 2, 0, 1, 3) 
        controls_layout.addWidget(self.inventory_button, 0, 2); controls_layout.addWidget(self.open_map_button, 3, 0, 1, 3)
        controls_group.setLayout(controls_layout)

        if self.controller.is_online:
            chat_group = QtWidgets.QGroupBox("Чат")
            chat_layout = QtWidgets.QVBoxLayout(chat_group)
            self.chat_display = QtWidgets.QTextEdit(); self.chat_display.setReadOnly(True)
            self.chat_input = QtWidgets.QLineEdit(); self.chat_input.setPlaceholderText("Введите сообщение...")
            self.chat_input.returnPressed.connect(self._send_chat_message) # <--- Вызываем локальный метод
            chat_layout.addWidget(self.chat_display); chat_layout.addWidget(self.chat_input)
            right_panel_layout.addWidget(chat_group, 2)

        right_panel_layout.addWidget(self.log_view, 3)
        right_panel_layout.addWidget(controls_group, 1)
        main_layout.addLayout(left_panel_layout, 1)
        main_layout.addLayout(right_panel_layout, 2)
        
    # --- Слоты, которые реагируют на сигналы контроллера ---

    @QtCore.pyqtSlot()
    def on_state_updated(self):
        """Обновляет все элементы UI на основе данных из контроллера."""
        self._update_character_panel()
        self._update_location_panel()
        self.minimap_widget.update_data(self.controller.character, self.controller.world, self.controller.all_players_on_server)

    @QtCore.pyqtSlot(object)
    def on_poi_status_changed(self, current_poi: Optional[PointOfInterest]):
        """Обновляет кнопку взаимодействия."""
        if current_poi:
            self.interact_button.setEnabled(True)
            self.interact_button.setText(f"Взаимодействовать с '{current_poi.name}' (E)")
        else:
            self.interact_button.setEnabled(False)
            self.interact_button.setText("Взаимодействовать (E)")

    @QtCore.pyqtSlot(str)
    def on_game_over(self, reason: str):
        """Показывает сообщение и закрывает окно."""
        QtWidgets.QMessageBox.warning(self, "Игра окончена", reason)
        self.close()

    @QtCore.pyqtSlot(str)
    def _log_message(self, message):
        self.log_view.append(message)

    @QtCore.pyqtSlot(str)
    def _log_chat_message(self, message):
        if hasattr(self, 'chat_display'):
            self.chat_display.append(message)
    
    # --- Локальные методы UI и обработки ввода ---

    def _send_chat_message(self):
        message = self.chat_input.text().strip()
        self.controller.send_chat_message(message)
        self.chat_input.clear()
        self.setFocus()
    
    def _update_character_panel(self):
        char = self.controller.character
        if char:
            final_stats = self.controller.rules_engine.calculate_final_stats(char)
            for name, label in self.stat_labels.items():
                label.setText(str(getattr(final_stats, name, 0)))
            self.hp_label.setText(f"{char.current_hp} / {char.max_hp}")

    def _update_location_panel(self):
        char = self.controller.character
        world = self.controller.world
        px, py = char.position
        self.coords_label.setText(f"({px}, {py})")
        self.biome_label.setText(world.biome_map[py][px].replace('_', ' ').capitalize())
        
        poi = self.controller._get_poi_at(px, py)
        if poi:
            self.poi_label.setText(f"{poi.name} ({poi.type.capitalize()})")
        else:
            self.poi_label.setText("Нет")

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        key = event.key()
        if self.controller.is_online and self.chat_input.hasFocus():
            super().keyPressEvent(event)
            return

        key_map = {
            QtCore.Qt.Key_W: lambda: self.controller.move_character(0, -1),
            QtCore.Qt.Key_S: lambda: self.controller.move_character(0, 1),
            QtCore.Qt.Key_A: lambda: self.controller.move_character(-1, 0),
            QtCore.Qt.Key_D: lambda: self.controller.move_character(1, 0),
            QtCore.Qt.Key_J: self.controller.open_quest_log,
            QtCore.Qt.Key_E: self.controller.interact_with_location,
            QtCore.Qt.Key_I: self.controller.open_inventory,
            MAP_WINDOW_KEY: self.controller.open_world_map,
        }
        action = key_map.get(key)
        if action:
            action()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent):
        # Логика закрытия остается здесь, так как это жизненный цикл окна
        if self.controller.is_online and self.controller.network_worker:
            reply = QtWidgets.QMessageBox.question(self, 'Подтверждение выхода', "Вы уверены? Вы будете отключены от сервера.", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                self.controller.network_worker.disconnect()
                if self.network_thread:
                    self.network_thread.quit()
                    self.network_thread.wait(2000)
                event.accept()
            else:
                event.ignore()
        elif not self.controller.is_online:
            reply = QtWidgets.QMessageBox.question(self, 'Подтверждение выхода', "Вы уверены? Весь прогресс будет сохранен.", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                # Сохраняем и персонажа, и мир через контроллер
                self.controller.game_manager.save_character_progress(self.controller.character, self.controller.save_id)
                self.controller.game_manager.save_world_state(self.controller.world)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()