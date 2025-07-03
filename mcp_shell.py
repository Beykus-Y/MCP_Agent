# mcp_shell.py

import os
import json
import subprocess
from flask import Flask, request, jsonify
from waitress import serve
import datetime
app = Flask(__name__)

# --- Безопасность: определяем "белый список" разрешенных команд ---
# Ключ - имя команды, как его видит ИИ.
# Значение - реальная команда или путь к исполняемому файлу.
# Мы не даем ИИ возможность выполнять произвольные строки, только эти команды.
ALLOWED_COMMANDS = {
    "list_files_detailed": "ls -la" if os.name != 'nt' else "dir",
    "show_git_status": "git status",
    "show_pip_packages": "pip list",
    # Пример команды с аргументами, которые будет подставлять ИИ.
    # Мы будем экранировать аргументы для безопасности.
    "install_pip_package": "pip install",
    "check_python_version": "python --version",
}


# --- Описания функций для ИИ ---
SHELL_FUNCTIONS = [
    {
        "name": "execute_shell_command",
        "description": "Выполняет одну из разрешенных команд в терминале. Аргументы можно передавать только для команд, которые их поддерживают.",
        "parameters": {
            "type": "object",
            "properties": {
                "command_name": {
                    "type": "string",
                    "description": "Имя команды из списка разрешенных.",
                    "enum": list(ALLOWED_COMMANDS.keys())
                },
                "args": {
                    "type": "array",
                    "description": "Список аргументов для команды. Например, для 'install_pip_package' это будет ['requests'].",
                    "items": { "type": "string" }
                }
            },
            "required": ["command_name"]
        }
    },
    # ИЗМЕНЕНО: Описание функции - теперь она получает время напрямую, а не через ОС
    {
        "name": "get_current_time",
        "description": "Возвращает текущую дату и время операционной системы. Используй эту функцию, когда пользователь спрашивает 'сколько сейчас время' или 'какая дата'.",
        "parameters": {"type": "object", "properties": {}} # Нет параметров
    }
]

# --- Класс ошибки и хелперы (стандартные) ---
class JsonRpcError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message

def make_error_response(id_, code, message): return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})
def make_success_response(id_, result): return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})

# --- Реализация метода --
def execute_shell_command(params):
    command_name = params.get("command_name")
    args = params.get("args", [])

    if command_name not in ALLOWED_COMMANDS:
        raise JsonRpcError(-32602, f"Команда '{command_name}' не разрешена.")

    base_command = ALLOWED_COMMANDS[command_name].split()
    full_command = base_command + args
    
    try:
        print(f"[MCP_Shell] Выполнение команды: {' '.join(full_command)}")
        result = subprocess.run(
            full_command, 
            capture_output=True, 
            text=True, 
            timeout=60, # Вернем стандартный таймаут для команд ОС
            check=False,
            encoding='utf-8',
            errors='ignore'
        )
        
        output = result.stdout
        error_output = result.stderr

        # Ограничиваем объем вывода только для больших команд
        MAX_LEN = 3000 # Вернем стандартный лимит
        if len(output) > MAX_LEN:
            output = output[:MAX_LEN] + "\n... (stdout обрезан)"
        if len(error_output) > MAX_LEN:
            error_output = error_output[:MAX_LEN] + "\n... (stderr обрезан)"


        return {
            "command_executed": ' '.join(full_command),
            "return_code": result.returncode,
            "stdout": output,
            "stderr": error_output
        }

    except FileNotFoundError:
        raise JsonRpcError(-32000, f"Ошибка выполнения: команда или программа '{base_command[0]}' не найдена. Возможно, она не установлена или не в системном PATH.")
    except subprocess.TimeoutExpired:
        raise JsonRpcError(-32000, "Ошибка выполнения: команда выполнялась слишком долго и была прервана.")
    except Exception as e:
        raise JsonRpcError(-32000, f"Неизвестная ошибка при выполнении команды: {e}")

# НОВОЕ: Реализация функции get_current_time с использованием datetime
def get_current_time(params):
    """
    Возвращает текущую дату и время с использованием встроенной библиотеки datetime.
    """
    now = datetime.datetime.now()
    # Форматируем дату и время в удобочитаемый формат
    formatted_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
    return {"current_datetime": formatted_datetime}


# ИЗМЕНЕНО: Список методов
METHODS = {
    "execute_shell_command": execute_shell_command,
    "get_current_time": get_current_time, # Используем новую реализацию
}

# --- Эндпоинты Flask (стандартные) ---
@app.route("/functions")
def get_functions_route(): return jsonify(SHELL_FUNCTIONS)

@app.route("/mcp", methods=["POST"])
def mcp_entrypoint():
    try:
        req = request.get_json(force=True)
        # ... (валидация запроса, как в других MCP)
        result = METHODS[req['method']](req.get('params', {}))
        return make_success_response(req['id'], result)
    except Exception as e:
        code = e.code if isinstance(e, JsonRpcError) else -32603
        msg = e.message if isinstance(e, JsonRpcError) else str(e)
        return make_error_response(req.get('id'), code, msg), 500

if __name__ == "__main__":
    port = int(os.getenv("MCP_SHELL_PORT", 8003))
    print(f"[*] MCP_Shell (команды ОС) запускается на порту: {port} через Waitress.")
    serve(app, host="0.0.0.0", port=port)