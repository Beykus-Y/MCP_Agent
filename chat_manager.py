# chat_manager.py (Версия 2.0 - с поддержкой мультимодальных сообщений)
import os
import json
import time
from datetime import datetime

class ChatManager:
    def __init__(self, chats_dir="chats"):
        self.chats_dir = chats_dir
        if not os.path.exists(self.chats_dir):
            os.makedirs(self.chats_dir)

    def _generate_id(self):
        """Генерирует уникальный ID на основе текущего времени."""
        return str(int(time.time() * 1000))

    def get_chats(self):
        """Сканирует директорию и возвращает список чатов (id, title), отсортированных по дате."""
        chats = []
        for filename in os.listdir(self.chats_dir):
            if filename.endswith(".json"):
                try:
                    chat_id = filename.split('.')[0]
                    path = os.path.join(self.chats_dir, filename)
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Получаем заголовок. Он может быть строкой или (из-за бага) списком.
                    title = data.get("title", "Без названия")
                    if isinstance(title, list):
                        # Аварийный обработчик для чатов, которые уже были сохранены с багом
                        title = "Поврежденный заголовок"

                    chats.append({
                        "id": chat_id,
                        "title": title
                    })
                except (json.JSONDecodeError, IndexError):
                    print(f"Ошибка чтения файла чата: {filename}")
                    continue
        
        # Сортируем по ID (т.к. это timestamp), от новых к старым
        chats.sort(key=lambda x: int(x['id']), reverse=True)
        return chats

    def load_chat_history(self, chat_id):
        """Загружает историю сообщений для конкретного чата."""
        path = os.path.join(self.chats_dir, f"{chat_id}.json")
        if not os.path.exists(path):
            return [], "Новый чат"
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        title = data.get("title", "Без названия")
        if isinstance(title, list):
            title = "Поврежденный заголовок"
            
        return data.get("messages", []), title

    def save_chat(self, chat_id, messages, title=None):
        """Сохраняет или обновляет чат."""
        if not chat_id:
            chat_id = self._generate_id()
        
        # --- ИСПРАВЛЕНО: Умная генерация заголовка ---
        if not title:
            # Автоматически генерируем заголовок из первого сообщения пользователя
            for msg in messages:
                if msg.get('role') == 'user':
                    content = msg.get('content')
                    
                    # Проверяем, старый формат (строка) или новый (список)
                    if isinstance(content, list):
                        # Ищем текстовую часть в новом формате
                        for part in content:
                            if part.get('type') == 'text':
                                title = part.get('text', '')[:50].strip()
                                break # Нашли текст, выходим из внутреннего цикла
                    elif isinstance(content, str):
                        # Обрабатываем старый формат
                        title = content[:50].strip()
                    
                    if title: # Если заголовок найден (не пустой), выходим из внешнего цикла
                        break
            
            if not title:
                title = "Новый чат " + datetime.fromtimestamp(int(chat_id)/1000).strftime('%Y-%m-%d %H:%M')

        path = os.path.join(self.chats_dir, f"{chat_id}.json")
        data = {
            "title": title,
            "messages": messages
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        return chat_id, title

    def delete_chat(self, chat_id):
        """Удаляет файл чата."""
        path = os.path.join(self.chats_dir, f"{chat_id}.json")
        if os.path.exists(path):
            os.remove(path)
            return True
        return False