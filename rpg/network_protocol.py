# rpg/network_protocol.py
import json
import struct # Для упаковки/распаковки длины сообщения
import socket
from typing import Optional, Any


# Типы сообщений
class MessageType:
    LOGIN = "login"                     # Клиент -> Сервер: запрос на подключение
    INITIAL_WORLD_STATE = "initial_world_state" # Сервер -> Клиент: первое полное состояние мира
    WORLD_STATE_UPDATE = "world_state_update" # Сервер -> Клиент: обновление состояния мира (позиции игроков и т.д.)
    PLAYER_MOVE = "player_move"         # Клиент -> Сервер: команда на передвижение
    CHAT_MESSAGE = "chat_message"       # Клиент <-> Сервер: сообщение в чате
    ERROR = "error"                     # Сервер -> Клиент: сообщение об ошибке
    EQUIP_ITEM = "equip_item"           # Клиент -> Сервер: запрос на экипировку предмета
    UNEQUIP_ITEM = "unequip_item"         # Клиент -> Сервер: запрос на снятие предмета
    USE_ITEM = "use_item"               # Клиент -> Сервер: запрос на использование предмета
    DISCARD_ITEM = "discard_item"       # Клиент -> Сервер: запрос на выбрасывание предмета
    PLAYER_ENTERED_POI = "player_entered_poi"
# --- Функции для отправки/получения сообщений ---

def send_json_message(sock: socket.socket, message: dict, cls: Optional[Any] = None):
    """Отправляет JSON-сообщение с 4-байтовым префиксом длины."""
    message_str = json.dumps(message, ensure_ascii=False, cls=cls)
    message_bytes = message_str.encode('utf-8')
    length_prefix = struct.pack('>I', len(message_bytes))
    
    # print(f"[SEND DEBUG] Sending {len(message_bytes)} bytes to {sock.fileno()} type={message.get('type')}")
    
    sock.sendall(length_prefix + message_bytes)


def _recv_all(sock: socket.socket, n: int) -> Optional[bytes]:
    """Вспомогательная функция для гарантированного чтения N байт."""
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            # Если sock.recv вернул пустую строку, это означает, что соединение закрыто
            # print(f"[RECV_ALL DEBUG] Connection closed prematurely while reading {n} bytes from {sock.fileno()}.")
            return None
        data += packet
    return data

def receive_json_message(sock: socket.socket) -> Optional[dict]:
    """Принимает JSON-сообщение, читая 4-байтовый префикс длины, используя _recv_all."""
    # print(f"[RECV DEBUG] Waiting for 4 bytes length from {sock.fileno()}...")
    raw_length = _recv_all(sock, 4) # <--- ИСПРАВЛЕНИЕ: Используем _recv_all
    if not raw_length:
        #rint(f"[RECV DEBUG] No raw_length. Connection closed by peer for {sock.fileno()}.")
        return None
    
    message_length = struct.unpack('>I', raw_length)[0]
    # print(f"[RECV DEBUG] Received length {message_length} from {sock.fileno()}.")
    
    # print(f"[RECV DEBUG] Requesting {message_length} bytes for message from {sock.fileno()}...")
    data_buffer = _recv_all(sock, message_length) # <--- ИСПРАВЛЕНИЕ: Используем _recv_all
    if not data_buffer:
        # print(f"[RECV DEBUG] Incomplete message. Connection closed prematurely for {sock.fileno()}.")
        return None
    
    # print(f"[RECV DEBUG] Full message received ({len(data_buffer)} bytes) from {sock.fileno()}.")
    return json.loads(data_buffer.decode('utf-8'))