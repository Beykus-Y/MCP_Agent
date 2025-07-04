# launcher.py (ВЕРСИЯ 4.0 - Улучшенный UI/UX)
import sys
import os
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui
from dotenv import set_key, find_dotenv, dotenv_values
import qtawesome as qta

from mcp_registry import MCP_REGISTRY

# --- Классы ProcessStopper и StreamReader остаются без изменений ---
class ProcessStopper(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    log_message = QtCore.pyqtSignal(str)
    def __init__(self, processes_dict):
        super().__init__(); self.processes_to_stop = processes_dict
    @QtCore.pyqtSlot()
    def run(self):
        self.log_message.emit("--- [СТОП] Начало асинхронной остановки MCP ---")
        if not self.processes_to_stop:
            self.log_message.emit("[INFO] Нет активных MCP для остановки."); self.finished.emit(); return
        for key, data in list(self.processes_to_stop.items()):
            config = MCP_REGISTRY[key]
            self.log_message.emit(f"[*] Останавливаем '{config['name']}' (PID: {data['process'].pid})...")
            if data['reader']: data['reader'].stop()
            if data['thread']: data['thread'].quit(); data['thread'].wait(2000)
            if data['process']: data['process'].terminate(); data['process'].wait(5000)
            self.log_message.emit(f"[OK] MCP '{config['name']}' остановлен.")
        self.log_message.emit("--- [СТОП] Все процессы завершены ---"); self.finished.emit()

class StreamReader(QtCore.QObject):
    new_log_line = QtCore.pyqtSignal(str)
    def __init__(self, stream):
        super().__init__(); self.stream = stream; self._stopped = False
    @QtCore.pyqtSlot()
    def run(self):
        while not self._stopped:
            try:
                line = self.stream.readline()
                if line: self.new_log_line.emit(line.strip())
                else: break
            except Exception: break
    def stop(self): self._stopped = True

class LauncherWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.processes = {} 
        self.running_mcps = []
        self.is_shutting_down = False
        
        # Устанавливаем иконку для окна
        self.setWindowIcon(qta.icon('fa5s.rocket'))
        
        self.setup_ui()
        self.setWindowTitle("MCP Launcher v4.0 - Центр Управления")
        self.resize(850, 700)
        self.load_settings()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # 1. Секция выбора MCP
        mcp_selection_box = QtWidgets.QGroupBox("1. Выберите MCP для запуска")
        form_layout = QtWidgets.QFormLayout()
        form_layout.setSpacing(10)
        self.checkboxes = {}
        for key, config in MCP_REGISTRY.items():
            self.checkboxes[key] = QtWidgets.QCheckBox(config["name"])
            
            # НОВОЕ: Кнопка помощи (?)
            help_button = QtWidgets.QPushButton(qta.icon('fa5.question-circle'), "")
            help_button.setFixedSize(24, 24)
            help_button.setFlat(True)
            help_button.setToolTip("Узнать возможности этого MCP")
            # Используем lambda для передачи нужного описания в обработчик
            help_button.clicked.connect(lambda _, d=config['description'], t=config['name']: self._show_mcp_info(t, d))

            row_layout = QtWidgets.QHBoxLayout()
            row_layout.addWidget(self.checkboxes[key])
            row_layout.addStretch()
            row_layout.addWidget(help_button)
            
            form_layout.addRow(row_layout)
        mcp_selection_box.setLayout(form_layout)

        # 2. Глобальные настройки
        settings_box = QtWidgets.QGroupBox("2. Глобальные настройки (.env)")
        settings_layout = QtWidgets.QFormLayout()
        self.setting_inputs = {
            "OPENAI_API_KEY": QtWidgets.QLineEdit(),
            "OPENAI_API_BASE": QtWidgets.QLineEdit(),
            "TELEGRAM_API_ID": QtWidgets.QLineEdit(),
            "TELEGRAM_API_HASH": QtWidgets.QLineEdit(),
            "MCP_FILES_BASE_DIR": QtWidgets.QLineEdit(),
        }
        
        # НОВОЕ: Поля с кнопкой "Показать/Скрыть"
        self._add_password_field(settings_layout, "OpenAI API Key:", self.setting_inputs["OPENAI_API_KEY"])
        settings_layout.addRow("OpenAI API Base URL:", self.setting_inputs["OPENAI_API_BASE"])
        settings_layout.addRow("Telegram API ID:", self.setting_inputs["TELEGRAM_API_ID"])
        self._add_password_field(settings_layout, "Telegram API Hash:", self.setting_inputs["TELEGRAM_API_HASH"])
        
        # НОВОЕ: Поле с кнопкой "Выбрать папку"
        self._add_browse_field(settings_layout, "Workspace Path:", self.setting_inputs["MCP_FILES_BASE_DIR"])

        save_settings_button = QtWidgets.QPushButton(qta.icon('fa5s.save'), "Сохранить настройки в .env")
        save_settings_button.clicked.connect(self.save_settings)
        settings_layout.addRow(save_settings_button)
        settings_box.setLayout(settings_layout)

        # 3. Секция управления
        control_box = QtWidgets.QGroupBox("3. Управление процессами")
        control_layout = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton(qta.icon('fa5s.play'), " Запустить выбранные")
        self.start_button.clicked.connect(self.start_processes)
        self.stop_button = QtWidgets.QPushButton(qta.icon('fa5s.stop'), " Остановить все")
        self.stop_button.clicked.connect(self.stop_processes)
        control_layout.addWidget(self.start_button); control_layout.addWidget(self.stop_button)
        control_box.setLayout(control_layout)

        # 4. Логи
        log_box = QtWidgets.QGroupBox("Логи MCP")
        log_layout = QtWidgets.QVBoxLayout()
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        # Улучшенный стиль для логов
        self.log_view.setFont(QtGui.QFont("Consolas", 9))
        self.log_view.setStyleSheet("QTextEdit { color: #dcdcdc; background-color: #2b2b2b; }")
        log_layout.addWidget(self.log_view)
        log_box.setLayout(log_layout)
        
        # 5. Секция Запуска
        launch_box = QtWidgets.QGroupBox("4. Запуск приложений")
        launch_layout = QtWidgets.QGridLayout()
        
        self.launch_main_button = QtWidgets.QPushButton(qta.icon('fa5s.desktop'), " Запустить главный GUI")
        self.launch_main_button.clicked.connect(self.launch_main_app)
        self.launch_main_button.setEnabled(False)
        self.launch_main_button.setToolTip("Запускает main.py, используя настройки из .env")

        self.launch_visualizer_button = QtWidgets.QPushButton(qta.icon('fa5s.map-marked-alt'), " Запустить Визуализатор RPG")
        self.launch_visualizer_button.clicked.connect(self.launch_visualizer)
        self.launch_visualizer_button.setToolTip("Запускает rpg_visualizer.py.\nТребует запущенного 'RPG Engine' MCP.")

        launch_layout.addWidget(self.launch_main_button, 0, 0)
        launch_layout.addWidget(self.launch_visualizer_button, 0, 1)
        launch_box.setLayout(launch_layout)

        # Компоновка
        main_layout.addWidget(mcp_selection_box)
        main_layout.addWidget(settings_box)
        main_layout.addWidget(control_box)
        main_layout.addWidget(log_box, stretch=1)
        main_layout.addWidget(launch_box)

    # --- НОВЫЕ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ДЛЯ UI ---
    def _add_password_field(self, layout, label_text, line_edit):
        line_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        
        reveal_button = QtWidgets.QPushButton(qta.icon('fa5s.eye'), "")
        reveal_button.setFixedSize(28, 28)
        reveal_button.setToolTip("Показать/Скрыть")
        reveal_button.setCheckable(True)
        reveal_button.clicked.connect(lambda checked: self._toggle_password_visibility(line_edit, reveal_button, checked))
        
        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(line_edit)
        hbox.addWidget(reveal_button)
        layout.addRow(label_text, hbox)

    def _add_browse_field(self, layout, label_text, line_edit):
        browse_button = QtWidgets.QPushButton(qta.icon('fa5s.folder-open'), "")
        browse_button.setFixedSize(28, 28)
        browse_button.setToolTip("Выбрать папку")
        browse_button.clicked.connect(lambda: self._browse_workspace_path(line_edit))
        
        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(line_edit)
        hbox.addWidget(browse_button)
        layout.addRow(label_text, hbox)

    # --- НОВЫЕ СЛОТЫ ДЛЯ КНОПОК ---
    def _toggle_password_visibility(self, line_edit, button, checked):
        if checked:
            line_edit.setEchoMode(QtWidgets.QLineEdit.Normal)
            button.setIcon(qta.icon('fa5s.eye-slash'))
        else:
            line_edit.setEchoMode(QtWidgets.QLineEdit.Password)
            button.setIcon(qta.icon('fa5s.eye'))

    def _browse_workspace_path(self, line_edit):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Выберите рабочую папку", line_edit.text())
        if directory:
            line_edit.setText(directory)
            self.log(f"[INFO] Выбрана рабочая папка: {directory}")

    def _show_mcp_info(self, title, description):
        QtWidgets.QMessageBox.information(self, f"Возможности MCP: {title}", description)

    # --- Остальные методы остаются без изменений в своей логике ---
    def load_settings(self):
        self.log("[INFO] Загрузка настроек из .env файла...")
        dotenv_path = find_dotenv();
        if not os.path.exists(dotenv_path): self.log("[WARN] .env файл не найден."); return
        values = dotenv_values(dotenv_path)
        for key, widget in self.setting_inputs.items(): widget.setText(values.get(key, ""))
        self.log("[OK] Настройки загружены.")

    def save_settings(self):
        self.log("[INFO] Сохранение настроек в .env файл...")
        dotenv_path = find_dotenv()
        if not os.path.exists(dotenv_path):
            with open(".env", "w"): pass; dotenv_path = find_dotenv()
        for key, widget in self.setting_inputs.items(): set_key(dotenv_path, key, widget.text())
        self.log("[OK] Настройки успешно сохранены в .env.")
        QtWidgets.QMessageBox.information(self, "Успех", "Настройки сохранены в .env файл.")
        
    def log(self, message):
        self.log_view.append(message); self.log_view.moveCursor(QtGui.QTextCursor.End)

    def start_processes(self):
        self.log("--- [ЗАПУСК] Начало запуска выбранных MCP ---")
        to_start_keys = [key for key, cb in self.checkboxes.items() if cb.isChecked() and key not in self.processes]
        if not to_start_keys:
            self.log("[INFO] Нет новых MCP для запуска.")
            self.launch_main_button.setEnabled(len(self.processes) > 0); return
        for key in to_start_keys:
            config = MCP_REGISTRY[key]
            self.log(f"[*] Запускаем '{config['name']}' ({config['script']})...")
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                process = subprocess.Popen([sys.executable, config['script']], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
                reader_thread = QtCore.QThread(); stream_reader = StreamReader(process.stdout)
                stream_reader.moveToThread(reader_thread)
                stream_reader.new_log_line.connect(lambda line, p=config['name']: self.log(f"[{p}] {line}"))
                reader_thread.started.connect(stream_reader.run); reader_thread.start()
                self.processes[key] = {"process": process, "thread": reader_thread, "reader": stream_reader}
                self.running_mcps.append(key)
                self.log(f"[OK] MCP '{config['name']}' запущен с PID: {process.pid}")
            except Exception as e:
                self.log(f"[ОШИБКА] Не удалось запустить '{config['name']}': {e}")
        self.launch_main_button.setEnabled(True); self.start_button.setEnabled(False); self.stop_button.setEnabled(True)

    def stop_processes(self):
        if not self.processes: self.log("[INFO] Нет активных MCP для остановки."); return
        self.stop_button.setEnabled(False); self.start_button.setEnabled(False); self.launch_main_button.setEnabled(False)
        self.stopper_thread = QtCore.QThread(); self.stopper_worker = ProcessStopper(self.processes.copy())
        self.stopper_worker.moveToThread(self.stopper_thread)
        self.stopper_thread.started.connect(self.stopper_worker.run)
        self.stopper_worker.finished.connect(self.on_stopping_finished)
        self.stopper_worker.log_message.connect(self.log)
        self.stopper_worker.finished.connect(self.stopper_thread.quit)
        self.stopper_worker.finished.connect(self.stopper_worker.deleteLater)
        self.stopper_thread.finished.connect(self.stopper_thread.deleteLater)
        self.stopper_thread.start()

    @QtCore.pyqtSlot()
    def on_stopping_finished(self):
        self.processes.clear(); self.running_mcps.clear()
        self.start_button.setEnabled(True); self.stop_button.setEnabled(False)
        self.launch_main_button.setEnabled(False)
        if self.is_shutting_down: self.log("[INFO] Процессы остановлены, приложение закрывается."); self.close()

    def launch_main_app(self):
        self.log("--- [ЗАПУСК] Запуск main.py с передачей активных MCP ---")
        
        if not self.running_mcps:
            self.log("[ОШИБКА] Нет запущенных MCP для передачи в main.py.")
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Сначала запустите хотя бы один MCP.")
            return

        active_mcps_string = ",".join(sorted(self.running_mcps))
        self.log(f"[*] Передаем в main.py следующие MCP: {active_mcps_string}")
        
        # Формируем команду: python.exe main.py files,web,rpg
        command = [sys.executable, "main.py", active_mcps_string]
        
        try:
            subprocess.Popen(command)
            self.log("[OK] Главный GUI запущен в отдельном процессе.")
        except Exception as e:
            self.log(f"[ОШИБКА] Не удалось запустить main.py: {e}")
    
    def launch_visualizer(self):
        self.log("--- [ЗАПУСК] Запускаем Визуализатор RPG ---")
        if "rpg" not in self.running_mcps:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Для запуска визуализатора необходимо сначала запустить 'RPG Engine' MCP.")
            self.log("[ОШИБКА] Попытка запуска визуализатора без запущенного MCP_RPG.")
            return
        try:
            subprocess.Popen([sys.executable, "rpg_visualizer.py"])
            self.log("[OK] Визуализатор запущен в отдельном процессе.")
        except Exception as e:
            self.log(f"[ОШИБКА] Не удалось запустить rpg_visualizer.py: {e}")

    def closeEvent(self, event):
        if self.is_shutting_down: event.accept(); return
        if self.processes:
            reply = QtWidgets.QMessageBox.question(self, 'Подтверждение выхода', "Вы уверены? Все запущенные MCP будут остановлены.", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                self.log("[INFO] Инициирован выход из приложения. Остановка MCP...")
                self.is_shutting_down = True; self.stop_processes(); event.ignore()
            else:
                event.ignore()
        else:
            event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    # Применяем стиль для улучшения внешнего вида на разных ОС
    app.setStyle("Fusion")
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec_())