# rpg_server.py (в корне проекта, рядом с launcher.py)
import sys
import os
import socket
import threading
import json
import time
import uuid
import logging # <--- Добавлен модуль логирования
from typing import List, Dict, Any, Optional, Tuple 
from dataclasses import dataclass, asdict
import signal
# Настраиваем базовый уровень логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Добавляем корневую папку проекта в sys.path, чтобы импортировать rpg.*
# Это важно, если rpg_server.py запускается из корневой директории, а rpg/ находится в подпапке
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv, find_dotenv
from rpg.models import Character, NPC, Item, Quest, Stats # <--- Убедимся, что все dataclass импортированы
from rpg.game_manager import GameManager, EnhancedJSONEncoder
from rpg.world.world_state import WorldState, PointOfInterest, Faction
from rpg.world.generator import WorldGenerator
from rpg.network_protocol import send_json_message, receive_json_message, MessageType
from rpg.constants import BIOME_COLORS, BUFFER_SIZE, PORT, HOST, FOG_REVEAL_SIZE, WORLD_STATES_DIR, WORLD_TEMPLATES_DIR
from rpg.world.nomenclator import Nomenclator
@dataclass
class PlayerInfo:
    character: Character
    save_id: str

class GameServer:
    def __init__(self, world_name: str):
        dotenv_path = find_dotenv()
        if os.path.exists(dotenv_path):
            load_dotenv(dotenv_path)
        else:
            logging.warning("[SERVER WARNING] .env file not found. AI features might not work.")

        self.game_manager = GameManager()
        self.connected_clients: dict[str, socket.socket] = {} # {player_id: socket}
        self.player_data: dict[str, PlayerInfo] = {} # {player_id: PlayerInfo object}
        self.nomenclator = Nomenclator()
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.world_name = world_name
        self.lock = threading.RLock() # Блокировка для доступа к общим данным (мир, персонажи)
        if not os.path.exists(WORLD_STATES_DIR):
            os.makedirs(WORLD_STATES_DIR)
        
        self.game_manager = GameManager()
        self.nomenclator = Nomenclator()
        logging.info(f"--- RPG Server Initialized ---")
        self.world: WorldState = self._load_or_initialize_world() # <--- Вызываем новый метод
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.lock = threading.RLock()

        logging.info(f"--- RPG Server Initialized for world '{self.world_name}' ---")
        logging.info(f"World: {self.world.world_name} (Size: {self.world.map_size[0]}x{self.world.map_size[1]})")
        logging.info(f"Listening on {HOST}:{PORT}")


    def _load_or_initialize_world(self) -> WorldState:
        # 1. Пытаемся загрузить сохраненное СОСТОЯНИЕ через GameManager
        logging.info(f"Attempting to load state for world '{self.world_name}'...")
        world = self.game_manager.load_world_state(self.world_name)
        if world:
            logging.info("Saved world state loaded successfully.")
            return world

        # 2. Если не получилось, пытаемся загрузить ШАБЛОН через GameManager
        logging.info(f"No saved state found. Initializing from template '{self.world_name}'...")
        world = self.game_manager.load_world_template(self.world_name)
        if world:
            logging.info("World template loaded successfully.")
            return world

        # --- Шаг 3: Если нет ни состояния, ни шаблона, ГЕНЕРАЦИЯ нового мира ---
        logging.warning(f"No state or template found for '{self.world_name}'. Generating a new world as a fallback.")
        
        generator = WorldGenerator(map_width=50, map_height=50)
        
        # Используем self.world_name для генерации, а не жестко заданное имя
        params = {
            "world_name": self.world_name,
            "year": 1000,
            "tech_level": "fantasy",
            "magic_level": "medium",
            "civilizations": [
                {"id": "feudal_kingdom", "name": "Феодальное королевство", "description": "", "tech_level": ["fantasy"], "magic_level": ["low", "medium"]},
                {"id": "ancient_elves", "name": "Древние эльфы", "description": "", "tech_level": ["fantasy"], "magic_level": ["medium", "high"]},
                {"id": "nomad_horde", "name": "Кочевая орда", "description": "", "tech_level": ["stone_age", "fantasy"], "magic_level": ["none", "low"]}
            ]
        }
        
        world = generator.generate_new_world(params)
        # Сохраняем сгенерированный мир как новый ШАБЛОН
        generator.save_world(world)
        logging.info(f"New world template '{self.world_name}' generated and saved.")
        
        return world
    

    def _handle_player_entered_poi(self, character: Character, data: dict):
        poi_id = data.get('poi_id')
        if not poi_id: return

        # Проверяем, посещал ли персонаж это место РАНЬШЕ
        if poi_id in character.visited_pois:
            return # Ничего не делаем, он тут уже был

        # Находим объект POI в мире
        poi_object = next((p for p in self.world.points_of_interest if p.id == poi_id), None)
        if not poi_object:
            logging.warning(f"Player {character.name} entered non-existent POI {poi_id}")
            return

        # Игрок здесь впервые!
        logging.info(f"Player {character.name} discovered a new POI: {poi_object.name}")
        character.visited_pois.append(poi_id)

        # Генерируем описание, ТОЛЬКО если оно еще не было сгенерировано
        if not poi_object.description:
            logging.info(f"Generating description for {poi_object.name} for the first time...")
            try:
                # Nomenclator нужно будет создать в __init__ сервера
                context = f"Локация: {poi_object.name}. Тип: {poi_object.type}. Мир: {self.world.world_name}."
                poi_object.description = self.nomenclator.generate_description(poi_object.name, poi_object.type, context)
            except Exception as e:
                logging.error(f"Failed to generate POI description: {e}")
                poi_object.description = "Это место выглядит загадочно, но слова не могут его описать."

        # Рассылаем всем обновленное состояние мира (с новым visited_pois и, возможно, новым описанием)
        self.broadcast_game_state_update()
    def save_world_state(self):
        """Сохраняет текущее состояние мира в файл."""
        logging.info(f"Saving current world state for '{self.world.world_name}'...")
        # Просто вызываем метод менеджера
        self.game_manager.save_world_state(self.world)
        logging.info("World state saved successfully via GameManager.")

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1.0) # Таймаут для accept()
        self.server_socket.bind((HOST, PORT))
        self.server_socket.listen(5)
        self.running = True
        signal.signal(signal.SIGINT, self.signal_handler)
        logging.info(f"Server started, listening on {HOST}:{PORT} Press Ctrl+C to stop.")

        accept_thread = threading.Thread(target=self._accept_connections)
        accept_thread.daemon = True # Позволяет потоку завершиться при закрытии основной программы
        accept_thread.start()

        # Основной цикл сервера (можно добавить логику обновления мира)
        try:
            while self.running:
                time.sleep(1) # Просто ждем, чтобы главный поток не завершился
        except KeyboardInterrupt:
            logging.info("KeyboardInterrupt received in main thread.")
        finally:
            self.stop()
    def signal_handler(self, sig, frame):
        """Обработчик для Ctrl+C."""
        logging.warning(f"Signal {sig} received. Initiating graceful shutdown...")
        if self.running:
            self.stop()

    def _accept_connections(self):
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                logging.info(f"Accepted connection from {addr}")
                client_handler = threading.Thread(target=self._handle_client, args=(conn, addr))
                client_handler.daemon = True
                client_handler.start()
            except socket.timeout: 
                continue
            except OSError as e:
                if self.running: 
                    logging.error(f"Error accepting connection: {e}")
                break
            except Exception as e:
                logging.critical(f"General error in accept_connections: {e}", exc_info=True)
                if self.running:
                    logging.error(f"Error accepting connection: {e}")
                break

    def _handle_client(self, conn: socket.socket, addr: tuple):
        player_id = str(uuid.uuid4())
        # Инициализируем PlayerInfo в dict, чтобы избежать KeyError
        self.player_data[player_id] = None 
        self.connected_clients[player_id] = conn

        try:
            logging.info(f"Client handler for {addr} ({player_id}): Waiting for login message.")
            login_msg = receive_json_message(conn)

            if login_msg and login_msg.get('type') == MessageType.LOGIN:
                char_save_id = login_msg.get('data', {}).get('character_id')
                if char_save_id:
                    character = self.game_manager.load_character(char_save_id)
                    if character:
                        with self.lock:
                            # Убедимся, что персонаж стартует на клетке мира, а не где-то далеко
                            if not (0 <= character.position[0] < self.world.map_size[0] and
                                    0 <= character.position[1] < self.world.map_size[1]):
                                capital = next((p for p in self.world.points_of_interest if p.type == "capital"), None)
                                if capital:
                                    character.position = capital.position
                                else:
                                    character.position = (self.world.map_size[0] // 2, self.world.map_size[1] // 2)
                            
                            self.player_data[player_id] = PlayerInfo(character=character, save_id=char_save_id)
                            logging.info(f"Player {character.name} ({char_save_id}) connected. Server ID: {player_id}")
                            
                        self.send_full_world_state(player_id)

                        # Устанавливаем таймаут на клиентский сокет для последующих recv()


                    else:
                        logging.warning(f"Failed to load character {char_save_id} for new client.")
                        send_json_message(conn, {'type': MessageType.ERROR, 'data': 'Character not found'})
                        conn.close()
                        del self.connected_clients[player_id]
                        del self.player_data[player_id]
                        return
                else:
                    logging.warning(f"Login message from {addr} missing character_id.")
                    send_json_message(conn, {'type': MessageType.ERROR, 'data': 'Missing character_id'})
                    conn.close()
                    del self.connected_clients[player_id]
                    del self.player_data[player_id]
                    return
            else:
                logging.warning(f"Received non-login message first or invalid login sequence from {addr}.")
                send_json_message(conn, {'type': MessageType.ERROR, 'data': 'Invalid login sequence'})
                conn.close()
                del self.connected_clients[player_id]
                del self.player_data[player_id]
                return

            # 2. Основной цикл приема команд
            logging.info(f"Client handler for {player_id}: Entering main receive loop.")
            while self.running:
                try:
                    # receive_json_message(conn) будет блокировать до получения данных
                    client_msg = receive_json_message(conn)
                    if not client_msg:
                        logging.info(f"Client {player_id} disconnected gracefully (receive_json_message returned None).")
                        break # Выходим из цикла
                    
                    player_info = self.player_data.get(player_id)
                    if not player_info:
                        logging.warning(f"PlayerInfo for {player_id} not found during message handling. Disconnecting client.")
                        break 
                    
                    logging.info(f"Client {player_id} ({player_info.character.name}): Received message type={client_msg.get('type')}")
                    
                    with self.lock: 
                        if client_msg['type'] == MessageType.PLAYER_MOVE:
                            self._handle_player_move(player_id, player_info.character, client_msg['data'])
                        elif client_msg['type'] == MessageType.CHAT_MESSAGE:
                            self._handle_chat_message(player_id, player_info.character, client_msg['data'])

                        elif client_msg['type'] == MessageType.EQUIP_ITEM:
                            self._handle_equip_item(player_info.character, client_msg['data'])
                        elif client_msg['type'] == MessageType.UNEQUIP_ITEM:
                            self._handle_unequip_item(player_info.character, client_msg['data'])
                        elif client_msg['type'] == MessageType.USE_ITEM:
                            self._handle_use_item(player_info.character, client_msg['data'])
                        elif client_msg['type'] == MessageType.PLAYER_ENTERED_POI:
                            self._handle_player_entered_poi(player_info.character, client_msg['data'])
                        else:
                            logging.warning(f"Unknown message type from {player_id}: {client_msg['type']}")

                except json.JSONDecodeError as e:
                    logging.error(f"JSONDecodeError from client {player_id}: {e}. Invalid message format. Disconnecting.", exc_info=True)
                    send_json_message(conn, {'type': MessageType.ERROR, 'data': 'Invalid JSON message format'})
                    break
                # ИСПРАВЛЕНИЕ: УДАЛЯЕМ ОБРАБОТКУ socket.timeout здесь, т.к. его не будет
                # except socket.timeout: 
                #    continue 
                except (OSError, ConnectionResetError) as e:
                    if e.errno == 10054: # Connection reset by peer (Windows)
                        logging.info(f"Client {player_id} forcibly disconnected (Error 10054 - Connection reset by peer).")
                    elif e.errno == 10038: # Operation on non-socket (Windows) - often happens when socket is closed from another thread
                        logging.info(f"Client {player_id} socket already closed (Error 10038 - Operation on non-socket).")
                    else:
                        logging.error(f"OSError from client {player_id}: {e}", exc_info=True)
                    break
                except ConnectionResetError: # For Linux/macOS
                    logging.info(f"Client {player_id} forcibly disconnected (ConnectionResetError).")
                    break
                except Exception as e: # Общий обработчик для неожиданных ошибок в цикле
                    logging.critical(f"Unhandled error in client loop {player_id}: {e}", exc_info=True)
                    break

        except Exception as e: # Общий обработчик ошибок при инициализации или во внешнем цикле (логин)
            logging.critical(f"Error in _handle_client for {player_id} during setup/initial login: {e}", exc_info=True)
            try:
                send_json_message(conn, {'type': MessageType.ERROR, 'data': f'Server error during connection handling: {e}'})
            except Exception:
                pass # Если не удалось отправить, то ничего страшного
        finally:
            self._cleanup_client(player_id)


    def _handle_chat_message(self, sender_player_id: str, sender_character: Character, chat_data: dict):
        logging.info(f"Handling CHAT_MESSAGE from {sender_character.name} (ID: {sender_player_id}).")

        message_content = chat_data.get('message', '')
        sender_name = chat_data.get('sender', sender_character.name) 

        if message_content:
            logging.info(f"[CHAT] {sender_name}: {message_content}")
            chat_message_for_clients = {
                'type': MessageType.CHAT_MESSAGE,
                'data': {'sender': sender_name, 'message': message_content}
            }
            self.broadcast_message(chat_message_for_clients)
        else:
            logging.warning(f"Received empty chat message from {sender_character.name}.")

    def broadcast_message(self, message: dict):
        logging.info(f"Broadcasting message type: {message.get('type')}.")
        # Делаем копию списка клиентов, чтобы избежать проблем, если клиент отключится во время итерации
        clients_to_send = list(self.connected_clients.items()) 
        for client_id, client_socket in clients_to_send: 
            try:
                send_json_message(client_socket, message, cls=EnhancedJSONEncoder)
            except Exception as e:
                logging.error(f"Error broadcasting message to client {client_id}: {e}. Initiating cleanup.", exc_info=True)
                # Если произошла ошибка при отправке, это может означать, что сокет недействителен.
                # Вызываем cleanup, чтобы удалить этого клиента.
                self._cleanup_client(client_id) 


    def _handle_player_move(self, player_id: str, character: Character, move_data: dict):
        logging.info(f"Handling PLAYER_MOVE from {character.name} (ID: {player_id}).")
        dx = move_data.get('dx', 0)
        dy = move_data.get('dy', 0)

        new_x, new_y = character.position[0] + dx, character.position[1] + dy

        # Проверки на выход за пределы карты и непроходимость биома...
        if not (0 <= new_x < self.world.map_size[0] and 0 <= new_y < self.world.map_size[1]):
            logging.warning(f"Move rejected for {character.name}: out of bounds ({new_x},{new_y}).")
            return

        target_biome_name = self.world.biome_map[new_y][new_x]
        biome_data = BIOME_COLORS.get(target_biome_name)
        if biome_data and not biome_data[1]:
            logging.warning(f"Move rejected for {character.name}: cannot move to impassable biome '{target_biome_name}'.")
            return
        
        # Захватываем блокировку для всех изменений общих данных
        with self.lock:
            # Изменяем позицию
            character.position = (new_x, new_y)
            logging.info(f"Player {character.name} moved to {character.position}.")

            # ИЗМЕНЯЕМ ТУМАН ВОЙНЫ ТОЖЕ ПОД ЗАМКОМ
            half_size = FOG_REVEAL_SIZE // 2
            start_offset_x = -half_size
            end_offset_x = half_size - (1 if FOG_REVEAL_SIZE % 2 == 0 else 0)
            start_offset_y = -half_size
            end_offset_y = half_size - (1 if FOG_REVEAL_SIZE % 2 == 0 else 0)

            for dy_fov in range(start_offset_y, end_offset_y + 1):
                for dx_fov in range(start_offset_x, end_offset_x + 1):
                    map_x_fov, map_y_fov = new_x + dx_fov, new_y + dy_fov
                    if 0 <= map_x_fov < self.world.map_size[0] and 0 <= map_y_fov < self.world.map_size[1]:
                        character.discovered_cells.add((map_x_fov, map_y_fov))
        
        # Рассылка происходит после того, как все данные изменены и блокировка освобождена
        self.broadcast_game_state_update()
        logging.info(f"Broadcasted world state update after {character.name}'s move.")


    def broadcast_game_state_update(self):
    # Захватываем блокировку, чтобы безопасно скопировать данные
        with self.lock:
            player_states = {pid: asdict(p_info.character) for pid, p_info in self.player_data.items() if p_info and p_info.character}
            world_state_copy = asdict(self.world)
        # Блокировка здесь освобождена!

        # Собираем сообщение, ИСПОЛЬЗУЯ СКОПИРОВАННЫЕ ДАННЫЕ
        full_state_update = {
            'world': world_state_copy,  # <-- ИСПОЛЬЗУЕМ КОПИЮ
            'players': player_states
        }
        
        message = {'type': MessageType.WORLD_STATE_UPDATE, 'data': full_state_update}
        
        logging.info(f"Preparing to broadcast WORLD_STATE_UPDATE message (containing {len(player_states)} players).")
        self.broadcast_message(message)


    def send_full_world_state(self, player_id: str):
        client_socket = self.connected_clients.get(player_id)
        player_info = self.player_data.get(player_id)
        character = player_info.character if player_info else None
        if not client_socket or not character: 
            logging.warning(f"Attempted to send full world state to non-existent client/character: {player_id}")
            return

        player_states = {}
        for pid, p_info in self.player_data.items():
            if p_info and p_info.character:
                player_states[pid] = asdict(p_info.character)

        message = {
            'type': MessageType.INITIAL_WORLD_STATE,
            'data': {
                'world': asdict(self.world),
                'player_character_id': player_id,
                'players': player_states
            }
        }
        logging.info(f"Sending INITIAL_WORLD_STATE to new client {player_id} ({character.name}).")
        try:
            send_json_message(client_socket, message, cls=EnhancedJSONEncoder)
            logging.info(f"INITIAL_WORLD_STATE sent successfully to {player_id}.")
        except Exception as e:
            logging.error(f"Error sending initial state to client {player_id}: {e}. Initiating cleanup.", exc_info=True)
            self._cleanup_client(player_id)


    def _cleanup_client(self, player_id: str):
        logging.info(f"Cleaning up client {player_id}.")
        with self.lock:
            # Проверяем наличие перед удалением
            if player_id in self.connected_clients:
                try:
                    # Попытка грациозно закрыть сокет
                    # conn.shutdown(socket.SHUT_RDWR) может быть причиной EWOULDBLOCK на неблокирующих сокетах
                    # или OSError если уже закрыт. Простой close() часто достаточен.
                    self.connected_clients[player_id].close()
                except OSError as e:
                    logging.debug(f"OSError during socket close for {player_id}: {e}")
                except Exception as e:
                    logging.warning(f"Unexpected error during socket close for {player_id}: {e}")
                finally:
                    del self.connected_clients[player_id]
                    logging.info(f"Socket for {player_id} closed and removed from connected_clients.")
            else:
                logging.debug(f"Client {player_id} not found in connected_clients during cleanup.")


            if player_id in self.player_data:
                player_info = self.player_data[player_id]
                character = player_info.character
                save_id = player_info.save_id
                
                try:
                    self.game_manager.save_character_progress(character, save_id)
                    logging.info(f"Player {character.name} (ID: {player_id}) disconnected. State saved.")
                except Exception as e:
                    logging.error(f"Error saving character {character.name} (ID: {player_id}) on disconnect: {e}", exc_info=True)
                finally:
                    del self.player_data[player_id]
                    logging.info(f"Player data for {player_id} removed from player_data.")
            else:
                logging.debug(f"Player {player_id} not found in player_data during cleanup.")
        
        # После cleanup, рассылаем обновление, чтобы другие клиенты знали об отключении
        # Если это последнее отключение, то список игроков будет пуст.
        self.broadcast_game_state_update() 
        logging.info(f"Cleanup of client {player_id} finished, state broadcasted.")

    def stop(self):
        if not self.running: # Предотвращаем двойной вызов
            return
            
        logging.info("Stopping server...")
        self.running = False
        
        # 1. Закрываем главный сокет, чтобы не принимать новые подключения
        if self.server_socket:
            self.server_socket.close()
            logging.info("Server listening socket closed.")
        
        # 2. Сохраняем прогресс всех игроков и закрываем их сокеты
        with self.lock:
            # Итерируем по копии, так как элементы будут удаляться
            for player_id, p_info in list(self.player_data.items()): 
                try:
                    if p_info and p_info.character:
                        char = p_info.character
                        save_id = p_info.save_id
                        self.game_manager.save_character_progress(char, save_id)
                        logging.info(f"Saved {char.name} on server shutdown.")
                    
                    # Закрываем клиентский сокет, если он еще открыт
                    client_socket = self.connected_clients.get(player_id)
                    if client_socket:
                        try:
                            # client_socket.shutdown(socket.SHUT_RDWR) # Может вызвать проблемы
                            client_socket.close()
                            logging.info(f"Client socket for {player_id} closed during server shutdown.")
                        except OSError as e:
                            logging.debug(f"OSError closing client socket {player_id} during shutdown: {e}")
                except Exception as e:
                    logging.critical(f"Unexpected error during client cleanup {player_id} on server stop: {e}", exc_info=True)
                finally:
                    if player_id in self.connected_clients:
                        del self.connected_clients[player_id]
                    if player_id in self.player_data:
                        del self.player_data[player_id]
            self.player_data.clear()
            self.connected_clients.clear()
            self.save_world_state()
        logging.info("Server stopped successfully.")

    def _handle_equip_item(self, character: Character, data: dict):
        item_id = data.get('item_id')
        if not item_id: return

        # Находим предмет в инвентаре персонажа
        item_to_equip = next((item for item in character.inventory if item.id == item_id), None)
        if not item_to_equip:
            logging.warning(f"Equip failed: Item {item_id} not in inventory for {character.name}.")
            return

        target_slot = item_to_equip.slot
        if target_slot in ["consumable", "misc"]: # Неэкипируемые типы
            logging.warning(f"Equip failed: Item {item_id} is not equippable.")
            return

        logging.info(f"Player {character.name} attempts to equip {item_to_equip.name} in slot {target_slot}.")

        # Если слот занят, снимаем старый предмет и кладем в инвентарь
        if target_slot in character.equipment:
            current_item = character.equipment.pop(target_slot)
            character.inventory.append(current_item)
            logging.info(f"Unequipped {current_item.name} to make space.")

        # Экипируем новый предмет
        character.inventory.remove(item_to_equip)
        character.equipment[target_slot] = item_to_equip
        
        # Рассылаем всем обновленное состояние
        self.broadcast_game_state_update()

    def _handle_unequip_item(self, character: Character, data: dict):
        slot = data.get('slot')
        if not slot: return

        if slot not in character.equipment:
            logging.warning(f"Unequip failed: Slot {slot} is empty for {character.name}.")
            return
            
        item_to_unequip = character.equipment.pop(slot)
        character.inventory.append(item_to_unequip)
        logging.info(f"Player {character.name} unequipped {item_to_unequip.name} from {slot}.")

        # Рассылаем всем обновленное состояние
        self.broadcast_game_state_update()

    def _handle_use_item(self, character: Character, data: dict):
        item_id = data.get('item_id')
        if not item_id: return

        item_to_use = next((item for item in character.inventory if item.id == item_id), None)
        if not item_to_use:
            logging.warning(f"Use item failed: Item {item_id} not in inventory for {character.name}.")
            return
            
        if item_to_use.slot != "consumable":
            logging.warning(f"Use item failed: Item {item_to_use.name} is not a consumable.")
            return

        # Используем RulesEngine для применения эффектов. Вместо log_callback передаем logging.info
        # GameManager нам здесь не нужен, так как RulesEngine уже есть в сервере.
        # Для этого нужно добавить self.rules_engine = RulesEngine() в __init__ сервера
        consumed = self.game_manager.rules_engine.apply_item_effects(character, item_to_use, logging.info)
        
        if consumed:
            character.inventory.remove(item_to_use)
            logging.info(f"Player {character.name} used {item_to_use.name}.")
            # Рассылаем всем обновленное состояние
            self.broadcast_game_state_update()
        else:
            logging.warning(f"Failed to apply effects for item {item_to_use.name} for player {character.name}.")

if __name__ == "__main__":

    WORLD_TO_RUN = "Тестовый мир" 

    dotenv_path = find_dotenv()
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)

    server = GameServer(world_name=WORLD_TO_RUN)
    try:
        server.start()
    except FileNotFoundError as e:
        logging.error(str(e))
        logging.error("Please create the world using the main menu first.")
    except Exception as e:
        logging.critical(f"An unhandled exception caused the server to crash: {e}", exc_info=True)
    finally:
        logging.info("Server process finished.")