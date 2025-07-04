# mcp_registry.py
"""
Единый источник истины (Single Source of Truth) для всех MCP-модулей.
Чтобы добавить новый MCP в систему, достаточно добавить запись в этот словарь.
"""

MCP_REGISTRY = {
    # Ключ: (строка) уникальный идентификатор MCP. Используется внутри кода.
    # ---
    # name: (строка) Человеко-понятное имя для отображения в GUI.
    # script: (строка) Имя файла скрипта для запуска.
    # port_env: (строка) Имя переменной окружения, хранящей порт.
    # default_port: (строка) Порт по умолчанию, если переменная не найдена.
    
    "files": {
        "name": "Files (Файлы)", 
        "script": "mcp_files.py", 
        "port_env": "MCP_FILES_PORT", 
        "default_port": "8001"
    },
    "web": {
        "name": "Web (Selenium)", 
        "script": "mcp_web.py", 
        "port_env": "MCP_WEB_PORT", 
        "default_port": "8002"
    },
    "shell": {
        "name": "Shell (Терминал)", 
        "script": "mcp_shell.py", 
        "port_env": "MCP_SHELL_PORT", 
        "default_port": "8003"
    },
    "clipboard": {
        "name": "Clipboard (Буфер обмена)", 
        "script": "mcp_clipboard.py", 
        "port_env": "MCP_CLIPBOARD_PORT", 
        "default_port": "8004"
    },
    "telegram": {
        "name": "Telegram", 
        "script": "mcp_telegram.py", 
        "port_env": "MCP_TELEGRAM_PORT", 
        "default_port": "8005"
    },
    "semantic_memory": {
        "name": "Semantic Memory (Память)", 
        "script": "mcp_semantic_memory.py", 
        "port_env": "MCP_SEMANTIC_MEMORY_PORT", 
        "default_port": "8007"
    },
    "rpg": {
    "name": "RPG Engine (Ролевые игры)", 
    "script": "mcp_rpg.py", 
    "port_env": "MCP_RPG_PORT", 
    "default_port": "8008"
    },
    # --- Сюда можно добавлять новые MCP в будущем ---
    # "new_mcp": {
    #     "name": "My New MCP",
    #     "script": "mcp_new.py",
    #     "port_env": "MCP_NEW_PORT",
    #     "default_port": "8008"
    # },
}