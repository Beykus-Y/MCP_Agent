# rpg/game_manager.py
import os
import json
from typing import Optional

from .models import Character, Stats, Item, Quest # Добавлен Quest
from .rules import RulesEngine
from dataclasses import asdict, is_dataclass
from .constants import DEFAULT_MAX_HP, DEFAULT_STARTING_HP
from .world.world_state import WorldState, PointOfInterest, Faction, NPC # Добавлен NPC

class EnhancedJSONEncoder(json.JSONEncoder):
    """Кастомный кодировщик, который умеет превращать dataclass'ы в словари и set'ы в списки."""
    def default(self, o):
        if isinstance(o, set):
            return list(o)
        if is_dataclass(o):
            return asdict(o)
        return super().default(o)

BASE_SAVES_DIR = os.path.join(os.path.dirname(__file__), 'saves')
CHAR_SAVES_DIR = os.path.join(BASE_SAVES_DIR, 'characters')


class GameManager:
    def __init__(self):
        if not os.path.exists(CHAR_SAVES_DIR):
            os.makedirs(CHAR_SAVES_DIR)
            
        self.rules_engine = RulesEngine()

    def get_save_list(self):
        saves = []
        for filename in os.listdir(CHAR_SAVES_DIR):
            if filename.endswith(".json"):
                try:
                    path = os.path.join(CHAR_SAVES_DIR, filename)
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    saves.append({
                        "id": filename.replace(".json", ""),
                        "character_name": data.get("name", "Неизвестно")
                    })
                except Exception:
                    continue
        return saves
    
    def get_character_save_id(self, character_name: str) -> Optional[str]:
        saves = self.get_save_list()
        for save in saves:
            if save['character_name'] == character_name:
                return save['id']
        return None

    def load_world(self, world_name: str) -> Optional[WorldState]:
        return None

    def get_next_save_id(self) -> str:
        saves = self.get_save_list()
        if not saves: return "save_1"
        max_id = 0
        for save in saves:
            try:
                num = int(save['id'].split('_')[1])
                if num > max_id: max_id = num
            except (ValueError, IndexError): continue
        return f"save_{max_id + 1}"

    def create_new_save(self, character: Character) -> str:
        save_id = self.get_next_save_id()
        path = os.path.join(CHAR_SAVES_DIR, f"{save_id}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(character, f, ensure_ascii=False, indent=4, cls=EnhancedJSONEncoder)
        return save_id
    
    def load_character(self, save_id: str) -> Optional[Character]:
        path = os.path.join(CHAR_SAVES_DIR, f"{save_id}.json")
        if not os.path.exists(path): return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # ИСПРАВЛЕНИЕ: Используем новый Character.from_dict()
        return Character.from_dict(data)
    
    def save_character_progress(self, character: Character, save_id: str):
        path = os.path.join(CHAR_SAVES_DIR, f"{save_id}.json")
        if not os.path.exists(path):
            print(f"[Ошибка] Попытка сохранить прогресс для несуществующего файла: {save_id}")
            return

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(character, f, ensure_ascii=False, indent=4, cls=EnhancedJSONEncoder)