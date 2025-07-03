@echo off
REM Устанавливаем кодировку консоли на UTF-8, чтобы правильно отображать кириллицу
chcp 65001 > NUL

echo [LAUNCHER] Запускаем MCP-серверы в фоновом режиме...

REM ИЗМЕНЕНО: Используем полный путь к Python из виртуального окружения
set PYTHON_EXE=.\venv\Scripts\python.exe

start "MCP Files" %PYTHON_EXE% .\mcp_files.py
start "MCP Web" %PYTHON_EXE% .\mcp_web.py
start "MCP Shell" %PYTHON_EXE% .\mcp_shell.py
start "MCP Clipboard" %PYTHON_EXE% .\mcp_clipboard.py
start "MCP Telegram" %PYTHON_EXE% .\mcp_telegram.py
start "MCP Memory" %PYTHON_EXE% .\mcp_memory.py
start "MCP Semantic Memory" %PYTHON_EXE% .\mcp_semantic_memory.py


echo [LAUNCHER] Ожидаем 5 секунд для стабилизации серверов...
timeout /t 5 /nobreak > NUL

echo [LAUNCHER] Запускаем основной GUI...
REM ИЗМЕНЕНО: Здесь тоже используем Python из venv
%PYTHON_EXE% .\main.py

echo [LAUNCHER] Приложение закрыто. Нажмите любую клавишу для выхода...
pause > NUL