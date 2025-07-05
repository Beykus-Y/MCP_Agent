# rpg/world/generator.py
import time
import random
import json
import os 
from dataclasses import asdict

from .world_state import WorldState
from .geography import generate_world_map
from .history import generate_history
from .nomenclator import Nomenclator

WORLD_SAVES_DIR = os.path.join(os.path.dirname(__file__), '..', 'saves', 'worlds')

class WorldGenerator:
    def __init__(self, map_width=128, map_height=128, progress_callback=None):
        self.width = map_width
        self.height = map_height
        self.nomenclator = Nomenclator()
        # Сохраняем колбэк. Если он не передан, создаем "пустышку"
        self.report_progress = progress_callback if progress_callback else lambda msg: None

    def generate_new_world(self, params: dict, seed: int = None):
        if seed is None:
            seed = int(time.time())
        random.seed(seed)
        
        world_name = params['world_name']
        self.report_progress(f"Начало генерации мира '{world_name}' (Сид: {seed})...")
        
        world = WorldState(
            world_name=world_name, seed=seed, map_size=(self.width, self.height),
            year=params['year'], tech_level=params['tech_level'], magic_level=params['magic_level']
        )
        
        self.report_progress("Создание континентов и океанов...")
        world.biome_map = generate_world_map(self.width, self.height, seed)
        self.report_progress("Расчет биомов на основе климата...")
        
        self.report_progress("Симуляция древней истории...")
        # 👇 Передаем колбэк дальше 👇
        factions, pois, history_log = generate_history(
            world.biome_map, self.nomenclator, params, self.report_progress
        )
        world.factions = factions
        world.points_of_interest = pois
        world.history_log = history_log
        
        self.report_progress("Детализация мира завершена.")
        return world

    def save_world(self, world: WorldState):
        """Сохраняет сгенерированный мир в файл в папку saves/worlds."""
        
        # --- ИЗМЕНЕНИЕ: Работаем с новой папкой ---
        if not os.path.exists(WORLD_SAVES_DIR):
            os.makedirs(WORLD_SAVES_DIR)

        filename = f"{world.world_name.replace(' ', '_')}.world"
        filepath = os.path.join(WORLD_SAVES_DIR, filename)

        self.report_progress(f"Сохранение мира в файл: {filepath}...")
        try:
            world_data = asdict(world)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(world_data, f, ensure_ascii=False, indent=4)
            self.report_progress("Мир успешно сохранен.")
            return filepath
        except Exception as e:
            self.report_progress(f"[!!!] Критическая ошибка при сохранении мира: {e}")
            return None