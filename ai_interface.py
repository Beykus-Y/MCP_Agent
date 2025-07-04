# ai_interface.py (Версия 5.0 - с Иерархическими Агентами)

import os
import json
import requests
import copy
import logging
from dotenv import load_dotenv
from openai import OpenAI
from PyQt5 import QtCore


def _sanitize_log_data(data):
    """Рекурсивно очищает данные для логирования, заменяя base64 на заменитель."""
    if not isinstance(data, (dict, list)):
        return data

    # Создаем глубокую копию, чтобы не изменять оригинальные данные
    log_data = copy.deepcopy(data)

    if isinstance(log_data, list):
        return [_sanitize_log_data(item) for item in log_data]

    # Обрабатываем словари
    for key, value in log_data.items():
        if isinstance(value, str) and value.startswith('data:image'):
            log_data[key] = f"<base64_image_data len={len(value)}>"
        elif isinstance(value, (dict, list)):
            log_data[key] = _sanitize_log_data(value)
            
    return log_data

class MCPServer:
    """
    Представляет собой клиент для одного MCP-сервера.
    """
    def __init__(self, name: str, url: str, headers=None):
        self.name = name
        self.url = url.rstrip("/") + "/mcp"
        self.headers = headers or {}
        self.id_counter = 1

    def call(self, method: str, params: dict):
        """Выполняет вызов метода на удаленном MCP-сервере."""
        payload = {
            "jsonrpc": "2.0",
            "id": self.id_counter,
            "method": method,
            "params": params
        }
        self.id_counter += 1
        
        # ИСПРАВЛЕНО: Используем очищенные данные для логирования
        log_params = _sanitize_log_data(params)
        logging.info(f"AGENT_CALL -> {self.name}: method={method}, params={json.dumps(log_params)}")
        
        resp = requests.post(self.url, json=payload, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP {self.name} error: {data['error']['message']} (code: {data['error']['code']})")
        
        # ИСПРАВЛЕНО: Логируем и результат тоже, предварительно очистив
        log_result = _sanitize_log_data(data.get('result'))
        logging.info(f"AGENT_CALL <- {self.name}: result={json.dumps(log_result)}")
        
        return data.get("result")

class AIWithMCPInterface(QtCore.QObject):
    """
    Универсальный "движок" для ИИ-агентов. Может быть настроен как Оркестратор
    или как узкоспециализированный суб-агент с помощью разных промптов и наборов инструментов.
    """
    action_started = QtCore.pyqtSignal(str)

    # ### ИЗМЕНЕНО: Конструктор теперь принимает путь к промпту и фильтры ###
    def __init__(self, client: OpenAI, prompt_path: str, all_mcp_servers: dict, allowed_mcp_filter: list = None):
        """
        Инициализирует агента.
        :param client: Клиент OpenAI.
        :param prompt_path: Путь к текстовому файлу с системным промптом.
        :param all_mcp_servers: Словарь ВСЕХ доступных MCP-серверов в системе.
        :param allowed_mcp_filter: Список ключей MCP (например, ['rpg', 'files']), которые
                                   разрешено использовать ЭТОМУ конкретному агенту.
                                   Если None, разрешены все.
        """
        super().__init__()
        load_dotenv()
        self.client = client
        self._load_model()
        self.system_prompt = self._load_prompt(prompt_path)
        
        # Этот словарь содержит все возможные MCP.
        self.ALL_MCP_SERVERS = all_mcp_servers
        
        # А эти словари - только те, что разрешены данному агенту.
        self.mcp_servers = {}
        self.functions = []
        self._function_to_server_map = {}
        
        # ### НОВОЕ: Локальные инструменты, определенные в коде, а не через MCP ###
        # Оркестратор будет использовать это для вызова суб-агентов.
        self.local_tools = {
            "execute_rpg_task": self.execute_rpg_task,
            "show_image_in_chat": self.show_image_in_chat
            # ... другие инструменты :
        }
        self.local_tools_schema = [
            {
                "name": "execute_rpg_task",
                "description": "Делегирует сложную задачу, связанную с ролевой игрой (RPG), специализированному RPG-агенту. Используй для ВСЕХ RPG-запросов.",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "task_description": {
                            "type": "string", 
                            "description": "Четкое и полное описание задачи для RPG-агента. Например: 'Узнай, где находится игрок и что он видит'."
                        }
                    }, 
                    "required": ["task_description"]
                }
            },
            {
                "name": "show_image_in_chat",
                "description": "Показывает пользователю изображение прямо в окне чата. Используй эту функцию, когда пользователь просит что-то показать, или когда визуальное представление информации будет полезно. Всегда предоставляй прямой URL изображения.",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "image_url": {
                            "type": "string", 
                            "description": "Прямая ссылка (URL) на изображение (например, с окончанием .jpg, .png, .webp)."
                        },
                        "caption": {
                            "type": "string",
                            "description": "Краткое описание того, что изображено на картинке."
                        }
                    }, 
                    "required": ["image_url", "caption"]
                }
            }
        ]
        
        # Регистрируем разрешенные MCP
        self._register_allowed_mcps(allowed_mcp_filter)


    def _load_model(self):
        load_dotenv(override=True)
        self.model = os.getenv("SELECTED_MODEL", "openai/gpt-4o")

    def _load_prompt(self, prompt_path):
        """Загружает системный промпт из файла."""
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logging.error(f"Критическая ошибка: Файл промпта не найден по пути: {prompt_path}")
            # Возвращаем простой промпт по умолчанию, чтобы избежать падения
            return "Ты — полезный ассистент."
        
    def find_and_show_image(self, params: dict) -> str:
        """
        Инструмент-обертка, который ищет картинку в вебе и вызывает другой инструмент для ее отображения.
        """
        query = params.get("query")
        if not query:
            return "Ошибка: поисковый запрос не предоставлен."

        web_server = self.mcp_servers.get("web")
        if not web_server:
            return "Ошибка: MCP-сервер 'web' не доступен для этого агента."

        try:
            self.action_started.emit(f"Ищу картинку: {query}...")
            # Шаг 1: Навигация (логика спрятана здесь)
            search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}&tbm=isch"
            web_server.call("navigate_to_url", {"url": search_url})
            
            # Шаг 2: Поиск изображений
            self.action_started.emit("Анализирую страницу с результатами...")
            result = web_server.call("find_images_on_page", {})
            
            images = result.get("images")
            if not images:
                return "Не удалось найти подходящих изображений по вашему запросу."
            
            # Шаг 3: Парсинг результата и выбор картинки (логика спрятана здесь)
            first_image = images[0]
            image_url = first_image.get("src")
            caption = first_image.get("alt", query)

            if not image_url:
                return "Найдено изображение, но у него нет URL."

            self.action_started.emit("Отображаю найденное изображение...")
            # Шаг 4: Вызов ДРУГОГО локального инструмента для формирования ответа для GUI
            return self.show_image_in_chat({"image_url": image_url, "caption": caption})

        except Exception as e:
            logging.error(f"Ошибка в инструменте find_and_show_image: {e}")
            return f"Произошла ошибка во время поиска изображения: {e}"

    def _register_allowed_mcps(self, filter_list: list = None):
        """
        Регистрирует только те MCP, которые разрешены фильтром.
        """
        # Если фильтр не задан, разрешаем все MCP.
        if filter_list is None:
            filter_list = self.ALL_MCP_SERVERS.keys()

        for name, url in self.ALL_MCP_SERVERS.items():
            if name in filter_list:
                try:
                    logging.info(f"Агент регистрирует MCP '{name}'...")
                    functions_url = url.rstrip("/") + "/functions"
                    resp = requests.get(functions_url, timeout=5)
                    resp.raise_for_status()
                    
                    mcp_functions = resp.json()
                    
                    self.mcp_servers[name] = MCPServer(name, url)
                    self.functions.extend(mcp_functions)
                    for func in mcp_functions:
                        self._function_to_server_map[func['name']] = name
                except Exception as e:
                    logging.error(f"Ошибка при регистрации MCP '{name}' для агента: {e}")

    

    # ### НОВОЕ: Реализация локального инструмента ###
    def execute_rpg_task(self, params: dict) -> str:
        """
        Метод-инструмент. Создает и запускает узкоспециализированного RPG-агента.
        Вызывается Оркестратором.
        """
        task_description = params.get("task_description")
        if not task_description:
            return "Ошибка: задача для RPG-агента не была предоставлена."

        logging.info(f"--- [DELEGATING TO RPG AGENT] --- Задача: {task_description}")
        self.action_started.emit("Запускаю RPG-агента для выполнения задачи...")

        # 1. Создаем экземпляр RPG-агента
        rpg_agent = AIWithMCPInterface(
            client=self.client,
            prompt_path="prompts/rpg_agent_prompt.txt",
            all_mcp_servers=self.ALL_MCP_SERVERS,
            allowed_mcp_filter=["rpg"] # <-- Ключевой момент: разрешаем ему только RPG-инструменты
        )
        
        # 2. Убираем у суб-агента возможность вызывать других суб-агентов, чтобы избежать рекурсии
        rpg_agent.local_tools = {}
        rpg_agent.local_tools_schema = []
        
        # 3. Запускаем его с одной единственной задачей от Оркестратора
        initial_history = [{"role": "user", "content": task_description}]
        result = rpg_agent.call_ai(initial_history)
        
        logging.info(f"--- [RPG AGENT FINISHED] --- Результат: {result}")
        self.action_started.emit("RPG-агент завершил работу.")

        gui_command = {
       "gui_tool": "display_text", # Новый тип gui_tool для текстового ответа
        "params": {
        "text": result # Текст от RPG-агента
            }
        }
        
        # 4. Возвращаем текстовый результат как итог работы нашего инструмента
        logging.info(f"Агент сгенерировал команду для GUI: {gui_command}")
        return json.dumps(gui_command)

    def show_image_in_chat(self, params: dict) -> str:
        """
        Этот метод не выполняет логику сам, а форматирует специальную команду для GUI,
        которая будет перехвачена и обработана в UI.py.
        """
        url = params.get("image_url")
        caption = params.get("caption", "Изображение от ИИ")

        # Формируем специальный JSON-ответ, который распознает GUI
        gui_command = {
            "gui_tool": "display_image",
            "params": {
                "url": url,
                "caption": caption
            }
        }
        logging.info(f"Агент сгенерировал команду для GUI: {gui_command}")
        # Возвращаем эту строку. UI.py ее поймает.
        return json.dumps(gui_command)

    def call_ai(self, history: list, **kwargs) -> str:
        """Основной цикл работы агента."""
        self._load_model()
        messages = [{"role": "system", "content": self.system_prompt}] + history
        
        # Агент видит только разрешенные ему инструменты
        available_tools = self.functions + self.local_tools_schema
        
        MAX_AGENT_TURNS = 10 # Ограничение, чтобы избежать бесконечных циклов
        for i in range(MAX_AGENT_TURNS):
            logging.info(f"Агент (итерация {i+1}). История: {len(messages)} сообщений.")
            
            # Вызов LLM
            response = self.client.chat.completions.create(
                model=self.model, 
                messages=messages, 
                tools=[{"type": "function", "function": f} for f in available_tools], 
                tool_choice="auto", 
                **kwargs
            )
            message_obj = response.choices[0].message
            
            # Если нет вызова инструментов, а есть текст - это финальный ответ
            if not message_obj.tool_calls and message_obj.content:
                logging.info("Агент завершил работу и предоставил финальный текстовый ответ.")
                self.action_started.emit("") # Очищаем статус
                return message_obj.content

            # Добавляем ответ модели в историю
            messages.append(json.loads(message_obj.model_dump_json(exclude_none=True)))
            
            # Проверяем, есть ли что выполнять
            if not message_obj.tool_calls:
                logging.warning("Агент завершил работу без ответа или вызова инструмента.")
                break

            # Обрабатываем вызовы инструментов
            for tool_call in message_obj.tool_calls:
                func_name = tool_call.function.name
                try:
                    func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    result = f"Ошибка: неверный JSON в аргументах для функции {func_name}."
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": result})
                    continue

                tool_call_id = tool_call.id
                result = None

                # Выбираем, какой инструмент вызвать: локальный или удаленный MCP
                if func_name in self.local_tools:
                    self.action_started.emit(f"Выполняю задачу: {func_name}...")
                    result = self.local_tools[func_name](func_args)
                elif func_name in self._function_to_server_map:
                    self.action_started.emit(f"Вызываю MCP: {func_name}...")
                    server_name = self._function_to_server_map[func_name]
                    result = self.mcp_servers[server_name].call(func_name, func_args)
                else:
                    result = f"Критическая ошибка: инструмент '{func_name}' не найден в доступных для этого агента."

                # ### НАЧАЛО ИСПРАВЛЕНИЯ ###
                # Проверяем, не является ли результат вызова инструмента финальной командой для GUI.
                # `show_image_in_chat` возвращает именно такую команду в виде JSON-строки.
                is_gui_command = False
                if isinstance(result, str):
                    try:
                        parsed_result = json.loads(result)
                        if isinstance(parsed_result, dict) and "gui_tool" in parsed_result:
                            is_gui_command = True
                    except (json.JSONDecodeError, TypeError):
                        pass # Это обычный строковый результат, а не JSON-команда.

                if is_gui_command:
                    # Если это команда для GUI - это и есть финальный ответ.
                    # Немедленно возвращаем его, не продолжая цикл.
                    logging.info("Агент сгенерировал финальную команду для GUI. Завершение работы.")
                    self.action_started.emit("") # Очищаем статус
                    return result # Возвращаем JSON-строку как есть
                # ### КОНЕЦ ИСПРАВЛЕНИЯ ###

                messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": func_name, "content": json.dumps(result, ensure_ascii=False)})

        logging.warning("Достигнут лимит итераций, или агент не смог дать финальный ответ.")
        return "К сожалению, я не смог завершить задачу. Попробуйте переформулировать запрос."