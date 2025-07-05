# rpg/world/history.py
import random
import json
import os
from .world_state import Faction, PointOfInterest
from ..models import NPC
# Загружаем данные для генерации NPC один раз
BASE_DIR = os.path.join(os.path.dirname(__file__), '..', 'game_data')
try:
    with open(os.path.join(BASE_DIR, 'names.json'), 'r', encoding='utf-8') as f:
        NAMES_DATA = json.load(f)
    with open(os.path.join(BASE_DIR, 'professions.json'), 'r', encoding='utf-8') as f:
        PROFESSIONS_DATA = json.load(f)
except FileNotFoundError:
    print("[History Generator Warning] names.json или professions.json не найдены. NPC не будут сгенерированы.")
    NAMES_DATA = {"male": [], "female": [], "unisex": []}
    PROFESSIONS_DATA = []

def _generate_npcs_for_location(poi_type: str, count: int) -> list[NPC]:
    """Генерирует список NPC для локации."""
    npcs = []
    # NPC генерируются только для городов и столиц
    available_professions = [p for p in PROFESSIONS_DATA if poi_type in ['capital', 'town']]
    if not available_professions or not any(NAMES_DATA.values()):
        return []

    for _ in range(count):
        gender = random.choice(['male', 'female'])
        name = random.choice(NAMES_DATA.get(gender, ["Житель"]))
        profession_data = random.choice(available_professions)
        npcs.append(NPC(name=name, profession=profession_data['name']))
    return npcs

def generate_history(world_map, nomenclator, params: dict, report_progress):
    factions = []
    pois = []
    history_log = []
    width, height = len(world_map[0]), len(world_map)
    start_year = params.get('year', 1000)

    report_progress("Определение стартовых цивилизаций...")
    chosen_civs = params.get('civilizations', [])
    
    for i, civ_spec in enumerate(chosen_civs):
        context = (
            f"Уровень технологий: {params['tech_level']}. "
            f"Уровень магии: {params['magic_level']}. "
            f"Описание цивилизации: {civ_spec['description']}"
        )
        report_progress(f"ИИ придумывает название для цивилизации '{civ_spec['name']}'...")
        faction_name = nomenclator.generate_names(civ_spec["name"], context, 1)[0]
        faction = Faction(id=f"faction_{i}", name=faction_name, type=civ_spec["id"], description=context)
        factions.append(faction)
        history_log.append(f"Год {start_year - random.randint(400, 600)}: Зародилась цивилизация '{faction_name}'.")

        report_progress(f"Поиск подходящего места для столицы '{faction_name}'...")
        preferred_biomes = []
        civ_id = civ_spec.get('id', '')
        if civ_id == 'ancient_elves': preferred_biomes = ['forest', 'jungle']
        elif civ_id == 'nomad_horde': preferred_biomes = ['grassland', 'temperate_desert']
        else: preferred_biomes = ['grassland', 'forest', 'beach']

        capital_placed = False
        for _ in range(200):
            x, y = random.randint(0, width - 1), random.randint(0, height - 1)
            if world_map[y][x] in preferred_biomes:
                report_progress(f"ИИ придумывает название для столицы...")
                capital_name = nomenclator.generate_names("Столица", f"Столица для нации '{faction_name}'", 1)[0]
                
                # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
                capital = PointOfInterest(
                    id=f"poi_capital_{i}", # Добавляем уникальный ID
                    name=capital_name,
                    type="capital",
                    position=(x, y),
                    controlling_faction_id=faction.id
                )
                
                num_npcs = random.randint(2, 4)
                capital.npcs = _generate_npcs_for_location(capital.type, num_npcs)
                report_progress(f"Заселение столицы '{capital.name}' {len(capital.npcs)} жителями...")
                
                pois.append(capital)
                history_log.append(f"Год {start_year - random.randint(300, 400)}: Они основали столицу '{capital_name}' в точке ({x}, {y}).")
                capital_placed = True
                break
        
        if not capital_placed:
            history_log.append(f"[!] Не удалось найти подходящее место для столицы '{faction_name}'.")

    if len(factions) >= 2:
        report_progress("Симуляция древних конфликтов...")
        f1, f2 = random.sample(factions, 2)
        history_log.append(f"Год {start_year - random.randint(100, 200)}: Разразилась великая война между '{f1.name}' и '{f2.name}'.")
        
        p1_obj = next((p for p in pois if p.controlling_faction_id == f1.id), None)
        p2_obj = next((p for p in pois if p.controlling_faction_id == f2.id), None)

        if p1_obj and p2_obj:
            report_progress("Создание древних руин на месте битвы...")
            p1, p2 = p1_obj.position, p2_obj.position
            ruin_x, ruin_y = (p1[0] + p2[0]) // 2 + random.randint(-5, 5), (p1[1] + p2[1]) // 2 + random.randint(-5, 5)
            
            ruin_name = nomenclator.generate_names("Древние руины", f"Место великой битвы между {f1.name} и {f2.name}", 1)[0]
            
            # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
            ruin = PointOfInterest(
                id=f"poi_ruin_{random.randint(100,999)}", # Добавляем уникальный ID
                name=ruin_name,
                type="ruin",
                position=(ruin_x, ruin_y)
            )
            ruin.npcs = _generate_npcs_for_location(ruin.type, random.choice([0, 0, 1]))
            pois.append(ruin)
            history_log.append(f"Поля сражений оставили шрамы на земле. Руины '{ruin_name}' напоминают о тех временах.")

    return factions, pois, history_log