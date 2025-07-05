# rpg/world/creation_dialog.py
import sys
import json
import os
from PyQt5 import QtWidgets, QtCore

# Определяем путь к файлу данных относительно текущего файла
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CIVS_FILE = os.path.join(BASE_DIR, '..', 'game_data', 'civilizations.json')

class WorldCreationDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Параметры нового мира")
        self.setMinimumWidth(500)
        
        try:
            with open(CIVS_FILE, 'r', encoding='utf-8') as f:
                self.all_civs = json.load(f)
        except FileNotFoundError:
            # Обработка ошибки, если файл не найден
            self.all_civs = []
            msg_box = QtWidgets.QMessageBox()
            msg_box.setIcon(QtWidgets.QMessageBox.Critical)
            msg_box.setText(f"Ошибка: Файл цивилизаций не найден!\nПуть: {CIVS_FILE}")
            msg_box.exec_()

        self.setup_ui()
        self.filter_civilizations()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        form_layout = QtWidgets.QFormLayout()

        self.world_name_input = QtWidgets.QLineEdit("Новый мир")
        self.year_input = QtWidgets.QSpinBox()
        self.year_input.setRange(100, 9999); self.year_input.setValue(1000)
        
        self.tech_level_combo = QtWidgets.QComboBox()
        self.tech_level_combo.addItems(["stone_age", "fantasy", "sci_fi"])
        self.tech_level_combo.setCurrentText("fantasy")
        
        self.magic_level_combo = QtWidgets.QComboBox()
        self.magic_level_combo.addItems(["none", "low", "medium", "high"])
        self.magic_level_combo.setCurrentText("medium")

        civs_group = QtWidgets.QGroupBox("Выберите цивилизации для мира (3-5)")
        civs_layout = QtWidgets.QVBoxLayout()
        self.civs_list_widget = QtWidgets.QListWidget()
        self.civs_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        civs_layout.addWidget(self.civs_list_widget)
        civs_group.setLayout(civs_layout)
        
        form_layout.addRow("Название мира:", self.world_name_input)
        form_layout.addRow("Текущий год:", self.year_input)
        form_layout.addRow("Уровень технологий:", self.tech_level_combo)
        form_layout.addRow("Уровень магии:", self.magic_level_combo)

        main_layout.addLayout(form_layout)
        main_layout.addWidget(civs_group)
        
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
        self.tech_level_combo.currentTextChanged.connect(self.filter_civilizations)
        self.magic_level_combo.currentTextChanged.connect(self.filter_civilizations)

    def filter_civilizations(self):
        current_tech = self.tech_level_combo.currentText()
        current_magic = self.magic_level_combo.currentText()
        self.civs_list_widget.clear()
        
        for civ in self.all_civs:
            if current_tech in civ["tech_level"] and current_magic in civ["magic_level"]:
                item = QtWidgets.QListWidgetItem(civ["name"])
                item.setToolTip(civ["description"])
                item.setData(QtCore.Qt.UserRole, civ)
                self.civs_list_widget.addItem(item)

    def get_parameters(self) -> dict:
        selected_civs = [item.data(QtCore.Qt.UserRole) for item in self.civs_list_widget.selectedItems()]
        if not (3 <= len(selected_civs) <= 5):
            QtWidgets.QMessageBox.warning(self, "Ошибка выбора", "Пожалуйста, выберите от 3 до 5 цивилизаций.")
            return None
        return {
            "world_name": self.world_name_input.text(),
            "year": self.year_input.value(),
            "tech_level": self.tech_level_combo.currentText(),
            "magic_level": self.magic_level_combo.currentText(),
            "civilizations": selected_civs
        }

    def accept(self):
        if self.get_parameters() is not None:
            super().accept()

# Блок для автономного теста
if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    dialog = WorldCreationDialog()
    if dialog.exec_() == QtWidgets.QDialog.Accepted:
        params = dialog.get_parameters()
        print("Мир будет сгенерирован с параметрами:")
        import pprint
        pprint.pprint(params)
    else:
        print("Генерация отменена.")
    sys.exit(0)