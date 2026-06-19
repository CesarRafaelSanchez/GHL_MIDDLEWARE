import requests
import time

URL_BASE = "https://webhook.novacoresac.com"

def run_tests():
    # TEST CASE A: Novacore BO
    proj_a = "GENESIS TEST NOVACORE BO 2"
    payload_a = {
        "cf_nombre_proyecto": proj_a,
        "cf_ejecutivo_principal": "BO ( Para revision si no se ecuentra su nombre)",
        "cf_tipo_ingreso": "Novacore",
        "cf_distrito": "Miraflores",
        "cf_inmobiliaria": "INMOBILIARIA FUTURA S.A.C.",
        "cf_tipo_proyecto": "NUEVO PREDIO",
        "cf_fuente_hunting": "PROPIO"
    }
    
    print(f"\n--- [TEST A] Triggering Form 1 for '{proj_a}' (Novacore + BO) ---")
    res_a = requests.post(f"{URL_BASE}/webhook-formulario1", json=payload_a, timeout=45)
    print("Status code:", res_a.status_code)
    print("Response:", res_a.text)
    
    # TEST CASE B: Futura BO
    proj_b = "GENESIS TEST FUTURA BO 2"
    payload_b = {
        "cf_nombre_proyecto": proj_b,
        "cf_ejecutivo_principal": "BO ( Para revision si no se ecuentra su nombre)",
        "cf_tipo_ingreso": "Futura",
        "cf_distrito": "Miraflores",
        "cf_inmobiliaria": "INMOBILIARIA FUTURA S.A.C.",
        "cf_tipo_proyecto": "NUEVO PREDIO",
        "cf_fuente_hunting": "PROPIO"
    }
    
    print(f"\n--- [TEST B] Triggering Form 1 for '{proj_b}' (Futura + BO) ---")
    res_b = requests.post(f"{URL_BASE}/webhook-formulario1", json=payload_b, timeout=45)
    print("Status code:", res_b.status_code)
    print("Response:", res_b.text)
    
    print("\nWaiting 5 seconds for background API syncs to complete...")
    time.sleep(5)
    
    # Verification A
    print(f"\n--- Verifying '{proj_a}' from cache API ---")
    res_ver_a = requests.get(f"{URL_BASE}/api/cache/{proj_a}")
    if res_ver_a.status_code == 200:
        data = res_ver_a.json()
        print("Project Name:", data.get("nombre_proyecto"))
        print("Gestor (Expected: Alexander Watson Huamani):", data.get("gestor"))
        print("Ejecutivo in raw_json:", data.get("cf_ejecutivo_principal"))
        print("Tipo Ingreso in raw_json:", data.get("cf_tipo_ingreso"))
    else:
        print(f"Failed to query cache API: {res_ver_a.status_code} - {res_ver_a.text}")
        
    # Verification B
    print(f"\n--- Verifying '{proj_b}' from cache API ---")
    res_ver_b = requests.get(f"{URL_BASE}/api/cache/{proj_b}")
    if res_ver_b.status_code == 200:
        data = res_ver_b.json()
        print("Project Name:", data.get("nombre_proyecto"))
        print("Gestor (Expected: Stefano Sotomarino Goche Back Office):", data.get("gestor"))
        print("Ejecutivo in raw_json:", data.get("cf_ejecutivo_principal"))
        print("Tipo Ingreso in raw_json:", data.get("cf_tipo_ingreso"))
    else:
        print(f"Failed to query cache API: {res_ver_b.status_code} - {res_ver_b.text}")

if __name__ == "__main__":
    run_tests()
