# rpg_visualizer.py (Версия 1.1 - Исправленная)
import sys
import os
import requests
import json
from PyQt5 import QtWidgets, QtCore, QtGui
from dotenv import load_dotenv

# --- Конфигурация ---
load_dotenv()
RPG_MCP_PORT = os.getenv("MCP_RPG_PORT", "8008")
RPG_MCP_URL = f"http://127.0.0.1:{RPG_MCP_PORT}/mcp"
MAP_SIZE = 11  # Размер отображаемой карты (нечетное число для центрирования)
UPDATE_INTERVAL = 3000 # 3 секунды

# --- Цвета и иконки для карты ---
TERRAIN_COLORS = {
    "plains": "#a1c45a",
    "forest": "#2a6141",
    "fort": "#808080",
    "default": "#d3d3d3"
}
PLAYER_ICON = "👤"
NPC_ICON = "🤖"

class RPGVisualizer(QtWidgets.QWidget):
    def __init__(self, player_id):
        super().__init__()
        
        if not player_id:
            raise ValueError("Необходимо указать ID игрока!")
        
        ### ИСПРАВЛЕНИЕ: Инициализируем save_id как None ###
        self.save_id = None
        self.player_id = int(player_id)
        
        # Данные, которые мы будем обновлять
        self.player_data = {}
        self.inventory_data = []
        self.map_data = {} # { (x, y): details, ... }

        # Теперь эта строка будет работать, т.к. self.save_id существует
        self.setWindowTitle(f"RPG Visualizer - Загрузка...")
        self.setup_ui()
        self.resize(600, 600)

        # Таймер для периодического обновления данных
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_all_data)
        self.timer.start(UPDATE_INTERVAL)
        
        # Первоначальное обновление
        self.update_all_data()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # --- Секция статуса персонажа ---
        status_box = QtWidgets.QGroupBox("Статус Персонажа")
        status_layout = QtWidgets.QFormLayout()
        self.name_label = QtWidgets.QLabel("Загрузка...")
        self.hp_label = QtWidgets.QLabel("Загрузка...")
        self.location_label = QtWidgets.QLabel("Загрузка...")
        status_layout.addRow("Имя:", self.name_label)
        status_layout.addRow("HP:", self.hp_label)
        status_layout.addRow("Координаты:", self.location_label)
        status_box.setLayout(status_layout)

        # --- Секция карты ---
        map_box = QtWidgets.QGroupBox("Карта")
        self.map_grid_layout = QtWidgets.QGridLayout()
        self.map_grid_layout.setSpacing(1)
        self.map_labels = {}
        for y in range(MAP_SIZE):
            for x in range(MAP_SIZE):
                label = QtWidgets.QLabel("?")
                label.setFixedSize(40, 40)
                label.setAlignment(QtCore.Qt.AlignCenter)
                label.setStyleSheet("border: 1px solid grey; font-size: 18px;")
                self.map_grid_layout.addWidget(label, y, x)
                self.map_labels[(x, y)] = label
        map_box.setLayout(self.map_grid_layout)

        # --- Секция инвентаря ---
        inventory_box = QtWidgets.QGroupBox("Инвентарь")
        inventory_layout = QtWidgets.QVBoxLayout()
        self.inventory_list = QtWidgets.QListWidget()
        inventory_layout.addWidget(self.inventory_list)
        inventory_box.setLayout(inventory_layout)

        main_layout.addWidget(status_box)
        main_layout.addWidget(map_box)
        main_layout.addWidget(inventory_box, stretch=1)

    def _mcp_call(self, method, params):
        """Вспомогательная функция для вызова MCP_RPG."""
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            response = requests.post(RPG_MCP_URL, json=payload, timeout=2)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                print(f"Ошибка от MCP: {data['error']['message']}")
                return None
            return data.get("result")
        except requests.exceptions.RequestException as e:
            # Делаем вывод ошибки более заметным
            print(f"!!! КРИТИЧЕСКАЯ ОШИБКА ПОДКЛЮЧЕНИЯ к MCP_RPG: {e}")
            self.statusBar().showMessage("Ошибка подключения к MCP_RPG!", 5000) if hasattr(self, 'statusBar') else None
            return None

    @QtCore.pyqtSlot()
    def update_all_data(self):
        """Запрашивает все данные от MCP и обновляет UI."""
        
        # 1. Если не знаем ID сохранения, сначала узнаем его
        if self.save_id is None:
            active_game_data = self._mcp_call("get_active_game", {})
            if active_game_data and active_game_data.get("status") == "ok":
                self.save_id = active_game_data.get("active_save_id")
                # Обновляем заголовок, когда ID становится известен
                self.setWindowTitle(f"RPG Visualizer - Игра #{self.save_id}")
            else:
                self.setWindowTitle(f"RPG Visualizer - Активная игра не выбрана")
                return # Прерываем обновление, если не знаем, с какой игрой работать

        # 2. Получаем данные персонажа
        player_data = self._mcp_call("get_character_details", {"character_id": self.player_id})
        if player_data: self.player_data = player_data
        
        # 3. Получаем инвентарь
        inventory_data = self._mcp_call("get_inventory", {"character_id": self.player_id})
        if inventory_data: self.inventory_data = inventory_data.get("inventory", [])

        # 4. Получаем данные о локациях вокруг игрока
        if "location_x" in self.player_data and self.save_id is not None:
            center_x, center_y = self.player_data["location_x"], self.player_data["location_y"]
            radius = MAP_SIZE // 2
            for y_offset in range(-radius, radius + 1):
                for x_offset in range(-radius, radius + 1):
                    x, y = center_x + x_offset, center_y + y_offset
                    # Передаем save_id в get_location_details, т.к. он у нас уже есть
                    loc_data = self._mcp_call("get_location_details", {"save_id": self.save_id, "x": x, "y": y})
                    if loc_data and loc_data.get("status") == "ok":
                        self.map_data[(x, y)] = loc_data.get("details")

        # После сбора всех данных, обновляем интерфейс
        self.refresh_ui()

    def refresh_ui(self):
        """Обновляет все виджеты на основе загруженных данных."""
        # Обновляем статус
        self.name_label.setText(self.player_data.get("name", "N/A"))
        self.hp_label.setText(f"{self.player_data.get('hp', 0)} / {self.player_data.get('max_hp', 0)}")
        self.location_label.setText(f"({self.player_data.get('location_x', 0)}, {self.player_data.get('location_y', 0)})")
        
        # Обновляем инвентарь
        self.inventory_list.clear()
        for item in self.inventory_data:
            self.inventory_list.addItem(f"{item['item_name']} (x{item.get('quantity', 1)})")

        # Обновляем карту
        if "location_x" in self.player_data:
            center_x, center_y = self.player_data["location_x"], self.player_data["location_y"]
            radius = MAP_SIZE // 2
            for y_map in range(MAP_SIZE):
                for x_map in range(MAP_SIZE):
                    world_x = center_x - radius + x_map
                    world_y = center_y - radius + y_map
                    
                    label = self.map_labels[(x_map, y_map)]
                    loc_details = self.map_data.get((world_x, world_y))
                    
                    icon = ""
                    if world_x == center_x and world_y == center_y:
                        icon = PLAYER_ICON
                    
                    if loc_details:
                        terrain = loc_details.get("terrain", "default").lower()
                        color = TERRAIN_COLORS.get(terrain, TERRAIN_COLORS["default"])
                        label.setStyleSheet(f"background-color: {color}; border: 1px solid grey; font-size: 18px;")
                        label.setToolTip(loc_details.get("name", "Неизвестно"))
                    else:
                        label.setStyleSheet("background-color: #333; border: 1px solid grey; color: #555;")
                        label.setToolTip("Неизведанная область")

                    label.setText(icon)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    
    dialog = QtWidgets.QInputDialog()
    player_id_str, ok = dialog.getText(None, "Ввод данных", "Введите ID персонажа игрока (character_id):")

    if ok and player_id_str.isdigit():
        window = RPGVisualizer(player_id=player_id_str)
        window.show()
        sys.exit(app.exec_())
    else:
        print("Неверный ввод. Визуализатор не будет запущен.")
        sys.exit(0)