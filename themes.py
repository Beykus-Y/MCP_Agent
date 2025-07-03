# themes.py

# Описываем цветовые палитры для разных тем
THEMES = {
    "light": {
        "window_bg": "#f0f0f0",
        "text_color": "#000000",
        "widget_bg": "#ffffff",
        "list_selection_bg": "#0078d7",
        "list_selection_text": "#ffffff",
        "button_bg": "#e1e1e1",
        "button_hover_bg": "#e5f1fb",
        "border_color": "#c0c0c0"
    },
    "dark": {
        "window_bg": "#2b2b2b",
        "text_color": "#dcdcdc",
        "widget_bg": "#3c3c3c",
        "list_selection_bg": "#0078d7",
        "list_selection_text": "#ffffff",
        "button_bg": "#555555",
        "button_hover_bg": "#6a6a6a",
        "border_color": "#505050"
    }
}

def get_stylesheet(theme_name: str) -> str:
    """Генерирует полную таблицу стилей QSS для указанной темы."""
    if theme_name not in THEMES:
        theme_name = "light" # Тема по умолчанию, если запрошена неизвестная
    
    colors = THEMES[theme_name]

    return f"""
        QMainWindow, QDialog {{
            background-color: {colors['window_bg']};
        }}
        QWidget {{
            color: {colors['text_color']};
        }}
        QTextEdit, QLineEdit, QComboBox, QSpinBox, QListWidget {{
            background-color: {colors['widget_bg']};
            color: {colors['text_color']};
            border: 1px solid {colors['border_color']};
            border-radius: 4px;
            padding: 4px;
        }}
        QTextEdit:read-only, QLineEdit:read-only {{
            background-color: {colors['window_bg']};
        }}
        QPushButton {{
            background-color: {colors['button_bg']};
            border: 1px solid {colors['border_color']};
            padding: 5px 10px;
            border-radius: 4px;
        }}
        QPushButton:hover {{
            background-color: {colors['button_hover_bg']};
        }}
        QPushButton:disabled {{
            background-color: {colors['window_bg']};
            color: #888888;
        }}
        QLabel {{
            color: {colors['text_color']};
            padding: 2px;
        }}
        QSplitter::handle {{
            background-color: {colors['window_bg']};
        }}
        QSplitter::handle:horizontal {{
            width: 1px;
        }}
        QSplitter::handle:vertical {{
            height: 1px;
        }}
        QListWidget::item:selected {{
            background-color: {colors['list_selection_bg']};
            color: {colors['list_selection_text']};
        }}
    """