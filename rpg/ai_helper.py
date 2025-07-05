# rpg/ai_helper.py
import os
import json
from openai import OpenAI
from .rules import RulesEngine # Импортируем движок правил

PROMPT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'character_generator_prompt.txt')

class AIHelper:
    def __init__(self):
        # Загружает ключи из .env файла в корне проекта
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_API_BASE"))
        self.model = os.getenv("SELECTED_MODEL", "openai/gpt-4o")
        
        # Загружаем ШАБЛОН промпта
        with open(PROMPT_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            self.prompt_template = f.read()
            
        # Используем RulesEngine для доступа к игровым данным
        self.rules_engine = RulesEngine()

    def generate_character_details(self, user_wish: str) -> dict:
        """
        Собирает полный промпт с данными и отправляет запрос к ИИ.
        """
        # --- НОВАЯ ЛОГИКА: ДИНАМИЧЕСКАЯ СБОРКА ПРОМПТА ---
        
        # 1. Получаем данные из движка правил
        traits_for_prompt = self.rules_engine.traits_data
        
        # Собираем все предметы в один список для простоты
        items_for_prompt = []
        if isinstance(self.rules_engine.items_data, dict):
            for category_items in self.rules_engine.items_data.values():
                items_for_prompt.extend(category_items)

        # 2. Превращаем данные в JSON-строки
        traits_json_string = json.dumps(traits_for_prompt, ensure_ascii=False)
        items_json_string = json.dumps(items_for_prompt, ensure_ascii=False)
        
        # 3. Вставляем JSON-строки в шаблон промпта
        system_prompt = self.prompt_template.replace("{{TRAITS_JSON}}", traits_json_string)
        system_prompt = system_prompt.replace("{{ITEMS_JSON}}", items_json_string)
        
        # --- КОНЕЦ НОВОЙ ЛОГИКИ ---
        
        try:
            print("Отправка запроса к ИИ для генерации персонажа...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_wish}
                ],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            print("Ответ от ИИ получен.")
            return json.loads(content)
        except Exception as e:
            print(f"Ошибка при генерации данных персонажа: {e}")
            return {"error": str(e)}