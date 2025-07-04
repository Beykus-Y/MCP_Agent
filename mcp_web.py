# mcp_web.py (Версия 4.2 - Финальная, с полным разделением обязанностей)

import os
import json
from flask import Flask, request, jsonify
from waitress import serve
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# --- Глобальное состояние и инициализация ---
app = Flask(__name__)
browser = None

def start_browser():
    """Инициализирует и запускает браузер, если он еще не запущен."""
    global browser
    if browser is None:
        print("[MCP_Web] Инициализация браузера Selenium...")
        try:
            # Убедитесь, что chromedriver.exe находится в той же папке или прописан в системный PATH
            service = Service(executable_path='./chromedriver.exe')
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            browser = webdriver.Chrome(service=service, options=options)
            browser.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            print("[MCP_Web] Браузер успешно запущен.")
        except Exception as e:
            print(f"[MCP_Web] КРИТИЧЕСКАЯ ОШИБКА: Не удалось запустить браузер: {e}")
            browser = None

# --- Класс ошибки и хелперы ---
class JsonRpcError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message
def make_error_response(id_, code, message): return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})
def make_success_response(id_, result): return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})


# --- ФИНАЛЬНЫЙ НАБОР ИНСТРУМЕНТОВ С ЧЕТКИМ РАЗДЕЛЕНИЕМ ---

def navigate_to_url(params):
    """Шаг 1: Переходит по указанному URL. Не возвращает содержимое страницы. После этого нужно 'осмотреться'."""
    start_browser()
    if browser is None: raise JsonRpcError(-32001, "Браузер не запущен.")
    url = params.get("url")
    if not url: raise JsonRpcError(-32602, "'url' отсутствует.")
    try:
        browser.get(url)
        WebDriverWait(browser, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        return {"status": "ok", "url": browser.current_url}
    except Exception as e:
        raise JsonRpcError(-32000, f"Ошибка при навигации на {url}: {e}")

def read_page_text(params):
    """Инструмент для ЧТЕНИЯ: извлекает и возвращает основной текстовый контент с текущей страницы."""
    if browser is None: raise JsonRpcError(-32001, "Браузер не запущен.")
    try:
        soup = BeautifulSoup(browser.page_source, "html.parser")
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)
        return {"title": browser.title, "text_summary": text[:4000] + ("..." if len(text) > 4000 else "")}
    except Exception as e:
        raise JsonRpcError(-32000, f"Ошибка при чтении текста страницы: {e}")

def find_images_on_page(params):
    """Инструмент для ПОИСКА КАРТИНОК: сканирует страницу и возвращает список URL изображений."""
    if browser is None: raise JsonRpcError(-32001, "Браузер не запущен.")
    found_images = []
    try:
        img_elements = browser.find_elements(By.TAG_NAME, "img")
        for i, el in enumerate(img_elements):
            if el.is_displayed() and el.size['width'] > 100 and el.size['height'] > 100:
                src = el.get_attribute('src')
                if src and src.startswith('http'):
                    found_images.append({"id": f"image_{i}", "src": src, "alt": el.get_attribute('alt') or "Без описания"})
    except Exception as e:
        raise JsonRpcError(-32000, f"Ошибка при поиске изображений: {e}")
    return {"images": found_images[:20]}

def get_interactive_elements(params):
    """Инструмент для НАВИГАЦИИ: возвращает список ссылок, кнопок и полей ввода."""
    if browser is None: raise JsonRpcError(-32001, "Браузер не запущен.")
    elements = []
    try:
        link_elements = browser.find_elements(By.XPATH, "//a[@href]")
        for i, el in enumerate(link_elements):
            if el.is_displayed() and el.text.strip(): elements.append({"id": f"link_{i}", "type": "link", "text": el.text.strip()})
        input_elements = browser.find_elements(By.XPATH, "//input[@type='text' or @type='password' or @type='search' or @type='email'] | //textarea")
        for i, el in enumerate(input_elements):
            if el.is_displayed():
                text = el.get_attribute('aria-label') or el.get_attribute('placeholder') or el.get_attribute('title') or f"Поле ввода {i}"
                elements.append({"id": f"input_{i}", "type": "input", "text": text})
        button_elements = browser.find_elements(By.XPATH, "//button | //input[@type='submit' or @type='button']")
        for i, el in enumerate(button_elements):
            if el.is_displayed():
                text = el.text.strip() or el.get_attribute('value') or f"Кнопка {i}"
                if text: elements.append({"id": f"button_{i}", "type": "button", "text": text})
    except Exception as e:
        raise JsonRpcError(-32000, f"Ошибка при поиске интерактивных элементов: {e}")
    return {"elements": elements[:50]}

def click_element(params):
    """Выполняет клик по элементу, найденному через get_interactive_elements."""
    if browser is None: raise JsonRpcError(-32001, "Браузер не запущен.")
    element_id = params.get("id");
    if not element_id: raise JsonRpcError(-32602, "'id' отсутствует.")
    try:
        el_type, el_index_str = element_id.split('_'); el_index = int(el_index_str)
        xpath_map = {'link': "//a[@href]", 'button': "//button | //input[@type='submit' or @type='button']"}
        if el_type not in xpath_map: raise JsonRpcError(-32602, "Неверный тип элемента.")
        visible_elements = [el for el in browser.find_elements(By.XPATH, xpath_map[el_type]) if el.is_displayed()]
        if el_index >= len(visible_elements): raise IndexError("Индекс элемента вне диапазона.")
        target_element = visible_elements[el_index]
        target_element.click()
        WebDriverWait(browser, 10).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        return {"status": "ok", "url": browser.current_url}
    except Exception as e:
        raise JsonRpcError(-32000, f"Ошибка клика по элементу {element_id}: {e}")

def type_in_element(params):
    """Вводит текст в поле, найденное через get_interactive_elements."""
    if browser is None: raise JsonRpcError(-32001, "Браузер не запущен.")
    element_id, text_to_type = params.get("id"), params.get("text")
    if not element_id or text_to_type is None: raise JsonRpcError(-32602, "Отсутствуют 'id' или 'text'.")
    try:
        el_type, el_index_str = element_id.split('_'); el_index = int(el_index_str)
        if el_type != 'input': raise JsonRpcError(-32602, "Тип элемента должен быть 'input'.")
        xpath = "//input[@type='text' or @type='password' or @type='search' or @type='email'] | //textarea"
        visible_elements = [el for el in browser.find_elements(By.XPATH, xpath) if el.is_displayed()]
        if el_index >= len(visible_elements): raise IndexError("Индекс поля ввода вне диапазона.")
        target_element = visible_elements[el_index]
        target_element.clear(); target_element.send_keys(text_to_type)
        return {"status": "ok"}
    except Exception as e:
        raise JsonRpcError(-32000, f"Ошибка ввода текста в {element_id}: {e}")

# --- ОБНОВЛЕННЫЕ ОПИСАНИЯ ИНСТРУМЕНТОВ ---
WEB_FUNCTIONS = [
    {
        "name": "navigate_to_url",
        "description": "Шаг 1: Открывает веб-страницу по URL. После этого необходимо 'осмотреться', используя другие инструменты.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "Полный URL для перехода"}}, "required": ["url"]}
    },
    {
        "name": "read_page_text",
        "description": "Инструмент для ЧТЕНИЯ: извлекает основной текстовый контент со страницы. Используй, если нужно найти информацию, прочитать статью или ответить на вопрос по содержимому страницы.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "find_images_on_page",
        "description": "Инструмент для ПОИСКА КАРТИНОК: сканирует текущую страницу и возвращает список URL-адресов изображений. Используй, если конечная цель — показать картинку пользователю.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_interactive_elements",
        "description": "Инструмент для НАВИГАЦИИ: сканирует страницу и возвращает список ссылок, кнопок и полей ввода. Используй, чтобы понять, куда можно кликнуть или что-то ввести.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "click_element",
        "description": "Выполняет клик по элементу (ссылке или кнопке) по его ID из результата `get_interactive_elements`.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string", "description": "ID элемента, например, 'link_5'"}}, "required": ["id"]}
    },
    {
        "name": "type_in_element",
        "description": "Вводит текст в поле ввода по его ID из результата `get_interactive_elements`.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string", "description": "ID поля ввода, например, 'input_0'"}, "text": {"type": "string", "description": "Текст для ввода"}}, "required": ["id", "text"]}
    }
]

METHODS = {func['name']: globals()[func['name']] for func in WEB_FUNCTIONS}

@app.route("/functions")
def get_functions_route(): return jsonify(WEB_FUNCTIONS)

@app.route("/mcp", methods=["POST"])
def mcp_entrypoint():
    try:
        req = request.get_json(force=True)
        if req.get("method") not in METHODS: raise JsonRpcError(-32601, f"Метод не найден: {req.get('method')}")
        result = METHODS[req['method']](req.get('params', {}))
        return make_success_response(req.get('id'), result)
    except Exception as e:
        code = getattr(e, 'code', -32603); msg = getattr(e, 'message', str(e))
        return make_error_response(req.get('id'), code, msg), 500

if __name__ == "__main__":
    port = int(os.getenv("MCP_WEB_PORT", 8002))
    print(f"[*] MCP_Web (v4.2 - Финал) запускается на порту: {port} через Waitress.")
    serve(app, host="0.0.0.0", port=port)