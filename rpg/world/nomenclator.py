# rpg/world/nomenclator.py
import json
from ..ai_helper import AIHelper

class Nomenclator:
    """
    Класс-помощник, использующий ИИ для генерации названий и описаний
    в рамках заданного контекста мира.
    """
    def __init__(self):
        self.ai_helper = AIHelper()

    def generate_names(self, entity_type: str, context: str, count: int = 1) -> list[str]:
        """Генерирует список имен для сущности с учетом контекста."""
        prompt = f"""
        Сгенерируй {count} уникальных, фэнтезийных или научно-фантастических названий для сущности типа '{entity_type}'.
        Контекст мира: {context}.
        
        Требования:
        1. Названия должны соответствовать контексту.
        2. Избегай банальных клише.
        3. Верни ТОЛЬКО JSON-объект с одним ключом "names", который содержит массив строк.

        Пример ответа:
        {{
            "names": ["Архория", "Хребет Заката", "Этериевы Шпили"]
        }}
        """
        try:
            response = self.ai_helper.client.chat.completions.create(
                model=self.ai_helper.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            # Извлекаем JSON-строку
            json_string = response.choices[0].message.content
            # Парсим JSON и извлекаем список по ключу "names"
            data = json.loads(json_string)
            names = data.get("names", [])
            # Проверяем, что результат - это список строк
            if isinstance(names, list) and all(isinstance(n, str) for n in names):
                return names
            else:
                # Если формат неверный, возвращаем заглушку
                raise ValueError("AI returned data in unexpected format.")
        except Exception as e:
            print(f"[Nomenclator Warning] AI name generation failed: {e}. Using fallback.")
            # Возвращаем простые имена-заглушки в случае ошибки
            return [f"{entity_type.capitalize()} {i+1}" for i in range(count)]

    def generate_description(self, entity_name: str, entity_type: str, context: str) -> str:
        """Генерирует краткое художественное описание для сущности."""
        prompt = f"""
        Напиши краткое (2-4 предложения) художественное описание для сущности.

        Название: {entity_name}
        Тип сущности: {entity_type}
        Контекст мира: {context}

        Требования:
        1. Описание должно быть атмосферным и интригующим.
        2. Верни ТОЛЬКО текст описания, без лишних фраз и JSON-форматирования.
        """
        try:
            response = self.ai_helper.client.chat.completions.create(
                model=self.ai_helper.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Nomenclator Warning] AI description generation failed: {e}. Using fallback.")
            return f"Это место, известное как {entity_name}, хранит много тайн."