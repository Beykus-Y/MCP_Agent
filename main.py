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
from mcp_registry import MCP_REGISTRY
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
    
    active_mcps_str = os.getenv("ACTIVE_MCPS", "")
    if not active_mcps_str:
        logging.critical("Переменная ACTIVE_MCPS не найдена или пуста в .env файле.")
        logging.critical("Пожалуйста, запустите приложение через launcher.py, чтобы выбрать и запустить MCP.")
        sys.exit(1) # Завершаем работу, если неясно, какие MCP активны

    active_mcp_keys = [key.strip() for key in active_mcps_str.split(',')]
    print(f"[MAIN] Активные MCP, согласно .env: {active_mcp_keys}")

    # 2. Динамически строим словарь servers_to_check на основе реестра
    servers_to_check = {}
    for key in active_mcp_keys:
        if key in MCP_REGISTRY:
            config = MCP_REGISTRY[key]
            port = os.getenv(config['port_env'], config['default_port'])
            servers_to_check[key] = f"http://127.0.0.1:{port}"
        else:
            logging.warning(f"Неизвестный ключ MCP '{key}' найден в ACTIVE_MCPS, игнорируется.")
    
    # --- ОЖИДАНИЕ ---
    try:
        # wait_for_mcp_servers теперь получает динамически созданный список
        wait_for_mcp_servers(servers_to_check)
    except RuntimeError as e:
        logging.critical(f"Критическая ошибка при запуске: {e}")
        sys.exit(1)

    # --- ИНИЦИАЛИЗАЦИЯ (далее без существенных изменений) ---
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
    # Регистрация также теперь использует динамический список
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