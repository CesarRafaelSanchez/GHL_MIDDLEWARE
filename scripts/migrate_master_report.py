import os
import sys
import re
import json
import argparse
import sqlite3
import pandas as pd
import requests
import time
from datetime import datetime

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

os.environ["GHL_ACCESS_TOKEN"] = GHL_TOKEN
os.environ["GHL_LOCATION_ID"] = LOCATION_ID
os.environ["PIPELINE_ID"] = PIPELINE_ID

from app.database import get_db_connection, guardar_oportunidad_db_internal
from app.services.ficha_service import construir_datos_ficha_desde_webhook
from app.utils.helpers import obtener_mapa_keys_a_ids, extraer_custom_fields_para_ghl, obtener_session_con_retries

# 16 recent opportunities to exclude (17 IDs in DB)
EXCLUDE_IDS = {
    'z5riMGZlHe8E3xlfRFYr', 'tzZ720aGIcWWa2GuctDg', 'vk9wwTNRTBAxGLXuNNzh', 
    'fTgTm8HwLD6k1HGhW7LY', 'f4mxY8l6f41qzebbiaeG', 'MjHgRfsjKyAKgbZFLjbo', 
    'UmH9T4TJSF0pzP2P1UIz', 'JgkafWf0yqp7B8oYFPHI', 'ewJL121xefe3OWQWizAX', 
    'ljXhLgKTfs0dNutOpj4m', '3WsFNurMHI1UIwU0Xg5U', 'u6G8vZ5QJdFDhcutNWMY', 
    'pO1AwPvzsQAfy39Ijo70', 'MnEjJEUCaXZWg1Sc7Y1W', 'MlsAviu6V3qwSw9PuVMw', 
    'TlyHPDBgzlPz00P6HcJc', 'kPpNIA7Rua0yekezkVtc'
}

EXCLUDE_NAMES = {
    "EDIFICIO RUMI", "ALBA", "DIBOS 840", "AURELIO GARCIA Y GARCIA 239", 
    "EDIFICIO POMALCA 173", "LOS PRECURSORES 880", "EDIFICIO GALLESE TARICCHI 880", 
    "RAFAEL ESCARDO 1", "EDIFICIO LIMA 675", "EDIFICIO DOMODOSSOLA", 
    "EDIFICIO GERARD BLANCHERE 163", "EDIFICIO BARBIERI", "RESIDENCIAL INDEPENDENCIA", 
    "EDIFICIO PADEREWSKI 137", "EDIFICIO CALVINO", 
    "EDIFICIO DOMINGO ORUE 261 (CONJUNTO HABITACIONAL DAMMERT MUELLE)"
}

# GHL Pipelines Stage IDs Mapping
STAGE_PENDIENTE_ASIGNACION = "164e9a2c-2ab8-4bd1-91b9-c2c3aa2dd85d"
STAGE_LOST = "b9549f80-9858-4e84-8afc-aacdcd4db23f"
STAGE_HABILITACION_COMPLETA = "dc5a218f-50a8-4bb6-9351-82b2f10d9886"
STAGE_STANDBY_ACCESOS = "5214c97a-30b6-44b4-8f6f-dd1798622a8b"
STAGE_HABILITACION_TECNICA = "46400c15-10a3-4c96-a5b0-76f0cf65b753"
STAGE_VALIDACION_BACKOFFICE = "76f257d1-73b2-46a5-86f6-0b83fc59b716"
STAGE_ESPERANDO_WIN = "fdc27149-b398-4ed7-9271-946c66dc9f0f"
STAGE_ASIGNACION_APROBADA = "63afa897-dcb3-4d08-9a7a-c82f1e87c49f"
STAGE_PENDIENTE_HABILITACION = "f251b78c-b57f-4cbd-aa61-3653b54c7677"
STAGE_EDIFICIO_PROSPECTADO = "4d5d6906-d70f-466a-9b9b-0acf0a203138"

# Stefano Sotomarino Back Office (Default assigned user for invalid/missing hunters)
DEFAULT_STEFANO_ID = "6u8iZhDXnxp0xSp7XfDl"

# Load users map from usuarios.json
def load_usuarios():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    path = os.path.join(base_dir, "usuarios.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

usuarios_dict = load_usuarios()

def clean_text(text):
    if pd.isna(text) or text is None:
        return ""
    text = str(text).strip().upper()
    replacements = {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U", "Ñ": "N"}
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def clean_building_name(name):
    if pd.isna(name) or name is None:
        return ""
    name = str(name).strip().upper()
    # Remove accents
    name = clean_text(name)
    # Remove common prefixes
    for prefix in ['EDIFICIO ', 'EDIFICIO', 'CONDOMINIO ', 'CONDOMINIO', 'RESIDENCIAL ', 'RESIDENCIAL', 'CONJUNTO RESIDENCIAL ', 'PROYECTO ']:
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
    # Replace multiple spaces with single space
    name = " ".join(name.split())
    return name

def normalize_phone(phone):
    if pd.isna(phone) or phone is None:
        return ""
    digits = "".join([c for c in str(phone) if c.isdigit()])
    if not digits:
        return ""
    
    # Handle multiple concatenated phone numbers
    if len(digits) >= 18:
        if digits.startswith("51") and digits[2] == "9":
            digits = digits[:11]
        elif digits.startswith("9"):
            digits = digits[:9]
            
    if len(digits) == 11 and digits.startswith("51"):
        return digits
    if len(digits) == 9 and digits.startswith("9"):
        return "51" + digits
    if digits.startswith("0051") and len(digits) == 13:
        return digits[2:]
        
    # Truncate to maximum 15 digits for GHL API compliance
    return digits[:15]


def clean_email(email_str):
    if not email_str or pd.isna(email_str):
        return ""
    email_str = str(email_str).strip()
    match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', email_str)
    if match:
        return match.group(0)
    return ""


def clean_url(url_str):
    if not url_str or pd.isna(url_str):
        return ""
    url_str = str(url_str).strip()
    if url_str.lower().startswith("http"):
        return url_str
    return ""


def map_stage_id(fase, dashboard):
    fase_clean = clean_text(fase)
    db_clean = clean_text(dashboard)
    
    if db_clean == "HISTORICO":
        return STAGE_PENDIENTE_ASIGNACION
    
    if fase_clean == "DESESTIMADO" or fase_clean == "DESESTIMADO TEC.":
        return STAGE_LOST
    elif fase_clean == "TERMINADO":
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

def find_user_id(hunter_name):
    if not hunter_name or pd.isna(hunter_name):
        return DEFAULT_STEFANO_ID
    
    hunter_clean = clean_text(hunter_name)
    
    # Check exact normalized match
    for u_name, u_id in usuarios_dict.items():
        if clean_text(u_name) == hunter_clean:
            return u_id
            
    # Check partial match
    for u_name, u_id in usuarios_dict.items():
        u_clean = clean_text(u_name)
        en_words = set(hunter_clean.split())
        ghl_words = set(u_clean.split())
        # Filter GHL suffix descriptions
        ignore = {"HUNTER", "BACK", "OFFICE", "TI", "CEO"}
        en_words_f = en_words - ignore
        ghl_words_f = ghl_words - ignore
        overlap = en_words_f.intersection(ghl_words_f)
        if len(overlap) >= 2 or (len(en_words_f) == 1 and len(overlap) == 1):
            return u_id
            
    return DEFAULT_STEFANO_ID

def parse_id(val):
    if pd.isna(val) or val is None:
        return None
    try:
        s = str(val).strip()
        if s.endswith('.0'):
            s = s[:-2]
        if s in ('-', '', 'nan'):
            return None
        return int(float(s))
    except ValueError:
        return None

def main():
    parser = argparse.ArgumentParser(description="Migracion Masiva de Oportunidades del Reporte Maestro a GHL y SQLite")
    parser.add_argument("--excel-master", default="CONSOLIDADO DE FICHAS - WIN (respuestas) (1).xlsx", help="Excel maestro de fichas")
    parser.add_argument("--excel-asig", default="WIN - FORMATO DE ASIGNACION (Respuestas).xlsx", help="Excel de asignaciones")
    parser.add_argument("--dry-run", action="store_true", help="Modo simulado sin realizar cambios en GHL ni BD")
    parser.add_argument("--limit", type=int, default=None, help="Limite de filas a procesar")
    args = parser.parse_args()
    print("==================================================")




    print("[MIGRATION] MIGRACION MASIVA DE REPORTE MAESTRO A GHL & DB")
    print(f"  Master Excel: {args.excel_master}")
    print(f"  Asignacion Excel: {args.excel_asig}")
    print(f"  Modo Dry-run: {args.dry_run}")
    if args.limit:
        print(f"  Limite: {args.limit} filas")
    print("==================================================")

    # 1. Load Excel DataFrames
    print("[INFO] Cargando excels en memoria...")
    df_reporte = pd.read_excel(args.excel_master, sheet_name='REPORTE DE FICHAS ENVIADAS')
    df_fichas = pd.read_excel(args.excel_master, sheet_name='Respuestas de formulario 1')
    df_asignaciones = pd.read_excel(args.excel_asig, sheet_name='CONSOLIDADO ASIGNACIONES')

    print(f"  Registros leidos: Reporte={len(df_reporte)}, Fichas={len(df_fichas)}, Asignaciones={len(df_asignaciones)}")


    # Index Fichas and Asignaciones for fast lookup
    df_fichas['parsed_id'] = df_fichas['ID'].apply(parse_id)
    df_fichas['clean_name'] = df_fichas['Nombre del Edificio / Condominio'].apply(clean_building_name)
    fichas_by_id = {int(row['parsed_id']): row for _, row in df_fichas.iterrows() if pd.notna(row['parsed_id'])}
    fichas_by_name = {row['clean_name']: row for _, row in df_fichas.iterrows() if row['clean_name']}

    df_asignaciones['parsed_id'] = df_asignaciones['ID'].apply(parse_id)
    df_asignaciones['clean_name'] = df_asignaciones['NOMBRE DEL EDIFICIO / PROYECTO'].apply(clean_building_name)
    asig_by_id = {int(row['parsed_id']): row for _, row in df_asignaciones.iterrows() if pd.notna(row['parsed_id'])}
    asig_by_name = {row['clean_name']: row for _, row in df_asignaciones.iterrows() if row['clean_name']}

    session = obtener_session_con_retries()
    HEADERS_GHL = {
        "Authorization": f"Bearer {GHL_TOKEN}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }
    HEADERS_GHL_COMPANY = {
        "Authorization": f"Bearer {GHL_TOKEN}",
        "Version": "2023-02-21",
        "Content-Type": "application/json"
    }

    # Setup database connection
    db_conn = get_db_connection()
    db_conn.row_factory = sqlite3.Row
    db_cursor = db_conn.cursor()

    # Load currently cached opportunities to ensure idempotency (skipping recent/already migrated ones)
    db_cursor.execute("SELECT oportunidad_id, contacto_id, nombre_proyecto FROM oportunidades_ficha")
    db_rows = db_cursor.fetchall()
    existing_clean_names = {clean_building_name(r["nombre_proyecto"]) for r in db_rows if r["nombre_proyecto"]}
    existing_opp_ids = {r["oportunidad_id"] for r in db_rows if r["oportunidad_id"]}
    
    print(f"[INFO] Se cargaron {len(db_rows)} oportunidades de la cache SQLite.")
    print(f"[INFO] Nombres limpios existentes en cache (no se migraran): {existing_clean_names}")

    # Normalize names for exclusions (as backup)
    EXCLUDE_NAMES_CLEAN = {clean_building_name(n) for n in EXCLUDE_NAMES}

    success_count = 0
    exclude_count = 0
    error_count = 0
    processed_count = 0

    for idx, row in df_reporte.iterrows():
        if args.limit and processed_count >= args.limit:
            break

        rep_id_raw = row['f']
        rep_id = parse_id(rep_id_raw)
        raw_name = str(row['NOMBRE DE PREDIO']).strip()
        c_name = clean_building_name(raw_name)

        # Skip if raw building name is empty
        if not raw_name or raw_name == 'nan':
            continue

        # Check if already exists in local DB or matches exclude names
        is_excluded = False
        if c_name in existing_clean_names:
            is_excluded = True
        elif c_name in EXCLUDE_NAMES_CLEAN:
            is_excluded = True

        if is_excluded:
            print(f"[EXCLUDED] Excluido (Existe en DB / Excluido): '{raw_name}' (ID: {rep_id})")
            exclude_count += 1
            continue

        processed_count += 1
        print("\n------------------------------------------")
        print(f"ROW Fila {idx+2} | Procesando: '{raw_name}' (ID: {rep_id})")



        # 3. Match Ficha and Asignacion details
        ficha_row = None
        if rep_id is not None and rep_id in fichas_by_id:
            ficha_row = fichas_by_id[rep_id]
        elif c_name in fichas_by_name:
            ficha_row = fichas_by_name[c_name]

        asig_row = None
        if rep_id is not None and rep_id in asig_by_id:
            asig_row = asig_by_id[rep_id]
        elif c_name in asig_by_name:
            asig_row = asig_by_name[c_name]

        # 4. Map Hunter / Owner
        gestor_excel = row['GESTOR DE HABILITACION']
        owner_id = find_user_id(gestor_excel)
        print(f"   [OWNER] Hunter original: '{gestor_excel}' -> Owner GHL ID: {owner_id}")

        # 5. Map Pipeline Stage and Status
        fase = row['FASE']
        dashboard = row['DASHBOARD']
        stage_id = map_stage_id(fase, dashboard)
        ghl_status = "lost" if stage_id == STAGE_LOST else "open"
        print(f"   [STAGE] Fase: '{fase}' | Dashboard: '{dashboard}' -> GHL Stage ID: {stage_id} (Status: {ghl_status})")


        # 6. Gather Flat Custom Fields
        # Start with Master Report data (single source of truth)
        flat_fields = {
            "cf_nombre_proyecto": raw_name,
            "cf_distrito": row['DISTRITO'] if pd.notna(row['DISTRITO']) else "",
            "cf_direccion_edificio": row['DIRECCIÓN'] if pd.notna(row['DIRECCIÓN']) else "",
            "cf_codigo_postal_edificio": str(int(float(row['CODIGO POSTAL']))) if pd.notna(row['CODIGO POSTAL']) and str(row['CODIGO POSTAL']).replace('.0','').isdigit() else "",
            "cf_total_torres_proyecto": str(int(float(row['TOTAL TORRES']))) if pd.notna(row['TOTAL TORRES']) else "1",
            "cf_total_hogares_proyecto": str(int(float(row['TOTAL HOGARES']))) if pd.notna(row['TOTAL HOGARES']) else "",
            "cf_supervisor_hunting": row['SUPERVISOR COMERCIAL'] if pd.notna(row['SUPERVISOR COMERCIAL']) else "",
            "cf_nombre_canal_hunting": row['CANAL DE HABILITACION'] if pd.notna(row['CANAL DE HABILITACION']) else "Futura",
            "cf_tipo_ingreso": "Hunting",
            "cf_gestor_real": gestor_excel if pd.notna(gestor_excel) else "",
            "cf_ejecutivo_principal": gestor_excel if pd.notna(gestor_excel) else "",
            "cf_fuente_hunting": row['FUENTE'] if pd.notna(row['FUENTE']) else "Propio",
            "cf_tipo_proyecto": row['TIPO DE PROYECTO'] if pd.notna(row['TIPO DE PROYECTO']) else "NUEVO PREDIO",
            "cf_tipo_construccion_edificio": "Moderno"
        }

        # Enrich with Ficha (Formulario 2) data if available
        resp_nombre = ""
        resp_tel = ""
        resp_correo = ""
        if ficha_row is not None:
            print("   [FICHA] Ficha de Datos (Formulario 2) encontrada. Enriqueciendo...")
            resp_nombre = ficha_row['Nombre del Responsable'] if pd.notna(ficha_row['Nombre del Responsable']) else ""
            resp_tel = normalize_phone(ficha_row['Teléfono - Móvil'])
            resp_correo = clean_email(ficha_row['Correo'])
            
            flat_fields.update({
                "cf_nombre_responsable_edificio": resp_nombre,
                "cf_cargo_responsable_edificio": ficha_row['Cargo del Responsable'] if pd.notna(ficha_row['Cargo del Responsable']) else "",
                "cf_telefono_responsable_edificio": resp_tel,
                "cf_correo_responsable_edificio": resp_correo,
                "cf_junta_directiva": ficha_row['Junta Directiva'] if pd.notna(ficha_row['Junta Directiva']) else "",
                "cf_operador_actual": ficha_row['Operador Actual'] if pd.notna(ficha_row['Operador Actual']) else "",
                "cf_rango_horario_visita_tecnica": ficha_row['Rango Horario'] if pd.notna(ficha_row['Rango Horario']) else "",
                "cf_foto_edificio": clean_url(ficha_row['Foto del edificio']),
                "cf_foto_montantes": clean_url(ficha_row['Foto de las montantes (ducterías) y acometida (mecha)  ']),
                "cf_nombre_torre1_proyecto": ficha_row['Nombre Primera Torre (1; A; Nombre)'] if pd.notna(ficha_row['Nombre Primera Torre (1; A; Nombre)']) else "1",
                "cf_pisos_torre1_proyecto": str(int(float(ficha_row['Cantidad de Pisos (Primera Torre)']))) if pd.notna(ficha_row['Cantidad de Pisos (Primera Torre)']) else "",
                "cf_hogares_por_piso_torre1": str(int(float(ficha_row['Cantidad de Hogares Por Piso (Primera Torre)']))) if pd.notna(ficha_row['Cantidad de Hogares Por Piso (Primera Torre)']) else "",
                "cf_clasificacion_proyecto": ficha_row['Clasificación'] if pd.notna(ficha_row['Clasificación']) else "Edificio (1 a 2 torres)"
            })
            # Compute total hogares if empty
            if not flat_fields["cf_total_hogares_proyecto"] and pd.notna(ficha_row['Total Hogares']):
                flat_fields["cf_total_hogares_proyecto"] = str(int(float(ficha_row['Total Hogares'])))

        # Enrich with Asignacion (Formulario 1) data if available
        if asig_row is not None:
            print("   [ASIGNACION] Formulario de Asignacion (Formulario 1) encontrado. Enriqueciendo...")
            if pd.notna(asig_row['COORDENADAS']):
                flat_fields["cf_coordenadas"] = str(asig_row['COORDENADAS']).strip()
            if pd.notna(asig_row['INMOBILIARIA  (EDIFICIOS NUEVOS)']) and str(asig_row['INMOBILIARIA  (EDIFICIOS NUEVOS)']).strip() not in ["", "-"]:
                flat_fields["cf_inmobiliaria"] = str(asig_row['INMOBILIARIA  (EDIFICIOS NUEVOS)']).strip()

        # Build custom fields payload
        custom_fields_ghl = extraer_custom_fields_para_ghl(flat_fields)

        # 7. Execute GHL API requests (only if dry-run is False)
        contact_id = None
        opp_id = None

        if args.dry_run:
            contact_id = f"sim_contact_{idx}"
            opp_id = f"sim_opp_{idx}"
            print(f"   [DRY-RUN] Crear/Actualizar Contacto GHL: firstName='Administración:', lastName='{raw_name}', assignedTo='{owner_id}'")
            if resp_nombre:
                print(f"   [DRY-RUN] Enriquecido con Responsable: '{resp_nombre}' | Tel: '{resp_tel}' | Email: '{resp_correo}'")
            print(f"   [DRY-RUN] Crear Compañía en GHL: name='{raw_name}'")
            print(f"   [DRY-RUN] Crear Oportunidad GHL: name='{raw_name}', stage='{stage_id}', status='{ghl_status}', assignedTo='{owner_id}'")
            success_count += 1
        else:
            try:
                # 7A. Create Contact in GHL
                # Split responsible name if present, otherwise use defaults
                first_name = "Administración:"
                last_name = raw_name
                
                contact_payload = {
                    "locationId": LOCATION_ID,
                    "firstName": first_name,
                    "lastName": last_name,
                    "assignedTo": owner_id,
                    "customFields": custom_fields_ghl
                }
                
                if resp_tel:
                    contact_payload["phone"] = resp_tel
                if resp_correo and "@" in resp_correo and "." in resp_correo:
                    contact_payload["email"] = resp_correo

                res_contact = session.post("https://services.leadconnectorhq.com/contacts/", headers=HEADERS_GHL, json=contact_payload, timeout=25)
                
                # If contact already exists by email/phone (400 Bad Request / duplicated)
                if res_contact.status_code == 400 and "duplicated" in res_contact.text.lower():
                    # Retry without unique fields to update or create
                    print("   [INFO] Contacto duplicado por email/telefono. Creando contacto solo con nombre...")
                    contact_payload.pop("email", None)
                    contact_payload.pop("phone", None)
                    res_contact = session.post("https://services.leadconnectorhq.com/contacts/", headers=HEADERS_GHL, json=contact_payload, timeout=25)
                
                if res_contact.status_code not in [200, 201]:
                    print(f"   [ERROR] Error al crear contacto GHL: {res_contact.text}")
                    error_count += 1
                    continue
                    
                contact_id = res_contact.json().get("contact", {}).get("id")
                print(f"   [SUCCESS] Contacto GHL creado exitosamente. ID: {contact_id}")

                # 7B. Create and link Company (Business)
                company_payload = {
                    "locationId": LOCATION_ID,
                    "name": raw_name,
                    "address": flat_fields.get("cf_direccion_edificio") or "No especificada",
                    "city": flat_fields.get("cf_distrito") or "Lima",
                    "state": "Lima",
                    "country": "PE"
                }
                res_comp = session.post("https://services.leadconnectorhq.com/businesses/", headers=HEADERS_GHL_COMPANY, json=company_payload, timeout=25)
                company_id = None
                if res_comp.status_code in [200, 201]:
                    resp_json = res_comp.json()
                    company_id = resp_json.get("id") or resp_json.get("business", {}).get("id")
                    print(f"   [SUCCESS] Compania GHL creada exitosamente. ID: {company_id}")
                    
                    # Link Contact and Company (Business)
                    link_payload = {"businessId": company_id}
                    session.put(f"https://services.leadconnectorhq.com/contacts/{contact_id}", headers=HEADERS_GHL, json=link_payload, timeout=25)
                    print(f"   [SUCCESS] Compania vinculada al contacto.")
                else:
                    print(f"   [WARNING] Compania no creada: {res_comp.text}")

                # 7C. Create Opportunity in GHL
                opp_payload = {
                    "locationId": LOCATION_ID,
                    "contactId": contact_id,
                    "pipelineId": PIPELINE_ID,
                    "pipelineStageId": stage_id,
                    "name": raw_name,
                    "status": ghl_status,
                    "assignedTo": owner_id,
                    "customFields": custom_fields_ghl
                }
                res_opp = session.post("https://services.leadconnectorhq.com/opportunities/", headers=HEADERS_GHL, json=opp_payload, timeout=25)
                if res_opp.status_code not in [200, 201]:
                    print(f"   [ERROR] Error al crear oportunidad GHL: {res_opp.text}")
                    error_count += 1
                    continue
                    
                opp_id = res_opp.json().get("opportunity", {}).get("id")
                print(f"   [SUCCESS] Oportunidad GHL creada exitosamente. ID: {opp_id}")

                # Add follower (Stefano)
                session.post(f"https://services.leadconnectorhq.com/opportunities/{opp_id}/followers", headers=HEADERS_GHL, json={"followers": [DEFAULT_STEFANO_ID]}, timeout=20)

                # 7D. Save in Local SQLite DB
                datos_mapeados = construir_datos_ficha_desde_webhook(flat_fields)
                guardar_oportunidad_db_internal(db_cursor, opp_id, contact_id, datos_mapeados, flat_fields)
                db_conn.commit()
                print("   [SUCCESS] Guardado en base de datos local SQLite.")
                success_count += 1

                # Sleep to respect rate limits
                time.sleep(0.3)

            except Exception as ex:
                print(f"   [ERROR] Excepcion durante la inyeccion de la fila: {ex}")
                error_count += 1
                db_conn.rollback()

    db_conn.close()

    print("\n" + "="*50)
    print("📋 RESUMEN DE MIGRACION MASIVA:")
    print(f"  • Filas procesadas: {processed_count}")
    print(f"  • Oportunidades creadas con éxito: {success_count}")
    print(f"  • Edificios excluidos (ya existentes): {exclude_count}")
    print(f"  • Errores durante el procesamiento: {error_count}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()

