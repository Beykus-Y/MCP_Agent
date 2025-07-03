# UI.py
import os
import logging
from dotenv import set_key, find_dotenv

from PyQt5 import QtWidgets, QtCore, QtGui
from themes import get_stylesheet, THEMES
from chat_manager import ChatManager
from settings_manager import SettingsManager

# --- Класс QTextEditLogger ---
class QTextEditLogger(logging.Handler, QtCore.QObject):
    """
    Класс для перенаправления логов в QTextEdit потокобезопасным способом.
    """
    log_received = QtCore.pyqtSignal(str)

    def __init__(self, widget):
        super().__init__()
        QtCore.QObject.__init__(self)
        self.widget = widget
        self.log_received.connect(self.widget.append)
        self.log_received.connect(lambda: self.widget.moveCursor(QtGui.QTextCursor.End))

    def emit(self, record):
        msg = self.format(record)
        self.log_received.emit(msg)

# --- Класс AIWorker ---
class AIWorker(QtCore.QObject):
    """Рабочий класс для выполнения запросов к ИИ в отдельном потоке."""
    finished = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    action_update = QtCore.pyqtSignal(str) # Новый сигнал

    def __init__(self, ai_iface, history):
        super().__init__()
        self.ai = ai_iface
        self.history = history
        self.ai.action_started.connect(self.action_update)

    @QtCore.pyqtSlot()
    def run(self):
        try:
            reply = self.ai.call_ai(self.history)
            self.finished.emit(reply)
        except Exception as e:
            logging.error(f"Критическая ошибка в потоке AIWorker: {e}", exc_info=True)
            self.error.emit(str(e))

# --- Класс SettingsDialog ---
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(300)
        
        layout = QtWidgets.QVBoxLayout(self)
        form_layout = QtWidgets.QFormLayout()

        # Настройка: Выбор цветовой темы
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(THEMES.keys()) # Заполняем из нашего словаря тем
        self.theme_combo.setCurrentText(self.settings_manager.get("color_theme"))
        form_layout.addRow("Цветовая тема:", self.theme_combo)

        # Настройка: Размер шрифта в чате
        self.chat_font_spinbox = QtWidgets.QSpinBox()
        self.chat_font_spinbox.setRange(8, 24)
        self.chat_font_spinbox.setValue(self.settings_manager.get("font_size_chat"))
        form_layout.addRow("Размер шрифта в чате:", self.chat_font_spinbox)
        
        # Настройка: Размер шрифта в логах
        self.logs_font_spinbox = QtWidgets.QSpinBox()
        self.logs_font_spinbox.setRange(8, 20)
        self.logs_font_spinbox.setValue(self.settings_manager.get("font_size_logs"))
        form_layout.addRow("Размер шрифта в логах:", self.logs_font_spinbox)

        layout.addLayout(form_layout)
        
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        # Сохраняем все значения
        self.settings_manager.set("color_theme", self.theme_combo.currentText())
        self.settings_manager.set("font_size_chat", self.chat_font_spinbox.value())
        self.settings_manager.set("font_size_logs", self.logs_font_spinbox.value())
        self.settings_manager.save_settings()
        super().accept()

# --- Класс MainWindow ---
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, ai_iface, models):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.setWindowTitle("AI + MCP Управление ПК")
        self.resize(800, 600)
        self.ai = ai_iface
        self.chat_manager = ChatManager()
        self.current_chat_id = None
        self.current_messages = []

        self.setup_ui(models) # Выносим создание UI в отдельный метод
        
        self.log_handler = QTextEditLogger(self.log_view)
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        
        self.populate_chat_list()
        self.apply_theme_and_settings() # Переименовали метод для ясности
        self.statusBar = QtWidgets.QStatusBar()
        self.setStatusBar(self.statusBar)
        logging.info("GUI инициализировано")

    def setup_ui(self, models):
        """Метод для создания и компоновки всех виджетов."""
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems(models)
        current = os.getenv("SELECTED_MODEL", models[0] if models else "")
        if current in models: self.model_combo.setCurrentText(current)
        save_btn = QtWidgets.QPushButton("Сохранить модель")
        save_btn.clicked.connect(self.on_save_model)
        
        settings_btn = QtWidgets.QPushButton()
        settings_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon))
        settings_btn.setToolTip("Настройки")
        settings_btn.clicked.connect(self.open_settings_dialog)
        
        self.chat_history = QtWidgets.QTextEdit()
        self.chat_history.setReadOnly(True)
        self.prompt_input = QtWidgets.QLineEdit()
        self.prompt_input.setPlaceholderText("Выберите чат или создайте новый...")
        self.send_btn = QtWidgets.QPushButton("Отправить")
        self.send_btn.clicked.connect(self.on_send)
        self.send_btn.setEnabled(False)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)

        self.chat_list_widget = QtWidgets.QListWidget()
        self.chat_list_widget.currentItemChanged.connect(self.on_select_chat)
        
        new_chat_btn = QtWidgets.QPushButton("Новый чат")
        new_chat_btn.clicked.connect(self.on_new_chat)
        delete_chat_btn = QtWidgets.QPushButton("Удалить чат")
        delete_chat_btn.clicked.connect(self.on_delete_chat)
        
        left_panel_layout = QtWidgets.QVBoxLayout()
        chat_buttons_layout = QtWidgets.QHBoxLayout()
        chat_buttons_layout.addWidget(new_chat_btn)
        chat_buttons_layout.addWidget(delete_chat_btn)
        left_panel_layout.addLayout(chat_buttons_layout)
        left_panel_layout.addWidget(self.chat_list_widget)
        left_panel_widget = QtWidgets.QWidget()
        left_panel_widget.setLayout(left_panel_layout)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(QtWidgets.QLabel("Модель:"))
        top_layout.addWidget(self.model_combo)
        top_layout.addWidget(save_btn)
        top_layout.addStretch()
        top_layout.addWidget(settings_btn)

        chat_input_layout = QtWidgets.QHBoxLayout()
        chat_input_layout.addWidget(self.prompt_input)
        chat_input_layout.addWidget(self.send_btn)

        right_panel_layout = QtWidgets.QVBoxLayout()
        right_panel_layout.addLayout(top_layout)
        right_panel_layout.addWidget(QtWidgets.QLabel("Чат с ИИ:"))
        right_panel_layout.addWidget(self.chat_history, stretch=3)
        right_panel_layout.addLayout(chat_input_layout)
        right_panel_layout.addWidget(QtWidgets.QLabel("Логи:"))
        right_panel_layout.addWidget(self.log_view, stretch=1)
        right_panel_widget = QtWidgets.QWidget()
        right_panel_widget.setLayout(right_panel_layout)

        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_splitter.addWidget(left_panel_widget)
        main_splitter.addWidget(right_panel_widget)
        main_splitter.setStretchFactor(1, 3)
        
        self.setCentralWidget(main_splitter)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings_manager, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.apply_theme_and_settings()
            logging.info("Настройки обновлены и применены.")

    def apply_theme_and_settings(self):
        """Применяет и цветовую тему, и настройки шрифтов."""
        # 1. Применяем глобальную цветовую тему
        theme_name = self.settings_manager.get("color_theme")
        stylesheet = get_stylesheet(theme_name)
        # Получаем экземпляр QApplication и устанавливаем стиль для всего приложения
        app = QtWidgets.QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
            
        # 2. Применяем индивидуальные размеры шрифтов (это надежнее делать поверх QSS)
        chat_font_size = self.settings_manager.get("font_size_chat")
        logs_font_size = self.settings_manager.get("font_size_logs")
        
        font = self.chat_history.font()
        font.setPointSize(chat_font_size)
        self.chat_history.setFont(font)
        self.prompt_input.setFont(font)
        
        font.setPointSize(logs_font_size)
        self.log_view.setFont(font)

    def populate_chat_list(self):
        self.chat_list_widget.clear()
        chats = self.chat_manager.get_chats()
        for chat in chats:
            item = QtWidgets.QListWidgetItem(chat["title"])
            item.setData(QtCore.Qt.UserRole, chat["id"])
            self.chat_list_widget.addItem(item)
    
    def on_new_chat(self):
        self.chat_list_widget.setCurrentItem(None)
        self.current_chat_id = None
        self.current_messages = []
        self.chat_history.clear()
        self.prompt_input.setPlaceholderText("Введите первое сообщение для нового чата...")
        self.send_btn.setEnabled(True)
        self.prompt_input.setFocus()
        logging.info("Начат новый чат.")

    def on_delete_chat(self):
        current_item = self.chat_list_widget.currentItem()
        if not current_item:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выберите чат для удаления.")
            return
        reply = QtWidgets.QMessageBox.question(self, "Подтверждение",
            f"Вы уверены, что хотите удалить чат «{current_item.text()}»?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            chat_id = current_item.data(QtCore.Qt.UserRole)
            self.chat_manager.delete_chat(chat_id)
            logging.info(f"Чат {chat_id} удален.")
            self.populate_chat_list()
            self.on_new_chat()

    def on_select_chat(self, current_item, previous_item):
        if not current_item:
            return
        chat_id = current_item.data(QtCore.Qt.UserRole)
        self.current_chat_id = chat_id
        messages, title = self.chat_manager.load_chat_history(chat_id)
        self.current_messages = messages
        self.chat_history.clear()
        for msg in self.current_messages:
            role = "Вы" if msg['role'] == 'user' else 'ИИ'
            color = 'blue' if role == 'Вы' else 'black'
            self.chat_history.append(f"<b style='color:{color};'>{role}:</b> {msg['content']}")
        self.prompt_input.setPlaceholderText("Введите команду или вопрос ИИ...")
        self.send_btn.setEnabled(True)
        logging.info(f"Загружен чат «{title}» ({chat_id})")

    def on_save_model(self):
        new_model = self.model_combo.currentText()
        env_path = find_dotenv()
        set_key(env_path, "SELECTED_MODEL", new_model)
        logging.info(f"Модель сохранена: {new_model}")
        QtWidgets.QMessageBox.information(self, "Успех", f"Модель «{new_model}» сохранена в .env")

    def on_send(self):
        prompt = self.prompt_input.text().strip()
        if not prompt:
            return
        
        self.current_messages.append({"role": "user", "content": prompt})
        self.chat_history.append(f"<b style='color:blue;'>Вы:</b> {prompt}")
        self.prompt_input.clear()
        
        self.statusBar.showMessage("Отправка запроса ИИ...")
        self.set_input_state(enabled=False, placeholder="ИИ думает...")

        # --- ИЗМЕНЕНО: Упрощаем вызов AIWorker ---
        # Теперь мы передаем только ПОЛНУЮ ИСТОРИЮ.
        # AIWorker и call_ai сами разберутся, что делать.
        self.worker = AIWorker(self.ai, self.current_messages.copy()) 
        # --------------------------------------------
        
        self.thread = QtCore.QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.handle_ai_reply)
        self.worker.error.connect(self.handle_ai_error)
        self.worker.action_update.connect(self.update_status)
        
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()


    @QtCore.pyqtSlot(str)
    def update_status(self, message):
        self.statusBar.showMessage(message)

    def handle_ai_reply(self, reply):
        """Слот для обработки успешного ответа от ИИ."""
        self.chat_history.append(f"<b>ИИ:</b> {reply}")
        self.current_messages.append({"role": "assistant", "content": reply})
        logging.info("Ответ ИИ получен.")
        self.statusBar.clearMessage()
        new_id, new_title = self.chat_manager.save_chat(self.current_chat_id, self.current_messages)
        if not self.current_chat_id:
            self.current_chat_id = new_id
            self.populate_chat_list()
            for i in range(self.chat_list_widget.count()):
                item = self.chat_list_widget.item(i)
                if item.data(QtCore.Qt.UserRole) == self.current_chat_id:
                    item.setText(new_title)
                    self.chat_list_widget.setCurrentItem(item)
                    break
        self.set_input_state(enabled=True)

    def handle_ai_error(self, err):
        """Слот для обработки ошибки."""
        self.chat_history.append(f"<span style='color:red;'><b>Ошибка:</b> {err}</span>")
        logging.error(f"Ошибка при вызове ИИ: {err}")
        self.statusBar.clearMessage()

        self.set_input_state(enabled=True)

    def set_input_state(self, enabled, placeholder=None):
        """Вспомогательный метод для управления состоянием поля ввода."""
        self.send_btn.setEnabled(enabled)
        self.prompt_input.setEnabled(enabled)
        if placeholder is None:
            placeholder = "Введите команду или вопрос ИИ..." if enabled else ""
        self.prompt_input.setPlaceholderText(placeholder)