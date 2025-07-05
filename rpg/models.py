# rpg/models.py
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Set, Any # Добавлен Any для универсальности

@dataclass
class Quest:
    id: str
    name: str
    description: str
    status: str = "active"  # "active", "completed", "failed"
    objectives: List[Dict] = field(default_factory=list) # [{"text": "...", "completed": False}]

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Quest':
        return Quest(
            id=data.get('id', ''),
            name=data.get('name', ''),
            description=data.get('description', ''),
            status=data.get('status', 'active'),
            objectives=data.get('objectives', [])
        )

@dataclass
class NPC:
    name: str
    profession: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'NPC':
        return NPC(
            name=data.get('name', 'Unknown'),
            profession=data.get('profession', 'Citizen')
        )

@dataclass
class Stats:
    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    charisma: int = 10

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Stats':
        return Stats(
            strength=data.get('strength', 10),
            dexterity=data.get('dexterity', 10),
            intelligence=data.get('intelligence', 10),
            charisma=data.get('charisma', 10)
        )

@dataclass
class Item:
    id: str
    name: str
    description: str
    slot: str
    effects: List[Dict] = field(default_factory=list)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Item':
        return Item(
            id=data.get('id', ''),
            name=data.get('name', ''),
            description=data.get('description', ''),
            slot=data.get('slot', 'misc'),
            effects=data.get('effects', [])
        )

@dataclass
class Character:
    name: str
    backstory: str
    traits: List[str] = field(default_factory=list)
    stats: Stats = field(default_factory=Stats)
    equipment: Dict[str, Item] = field(default_factory=dict)
    inventory: List[Item] = field(default_factory=list)
    position: Tuple[int, int] = (0, 0)
    quests: List[Quest] = field(default_factory=list)
    max_hp: int = 100
    current_hp: int = 100
    active_flags: List[str] = field(default_factory=list) 
    discovered_cells: Set[Tuple[int, int]] = field(default_factory=set)
    visited_pois: List[str] = field(default_factory=list)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Character':
        # Десериализация вложенных объектов
        stats = Stats.from_dict(data.get('stats', {}))
        
        equipment = {}
        for slot, item_data in data.get('equipment', {}).items():
            equipment[slot] = Item.from_dict(item_data)
        
        inventory = [Item.from_dict(i_data) for i_data in data.get('inventory', [])]
        quests = [Quest.from_dict(q_data) for q_data in data.get('quests', [])]
        
        # Преобразование списка кортежей в набор кортежей для discovered_cells
        discovered_cells_set = set(tuple(c) for c in data.get('discovered_cells', []))

        return Character(
            name=data.get('name', 'Безымянный'),
            backstory=data.get('backstory', ''),
            traits=data.get('traits', []),
            stats=stats,
            equipment=equipment,
            inventory=inventory,
            position=tuple(data.get('position', (0, 0))),
            quests=quests,
            max_hp=data.get('max_hp', 100),
            current_hp=data.get('current_hp', 100),
            active_flags=data.get('active_flags', []),
            discovered_cells=discovered_cells_set,
            visited_pois=data.get('visited_pois', [])
        )