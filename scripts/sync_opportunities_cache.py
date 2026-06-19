import os
import sys
import json
import requests
from datetime import datetime

# Agregar la raiz del proyecto al sys.path para poder importar app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import get_db_connection, guardar_oportunidad_db_internal
from app.services.ficha_service import construir_datos_ficha_desde_webhook

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

headers_contacts = {
    "Authorization": f"Bearer {GHL_TOKEN}",
    "Version": "2021-07-28",
    "Content-Type": "application/json"
}

headers_opps = {
    "Authorization": f"Bearer {GHL_TOKEN}",
    "Version": "2021-04-15",
    "Content-Type": "application/json"
}

def fetch_all_pages(start_url, headers, initial_params=None):
    results = []
    url = start_url
    params = initial_params
    while url:
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"[ERROR] HTTP {resp.status_code} - {resp.text}")
            break
        data = resp.json()
        
        # El key puede ser 'contacts' u 'opportunities'
        key = "contacts" if "contacts" in url else "opportunities"
        items = data.get(key, [])
        results.extend(items)
        print(f"[FETCH] Traidos {len(items)} items. Total: {len(results)}")
        
        meta = data.get("meta", {})
        url = meta.get("nextPageUrl")
        params = None
    return results

def flatten_custom_fields(custom_fields_list, id_to_key=None):
    flat = {}
    for f in custom_fields_list or []:
        fid = f.get("id")
        key = f.get("key", "")
        val = f.get("value")
        if val is None:
            val = f.get("fieldValue")
            
        if key and key.startswith("contact."):
            key = key.split(".", 1)[1]
            
        if key:
            flat[key] = val
        if fid:
            flat[fid] = val
            if id_to_key:
                translated_key = id_to_key.get(fid)
                if translated_key:
                    flat[translated_key] = val
    return flat

def main():
    print("[INFO] Iniciando sincronizacion de oportunidades de GHL en cache SQLite...")
    
    # 1. Traer todos los contactos de GHL (para obtener customFields)
    print("[INFO] Cargando todos los contactos de GHL...")
    contacts = fetch_all_pages(
        "https://services.leadconnectorhq.com/contacts/",
        headers_contacts,
        {"locationId": LOCATION_ID, "limit": 100}
    )
    
    contacts_dict = {c["id"]: c for c in contacts}
    print(f"[INFO] Se cargaron {len(contacts_dict)} contactos en memoria.")
    
    # 2. Traer todas las oportunidades
    print("[INFO] Cargando todas las oportunidades del Pipeline...")
    opportunities = fetch_all_pages(
        "https://services.leadconnectorhq.com/opportunities/search",
        headers_opps,
        {"location_id": LOCATION_ID, "pipeline_id": PIPELINE_ID, "limit": 100}
    )
    print(f"[INFO] Se cargaron {len(opportunities)} oportunidades.")
    
    # 3. Cargar mapeo de usuarios para gestores
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    ruta_json = os.path.join(base_dir, "usuarios.json")
    mapa_usuarios = {}
    if os.path.exists(ruta_json):
        with open(ruta_json, "r", encoding="utf-8") as f:
            mapa_usuarios = json.load(f)
    user_names_by_id = {v: k for k, v in mapa_usuarios.items()}
    
    # 3.5. Cargar mapa de IDs a Claves de Custom Fields para traducción
    from app.utils.helpers import obtener_mapa_keys_a_ids
    mapa_keys_ids = obtener_mapa_keys_a_ids()
    id_to_key = {v: k for k, v in mapa_keys_ids.items() if k.startswith("cf_")}
    print(f"[INFO] Se cargaron {len(id_to_key)} custom fields de GHL para mapeo de traducción.")

    # 4. Insertar/Actualizar en SQLite
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updated_count = 0
    for opp in opportunities:
        opp_id = opp["id"]
        contact_id = opp.get("contactId")
        assigned_to = opp.get("assignedTo")
        
        contact_data = contacts_dict.get(contact_id, {})
        
        # Unificar campos del contacto y la oportunidad
        flat_fields = flatten_custom_fields(contact_data.get("customFields", []), id_to_key)
        flat_fields.update(flatten_custom_fields(opp.get("customFields", []), id_to_key))
        
        # Agregar datos base de la oportunidad
        flat_fields["opportunity_name"] = opp.get("name")
        
        # Limpiar el nombre si tiene prefijo
        opp_name = opp.get("name", "")
        if opp_name.startswith("Administracion:") or opp_name.startswith("Administración:"):
            opp_name = opp_name.split(":", 1)[1].strip()
            
        if not flat_fields.get("cf_nombre_proyecto"):
            flat_fields["cf_nombre_proyecto"] = opp_name
            
        flat_fields["cf_gestor_real"] = user_names_by_id.get(assigned_to, "Sin asignar")
        
        # Mapear a base de datos
        datos_mapeados = construir_datos_ficha_desde_webhook(flat_fields)
        
        # Asegurar distrito, urbanizacion, etc. si existen en el contacto
        if contact_data.get("city") and not datos_mapeados.get("distrito"):
            datos_mapeados["distrito"] = contact_data.get("city")
        if contact_data.get("state") and not datos_mapeados.get("provincia"):
            datos_mapeados["provincia"] = contact_data.get("state")
        if contact_data.get("address1") and not datos_mapeados.get("nombre_via"):
            datos_mapeados["nombre_via"] = contact_data.get("address1")
            
        # Insertar
        guardar_oportunidad_db_internal(cursor, opp_id, contact_id, datos_mapeados, flat_fields)
        updated_count += 1
        
    conn.commit()
    conn.close()
    
    print(f"[INFO] Sincronizacion finalizada. Se insertaron/actualizaron {updated_count} registros en la base de datos.")

if __name__ == "__main__":
    main()
