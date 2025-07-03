# mcp_clipboard.py

import os
import json
import pyperclip # Наша новая библиотека
from flask import Flask, request, jsonify
from waitress import serve

app = Flask(__name__)

# --- Описания функций для ИИ ---
CLIPBOARD_FUNCTIONS = [
    {
        "name": "get_clipboard_content",
        "description": "Возвращает текстовое содержимое, которое в данный момент находится в буфере обмена операционной системы.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "set_clipboard_content",
        "description": "Помещает указанный текст в буфер обмена операционной системы, затирая предыдущее содержимое.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Текст, который нужно поместить в буфер обмена."
                }
            },
            "required": ["text"]
        }
    }
]

# --- Класс ошибки и хелперы (стандартные) ---
class JsonRpcError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message

def make_error_response(id_, code, message): return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})
def make_success_response(id_, result): return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})

# --- Реализация методов ---
def get_clipboard_content(params):
    """Получает текст из буфера обмена."""
    try:
        content = pyperclip.paste()
        return {"content": content}
    except Exception as e:
        # Pyperclip может вызывать ошибки, если буфер обмена недоступен (например, в headless-системах)
        raise JsonRpcError(-32000, f"Не удалось прочитать буфер обмена: {e}")

def set_clipboard_content(params):
    """Помещает текст в буфер обмена."""
    text_to_copy = params.get("text")
    if text_to_copy is None:
        raise JsonRpcError(-32602, "Параметр 'text' отсутствует.")
    
    try:
        pyperclip.copy(text_to_copy)
        return {"status": "ok", "message": "Текст успешно скопирован в буфер обмена."}
    except Exception as e:
        raise JsonRpcError(-32000, f"Не удалось записать в буфер обмена: {e}")

METHODS = {
    "get_clipboard_content": get_clipboard_content,
    "set_clipboard_content": set_clipboard_content
}

# --- Эндпоинты Flask (стандартные) ---
@app.route("/functions")
def get_functions_route(): return jsonify(CLIPBOARD_FUNCTIONS)

@app.route("/mcp", methods=["POST"])
def mcp_entrypoint():
    try:
        req = request.get_json(force=True)
        result = METHODS[req['method']](req.get('params', {}))
        return make_success_response(req['id'], result)
    except Exception as e:
        code = e.code if isinstance(e, JsonRpcError) else -32603
        msg = e.message if isinstance(e, JsonRpcError) else str(e)
        return make_error_response(req.get('id'), code, msg), 500

if __name__ == "__main__":
    port = int(os.getenv("MCP_CLIPBOARD_PORT", 8004))
    print(f"[*] MCP_Clipboard (буфер обмена) запускается на порту: {port} через Waitress.")
    serve(app, host="0.0.0.0", port=port)