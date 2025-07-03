# mcp_telegram.py (ФИНАЛЬНАЯ ВЕРСИЯ С ID)

import os
import json
import asyncio
import threading
from dotenv import load_dotenv
from telethon import TelegramClient, errors
from flask import Flask, request, jsonify
from waitress import serve

# --- Конфигурация ---
load_dotenv()
API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
SESSION_NAME = "ai_agent_session"

# --- Глобальные переменные ---
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
loop = asyncio.new_event_loop()

# --- Описания функций для ИИ (с упором на dialog_id) ---
TELEGRAM_FUNCTIONS = [
    {
        "name": "send_telegram_message",
        "description": "Отправляет текстовое сообщение в диалог. КРАЙНЕ ВАЖНО: ID диалога (`dialog_id`) ДОЛЖЕН быть взят из РЕАЛЬНОГО результата вызова `list_telegram_dialogs`. НЕ ПРИДУМЫВАЙ ID.",
        "parameters": {
            "type": "object", "properties": {
                "dialog_id": {"type": "integer", "description": "Числовой ID пользователя или чата из `list_telegram_dialogs`. Для 'Избранного' используй 777000."},
                "message_text": {"type": "string", "description": "Текст сообщения для отправки."}
            }, "required": ["dialog_id", "message_text"]
        }
    },
    {
        "name": "list_telegram_dialogs",
        "description": "Возвращает СПИСОК реальных диалогов и их ID. Получив этот список, проанализируй его самостоятельно, чтобы найти нужный ID для других функций. Не используй другие инструменты для анализа этого списка.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "read_last_messages",
        "description": "Читает сообщения из диалога. КРАЙНЕ ВАЖНО: `dialog_id` ДОЛЖЕН быть взят из РЕАЛЬНОГО результата вызова `list_telegram_dialogs`.",
        "parameters": {
            "type": "object", "properties": {
                "dialog_id": {"type": "integer", "description": "Числовой ID пользователя или чата из `list_telegram_dialogs`."},
                "limit": {"type": "integer", "description": "Количество сообщений.", "default": 10}
            }, "required": ["dialog_id"]
        }
    },
    
    {
        "name": "get_chat_participants",
        "description": "Возвращает список участников указанного группового чата или канала. Полезно, чтобы понять, кто состоит в чате.",
        "parameters": {
            "type": "object", "properties": {
                "dialog_id": {"type": "integer", "description": "Числовой ID группового чата или канала из `list_telegram_dialogs`."},
                "limit": {"type": "integer", "description": "Максимальное количество участников для возврата.", "default": 20}
            }, "required": ["dialog_id"]
        }
    }
]

# --- Асинхронная логика Telethon ---

def run_async_task(coro):
    """Безопасно выполняет асинхронную задачу в event loop'е Telethon."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=45)
    except Exception as e:
        print(f"[MCP_Telegram] Ошибка при выполнении асинхронной задачи: {e}")
        raise JsonRpcError(-32000, f"Ошибка выполнения задачи в Telegram: {e}")

async def _send_message(dialog_id, text):
    try:
        entity = 'me' if dialog_id == 777000 else int(dialog_id)
        await client.send_message(entity, text)
        return {"status": "ok", "message": f"Сообщение для {dialog_id} успешно отправлено."}
    except (errors.rpcerrorlist.PeerIdInvalidError, ValueError):
        return {"status": "error", "message": f"Не удалось найти пользователя или чат с ID '{dialog_id}'."}
    except Exception as e:
        return {"status": "error", "message": f"Произошла ошибка при отправке: {e}"}

async def _list_dialogs():
    dialogs_list = []
    async for dialog in client.iter_dialogs(limit=15):
        dialogs_list.append({"name": dialog.name, "id": dialog.id})
    return dialogs_list

async def _read_messages(dialog_id, limit):
    messages_list = []
    try:
        entity = int(dialog_id)
        async for message in client.iter_messages(entity, limit=limit):
            if not message.text: continue
            sender_name = "Неизвестно"
            if message.sender:
                try:
                    sender = await message.get_sender()
                    if sender: sender_name = sender.first_name or sender.username or sender.title
                except Exception:
                    sender_name = "Удаленный аккаунт"
            messages_list.append({"from": sender_name, "text": message.text, "date": message.date.strftime("%Y-%m-%d %H:%M:%S")})
        return messages_list
    except (errors.rpcerrorlist.PeerIdInvalidError, ValueError):
        return {"status": "error", "message": f"Не удалось найти пользователя или чат с ID '{dialog_id}'."}
    except Exception as e:
        return {"status": "error", "message": f"Произошла ошибка при чтении сообщений: {e}"}
    
async def _get_chat_participants(dialog_id, limit):
    participants_list = []
    try:
        entity = int(dialog_id)
        async for user in client.iter_participants(entity, limit=limit):
            participants_list.append({
                "id": user.id,
                "username": user.username or "N/A",
                "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip()
            })
        return participants_list
    except (ValueError, errors.rpcerrorlist.PeerIdInvalidError):
         return {"status": "error", "message": f"Не удалось найти чат с ID '{dialog_id}' или это не групповой чат."}
    except Exception as e:
        return {"status": "error", "message": f"Произошла ошибка при получении списка участников: {e}"}

# --- Реализация методов для MCP (обертки) ---

def send_telegram_message(params):
    return run_async_task(_send_message(params['dialog_id'], params['message_text']))

def list_telegram_dialogs(params):
    return run_async_task(_list_dialogs())

def read_last_messages(params):
    return run_async_task(_read_messages(params['dialog_id'], params.get('limit', 10)))
def get_chat_participants(params): 
    return run_async_task(_get_chat_participants(params['dialog_id'], params.get('limit', 20)))

# --- Стандартная часть MCP (Flask, эндпоинты) ---
app = Flask(__name__)
class JsonRpcError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message

def make_error_response(id_, code, message): return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})
def make_success_response(id_, result): return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})

METHODS = {func['name']: globals()[func['name']] for func in TELEGRAM_FUNCTIONS}

@app.route("/functions")
def get_functions_route(): return jsonify(TELEGRAM_FUNCTIONS)

@app.route("/mcp", methods=["POST"])
def mcp_entrypoint():
    try:
        req = request.get_json(force=True)
        id_ = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if req.get("jsonrpc") != "2.0" or id_ is None or not method:
            raise JsonRpcError(-32600, "Invalid JSON-RPC request format")
        if method not in METHODS:
            raise JsonRpcError(-32601, f"Method not found: {method}")

        result = METHODS[method](params)
        return make_success_response(id_, result)
    except Exception as e:
        code = e.code if isinstance(e, JsonRpcError) else -32603
        msg = str(e.message) if isinstance(e, JsonRpcError) else str(e)
        return make_error_response(req.get('id'), code, msg), 500

# --- Логика запуска ---
async def main_telethon_logic():
    await client.start()
    print("[MCP_Telegram] Клиент успешно подключен и готов к работе.")
    await client.run_until_disconnected()

def telethon_thread_target():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main_telethon_logic())

if __name__ == "__main__":
    telethon_thread = threading.Thread(target=telethon_thread_target, daemon=True)
    telethon_thread.start()
    port = int(os.getenv("MCP_TELEGRAM_PORT", 8005))
    print(f"[*] MCP_Telegram (агент TG) запускается на порту: {port} через Waitress.")
    serve(app, host="0.0.0.0", port=port)