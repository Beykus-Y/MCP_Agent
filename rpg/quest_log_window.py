# rpg/quest_log_window.py
from PyQt5 import QtWidgets, QtCore
from .world.world_state import PointOfInterest # <--- Добавь этот импорт

class QuestLogWindow(QtWidgets.QDialog):
    def __init__(self, character, world, parent=None): # <--- Добавь 'world' в параметры
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.character = character
        self.world = world # <--- Сохрани мир
        self.setWindowTitle("Журнал") # <--- Переименовываем
        self.setMinimumSize(500, 500) # <--- Немного увеличим
        self.setup_ui()
        self.populate_quests()
        self.populate_locations() # <--- Вызываем новый метод

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        
        self.tabs = QtWidgets.QTabWidget()
        self.active_quests_list = QtWidgets.QListWidget()
        self.completed_quests_list = QtWidgets.QListWidget()
        # --- НОВАЯ ВКЛАДКА ---
        self.locations_list = QtWidgets.QListWidget() 
        
        # Создаем виджет для вкладок с квестами
        quests_widget = QtWidgets.QWidget()
        quests_layout = QtWidgets.QVBoxLayout(quests_widget)
        quest_tabs = QtWidgets.QTabWidget()
        quest_tabs.addTab(self.active_quests_list, "Активные")
        quest_tabs.addTab(self.completed_quests_list, "Завершенные")
        quests_layout.addWidget(quest_tabs)
        quests_layout.setContentsMargins(0,0,0,0)

        # Добавляем вкладки в главный QTabWidget
        self.tabs.addTab(quests_widget, "Задания")
        self.tabs.addTab(self.locations_list, "Известные места") # <--- Добавляем вкладку
        
        self.details_view = QtWidgets.QTextEdit() # Переименовываем для универсальности
        self.details_view.setReadOnly(True)
        
        main_layout.addWidget(self.tabs)
        main_layout.addWidget(QtWidgets.QLabel("Описание и детали:"))
        main_layout.addWidget(self.details_view)
        
        # Подключаем сигналы для всех списков
        self.active_quests_list.currentItemChanged.connect(self.display_details)
        self.completed_quests_list.currentItemChanged.connect(self.display_details)
        self.locations_list.currentItemChanged.connect(self.display_details) # <--- Подключаем сигнал
        # Сигнал переключения главных вкладок, чтобы очищать описание
        self.tabs.currentChanged.connect(lambda: self.details_view.clear())

    # --- НОВЫЙ МЕТОД ---
    def populate_locations(self):
        """Заполняет список посещенных локаций."""
        self.locations_list.clear()
        
        # Итерируемся по ID посещенных POI
        for poi_id in self.character.visited_pois:
            # Находим сам объект POI в мире по его ID
            poi = next((p for p in self.world.points_of_interest if p.id == poi_id), None)
            if poi:
                item = QtWidgets.QListWidgetItem(f"{poi.name} ({poi.type.capitalize()})")
                item.setData(QtCore.Qt.UserRole, poi) # Храним весь объект POI
                self.locations_list.addItem(item)
    
    def populate_quests(self):
        """Заполняет списки квестов из данных персонажа."""
        self.active_quests_list.clear()
        self.completed_quests_list.clear()
        for quest in self.character.quests:
            item = QtWidgets.QListWidgetItem(quest.name)
            item.setData(QtCore.Qt.UserRole, quest) 
            if quest.status == "active":
                self.active_quests_list.addItem(item)
            elif quest.status == "completed":
                self.completed_quests_list.addItem(item)
                
    # --- УНИВЕРСАЛЬНЫЙ МЕТОД ОТОБРАЖЕНИЯ ---
    def display_details(self, current, previous):
        """Показывает подробности выбранного элемента (квеста или локации)."""
        if not current:
            self.details_view.clear()
            return
            
        data_item = current.data(QtCore.Qt.UserRole)
        
        # Проверяем тип объекта, который мы получили
        if isinstance(data_item, PointOfInterest):
            self.display_location_details(data_item)
        else: # Иначе считаем, что это квест (можно добавить явную проверку)
            self.display_quest_details(data_item)

    def display_quest_details(self, quest):
        """Форматирует и выводит информацию о квесте."""
        description_html = f"<h3>{quest.name}</h3>"
        description_html += f"<p><i>{quest.description}</i></p><hr>"
        description_html += "<h4>Цели:</h4><ul>"
        
        for objective in quest.objectives:
            if objective.get('completed', False):
                description_html += f"<li><s>{objective['text']}</s></li>"
            else:
                description_html += f"<li>{objective['text']}</li>"
        
        description_html += "</ul>"
        self.details_view.setHtml(description_html)

    # --- НОВЫЙ МЕТОД ДЛЯ ЛОКАЦИЙ ---
    def display_location_details(self, poi: PointOfInterest):
        """Форматирует и выводит информацию о локации."""
        description_html = f"<h3>{poi.name}</h3>"
        description_html += f"<b>Тип:</b> {poi.type.capitalize()}<br>"
        description_html += f"<b>Координаты:</b> {poi.position}<br><hr>"
        
        # Добавляем описание, если оно есть
        if poi.description:
            description_html += f"<p><i>{poi.description}</i></p>"
        else:
            description_html += "<p><i>Подробного описания этого места пока нет.</i></p>"
        
        # Добавляем список известных личностей (NPC)
        if poi.npcs:
            description_html += "<hr><h4>Известные личности:</h4><ul>"
            for npc in poi.npcs:
                description_html += f"<li><b>{npc.name}</b> ({npc.profession})</li>"
            description_html += "</ul>"
        
        self.details_view.setHtml(description_html)