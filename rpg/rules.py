# rpg/rules.py
import os
import json
import random
import copy
from typing import List, Dict, Optional, Union
import math

# Импортируем наши модели данных
from .models import Character, Stats, Item

# --- Константы для путей к файлам с данными ---
BASE_DIR = os.path.dirname(__file__)
TRAITS_FILE = os.path.join(BASE_DIR, 'game_data', 'traits.json')
ITEMS_DIR = os.path.join(BASE_DIR, 'game_data', 'items')

class RulesEngine:
    """
    Класс, отвечающий за игровую логику, загрузку данных и применение правил.
    Работает как синглтон (единый экземпляр) для кэширования данных.
    """
    _instance = None

    def __new__(cls):
        # Реализация паттерна Синглтон, чтобы не загружать JSON-файлы каждый раз.
        if cls._instance is None:
            cls._instance = super(RulesEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        print("Инициализация движка правил...")
        self.traits_data: List[Dict] = self._load_data(TRAITS_FILE)
        self.items_data: Dict[str, List[Dict]] = self._load_data(ITEMS_DIR) 
        
        # Создаем словари для быстрого доступа по ID
        self.traits_by_id: Dict[str, Dict] = {trait['id']: trait for trait in self.traits_data}
        self.items_by_id: Dict[str, Dict] = {}
        if isinstance(self.items_data, dict):
            for category in self.items_data.values():
                for item in category:
                    self.items_by_id[item['id']] = item
        
        self._initialized = True
        print("Движок правил готов.")

    def _load_data(self, path: str) -> Union[List, Dict]:
        """
        Универсальная функция для загрузки данных.
        Если путь - файл, загружает его.
        Если путь - папка, загружает все .json файлы из нее.
        """
        # --- НАЧАЛО БОЛЬШОГО ИЗМЕНЕНИЯ ---
        if os.path.isdir(path):
            # Если это директория (наш случай для ITEMS_DIR)
            all_data = {}
            if not os.path.exists(path):
                print(f"[!] Директория с данными не найдена: {path}")
                return {}
                
            for filename in os.listdir(path):
                if filename.endswith('.json'):
                    file_path = os.path.join(path, filename)
                    category_name = filename.replace('.json', '')
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            all_data[category_name] = json.load(f)
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"[!] Ошибка загрузки файла {filename}: {e}")
            return all_data
        
        elif os.path.isfile(path):
            # Если это одиночный файл (наш случай для TRAITS_FILE)
            if not os.path.exists(path):
                print(f"[!] Файл данных не найден: {path}")
                return []
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[!] Ошибка загрузки файла {path}: {e}")
                return []
        else:
            print(f"[!] Путь не найден: {path}")
            return {}

    def get_trait(self, trait_id: str) -> Optional[Dict]:
        """Возвращает данные о черте по ее ID."""
        return self.traits_by_id.get(trait_id)

    def get_item(self, item_id: str) -> Optional[Dict]:
        """Возвращает данные о предмете по его ID."""
        return self.items_by_id.get(item_id)
        
    def create_item_instance(self, item_id: str) -> Optional[Item]:
        """Создает экземпляр dataclass Item на основе данных из базы."""
        item_data = self.get_item(item_id)
        if not item_data:
            return None
        return Item(
            id=item_data['id'],
            name=item_data['name'],
            description=item_data['description'],
            slot=item_data['slot'],
            effects=item_data.get('effects', [])
        )

    def apply_item_effects(self, character: Character, item: Item, log_callback=None) -> bool:
        """
        Применяет эффекты предмета к персонажу.
        Возвращает True, если предмет был успешно использован (и должен быть удален), False в противном случае.
        """
        if not item or not item.effects:
            if log_callback: log_callback(f"[INFO] Предмет '{item.name}' не имеет эффектов.")
            return False

        if log_callback: log_callback(f"[INFO] Применение эффектов от '{item.name}'...")
        
        for effect in item.effects:
            effect_type = effect.get("type")
            value = effect.get("value")
            
            # Эффекты, которые срабатывают при использовании (consumable)
            if effect.get("on_use"):
                if effect_type == "heal":
                    if isinstance(value, str):
                        # Простая парсинг формулы d&d типа "2d4+2"
                        try:
                            roll_parts = value.split('+')
                            dice_part = roll_parts[0]
                            bonus_part = int(roll_parts[1]) if len(roll_parts) > 1 else 0

                            num_dice, dice_sides = map(int, dice_part.split('d'))
                            healing_amount = 0
                            for _ in range(num_dice):
                                healing_amount += random.randint(1, dice_sides)
                            healing_amount += bonus_part

                            # Применяем лечение
                            character.current_hp = min(character.max_hp, character.current_hp + healing_amount)
                            if log_callback: log_callback(f"[ИСЦЕЛЕНИЕ] {character.name} восстановил {healing_amount} HP. Текущее HP: {character.current_hp}.")
                        except Exception as e:
                            if log_callback: log_callback(f"[ОШИБКА] Не удалось применить эффект лечения: {e}")
                            return False # Не удалось применить эффект, предмет не расходуется
                    else:
                        # Если value - просто число
                        character.current_hp = min(character.max_hp, character.current_hp + int(value))
                        if log_callback: log_callback(f"[ИСЦЕЛЕНИЕ] {character.name} восстановил {value} HP. Текущее HP: {character.current_hp}.")
                    
                elif effect_type == "flag_modifier":
                    flag = effect.get("flag")
                    action = effect.get("action")
                    if action == "add":
                        if flag not in character.active_flags: # Используем новое поле active_flags
                            character.active_flags.append(flag)
                            if log_callback: log_callback(f"[ЭФФЕКТ] Активирован флаг '{flag}' на {character.name}.")
                        else:
                            if log_callback: log_callback(f"[ЭФФЕКТ] Флаг '{flag}' уже активен на {character.name}.")
                    elif action == "remove":
                        if flag in character.active_flags:
                            character.active_flags.remove(flag)
                            if log_callback: log_callback(f"[ЭФФЕКТ] Флаг '{flag}' снят с {character.name}.")
                # Добавьте сюда другие типы эффектов по мере необходимости
                else:
                    if log_callback: log_callback(f"[ПРЕДУПРЕЖДЕНИЕ] Неизвестный эффект на использование: {effect_type}.")
                    return False # Неизвестный эффект, не расходуем предмет
            else:
                if log_callback: log_callback(f"[ПРЕДУПРЕЖДЕНИЕ] Эффект '{effect_type}' не имеет 'on_use' и не является пассивным. Пропущен.")
        return True # Предмет успешно использован

    def calculate_final_stats(self, character: Character) -> Stats:
        """
        Главная функция: рассчитывает финальные характеристики персонажа.
        Применяет модификаторы от черт и экипировки.
        """
        final_stats = copy.deepcopy(character.stats)

        # 1. Применяем эффекты от ЧЕРТ ХАРАКТЕРА
        for trait_id in character.traits:
            trait_data = self.get_trait(trait_id)
            if trait_data and 'effects' in trait_data:
                for effect in trait_data['effects']:
                    if effect.get('type') == 'stat_modifier':
                        stat_name = effect.get('stat')
                        value = effect.get('value', 0)
                        if hasattr(final_stats, stat_name):
                            current_value = getattr(final_stats, stat_name)
                            setattr(final_stats, stat_name, current_value + value)
                    # Также можно обрабатывать другие пассивные эффекты от черт здесь
                    elif effect.get('type') == 'armor_class':
                        # Пока не используется в UI, но логика будет тут
                        pass
        # 2. Применяем эффекты от ЭКИПИРОВАННЫХ ПРЕДМЕТОВ
        for slot, item in character.equipment.items():
            if item and item.effects:
                for effect in item.effects:
                    if effect.get('type') == 'stat_modifier':
                        stat_name = effect.get('stat')
                        value = effect.get('value', 0)
                        if hasattr(final_stats, stat_name):
                            current_value = getattr(final_stats, stat_name)
                            setattr(final_stats, stat_name, current_value + value)
                    # Также можно обрабатывать другие пассивные эффекты от предметов здесь
                    elif effect.get('type') == 'armor_class':
                        # Пока не используется в UI, но логика будет тут
                        pass
        
        return final_stats