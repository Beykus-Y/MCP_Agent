# mcp_web.py (ОКОНЧАТЕЛЬНАЯ ВЕРСИЯ)

import os
import json
from flask import Flask, request, jsonify
from waitress import serve
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Глобальное состояние и инициализация ---
app = Flask(__name__)
browser = None

def start_browser():
    """Инициализирует и запускает браузер, маскируясь под человека."""
    global browser
    if browser is None:
        print("[MCP_Web] Инициализация браузера Selenium...")
        try:
            service = Service(executable_path='./chromedriver.exe')
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            
            # --- УЛУЧШЕННАЯ МАСКИРОВКА ---
            # Устанавливаем "человеческий" User-Agent
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
            # Отключаем флаг, который кричит "Я - автоматизированный браузер!"
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            browser = webdriver.Chrome(service=service, options=options)
            
            # Дополнительный шаг, чтобы скрыть следы Selenium
            browser.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print("[MCP_Web] Браузер успешно запущен.")
        except Exception as e:
            print(f"[MCP_Web] КРИТИЧЕСКАЯ ОШИБКА: {e}")
            browser = None
# --- Класс ошибки и хелперы ---
class JsonRpcError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message

def make_error_response(id_, code, message): return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})
def make_success_response(id_, result): return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})

# --- Инструменты для ИИ ---

def get_page_content(params):
    if browser is None: raise JsonRpcError(-32001, "Браузер не запущен.")
    
    # Используем Selenium для поиска видимых элементов
    interactive_elements = []
    
    # 1. Ссылки
    link_elements = browser.find_elements(By.XPATH, "//a[@href]")
    for i, el in enumerate(link_elements):
        if el.is_displayed() and el.text.strip():
            interactive_elements.append({"id": f"link_{i}", "type": "link", "text": el.text.strip()})
            
    # 2. Поля ввода
    input_elements = browser.find_elements(By.XPATH, "//input[@type='text' or @type='password' or @type='search' or @type='email'] | //textarea")
    for i, el in enumerate(input_elements):
        if el.is_displayed():
            text = el.get_attribute('aria-label') or el.get_attribute('placeholder') or el.get_attribute('title') or f"Поле ввода {i}"
            interactive_elements.append({"id": f"input_{i}", "type": "input", "text": text})
            
    # 3. Кнопки
    button_elements = browser.find_elements(By.XPATH, "//button | //input[@type='submit' or @type='button']")
    for i, el in enumerate(button_elements):
        if el.is_displayed():
            text = el.text.strip() or el.get_attribute('value') or f"Кнопка {i}"
            if text:
                interactive_elements.append({"id": f"button_{i}", "type": "button", "text": text})

    page_text = browser.find_element(By.TAG_NAME, 'body').text
    return {
        "title": browser.title,
        "url": browser.current_url,
        "text_content": page_text[:4000] + "\n... (текст обрезан)" if len(page_text) > 4000 else page_text,
        "interactive_elements": interactive_elements[:50]
    }

def navigate_to_url(params):
    start_browser()
    if browser is None: raise JsonRpcError(-32001, "Не удалось запустить браузер.")
    url = params.get("url")
    if not url: raise JsonRpcError(-32602, "'url' отсутствует.")
    browser.get(url)
    WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    return get_page_content({})

def click_element(params):
    if browser is None: raise JsonRpcError(-32001, "Браузер не запущен.")
    element_id = params.get("id")
    if not element_id: raise JsonRpcError(-32602, "'id' отсутствует.")
    
    try:
        el_type, el_index_str = element_id.split('_')
        el_index = int(el_index_str)
        
        xpath_map = {'link': "//a[@href]", 'button': "//button | //input[@type='submit' or @type='button']"}
        if el_type not in xpath_map: raise JsonRpcError(-32602, "Неверный тип элемента.")
        
        visible_elements = [el for el in browser.find_elements(By.XPATH, xpath_map[el_type]) if el.is_displayed()]
        if el_index >= len(visible_elements): raise IndexError("Индекс элемента вне диапазона.")
        
        target_element = visible_elements[el_index]
        target_element.click()
        WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    except Exception as e:
        print(f"Ошибка клика: {e}")
    
    return get_page_content({})

def type_in_element(params):
    if browser is None: raise JsonRpcError(-32001, "Браузер не запущен.")
    element_id, text_to_type = params.get("id"), params.get("text")
    if not element_id or text_to_type is None: raise JsonRpcError(-32602, "Отсутствуют 'id' или 'text'.")
        
    try:
        el_type, el_index_str = element_id.split('_')
        el_index = int(el_index_str)
        
        if el_type != 'input': raise JsonRpcError(-32602, "Неверный тип элемента.")
        
        xpath = "//input[@type='text' or @type='password' or @type='search' or @type='email'] | //textarea"
        visible_elements = [el for el in browser.find_elements(By.XPATH, xpath) if el.is_displayed()]
        if el_index >= len(visible_elements): raise IndexError("Индекс поля ввода вне диапазона.")
        
        target_element = visible_elements[el_index]
        target_element.clear()
        target_element.send_keys(text_to_type)
        return {"status": "ok"}
    except Exception as e:
        raise JsonRpcError(-32000, f"Ошибка ввода текста: {e}")

# --- Описания функций и эндпоинты ---

# ИСПРАВЛЕНО: Возвращаем полные описания параметров
WEB_FUNCTIONS = [
    {
        "name": "navigate_to_url",
        "description": "Открывает веб-страницу по URL. Используй первым.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
    },
    {
        "name": "get_page_content",
        "description": "Анализирует ТЕКУЩУЮ страницу, возвращает текст и список ВИДИМЫХ интерактивных элементов (ссылки, поля, кнопки) с их ID. Вызывай, чтобы 'осмотреться'.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "click_element",
        "description": "Кликает по элементу по его ID из get_page_content.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string", "description": "ID элемента, например, 'link_5' или 'button_0'"}}, "required": ["id"]}
    },
    {
        "name": "type_in_element",
        "description": "Вводит текст в поле ввода по его ID из get_page_content.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}}, "required": ["id", "text"]}
    }
]
METHODS = {func['name']: globals()[func['name']] for func in WEB_FUNCTIONS}

@app.route("/functions")
def get_functions_route(): return jsonify(WEB_FUNCTIONS)

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
    port = int(os.getenv("MCP_WEB_PORT", 8002))
    print(f"[*] MCP_Web (Selenium) запускается на порту: {port} через Waitress.")
    serve(app, host="0.0.0.0", port=port)