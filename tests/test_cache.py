import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import os

path = '/app/storage/cache_fichas_datos.json'
if not os.path.exists(path):
    print("ERROR: Cache file does not exist")
    sys.exit(1)

with open(path, 'r', encoding='utf-8') as f:
    cache = json.load(f)

key = 'opp::TLiHyuFC1dZZ4pQrw3gY'
if key not in cache:
    print(f"ERROR: Key {key} not in cache")
    print("Available keys:", list(cache.keys())[:10])
else:
    data = cache[key]
    print("=== CACHED OPPORTUNITY DETAILS ===")
    print("Project Name:", data.get("cf_nombre_proyecto"))
    print("foto_edificio:", data.get("cf_foto_edificio"))
    print("foto_montantes:", data.get("cf_foto_montantes"))
    print("foto_edificio_path:", data.get("foto_edificio_path"))
    print("foto_montantes_path:", data.get("foto_montantes_path"))
    print("=== END ===")
