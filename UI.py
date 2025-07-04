# UI.py (Версия 3.5 - Финальная исправленная)
import os
import logging
import base64
import json
import mimetypes
import requests

from dotenv import set_key, find_dotenv
from PyQt5 import QtWidgets, QtCore, QtGui
import qtawesome as qta

from themes import get_stylesheet, THEMES
from chat_manager import ChatManager
from settings_manager import SettingsManager


class ImageDownloader(QtCore.QObject):
    """Загружает изображения из сети в отдельном потоке."""
    finished = QtCore.pyqtSignal(QtGui.QPixmap)
    def __init__(self, url):
        super().__init__(); self.url = url
    @QtCore.pyqtSlot()
    def run(self):
        try:
            resp = requests.get(self.url, timeout=10)
            resp.raise_for_status()
            pixmap = QtGui.QPixmap(); pixmap.loadFromData(resp.content)
            self.finished.emit(pixmap)
        except Exception as e:
            logging.error(f"Ошибка загрузки изображения с {self.url}: {e}")
            self.finished.emit(QtGui.QPixmap()) # Отправляем пустую картинку в случае ошибки

class ChatMessageWidget(QtWidgets.QWidget):
    """Виджет для отображения одного сообщения с текстом и/или картинкой."""
    def __init__(self, text, role, image_path=None, image_url=None, parent=None):
        super().__init__(parent); self.setObjectName("ChatMessageWidget")
        
        main_layout = QtWidgets.QVBoxLayout(self); main_layout.setSpacing(5)
        self.bubble_widget = QtWidgets.QWidget(); self.bubble_widget.setObjectName("BubbleWidget")
        bubble_layout = QtWidgets.QVBoxLayout(self.bubble_widget); bubble_layout.setContentsMargins(10, 10, 10, 10)
        
        if image_path or image_url:
            self.image_label = QtWidgets.QLabel("Загрузка изображения...")
            self.image_label.setMinimumHeight(100); self.image_label.setAlignment(QtCore.Qt.AlignCenter)
            self.image_label.setStyleSheet("border: 1px dashed #888; border-radius: 8px;")
            bubble_layout.addWidget(self.image_label)
            
            if image_path:
                self.set_pixmap(QtGui.QPixmap(image_path))
            elif image_url:
                if image_url.startswith('data:image'):
                    try:
                        header, b64_data = image_url.split(',', 1)
                        image_bytes = base64.b64decode(b64_data)
                        pixmap = QtGui.QPixmap(); pixmap.loadFromData(image_bytes)
                        self.set_pixmap(pixmap)
                    except Exception as e:
                        logging.error(f"Ошибка декодирования base64: {e}")
                        self.image_label.setText("Ошибка\nотображения")
                else:
                    self.downloader = ImageDownloader(image_url); self.thread = QtCore.QThread()
                    self.downloader.moveToThread(self.thread); self.thread.started.connect(self.downloader.run)
                    self.downloader.finished.connect(self.set_pixmap); self.downloader.finished.connect(self.thread.quit)
                    self.downloader.finished.connect(self.downloader.deleteLater); self.thread.finished.connect(self.thread.deleteLater)
                    self.thread.start()

        if text:
            self.text_label = QtWidgets.QLabel(text); self.text_label.setWordWrap(True)
            self.text_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            bubble_layout.addWidget(self.text_label)
        
        hbox = QtWidgets.QHBoxLayout(); hbox.setContentsMargins(0, 0, 0, 0)
        theme_colors = THEMES.get(SettingsManager().get("color_theme"), THEMES["light"])
        
        if role == 'user':
            bg_color = theme_colors["list_selection_bg"]
            hbox.addStretch(); hbox.addWidget(self.bubble_widget, 0, QtCore.Qt.AlignRight)
        else:
            bg_color = theme_colors["ai_bubble_bg"] if role != 'error' else "#d32f2f"
            hbox.addWidget(self.bubble_widget, 0, QtCore.Qt.AlignLeft); hbox.addStretch()
            
        self.bubble_widget.setStyleSheet(f"QWidget#BubbleWidget {{ background-color: {bg_color}; border-radius: 15px; }}")
        main_layout.addLayout(hbox)

    def set_pixmap(self, pixmap):
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(300, 300, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap); self.image_label.setFixedSize(scaled_pixmap.size())
        else:
            self.image_label.setText("Не удалось\nзагрузить\nизображение")

class QTextEditLogger(logging.Handler, QtCore.QObject):
    log_received = QtCore.pyqtSignal(str)
    def __init__(self, widget):
        super().__init__(); QtCore.QObject.__init__(self); self.widget = widget
        self.log_received.connect(self.widget.append); self.log_received.connect(lambda: self.widget.moveCursor(QtGui.QTextCursor.End))
    def emit(self, record): self.log_received.emit(self.format(record))
class AIWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(str); error = QtCore.pyqtSignal(str); action_update = QtCore.pyqtSignal(str)
    def __init__(self, ai_iface, history):
        super().__init__(); self.ai = ai_iface; self.history = history; self.ai.action_started.connect(self.action_update)
    @QtCore.pyqtSlot()
    def run(self):
        try: self.finished.emit(self.ai.call_ai(self.history))
        except Exception as e: logging.error(f"Критическая ошибка: {e}", exc_info=True); self.error.emit(str(e))
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent); self.settings_manager = settings_manager; self.setWindowTitle("Настройки"); self.setMinimumWidth(300)
        layout = QtWidgets.QVBoxLayout(self); form_layout = QtWidgets.QFormLayout()
        self.theme_combo = QtWidgets.QComboBox(); self.theme_combo.addItems(THEMES.keys()); self.theme_combo.setCurrentText(self.settings_manager.get("color_theme")); form_layout.addRow("Цветовая тема:", self.theme_combo)
        self.chat_font_spinbox = QtWidgets.QSpinBox(); self.chat_font_spinbox.setRange(8, 24); self.chat_font_spinbox.setValue(self.settings_manager.get("font_size_chat")); form_layout.addRow("Размер шрифта в чате:", self.chat_font_spinbox)
        self.logs_font_spinbox = QtWidgets.QSpinBox(); self.logs_font_spinbox.setRange(8, 20); self.logs_font_spinbox.setValue(self.settings_manager.get("font_size_logs")); form_layout.addRow("Размер шрифта в логах:", self.logs_font_spinbox)
        layout.addLayout(form_layout)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, QtCore.Qt.Horizontal, self); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def accept(self):
        self.settings_manager.set("color_theme", self.theme_combo.currentText()); self.settings_manager.set("font_size_chat", self.chat_font_spinbox.value()); self.settings_manager.set("font_size_logs", self.logs_font_spinbox.value())
        self.settings_manager.save_settings(); super().accept()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, ai_iface, models):
        super().__init__()
        self.settings_manager = SettingsManager(); self.setWindowTitle("AI + MCP Управление ПК"); self.resize(900, 700)
        self.ai = ai_iface; self.chat_manager = ChatManager(); self.current_chat_id = None
        self.current_messages = []; self.loading_timer = QtCore.QTimer(self); self.loading_timer.timeout.connect(self._update_loading_animation)
        self.loading_dot_count = 0; self.attached_image_path = None
        self.setup_ui(models)
        self.log_handler = QTextEditLogger(self.log_view); self.log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        logging.getLogger().addHandler(self.log_handler); logging.getLogger().setLevel(logging.INFO); logging.getLogger("httpx").setLevel(logging.WARNING)
        self.populate_chat_list(); self.apply_theme_and_settings(); self.setStatusBar(QtWidgets.QStatusBar()); logging.info("GUI инициализировано")

    def setup_ui(self, models):
        self.model_combo = QtWidgets.QComboBox(); self.model_combo.addItems(models); current = os.getenv("SELECTED_MODEL", models[0] if models else "");
        if current in models: self.model_combo.setCurrentText(current)
        save_btn = QtWidgets.QPushButton("Сохранить модель"); save_btn.clicked.connect(self.on_save_model)
        settings_btn = QtWidgets.QPushButton(qta.icon('fa5s.cog'), ""); settings_btn.setToolTip("Настройки"); settings_btn.setFlat(True); settings_btn.clicked.connect(self.open_settings_dialog)
        
        # --- Кнопки управления чатами ---
        new_chat_btn = QtWidgets.QPushButton(qta.icon('fa5s.plus-circle'), " Новый чат")
        new_chat_btn.clicked.connect(self.on_new_chat) # <-- ВОССТАНОВЛЕНО
        delete_chat_btn = QtWidgets.QPushButton(qta.icon('fa5s.trash-alt'), " Удалить чат")
        delete_chat_btn.clicked.connect(self.on_delete_chat) # <-- ВОССТАНОВЛЕНО

        self.chat_list_widget = QtWidgets.QListWidget()
        self.chat_list_widget.currentItemChanged.connect(self.on_select_chat) # <-- ВОССТАНОВЛЕНО
        
        left_panel_layout = QtWidgets.QVBoxLayout(); chat_buttons_layout = QtWidgets.QHBoxLayout(); chat_buttons_layout.addWidget(new_chat_btn); chat_buttons_layout.addWidget(delete_chat_btn)
        left_panel_layout.addLayout(chat_buttons_layout); left_panel_layout.addWidget(self.chat_list_widget); left_panel_widget = QtWidgets.QWidget(); left_panel_widget.setLayout(left_panel_layout)
        top_layout = QtWidgets.QHBoxLayout(); top_layout.addWidget(QtWidgets.QLabel("Модель:")); top_layout.addWidget(self.model_combo); top_layout.addWidget(save_btn); top_layout.addStretch(); top_layout.addWidget(settings_btn)
        self.chat_history_list = QtWidgets.QListWidget(); self.chat_history_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection); self.chat_history_list.setStyleSheet("QListWidget { border: none; }")
        self.loading_indicator_label = QtWidgets.QLabel("ИИ думает..."); self.loading_indicator_label.setAlignment(QtCore.Qt.AlignCenter); self.loading_indicator_label.hide()
        self.attachment_preview = QtWidgets.QWidget(); self.attachment_preview.setObjectName("AttachmentPreview"); preview_layout = QtWidgets.QHBoxLayout(self.attachment_preview); preview_layout.setContentsMargins(5,5,5,5)
        self.attachment_thumb = QtWidgets.QLabel(); self.attachment_thumb.setFixedSize(40,40)
        remove_btn = QtWidgets.QPushButton(qta.icon('fa5s.times-circle'), ""); remove_btn.setFlat(True); remove_btn.clicked.connect(self._remove_attachment)
        preview_layout.addWidget(self.attachment_thumb); preview_layout.addStretch(); preview_layout.addWidget(remove_btn); self.attachment_preview.hide()
        attach_btn = QtWidgets.QPushButton(qta.icon('fa5s.paperclip'), ""); attach_btn.setFlat(True); attach_btn.setToolTip("Прикрепить изображение"); attach_btn.clicked.connect(self._on_attach_file)
        self.prompt_input = QtWidgets.QLineEdit(); self.prompt_input.setObjectName("PromptInput"); self.prompt_input.setPlaceholderText("Выберите чат или создайте новый...")
        self.send_btn = QtWidgets.QPushButton(qta.icon('fa5s.paper-plane'), " Отправить"); self.send_btn.clicked.connect(self.on_send); self.send_btn.setEnabled(False)
        self.prompt_input.returnPressed.connect(self.on_send)
        chat_input_layout = QtWidgets.QHBoxLayout(); chat_input_layout.addWidget(attach_btn); chat_input_layout.addWidget(self.prompt_input); chat_input_layout.addWidget(self.send_btn)
        self.log_view = QtWidgets.QTextEdit(); self.log_view.setReadOnly(True); self.log_view.setObjectName("LogView")
        right_panel_layout = QtWidgets.QVBoxLayout(); right_panel_layout.addLayout(top_layout); right_panel_layout.addWidget(QtWidgets.QLabel("Чат с ИИ:"))
        right_panel_layout.addWidget(self.chat_history_list, stretch=3); right_panel_layout.addWidget(self.loading_indicator_label)
        right_panel_layout.addWidget(self.attachment_preview); right_panel_layout.addLayout(chat_input_layout); right_panel_layout.addWidget(QtWidgets.QLabel("Логи:")); right_panel_layout.addWidget(self.log_view, stretch=1)
        right_panel_widget = QtWidgets.QWidget(); right_panel_widget.setLayout(right_panel_layout)
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal); main_splitter.addWidget(left_panel_widget); main_splitter.addWidget(right_panel_widget)
        main_splitter.setStretchFactor(1, 3); main_splitter.setSizes([250, 650]); self.setCentralWidget(main_splitter)

    def _on_attach_file(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите изображение", "", "Изображения (*.png *.jpg *.jpeg *.webp)")
        if file_path: self.attached_image_path = file_path; pixmap = QtGui.QPixmap(file_path).scaled(40, 40, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation); self.attachment_thumb.setPixmap(pixmap); self.attachment_preview.show()

    def _remove_attachment(self): self.attached_image_path = None; self.attachment_preview.hide()

    def _add_message_static(self, text, role, image_path=None, image_url=None):
        widget = ChatMessageWidget(text, role, image_path, image_url); item = QtWidgets.QListWidgetItem(self.chat_history_list)
        item.setSizeHint(widget.sizeHint()); self.chat_history_list.addItem(item); self.chat_history_list.setItemWidget(item, widget)

    def add_message_to_chat(self, text, role, image_path=None, image_url=None):
        self._add_message_static(text, role, image_path, image_url)
        last_item_widget = self.chat_history_list.itemWidget(self.chat_history_list.item(self.chat_history_list.count() - 1))
        if last_item_widget:
            effect = QtWidgets.QGraphicsOpacityEffect(opacity=0.0); last_item_widget.setGraphicsEffect(effect); self.anim = QtCore.QPropertyAnimation(effect, b"opacity"); self.anim.setDuration(350)
            self.anim.setStartValue(0.0); self.anim.setEndValue(1.0); self.anim.setEasingCurve(QtCore.QEasingCurve.InQuad); self.anim.start(QtCore.QAbstractAnimation.DeleteWhenStopped)
        QtCore.QTimer.singleShot(50, self.chat_history_list.scrollToBottom)

    def apply_theme_and_settings(self):
        theme_name = self.settings_manager.get("color_theme"); chat_font_size = self.settings_manager.get("font_size_chat"); logs_font_size = self.settings_manager.get("font_size_logs")
        base_stylesheet = get_stylesheet(theme_name)
        font_stylesheet = f"""QWidget#ChatMessageWidget QLabel {{font-size: {chat_font_size}pt;}} QLineEdit#PromptInput {{font-size: {chat_font_size}pt;}} QTextEdit#LogView {{font-size: {logs_font_size}pt;}}"""
        final_stylesheet = base_stylesheet + font_stylesheet; app = QtWidgets.QApplication.instance();
        if app: app.setStyleSheet(final_stylesheet)

    def _update_loading_animation(self): self.loading_dot_count = (self.loading_dot_count + 1) % 4; self.loading_indicator_label.setText(f"ИИ думает{'.' * self.loading_dot_count}")
    
    def _start_loading_animation(self): self.loading_dot_count = 0; self.loading_indicator_label.setText("ИИ думает."); self.loading_indicator_label.show(); self.loading_timer.start(500)

    def _stop_loading_animation(self): self.loading_timer.stop(); self.loading_indicator_label.hide()
        
    def set_input_state(self, enabled, placeholder=None):
        self.send_btn.setEnabled(enabled); self.prompt_input.setEnabled(enabled)
        attach_btn = self.send_btn.parent().findChild(QtWidgets.QPushButton);
        if attach_btn: attach_btn.setEnabled(enabled)
        if enabled:
            self._stop_loading_animation(); self.statusBar().clearMessage()
            self.prompt_input.setPlaceholderText(placeholder or "Введите команду..."); self.prompt_input.setFocus()
        else:
            self._start_loading_animation()
            self.statusBar().showMessage(placeholder or "ИИ обрабатывает запрос..."); self.prompt_input.setPlaceholderText("")

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings_manager, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.apply_theme_and_settings()
            if self.current_chat_id:
                current_item = self.chat_list_widget.currentItem()
                if current_item: self.on_select_chat(current_item, None)
            logging.info("Настройки обновлены.")

    def on_select_chat(self, current_item, previous_item):
        """
        Загружает историю сообщений для выбранного чата и отображает их.
        Исправлено для поддержки мультимодальных сообщений и GUI-команд.
        """
        if not current_item: return
        chat_id = current_item.data(QtCore.Qt.UserRole)
        self.current_chat_id = chat_id
        messages, title = self.chat_manager.load_chat_history(chat_id)
        self.current_messages = messages
        self.chat_history_list.clear()

        for msg in self.current_messages:
            content = msg.get('content')
            role = msg.get('role')
            text_to_display = ""
            image_url_to_display = None

            if role == 'user':
                # Сообщения пользователя могут быть мультимодальными (текст + изображение)
                if isinstance(content, list):
                    for part in content:
                        if part.get('type') == 'text':
                            text_to_display = part.get('text', '')
                        if part.get('type') == 'image_url':
                            image_url_to_display = part.get('image_url', {}).get('url')
                elif isinstance(content, str): # Старый формат, только текст
                    text_to_display = content
                self._add_message_static(text_to_display, role, image_url=image_url_to_display)

            elif role == 'assistant':
                # Сообщения ассистента могут быть простым текстом или GUI-командой (JSON-строкой)
                if isinstance(content, str):
                    try:
                        # Попытка разобрать как JSON для GUI-команд
                        parsed_content = json.loads(content)
                        if isinstance(parsed_content, dict) and "gui_tool" in parsed_content:
                            tool_name = parsed_content["gui_tool"]
                            params = parsed_content.get("params", {})
                            if tool_name == "display_text":
                                text_to_display = params.get("text", "")
                            elif tool_name == "display_image":
                                text_to_display = params.get("caption", "")
                                image_url_to_display = params.get("url")
                            else:
                                text_to_display = f"Неизвестная GUI команда при загрузке: {tool_name}"
                        else:
                            # Не GUI-команда, обрабатываем как обычный текст
                            text_to_display = content
                    except json.JSONDecodeError:
                        # Не JSON-строка, обрабатываем как обычный текст
                        text_to_display = content
                
                # Если content был уже списком (из более старых мультимодальных ответов ассистента, хотя это менее распространено)
                elif isinstance(content, list):
                     for part in content:
                        if part.get('type') == 'text':
                            text_to_display = part.get('text', '')
                        if part.get('type') == 'image_url':
                            image_url_to_display = part.get('image_url', {}).get('url')
                else: # Запасной вариант для всего остального (например, числа, булевы значения - хотя маловероятно для content)
                    text_to_display = str(content)

                self._add_message_static(text_to_display, role, image_url=image_url_to_display)
            
            else: # Для ролей 'error' или других
                 if isinstance(content, list):
                    for part in content:
                        if part.get('type') == 'text':
                            text_to_display = part.get('text', '')
                        # Сообщения об ошибках обычно не содержат изображений, но сохраняем для надежности
                        if part.get('type') == 'image_url':
                            image_url_to_display = part.get('image_url', {}).get('url')
                 else:
                     text_to_display = str(content) # Преобразуем любой тип в строку

                 self._add_message_static(text_to_display, role, image_url=image_url_to_display)


        self.chat_history_list.scrollToBottom()
        self.prompt_input.setPlaceholderText("Введите команду...")
        self.send_btn.setEnabled(True)
        logging.info(f"Загружен чат «{title}» ({chat_id})")

    # --- ВОССТАНОВЛЕННЫЕ МЕТОДЫ УПРАВЛЕНИЯ ЧАТАМИ ---
    def on_new_chat(self):
        self.chat_list_widget.setCurrentItem(None)
        self.current_chat_id = None
        self.current_messages = []
        self.chat_history_list.clear()
        self.prompt_input.setPlaceholderText("Введите первое сообщение...")
        self.send_btn.setEnabled(True)
        self.prompt_input.setFocus()
        logging.info("Начат новый чат.")

    def on_delete_chat(self):
        current_item = self.chat_list_widget.currentItem()
        if not current_item:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выберите чат для удаления.")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "Подтверждение",
            f"Вы уверены, что хотите удалить чат «{current_item.text()}»?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            chat_id = current_item.data(QtCore.Qt.UserRole)
            self.chat_manager.delete_chat(chat_id)
            logging.info(f"Чат {chat_id} удален.")
            self.populate_chat_list()
            self.on_new_chat() # После удаления переключаемся на новый чат

    def on_send(self):
        prompt = self.prompt_input.text().strip()
        if not prompt and not self.attached_image_path: return
        self.set_input_state(enabled=False); content_list = []
        if prompt: content_list.append({"type": "text", "text": prompt})
        if self.attached_image_path:
            try:
                mime_type, _ = mimetypes.guess_type(self.attached_image_path)
                if not mime_type: mime_type = "image/jpeg"
                with open(self.attached_image_path, "rb") as f: image_data_b64 = base64.b64encode(f.read()).decode('utf-8')
                content_list.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data_b64}"}})
            except Exception as e: logging.error(f"Ошибка кодирования: {e}"); self.add_message_to_chat(f"Ошибка: {e}", "error"); self.set_input_state(enabled=True); return
        self.current_messages.append({"role": "user", "content": content_list}); self.add_message_to_chat(prompt, 'user', image_path=self.attached_image_path); self.prompt_input.clear(); self._remove_attachment()
        self.worker = AIWorker(self.ai, self.current_messages.copy()); self.thread = QtCore.QThread()
        self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.finished.connect(self.handle_ai_reply); self.worker.error.connect(self.handle_ai_error); self.worker.action_update.connect(self.statusBar().showMessage)
        self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater); self.thread.start()

    def handle_ai_reply(self, reply):
        self.set_input_state(enabled=True)
        try:
            gui_command = json.loads(reply)
            if isinstance(gui_command, dict) and "gui_tool" in gui_command:
                tool_name = gui_command["gui_tool"]; params = gui_command.get("params", {})
                if tool_name == "display_image": 
                    self.add_message_to_chat(params.get("caption", ""), "assistant", image_url=params.get("url"))
                    self.current_messages.append({"role": "assistant", "content": reply})
                elif tool_name == "display_text": # НОВОЕ
                    self.add_message_to_chat(params.get("text", ""), "assistant")
                    self.current_messages.append({"role": "assistant", "content": reply})
                else: self.add_message_to_chat(f"Неизвестная GUI команда: {tool_name}", "error")
                self.chat_manager.save_chat(self.current_chat_id, self.current_messages); return
        except (json.JSONDecodeError, TypeError): pass
        self.add_message_to_chat(reply, 'assistant'); self.current_messages.append({"role": "assistant", "content": reply}); logging.info("Ответ ИИ получен.")
        new_id, new_title = self.chat_manager.save_chat(self.current_chat_id, self.current_messages)
        if not self.current_chat_id:
            self.current_chat_id = new_id; self.populate_chat_list()
            for i in range(self.chat_list_widget.count()):
                item = self.chat_list_widget.item(i)
                if item.data(QtCore.Qt.UserRole) == self.current_chat_id: item.setText(new_title); self.chat_list_widget.setCurrentItem(item); break

    def handle_ai_error(self, err_msg): self.set_input_state(enabled=True); self.add_message_to_chat(f"Ошибка: {err_msg}", "error"); logging.error(f"Ошибка при вызове ИИ: {err_msg}")

    def populate_chat_list(self):
        self.chat_list_widget.clear(); chats = self.chat_manager.get_chats()
        for chat in chats: item = QtWidgets.QListWidgetItem(chat["title"]); item.setData(QtCore.Qt.UserRole, chat["id"]); self.chat_list_widget.addItem(item)
    
    def on_save_model(self):
        new_model = self.model_combo.currentText(); env_path = find_dotenv()
        if env_path: set_key(env_path, "SELECTED_MODEL", new_model); logging.info(f"Модель сохранена: {new_model}"); QtWidgets.QMessageBox.information(self, "Успех", f"Модель «{new_model}» сохранена в .env")
        else: logging.warning("Файл .env не найден."); QtWidgets.QMessageBox.warning(self, "Ошибка", "Не удалось найти файл .env.")