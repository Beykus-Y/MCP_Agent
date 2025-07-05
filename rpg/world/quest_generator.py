# rpg/world/quest_generator.py
import json
from typing import Optional, List, Dict

from ..ai_helper import AIHelper
from ..world.world_state import WorldState, PointOfInterest
from ..models import Quest, NPC # <--- импортируем NPC

PROMPT_TEMPLATE_PATH = "rpg/prompts/quest_generator_prompt.txt"

class QuestGenerator:
    def __init__(self):
        self.ai_helper = AIHelper()
        with open(PROMPT_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            self.prompt_template = f.read()

    def generate_quest_for_location(self, world: WorldState, location: PointOfInterest, existing_quests: List[Quest]) -> Optional[Dict]:
        """
        Генерирует уникальный квест и возвращает СЛОВАРЬ с данными (включая диалог).
        """
        print(f"Запрос на генерацию квеста для локации '{location.name}'...")
        
        world_context = self._build_world_context(world)
        existing_quests_context = self._build_existing_quests_context(existing_quests)
        location_npcs_context = self._build_location_npcs_context(location.npcs)
        
        prompt = self.prompt_template.replace("{{WORLD_CONTEXT}}", world_context)
        prompt = prompt.replace("{{EXISTING_QUESTS_CONTEXT}}", existing_quests_context)
        prompt = prompt.replace("{{LOCATION_NAME}}", location.name)
        prompt = prompt.replace("{{LOCATION_NPCS}}", location_npcs_context)
        
        try:
            response = self.ai_helper.client.chat.completions.create(
                model=self.ai_helper.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.8
            )
            # Возвращаем весь JSON-ответ, как он есть
            response_data = json.loads(response.choices[0].message.content)
            print(f"ИИ сгенерировал ответ на запрос квеста.")
            return response_data
        except Exception as e:
            print(f"Ошибка при генерации квеста: {e}")
            return None

    def _build_world_context(self, world: WorldState) -> str:
        context = f"НАЗВАНИЕ МИРА: {world.world_name}, ТЕКУЩИЙ ГОД: {world.year}\n"
        context += f"ИСТОРИЯ: {' '.join(world.history_log)}\n\n"
        context += "ФРАКЦИИ:\n"
        for faction in world.factions:
            context += f"- {json.dumps(faction.__dict__, ensure_ascii=False)}\n"
        context += "\nКЛЮЧЕВЫЕ ЛОКАЦИИ:\n"
        for poi in world.points_of_interest:
            poi_dict = {"id": poi.id, "name": poi.name, "type": poi.type}
            context += f"- {json.dumps(poi_dict, ensure_ascii=False)}\n"
        return context

    def _build_existing_quests_context(self, quests: List[Quest]) -> str:
        if not quests: return "Пока нет активных или выполненных квестов."
        context = ""
        for quest in quests:
            quest_info = {"id": quest.id, "name": quest.name, "status": quest.status}
            context += f"- {json.dumps(quest_info, ensure_ascii=False)}\n"
        return context

    def _build_location_npcs_context(self, npcs: List[NPC]) -> str:
        """Собирает информацию о NPC в текущей локации."""
        if not npcs: return "В этой локации нет ключевых жителей."
        context = ""
        for npc in npcs:
            context += f"- {json.dumps(npc.__dict__, ensure_ascii=False)}\n"
        return context