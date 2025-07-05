# rpg/world/geography.py
import numpy as np
from opensimplex import OpenSimplex

def generate_world_map(width, height, seed):
    """
    Генерирует карту высот и биомов, используя OpenSimplex шум.
    """
    # Инициализируем генераторы для разных карт
    elevation_simplex = OpenSimplex(seed)
    moisture_simplex = OpenSimplex(seed + 1) # Используем другой сид для влажности

    # 1. Генерация карты высот
    scale = 0.02 # Масштаб. Меньше значение = более "приближенная" карта.
    elevation = np.zeros((height, width))
    for y in range(height):
        for x in range(width):
            # Используем несколько слоев (октав) для большей детализации
            e1 = elevation_simplex.noise2(x * scale, y * scale)
            e2 = elevation_simplex.noise2(x * scale * 2, y * scale * 2) * 0.5
            e3 = elevation_simplex.noise2(x * scale * 4, y * scale * 4) * 0.25
            elevation[y][x] = e1 + e2 + e3
    
    # 2. Генерация карты влажности
    moisture_scale = 0.03
    moisture = np.zeros((height, width))
    for y in range(height):
        for x in range(width):
            moisture[y][x] = moisture_simplex.noise2(x * moisture_scale, y * moisture_scale)

    # 3. Определение биомов (логика остается прежней)
    biome_map = [["" for _ in range(width)] for _ in range(height)]
    for y in range(height):
        for x in range(width):
            e = elevation[y][x]
            m = moisture[y][x]
            
            # Нормализуем значения, так как OpenSimplex возвращает от -1 до 1
            e_norm = (e + 1) / 2 

            if e_norm < 0.2: biome_map[y][x] = "deep_ocean"
            elif e_norm < 0.35: biome_map[y][x] = "ocean"
            elif e_norm < 0.4: biome_map[y][x] = "beach"
            elif e_norm > 0.8:
                if m < -0.2: biome_map[y][x] = "scorched"
                else: biome_map[y][x] = "snowy_peak"
            elif e_norm > 0.65:
                if m < -0.3: biome_map[y][x] = "temperate_desert"
                else: biome_map[y][x] = "mountains"
            elif e_norm > 0.45:
                if m < -0.4: biome_map[y][x] = "desert"
                elif m < 0.4: biome_map[y][x] = "forest"
                else: biome_map[y][x] = "jungle"
            else:
                if m < -0.5: biome_map[y][x] = "desert"
                else: biome_map[y][x] = "grassland"

    return biome_map