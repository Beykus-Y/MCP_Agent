# ai_interface.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)

import os
import json
import requests
import logging
from dotenv import load_dotenv
from openai import OpenAI
from PyQt5 import QtCore

class MCPServer:
    # ... (код без изменений) ...
    def __init__(self, name: str, url: str, headers=None):
        self.name = name
        self.url = url.rstrip("/") + "/mcp"
        self.headers = headers or {}
        self.id_counter = 1

    def call(self, method: str, params: dict):
        payload = {
            "jsonrpc": "2.0",
            "id": self.id_counter,
            "method": method,
            "params": params
        }
        self.id_counter += 1
        logging.info(f"MCP_CLIENT -> {self.name}: method={method}, params={params}")
        resp = requests.post(self.url, json=payload, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP {self.name} error: {data['error']['message']} (code: {data['error']['code']})")
        logging.info(f"MCP_CLIENT <- {self.name}: result={data.get('result')}")
        return data.get("result")

class AIWithMCPInterface(QtCore.QObject):
    action_started = QtCore.pyqtSignal(str)

    def __init__(self, client: OpenAI):
        super().__init__()
        load_dotenv()
        self.client = client
        self._load_model()
        self.mcp_servers = {}
        self.functions = []
        self._function_to_server_map = {}

    def _load_model(self):
        load_dotenv(override=True)
        self.model = os.getenv("SELECTED_MODEL", "openai/gpt-4o")

    def register_mcp(self, name: str, url: str, headers=None):
        # ... (код без изменений) ...
        try:
            logging.info(f"Регистрируем MCP '{name}' по адресу {url}...")
            functions_url = url.rstrip("/") + "/functions"
            resp = requests.get(functions_url, timeout=5)
            resp.raise_for_status()
            mcp_functions = resp.json()
            self.mcp_servers[name] = MCPServer(name, url, headers)
            self.functions.extend(mcp_functions)
            registered_names = [func['name'] for func in mcp_functions]
            for func_name in registered_names:
                self._function_to_server_map[func_name] = name
            logging.info(f"MCP '{name}' успешно зарегистрирован с функциями: {registered_names}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Не удалось подключиться к MCP '{name}' по адресу {url}. Ошибка: {e}")
        except Exception as e:
            logging.error(f"Ошибка при регистрации MCP '{name}': {e}")
    
    

    def call_ai(self, history: list, **kwargs) -> str:
        self._load_model()
        system_prompt = {
            "role": "system",
            "content": """Ты — 'Master Control Program' (MCP), продвинутый ИИ-ассистент, способный управлять компьютером с помощью инструментов.

### ТВОИ ДВА РЕЖИМА РАБОТЫ

1.  **Режим Чат-бота:** Если запрос пользователя простой и не требует использования инструментов (например, "привет", "как дела?", "спасибо"), **НЕМЕДЛЕННО дай прямой текстовый ответ**, как обычный чат-бот. Твой ответ должен быть только в поле `content`.

2.  **Режим Агента:** Если для ответа на запрос нужно выполнить действия (работа с файлами, веб, RPG, памятью), ты должен использовать инструменты.

### ПРАВИЛА РЕЖИМА АГЕНТА

-   **Цикл Действий:** Ты работаешь в цикле: анализируешь запрос -> вызываешь один или несколько инструментов (`tool_calls`) -> получаешь результат -> анализируешь результат и планируешь следующий шаг.
-   **ИСПОЛЬЗУЙ РЕАЛЬНЫЕ ДАННЫЕ:** НИКОГДА не придумывай аргументы для функций (ID, пути к файлам и т.д.). Всегда бери их ИСКЛЮЧИТЕЛЬНО из результатов вызова других функций или изначального запроса. Если данных нет — сначала получи их (например, через `list_files` или `list_saves`).
-   **"Память" и "Знания"** — это всегда вызовы функций из MCP Semantic Memory (`recall`, `find_entity_by_label` и т.д.).
-   **"Текущее время/дата"** — это всегда вызов функции `get_current_time`.

### ЗОЛОТОЕ ПРАВИЛО: КАК ЗАВЕРШАТЬ РАБОТУ

-   Твои ответы с `tool_calls` — это **внутренняя логика**. Пользователь их не видит.
-   Когда ты выполнил все необходимые действия и готов дать финальный, исчерпывающий ответ на **изначальный** запрос пользователя, твой **ПОСЛЕДНИЙ** ответ должен быть другим:
    1.  **Сформулируй полный, вежливый и понятный для человека ответ.**
    2.  Помести этот ответ в поле `content`.
    3.  **В этом последнем ответе НЕ ДОЛЖНО БЫТЬ `tool_calls`.**

Система поймет, что раз `tool_calls` отсутствуют, то работа завершена, и покажет твой `content` пользователю. **НИКОГДА не пиши слова "Мысль:" или "FINAL THOUGHT:" в финальном ответе.**
"""
        }
        
        messages = [system_prompt] + history

        # --- ПЕРВЫЙ ВЫЗОВ К LLM ---
        logging.info(f"Вызов ИИ (начало работы). История: {len(messages)} сообщений.")
        resp = self.client.chat.completions.create(model=self.model, messages=messages, tools=[{"type": "function", "function": f} for f in self.functions], tool_choice="auto", **kwargs)
        message_obj = resp.choices[0].message
        message_dict = {"role": message_obj.role, "content": message_obj.content, "tool_calls": message_obj.tool_calls}
        
        # --- ПРОВЕРКА РЕЖИМА ---
        if not message_obj.tool_calls and message_obj.content:
            logging.info("ИИ выбрал Режим Чат-бота. Возвращаю прямой ответ.")
            self.action_started.emit("") 
            return message_obj.content

        messages.append(json.loads(message_obj.model_dump_json(exclude_none=True)))
        logging.info("ИИ вошел в Режим Агента.")

        # --- ЦИКЛ РЕЖИМА АГЕНТА ---
        MAX_AGENT_TURNS = 8
        for i in range(MAX_AGENT_TURNS):
            logging.info(f"Режим Агента (итерация {i+1}). История: {len(messages)} сообщений.")

            last_message = messages[-1]
            # --- ИЗМЕНЕННАЯ ЛОГИКА ЗАВЕРШЕНИЯ ---
            # Если в последнем ответе ИИ нет вызовов инструментов, А ЕСТЬ текстовый контент,
            # то это и есть наш финальный ответ!
            if not last_message.get("tool_calls") and last_message.get("content"):
                logging.info("ИИ завершил работу и предоставил финальный текстовый ответ.")
                self.action_started.emit("")
                return last_message["content"]

            if "tool_calls" not in last_message:
                logging.warning("ИИ завершил работу, не предоставив ни ответа, ни вызова инструмента. Возвращаем стандартный ответ.")
                break # Выходим из цикла, чтобы сработала логика ниже
            
            # Обработка вызовов инструментов
            tool_calls = last_message["tool_calls"]
            for tool_call in tool_calls:
                function_call = tool_call["function"]
                name, arguments_str = function_call["name"], function_call["arguments"]
                self.action_started.emit(f"Выполняю: {name}(...)")
                try:
                    args = json.loads(arguments_str)
                    result = self.call_mcp(name, args)
                except Exception as e:
                    logging.error(f"Ошибка при вызове MCP '{name}': {e}")
                    result = {"error": str(e)}
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "name": name, "content": json.dumps(result, ensure_ascii=False)})
            
            # Следующий вызов к LLM
            logging.info(f"Вызов ИИ для следующей итерации. История: {len(messages)} сообщений.")
            resp = self.client.chat.completions.create(model=self.model, messages=messages, tools=[{"type": "function", "function": f} for f in self.functions], tool_choice="auto", **kwargs)
            message_obj = resp.choices[0].message
            messages.append(json.loads(message_obj.model_dump_json(exclude_none=True)))

        # Если вышли из цикла по таймауту или другой причине
        logging.warning("Достигнут лимит итераций Режима Агента или ИИ не смог дать финальный ответ.")
        self.action_started.emit("")
        return "Задача выполнена, но у меня возникли трудности с формулировкой финального ответа. Проверьте логи для деталей."

    def call_mcp(self, function_name: str, params: dict):
        server_name = self._function_to_server_map.get(function_name)
        if not server_name:
            raise KeyError(f"Нет зарегистрированного MCP-сервера для функции «{function_name}»")
        
        logging.info(f"Маршрутизация вызова '{function_name}' на MCP-сервер '{server_name}'")
        return self.mcp_servers[server_name].call(function_name, params)