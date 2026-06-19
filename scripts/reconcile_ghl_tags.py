import os
import sys
import json
import requests
import argparse

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

LIST_ACCION_1 = [
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

# Novacore Hunter IDs from usuarios.json
IDS_NOVACORE_HUNTERS = [
    "qWzm9AoW9fPl7VGEgS0q",  # Carmen Yanagui Uribe
    "zFGLVi7kcOyO8x77eF2W",  # Karlo Gabriel Dominguez Chavez
    "PrasdeqihpR9ZJ08al7w",  # Rubén Dario Bastardo Rivera
    "yEkQ9UMQvZ7fPMLia3Du",  # Lorena Lizet Segura Solis
    "At6bmaGN4ltXo9yzQ3y7",  # Alex Aldair Correa Peralta
    "TA2HBI8oI8TTsSnTlNUF",  # Victor Enrique Urrunaga Solis
    "h1nHzZ8ROVTymjPsL6Ea",  # Mario Eugenio Murgado Blas
    "ZHEWJWubQ9JEjhD7ITCl",  # Isabel Milagros Miranda Castillo
    "GSmuJmZXsFvd5eIYADgO"   # Stephany Anthuaneth Arias Quiroz
]

ID_ALEXANDER_BO_NOVACORE = "jIX0i1eicDNv2KQDAmRq"
ID_STEFANO_BO_FUTURA = "6u8iZhDXnxp0xSp7XfDl"

def clean_project_name(name):
    return name.upper().replace("EDIFICIO", "").replace("RESIDENCIAL", "").replace("EDIFICO", "").strip()

def main():
    parser = argparse.ArgumentParser(description="Reconcile GHL Contact Tags and Owners")
    parser.add_argument("--dry-run", action="store_true", help="Simulate changes without calling GHL API")
    args = parser.parse_args()
    
    env = load_env_manually()
    GHL_TOKEN = env.get("GHL_ACCESS_TOKEN", "pit-91efad56-ae58-41d7-85f6-6b66504b7e16")
    LOCATION_ID = env.get("GHL_LOCATION_ID", "dHdydlGzW0HODg6XDQe7")
    PIPELINE_ID = env.get("PIPELINE_ID", "LPfxv2sqrrNOTtjbWZ3h")
    
    os.environ["GHL_ACCESS_TOKEN"] = GHL_TOKEN
    os.environ["GHL_LOCATION_ID"] = LOCATION_ID
    os.environ["PIPELINE_ID"] = PIPELINE_ID
    
    headers = {
        "Authorization": f"Bearer {GHL_TOKEN}",
        "Version": "2021-07-28",
        "Content-Type": "application/json"
    }
    
    # Get custom field IDs
    from app.utils.helpers import obtener_mapa_keys_a_ids
    mapa = obtener_mapa_keys_a_ids()
    id_tipo_ingreso = mapa.get("cf_tipo_ingreso")
    id_ejecutivo = mapa.get("cf_ejecutivo_principal")
    id_gestor_real = mapa.get("cf_gestor_real")
    
    print(f"[ENV] Custom Field IDs:")
    print(f"  cf_tipo_ingreso: {id_tipo_ingreso}")
    print(f"  cf_ejecutivo_principal: {id_ejecutivo}")
    print(f"  cf_gestor_real: {id_gestor_real}")
    
    print("\nFetching all contacts from GHL...")
    contacts = []
    url = "https://services.leadconnectorhq.com/contacts/"
    params = {"locationId": LOCATION_ID, "limit": 100}
    
    while url:
        resp = requests.get(url, headers=headers, params=params)
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
    
    print("\nFetching all opportunities from GHL (to match and reassign owners)...")
    opportunities = []
    opp_url = "https://services.leadconnectorhq.com/opportunities/search"
    opp_params = {"location_id": LOCATION_ID, "pipeline_id": PIPELINE_ID, "limit": 100}
    opp_headers = {
        "Authorization": f"Bearer {GHL_TOKEN}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }
    
    while opp_url:
        resp = requests.get(opp_url, headers=opp_headers, params=opp_params)
        if resp.status_code != 200:
            print(f"Error fetching opportunities: {resp.status_code} - {resp.text}")
            break
        data = resp.json()
        items = data.get("opportunities", [])
        opportunities.extend(items)
        meta = data.get("meta", {})
        opp_url = meta.get("nextPageUrl")
        opp_params = None
        
    print(f"Total opportunities fetched: {len(opportunities)}")
    
    # Map contactId to opportunity object
    contact_opp_map = {o.get("contactId"): o for o in opportunities if o.get("contactId")}
    
    clean_accion_1 = [clean_project_name(name) for name in LIST_ACCION_1]
    
    updates_fase1 = []
    updates_fase2 = []
    updates_fase3 = []
    
    # Track which contacts have already been mapped to Action 1 so they are skipped in Action 2 & 3
    handled_ids = set()
    
    # --- PHASE 1: ACTION 1 (The 26 BO contacts) ---
    print("\n=== Processing Phase 1: Action 1 (26 BO Contacts) ===")
    for c in contacts:
        c_id = c.get("id")
        c_name = f"{c.get('firstName', '')} {c.get('lastName', '')}".upper()
        
        # Check match
        matched_proj = None
        for orig_name, clean_name in zip(LIST_ACCION_1, clean_accion_1):
            if clean_name in c_name:
                matched_proj = orig_name
                break
                
        if matched_proj:
            handled_ids.add(c_id)
            
            # Tags modification
            orig_tags = c.get("tags", [])
            tags_lower = [t.lower().strip() for t in orig_tags]
            
            # Remove "⚠️ usuario no encontrado" and variations
            new_tags = [t for t in orig_tags if "usuario no encontrado" not in t.lower()]
            
            # Add "novacore" and "BO Revision" if missing
            if "novacore" not in tags_lower:
                new_tags.append("novacore")
            if "bo revision" not in tags_lower:
                new_tags.append("BO Revision")
                
            opp_data = contact_opp_map.get(c_id)
            opp_id = opp_data.get("id") if opp_data else None
                
            updates_fase1.append({
                "id": c_id,
                "name": c_name,
                "opp_id": opp_id,
                "original_tags": orig_tags,
                "new_tags": new_tags,
                "owner_id": ID_ALEXANDER_BO_NOVACORE,
                "custom_fields": [
                    {"id": id_tipo_ingreso, "value": "Novacore"},
                    {"id": id_ejecutivo, "value": "Alexander Watson Huamani"},
                    {"id": id_gestor_real, "value": "Alexander Watson Huamani"}
                ]
            })
            print(f"Found Action 1 Match: '{c_name}' (Project: '{matched_proj}', Opp ID: '{opp_id}')")
            
    # --- PHASE 2: ACTION 2 (39 contacts with novacore tag and old origin) ---
    print("\n=== Processing Phase 2: Action 2 (novacore tag + old origin) ===")
    for c in contacts:
        c_id = c.get("id")
        if c_id in handled_ids:
            continue
            
        orig_tags = c.get("tags", [])
        tags_lower = [t.lower().strip() for t in orig_tags]
        
        has_nova = "novacore" in tags_lower
        if has_nova:
            print(f"Debug Action 2: '{c.get('firstName', '')} {c.get('lastName', '')}'")
            print(f"  tags: {orig_tags}")
            
        has_old_origen = any("origen:hunting(futuraynovacore)" in t.replace(" ", "").lower() for t in tags_lower)
        has_new_origen = any("origen:novacore" in t.replace(" ", "").lower() for t in tags_lower)
        
        # Check custom field value
        tipo_ingreso_val = None
        for cf in c.get("customFields", []):
            if cf.get("id") == id_tipo_ingreso:
                tipo_ingreso_val = cf.get("value")
        needs_update = tipo_ingreso_val != "Novacore"
        
        if has_nova:
            print(f"  has_old_origen: {has_old_origen} | has_new_origen: {has_new_origen} | tipo_ingreso_val: {tipo_ingreso_val} | needs_update: {needs_update}")
            
        if has_nova and (has_old_origen or (has_new_origen and needs_update)):
            handled_ids.add(c_id)
            
            # Modify tags
            new_tags = [t for t in orig_tags if "hunting (futura y novacore)" not in t.lower()]
            if "origen: novacore" not in [t.lower() for t in new_tags]:
                new_tags.append("origen: novacore")
                
            updates_fase2.append({
                "id": c_id,
                "name": f"{c.get('firstName', '')} {c.get('lastName', '')}",
                "original_tags": orig_tags,
                "new_tags": new_tags,
                "custom_fields": [
                    {"id": id_tipo_ingreso, "value": "Novacore"}
                ]
            })
            
    # --- PHASE 3: ACTION 3 (Option A - separation by hunter for all remaining with old origin) ---
    print("\n=== Processing Phase 3: Action 3 (Separation by Hunter) ===")
    for c in contacts:
        c_id = c.get("id")
        if c_id in handled_ids:
            continue
            
        orig_tags = c.get("tags", [])
        tags_lower = [t.lower().strip() for t in orig_tags]
        has_old_origen = any("origen:hunting(futuraynovacore)" in t.replace(" ", "").lower() for t in tags_lower)
        has_futura = "futura" in tags_lower or any("origen:futura" in t.replace(" ", "").lower() for t in tags_lower)
        
        # Check custom field value
        tipo_ingreso_val = None
        for cf in c.get("customFields", []):
            if cf.get("id") == id_tipo_ingreso:
                tipo_ingreso_val = cf.get("value")
        needs_update = tipo_ingreso_val != "Futura"
        
        if has_old_origen or (has_futura and needs_update):
            owner_id = c.get("assignedTo")
            is_novacore_owner = (owner_id in IDS_NOVACORE_HUNTERS) or (owner_id == ID_ALEXANDER_BO_NOVACORE)
            
            # If we are matching because of has_futura, we default to Futura team
            if has_futura and not has_old_origen:
                team = "Futura"
            else:
                team = "Novacore" if is_novacore_owner else "Futura"
                
            new_tags = [t for t in orig_tags if "hunting (futura y novacore)" not in t.lower()]
            
            if team == "Novacore":
                # Classify as Novacore
                if "origen: novacore" not in [t.lower() for t in new_tags]:
                    new_tags.append("origen: novacore")
                if "novacore" not in [t.lower() for t in new_tags]:
                    new_tags.append("novacore")
                    
                updates_fase3.append({
                    "id": c_id,
                    "name": f"{c.get('firstName', '')} {c.get('lastName', '')}",
                    "team": "Novacore",
                    "owner_id": owner_id,
                    "original_tags": orig_tags,
                    "new_tags": new_tags,
                    "custom_fields": [
                        {"id": id_tipo_ingreso, "value": "Novacore"}
                    ]
                })
            else:
                # Classify as Futura
                if "origen: futura" not in [t.lower() for t in new_tags]:
                    new_tags.append("origen: futura")
                if "futura" not in [t.lower() for t in new_tags]:
                    new_tags.append("futura")
                    
                updates_fase3.append({
                    "id": c_id,
                    "name": f"{c.get('firstName', '')} {c.get('lastName', '')}",
                    "team": "Futura",
                    "owner_id": owner_id,
                    "original_tags": orig_tags,
                    "new_tags": new_tags,
                    "custom_fields": [
                        {"id": id_tipo_ingreso, "value": "Futura"}
                    ]
                })

                
    # --- PRINT SUMMARY ---
    print("\n================== SUMMARY OF PENDING CHANGES ==================")
    print(f"Action 1 Updates: {len(updates_fase1)}")
    print(f"Action 2 Updates: {len(updates_fase2)}")
    print(f"Action 3 Updates (Option A): {len(updates_fase3)}")
    novacore_f3 = len([u for u in updates_fase3 if u["team"] == "Novacore"])
    futura_f3 = len([u for u in updates_fase3 if u["team"] == "Futura"])
    print(f"  -> Novacore classified: {novacore_f3}")
    print(f"  -> Futura classified: {futura_f3}")
    
    if args.dry_run:
        print("\n[DRY RUN] Simulating updates in GHL...")
        print("\nSample Action 1 Update:")
        if updates_fase1:
            u = updates_fase1[0]
            print(f"  ID: {u['id']}")
            print(f"  Name: {u['name']}")
            print(f"  Original Tags: {u['original_tags']}")
            print(f"  New Tags: {u['new_tags']}")
            print(f"  New Owner: {u['owner_id']}")
            print(f"  Custom Fields: {u['custom_fields']}")
            
        print("\nSample Action 2 Update:")
        if updates_fase2:
            u = updates_fase2[0]
            print(f"  ID: {u['id']}")
            print(f"  Name: {u['name']}")
            print(f"  Original Tags: {u['original_tags']}")
            print(f"  New Tags: {u['new_tags']}")
            print(f"  Custom Fields: {u['custom_fields']}")
            
        print("\nSample Action 3 Update:")
        if updates_fase3:
            u = updates_fase3[0]
            print(f"  ID: {u['id']}")
            print(f"  Name: {u['name']}")
            print(f"  Owner: {u['owner_id']}")
            print(f"  Classified As: {u['team']}")
            print(f"  Original Tags: {u['original_tags']}")
            print(f"  New Tags: {u['new_tags']}")
            print(f"  Custom Fields: {u['custom_fields']}")
            
        print("\n[DRY RUN] Finished. No API changes were made.")
        return
        
    # --- EXECUTE ACTUAL UPDATES ---
    print("\n🚀 Executing actual GHL updates...")
    
    all_updates = []
    for u in updates_fase1:
        all_updates.append((u, "Action 1"))
    for u in updates_fase2:
        all_updates.append((u, "Action 2"))
    for u in updates_fase3:
        all_updates.append((u, "Action 3"))
        
    success_count = 0
    error_count = 0
    
    import time
    for i, (u, phase) in enumerate(all_updates, 1):
        c_id = u["id"]
        print(f"[{i}/{len(all_updates)}] Updating contact {u['name']} ({phase})...")
        
        payload = {
            "tags": u["new_tags"],
            "customFields": u["custom_fields"]
        }
        if "owner_id" in u:
            payload["assignedTo"] = u["owner_id"]
            
        try:
            res = requests.put(
                f"https://services.leadconnectorhq.com/contacts/{c_id}",
                headers=headers,
                json=payload
            )
            if res.status_code in [200, 201]:
                print(f"  ✅ Contact updated successfully.")
                success_count += 1
            else:
                print(f"  ❌ Error updating contact: {res.status_code} - {res.text}")
                error_count += 1
        except Exception as e:
            print(f"  ❌ Exception updating contact: {e}")
            error_count += 1
            
        # Update Opportunity assignedTo owner in GHL if applicable
        if u.get("opp_id") and "owner_id" in u:
            opp_id = u["opp_id"]
            print(f"  -> Updating owner for opportunity: {opp_id}")
            opp_headers = {
                "Authorization": f"Bearer {GHL_TOKEN}",
                "Version": "2021-04-15",
                "Content-Type": "application/json"
            }
            try:
                res_opp = requests.put(
                    f"https://services.leadconnectorhq.com/opportunities/{opp_id}",
                    headers=opp_headers,
                    json={"assignedTo": u["owner_id"]}
                )
                if res_opp.status_code in [200, 201]:
                    print(f"    ✅ Opportunity owner updated successfully.")
                else:
                    print(f"    ❌ Error updating opportunity owner: {res_opp.status_code} - {res_opp.text}")
            except Exception as e:
                print(f"    ❌ Exception updating opportunity owner: {e}")
            
        # Rate limit compliance (4 requests per second limit in GHL)
        time.sleep(0.25)
        
    print(f"\nReconciliation finished: {success_count} succeeded, {error_count} failed.")

if __name__ == "__main__":
    main()
