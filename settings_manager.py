# settings_manager.py
import json
import os

class SettingsManager:
    def __init__(self, settings_file="settings.json"):
        self.settings_file = settings_file
        # ИЗМЕНЕНО: Добавляем настройку темы
        self.defaults = {
            "font_size_chat": 12,
            "font_size_logs": 10,
            "color_theme": "light" # По умолчанию светлая тема
        }
        self.settings = self.load_settings()

    def load_settings(self):
        """Загружает настройки из файла или возвращает значения по умолчанию."""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    # Убедимся, что все ключи из defaults есть в загруженных настройках
                    loaded_settings = json.load(f)
                    # Добавляем недостающие ключи из defaults, если их нет
                    settings = self.defaults.copy()
                    settings.update(loaded_settings)
                    return settings
            except (json.JSONDecodeError, TypeError):
                return self.defaults.copy()
        return self.defaults.copy()

    def save_settings(self):
        """Сохраняет текущие настройки в файл."""
        with open(self.settings_file, 'w') as f:
            json.dump(self.settings, f, indent=4)

    def get(self, key):
        """Получает значение настройки по ключу."""
        return self.settings.get(key, self.defaults.get(key))

    def set(self, key, value):
        """Устанавливает значение настройки."""
        self.settings[key] = value