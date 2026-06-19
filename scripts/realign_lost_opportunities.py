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

# GHL Stages
STAGE_LOST = "b9549f80-9858-4e84-8afc-aacdcd4db23f"
STAGE_PENDIENTE_ASIGNACION = "164e9a2c-2ab8-4bd1-91b9-c2c3aa2dd85d"
STAGE_STANDBY_ACCESOS = "5214c97a-30b6-44b4-8f6f-dd1798622a8b"
STAGE_HABILITACION_TECNICA = "46400c15-10a3-4c96-a5b0-76f0cf65b753"
STAGE_VALIDACION_BACKOFFICE = "76f257d1-73b2-46a5-86f6-0b83fc59b716"
STAGE_ESPERANDO_WIN = "fdc27149-b398-4ed7-9271-946c66dc9f0f"
STAGE_ASIGNACION_APROBADA = "63afa897-dcb3-4d08-9a7a-c82f1e87c49f"
STAGE_PENDIENTE_HABILITACION = "f251b78c-b57f-4cbd-aa61-3653b54c7677"
STAGE_HABILITACION_COMPLETA = "dc5a218f-50a8-4bb6-9351-82b2f10d9886"
STAGE_EDIFICIO_PROSPECTADO = "4d5d6906-d70f-466a-9b9b-0acf0a203138"

from scripts.migrate_master_report import clean_building_name, clean_text

def map_stage_id_by_status(status_str, fase_str, dashboard_str):
    status_clean = clean_text(status_str)
    fase_clean = clean_text(fase_str)
    db_clean = clean_text(dashboard_str)
    
    # Historicos map to Pendiente Asignacion
    if db_clean == "HISTORICO":
        return STAGE_PENDIENTE_ASIGNACION
        
    # If Status is Desestimado, it goes to STAGE_LOST
    if status_clean in ["DESESTIMADO", "DESESTIMADO TEC.", "DESESTIMADO TEC"]:
        return STAGE_LOST
        
    # Otherwise, map based on STATUS
    if "APROBACION" in status_clean:
        return STAGE_ESPERANDO_WIN
    elif "CAPEX OBSERVADO" in status_clean or "REASIGNADO" in status_clean:
        return "07edaecc-8564-4618-a2be-bb9d7c81444c" # Pendiente Envío de Formulario Ficha de Datos
    elif "CON PERMISOS" in status_clean or "SIN PERMISOS" in status_clean or "REPROGRAMACION" in status_clean:
        return STAGE_VALIDACION_BACKOFFICE
    elif "CONSTRUCCION DE RED" in status_clean or "PRE FACTIBILIDAD" in status_clean:
        return STAGE_PENDIENTE_HABILITACION
    elif "OBRA" in status_clean or "PROGRAMACION" in status_clean or "PROGRAMADO" in status_clean or "PARALIZADO" in status_clean:
        return STAGE_HABILITACION_TECNICA
    elif "ACCESO" in status_clean or "ACCESOS" in status_clean:
        return STAGE_STANDBY_ACCESOS
    elif "HABILITADO" in status_clean:
        return STAGE_HABILITACION_COMPLETA
        
    # Fallback to FASE mapping
    if fase_clean == "TERMINADO":
        return STAGE_HABILITACION_COMPLETA
    elif fase_clean == "POR ACCESOS":
        return STAGE_STANDBY_ACCESOS
    elif fase_clean == "EN CONSTRUCCION":
        return STAGE_HABILITACION_TECNICA
    elif fase_clean == "TRAMITE":
        return STAGE_VALIDACION_BACKOFFICE
    elif fase_clean == "POR APROBACION":
        return STAGE_ESPERANDO_WIN
    elif fase_clean == "AMORTIZACION CAPEX":
        return STAGE_ASIGNACION_APROBADA
    elif fase_clean == "DISENO PREDIO":
        return STAGE_PENDIENTE_HABILITACION
        
    return STAGE_EDIFICIO_PROSPECTADO

def fetch_lost_opportunities(headers):
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
        for opp in items:
            if opp.get("pipelineStageId") == STAGE_LOST:
                results.append(opp)
        meta = data.get("meta", {})
        url = meta.get("nextPageUrl")
        params = None
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Realinear oportunidades desestimadas incorrectamente en GHL")
    parser.add_argument("--dry-run", action="store_true", help="Modo simulado sin realizar cambios en GHL")
    args = parser.parse_args()

    print("==================================================")
    print(f"[REALIGN] REALINEACIÓN DE OPORTUNIDADES DESESTIMADAS")
    print(f"  Modo Dry-run: {args.dry_run}")
    print("==================================================")

    # 1. Load Excel
    print("[INFO] Cargando Excel...")
    df_reporte = pd.read_excel('CONSOLIDADO DE FICHAS - WIN (respuestas) (1).xlsx', sheet_name='REPORTE DE FICHAS ENVIADAS')
    
    excel_by_name = {}
    for idx, row in df_reporte.iterrows():
        raw_name = str(row['NOMBRE DE PREDIO']).strip()
        c_name = clean_building_name(raw_name)
        excel_by_name[c_name] = row

    headers = {
        "Authorization": f"Bearer {GHL_TOKEN}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }

    # 2. Fetch opportunities in STAGE_LOST from GHL
    print("[INFO] Buscando oportunidades en etapa 'Hunting Perdido/ No Recuperable' en GHL...")
    lost_opps = fetch_lost_opportunities(headers)
    print(f"[INFO] Se encontraron {len(lost_opps)} oportunidades en la etapa de Perdidos en GHL.")

    realigned_count = 0
    kept_lost_count = 0
    not_found_excel = 0
    error_count = 0

    print("[INFO] Procesando realineacion...")
    for opp in lost_opps:
        opp_id = opp["id"]
        opp_name = opp["name"]
        
        # Clean name
        clean_name = opp_name
        if ":" in clean_name:
            clean_name = clean_name.split(":", 1)[1].strip()
        c_name = clean_building_name(clean_name)
        
        if c_name not in excel_by_name:
            print(f"  - [NOT IN EXCEL] '{opp_name}' (ID: {opp_id}) no se encuentra en el Excel.")
            not_found_excel += 1
            continue
            
        row = excel_by_name[c_name]
        status = row.get("STATUS")
        fase = row.get("FASE")
        dashboard = row.get("DASHBOARD")
        
        correct_stage = map_stage_id_by_status(status, fase, dashboard)
        
        if correct_stage == STAGE_LOST:
            print(f"  - [KEEP LOST] '{opp_name}' (ID: {opp_id}) se queda en Hunting Perdido (Status Excel: {status})")
            kept_lost_count += 1
            continue
            
        print(f"  - [REALIGN OPPORTUNITY] '{opp_name}' (ID: {opp_id}) -> Nueva Etapa: '{correct_stage}' (Status Excel: {status})")
        realigned_count += 1
        
        if not args.dry_run:
            url = f"https://services.leadconnectorhq.com/opportunities/{opp_id}"
            update_payload = {
                "pipelineStageId": correct_stage,
                "status": "open" # Re-open since it is not lost anymore!
            }
            res_put = requests.put(url, headers=headers, json=update_payload, timeout=15)
            if res_put.status_code in [200, 201]:
                print(f"    [SUCCESS] Actualizado en GHL con exito.")
            else:
                print(f"    [ERROR] Error al actualizar en GHL: {res_put.text}")
                error_count += 1
            time.sleep(0.25)

    print("\n" + "="*50)
    print("RESUMEN DE REALINEACIÓN DE PERDIDOS:")
    print(f"  - Oportunidades que permanecen como Perdidos (Correctas): {kept_lost_count}")
    print(f"  - Oportunidades realineadas (Movidas de etapa): {realigned_count}")
    print(f"  - No encontradas en Excel: {not_found_excel}")
    print(f"  - Errores de API: {error_count}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
