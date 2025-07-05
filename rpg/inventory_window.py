# rpg/inventory_window.py
from PyQt5 import QtWidgets, QtCore, QtGui
from typing import Dict, List, Optional

from .models import Character, Item
from .rules import RulesEngine
from .network_protocol import MessageType

class InventoryWindow(QtWidgets.QDialog):
    # Сигнал для оповещения основного окна, что состояние персонажа изменилось
    # (например, изменились статы после экипировки/снятия)
    character_updated = QtCore.pyqtSignal()
    # Сигнал для оповещения основного окна, что нужно сохранить игру
    save_game_requested = QtCore.pyqtSignal()

    def __init__(self, character: Character, rules_engine: RulesEngine, is_online: bool, network_worker=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.character = character
        self.rules_engine = rules_engine
        self.setWindowTitle("Инвентарь и Экипировка")
        self.setMinimumSize(700, 600)
        self.setup_ui()
        self.populate_ui()
        self.network_worker = network_worker
        self.is_online = is_online

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # Разделение на экипировку и инвентарь
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_layout.addWidget(splitter)

        # --- Левая панель: Экипировка ---
        equipment_widget = QtWidgets.QWidget()
        equipment_layout = QtWidgets.QVBoxLayout(equipment_widget)
        equipment_group = QtWidgets.QGroupBox("Экипировка")
        self.equipment_form_layout = QtWidgets.QFormLayout(equipment_group)
        
        self.equipment_labels: Dict[str, QtWidgets.QLabel] = {}
        self.unequip_buttons: Dict[str, QtWidgets.QPushButton] = {}

        # Определяем порядок слотов для отображения
        self.slots_order = ["head", "chest", "legs", "feet", "hands", "cloak", "amulet", "ring", "weapon", "shield"]

        for slot in self.slots_order:
            item_label = QtWidgets.QLabel("Нет")
            self.equipment_labels[slot] = item_label

            unequip_btn = QtWidgets.QPushButton("Снять")
            unequip_btn.setFixedSize(50, 24)
            unequip_btn.clicked.connect(lambda _, s=slot: self.unequip_item(s))
            unequip_btn.setEnabled(False) # Изначально отключена
            self.unequip_buttons[slot] = unequip_btn

            hbox = QtWidgets.QHBoxLayout()
            hbox.addWidget(item_label)
            hbox.addStretch()
            hbox.addWidget(unequip_btn)
            
            self.equipment_form_layout.addRow(f"{slot.capitalize()}:", hbox)
        
        equipment_layout.addWidget(equipment_group)
        equipment_layout.addStretch()
        splitter.addWidget(equipment_widget)

        # --- Правая панель: Инвентарь и Детали Предмета ---
        right_panel_widget = QtWidgets.QWidget()
        right_panel_layout = QtWidgets.QVBoxLayout(right_panel_widget)

        inventory_group = QtWidgets.QGroupBox("Инвентарь")
        inventory_layout = QtWidgets.QVBoxLayout(inventory_group)
        self.inventory_list = QtWidgets.QListWidget()
        self.inventory_list.itemSelectionChanged.connect(self.display_selected_item_details)
        inventory_layout.addWidget(self.inventory_list)
        inventory_group.setLayout(inventory_layout)
        right_panel_layout.addWidget(inventory_group, 2) # Занимает 2/3 пространства

        item_details_group = QtWidgets.QGroupBox("Детали предмета")
        item_details_layout = QtWidgets.QVBoxLayout(item_details_group)
        self.item_details_name = QtWidgets.QLabel("Выберите предмет")
        self.item_details_description = QtWidgets.QTextEdit()
        self.item_details_description.setReadOnly(True)
        self.item_details_description.setPlaceholderText("Описание предмета появится здесь...")
        item_details_layout.addWidget(self.item_details_name)
        item_details_layout.addWidget(self.item_details_description)
        item_details_group.setLayout(item_details_layout)
        right_panel_layout.addWidget(item_details_group, 1) # Занимает 1/3 пространства

        # Кнопки действий
        actions_layout = QtWidgets.QHBoxLayout()
        self.equip_button = QtWidgets.QPushButton("Экипировать")
        self.equip_button.clicked.connect(self.equip_selected_item)
        self.use_button = QtWidgets.QPushButton("Использовать")
        self.use_button.clicked.connect(self.use_selected_item)
        self.discard_button = QtWidgets.QPushButton("Выбросить")
        self.discard_button.clicked.connect(self.discard_selected_item)
        
        self.equip_button.setEnabled(False)
        self.use_button.setEnabled(False)
        self.discard_button.setEnabled(False)

        actions_layout.addWidget(self.equip_button)
        actions_layout.addWidget(self.use_button)
        actions_layout.addWidget(self.discard_button)
        right_panel_layout.addLayout(actions_layout)

        splitter.addWidget(right_panel_widget)
        splitter.setSizes([200, 500]) # Начальные размеры панелей

        # Кнопка закрытия окна
        close_button = QtWidgets.QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        main_layout.addWidget(close_button, 0, QtCore.Qt.AlignRight)

    def refresh_from_server(self, new_character_data: Character):
        """Обновляет окно данными, полученными от сервера."""
        self.character = new_character_data
        self.populate_ui()

    def populate_ui(self):
        """Заполняет UI текущими данными персонажа."""
        # Очищаем детали предмета
        self.item_details_name.setText("Выберите предмет")
        self.item_details_description.clear()
        self.equip_button.setEnabled(False)
        self.use_button.setEnabled(False)
        self.discard_button.setEnabled(False)

        # Заполняем экипировку
        for slot in self.slots_order:
            item = self.character.equipment.get(slot)
            if item:
                self.equipment_labels[slot].setText(item.name)
                self.unequip_buttons[slot].setEnabled(True)
                self.unequip_buttons[slot].setProperty("item_id", item.id) # Для удобства
            else:
                self.equipment_labels[slot].setText("Нет")
                self.unequip_buttons[slot].setEnabled(False)
                self.unequip_buttons[slot].setProperty("item_id", None)

        # Заполняем инвентарь
        self.inventory_list.clear()
        for item in self.character.inventory:
            list_item = QtWidgets.QListWidgetItem(item.name)
            list_item.setData(QtCore.Qt.UserRole, item) # Сохраняем сам объект Item
            self.inventory_list.addItem(list_item)
        
        # Если есть выбранный предмет, обновляем его детали
        self.display_selected_item_details()

    def display_selected_item_details(self):
        """Отображает детали выбранного предмета из инвентаря."""
        selected_item_widget = self.inventory_list.currentItem()
        if selected_item_widget:
            item: Item = selected_item_widget.data(QtCore.Qt.UserRole)
            self.item_details_name.setText(item.name)
            self.item_details_description.setText(item.description)

            # Управление кнопками действий
            self.equip_button.setEnabled(item.slot in self.slots_order)
            self.use_button.setEnabled(item.slot == "consumable")
            self.discard_button.setEnabled(True) # Всегда можно выбросить
        else:
            self.item_details_name.setText("Выберите предмет")
            self.item_details_description.clear()
            self.equip_button.setEnabled(False)
            self.use_button.setEnabled(False)
            self.discard_button.setEnabled(False)

    def equip_selected_item(self):
        selected_item_widget = self.inventory_list.currentItem()
        if not selected_item_widget: return
        item_to_equip: Item = selected_item_widget.data(QtCore.Qt.UserRole)
        
        # --- НОВАЯ ЛОГИКА ДЛЯ МУЛЬТИПЛЕЕРА ---
        if self.is_online and self.network_worker:
            action = {'type': MessageType.EQUIP_ITEM, 'data': {'item_id': item_to_equip.id}}
            self.network_worker.send_action(action)
            # В онлайне мы не меняем UI сразу, а ждем ответа от сервера
            # Можем временно заблокировать кнопки, чтобы избежать спама
            self.equip_button.setEnabled(False)
        else:
            # --- СТАРАЯ ЛОГИКА ДЛЯ ОФФЛАЙНА ---
            target_slot = item_to_equip.slot
            if target_slot in self.character.equipment:
                current_item_in_slot = self.character.equipment[target_slot]
                del self.character.equipment[target_slot]
                self.character.inventory.append(current_item_in_slot)
            self.character.equipment[target_slot] = item_to_equip
            self.character.inventory.remove(item_to_equip)
            self.item_changed() # Обновляем UI и сохраняем

    def unequip_item(self, slot: str):
        if slot not in self.character.equipment: return
        
        # --- НОВАЯ ЛОГИКА ДЛЯ МУЛЬТИПЛЕЕРА ---
        if self.is_online and self.network_worker:
            action = {'type': MessageType.UNEQUIP_ITEM, 'data': {'slot': slot}}
            self.network_worker.send_action(action)
            self.unequip_buttons[slot].setEnabled(False) # Блокируем кнопку
        else:
            # --- СТАРАЯ ЛОГИКА ДЛЯ ОФФЛАЙНА ---
            item_to_unequip: Item = self.character.equipment[slot]
            del self.character.equipment[slot]
            self.character.inventory.append(item_to_unequip)
            self.item_changed()

    def use_selected_item(self):
        selected_item_widget = self.inventory_list.currentItem()
        if not selected_item_widget: return
        item_to_use: Item = selected_item_widget.data(QtCore.Qt.UserRole)
        if item_to_use.slot != "consumable": return

        # --- НОВАЯ ЛОГИКА ДЛЯ МУЛЬТИПЛЕЕРА ---
        if self.is_online and self.network_worker:
            action = {'type': MessageType.USE_ITEM, 'data': {'item_id': item_to_use.id}}
            self.network_worker.send_action(action)
            self.use_button.setEnabled(False)
        else:
            # --- СТАРАЯ ЛОГИКА ДЛЯ ОФФЛАЙНА ---
            log_callback = lambda msg: self.parent()._log_message(msg) if hasattr(self.parent(), '_log_message') else print(msg)
            consumed = self.rules_engine.apply_item_effects(self.character, item_to_use, log_callback)
            if consumed:
                self.character.inventory.remove(item_to_use)
                self.item_changed()

    def discard_selected_item(self):
        """Выбрасывает выбранный предмет."""
        selected_item_widget = self.inventory_list.currentItem()
        if not selected_item_widget:
            # Возможно, выбран предмет из экипировки
            for slot, button in self.unequip_buttons.items():
                if button.isEnabled() and button == self.sender(): # Если кнопка "Выбросить" была нажата для экипированного предмета (не реализовано сейчас)
                     # Здесь нужно было бы снять предмет перед выбросом, или сделать отдельную кнопку выброса для экипированных.
                     # Пока что сосредоточимся на инвентаре.
                    pass
            return

        item_to_discard: Item = selected_item_widget.data(QtCore.Qt.UserRole)

        reply = QtWidgets.QMessageBox.question(self, "Подтверждение", 
                                                f"Вы уверены, что хотите выбросить '{item_to_discard.name}'? Он будет потерян навсегда.",
                                                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, 
                                                QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            self.character.inventory.remove(item_to_discard)
            QtWidgets.QMessageBox.information(self, "Предмет выброшен", f"Предмет '{item_to_discard.name}' был выброшен.")
            self.item_changed()

    def item_changed(self):
        """Обновляет UI и сигнализирует об изменении состояния персонажа."""
        self.populate_ui()
        self.character_updated.emit()
        self.save_game_requested.emit() # Просим сохранить игру после изменения инвентаря/экипировки