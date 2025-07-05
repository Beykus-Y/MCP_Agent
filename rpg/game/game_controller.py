# rpg/game/game_controller.py
from PyQt5 import QtCore, QtWidgets
from typing import Optional, Dict

from ..models import Character, Stats, Quest
from ..world.world_state import WorldState, PointOfInterest
from ..rules import RulesEngine
from ..game_manager import GameManager
from ..network_protocol import MessageType
from ..constants import BIOME_COLORS, FOG_REVEAL_SIZE

# Импортируем окна, которыми будет управлять контроллер
from ..location_window import LocationWindow
from ..quest_log_window import QuestLogWindow
from ..inventory_window import InventoryWindow
from ..world_map_window import WorldMapWindow
from ..world.quest_generator import QuestGenerator
from ..world.nomenclator import Nomenclator


class GameController(QtCore.QObject):
    # Сигналы, которые контроллер посылает в View для обновления UI
    state_updated = QtCore.pyqtSignal()
    log_message_sent = QtCore.pyqtSignal(str)
    chat_message_sent = QtCore.pyqtSignal(str)
    poi_status_changed = QtCore.pyqtSignal(object) # Передает объект POI или None
    game_over = QtCore.pyqtSignal(str) # Сигнал о завершении игры (например, дисконнект)

    def __init__(self, world, character, save_id, is_online, network_worker, initial_player_id, initial_player_data):
        super().__init__()
        # --- Инициализация всего состояния игры ---
        self.world = world
        self.character: Optional[Character] = None
        self.all_players_on_server: Dict[str, Character] = {}
        self.save_id = save_id
        self.is_online = is_online
        self.network_worker = network_worker
        self.my_server_player_id = initial_player_id
        
        # --- Инициализация менеджеров и генераторов ---
        self.rules_engine = RulesEngine()
        self.game_manager = GameManager()
        self.quest_generator = QuestGenerator()
        self.nomenclator = Nomenclator()
        
        self.last_known_biome = ""

        # --- Инициализация окон (они будут None, пока не открыты) ---
        self.location_window = None
        self.quest_log_window = None
        self.inventory_window = None
        self.world_map_window = None
        
        # --- Первоначальная настройка состояния ---
        self._initialize_player_data(character, initial_player_data)
        
        if not self.character.discovered_cells:
            self._reveal_fog_around_player(*self.character.position)

        # --- Подключение к сетевым сигналам ---
        if self.is_online and self.network_worker:
            self.network_worker.state_update.connect(self._update_all_game_state_from_server)
            self.network_worker.disconnected.connect(self.handle_server_disconnect)
            self.network_worker.error.connect(self.handle_server_error)
            self.network_worker.chat_message_received.connect(self._handle_incoming_chat_message)
    
    def _initialize_player_data(self, local_char, initial_player_data):
        """Устанавливает начальные данные об игроках."""
        if self.is_online:
            if initial_player_data:
                for p_id, p_data in initial_player_data.items():
                    self.all_players_on_server[p_id] = Character.from_dict(p_data)
            
            if self.my_server_player_id in self.all_players_on_server:
                self.character = self.all_players_on_server[self.my_server_player_id]
            else:
                self.game_over.emit("Ваш персонаж не найден на сервере! Отключение.")
                return
        else:
            self.character = local_char
            self.my_server_player_id = self.save_id
            self.all_players_on_server = {self.my_server_player_id: self.character}
        
        self.last_known_biome = self.world.biome_map[self.character.position[1]][self.character.position[0]]

    # --- Методы, вызываемые из View (действия игрока) ---
    
    def move_character(self, dx, dy):
        if self.is_online:
            self.network_worker.send_action({'type': MessageType.PLAYER_MOVE, 'data': {'dx': dx, 'dy': dy}})
            self.log_message_sent.emit(f"Отправлен запрос на перемещение на ({dx}, {dy}). Ожидание ответа сервера...")
            return

        # Логика для оффлайн режима
        px, py = self.character.position; new_x, new_y = px + dx, py + dy
        if not (0 <= new_x < self.world.map_size[0] and 0 <= new_y < self.world.map_size[1]):
            self.log_message_sent.emit("Вы не можете идти дальше, это край мира."); return
        
        target_biome_name = self.world.biome_map[new_y][new_x]
        biome_data = BIOME_COLORS.get(target_biome_name)
        if biome_data and not biome_data[1]:
            self.log_message_sent.emit(f"Вы не можете плыть по '{target_biome_name}'. Найдите другой путь."); return
        
        self.character.position = (new_x, new_y)
        self._reveal_fog_around_player(new_x, new_y)
        self._process_movement_consequences() # <--- Выносим общие последствия движения
        self.game_manager.save_character_progress(self.character, self.save_id)
        self.state_updated.emit()

    def send_chat_message(self, message: str):
        if message and self.is_online and self.network_worker:
            self.network_worker.send_action({'type': MessageType.CHAT_MESSAGE, 'data': {'sender': self.character.name, 'message': message}})

    def open_inventory(self):
        self.inventory_window = InventoryWindow(self.character, self.rules_engine, self.is_online, self.network_worker, parent=None)
        if not self.is_online:
            self.inventory_window.character_updated.connect(self.state_updated.emit)
            self.inventory_window.save_game_requested.connect(lambda: self.game_manager.save_character_progress(self.character, self.save_id))
        self.inventory_window.exec_()

    def open_quest_log(self):
        self.quest_log_window = QuestLogWindow(self.character, self.world, parent=None)
        self.quest_log_window.exec_()
        
    def open_world_map(self):
        self.world_map_window = WorldMapWindow(self.character, self.world, self.rules_engine, self.nomenclator, self.all_players_on_server, parent=None)
        self.world_map_window.exec_()

    def interact_with_location(self):
        current_poi = self._get_poi_at(*self.character.position)
        if not current_poi: return
        
        self.location_window = LocationWindow(current_poi, self.character, parent=None)
        self.location_window.quest_requested_from_npc.connect(self.try_to_generate_quest)
        self.location_window.exec_()

    def try_to_generate_quest(self, npc_giver):
        location = self._get_poi_at(*self.character.position)
        if not location: return

        if npc_giver:
            self._log_message(f"*Вы подходите поговорить с {npc_giver.name}...*")
        else:
            self._log_message(f"*Вы начинаете расспрашивать местных в поисках работы в '{location.name}'...*")
        
        response_data = self.quest_generator.generate_quest_for_location(self.world, location, self.character.quests)
        
        if response_data and "quest" in response_data:
            quest_data = response_data["quest"]
            new_quest_id = quest_data.get("id")

            if new_quest_id and not any(q.id == new_quest_id for q in self.character.quests):
                quest = Quest(**quest_data)
                self.character.quests.append(quest)
                
                dialogue = response_data.get("dialogue_line", "Мне нужна твоя помощь.")
                giver_name = response_data.get("quest_giver_name", "Местный житель")
                self._log_message(f"<b>{giver_name}:</b> \"{dialogue}\"")
                
                self._log_message(f"**Новое задание получено: {quest.name}** (Нажмите J, чтобы открыть журнал).")
                if not self.is_online: # Сохраняем только в оффлайн режиме
                    self.game_manager.save_character_progress(self.character, self.save_id)
            else:
                self._log_message("Никто не смог предложить вам ничего нового.")
        else:
            self._log_message("Никто не смог предложить вам ничего интересного.")

    # --- Внутренняя логика и обработчики ---

    def _process_movement_consequences(self):
        """Объединяет все проверки, которые нужно делать после движения."""
        current_pos = self.character.position
        current_biome_name = self.world.biome_map[current_pos[1]][current_pos[0]]
        
        if current_biome_name != self.last_known_biome:
            self.log_message_sent.emit(f"Вы вошли в новую местность: **{current_biome_name.replace('_', ' ').capitalize()}**.")
            self.last_known_biome = current_biome_name
            
        self._check_for_poi()
        self._check_quest_objectives()

    def _get_poi_at(self, x, y) -> Optional[PointOfInterest]:
        return next((poi for poi in self.world.points_of_interest if tuple(poi.position) == (x, y)), None)

    def _check_for_poi(self):
        current_poi = self._get_poi_at(*self.character.position)
        self.poi_status_changed.emit(current_poi) # Сообщаем View о статусе
        
        if current_poi and current_poi.id not in self.character.visited_pois:
            self.log_message_sent.emit(f"Вы открыли новую локацию: **{current_poi.name}** ({current_poi.type.capitalize()}).")
            if self.is_online:
                self.network_worker.send_action({'type': MessageType.PLAYER_ENTERED_POI, 'data': {'poi_id': current_poi.id}})
            else:
                # Логика для оффлайна
                self.character.visited_pois.append(current_poi.id)
                # ... (генерация описания для оффлайна) ...
    
    def _check_quest_objectives(self):
        quest_state_changed = False
        for quest in self.character.quests:
            if quest.status != "active":
                continue

            active_objectives = [obj for obj in quest.objectives if not obj.get("completed")]
            if not active_objectives:
                quest.status = "completed"
                self._log_message(f"**Задание '{quest.name}' ВЫПОЛНЕНО!**")
                quest_state_changed = True
                continue
            
            for objective in active_objectives:
                obj_type = objective.get("type")
                
                if obj_type == "reach_location":
                    target_pos = objective.get("target_position")
                    if target_pos and tuple(self.character.position) == tuple(target_pos):
                        objective["completed"] = True
                        self._log_message(f"**Цель задания '{quest.name}' выполнена:** {objective['text']}")
                        quest_state_changed = True

            if all(obj.get("completed") for obj in quest.objectives):
                quest.status = "completed"
                self._log_message(f"**Задание '{quest.name}' ВЫПОЛНЕНО!**")
                quest_state_changed = True

        if quest_state_changed and not self.is_online: # Сохраняем только если в оффлайн режиме
            self.game_manager.save_character_progress(self.character, self.save_id)

    def _reveal_fog_around_player(self, center_x, center_y):
        half_size = FOG_REVEAL_SIZE // 2
        start_offset_x = -half_size
        end_offset_x = half_size - (1 if FOG_REVEAL_SIZE % 2 == 0 else 0)

        start_offset_y = -half_size
        end_offset_y = half_size - (1 if FOG_REVEAL_SIZE % 2 == 0 else 0)

        for dy in range(start_offset_y, end_offset_y + 1):
            for dx in range(start_offset_x, end_offset_x + 1):
                map_x, map_y = center_x + dx, center_y + dy
                if 0 <= map_x < self.world.map_size[0] and 0 <= map_y < self.world.map_size[1]:
                    self.character.discovered_cells.add((map_x, map_y))
    # --- Обработчики сетевых событий ---

    @QtCore.pyqtSlot(dict)
    def _update_all_game_state_from_server(self, data_payload: dict):
        old_pos = self.character.position if self.character else None
        
        new_world_data = data_payload.get('world')
        all_players_data = data_payload.get('players')
        if not new_world_data or not all_players_data: return

        self.world = WorldState.from_dict(new_world_data)
        
        temp_all_players = {p_id: Character.from_dict(p_data) for p_id, p_data in all_players_data.items()}
        self.all_players_on_server = temp_all_players

        if self.my_server_player_id in self.all_players_on_server:
            self.character = self.all_players_on_server[self.my_server_player_id]
        else:
            self.game_over.emit("Ваш персонаж пропал с сервера.")
            return

        # Сообщаем View, что состояние изменилось
        self.state_updated.emit()
        
        # Проверяем последствия, только если НАШ персонаж сдвинулся
        if old_pos != self.character.position:
            self._process_movement_consequences()
            
        # Обновляем открытые дочерние окна
        if self.inventory_window and self.inventory_window.isVisible():
            self.inventory_window.refresh_from_server(self.character)
        if self.quest_log_window and self.quest_log_window.isVisible():
            self.quest_log_window.character = self.character
            self.quest_log_window.world = self.world
            self.quest_log_window.populate_quests()
            self.quest_log_window.populate_locations()

    @QtCore.pyqtSlot(str)
    def handle_server_disconnect(self, reason: str):
        self.game_over.emit(f"Отключено от сервера: {reason}")

    @QtCore.pyqtSlot(str)
    def handle_server_error(self, message: str):
        self.game_over.emit(f"Ошибка сети: {message}")
        
    @QtCore.pyqtSlot(dict)
    def _handle_incoming_chat_message(self, chat_data: dict):
        sender = chat_data.get('sender', 'Неизвестный')
        message = chat_data.get('message', '')
        self.chat_message_sent.emit(f"<b>{sender}:</b> {message}")