import os
import sys
import json
import requests

# Add project root to sys.path
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

# List of projects to check (Group 1 from user)
LIST_CHECK = [
    "EDIFICIO ONTARIO 156",
    "EDIFICIO PROGRESO ( BLOCK A,B )",
    "EDIFICIO MIGUEL GRAU 210 ( BLOCK A,B )",
    "EDIFICIO MARISCAL CASTILLA 232",
    "EDIFICIO FAISANES II",
    "EDIFICIO TERAN 576",
    "EDIFICIO TENDERINI 194",
    "EDIFICIO PASEO DE LA REPUBLICA 1542",
    "EDIFICIO URUGUAY 106 - 112",
    "EDIFICIO MORRO 570",
    "EDIFICIO SAN TADEO III",
    "EDIFICIO CANO (MARKO SAC)",
    "EDIFICIO MALECON GRAU 243",
    "EDIFICO ADOLFO VIERA",
    "EDIFICIO PUERTO RICO",
    "EDIFICIO MELLET 252",
    "EDIFICIO COSTA SUR 240",
    "EDIFICIO CARLOS MELET 534-538 URB SAN JUDAS TADEO",
    "EDIFICIO BOLIVAR 969",
    "EDIFICIO ARTIGAS 571",
    "EDIFICIO CARLOTA II",
    "EDIFICIO LORETO 246",
    "RESIDENCIAL ION 160",
    "SENDA DORADA BLOCK 2",
    "EDIFICIO AMADOR MERINO",
    "EDIFICIO VIRREY TOLEDO 330"
]

def main():
    env = load_env_manually()
    GHL_TOKEN = env.get("GHL_ACCESS_TOKEN", "pit-91efad56-ae58-41d7-85f6-6b66504b7e16")
    LOCATION_ID = env.get("GHL_LOCATION_ID", "dHdydlGzW0HODg6XDQe7")
    
    os.environ["GHL_ACCESS_TOKEN"] = GHL_TOKEN
    os.environ["GHL_LOCATION_ID"] = LOCATION_ID
    
    headers_contacts = {
        "Authorization": f"Bearer {GHL_TOKEN}",
        "Version": "2021-07-28",
        "Content-Type": "application/json"
    }
    
    # Get custom field ID for cf_tipo_ingreso
    from app.utils.helpers import obtener_mapa_keys_a_ids
    mapa = obtener_mapa_keys_a_ids()
    id_tipo_ingreso = mapa.get("cf_tipo_ingreso")
    print(f"Custom Field ID for cf_tipo_ingreso: {id_tipo_ingreso}")
    
    print("Fetching all contacts from GHL...")
    contacts = []
    url = "https://services.leadconnectorhq.com/contacts/"
    params = {"locationId": LOCATION_ID, "limit": 100}
    
    while url:
        resp = requests.get(url, headers=headers_contacts, params=params)
        if resp.status_code != 200:
            print(f"Error fetching contacts: {resp.status_code} - {resp.text}")
            break
        data = resp.json()
        items = data.get("contacts", [])
        contacts.extend(items)
        meta = data.get("meta", {})
        url = meta.get("nextPageUrl")
        params = None
        
    print(f"Total contacts fetched: {len(contacts)}")
    
    results = []
    
    # Let's match contacts by name
    for proj_name in LIST_CHECK:
        clean_proj = proj_name.upper().replace("EDIFICIO", "").replace("RESIDENCIAL", "").strip()
        matched_contacts = []
        
        for c in contacts:
            c_name = f"{c.get('firstName', '')} {c.get('lastName', '')}".upper()
            if clean_proj in c_name:
                matched_contacts.append(c)
                
        if matched_contacts:
            for matched_contact in matched_contacts:
                # Extract cf_tipo_ingreso
                tipo_ingreso_val = None
                for cf in matched_contact.get("customFields", []):
                    if cf.get("id") == id_tipo_ingreso:
                        tipo_ingreso_val = cf.get("value")
                        break
                
                results.append({
                    "project_name": proj_name,
                    "found_name": f"{matched_contact.get('firstName', '')} {matched_contact.get('lastName', '')}",
                    "tags": matched_contact.get("tags", []),
                    "cf_tipo_ingreso": tipo_ingreso_val,
                    "status": "Found"
                })
        else:
            results.append({
                "project_name": proj_name,
                "status": "Not Found"
            })
            
    print("\n=== CHECKING RESULTS ===")
    for r in results:
        print(f"Project: {r['project_name']}")
        if r["status"] == "Found":
            print(f"  Name in GHL: {r['found_name']}")
            print(f"  Tags: {r['tags']}")
            print(f"  cf_tipo_ingreso: {r['cf_tipo_ingreso']}")
        else:
            print("  ❌ Not found in GHL contacts")
        print("-" * 50)
        
    # Write to a JSON file for easy processing
    with open("scripts/checked_contacts.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
