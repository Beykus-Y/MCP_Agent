# mcp_files.py
import os
import json
from flask import Flask, request, jsonify
from waitress import serve

# ИЗМЕНЕНО: Убираем threading. Вместо него используем простые глобальные переменные.
_BASE_DIR = None
_BASE_DIR_INITIALIZED = False

app = Flask(__name__)
# --- Описания функций и класс ошибки (без изменений) ---
FILE_FUNCTIONS = [
    {
        "name": "list_dir",
        "description": "Список файлов и папок в директории. Всегда используй эту функцию, чтобы проверить наличие файлов, прежде чем пытаться их прочитать.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Путь к папке. Например, '.' или 'subfolder/another_folder'"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "read_file",
        "description": "Прочитать текстовый файл. Убедись, что файл существует, с помощью list_dir, прежде чем вызывать эту функцию.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Полный путь к файлу относительно рабочей папки."}},
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Записать КОРОТКИЙ текст в файл. Если файл существует, он будет перезаписан. Если нет - создан. Не используй эту функцию для сохранения больших объемов данных.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Путь к файлу."},
                "content": {"type": "string", "description": "Краткое текстовое содержимое для записи."}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "delete_file",
        "description": "Удалить файл из рабочей папки.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Путь к файлу."}},
            "required": ["path"]
        }
    }
]

class JsonRpcError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message

# --- ИЗМЕНЕНО: Функции инициализации и безопасности ---

def get_base_dir():
    """Ленивая инициализация BASE_DIR с использованием глобального флага."""
    global _BASE_DIR, _BASE_DIR_INITIALIZED
    
    if not _BASE_DIR_INITIALIZED:
        base_dir_path = os.path.abspath(os.getenv("MCP_FILES_BASE_DIR", "./workspace"))
        if not os.path.exists(base_dir_path):
            try:
                os.makedirs(base_dir_path)
                print(f"[*] Рабочая директория создана: {base_dir_path}")
            except OSError as e:
                print(f"[!] Ошибка создания директории: {e}")
                import tempfile
                base_dir_path = tempfile.gettempdir()
        
        _BASE_DIR = base_dir_path
        _BASE_DIR_INITIALIZED = True
        print(f"[*] MCP_Files (песочница) инициализирована в: {_BASE_DIR}")

    return _BASE_DIR


def _get_safe_path(path: str) -> str:
    """Проверяет путь, используя лениво инициализированную BASE_DIR."""
    base_dir = get_base_dir()
    if not path or '..' in path.split(os.path.sep):
        raise JsonRpcError(-32602, "Invalid path format or '..' detected.")
    requested_path = os.path.abspath(os.path.join(base_dir, path))
    if not requested_path.startswith(base_dir):
        raise JsonRpcError(-32001, f"Access denied: Path is outside of the allowed workspace.")
    return requested_path

# ... Функции make_error_response и make_success_response без изменений ...
def make_error_response(id_, code, message):
    return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})

def make_success_response(id_, result):
    return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})


# --- Реализация методов (без изменений в логике, но теперь они вызывают _get_safe_path) ---
def list_dir(params):
    path_param = params.get("path", ".")
    safe_path = _get_safe_path(path_param)
    if not os.path.isdir(safe_path):
        raise JsonRpcError(-32602, f"Path is not a valid directory: {path_param}")
    try:
        items = os.listdir(safe_path)
        return items
    except Exception as e:
        raise JsonRpcError(-32000, f"Error listing directory: {str(e)}")

def read_file(params):
    safe_path = _get_safe_path(params.get("path"))
    if not os.path.isfile(safe_path):
        raise JsonRpcError(-32602, f"File not found: {params.get('path')}")
    try:
        with open(safe_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content
    except Exception as e:
        raise JsonRpcError(-32000, f"Error reading file: {str(e)}")

def write_file(params):
    content = params.get("content")
    if content is None:
        raise JsonRpcError(-32602, "Missing required param: content")
    safe_path = _get_safe_path(params.get("path"))
    try:
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "ok", "path": params.get("path")}
    except Exception as e:
        raise JsonRpcError(-32000, f"Error writing file: {str(e)}")

def delete_file(params):
    safe_path = _get_safe_path(params.get("path"))
    if not os.path.exists(safe_path):
        raise JsonRpcError(-32602, f"File not found: {params.get('path')}")
    if not os.path.isfile(safe_path):
        raise JsonRpcError(-32602, f"Path is not a file: {params.get('path')}")
    try:
        os.remove(safe_path)
        return {"status": "ok"}
    except Exception as e:
        raise JsonRpcError(-32000, f"Error deleting file: {str(e)}")


METHODS = {
    "list_dir": list_dir,
    "read_file": read_file,
    "write_file": write_file,
    "delete_file": delete_file,
}

# --- Эндпоинты Flask ---

print("[*] Регистрируем endpoint /functions")

@app.route("/functions", methods=["GET"])
def get_functions():
    print("[*] Вызван /functions")
    return jsonify(FILE_FUNCTIONS)


@app.route("/mcp", methods=["POST"])
def mcp_entrypoint():
    # Эта функция без изменений
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
    except JsonRpcError as je:
        return make_error_response(req.get("id", None), je.code, je.message), 400
    except Exception as e:
        return make_error_response(req.get("id", None), -32603, f"Internal error: {str(e)}"), 500


if __name__ == "__main__":
    port = int(os.getenv("MCP_FILES_PORT", 8001))
    print(f"[*] MCP_Files запускается на порту: {port} через Waitress. Инициализация отложена.")
    serve(app, host="0.0.0.0", port=port)