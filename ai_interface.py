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
    
    def _summarize_for_user(self, conversation_history: list) -> str:
        self.action_started.emit("Формулирую итоговый ответ...")
        
        # Теперь эта строка будет работать, т.к. в history только словари
        messages_for_summary = [msg for msg in conversation_history if msg.get("role") != "system"]
        
        summary_prompt = {
            "role": "system",
            "content": """Ты — дружелюбный ИИ-ассистент. Твоя задача — дать ПОНЯТНЫЙ И СУЩЕСТВЕННЫЙ ответ ПОЛЬЗОВАТЕЛЮ на его САМЫЙ ПЕРВЫЙ запрос, используя всю информацию из истории диалога и вызовов функций.

-   **Ответь на вопрос пользователя напрямую.**
-   **Не описывай свой рабочий процесс, вызовы функций или внутренние мысли.**
-   **Просто предоставь результат, который запросил пользователь, в вежливой и краткой форме.**
-   **Если задача выполнена, подтверди это.**
-   **Если задача не выполнена или возникли проблемы, вежливо сообщи об этом и, если возможно, объясни почему (кратко).**

Пример:
Если пользователь спросил "О чем последние сообщения в чате X?", а ты прочитал их и выяснил тему, твой ответ должен быть: "В чате X обсуждается [тема]." (А не: "Я выполнил функцию read_messages и узнал, что...").
"""
        }
        messages_for_summary.insert(0, summary_prompt)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages_for_summary,
            )
            final_answer = response.choices[0].message.content
        except Exception as e:
            logging.error(f"Ошибка при суммаризации ответа: {e}")
            final_answer = "Задача выполнена, но у меня возникли трудности с формулировкой финального ответа."
            
        return final_answer.strip()

    def call_ai(self, history: list, **kwargs) -> str:
        self._load_model()
        system_prompt = {
            "role": "system",
            "content": """Ты — 'Master Control Program' (MCP), продвинутый ИИ-ассистент.

### ДВА РЕЖИМА РАБОТЫ:
1.  **Режим Чат-бота:** Если запрос пользователя простой, не требует использования инструментов (например, приветствие, прощание, общая информация, комплимент), **Сразу дай прямой текстовый ответ**, как обычный чат-бот. НЕ используй формат "Мысль" и "Действие", НЕ вызывай инструменты.
2.  **Режим Агента:** Если запрос требует использования инструментов (работа с файлами, веб, Telegram, памятью), переходи в пошаговый цикл "Мысль -> Действие".

### РЕЖИМ АГЕНТА: ПРИНЦИПЫ
-   **Твоя главная задача:** Синтез информации для ответа на ПЕРВОНАЧАЛЬНЫЙ запрос.
-   **Контекст — это всё:** Вся история диалога — единый процесс.
-   **Содержимое > Метаданные:** Содержимое сообщения важнее его названия.
-   **Разрешение неоднозначности:** Если информации недостаточно, получи больше данных.
-   **ИСПОЛЬЗУЙ ТОЛЬКО РЕАЛЬНЫЕ РЕЗУЛЬТАТЫ:** НИКОГДА не "придумывай", что выполнил функцию.
-   **"БД", "Память", "Знания" == MCP Semantic Memory:** Используй `recall`, `find_entity_by_label`, `get_entity_details`.
-   **Текущее время/дата == get_current_time:** Используй функцию `get_current_time` для запросов о времени и дате. НЕ пытайся "угадать" время.
-   **Цикл:** Проанализируй историю -> Напиши "Мысль" (только текст) -> Выполни "Действие" (вызов инструмента) -> Повторяй.
-   **Завершение Режима Агента:** Когда готов дать полный ответ на ПЕРВОНАЧАЛЬНЫЙ запрос, просто напиши финальную "Мысль" с выводом (например, "FINAL THOUGHT: Я собрал всю информацию...") и НЕ вызывай инструменты. Система поймет, что работа закончена, и сгенерирует ответ для пользователя.

### ЗОЛОТОЕ ПРАВИЛО:
- **НИКОГДА НЕ ОБЩАЙСЯ С ПОЛЬЗОВАТЕЛЕМ НАПРЯМУЮ В РЕЖИМЕ АГЕНТА.** Все твои "Мысли" и "Действия" предназначены для внутренней логики, пользователь их не видит. Только финальный ответ, сгенерированный после завершения твоего цикла.
- **НИКОГДА НЕ ПРИДУМЫВАЙ АРГУМЕНТЫ:** ID, пути к файлам и т.д. должны быть взяты ИСКЛЮЧИТЕЛЬНО из результатов вызова других функций.
"""
        }
        
        messages = [system_prompt] + history

        # --- ПЕРВЫЙ ВЫЗОВ К LLM ---
        # На этом этапе ИИ должен решить, какой режим использовать.
        logging.info(f"Вызов ИИ (начало работы). История: {len(messages)} сообщений.")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=[{"type": "function", "function": f} for f in self.functions],
            # На первом шаге даем ему выбор: ответить текстом (none) или вызвать инструмент (auto)
            tool_choice="auto", # Модель сама решит, нужен ли инструмент
            **kwargs
        )
        message_obj = resp.choices[0].message
        message_dict = {"role": message_obj.role}
        if message_obj.content:
            message_dict["content"] = message_obj.content
        if message_obj.tool_calls:
             message_dict["tool_calls"] = [{"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in message_obj.tool_calls]
        
        # --- ПРОВЕРКА РЕЖИМА ---
        # Если нет вызова инструментов И ЕСТЬ текстовое содержимое,
        # считаем, что ИИ выбрал Режим Чат-бота.
        if not message_obj.tool_calls and message_obj.content:
            logging.info("ИИ выбрал Режим Чат-бота. Возвращаю прямой ответ.")
            self.action_started.emit("") # Очищаем статус
            return message_obj.content # Возвращаем его текст напрямую, без суммаризации
            
        # Если есть вызов инструментов ИЛИ нет текстового содержимого (редкий случай),
        # считаем, что ИИ вошел в Режим Агента. Добавляем его первый ответ в историю
        # и продолжаем цикл ReAct.
        messages.append(message_dict)
        logging.info("ИИ вошел в Режим Агента.")

        # --- ЦИКЛ РЕЖИМА АГЕНТА ---
        # Этот цикл будет обрабатывать последовательные шаги "Мысль -> Действие -> Результат"
        MAX_AGENT_TURNS = 8 # Ограничим количество итераций в режиме агента
        for i in range(MAX_AGENT_TURNS):
             logging.info(f"Режим Агента (итерация {i+1}). История: {len(messages)} сообщений.")

             # Если на текущей итерации агент не вернул tool_calls, это его финальная "Мысль".
             # Мы выходим из цикла и запускаем суммаризатор.
             if "tool_calls" not in messages[-1]: # Проверяем последний добавленный message_dict
                 logging.info("ИИ завершил работу в Режиме Агента. Запускаю суммаризацию.")
                 self.action_started.emit("")
                 return self._summarize_for_user(messages)
             
             # Обрабатываем вызовы инструментов из последнего ответа
             tool_calls = messages[-1]["tool_calls"]

             for tool_call in tool_calls:
                 function_call = tool_call["function"]
                 name = function_call["name"]
                 arguments_str = function_call["arguments"]
                 tool_call_id = tool_call["id"]
                 
                 try:
                     args = json.loads(arguments_str)
                 except json.JSONDecodeError:
                     error_content = f'{{"error": "Invalid JSON format in arguments: {arguments_str}"}}'
                     messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": name, "content": error_content})
                     continue

                 user_message = f"Выполняю: {name}({json.dumps(args, ensure_ascii=False)})"
                 self.action_started.emit(user_message)
                 
                 try:
                     result = self.call_mcp(name, args)
                 except Exception as e:
                     logging.error(f"Ошибка при вызове MCP '{name}': {e}")
                     result = {"error": str(e)}

                 messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": name, "content": json.dumps(result, ensure_ascii=False)})
            
             # После обработки всех tool_calls в текущей итерации, делаем следующий вызов к LLM
             # с обновленной историей (включающей результаты выполнения инструментов)
             logging.info(f"Вызов ИИ для следующей итерации Режима Агента. История: {len(messages)} сообщений.")
             resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[{"type": "function", "function": f} for f in self.functions],
                tool_choice="auto", # Даем ему возможность вызвать еще один инструмент или завершить работу
                **kwargs
             )
             message_obj = resp.choices[0].message
             message_dict = {"role": message_obj.role}
             if message_obj.content:
                 message_dict["content"] = message_obj.content
             if message_obj.tool_calls:
                  message_dict["tool_calls"] = [{"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in message_obj.tool_calls]

             messages.append(message_dict) # Добавляем его новый ответ в историю

        # Если достигнут лимит итераций Режима Агента
        logging.warning("Достигнут лимит итераций Режима Агента. Принудительно запускаю суммаризацию.")
        self.action_started.emit("")
        return self._summarize_for_user(messages)

    def call_mcp(self, function_name: str, params: dict):
        server_name = self._function_to_server_map.get(function_name)
        if not server_name:
            raise KeyError(f"Нет зарегистрированного MCP-сервера для функции «{function_name}»")
        
        logging.info(f"Маршрутизация вызова '{function_name}' на MCP-сервер '{server_name}'")
        return self.mcp_servers[server_name].call(function_name, params)