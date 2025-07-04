# themes.py (Версия 2.0 - Улучшенные палитры)

# Описываем цветовые палитры для разных тем
THEMES = {
    "light": {
        "window_bg": "#f0f0f0",
        "text_color": "#202020",      # Не чисто черный
        "widget_bg": "#ffffff",
        "ai_bubble_bg": "#e9e9ef",    # НОВЫЙ: Цвет для пузырька ИИ
        "list_selection_bg": "#0078d7",
        "list_selection_text": "#ffffff",
        "button_bg": "#e1e1e1",
        "button_hover_bg": "#d0d0d0",
        "border_color": "#c0c0c0"
    },
    "dark": {
        "window_bg": "#2b2b2b",
        "text_color": "#dcdcdc",
        "widget_bg": "#3c3c3c",
        "ai_bubble_bg": "#4a4a4f",    # НОВЫЙ: Цвет для пузырька ИИ (контрастный)
        "list_selection_bg": "#0078d7",
        "list_selection_text": "#ffffff",
        "button_bg": "#555555",
        "button_hover_bg": "#6a6a6a",
        "border_color": "#505050"
    }
}

def get_stylesheet(theme_name: str) -> str:
    """Генерирует полную таблицу стилей QSS для указанной темы."""
    colors = THEMES.get(theme_name, THEMES["light"])

    # ИЗМЕНЕНО: Убрали стили для шрифтов, т.к. они теперь будут добавляться динамически
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
        QListWidget {{
            border: 1px solid {colors['border_color']};
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
            background-color: #444444;
            color: #888888;
        }}
        QLabel {{
            color: {colors['text_color']};
            padding: 2px;
        }}
        QSplitter::handle {{
            background-color: {colors['border_color']};
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
         QListWidget::item:hover {{
            background-color: {colors['button_hover_bg']};
        }}
        QScrollBar:vertical {{
            border: none; background: {colors['window_bg']}; width: 10px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: #555555; min-height: 20px; border-radius: 5px;
        }}
        QScrollBar:horizontal {{
            border: none; background: {colors['window_bg']}; height: 10px; margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: #555555; min-width: 20px; border-radius: 5px;
        }}
    """