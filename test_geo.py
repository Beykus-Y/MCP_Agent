# test_geo.py (версия с opensimplex)
import numpy as np
from opensimplex import OpenSimplex
import time

def generate_world_map_simplex(width, height, seed):
    print(f"Начинаю генерацию с OpenSimplex {width}x{height} с сидом {seed}...")
    
    # Инициализируем генератор шума с сидом
    simplex = OpenSimplex(seed)
    elevation = np.zeros((height, width))
    
    try:
        scale = 0.05 # Масштаб шума, можно подбирать
        for y in range(height):
            if y % 20 == 0:
                print(f"  ... обрабатываю строку {y}/{height}")

            for x in range(width):
                # noise2d принимает x и y, возвращает значение от -1 до 1
                elevation[y][x] = simplex.noise2(x * scale, y * scale)
        
        print("Генерация завершена успешно!")
        return True

    except Exception as e:
        import traceback
        print("\n--- ПРОИЗОШЛА ОШИБКА! ---")
        traceback.print_exc()
        return False

if __name__ == '__main__':
    start_time = time.time()
    # OpenSimplex принимает большие числа в качестве сида
    success = generate_world_map_simplex(width=128, height=128, seed=int(time.time()))
    end_time = time.time()
    
    if success:
        print(f"\nТест с OpenSimplex пройден успешно за {end_time - start_time:.2f} секунд.")
    else:
        print("\nТест с OpenSimplex провален. Ошибка указана выше.")