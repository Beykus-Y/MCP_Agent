# mcp_semantic_memory.py

import os
import sqlite3
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from flask import Flask, request, jsonify
from waitress import serve
import threading
import json
import networkx as nx
from networkx.readwrite import json_graph

# --- Конфигурация ---
DB_FILE = "semantic_memory.db"
FAISS_INDEX_FILE = "semantic_memory.index"
GRAPH_FILE = "knowledge_graph.json"
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'

# --- Глобальные переменные для ленивой инициализации ---
app_globals = {"model": None, "index": None, "conn": None, "graph": None}
initialization_lock = threading.Lock()

app = Flask(__name__)

# --- Инициализация ---
def ensure_memory_loaded():
    """
    Проверяет, загружена ли память. Если нет - загружает ее.
    Выполняется под замком, чтобы избежать гонки состояний.
    """
    with initialization_lock:
        if app_globals["model"] is not None:
            return

        print("[MCP_Memory] НАЧАЛО ТЯЖЕЛОЙ ИНИЦИАЛИЗАЦИИ...")
        
        # 1. Модель для векторизации
        print("[MCP_Memory] Загрузка Sentence-Transformer модели...")
        app_globals["model"] = SentenceTransformer(MODEL_NAME)
        print("[MCP_Memory] Модель загружена.")
        
        # 2. SQLite для хранения текстов
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE IF NOT EXISTS memory_chunks (id INTEGER PRIMARY KEY, text_content TEXT NOT NULL)")
        app_globals["conn"] = conn
        
        # 3. FAISS индекс для векторов
        embedding_dim = app_globals["model"].get_sentence_embedding_dimension()
        if os.path.exists(FAISS_INDEX_FILE):
            print("[MCP_Memory] Загрузка FAISS индекса...")
            app_globals["index"] = faiss.read_index(FAISS_INDEX_FILE)
        else:
            print("[MCP_Memory] Создание нового FAISS индекса...")
            app_globals["index"] = faiss.IndexIDMap(faiss.IndexFlatL2(embedding_dim))
            
        # 4. Граф знаний
        print("[MCP_Memory] Загрузка графа знаний...")
        if os.path.exists(GRAPH_FILE):
            try:
                with open(GRAPH_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # ИСПРАВЛЕНО: Явно указываем параметр `edges`, чтобы убрать FutureWarning
                    app_globals["graph"] = json_graph.node_link_graph(data, edges="links") 
            except (json.JSONDecodeError, nx.NetworkXError):
                app_globals["graph"] = nx.DiGraph()
        else:
            app_globals["graph"] = nx.DiGraph()

        print("[MCP_Memory] ИНИЦИАЛИЗАЦИЯ ЗАВЕРШЕНА.")

# --- Описания функций для ИИ ---
MEMORY_FUNCTIONS = [
    {
        "name": "remember",
        "description": "Сохраняет фрагмент текста (факт, идею) в семантическую память для поиска по смыслу.",
        "parameters": {"type": "object", "properties": {"text_chunk": {"type": "string"}}, "required": ["text_chunk"]}
    },
    {
        "name": "recall",
        "description": "Ищет в семантической памяти информацию, похожую по смыслу на запрос.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    },
    {
        "name": "create_entity",
        "description": "Создает новую сущность (узел) в графе знаний. Используй для определения человека, проекта, места и т.д. ID должен быть уникальным.",
        "parameters": {"type": "object", "properties": {"node_id": {"type": "string", "description": "Уникальный ID узла, например, 'user_2105984481' или 'project_X'"}, "label": {"type": "string", "description": "Человеко-понятное имя, например, 'Юля'"}, "node_type": {"type": "string", "description": "Тип узла: 'Person', 'Project', 'Topic', 'Alias'"}}, "required": ["node_id", "label", "node_type"]}
    },
    {
        "name": "link_entities",
        "description": "Создает направленную связь (ребро) между двумя сущностями в графе знаний. Например, от ника к реальному имени.",
        "parameters": {"type": "object", "properties": {"source_id": {"type": "string"}, "target_id": {"type": "string"}, "relation": {"type": "string", "description": "Описание связи, например, 'is_alias_for', 'works_on', 'discussed'"}}, "required": ["source_id", "target_id", "relation"]}
    },
    {
        "name": "find_entity_by_label",
        "description": "Ищет в графе знаний ID сущности по ее человеко-понятному имени (label). Важнейшая функция для идентификации.",
        "parameters": {"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"]}
    },
     {
        "name": "get_entity_details",
        "description": "Получает всю информацию о сущности и ее связях по ID. Позволяет понять, с кем или чем связан объект.",
        "parameters": {"type": "object", "properties": {"node_id": {"type": "string"}}, "required": ["node_id"]}
    },
    {
        "name": "update_entity_label",
        "description": "Обновляет или добавляет человеко-понятное имя (label) для УЖЕ СУЩЕСТВУЮЩЕЙ сущности по ее ID.",
        "parameters": {"type": "object", "properties": {"node_id": {"type": "string"}, "new_label": {"type": "string"}}, "required": ["node_id", "new_label"]}
    }
]

# --- Класс ошибки и хелперы ---
class JsonRpcError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message
def make_error_response(id_, code, message): return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})
def make_success_response(id_, result): return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})

# --- Реализация методов ---
def remember(params):
    ensure_memory_loaded()
    text = params['text_chunk']
    if not text.strip(): raise JsonRpcError(-32602, "Нельзя запомнить пустой текст.")
    cursor = app_globals["conn"].cursor()
    cursor.execute("INSERT INTO memory_chunks (text_content) VALUES (?)", (text,))
    app_globals["conn"].commit()
    text_id = cursor.lastrowid
    embedding = app_globals["model"].encode([text])[0].astype('float32')
    app_globals["index"].add_with_ids(np.array([embedding]), np.array([text_id]))
    faiss.write_index(app_globals["index"], FAISS_INDEX_FILE)
    return {"status": "ok", "memory_id": text_id}

def recall(params):
    ensure_memory_loaded()
    query, top_k = params['query'], params.get('top_k', 3)
    if app_globals["index"].ntotal == 0: return {"status": "empty"}
    query_embedding = app_globals["model"].encode([query])[0].astype('float32')
    num_to_search = min(top_k * 2, app_globals["index"].ntotal)
    distances, ids = app_globals["index"].search(np.array([query_embedding]), num_to_search)
    found_ids = tuple(int(id_) for id_ in ids[0] if id_ != -1)
    if not found_ids: return {"status": "not_found"}
    cursor = app_globals["conn"].cursor()
    placeholders = ','.join('?' for _ in found_ids)
    cursor.execute(f"SELECT id, text_content FROM memory_chunks WHERE id IN ({placeholders})", found_ids)
    rows_map = {row['id']: row['text_content'] for row in cursor.fetchall()}
    results = [{"relevance": round(float(np.exp(-dist / 2)), 2), "memory": rows_map[id_]} for id_, dist in zip(found_ids, distances[0]) if id_ in rows_map]
    results.sort(key=lambda x: x['relevance'], reverse=True)
    return {"status": "ok", "recalled_memories": results[:top_k]}

def save_graph():
    data = json_graph.node_link_data(app_globals["graph"])
    with open(GRAPH_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def create_entity(params):
    ensure_memory_loaded()
    node_id, label, node_type = params['node_id'], params['label'], params['node_type']
    app_globals["graph"].add_node(node_id, label=label, type=node_type)
    save_graph()
    return {"status": "ok", "message": f"Сущность '{label}' создана с ID '{node_id}'."}

def link_entities(params):
    ensure_memory_loaded()
    source_id, target_id, relation = params['source_id'], params['target_id'], params['relation']
    if not app_globals["graph"].has_node(source_id) or not app_globals["graph"].has_node(target_id):
        raise JsonRpcError(-32602, "Одна или обе сущности не существуют. Сначала создайте их.")
    app_globals["graph"].add_edge(source_id, target_id, label=relation)
    save_graph()
    return {"status": "ok", "message": f"Связь '{relation}' установлена."}

def find_entity_by_label(params):
    ensure_memory_loaded()
    label_to_find = params['label'].lower()
    found_nodes = [{"id": node, **data} for node, data in app_globals["graph"].nodes(data=True) if data.get('label', '').lower() == label_to_find]
    return {"entities": found_nodes} if found_nodes else {"status": "not_found"}

def get_entity_details(params):
    ensure_memory_loaded()
    node_id = params['node_id']
    if not app_globals["graph"].has_node(node_id):
        return {"status": "not_found"}
    details = {"node": {"id": node_id, **app_globals["graph"].nodes[node_id]}}
    details["relations"] = [{"source": u, "target": v, "relation": d.get('label')} for u, v, d in app_globals["graph"].edges(data=True) if u == node_id or v == node_id]
    return details

def update_entity_label(params):
    ensure_memory_loaded()
    node_id, new_label = params['node_id'], params['new_label']
    if not app_globals["graph"].has_node(node_id):
        raise JsonRpcError(-32602, f"Сущность с ID '{node_id}' не найдена. Сначала создайте ее.")
    
    app_globals["graph"].nodes[node_id]['label'] = new_label
    save_graph()
    return {"status": "ok", "message": f"Имя для сущности '{node_id}' обновлено на '{new_label}'."}

# --- Стандартная часть MCP ---
METHODS = {
    "remember": remember, "recall": recall, "create_entity": create_entity,
    "link_entities": link_entities, "find_entity_by_label": find_entity_by_label,
    "get_entity_details": get_entity_details,
    "update_entity_label": update_entity_label
}

@app.route("/functions")
def get_functions_route(): return jsonify(MEMORY_FUNCTIONS)

@app.route("/mcp", methods=["POST"])
def mcp_entrypoint():
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
    except Exception as e:
        code = e.code if isinstance(e, JsonRpcError) else -32603
        msg = str(e.message) if isinstance(e, JsonRpcError) else str(e)
        return make_error_response(req.get('id'), code, msg), 500

if __name__ == "__main__":
    # Выполняем инициализацию сразу при старте, т.к. она теперь включает граф
    # и другие важные компоненты, которые лучше подготовить заранее.
    # Ленивая инициализация остается на случай сбоев.
    ensure_memory_loaded() 
    port = int(os.getenv("MCP_SEMANTIC_MEMORY_PORT", 8007))
    print(f"[*] MCP_Semantic_Memory (граф+векторы) запускается на порту: {port} через Waitress.")
    serve(app, host="0.0.0.0", port=port)