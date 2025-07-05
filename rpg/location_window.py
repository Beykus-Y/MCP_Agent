# rpg/location_window.py
from PyQt5 import QtWidgets, QtCore

class LocationWindow(QtWidgets.QDialog):
    # --- НОВЫЙ СИГНАЛ: теперь передает NPC ---
    quest_requested_from_npc = QtCore.pyqtSignal(object) # object, т.к. передаем объект NPC

    def __init__(self, location, character, parent=None):
        super().__init__(parent)
        self.location = location; self.character = character
        self.setWindowTitle(f"Локация: {self.location.name}")
        self.setMinimumSize(500, 400); self.setup_ui()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        description_label = QtWidgets.QLabel(self.location.description or "Вы оглядываетесь по сторонам...")
        description_label.setWordWrap(True)
        
        line = QtWidgets.QFrame(); line.setFrameShape(QtWidgets.QFrame.HLine); line.setFrameShadow(QtWidgets.QFrame.Sunken)
        
        # --- ИЗМЕНЕНИЕ: Убираем вкладки, делаем единый список ---
        actions_group = QtWidgets.QGroupBox("Что вы хотите сделать?")
        actions_layout = QtWidgets.QVBoxLayout(actions_group)

        # Действие "Искать слухи"
        self.look_for_trouble_button = QtWidgets.QPushButton("Расспросить о работе / поискать приключений")
        self.look_for_trouble_button.clicked.connect(self.request_generic_quest)
        actions_layout.addWidget(self.look_for_trouble_button)
        
        actions_layout.addWidget(QtWidgets.QLabel("--- или поговорить с кем-то конкретным ---"))

        # Список NPC
        if not self.location.npcs:
            actions_layout.addWidget(QtWidgets.QLabel("Здесь никого нет."))
        else:
            for npc in self.location.npcs:
                npc_layout = QtWidgets.QHBoxLayout()
                npc_label = QtWidgets.QLabel(f"<b>{npc.name}</b> ({npc.profession})")
                talk_button = QtWidgets.QPushButton("Говорить")
                # --- ИЗМЕНЕНИЕ: Кнопка "Говорить" теперь тоже может выдавать квест ---
                talk_button.clicked.connect(lambda _, n=npc: self.request_npc_quest(n))
                npc_layout.addWidget(npc_label); npc_layout.addStretch(); npc_layout.addWidget(talk_button)
                actions_layout.addLayout(npc_layout)
        actions_layout.addStretch()

        close_button = QtWidgets.QPushButton("Уйти"); close_button.clicked.connect(self.accept)
        main_layout.addWidget(description_label); main_layout.addWidget(line)
        main_layout.addWidget(actions_group); main_layout.addStretch()
        main_layout.addWidget(close_button, 0, QtCore.Qt.AlignRight)
    
    def request_generic_quest(self):
        """Запрашивает общий квест для локации."""
        self.quest_requested_from_npc.emit(None) # Передаем None, чтобы показать, что это общий квест
        self.close()

    def request_npc_quest(self, npc):
        """Запрашивает квест от конкретного NPC."""
        self.quest_requested_from_npc.emit(npc)
        self.close()