# mcp_rpg.py (Версия 4.6 - Финальная исправленная, с подробным логированием ошибок)
import os
import json
import sqlite3
import re 
import random
import threading
import time
import traceback # <-- НОВОЕ: Для вывода полного traceback

from flask import Flask, request, jsonify
from waitress import serve

# --- Конфигурация ---
DB_FILE = "rpg_database.db"
ACTIVE_SAVE_FILE = "rpg_active_save.json" # Используется для глобально активной игры
SIMULATION_TICK_RATE = 300 # В секундах
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
                cursor.execute("INSERT INTO game_state (save_id, key, value) VALUES (?, 'weather', ?) ON CONFLICT(save_id, key) DO UPDATE SET value=excluded.value", (save_id, 'weather', new_weather))
                cursor.execute("SELECT id, location_x, location_y FROM characters WHERE save_id = ? AND is_player = 0 ORDER BY RANDOM() LIMIT 1", (save_id,)); npc = cursor.fetchone()
                if npc:
                    move_x, move_y = random.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
                    new_x, new_y = npc['location_x'] + move_x, npc['location_y'] + move_y
                    cursor.execute("UPDATE characters SET location_x = ?, location_y = ? WHERE id = ?", (new_x, new_y, npc['id']))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[World Sim] Ошибка в потоке симуляции: {e}")
            traceback.print_exc() # <-- Добавлено для отладки ошибок в симуляции
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
    # Проверить, что такой save_id существует
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM saves WHERE id = ?", (save_id,))
    if not cursor.fetchone():
        conn.close()
        raise JsonRpcError(-32000, f"Игра с ID {save_id} не найдена.")
    conn.close()

    with open(ACTIVE_SAVE_FILE, 'w') as f: json.dump({"active_save_id": save_id}, f)
    return {"status": "ok", "message": f"Игра с ID {save_id} теперь активна."}

def new_game(params):
    game_name = params.get("name")
    if not game_name: raise JsonRpcError(-32602, "Параметр 'name' обязателен.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO saves (name, last_saved) VALUES (?, datetime('now', 'localtime'))", (game_name,))
    new_id = cursor.lastrowid; conn.commit(); conn.close()
    
    # Автоматически делаем новую игру активной
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

# --- НОВЫЕ/ИЗМЕНЕННЫЕ ФУНКЦИИ УПРАВЛЕНИЯ СОСТОЯНИЕМ ---
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

def get_global_state(params):
    """Получает значение глобальной переменной для активной игры."""
    save_id = get_active_save_id(params)
    if save_id is None:
        raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    
    key = params.get("key")
    if key is None:
        raise JsonRpcError(-32602, "Необходим параметр 'key'.")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM game_state WHERE save_id = ? AND key = ?", (save_id, key))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"status": "ok", "value": row["value"]}
    else:
        return {"status": "not_found", "message": f"Состояние '{key}' не найдено для активной игры."}

def set_active_player_character(params):
    """
    Устанавливает указанного персонажа как активного игрового персонажа для текущей сессии.
    Это НЕ меняет статус 'is_player' персонажа, только определяет, какой из персонажей-игроков
    считается 'основным' для текущей игры.
    """
    character_id = params.get("character_id")
    if character_id is None:
        raise JsonRpcError(-32602, "Необходим параметр 'character_id'.")

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем, существует ли персонаж и к какой игре он принадлежит
    cursor.execute("SELECT save_id, is_player FROM characters WHERE id = ?", (character_id,))
    char_info = cursor.fetchone()
    if not char_info:
        conn.close()
        raise JsonRpcError(-32000, f"Персонаж с ID {character_id} не найден.")
    if not char_info['is_player']:
        conn.close()
        raise JsonRpcError(-32000, f"Персонаж с ID {character_id} не является игровым персонажем (is_player = false).")
    
    save_id = char_info['save_id']
    conn.close()
    
    # Устанавливаем его как активного игрока для этой save_id
    return set_global_state({"save_id": save_id, "key": "active_character_id", "value": str(character_id)})


# --- ИЗМЕНЕННЫЕ ФУНКЦИИ С УЧЕТОМ АКТИВНОЙ ИГРЫ/ПЕРСОНАЖА ---
def create_character(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру. Укажите save_id или используйте set_active_game.")
    
    # name и is_player теперь REQUIRED
    name = params.get('name')
    is_player = params.get('is_player')
    if name is None or is_player is None:
        raise JsonRpcError(-32602, "Отсутствуют обязательные параметры: 'name' или 'is_player'.")

    attributes_data = params.get('attributes', {}) 
    attributes_json = json.dumps(attributes_data)

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO characters (save_id, name, is_player, hp, max_hp, location_x, location_y, attributes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (save_id, name, is_player, params.get('hp', 10), params.get('max_hp', 10), params.get('location_x', 0), params.get('location_y', 0), attributes_json)
    )
    new_id = cursor.lastrowid; conn.commit(); conn.close()

    # Если это игровой персонаж, автоматически делаем его активным
    if is_player:
        set_active_player_character({"character_id": new_id})

    return {"status": "ok", "character_id": new_id}

def get_player_character_info(params):
    """
    Находит персонажа игрока в активной игре. Приоритет:
    1. Персонаж, установленный как 'active_character_id' в game_state.
    2. Любой персонаж с is_player = 1.
    """
    save_id = get_active_save_id(params)
    if save_id is None: 
        return {"status": "no_active_game_found", "message": "Активная игра не найдена."}
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    player_id = None
    # 1. Попытка получить active_character_id
    active_char_state = get_global_state({"save_id": save_id, "key": "active_character_id"})
    if active_char_state.get("status") == "ok":
        try:
            potential_player_id = int(active_char_state["value"])
            cursor.execute("SELECT id FROM characters WHERE save_id = ? AND id = ? AND is_player = 1", (save_id, potential_player_id))
            if cursor.fetchone():
                player_id = potential_player_id
        except (ValueError, TypeError):
            pass # Неверный формат ID, игнорируем и ищем дальше

    # 2. Если active_character_id не найден или недействителен, ищем первого is_player=1
    if player_id is None:
        cursor.execute("SELECT id FROM characters WHERE save_id = ? AND is_player = 1 ORDER BY id ASC LIMIT 1", (save_id,))
        first_player = cursor.fetchone()
        if first_player:
            player_id = first_player['id']
            # Если нашли, делаем его активным для будущих запросов
            set_active_player_character({"character_id": player_id})

    conn.close()

    if player_id is None: 
        return {"status": "player_character_not_found", "message": "Персонаж игрока не найден в этой игре."}

    # Теперь, когда player_id определен, используем get_character_details
    # Но избегаем рекурсии, вызывая логику get_character_details напрямую
    char_data = get_character_details({"character_id": player_id}) # передаем напрямую, без JsonRpcError
    if char_data:
        return {"status": "ok", "character_details": char_data}
    else:
        return {"status": "error_retrieving_details", "message": "Не удалось получить детали активного персонажа."}


def get_player_location(params):
    """Комбинированное действие: находит игрока и возвращает детали его текущей локации."""
    player_info = get_player_character_info(params)
    if player_info.get("status") != "ok":
        # Если игрока не нашли, возвращаем сообщение из get_player_character_info
        return player_info
    
    player_data = player_info["character_details"]
    location_params = {"save_id": player_data["save_id"], "x": player_data["location_x"], "y": player_data["location_y"]}
    return get_location_details(location_params) # get_location_details возвращает свой статус


def get_player_status(params):
    """
    Возвращает ПОЛНУЮ сводку по персонажу игрока за один вызов:
    детали персонажа, его инвентарь и информацию о его текущей локации.
    """
    # 1. Получаем инфо о персонаже
    player_info = get_player_character_info(params)
    if player_info.get("status") != "ok":
        # Если игрока не нашли, возвращаем соответствующий статус и сообщение
        return player_info 
    
    player_details = player_info["character_details"]
    player_id = player_details.get("id")
    
    # 2. Получаем инвентарь
    inventory_info = get_inventory({"character_id": player_id})
    
    # 3. Получаем инфо о локации
    location_info = get_player_location(params) # Это уже вернет статус из get_player_location
    
    return {
        "status": "ok",
        "character_details": player_details,
        "inventory": inventory_info.get("inventory", []),
        "location": location_info
    }


# --- ОСТАЛЬНЫЕ МЕТОДЫ (без существенных изменений, кроме get_active_save_id) ---
def update_location(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    
    x = params.get('x')
    y = params.get('y')
    if x is None or y is None:
        raise JsonRpcError(-32602, "Отсутствуют обязательные параметры: 'x' или 'y'.")

    details_data = params.get('details', {}) 
    details_json = json.dumps(details_data)

    conn = get_db_connection(); cursor = conn.cursor()
    # ИСПРАВЛЕНИЕ: Изменено excluded.value на excluded.details
    cursor.execute("INSERT INTO locations (save_id, x, y, details) VALUES (?, ?, ?, ?) ON CONFLICT(save_id, x, y) DO UPDATE SET details=excluded.details", (save_id, x, y, details_json))
    conn.commit(); conn.close()
    return {"status": "ok"}

def add_quest(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    
    title = params.get('title')
    objectives = params.get('objectives')
    if title is None or objectives is None:
        raise JsonRpcError(-32602, "Отсутствуют обязательные параметры: 'title' или 'objectives'.")

    objectives_list = [{"text": obj, "done": False} for obj in objectives]
    objectives_json = json.dumps(objectives_list)
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO quests (save_id, title, description, objectives) VALUES (?, ?, ?, ?)", (save_id, title, params.get('description', ''), objectives_json))
    quest_id = cursor.lastrowid; conn.commit(); conn.close()
    return {"status": "ok", "quest_id": quest_id}

def get_location_details(params):
    save_id = get_active_save_id(params)
    if save_id is None: return {"status": "no_active_game_found"} # Не JsonRpcError, т.к. это функция чтения
    
    x = params.get('x')
    y = params.get('y')
    if x is None or y is None:
        raise JsonRpcError(-32602, "Отсутствуют обязательные параметры: 'x' или 'y'.")

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT details FROM locations WHERE save_id = ? AND x = ? AND y = ?", (save_id, x, y))
    row = cursor.fetchone(); conn.close()
    if not row: return {"status": "not_explored", "x": x, "y": y, "message": "Эта локация еще не исследована."}
    return {"status": "ok", "details": json.loads(row['details']), "x": x, "y": y}

def get_quest_journal(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, status, objectives FROM quests WHERE save_id = ?", (save_id,))
    quests_raw = cursor.fetchall(); conn.close()
    quests = [dict(q) for q in quests_raw]
    for q in quests: 
        try:
            q['objectives'] = json.loads(q['objectives'])
        except (json.JSONDecodeError, TypeError):
            q['objectives'] = [] # В случае ошибки парсинга
    return {"quests": quests}

def generate_random_encounter(params):
    save_id = get_active_save_id(params)
    if save_id is None: raise JsonRpcError(-32000, "Не удалось определить активную игру.")
    
    x = params.get('x')
    y = params.get('y')
    if x is None or y is None:
        raise JsonRpcError(-32602, "Отсутствуют обязательные параметры: 'x' или 'y'.")

    # Передаем save_id в get_location_details
    location_details_result = get_location_details({'save_id': save_id, 'x': x, 'y': y})
    terrain = location_details_result.get("details", {}).get("terrain", "plains")
    encounters = {
        "forest": ["Вы натыкаетесь на поляну со светящимися грибами.", "Из кустов на вас смотрит олень."],
        "plains": ["Стадо бизонов медленно пересекает равнину.", "Вы находите старый, заброшенный колодец."],
        "fort": ["В коридоре вы замечаете следы старой битвы.", "Сквозняк задувает ваш факел."]
    }
    description = random.choice(encounters.get(terrain.lower(), encounters["plains"]))
    return {"status": "ok", "encounter_description": description}

def get_character_details(params):
    char_id = params.get("character_id")
    if char_id is None: raise JsonRpcError(-32602, "Отсутствует character_id.")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM characters WHERE id = ?", (char_id,)); char_data = cursor.fetchone(); conn.close()
    if not char_data: raise JsonRpcError(-32000, f"Персонаж с ID {char_id} не найден.")
    result = dict(char_data); 
    result['attributes'] = json.loads(result['attributes']) if result['attributes'] else {}
    return result

def update_character_attributes(params):
    char_id = params.get("character_id"); updates = params.get("attributes_to_update") or params.get("attributes") 
    if char_id is None or updates is None: raise JsonRpcError(-32602, "Отсутствуют character_id или attributes_to_update (или attributes).")
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
    char_id = params.get("character_id")
    new_x = params.get("new_x")
    new_y = params.get("new_y")
    if char_id is None or new_x is None or new_y is None:
        raise JsonRpcError(-32602, "Необходимы параметры: character_id, new_x, new_y.")

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE characters SET location_x = ?, location_y = ? WHERE id = ?", (new_x, new_y, char_id))
    if cursor.rowcount == 0:
        conn.close()
        raise JsonRpcError(-32000, f"Персонаж с ID {char_id} не найден.")
    conn.commit(); conn.close()
    return {"status": "ok"}

def update_quest_status(params):
    quest_id = params.get("quest_id")
    status = params.get("status")
    if quest_id is None or status is None:
        raise JsonRpcError(-32602, "Необходимы параметры: quest_id, status.")

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE quests SET status = ? WHERE id = ?", (status, quest_id))
    if cursor.rowcount == 0:
        conn.close()
        raise JsonRpcError(-32000, f"Квест с ID {quest_id} не найден.")
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

def explore_location(params):
    char_id = params.get("character_id"); new_x = params.get("new_x"); new_y = params.get("new_y")
    if char_id is None or new_x is None or new_y is None: raise JsonRpcError(-32602, "Необходимы параметры: character_id, new_x, new_y.")
    
    # Сначала перемещаем персонажа
    move_character({"character_id": char_id, "new_x": new_x, "new_y": new_y})

    # Теперь получаем данные о локации
    save_id_res = get_character_details({"character_id": char_id})
    save_id = save_id_res["save_id"] if save_id_res else None
    
    if save_id is None: 
        raise JsonRpcError(-32000, "Не удалось определить игру, к которой относится персонаж.")

    location_data = get_location_details({"save_id": save_id, "x": new_x, "y": new_y})
    
    if location_data["status"] == "not_explored":
        return {"status": "moved_to_unexplored_area", "message": "Персонаж перемещен. Эта область не исследована. Опиши ее и вызови 'update_location'.", "x": new_x, "y": new_y}
    else:
        return {"status": "moved_to_explored_area", "details": location_data["details"], "x": new_x, "y": new_y}
    
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
        "description": "Самый главный инструмент для получения полной информации о состоянии игрока. Используй его, если пользователь спрашивает 'где я?', 'что я вижу?', 'что у меня есть?' или просит общую сводку. Возвращает всё: статы, инвентарь и информацию о текущей локации АКТИВНОГО персонажа.",
        "parameters": {}
    },
    {
        "name": "get_player_location", 
        "description": "Самый быстрый способ узнать, где находится АКТИВНЫЙ игрок и что его окружает. Используй, если пользователь спрашивает 'где я?' или 'что я вижу?'.", 
        "parameters": {}
    },
    {
        "name": "get_player_character_info", 
        "description": "Получает полную информацию об АКТИВНОМ персонаже игрока (статы, HP, ID) в текущей активной игре.", 
        "parameters": {}
    },
    {
        "name": "explore_location", 
        "description": "Основное действие для перемещения. Перемещает указанного персонажа и сообщает, что находится в новой локации (или что она не исследована). Возвращает координаты, на которые переместился персонаж, в том числе, если локация не исследована.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "character_id": {"type": "integer", "description": "ID персонажа, который перемещается."}, 
                "new_x": {"type": "integer", "description": "Новая координата X."}, 
                "new_y": {"type": "integer", "description": "Новая координата Y."}
            }, 
            "required": ["character_id", "new_x", "new_y"]
        }
    },
    {
        "name": "new_game", 
        "description": "Начинает новую игру и автоматически делает ее активной. После создания игры, необходимо создать персонажа игрока с помощью `create_character`.", 
        "parameters": {
            "type": "object", 
            "properties": {"name": {"type": "string", "description": "Название новой игры."}}, 
            "required": ["name"]
        }
    },
    {
        "name": "list_saves", 
        "description": "Показывает список всех сохраненных игр.", 
        "parameters": {}
    },
    {
        "name": "set_active_game", 
        "description": "Выбирает игру для продолжения, делая ее активной для всех последующих команд. Всегда используй этот метод, если нужно поменять текущую игру.", 
        "parameters": {
            "type": "object", 
            "properties": {"save_id": {"type": "integer", "description": "ID игры, которую нужно сделать активной."}}, 
            "required": ["save_id"]
        }
    },
    {
        "name": "get_active_game", 
        "description": "Возвращает ID текущей активной игры.", 
        "parameters": {}
    },
    {
        "name": "create_character",
        "description": "Создает нового персонажа в активной игре. Если 'is_player' установлен в true, этот персонаж АВТОМАТИЧЕСКИ становится активным игровым персонажем для этой игры. ВСЕГДА предоставляй параметр `attributes` в виде ОБЪЕКТА (даже если он пустой `{}`).",
        "parameters": {
            "type": "object",
            "properties": {
                "save_id": {"type": "integer", "description": "ID игры, необязателен, если игра активна."},
                "name": {"type": "string", "description": "Имя персонажа."},
                "is_player": {"type": "boolean", "description": "Установить в true, если это игровой персонаж, false для NPC."},
                "attributes": {"type": "object", "description": "Объект с дополнительными атрибутами персонажа, например, {'class': 'mage', 'strength': 8}."}
            },
            "required": ["name", "is_player"]
        }
    },
    {
        "name": "set_active_player_character",
        "description": "Устанавливает указанного персонажа как АКТИВНОГО игрового персонажа для текущей игровой сессии. Это необходимо, если в игре несколько персонажей игрока и нужно переключиться между ними. Персонаж должен существовать и быть помечен как 'is_player=true'.",
        "parameters": {
            "type": "object",
            "properties": {
                "character_id": {"type": "integer", "description": "ID персонажа, который должен стать активным игроком."}
            },
            "required": ["character_id"]
        }
    },
    {
        "name": "update_location",
        "description": "Обновляет локацию в активной игре, добавляя или изменяя ее детали. save_id необязателен. ВСЕГДА указывай `details` в виде ОБЪЕКТА, например: `{\"name\": \"Темный лес\", \"description\": \"Густые заросли...\", \"terrain\": \"forest\"}`.",
        "parameters": {
            "type": "object",
            "properties": {
                "save_id": {"type": "integer", "description": "ID игры, необязателен, если игра активна."},
                "x": {"type": "integer", "description": "Координата X локации."},
                "y": {"type": "integer", "description": "Координата Y локации."},
                "details": {"type": "object", "description": "Объект с деталями локации, например, {'name': 'Лесная поляна', 'terrain': 'forest'}."}
            },
            "required": ["x", "y", "details"]
        }
    },
    {
        "name": "add_quest", 
        "description": "Добавляет квест в активную игру. save_id необязателен. `objectives` должен быть массивом строк.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "save_id": {"type": "integer", "description": "ID игры, необязателен, если игра активна."}, 
                "title": {"type": "string", "description": "Название квеста."}, 
                "description": {"type": "string", "description": "Подробное описание квеста."}, 
                "objectives": {"type": "array", "items": {"type": "string"}, "description": "Список задач для квеста."}
            }, 
            "required": ["title", "objectives"]
        }
    },
    {
        "name": "get_character_details", 
        "description": "Получает полную информацию о любом персонаже по его ID (включая NPC).", 
        "parameters": {
            "type": "object", 
            "properties": {"character_id": {"type": "integer", "description": "ID персонажа."}}, 
            "required": ["character_id"]
        }
    },
    {
        "name": "update_character_attributes", 
        "description": "Обновляет атрибуты персонажа. `attributes_to_update` должен быть объектом, содержащим ключи и новые значения атрибутов.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "character_id": {"type": "integer", "description": "ID персонажа."}, 
                "attributes_to_update": {"type": "object", "description": "Объект с атрибутами для обновления, например, {'strength': 10, 'dexterity': 12}."}
            }, 
            "required": ["character_id", "attributes_to_update"]
        }
    },
    {
        "name": "add_item_to_inventory", 
        "description": "Добавляет предмет в инвентарь персонажа.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "character_id": {"type": "integer", "description": "ID персонажа."}, 
                "item_name": {"type": "string", "description": "Название предмета."},
                "quantity": {"type": "integer", "description": "Количество предметов (по умолчанию 1)."},
                "description": {"type": "string", "description": "Описание предмета."}
            }, 
            "required": ["character_id", "item_name"]
        }
    },
    {
        "name": "get_inventory", 
        "description": "Возвращает инвентарь персонажа по его ID.", 
        "parameters": {
            "type": "object", 
            "properties": {"character_id": {"type": "integer", "description": "ID персонажа."}}, 
            "required": ["character_id"]
        }
    },
    {
        "name": "get_location_details", 
        "description": "Получает информацию о локации по ее координатам в активной игре. save_id необязателен. Возвращает статус 'not_explored', если локация не имеет деталей.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "save_id": {"type": "integer", "description": "ID игры, необязателен, если игра активна."}, 
                "x": {"type": "integer", "description": "Координата X локации."}, 
                "y": {"type": "integer", "description": "Координата Y локации."}
            }, 
            "required": ["x", "y"]
        }
    },
    {
        "name": "move_character", 
        "description": "Перемещает персонажа в новую локацию. НЕ используй это напрямую для игрока; вместо этого используй `explore_location`.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "character_id": {"type": "integer", "description": "ID персонажа."}, 
                "new_x": {"type": "integer", "description": "Новая координата X."}, 
                "new_y": {"type": "integer", "description": "Новая координата Y."}
            }, 
            "required": ["character_id", "new_x", "new_y"]
        }
    },
    {
        "name": "get_quest_journal", 
        "description": "Возвращает список всех квестов в активной игре. save_id необязателен.", 
        "parameters": {
            "type": "object", 
            "properties": {"save_id": {"type": "integer", "description": "ID игры, необязателен, если игра активна."}}
        }
    },
    {
        "name": "update_quest_status", 
        "description": "Обновляет статус квеста.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "quest_id": {"type": "integer", "description": "ID квеста."}, 
                "status": {"type": "string", "enum": ["active", "completed", "failed"], "description": "Новый статус квеста."}
            }, 
            "required": ["quest_id", "status"]
        }
    },
    {
        "name": "roll_dice", 
        "description": "Бросает кости по формуле (например, '1d20', '3d6+5').", 
        "parameters": {
            "type": "object", 
            "properties": {"expression": {"type": "string", "description": "Формула броска кубиков."}}, 
            "required": ["expression"]
        }
    },
    {
        "name": "suggest_mcp_action", 
        "description": "Предлагает ИИ выполнить действие с помощью ДРУГОГО MCP. Используется для выдачи инструкций Оркестратору.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "suggestion": {"type": "string", "description": "Краткое описание предлагаемого действия."}, 
                "details": {"type": "object", "description": "Детали и параметры для предлагаемого действия."}
            }, 
            "required": ["suggestion", "details"]
        }
    },
    {
        "name": "delete_save",
        "description": "Безвозвратно удаляет сохранение игры и всех связанных с ней персонажей, квесты и локации.",
        "parameters": {"type": "object", "properties": {"save_id": {"type": "integer", "description": "ID игры для удаления."}}, "required": ["save_id"]}
    },
    {
        "name": "set_global_state",
        "description": "Устанавливает глобальную переменную для текущей активной игры. Используй это для установки времени, погоды или других правил мира, а также для хранения `active_character_id`.",
        "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "Название переменной, например, 'current_time' или 'active_character_id'."}, "value": {"type": "string", "description": "Значение переменной."}}, "required": ["key", "value"]}
    },
    {
        "name": "get_global_state",
        "description": "Получает значение глобальной переменной для текущей активной игры.",
        "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "Название переменной, например, 'current_time' или 'active_character_id'."}}, "required": ["key"]}
    },
    {
        "name": "find_character_by_name",
        "description": "Ищет персонажа по имени в активной игре и возвращает список совпадений с их ID. Можно использовать для поиска как игроков, так и NPC.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "Имя персонажа для поиска (поддерживает частичное совпадение)."}}, "required": ["name"]}
    },
]

# --- Словарь методов ---
METHODS = {func['name']: globals()[func['name']] for func in RPG_FUNCTIONS}

# --- Эндпоинты Flask ---
@app.route("/functions")
def get_functions_route(): return jsonify(RPG_FUNCTIONS)

@app.route("/mcp", methods=["POST"])
def mcp_entrypoint():
    req_id = None
    method_name = "unknown" # Для более информативного сообщения об ошибке
    try:
        req = request.get_json(force=True)
        req_id = req.get('id')
        method_name = req.get('method')
        
        if req.get("jsonrpc") != "2.0" or req_id is None or not method_name:
            raise JsonRpcError(-32600, "Invalid JSON-RPC request format")
        
        if method_name not in METHODS: 
            raise JsonRpcError(-32601, f"Метод '{method_name}' не найден.")
        
        result = METHODS[method_name](req.get('params', {}))
        return make_success_response(req_id, result)
    except JsonRpcError as je: # <--- Ловим наши специфические ошибки
        print(f"[MCP_RPG ERROR] JSON-RPC Error in method '{method_name}': {je.message}") # <-- Улучшенный лог
        return make_error_response(req_id, je.code, je.message), 400 
    except Exception as e: # <--- Ловим все остальные, неожиданные ошибки
        # <-- НОВОЕ: Печатаем полный traceback в консоль MCP_RPG
        print(f"[MCP_RPG CRITICAL ERROR] Unhandled exception in method '{method_name}':")
        traceback.print_exc() 
        
        code = getattr(e, 'code', -32603)
        msg = getattr(e, 'message', str(e))
        return make_error_response(req_id, code, msg), 500

# if __name__ == "__main__":
#     initialize_database()
#     simulation_thread = threading.Thread(target=world_simulation_loop, daemon=True)
#     simulation_thread.start()
#     port = int(os.getenv("MCP_RPG_PORT", 8008))
    
#     # --- НА ВРЕМЯ ОТЛАДКИ: ИСПОЛЬЗУЕМ ВСТРОЕННЫЙ СЕРВЕР FLASK В РЕЖИМЕ DEBUG ---
#     print(f"[*] MCP_RPG (Игровой движок) запускается на порту: {port} через Flask dev server (DEBUG MODE).")
#     app.run(host="0.0.0.0", port=port, debug=True)
    
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