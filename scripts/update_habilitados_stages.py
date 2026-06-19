import os
import sys
import sqlite3
import pandas as pd
import requests
import time

# Add project root to sys.path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def load_env_manually():
    env_vars = {}
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    env_path = os.path.join(base_dir, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

env = load_env_manually()
GHL_TOKEN = env.get("GHL_ACCESS_TOKEN", "pit-91efad56-ae58-41d7-85f6-6b66504b7e16")
LOCATION_ID = env.get("GHL_LOCATION_ID", "dHdydlGzW0HODg6XDQe7")
PIPELINE_ID = env.get("PIPELINE_ID", "LPfxv2sqrrNOTtjbWZ3h")
STAGE_HABILITACION_COMPLETA = "dc5a218f-50a8-4bb6-9351-82b2f10d9886"

from scripts.migrate_master_report import clean_building_name

def fetch_all_opportunities(headers):
    results = []
    url = "https://services.leadconnectorhq.com/opportunities/search"
    params = {"location_id": LOCATION_ID, "pipeline_id": PIPELINE_ID, "limit": 100}
    while url:
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"[ERROR] HTTP {resp.status_code} al buscar oportunidades: {resp.text}")
            break
        data = resp.json()
        items = data.get("opportunities", [])
        results.extend(items)
        meta = data.get("meta", {})
        url = meta.get("nextPageUrl")
        params = None
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Actualizar oportunidades habilitadas a la etapa correcta en GHL")
    parser.add_argument("--dry-run", action="store_true", help="Modo simulado sin realizar cambios en GHL")
    args = parser.parse_args()

    print("==================================================")
    print(f"[UPDATE] ACTUALIZACIÓN OPTIMIZADA DE ETAPAS DE HABILITADOS EN GHL")
    print(f"  Modo Dry-run: {args.dry_run}")
    print("==================================================")

    # 1. Load Excel
    print("[INFO] Cargando Excel...")
    df_reporte = pd.read_excel('CONSOLIDADO DE FICHAS - WIN (respuestas) (1).xlsx', sheet_name='REPORTE DE FICHAS ENVIADAS')
    filtered = df_reporte[(df_reporte['STATUS'] == 'HABILITADO') & (df_reporte['SUB STATUS'] == 'EDIFICIO HABILITADO')]
    print(f"Total Habilitados en Excel: {len(filtered)}")

    # 2. Load SQLite database
    print("[INFO] Cargando cache de SQLite...")
    conn = sqlite3.connect('storage/ghl_system.db')
    c = conn.cursor()
    c.execute("SELECT oportunidad_id, contacto_id, nombre_proyecto FROM oportunidades_ficha")
    db_rows = c.fetchall()
    conn.close()

    db_by_name = {}
    for row in db_rows:
        opp_id, contact_id, name = row
        c_name = clean_building_name(name)
        db_by_name[c_name] = (opp_id, contact_id, name)

    headers = {
        "Authorization": f"Bearer {GHL_TOKEN}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }

    # 3. Fetch all current opportunities in GHL pipeline in bulk
    print("[INFO] Cargando todas las oportunidades del Pipeline desde GHL API...")
    ghl_opps = fetch_all_opportunities(headers)
    print(f"[INFO] Se cargaron {len(ghl_opps)} oportunidades de GHL en memoria.")
    
    # Map GHL opp_id -> stage_id
    ghl_stage_map = {opp["id"]: opp.get("pipelineStageId") for opp in ghl_opps}

    updated_count = 0
    skipped_count = 0
    error_count = 0
    not_found_in_db = 0

    print("[INFO] Validando y actualizando etapas...")
    for idx, row in filtered.iterrows():
        raw_name = str(row['NOMBRE DE PREDIO']).strip()
        c_name = clean_building_name(raw_name)

        if c_name not in db_by_name:
            print(f"  - [NOT IN DB] No se encuentra en SQLite: '{raw_name}' (Fila: {idx+2})")
            not_found_in_db += 1
            continue

        opp_id, contact_id, db_name = db_by_name[c_name]
        
        # Check current stage from our memory map
        current_stage = ghl_stage_map.get(opp_id)
        
        if not current_stage:
            # Fallback to direct fetch if not found in bulk search
            print(f"  - [FALLBACK] Opp {opp_id} no encontrada en busqueda masiva, haciendo GET directo...")
            url = f"https://services.leadconnectorhq.com/opportunities/{opp_id}"
            res_get = requests.get(url, headers=headers, timeout=15)
            if res_get.status_code == 200:
                opp_data = res_get.json().get("opportunity", {})
                current_stage = opp_data.get("pipelineStageId")
            else:
                print(f"    [ERROR] No se pudo obtener opp {opp_id}: HTTP {res_get.status_code}")
                error_count += 1
                continue

        if current_stage == STAGE_HABILITACION_COMPLETA:
            skipped_count += 1
            continue

        print(f"  - [STAGING DIFFERENCE] '{raw_name}' (ID: {opp_id}) esta en etapa '{current_stage}' -> Deberia ser Habilitacion Completa")
        
        if not args.dry_run:
            url = f"https://services.leadconnectorhq.com/opportunities/{opp_id}"
            update_payload = {
                "pipelineStageId": STAGE_HABILITACION_COMPLETA
            }
            res_put = requests.put(url, headers=headers, json=update_payload, timeout=15)
            if res_put.status_code in [200, 201]:
                print(f"    [SUCCESS] Actualizado en GHL con exito.")
                updated_count += 1
            else:
                print(f"    [ERROR] Error al actualizar en GHL: {res_put.text}")
                error_count += 1
            # Throttle API requests
            time.sleep(0.25)
        else:
            updated_count += 1

    print("\n" + "="*50)
    print("RESUMEN DE ACTUALIZACION DE HABILITADOS:")
    print(f"  - Ya en etapa Habilitacion Completa (omitidos): {skipped_count}")
    print(f"  - Pendientes de actualizacion / Actualizados: {updated_count}")
    print(f"  - Errores encontrados: {error_count}")
    print(f"  - No encontrados en SQLite: {not_found_in_db}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
