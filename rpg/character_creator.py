# rpg/character_creator.py
import sys
from PyQt5 import QtWidgets, QtCore, QtGui

from .ai_helper import AIHelper
from .game_manager import GameManager
from .models import Character, Stats, Item
from .rules import RulesEngine
from .constants import STARTING_TRAIT_POINTS, MAX_STAT_POINTS, DEFAULT_MAX_HP, DEFAULT_STARTING_HP


class AIWorker(QtCore.QObject):
    """Выполняет запрос к ИИ в отдельном потоке."""
    finished = QtCore.pyqtSignal(dict)
    error = QtCore.pyqtSignal(str)

    def __init__(self, ai_helper: AIHelper, user_wish: str):
        super().__init__()
        self.ai_helper = ai_helper
        self.user_wish = user_wish

    @QtCore.pyqtSlot()
    def run(self):
        try:
            result = self.ai_helper.generate_character_details(self.user_wish)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class CharacterCreatorWindow(QtWidgets.QDialog):
    """Модальное окно для создания нового персонажа с помощью ИИ."""
    character_created = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ai_helper = AIHelper()
        self.game_manager = GameManager()
        self.rules_engine = RulesEngine()

        self._generated_data = {}
        self.trait_points = STARTING_TRAIT_POINTS

        self.setWindowTitle("Создание нового персонажа")
        self.setMinimumSize(600, 750)
        self.setup_ui()
        self.update_total_stats()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_widget = QtWidgets.QWidget()
        form_layout = QtWidgets.QFormLayout(main_widget)
        form_layout.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("Например, Арагорн")
        self.wish_input = QtWidgets.QTextEdit()
        self.wish_input.setPlaceholderText("Опишите персонажа, которого хотите создать...")
        self.wish_input.setMinimumHeight(80)
        self.generate_button = QtWidgets.QPushButton("Сгенерировать с помощью ИИ")
        self.generate_button.clicked.connect(self.run_ai_generation)
        self.backstory_output = QtWidgets.QTextEdit()
        self.backstory_output.setReadOnly(True)

        stats_group = self.create_stats_group()
        traits_group = self.create_traits_group()
        equipment_group = self.create_equipment_group()

        form_layout.addRow("Имя персонажа:", self.name_input)
        form_layout.addRow("Описание для ИИ:", self.wish_input)
        form_layout.addRow(self.generate_button)
        form_layout.addRow("Предыстория:", self.backstory_output)
        form_layout.addRow(stats_group)
        form_layout.addRow(traits_group)
        form_layout.addRow(equipment_group)

        scroll_area.setWidget(main_widget)
        main_layout.addWidget(scroll_area)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        self.save_button = button_box.button(QtWidgets.QDialogButtonBox.Save)
        self.save_button.setText("Сохранить")
        self.save_button.setEnabled(False)
        button_box.accepted.connect(self.save_character)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
        self.populate_traits_list()
        self.update_trait_points_label()

    def create_stats_group(self):
        stats_group = QtWidgets.QGroupBox("Характеристики")
        stats_layout = QtWidgets.QFormLayout()
        self.str_spinbox, self.dex_spinbox, self.int_spinbox, self.cha_spinbox = (QtWidgets.QSpinBox() for _ in range(4))
        self.stat_spinboxes = [self.str_spinbox, self.dex_spinbox, self.int_spinbox, self.cha_spinbox]
        self.total_stats_label = QtWidgets.QLabel()
        self.total_stats_label.setStyleSheet("font-weight: bold;")
        for spinbox in self.stat_spinboxes:
            spinbox.setRange(5, 18); spinbox.setValue(10)
            spinbox.valueChanged.connect(self.update_total_stats)
        stats_layout.addRow("Сила:", self.str_spinbox); stats_layout.addRow("Ловкость:", self.dex_spinbox)
        stats_layout.addRow("Интеллект:", self.int_spinbox); stats_layout.addRow("Харизма:", self.cha_spinbox)
        stats_layout.addRow("Всего очков:", self.total_stats_label); stats_group.setLayout(stats_layout)
        return stats_group
        
    def create_traits_group(self):
        traits_group = QtWidgets.QGroupBox("Черты характера")
        traits_main_layout = QtWidgets.QHBoxLayout()
        available_layout = QtWidgets.QVBoxLayout(); available_layout.addWidget(QtWidgets.QLabel("Доступные:"))
        self.available_traits_list = QtWidgets.QListWidget(); available_layout.addWidget(self.available_traits_list)
        buttons_layout = QtWidgets.QVBoxLayout(); buttons_layout.addStretch()
        self.add_trait_button = QtWidgets.QPushButton("->"); self.add_trait_button.setFixedWidth(40)
        self.add_trait_button.clicked.connect(self.add_trait)
        self.remove_trait_button = QtWidgets.QPushButton("<-"); self.remove_trait_button.setFixedWidth(40)
        self.remove_trait_button.clicked.connect(self.remove_trait)
        buttons_layout.addWidget(self.add_trait_button); buttons_layout.addWidget(self.remove_trait_button)
        buttons_layout.addStretch()
        chosen_layout = QtWidgets.QVBoxLayout(); self.trait_points_label = QtWidgets.QLabel()
        chosen_layout.addWidget(self.trait_points_label); self.chosen_traits_list = QtWidgets.QListWidget()
        chosen_layout.addWidget(self.chosen_traits_list); traits_main_layout.addLayout(available_layout, 2)
        traits_main_layout.addLayout(buttons_layout); traits_main_layout.addLayout(chosen_layout, 2)
        traits_group.setLayout(traits_main_layout)
        return traits_group

    def create_equipment_group(self):
        equipment_group = QtWidgets.QGroupBox("Стартовое снаряжение (выбрано ИИ)")
        equipment_layout = QtWidgets.QVBoxLayout()
        self.equipment_list = QtWidgets.QListWidget()
        equipment_layout.addWidget(self.equipment_list)
        equipment_group.setLayout(equipment_layout)
        return equipment_group

    def populate_traits_list(self):
        self.available_traits_list.clear()
        for trait_data in self.rules_engine.traits_data:
            cost = trait_data.get('cost', 0)
            item = QtWidgets.QListWidgetItem(f"{trait_data['name']} (Стоимость: {-cost})")
            item.setToolTip(trait_data['description']); item.setData(QtCore.Qt.UserRole, trait_data)
            self.available_traits_list.addItem(item)
    
    def update_trait_points_label(self):
        self.trait_points_label.setText(f"Очки черт: {self.trait_points}")
        self.trait_points_label.setStyleSheet("color: green; font-weight: bold;" if self.trait_points >= 0 else "color: red; font-weight: bold;")

    def add_trait(self):
        selected_item = self.available_traits_list.currentItem()
        if not selected_item: return
        trait_data = selected_item.data(QtCore.Qt.UserRole); cost = trait_data.get('cost', 0)
        if self.trait_points + cost < 0:
            QtWidgets.QMessageBox.warning(self, "Недостаточно очков", "У вас не хватает очков для выбора этой черты."); return
        self.trait_points += cost; self.update_trait_points_label()
        self.chosen_traits_list.addItem(self.available_traits_list.takeItem(self.available_traits_list.row(selected_item)))

    def remove_trait(self):
        selected_item = self.chosen_traits_list.currentItem()
        if not selected_item: return
        trait_data = selected_item.data(QtCore.Qt.UserRole); cost = trait_data.get('cost', 0)
        self.trait_points -= cost; self.update_trait_points_label()
        self.available_traits_list.addItem(self.chosen_traits_list.takeItem(self.chosen_traits_list.row(selected_item)))
        self.available_traits_list.sortItems() # Сортируем для порядка

    def save_character(self):
        char_name = self.name_input.text().strip()
        if not char_name:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Пожалуйста, введите имя персонажа."); return
        if self.trait_points < 0:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "У вас отрицательное количество очков черт."); return
        total_stats = sum(s.value() for s in self.stat_spinboxes)
        if total_stats > MAX_STAT_POINTS:
            QtWidgets.QMessageBox.warning(self, "Превышен лимит", f"Сумма характеристик ({total_stats}) не должна превышать {MAX_STAT_POINTS}."); return

        chosen_trait_ids = [self.chosen_traits_list.item(i).data(QtCore.Qt.UserRole)['id'] for i in range(self.chosen_traits_list.count())]
        char_stats = Stats(strength=self.str_spinbox.value(), dexterity=self.dex_spinbox.value(), intelligence=self.int_spinbox.value(), charisma=self.cha_spinbox.value())
        
        char_equipment = {}
        # Используем данные, которые ИИ вернул в последний раз
        for item_id in self._generated_data.get("equipment_ids", []):
            item_instance = self.rules_engine.create_item_instance(item_id)
            if item_instance:
                char_equipment[item_instance.slot] = item_instance

        new_character = Character(
            name=char_name, backstory=self.backstory_output.toPlainText() or "История не написана.",
            traits=chosen_trait_ids, stats=char_stats, equipment=char_equipment, inventory=[],
            # --- НОВОЕ: Явная инициализация HP ---
            max_hp=DEFAULT_MAX_HP,
            current_hp=DEFAULT_STARTING_HP,
            discovered_cells=set(), 
            visited_pois=[]
            # --- КОНЕЦ НОВОГО ---
        )
        
        save_id = self.game_manager.create_new_save(new_character)
        QtWidgets.QMessageBox.information(self, "Успех", f"Персонаж '{char_name}' сохранен в '{save_id}'.")
        self.character_created.emit()
        self.accept()
        
    def update_total_stats(self):
        total = sum(s.value() for s in self.stat_spinboxes)
        self.total_stats_label.setText(f"{total} / {MAX_STAT_POINTS}")
        self.total_stats_label.setStyleSheet("font-weight: bold; color: green;" if total <= MAX_STAT_POINTS else "font-weight: bold; color: red;")
        
    def run_ai_generation(self):
        user_wish = self.wish_input.toPlainText().strip()
        if not user_wish: QtWidgets.QMessageBox.warning(self, "Ошибка", "Пожалуйста, опишите персонажа для ИИ."); return
        self.generate_button.setText("Генерация..."); self.generate_button.setEnabled(False)
        self.thread = QtCore.QThread(); self.worker = AIWorker(self.ai_helper, user_wish)
        self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_ai_finished); self.worker.error.connect(self.on_ai_error)
        self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater); self.thread.start()
        
    def on_ai_finished(self, data: dict):
        self.generate_button.setText("Сгенерировать с помощью ИИ"); self.generate_button.setEnabled(True)
        if "error" in data: self.on_ai_error(data["error"]); return
        self.populate_ui_with_data(data); self._generated_data = data; self.save_button.setEnabled(True)
        
    def on_ai_error(self, err_msg: str):
        self.generate_button.setText("Сгенерировать с помощью ИИ"); self.generate_button.setEnabled(True)
        QtWidgets.QMessageBox.critical(self, "Ошибка ИИ", f"Не удалось сгенерировать данные:\n{err_msg}")
        
    def populate_ui_with_data(self, data: dict):
        # Сброс перед заполнением
        self.reset_traits()

        # Заполнение основных полей
        self.backstory_output.setText(data.get("backstory", ""))
        stats = data.get("stats", {}); self.str_spinbox.setValue(stats.get("strength", 10))
        self.dex_spinbox.setValue(stats.get("dexterity", 10)); self.int_spinbox.setValue(stats.get("intelligence", 10))
        self.cha_spinbox.setValue(stats.get("charisma", 10)); self.update_total_stats()

        # --- НОВАЯ ЛОГИКА: Автоматический выбор черт ---
        trait_ids_from_ai = data.get("trait_ids", [])
        for trait_id in trait_ids_from_ai:
            for i in range(self.available_traits_list.count()):
                item = self.available_traits_list.item(i)
                if item.data(QtCore.Qt.UserRole)['id'] == trait_id:
                    self.add_trait_by_item(item)
                    break
        
        # --- НОВАЯ ЛОГИКА: Отображение выбранного снаряжения ---
        self.equipment_list.clear()
        equipment_ids_from_ai = data.get("equipment_ids", [])
        for item_id in equipment_ids_from_ai:
            item_data = self.rules_engine.get_item(item_id)
            if item_data:
                list_item = QtWidgets.QListWidgetItem(f"{item_data['name']}")
                list_item.setToolTip(item_data['description'])
                self.equipment_list.addItem(list_item)
                
    def reset_traits(self):
        """Перемещает все черты из 'выбранных' в 'доступные'."""
        while self.chosen_traits_list.count() > 0:
            self.remove_trait_by_item(self.chosen_traits_list.item(0))
        self.trait_points = STARTING_TRAIT_POINTS
        self.update_trait_points_label()
            
    def add_trait_by_item(self, item: QtWidgets.QListWidgetItem):
        """Служебный метод для программного добавления черты."""
        trait_data = item.data(QtCore.Qt.UserRole); cost = trait_data.get('cost', 0)
        self.trait_points += cost; self.update_trait_points_label()
        self.chosen_traits_list.addItem(self.available_traits_list.takeItem(self.available_traits_list.row(item)))
    
    def remove_trait_by_item(self, item: QtWidgets.QListWidgetItem):
        """Служебный метод для программного удаления черты."""
        trait_data = item.data(QtCore.Qt.UserRole); cost = trait_data.get('cost', 0)
        self.trait_points -= cost; self.update_trait_points_label()
        self.available_traits_list.addItem(self.chosen_traits_list.takeItem(self.chosen_traits_list.row(item)))
        self.available_traits_list.sortItems()

if __name__ == '__main__':
    from dotenv import load_dotenv
    import os
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))
    app = QtWidgets.QApplication(sys.argv)
    window = CharacterCreatorWindow()
    window.show()
    sys.exit(app.exec_())