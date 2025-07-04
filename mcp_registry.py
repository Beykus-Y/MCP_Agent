# mcp_registry.py (Версия с описаниями)
"""
Единый источник истины (Single Source of Truth) для всех MCP-модулей.
Чтобы добавить новый MCP в систему, достаточно добавить запись в этот словарь.
"""

MCP_REGISTRY = {
    "files": {
        "name": "Files (Файлы)", 
        "script": "mcp_files.py", 
        "port_env": "MCP_FILES_PORT", 
        "default_port": "8001",
        "description": "Предоставляет ИИ возможность работать с файлами и папками в изолированной 'песочнице' (рабочей папке).\n\n- list_dir: Посмотреть содержимое папки.\n- read_file: Прочитать текстовый файл.\n- write_file: Записать или создать файл.\n- delete_file: Удалить файл."
    },
    "web": {
        "name": "Web (Selenium)", 
        "script": "mcp_web.py", 
        "port_env": "MCP_WEB_PORT", 
        "default_port": "8002",
        "description": "Позволяет ИИ взаимодействовать с веб-страницами через браузер.\n\n- navigate_to_url: Открыть сайт.\n- get_page_content: 'Осмотреться' на странице, получить текст и список кнопок/ссылок.\n- click_element: Нажать на элемент.\n- type_in_element: Ввести текст в поле."
    },
    "shell": {
        "name": "Shell (Терминал)", 
        "script": "mcp_shell.py", 
        "port_env": "MCP_SHELL_PORT", 
        "default_port": "8003",
        "description": "Дает ИИ доступ к ограниченному набору безопасных команд в терминале.\n\n- execute_shell_command: Выполнить команду из белого списка (например, git status, pip list).\n- get_current_time: Узнать текущее время."
    },
    "clipboard": {
        "name": "Clipboard (Буфер обмена)", 
        "script": "mcp_clipboard.py", 
        "port_env": "MCP_CLIPBOARD_PORT", 
        "default_port": "8004",
        "description": "Позволяет ИИ читать и записывать текст в системный буфер обмена.\n\n- get_clipboard_content: Получить текст из буфера.\n- set_clipboard_content: Поместить текст в буфер."
    },
    "telegram": {
        "name": "Telegram", 
        "script": "mcp_telegram.py", 
        "port_env": "MCP_TELEGRAM_PORT", 
        "default_port": "8005",
        "description": "Интеграция с Telegram для чтения и отправки сообщений.\n\n- list_telegram_dialogs: Получить список чатов и их ID.\n- send_telegram_message: Отправить сообщение.\n- read_last_messages: Прочитать историю чата."
    },
    "semantic_memory": {
        "name": "Semantic Memory (Память)", 
        "script": "mcp_semantic_memory.py", 
        "port_env": "MCP_SEMANTIC_MEMORY_PORT", 
        "default_port": "8007",
        "description": "Продвинутая память для ИИ, сочетающая семантический поиск (по смыслу) и граф знаний (связи между сущностями).\n\n- remember: Сохранить факт.\n- recall: Вспомнить похожие факты.\n- create_entity: Создать объект в графе (человек, проект).\n- link_entities: Связать два объекта."
    },
    "rpg": {
        "name": "RPG Engine (Ролевые игры)", 
        "script": "mcp_rpg.py", 
        "port_env": "MCP_RPG_PORT", 
        "default_port": "8008",
        "description": "Движок для управления состоянием в ролевых играх. Хранит данные о персонажах, локациях, квестах.\n\n- get_player_status: Полная сводка о состоянии игрока.\n- explore_location: Переместиться и осмотреться.\n- new_game: Начать новую игру."
    },
}