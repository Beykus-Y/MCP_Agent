# mcp_rpg.py (Версия 4.4 - Финальная исправленная)
import os
import json
import sqlite3
import re 
import random
import threading
import time
from flask import Flask, request, jsonify
from waitress import serve

# --- Конфигурация ---
DB_FILE = "rpg_database.db"
ACTIVE_SAVE_FILE = "rpg_active_save.json"
SIMULATION_TICK_RATE = 300
app = Flask(__name__)

stop_simulation_event = threading.Event()

# --- Вспомогательные функции ---
def get_db_connection():
    """
    Вспомогательная функция для получения соединения с БД.
    check_same_thread=False необходимо для работы с БД из разных потоков (основного и симуляции).
    """
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_active_save_id(params):
    """
    Определяет ID активной игры. Приоритет:
    1. ID, явно переданный в параметрах.
    2. ID, сохраненный в файле ACTIVE_SAVE_FILE.
    """
    if params and "save_id" in params and params["save_id"] is not None:
        return params["save_id"]
    try:
        if os.path.exists(ACTIVE_SAVE_FILE):
            with open(ACTIVE_SAVE_FILE, 'r') as f:
                data = json.load(f)
                return data.get("active_save_id")
    except (IOError, json.JSONDecodeError):
        return None
    return None

# --- Инициализация и Симуляция ---
def initialize_database():
    """
    Создает все необходимые таблицы в базе данных, если они еще не существуют.
    Вызывается один раз при старте сервера.
    """
    print(f"[*] Проверка и инициализация базы данных '{DB_FILE}'...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Добавлено UNIQUE ограничение для game_state
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS game_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        UNIQUE(save_id, key),
        FOREIGN KEY (save_id) REFERENCES saves (id) ON DELETE CASCADE
    )""")
    
    # Остальные таблицы без изменений...
    cursor.execute("CREATE TABLE IF NOT EXISTS saves (id INTEGER PRIMARY KEY, name TEXT NOT NULL, last_saved TEXT NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS characters (id INTEGER PRIMARY KEY, save_id INTEGER NOT NULL, name TEXT NOT NULL, is_player BOOLEAN, hp INTEGER, max_hp INTEGER, location_x INTEGER, location_y INTEGER, attributes TEXT, FOREIGN KEY (save_id) REFERENCES saves (id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, character_id INTEGER NOT NULL, item_name TEXT NOT NULL, quantity INTEGER, description TEXT, FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS status_effects (id INTEGER PRIMARY KEY, character_id INTEGER NOT NULL, effect_name TEXT NOT NULL, duration INTEGER, FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY, save_id INTEGER NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL, details TEXT, UNIQUE(save_id, x, y), FOREIGN KEY (save_id) REFERENCES saves (id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS quests (id INTEGER PRIMARY KEY, save_id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT, status TEXT, objectives TEXT, FOREIGN KEY (save_id) REFERENCES saves (id) ON DELETE CASCADE)")
    
    conn.commit()
    conn.close()
    print("[OK] База данных готова к работе.")

def world_simulation_loop():
    """
    Эта функция выполняется в отдельном потоке и симулирует жизнь мира.
    """
    print("[World Sim] Поток симуляции запущен.")
    while not stop_simulation_event.is_set():
        try:
            stop_simulation_event.wait(SIMULATION_TICK_RATE)
            if stop_simulation_event.is_set(): break
            print(f"[World Sim] Тик симуляции мира в {time.ctime()}...")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM saves")
            saves = [row['id'] for row in cursor.fetchall()]
            for save_id in saves:
                weather_options = ["Ясно", "Облачно", "Легкий дождь", "Туман"]
                new_weather = random.choice(weather_options)
                cursor.execute("INSERT INTO game_state (save_id, key, value) VALUES (?, 'weather', ?) ON CONFLICT(save_id, key) DO UPDATE SET value=excluded.value", (save_id, new_weather))
                cursor.execute("SELECT id, location_x, location_y FROM characters WHERE save_id = ? AND is_player = 0 ORDER BY RANDOM() LIMIT 1", (save_id,)); npc = cursor.fetchone()
                if npc:
                    move_x, move_y = random.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
                    new_x, new_y = npc['location_x'] + move_x, npc['location_y'] + move_y
                    cursor.execute("UPDATE characters SET location_x = ?, location_y = ? WHERE id = ?", (new_x, new_y, npc['id']))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[World Sim] Ошибка в потоке симуляции: {e}")
            time.sleep(60)

# --- Класс ошибки ---
class JsonRpcError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message
def make_error_response(id_, code, message):
    """Форматирует ответ с ошибкой по стандарту JSON-RPC."""
    return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})

def make_success_response(id_, result):
    """Форматирует успешный ответ по стандарту JSON-RPC."""
    return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})

# --- Реализация методов ---
def set_active_game(params):
    save_id = params.get("save_id")
    if save_id is None: raise JsonRpcError(-32602, "Необходим параметр save_id.")
    with open(ACTIVE_SAVE_FILE, 'w') as f: json.dump({"active_save_id": save_id}, f)
    return {"status": "ok", "message": f"Игра с ID {save_id} теперь активна."}

def new_game(params):
    game_name = params.get("name")
    if not game_name: raise JsonRpcError(-32602, "Параметр 'name' обязателен.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO saves (name, last_saved) VALUES (?, datetime('now', 'localtime'))", (game_name,))
    new_id = cursor.lastrowid; conn.commit(); conn.close()
    set_active_game({"save_id": new_id})
    return {"status": "ok", "save_id": new_id, "message": f"Новая игра '{game_name}' создана и стала активной. ID: {new_id}."}

def list_saves(params):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id, name, last_saved FROM saves ORDER BY last_saved DESC")
    saves = [dict(row) for row in cursor.fetchall()]; conn.close()
    return {"status": "ok", "saves": saves} if saves else {"status": "no_saves_found", "saves": []}

def get_active_game(params):
    save_id = get_active_save_id({})
    if save_id is None: return {"status": "no_active_game"}
    return {"status": "ok", "active_save_id": save_id}

### ИСПРАВЛЕННЫЕ ФУНКЦИИ, ИСПОЛЬЗУЮЩИЕ АКТИВНУЮ ИГРУ ###
def create_character(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру. Укажите save_id или используйте set_active_game.")
    required = ['name', 'is_player', 'attributes']
    if not all(k in params for k in required): raise JsonRpcError(-32602, f"Отсутствуют обязательные параметры: {required}")
    attributes_json = json.dumps(params['attributes'])
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO characters (save_id, name, is_player, hp, max_hp, location_x, location_y, attributes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (save_id, params['name'], params['is_player'], params.get('hp', 10), params.get('max_hp', 10), params.get('location_x', 0), params.get('location_y', 0), attributes_json)
    )
    new_id = cursor.lastrowid; conn.commit(); conn.close()
    return {"status": "ok", "character_id": new_id}

def update_location(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    details_json = json.dumps(params['details'])
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO locations (save_id, x, y, details) VALUES (?, ?, ?, ?) ON CONFLICT(save_id, x, y) DO UPDATE SET details=excluded.details", (save_id, params['x'], params['y'], details_json))
    conn.commit(); conn.close()
    return {"status": "ok"}

def add_quest(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    objectives_list = [{"text": obj, "done": False} for obj in params['objectives']]
    objectives_json = json.dumps(objectives_list)
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO quests (save_id, title, description, objectives) VALUES (?, ?, ?, ?)", (save_id, params['title'], params.get('description', ''), objectives_json))
    quest_id = cursor.lastrowid; conn.commit(); conn.close()
    return {"status": "ok", "quest_id": quest_id}

def get_location_details(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT details FROM locations WHERE save_id = ? AND x = ? AND y = ?", (save_id, params['x'], params['y']))
    row = cursor.fetchone(); conn.close()
    if not row: return {"status": "not_explored"}
    return {"status": "ok", "details": json.loads(row['details'])}

def get_quest_journal(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, status, objectives FROM quests WHERE save_id = ?", (save_id,))
    quests_raw = cursor.fetchall(); conn.close()
    quests = [dict(q) for q in quests_raw]
    for q in quests: q['objectives'] = json.loads(q['objectives'])
    return {"quests": quests}

def generate_random_encounter(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    # Передаем save_id в get_location_details
    location_details = get_location_details({'save_id': save_id, 'x': params['x'], 'y': params['y']})
    terrain = location_details.get("details", {}).get("terrain", "plains")
    encounters = {
        "forest": ["Вы натыкаетесь на поляну со светящимися грибами.", "Из кустов на вас смотрит олень."],
        "plains": ["Стадо бизонов медленно пересекает равнину.", "Вы находите старый, заброшенный колодец."],
        "fort": ["В коридоре вы замечаете следы старой битвы.", "Сквозняк задувает ваш факел."]
    }
    description = random.choice(encounters.get(terrain.lower(), encounters["plains"]))
    return {"status": "ok", "encounter_description": description}

# Функции, которые не зависят от save_id или работают с character_id
def get_character_details(params):
    char_id = params.get("character_id")
    if char_id is None: raise JsonRpcError(-32602, "Отсутствует character_id.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM characters WHERE id = ?", (char_id,)); char_data = cursor.fetchone(); conn.close()
    if not char_data: raise JsonRpcError(-32000, f"Персонаж с ID {char_id} не найден.")
    result = dict(char_data); result['attributes'] = json.loads(result['attributes']) if result['attributes'] else {}
    return result

def update_character_attributes(params):
    char_id = params.get("character_id"); updates = params.get("attributes_to_update")
    if char_id is None or updates is None: raise JsonRpcError(-32602, "Отсутствуют character_id или attributes_to_update.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT attributes FROM characters WHERE id = ?", (char_id,)); row = cursor.fetchone()
    if not row: conn.close(); raise JsonRpcError(-32000, f"Персонаж с ID {char_id} не найден.")
    current_attributes = json.loads(row['attributes']) if row['attributes'] else {}; current_attributes.update(updates)
    new_attributes_json = json.dumps(current_attributes)
    cursor.execute("UPDATE characters SET attributes = ? WHERE id = ?", (new_attributes_json, char_id)); conn.commit(); conn.close()
    return {"status": "ok"}

def add_item_to_inventory(params):
    char_id = params.get("character_id"); item_name = params.get("item_name")
    if char_id is None or item_name is None: raise JsonRpcError(-32602, "Отсутствуют character_id или item_name.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO inventory (character_id, item_name, quantity, description) VALUES (?, ?, ?, ?)",(char_id, item_name, params.get('quantity', 1), params.get('description', '')))
    conn.commit(); conn.close()
    return {"status": "ok"}

def get_inventory(params):
    char_id = params.get("character_id")
    if char_id is None: raise JsonRpcError(-32602, "Отсутствует character_id.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT item_name, quantity, description FROM inventory WHERE character_id = ?", (char_id,))
    inventory = [dict(row) for row in cursor.fetchall()]; conn.close()
    return {"inventory": inventory}

def move_character(params):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE characters SET location_x = ?, location_y = ? WHERE id = ?", (params['new_x'], params['new_y'], params['character_id']))
    conn.commit(); conn.close()
    return {"status": "ok"}

def update_quest_status(params):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE quests SET status = ? WHERE id = ?", (params['status'], params['quest_id']))
    conn.commit(); conn.close()
    return {"status": "ok"}

def roll_dice(params):
    expression = params['expression'].lower().strip()
    match = re.match(r'(\d+)d(\d+)([\+\-]\d+)?', expression)
    if not match: raise JsonRpcError(-32602, "Неверный формат броска. Пример: '1d20' или '3d6+5'.")
    num_dice, die_type, modifier = match.groups(); num_dice, die_type = int(num_dice), int(die_type)
    modifier = int(modifier) if modifier else 0
    rolls = [random.randint(1, die_type) for _ in range(num_dice)]; total = sum(rolls) + modifier
    return {"rolls": rolls, "modifier": modifier, "total": total}

def suggest_mcp_action(params):
    suggestion = params.get("suggestion"); details = params.get("details")
    if not suggestion or not details: raise JsonRpcError(-32602, "Отсутствуют suggestion или details.")
    return {"status": "suggestion_provided", "message": "Пожалуйста, выполни следующее действие.", "suggested_action": suggestion, "suggested_params": details}

def get_player_character_info(params):
    """Находит персонажа игрока в активной игре и возвращает его данные."""
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Активная игра не найдена.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM characters WHERE save_id = ? AND is_player = 1", (save_id,))
    player_data = cursor.fetchone()
    if not player_data: raise JsonRpcError(-32000, "Персонаж игрока не найден в этой игре.")
    result = dict(player_data)
    result['attributes'] = json.loads(result['attributes']) if result['attributes'] else {}
    return result

def get_player_location(params):
    """Комбинированное действие: находит игрока и возвращает детали его текущей локации."""
    player_data = get_player_character_info(params)
    location_params = {"save_id": player_data["save_id"], "x": player_data["location_x"], "y": player_data["location_y"]}
    return get_location_details(location_params)

def explore_location(params):
    char_id = params.get("character_id"); new_x = params.get("new_x"); new_y = params.get("new_y")
    if char_id is None or new_x is None or new_y is None: raise JsonRpcError(-32602, "Необходимы параметры: character_id, new_x, new_y.")
    move_character(params)
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    location_data = get_location_details({"save_id": save_id, "x": new_x, "y": new_y})
    if location_data["status"] == "not_explored":
        return {"status": "moved_to_unexplored_area", "message": "Персонаж перемещен. Эта область не исследована. Опиши ее и вызови 'update_location'."}
    else:
        return {"status": "moved_to_explored_area", "details": location_data["details"]}
    
def get_player_status(params):
    """
    Возвращает ПОЛНУЮ сводку по персонажу игрока за один вызов:
    детали персонажа, его инвентарь и информацию о его текущей локации.
    """
    # 1. Получаем инфо о персонаже
    player_info = get_player_character_info(params)
    player_id = player_info.get("id")
    
    # 2. Получаем инвентарь
    inventory_info = get_inventory({"character_id": player_id})
    
    # 3. Получаем инфо о локации
    location_info = get_player_location(params)
    
    return {
        "character_details": player_info,
        "inventory": inventory_info.get("inventory", []),
        "location": location_info
    }

def delete_save(params):
    """Удаляет игру и все связанные с ней данные из БД."""
    save_id = params.get("save_id")
    if save_id is None:
        raise JsonRpcError(-32602, "Необходим параметр save_id для удаления.")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Благодаря "ON DELETE CASCADE", удаление записи из `saves`
    # автоматически удалит все связанные записи в других таблицах.
    cursor.execute("DELETE FROM saves WHERE id = ?", (save_id,))
    # Проверяем, была ли удалена строка
    if cursor.rowcount == 0:
        conn.close()
        raise JsonRpcError(-32000, f"Игра с ID {save_id} не найдена.")
    
    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"Игра с ID {save_id} и все ее данные были удалены."}

def set_global_state(params):
    """Устанавливает или обновляет глобальную переменную для активной игры."""
    save_id = get_active_save_id(params)
    if save_id is None:
        raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    
    key = params.get("key")
    value = params.get("value")
    if key is None or value is None:
        raise JsonRpcError(-32602, "Необходимы параметры 'key' и 'value'.")

    conn = get_db_connection()
    cursor = conn.cursor()
    # Используем UPSERT для удобства
    cursor.execute(
        """INSERT INTO game_state (save_id, key, value) VALUES (?, ?, ?)
           ON CONFLICT(save_id, key) DO UPDATE SET value=excluded.value""",
        (save_id, key, str(value)) # Сохраняем значение как строку
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}

def find_character_by_name(params):
    """Ищет персонажей по имени в активной игре."""
    save_id = get_active_save_id(params)
    if save_id is None:
        raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    
    name_to_find = params.get("name")
    if not name_to_find:
        raise JsonRpcError(-32602, "Необходим параметр 'name'.")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, is_player FROM characters WHERE save_id = ? AND name LIKE ?", (save_id, f"%{name_to_find}%"))
    characters = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"characters_found": characters}

RPG_FUNCTIONS = [
    {
        "name": "get_player_status",
        "description": "Самый главный инструмент для получения полной информации о состоянии игрока. Используй его, если пользователь спрашивает 'где я?', 'что я вижу?', 'что у меня есть?' или просит общую сводку. Возвращает всё: статы, инвентарь и информацию о локации.",
        "parameters": {}
    },
    {"name": "get_player_location", "description": "Самый быстрый способ узнать, где находится игрок и что его окружает. Используй, если пользователь спрашивает 'где я?' или 'что я вижу?'.", "parameters": {}},
    {"name": "get_player_character_info", "description": "Получает полную информацию о персонаже игрока (статы, HP, ID) в текущей активной игре.", "parameters": {}},
    {"name": "explore_location", "description": "Основное действие для перемещения. Перемещает персонажа и сообщает, что находится в новой локации.", "parameters": {"type": "object", "properties": {"character_id": {"type": "integer"}, "new_x": {"type": "integer"}, "new_y": {"type": "integer"}, "save_id": {"type": "integer", "description": "ID игры, необязателен, если игра активна."}}, "required": ["character_id", "new_x", "new_y"]}},
    {"name": "new_game", "description": "Начинает новую игру и автоматически делает ее активной.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "list_saves", "description": "Показывает список всех сохраненных игр.", "parameters": {}},
    {"name": "set_active_game", "description": "Выбирает игру для продолжения, делая ее активной для всех последующих команд.", "parameters": {"type": "object", "properties": {"save_id": {"type": "integer"}}, "required": ["save_id"]}},
    {"name": "get_active_game", "description": "Возвращает ID текущей активной игры.", "parameters": {}},
    {"name": "create_character", "description": "Создает персонажа в активной игре. save_id необязателен.", "parameters": {"type": "object", "properties": {"save_id": {"type": "integer"}, "name": {"type": "string"}, "is_player": {"type": "boolean"}, "attributes": {"type": "object"}}, "required": ["name", "is_player", "attributes"]}},
    {"name": "update_location", "description": "Обновляет локацию в активной игре. save_id необязателен.", "parameters": {"type": "object", "properties": {"save_id": {"type": "integer"}, "x": {"type": "integer"}, "y": {"type": "integer"}, "details": {"type": "object"}}, "required": ["x", "y", "details"]}},
    {"name": "add_quest", "description": "Добавляет квест в активную игру. save_id необязателен.", "parameters": {"type": "object", "properties": {"save_id": {"type": "integer"}, "title": {"type": "string"}, "description": {"type": "string"}, "objectives": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "objectives"]}},
    {"name": "get_character_details", "description": "Получает полную информацию о персонаже по ID.", "parameters": {"type": "object", "properties": {"character_id": {"type": "integer"}}, "required": ["character_id"]}},
    {"name": "update_character_attributes", "description": "Обновляет атрибуты персонажа.", "parameters": {"type": "object", "properties": {"character_id": {"type": "integer"}, "attributes_to_update": {"type": "object"}}, "required": ["character_id", "attributes_to_update"]}},
    {"name": "add_item_to_inventory", "description": "Добавляет предмет в инвентарь персонажа.", "parameters": {"type": "object", "properties": {"character_id": {"type": "integer"}, "item_name": {"type": "string"}}, "required": ["character_id", "item_name"]}},
    {"name": "get_inventory", "description": "Возвращает инвентарь персонажа.", "parameters": {"type": "object", "properties": {"character_id": {"type": "integer"}}, "required": ["character_id"]}},
    {"name": "get_location_details", "description": "Получает информацию о локации по ее координатам в активной игре. save_id необязателен.", "parameters": {"type": "object", "properties": {"save_id": {"type": "integer"}, "x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}},
    {"name": "move_character", "description": "Перемещает персонажа в новую локацию.", "parameters": {"type": "object", "properties": {"character_id": {"type": "integer"}, "new_x": {"type": "integer"}, "new_y": {"type": "integer"}}, "required": ["character_id", "new_x", "new_y"]}},
    {"name": "get_quest_journal", "description": "Возвращает список всех квестов в активной игре. save_id необязателен.", "parameters": {"type": "object", "properties": {"save_id": {"type": "integer"}}}},
    {"name": "update_quest_status", "description": "Обновляет статус квеста.", "parameters": {"type": "object", "properties": {"quest_id": {"type": "integer"}, "status": {"type": "string", "enum": ["active", "completed", "failed"]}}, "required": ["quest_id", "status"]}},
    {"name": "roll_dice", "description": "Бросает кости по формуле.", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}},
    {"name": "generate_random_encounter", "description": "Создает случайное событие в локации в активной игре. save_id необязателен.", "parameters": {"type": "object", "properties": {"save_id": {"type": "integer"}, "x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}},
    {"name": "suggest_mcp_action", "description": "Предлагает ИИ выполнить действие с помощью ДРУГОГО MCP.", "parameters": {"type": "object", "properties": {"suggestion": {"type": "string"}, "details": {"type": "object"}}, "required": ["suggestion", "details"]}},
    {
        "name": "delete_save",
        "description": "Безвозвратно удаляет сохранение игры и всех связанных с ней персонажей, квесты и локации.",
        "parameters": {"type": "object", "properties": {"save_id": {"type": "integer"}}, "required": ["save_id"]}
    },
    {
        "name": "set_global_state",
        "description": "Устанавливает глобальную переменную для текущей активной игры. Используй это для установки времени, погоды или других правил мира.",
        "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "Название переменной, например, 'current_time'."}, "value": {"type": "string", "description": "Значение переменной."}}, "required": ["key", "value"]}
    },
    {
        "name": "find_character_by_name",
        "description": "Ищет персонажа по имени в активной игре и возвращает список совпадений с их ID.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    },
]

# --- Словарь методов ---
METHODS = {func['name']: globals()[func['name']] for func in RPG_FUNCTIONS}

# --- Эндпоинты Flask ---
@app.route("/functions")
def get_functions_route(): return jsonify(RPG_FUNCTIONS)

@app.route("/mcp", methods=["POST"])
def mcp_entrypoint():
    try:
        req = request.get_json(force=True)
        method = req.get('method')
        if not method or method not in METHODS: raise JsonRpcError(-32601, f"Метод '{method}' не найден.")
        result = METHODS[method](req.get('params', {}))
        return make_success_response(req.get('id'), result)
    except Exception as e:
        code = getattr(e, 'code', -32603); msg = getattr(e, 'message', str(e))
        return make_error_response(req.get('id'), code, msg), 500

if __name__ == "__main__":
    initialize_database()
    simulation_thread = threading.Thread(target=world_simulation_loop, daemon=True)
    simulation_thread.start()
    port = int(os.getenv("MCP_RPG_PORT", 8008))
    print(f"[*] MCP_RPG (Игровой движок) запускается на порту: {port} через Waitress.")
    try:
        serve(app, host="0.0.0.0", port=port)
    finally:
        print("[World Sim] Остановка потока симуляции...")
        stop_simulation_event.set()
        simulation_thread.join(timeout=2)
        print("[World Sim] Поток симуляции остановлен.")