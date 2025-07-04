# launcher.py (ВЕРСИЯ 3.0 - с управлением .env и неблокирующей остановкой)
import sys
import os
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui
from dotenv import set_key, find_dotenv, dotenv_values

from mcp_registry import MCP_REGISTRY

# --- НОВЫЙ КЛАСС: Неблокирующий остановщик процессов ---
# Этот воркер будет выполняться в отдельном потоке, чтобы не замораживать GUI.
class ProcessStopper(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    log_message = QtCore.pyqtSignal(str)

    def __init__(self, processes_dict):
        super().__init__()
        self.processes_to_stop = processes_dict

    @QtCore.pyqtSlot()
    def run(self):
        self.log_message.emit("--- [СТОП] Начало асинхронной остановки MCP ---")
        if not self.processes_to_stop:
            self.log_message.emit("[INFO] Нет активных MCP для остановки.")
            self.finished.emit()
            return

        for key, data in list(self.processes_to_stop.items()):
            config = MCP_REGISTRY[key]
            self.log_message.emit(f"[*] Останавливаем '{config['name']}' (PID: {data['process'].pid})...")
            
            # Корректно завершаем потоки и процессы
            if data['reader']: data['reader'].stop()
            if data['thread']: data['thread'].quit(); data['thread'].wait(2000) # Ждем до 2 сек
            if data['process']: data['process'].terminate(); data['process'].wait(5000) # Ждем до 5 сек
            
            self.log_message.emit(f"[OK] MCP '{config['name']}' остановлен.")
        
        self.log_message.emit("--- [СТОП] Все процессы завершены ---")
        self.finished.emit()

# Класс StreamReader остается без изменений
class StreamReader(QtCore.QObject):
    new_log_line = QtCore.pyqtSignal(str)
    def __init__(self, stream):
        super().__init__()
        self.stream = stream; self._stopped = False
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
        self.setup_ui()
        self.setWindowTitle("MCP Launcher v3.0 - Центр Управления")
        self.resize(800, 650)
        self.load_settings() # Загружаем настройки при старте

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # 1. Секция выбора MCP
        mcp_selection_box = QtWidgets.QGroupBox("1. Выберите MCP для запуска")
        form_layout = QtWidgets.QFormLayout()
        self.checkboxes = {}
        for key, config in MCP_REGISTRY.items():
            self.checkboxes[key] = QtWidgets.QCheckBox(config["name"])
            form_layout.addRow(self.checkboxes[key])
        mcp_selection_box.setLayout(form_layout)

        # 2. НОВАЯ СЕКЦИЯ: Глобальные настройки
        settings_box = QtWidgets.QGroupBox("2. Глобальные настройки (.env)")
        settings_layout = QtWidgets.QFormLayout()
        
        # Словарь для хранения полей ввода
        self.setting_inputs = {
            "OPENAI_API_KEY": QtWidgets.QLineEdit(),
            "OPENAI_API_BASE": QtWidgets.QLineEdit(),
            "TELEGRAM_API_ID": QtWidgets.QLineEdit(),
            "TELEGRAM_API_HASH": QtWidgets.QLineEdit(),
            "MCP_FILES_BASE_DIR": QtWidgets.QLineEdit(),
        }
        
        # Настройка отображения паролей
        self.setting_inputs["OPENAI_API_KEY"].setEchoMode(QtWidgets.QLineEdit.Password)
        self.setting_inputs["TELEGRAM_API_HASH"].setEchoMode(QtWidgets.QLineEdit.Password)
        
        # Добавляем поля в форму
        settings_layout.addRow("OpenAI API Key:", self.setting_inputs["OPENAI_API_KEY"])
        settings_layout.addRow("OpenAI API Base URL:", self.setting_inputs["OPENAI_API_BASE"])
        settings_layout.addRow("Telegram API ID:", self.setting_inputs["TELEGRAM_API_ID"])
        settings_layout.addRow("Telegram API Hash:", self.setting_inputs["TELEGRAM_API_HASH"])
        settings_layout.addRow("Workspace Path:", self.setting_inputs["MCP_FILES_BASE_DIR"])
        
        save_settings_button = QtWidgets.QPushButton("Сохранить настройки в .env")
        save_settings_button.clicked.connect(self.save_settings)
        settings_layout.addRow(save_settings_button)
        
        settings_box.setLayout(settings_layout)

        # 3. Секция управления
        control_box = QtWidgets.QGroupBox("3. Управление процессами")
        control_layout = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("Запустить выбранные")
        self.start_button.clicked.connect(self.start_processes)
        self.stop_button = QtWidgets.QPushButton("Остановить все")
        self.stop_button.clicked.connect(self.stop_processes) # Теперь не будет зависать
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_box.setLayout(control_layout)

        # 4. Логи
        log_box = QtWidgets.QGroupBox("Логи MCP")
        log_layout = QtWidgets.QVBoxLayout()
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True); self.log_view.setFont(QtGui.QFont("Courier New", 9))
        log_layout.addWidget(self.log_view)
        log_box.setLayout(log_layout)
        
        # 5. Запуск GUI
        main_app_box = QtWidgets.QGroupBox("4. Запуск основного приложения")
        main_app_layout = QtWidgets.QVBoxLayout()
        self.launch_main_button = QtWidgets.QPushButton("Запустить главный GUI (main.py)")
        self.launch_main_button.clicked.connect(self.launch_main_app)
        self.launch_main_button.setEnabled(False) 
        info_label = QtWidgets.QLabel("Будет использована конфигурация из файла .env")
        info_label.setStyleSheet("color: grey;")
        main_app_layout.addWidget(self.launch_main_button)
        main_app_layout.addWidget(info_label, alignment=QtCore.Qt.AlignCenter)
        main_app_box.setLayout(main_app_layout)

        #6 Визуализатор
        visualizer_box = QtWidgets.QGroupBox("5. RPG Инструменты")
        visualizer_layout = QtWidgets.QHBoxLayout()
        self.launch_visualizer_button = QtWidgets.QPushButton("Запустить Визуализатор RPG")
        self.launch_visualizer_button.clicked.connect(self.launch_visualizer)
        visualizer_layout.addWidget(self.launch_visualizer_button)
        visualizer_box.setLayout(visualizer_layout)
        
        # Компоновка
        main_layout.addWidget(mcp_selection_box)
        main_layout.addWidget(settings_box)
        main_layout.addWidget(control_box)
        main_layout.addWidget(log_box, stretch=1)
        main_layout.addWidget(main_app_box)
        main_layout.addWidget(visualizer_box)

    # --- НОВЫЕ МЕТОДЫ для работы с .env ---
    def load_settings(self):
        """Загружает настройки из .env в поля ввода."""
        self.log("[INFO] Загрузка настроек из .env файла...")
        dotenv_path = find_dotenv()
        if not os.path.exists(dotenv_path):
            self.log("[WARN] .env файл не найден. Будет создан при сохранении.")
            return

        values = dotenv_values(dotenv_path)
        for key, widget in self.setting_inputs.items():
            widget.setText(values.get(key, ""))
        self.log("[OK] Настройки загружены.")

    def save_settings(self):
        """Сохраняет значения из полей ввода в .env файл."""
        self.log("[INFO] Сохранение настроек в .env файл...")
        dotenv_path = find_dotenv()
        if not os.path.exists(dotenv_path):
            with open(".env", "w"): pass # Создаем пустой файл
            dotenv_path = find_dotenv()

        for key, widget in self.setting_inputs.items():
            set_key(dotenv_path, key, widget.text())
        
        self.log("[OK] Настройки успешно сохранены в .env.")
        QtWidgets.QMessageBox.information(self, "Успех", "Настройки сохранены в .env файл.")
        
    def log(self, message):
        self.log_view.append(message)
        self.log_view.moveCursor(QtGui.QTextCursor.End)

    def start_processes(self):
        self.log("--- [ЗАПУСК] Начало запуска выбранных MCP ---")
        # Логика запуска остается такой же
        to_start_keys = [key for key, cb in self.checkboxes.items() if cb.isChecked() and key not in self.processes]
        
        if not to_start_keys:
            self.log("[INFO] Нет новых MCP для запуска.")
            self.launch_main_button.setEnabled(len(self.processes) > 0)
            return

        for key in to_start_keys:
            config = MCP_REGISTRY[key]
            self.log(f"[*] Запускаем '{config['name']}' ({config['script']})...")
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                process = subprocess.Popen(
                    [sys.executable, config['script']],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    encoding='utf-8', errors='replace', creationflags=creationflags
                )
                
                reader_thread = QtCore.QThread()
                stream_reader = StreamReader(process.stdout)
                stream_reader.moveToThread(reader_thread)
                stream_reader.new_log_line.connect(lambda line, p=config['name']: self.log(f"[{p}] {line}"))
                reader_thread.started.connect(stream_reader.run)
                reader_thread.start()

                self.processes[key] = {"process": process, "thread": reader_thread, "reader": stream_reader}
                self.running_mcps.append(key)
                self.log(f"[OK] MCP '{config['name']}' запущен с PID: {process.pid}")

            except Exception as e:
                self.log(f"[ОШИБКА] Не удалось запустить '{config['name']}': {e}")
        
        self.launch_main_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    # --- ОБНОВЛЕННЫЙ МЕТОД ОСТАНОВКИ ---
    def stop_processes(self):
        """Запускает неблокирующую остановку процессов."""
        if not self.processes:
            self.log("[INFO] Нет активных MCP для остановки."); return

        # Блокируем кнопки, чтобы избежать повторных нажатий
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.launch_main_button.setEnabled(False)

        # Создаем воркер и поток
        self.stopper_thread = QtCore.QThread()
        self.stopper_worker = ProcessStopper(self.processes.copy()) # Передаем копию
        self.stopper_worker.moveToThread(self.stopper_thread)

        # Связываем сигналы
        self.stopper_thread.started.connect(self.stopper_worker.run)
        self.stopper_worker.finished.connect(self.on_stopping_finished)
        self.stopper_worker.log_message.connect(self.log)
        
        # Очистка
        self.stopper_worker.finished.connect(self.stopper_thread.quit)
        self.stopper_worker.finished.connect(self.stopper_worker.deleteLater)
        self.stopper_thread.finished.connect(self.stopper_thread.deleteLater)
        
        # Запускаем!
        self.stopper_thread.start()

    # --- НОВЫЙ СЛОТ для завершения остановки ---
    @QtCore.pyqtSlot()
    def on_stopping_finished(self):
        """Выполняется, когда фоновый воркер закончил останавливать процессы."""
        self.processes.clear()
        self.running_mcps.clear()
        
        # Возвращаем кнопки в исходное состояние
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False) # Кнопка стоп неактивна, т.к. нечего останавливать
        self.launch_main_button.setEnabled(False)

        # ПРОВЕРЯЕМ ФЛАГ: если мы в процессе закрытия, то завершаем его
        if self.is_shutting_down:
            self.log("[INFO] Процессы остановлены, приложение закрывается.")
            self.close() # Вызываем закрытие еще раз, теперь оно пройдет

    def launch_main_app(self):
        self.log("--- [ЗАПУСК] Обновление .env и запуск main.py ---")
        active_mcps_string = ",".join(sorted(self.running_mcps))
        self.log(f"[*] Записываем в .env: ACTIVE_MCPS='{active_mcps_string}'")
        dotenv_path = find_dotenv()
        if not os.path.exists(dotenv_path):
            with open(".env", "w") as f: f.write("")
            dotenv_path = find_dotenv()
        set_key(dotenv_path, "ACTIVE_MCPS", active_mcps_string)
        self.log("[OK] Файл .env обновлен.")
        try:
            subprocess.Popen([sys.executable, "main.py"])
            self.log("[OK] Главный GUI запущен в отдельном процессе.")
        except Exception as e:
            self.log(f"[ОШИБКА] Не удалось запустить main.py: {e}")
        
    
    def launch_visualizer(self):
        """Запускает скрипт визуализатора в отдельном процессе."""
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
        # Если мы УЖЕ в процессе закрытия, просто даем окну закрыться
        if self.is_shutting_down:
            event.accept()
            return
            
        # Если есть запущенные процессы, спрашиваем пользователя
        if self.processes:
            reply = QtWidgets.QMessageBox.question(self, 'Подтверждение выхода',
                "Вы уверены, что хотите выйти? Все запущенные MCP будут остановлены.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)

            if reply == QtWidgets.QMessageBox.Yes:
                self.log("[INFO] Инициирован выход из приложения. Остановка MCP...")
                self.is_shutting_down = True  # Устанавливаем флаг
                self.stop_processes()         # Запускаем асинхронную остановку
                event.ignore()                # ЗАПРЕЩАЕМ окну закрываться немедленно
            else:
                event.ignore() # Пользователь передумал, запрещаем закрытие
        else:
            # Если нет запущенных процессов, просто закрываемся
            event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec_())