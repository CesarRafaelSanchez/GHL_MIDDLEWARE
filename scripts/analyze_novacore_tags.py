import os
import sys
import json
import requests

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

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))

def main():
    env = load_env_manually()
    GHL_TOKEN = env.get("GHL_ACCESS_TOKEN", "pit-91efad56-ae58-41d7-85f6-6b66504b7e16")
    LOCATION_ID = env.get("GHL_LOCATION_ID", "dHdydlGzW0HODg6XDQe7")
    
    headers = {
        "Authorization": f"Bearer {GHL_TOKEN}",
        "Version": "2021-07-28",
        "Content-Type": "application/json"
    }
    
    print("Fetching all contacts from GHL...")
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
    
    has_novacore_tag = []
    has_origen_novacore_tag = []
    
    for c in contacts:
        tags = [t.lower().strip() for t in c.get("tags", [])]
        name = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
        cid = c.get("id")
        
        # Check for "novacore" tag
        has_nova = "novacore" in tags
        # Check for "origen: novacore" or variations like "origen:novacore"
        has_orig_nova = any("origen:novacore" in t.replace(" ", "") for t in tags)
        
        c_info = {
            "id": cid,
            "name": name,
            "tags": c.get("tags", [])
        }
        
        if has_nova:
            has_novacore_tag.append(c_info)
        if has_orig_nova:
            has_origen_novacore_tag.append(c_info)
            
    print(f"\nContacts with 'novacore' tag: {len(has_novacore_tag)}")
    print(f"Contacts with 'origen: novacore' tag: {len(has_origen_novacore_tag)}")
    
    # Find mismatches
    ids_novacore = {c["id"] for c in has_novacore_tag}
    ids_origen = {c["id"] for c in has_origen_novacore_tag}
    
    only_in_novacore = [c for c in has_novacore_tag if c["id"] not in ids_origen]
    only_in_origen = [c for c in has_origen_novacore_tag if c["id"] not in ids_novacore]
    
    # Generate report string
    report_lines = []
    report_lines.append(f"ANALYSIS REPORT: NOVACORE TAGS CONFLICTS")
    report_lines.append(f"Total contacts: {len(contacts)}")
    report_lines.append(f"Contacts with 'novacore': {len(has_novacore_tag)}")
    report_lines.append(f"Contacts with 'origen: novacore': {len(has_origen_novacore_tag)}")
    
    report_lines.append(f"\n--- Contacts that have 'novacore' but DO NOT have 'origen: novacore' ({len(only_in_novacore)}) ---")
    for i, c in enumerate(only_in_novacore, 1):
        report_lines.append(f"{i}. {c['name']} (ID: {c['id']})")
        report_lines.append(f"   Tags: {c['tags']}")
        
    report_lines.append(f"\n--- Contacts that have 'origen: novacore' but DO NOT have 'novacore' ({len(only_in_origen)}) ---")
    for i, c in enumerate(only_in_origen, 1):
        report_lines.append(f"{i}. {c['name']} (ID: {c['id']})")
        report_lines.append(f"   Tags: {c['tags']}")
        
    # Write to local file with utf-8 encoding
    report_content = "\n".join(report_lines)
    report_path = os.path.join(os.path.dirname(__file__), "analysis_novacore_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"\nReport written to {report_path}")
    
    # Safely print summary to stdout
    safe_print(f"\n--- Summary of Mismatches (Only 'novacore'): {len(only_in_novacore)} ---")
    for c in only_in_novacore[:5]:
        safe_print(f"- {c['name']} | Tags: {c['tags']}")
    if len(only_in_novacore) > 5:
        safe_print("... (see report file for full list)")
        
    safe_print(f"\n--- Summary of Mismatches (Only 'origen: novacore'): {len(only_in_origen)} ---")
    for c in only_in_origen[:5]:
        safe_print(f"- {c['name']} | Tags: {c['tags']}")
    if len(only_in_origen) > 5:
        safe_print("... (see report file for full list)")

if __name__ == "__main__":
    main()
