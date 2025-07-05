# rpg/world/world_state.py
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Any

from ..models import NPC # Теперь NPC один, из models.py

@dataclass
class PointOfInterest:
    id: str
    name: str
    type: str  # "capital", "town", "ruin", "dungeon", "natural_wonder"
    position: Tuple[int, int] # (x, y)
    description: str = ""
    controlling_faction_id: str = ""
    npcs: List[NPC] = field(default_factory=list)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'PointOfInterest':
        npcs = [NPC.from_dict(npc_data) for npc_data in data.get('npcs', [])]
        return PointOfInterest(
            id=data.get('id', ''),
            name=data.get('name', ''),
            type=data.get('type', ''),
            position=tuple(data.get('position', (0,0))),
            description=data.get('description', ''),
            controlling_faction_id=data.get('controlling_faction_id', ''),
            npcs=npcs
        )

@dataclass
class Faction:
    id: str
    name: str
    type: str  # "kingdom", "horde", "merchant_guild", "ancient_race"
    description: str
    relations: Dict[str, int] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Faction':
        return Faction(
            id=data.get('id', ''),
            name=data.get('name', ''),
            type=data.get('type', ''),
            description=data.get('description', ''),
            relations=data.get('relations', {})
        )


@dataclass
class WorldState:
    """Хранит все данные о сгенерированном мире."""
    world_name: str
    seed: int
    map_size: Tuple[int, int]
    
    year: int = 1000
    tech_level: str = "fantasy"
    magic_level: str = "medium"
    
    biome_map: List[List[str]] = field(default_factory=list)
    points_of_interest: List[PointOfInterest] = field(default_factory=list)
    factions: List[Faction] = field(default_factory=list)
    history_log: List[str] = field(default_factory=list)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'WorldState':
        factions = [Faction.from_dict(f_data) for f_data in data.get('factions', [])]
        pois = [PointOfInterest.from_dict(p_data) for p_data in data.get('points_of_interest', [])]

        return WorldState(
            world_name=data.get('world_name', 'Безымянный мир'),
            seed=data.get('seed', 0),
            map_size=tuple(data.get('map_size', (0,0))),
            year=data.get('year', 1000),
            tech_level=data.get('tech_level', 'fantasy'),
            magic_level=data.get('magic_level', 'medium'),
            biome_map=data.get('biome_map', []),
            points_of_interest=pois,
            factions=factions,
            history_log=data.get('history_log', [])
        )