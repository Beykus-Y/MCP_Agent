# main.py (Версия 5.1 - с правильной фильтрацией инструментов для Оркестратора)

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
                resp = requests.get(f"{url}/functions", timeout=1)
                if resp.status_code == 200:
                    print(f"  ✓ MCP '{name}' готов.")
                    ready_servers.add(name)
            except requests.exceptions.RequestException:
                pass
        time.sleep(0.5)

    if len(ready_servers) < len(servers_to_check):
        unready = set(servers_to_check.keys()) - ready_servers
        raise RuntimeError(f"Не все MCP-серверы запустились в течение таймаута: {list(unready)}")
    
    print("[MAIN] Все MCP-серверы готовы к работе.")


def main():
    load_dotenv()
    
    # 1. Определяем, какие MCP активны
    active_mcps_str = os.getenv("ACTIVE_MCPS", "")
    if not active_mcps_str:
        app = QtWidgets.QApplication(sys.argv)
        QtWidgets.QMessageBox.critical(None, "Ошибка запуска", "Переменная ACTIVE_MCPS не найдена.\nЗапустите приложение через launcher.py.")
        sys.exit(1)

    active_mcp_keys = [key.strip() for key in active_mcps_str.split(',')]
    print(f"[MAIN] Активные MCP, согласно .env: {active_mcp_keys}")

    # 2. Строим словарь серверов для проверки
    servers_to_check = {}
    for key in active_mcp_keys:
        if key in MCP_REGISTRY:
            config = MCP_REGISTRY[key]
            port = os.getenv(config['port_env'], config['default_port'])
            servers_to_check[key] = f"http://127.0.0.1:{port}"
    
    # --- ОЖИДАНИЕ ---
    try:
        wait_for_mcp_servers(servers_to_check)
    except RuntimeError as e:
        app = QtWidgets.QApplication(sys.argv)
        QtWidgets.QMessageBox.critical(None, "Ошибка запуска", f"Не удалось дождаться MCP-серверов:\n{e}")
        sys.exit(1)

    # --- ИНИЦИАЛИЗАЦИЯ ---
    API_KEY  = os.getenv("OPENAI_API_KEY")
    API_BASE = os.getenv("OPENAI_API_BASE")
    if not API_KEY:
        app = QtWidgets.QApplication(sys.argv)
        QtWidgets.QMessageBox.critical(None, "Ошибка конфигурации", "OPENAI_API_KEY не найден в .env файле.\nПожалуйста, настройте его через launcher.py.")
        sys.exit(1)
        
    client = OpenAI(api_key=API_KEY, base_url=API_BASE)

    try:
        resp = requests.get(f"{API_BASE}/models", headers={"Authorization": f"Bearer {API_KEY}"})
        resp.raise_for_status()
        models = [m["id"] for m in resp.json()["data"]]
    except Exception as e:
        logging.error("Не удалось получить список моделей: %s", e)
        models = [os.getenv("SELECTED_MODEL", "openai/gpt-4o")]

    # ### ИСПРАВЛЕНО: Инициализируем Оркестратора с ФИЛЬТРОМ инструментов ###
    print("[MAIN] Создание Агента-Оркестратора...")
    
    # Создаем список MCP, которые Оркестратор может использовать НАПРЯМУЮ.
    # Он не должен видеть 'rpg', чтобы быть вынужденным его делегировать.
    orchestrator_allowed_mcps = [key for key in active_mcp_keys if key != 'rpg']
    print(f"[MAIN] Оркестратору разрешены следующие MCP: {orchestrator_allowed_mcps}")

    ai_iface = AIWithMCPInterface(
        client=client,
        prompt_path="prompts/orchestrator_prompt.txt",
        all_mcp_servers=servers_to_check,
        allowed_mcp_filter=orchestrator_allowed_mcps # <-- ПРИМЕНЯЕМ ФИЛЬТР
    )
    print("[MAIN] Оркестратор готов.")
    
    # --- ЗАПУСК GUI ---
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(ai_iface=ai_iface, models=models)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()