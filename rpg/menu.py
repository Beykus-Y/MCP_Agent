# rpg/menu.py
import sys
import os
import json
from PyQt5 import QtWidgets, QtCore
from typing import Optional
import socket
import time

# Относительные импорты, так как все находится внутри пакета 'rpg'
from .game_manager import GameManager
from .character_creator import CharacterCreatorWindow
from .world.creation_dialog import WorldCreationDialog
from .world.generator import WorldGenerator
from .world.world_state import WorldState, Faction, PointOfInterest, NPC 
from .network_protocol import MessageType, send_json_message, receive_json_message
from .game.game_window import GameWindow
from .constants import PORT
WORLD_SAVES_DIR = os.path.join(os.path.dirname(__file__), 'saves', 'worlds')

# --- Класс-поток для генерации мира, чтобы не замораживать GUI ---
class WorldGeneratorWorker(QtCore.QObject):
    """Выполняет генерацию мира в отдельном потоке."""
    finished = QtCore.pyqtSignal(WorldState)
    error = QtCore.pyqtSignal(str)
    progress_update = QtCore.pyqtSignal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    @QtCore.pyqtSlot()
    def run(self):
        try:
            generator = WorldGenerator(
                progress_callback=lambda msg: self.progress_update.emit(msg)
            )
            world = generator.generate_new_world(self.params)
            self.finished.emit(world)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))


class NetworkClientWorker(QtCore.QObject):
    connected = QtCore.pyqtSignal(dict)
    disconnected = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    state_update = QtCore.pyqtSignal(dict)
    finished = QtCore.pyqtSignal()
    chat_message_received = QtCore.pyqtSignal(dict)
    
    def __init__(self, host: str, port: int, character_id: str):
        super().__init__()
        self.host = host
        self.port = port
        self.character_id = character_id
        self._socket: Optional[socket.socket] = None
        self._running = False

    @QtCore.pyqtSlot()
    def run(self):
        self._running = True
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # ИСПРАВЛЕНИЕ: Увеличен таймаут на сокете, но без time.sleep в обработчике таймаута
            self._socket.settimeout(1.0) # <--- Увеличиваем таймаут
            print(f"[Client Worker] Connecting to {self.host}:{self.port}...")
            self._socket.connect((self.host, self.port))
            print(f"[Client Worker] Connected to server. Sending login for character {self.character_id}...")

            login_message = {'type': MessageType.LOGIN, 'data': {'character_id': self.character_id}}
            send_json_message(self._socket, login_message)
            
            initial_state_msg = receive_json_message(self._socket)
            if initial_state_msg and initial_state_msg.get('type') == MessageType.INITIAL_WORLD_STATE:
                self.connected.emit(initial_state_msg['data'])
                print("[Client Worker] Received initial world state. Listening for updates...")
            elif initial_state_msg and initial_state_msg.get('type') == MessageType.ERROR:
                self.error.emit(f"Server login error: {initial_state_msg.get('data', 'Unknown error')}")
                return
            else:
                self.error.emit("Failed to receive initial world state or invalid message.")
                return

            # Цикл приема обновлений от сервера
            while self._running:
                try:
                    update_msg = receive_json_message(self._socket)
                    if not update_msg: # Соединение закрыто сервером
                        self.disconnected.emit("Server disconnected gracefully.")
                        break
                    
                    if update_msg['type'] == MessageType.WORLD_STATE_UPDATE:
                        # print(f"[Client Worker] Received WORLD_STATE_UPDATE. Emitting state_update signal.")
                        self.state_update.emit(update_msg['data'])
                    elif update_msg['type'] == MessageType.ERROR:
                        self.error.emit(f"Server error: {update_msg.get('data', 'Unknown error')}")
                    elif update_msg['type'] == MessageType.CHAT_MESSAGE:
                        self.chat_message_received.emit(update_msg['data'])
                    else:
                        print(f"[Client Worker] Received unknown message type: {update_msg.get('type')}")

                except socket.timeout: # Если таймаут, просто продолжаем цикл без sleep
                    # print("[Client Worker] Socket timeout, continuing loop.") # Отладочный лог, можно включить
                    continue
                except (OSError, ConnectionResetError) as e:
                    if isinstance(e, OSError) and e.errno == 10038: 
                        print("[Client Worker] Expected socket error during shutdown (10038). Exiting receive loop.")
                    elif isinstance(e, ConnectionResetError):
                        print("[Client Worker] Server reset connection. Exiting receive loop.")
                        self.disconnected.emit("Server closed connection.")
                    else:
                        print(f"[Client Worker] Unexpected network error during receive: {e}")
                        self.error.emit(f"Network error: {e}")
                    break
                except json.JSONDecodeError as e:
                    print(f"[Client Worker] JSONDecodeError during receive: {e}. Disconnecting.")
                    self.error.emit(f"Invalid JSON received from server: {e}")
                    break
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"[Client Worker] General error in receive loop: {e}")
                    self.error.emit(f"Unexpected receive error: {e}")
                    break

        except ConnectionRefusedError:
            self.error.emit(f"Connection refused. Is the server running on {self.host}:{self.port}?")
        except socket.timeout:
            self.error.emit("Connection timed out.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"Network error during initial connection: {e}")
        finally:
            self.disconnect()
            self.finished.emit()

    @QtCore.pyqtSlot(dict)
    def send_action(self, action: dict):
        """Отправляет действие на сервер."""
        if self._socket and self._running:
            try:
                send_json_message(self._socket, action)
            except OSError as e:
                print(f"[Client Worker] OSError during send: {e}")
                self.error.emit(f"Send error: {e}")
                self.disconnect()
            except Exception as e:
                self.error.emit(f"Failed to send action: {e}")
                self.disconnect()
        else:
            print("[Client Worker] Not connected or worker not running, cannot send action.")

    def disconnect(self):
        """Закрывает соединение."""
        if not self._running:
            return
        
        self._running = False

        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
                self._socket.close()
            except OSError as e:
                print(f"[Client Worker] Error during socket shutdown/close: {e}")
            finally:
                self._socket = None
        print("[Client Worker] Disconnected.")

class MainMenuWindow(QtWidgets.QWidget):
    """
    Главное меню RPG.
    Позволяет загружать сохранения персонажей или создавать новые миры.
    """
    def __init__(self):
        super().__init__()
        self.game_manager = GameManager()
        self.creator_window = None
        self.thread = None
        self.worker = None

        self.setWindowTitle("Ролевая игра - Главное меню")
        self.setMinimumSize(400, 300)
        
        self.setup_ui()
        self.populate_saves_list()

    def setup_ui(self):
        """Создает и компонует все виджеты окна."""
        main_layout = QtWidgets.QVBoxLayout(self)

        saves_group = QtWidgets.QGroupBox("Сохраненные персонажи")
        saves_layout = QtWidgets.QVBoxLayout()
        self.saves_list_widget = QtWidgets.QListWidget()
        # --- ИСПРАВЛЕНИЕ: Подключаем правильный метод ---
        self.saves_list_widget.itemDoubleClicked.connect(self.load_selected_game_local)
        saves_layout.addWidget(self.saves_list_widget)
        saves_group.setLayout(saves_layout)

        network_group = QtWidgets.QGroupBox("Сетевая игра")
        network_layout = QtWidgets.QFormLayout(network_group)
        self.ip_input = QtWidgets.QLineEdit("127.0.0.1")
        self.port_input = QtWidgets.QLineEdit(str(PORT)) # Используем константу порта из rpg_server.py
        network_layout.addRow("IP Адрес:", self.ip_input)
        network_layout.addRow("Порт:", self.port_input)
        
        self.connect_button = QtWidgets.QPushButton("Подключиться к игре")
        self.connect_button.clicked.connect(self.connect_to_server)
        network_layout.addWidget(self.connect_button)
        network_group.setLayout(network_layout)

        button_layout = QtWidgets.QHBoxLayout()
        self.load_button = QtWidgets.QPushButton("Загрузить игру (локально)") # Переименовано
        self.load_button.clicked.connect(self.load_selected_game_local) # Новая функция для локальной загрузки
        
        self.new_world_button = QtWidgets.QPushButton("Создать новый мир")
        self.new_world_button.clicked.connect(self.create_new_world)
        
        self.new_game_button = QtWidgets.QPushButton("Новый персонаж")
        self.new_game_button.clicked.connect(self.open_character_creator)
        
        button_layout.addStretch()
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.new_world_button)
        button_layout.addWidget(self.new_game_button)

        main_layout.addWidget(saves_group)
        main_layout.addWidget(network_group) # <-- ДОБАВЛЯЕМ СЕТЕВУЮ ГРУППУ
        main_layout.addLayout(button_layout)


    def load_selected_game_local(self):
        """Загружает персонажа и мир для локальной игры (старый функционал)."""
        selected_item = self.saves_list_widget.currentItem()
        if not selected_item or selected_item.data(QtCore.Qt.UserRole) is None:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Пожалуйста, выберите персонажа для загрузки.")
            return
        
        char_save_id = selected_item.data(QtCore.Qt.UserRole)
        
        character = self.game_manager.load_character(char_save_id)
        if not character:
            QtWidgets.QMessageBox.critical(self, "Ошибка загрузки", f"Не удалось загрузить данные персонажа из {char_save_id}.")
            return
            
        world_filepath = self._select_world_dialog()
        if not world_filepath:
            return 

        world = self._load_world_from_file(world_filepath)
        if not world:
            QtWidgets.QMessageBox.critical(self, "Ошибка загрузки", f"Не удалось загрузить или прочитать файл мира:\n{world_filepath}")
            return
            
        self.game_window = GameWindow(
            world=world,
            character=character,
            save_id=char_save_id,
            is_online=False, # Это главное: мы не онлайн
            network_worker=None, # Нет воркера для оффлайн игры
            initial_player_id=None, # Нет серверного ID
            initial_player_data=None # Нет данных о других игроках
        )
        self.game_window.show()
        self.close()

    # --- НОВАЯ ФУНКЦИЯ: Подключение к серверу ---
    def connect_to_server(self):
        selected_item = self.saves_list_widget.currentItem()
        if not selected_item or selected_item.data(QtCore.Qt.UserRole) is None:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Пожалуйста, выберите персонажа для подключения.")
            return
        
        char_save_id = selected_item.data(QtCore.Qt.UserRole)
        host = self.ip_input.text().strip()
        port_str = self.port_input.text().strip()

        if not host or not port_str:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Введите IP адрес и порт сервера.")
            return

        try:
            port = int(port_str)
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Порт должен быть числом.")
            return

        self.connect_button.setEnabled(False)
        self.connect_button.setText("Подключение...")

        self.network_thread = QtCore.QThread()
        self.network_worker = NetworkClientWorker(host, port, char_save_id)
        self.network_worker.moveToThread(self.network_thread)

        self.network_thread.started.connect(self.network_worker.run)
        
        # ИСПРАВЛЕНИЕ: Сохраняем ссылку на соединение, чтобы можно было отключить
        self._on_server_connected_slot = lambda initial_state: self.on_server_connected(initial_state)
        self.network_worker.connected.connect(self._on_server_connected_slot) # <--- ИСПРАВЛЕНИЕ

        self.network_worker.disconnected.connect(self.on_server_disconnected)
        self.network_worker.error.connect(self.on_network_error)

        self.network_worker.finished.connect(self.network_thread.quit)
        self.network_worker.finished.connect(self.network_worker.deleteLater)
        self.network_thread.finished.connect(self.network_thread.deleteLater)

        self.network_thread.start()

    @QtCore.pyqtSlot(dict)
    def on_server_connected(self, initial_state: dict):
        print("[MainMenuWindow] on_server_connected called.") # Добавили лог для проверки

        # ИСПРАВЛЕНИЕ: Отключаем сигнал сразу после вызова
        try:
            self.network_worker.connected.disconnect(self._on_server_connected_slot)
        except TypeError: # На случай, если сигнал уже был отключен или не был подключен
            pass

        self.connect_button.setText("Подключиться к игре")
        self.connect_button.setEnabled(True)

        world_data = initial_state['world']
        player_character_id = initial_state['player_character_id']
        all_players_data = initial_state['players']
        
        world = WorldState.from_dict(world_data)
        
        self.game_window = GameWindow(
            world=world,
            character=None,
            save_id=self.saves_list_widget.currentItem().data(QtCore.Qt.UserRole),
            is_online=True,
            network_worker=self.network_worker,
            network_thread=self.network_thread,
            initial_player_id=player_character_id,
            initial_player_data=all_players_data
        )

        self.network_thread = None
        self.network_worker = None


        self.game_window.show()
        self.close()

    @QtCore.pyqtSlot(str)
    def on_server_disconnected(self, reason: str):
        self.connect_button.setText("Подключиться к игре")
        self.connect_button.setEnabled(True)
        QtWidgets.QMessageBox.warning(self, "Отключено", f"Отключено от сервера: {reason}")
        # Если GameWindow была открыта, ее тоже нужно закрыть
        if self.game_window and self.game_window.isVisible():
            self.game_window.close() # Или можно вызвать game_window.handle_server_disconnect()
            self.game_window = None

    @QtCore.pyqtSlot(str)
    def on_network_error(self, message: str):
        self.connect_button.setText("Подключиться к игре")
        self.connect_button.setEnabled(True)
        QtWidgets.QMessageBox.critical(self, "Ошибка сети", message)
        # Аналогично on_server_disconnected, если GameWindow открыта
        if self.game_window and self.game_window.isVisible():
            self.game_window.close()
            self.game_window = None


    def populate_saves_list(self):
        """Запрашивает список сохранений и заполняет виджет QListWidget."""
        self.saves_list_widget.clear()
        saves = self.game_manager.get_save_list()
        if not saves:
            item = QtWidgets.QListWidgetItem("Персонажей не найдено. Создайте нового.")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
            self.saves_list_widget.addItem(item)
            self.load_button.setEnabled(False)
            return

        self.load_button.setEnabled(True)
        for save in saves:
            item_text = f"{save['id']} - {save['character_name']}"
            item = QtWidgets.QListWidgetItem(item_text)
            item.setData(QtCore.Qt.UserRole, save['id'])
            self.saves_list_widget.addItem(item)

    def open_character_creator(self):
        """Открывает модальное окно создания персонажа."""
        self.creator_window = CharacterCreatorWindow(parent=self)
        self.creator_window.character_created.connect(self.on_character_creation_success)
        self.creator_window.show()

    def on_character_creation_success(self):
        """Слот, который вызывается после успешного создания и сохранения персонажа."""
        print("Персонаж успешно создан, обновляем список сохранений.")
        self.populate_saves_list()

    def create_new_world(self):
        """Открывает диалог параметров и запускает генерацию мира в потоке."""
        dialog = WorldCreationDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            params = dialog.get_parameters()
            if not params: return
            
            self.progress = QtWidgets.QProgressDialog("Запуск генератора...", "Отмена", 0, 0, self)
            self.progress.setWindowModality(QtCore.Qt.WindowModal)
            self.progress.setMinimumDuration(0)
            self.progress.show()
            
            self.thread = QtCore.QThread()
            self.worker = WorldGeneratorWorker(params)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.on_world_generation_finished)
            self.worker.error.connect(self.on_world_generation_error)
            self.worker.progress_update.connect(self.progress.setLabelText)
            self.progress.canceled.connect(self.thread.quit)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.thread.start()

    def on_world_generation_finished(self, world: WorldState):
        """Слот, который вызывается после успешной генерации мира."""
        self.progress.close()
        try:
            generator = WorldGenerator()
            filepath = generator.save_world(world)
            if filepath:
                QtWidgets.QMessageBox.information(self, "Успех", f"Мир '{world.world_name}' был сгенерирован и сохранен в:\n{filepath}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка сохранения", f"Мир сгенерирован, но не удалось его сохранить:\n{e}")
            
    def on_world_generation_error(self, err_msg: str):
        """Слот для обработки ошибок генерации."""
        self.progress.close()
        QtWidgets.QMessageBox.critical(self, "Ошибка генерации", f"Произошла ошибка при создании мира:\n{err_msg}")

    # --- ИСПРАВЛЕНИЕ: Переименованный метод ---
    def load_selected_game(self):
        """Главный метод для старта игры с существующим персонажем."""
        selected_item = self.saves_list_widget.currentItem()
        if not selected_item or selected_item.data(QtCore.Qt.UserRole) is None:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Пожалуйста, выберите персонажа для загрузки.")
            return
        
        char_save_id = selected_item.data(QtCore.Qt.UserRole)
        
        # Шаг 1: Загружаем данные персонажа
        character = self.game_manager.load_character(char_save_id)
        if not character:
            QtWidgets.QMessageBox.critical(self, "Ошибка загрузки", f"Не удалось загрузить данные персонажа из {char_save_id}.")
            return
            
        # Шаг 2: Предлагаем пользователю выбрать мир
        world_filepath = self._select_world_dialog()
        if not world_filepath:
            return # Пользователь нажал "Отмена"

        # Шаг 3: Загружаем данные мира из файла
        world = self._load_world_from_file(world_filepath)
        if not world:
            QtWidgets.QMessageBox.critical(self, "Ошибка загрузки", f"Не удалось загрузить или прочитать файл мира:\n{world_filepath}")
            return
            
        # Шаг 4: Запускаем игровое окно
        self.game_window = GameWindow(character, world, char_save_id)
        self.game_window.show()
        self.close()

    def _select_world_dialog(self) -> Optional[str]:
        """Открывает стандартный диалог выбора файла для мира."""
        if not os.path.exists(WORLD_SAVES_DIR):
            os.makedirs(WORLD_SAVES_DIR)
            
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Выберите файл мира для загрузки",
            WORLD_SAVES_DIR,
            "Файлы мира (*.world);;Все файлы (*)"
        )
        return filepath if filepath else None
        
    def _load_world_from_file(self, filepath: str) -> Optional[WorldState]:
        """Читает JSON из файла и воссоздает объект WorldState."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # ИСПРАВЛЕНИЕ: Используем WorldState.from_dict для десериализации
            return WorldState.from_dict(data)
        except Exception as e:
            print(f"Ошибка при загрузке мира из файла {filepath}: {e}")
            import traceback
            traceback.print_exc()
            return None

if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))
    app = QtWidgets.QApplication(sys.argv)
    window = MainMenuWindow()
    window.show()
    sys.exit(app.exec_())