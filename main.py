# main.py (ФИНАЛЬНАЯ ВЕРСИЯ)

import os
import sys
import requests
import logging
import time

from dotenv import load_dotenv
from openai import OpenAI
from PyQt5 import QtWidgets

from UI import MainWindow
from ai_interface import AIWithMCPInterface

# НОВОЕ: Возвращаем нашу функцию для "умного" ожидания
def wait_for_mcp_servers(servers_to_check, timeout=30):
    """
    Ожидает, пока все MCP-серверы из списка не станут доступны.
    Пингует их эндпоинт /functions.
    """
    print("[MAIN] Ожидаем готовности MCP-серверов...")
    start_time = time.time()
    
    ready_servers = set()

    while len(ready_servers) < len(servers_to_check) and time.time() - start_time < timeout:
        for name, url in servers_to_check.items():
            if name in ready_servers:
                continue
            try:
                # Пытаемся подключиться к серверу
                resp = requests.get(f"{url}/functions", timeout=1)
                if resp.status_code == 200:
                    print(f"  ✓ MCP '{name}' готов.")
                    ready_servers.add(name)
            except requests.exceptions.RequestException:
                # Сервер еще не отвечает, это нормально, ждем дальше
                pass
        time.sleep(0.5)

    if len(ready_servers) < len(servers_to_check):
        unready = set(servers_to_check.keys()) - ready_servers
        raise RuntimeError(f"Не все MCP-серверы запустились в течение таймаута: {list(unready)}")
    
    print("[MAIN] Все MCP-серверы готовы к работе.")


def main():
    load_dotenv()
    
    # --- НАСТРОЙКА ---
    # Определяем, какие серверы мы должны дождаться
    servers_to_check = {
        "files": f"http://127.0.0.1:{os.getenv('MCP_FILES_PORT', '8001')}",
        "web": f"http://127.0.0.1:{os.getenv('MCP_WEB_PORT', '8002')}",
        "shell": f"http://127.0.0.1:{os.getenv('MCP_SHELL_PORT', '8003')}",
        "clipboard": f"http://127.0.0.1:{os.getenv('MCP_CLIPBOARD_PORT', '8004')}",
        "telegram": f"http://127.0.0.1:{os.getenv('MCP_TELEGRAM_PORT', '8005')}",
        "semantic_memory": f"http://127.0.0.1:{os.getenv('MCP_SEMANTIC_MEMORY_PORT', '8007')}",
    }
    
    # --- ОЖИДАНИЕ ---
    try:
        wait_for_mcp_servers(servers_to_check)
    except RuntimeError as e:
        logging.critical(f"Критическая ошибка при запуске: {e}")
        sys.exit(1)

    # --- ИНИЦИАЛИЗАЦИЯ ---
    API_KEY  = os.getenv("OPENAI_API_KEY")
    API_BASE = os.getenv("OPENAI_API_BASE")
    client = OpenAI(api_key=API_KEY, base_url=API_BASE)

    try:
        resp = requests.get(f"{API_BASE}/models", headers={"Authorization": f"Bearer {API_KEY}"})
        resp.raise_for_status()
        models = [m["id"] for m in resp.json()["data"]]
    except Exception as e:
        logging.error("Не удалось получить список моделей: %s", e)
        models = [os.getenv("SELECTED_MODEL", "openai/gpt-4o")]

    ai_iface = AIWithMCPInterface(client)
    
    print("[MAIN] Попытка регистрации MCP-серверов...")
    for name, url in servers_to_check.items():
        ai_iface.register_mcp(name, url)
    print("[MAIN] Регистрация завершена.")

    # --- ЗАПУСК GUI ---
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(ai_iface=ai_iface, models=models)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()