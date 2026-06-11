import os
from app.utils.helpers import obtener_session_con_retries, extraer_custom_fields_para_ghl

# Diccionario de traducción inversa para GHL
DB_COL_TO_GHL_KEY = {
    "nombre_proyecto": "cf_nombre_proyecto",
    "tipo_proyecto": "cf_tipo_proyecto",
    "fuente_origen": "cf_fuente_hunting",
    "clasificacion": "cf_clasificacion_proyecto",
    "tipo_construccion": "cf_tipo_construccion_edificio",
    "fecha_entrega_edificio": "cf_fecha_entrega_edificio_estreno",
    "fecha_termino_montantes": "cf_fecha_termino_montantes_edificio_estreno",
    "fecha_termino_mecha": "cf_fecha_termino_mecha_edificio_estreno",
    "junta_directiva": "cf_junta_directiva",
    "cargo_responsable": "cf_cargo_responsable_edificio",
    "nombre_responsable": "cf_nombre_responsable_edificio",
    "telefono_responsable": "cf_telefono_responsable_edificio",
    "correo_responsable": "cf_correo_responsable_edificio",
    "hogares_por_piso_torre1": "cf_hogares_por_piso_torre1",
    "hogares_por_piso_torre2": "cf_hogares_por_piso_torre2",
    "hogares_por_piso_torre3": "cf_hogares_por_piso_torre3",
    "visita_inspeccion_tecnica": "cf_visita_inspeccion_tecnica_win",
    "rango_horario_visita": "cf_rango_horario_visita_tecnica",
    "departamento": "cf_departamento_edificio",
    "provincia": "cf_provincia_edificio",
    "distrito": "cf_distrito",
    "urbanizacion": "cf_urbanizacion_edificio",
    "codigo_postal": "cf_codigo_postal_edificio",
    "tipo_via": "cf_tipo_via",
    "nombre_via": "cf_nombre_via",
    "numero_via": "cf_numeracion_via",
    "coordenadas": "cf_coordenadas",
    "total_torres": "cf_total_torres_proyecto",
    "total_hogares": "cf_total_hogares_proyecto",
    "nombre_torre1": "cf_nombre_torre1_proyecto",
    "pisos_torre1": "cf_pisos_torre1_proyecto",
    "hogares_torre1": "cf_hogares_torre1_proyecto",
    "nombre_torre2": "cf_nombre_torre2_proyecto",
    "pisos_torre2": "cf_pisos_torre2_proyecto",
    "hogares_torre2": "cf_hogares_torre2_proyecto",
    "nombre_torre3": "cf_nombre_torre3_proyecto",
    "pisos_torre3": "cf_pisos_torre3_proyecto",
    "hogares_torre3": "cf_hogares_torre3_proyecto",
    "clientes_interesados": "cf_cantidad_clientes_interesados",
    "nombre_canal": "cf_nombre_canal_hunting",
    "gestor": "cf_gestor_real",
    "foto_edificio": "cf_foto_edificio",
    "foto_montantes": "cf_foto_montantes"
}

def normalizar_valor_para_ghl(val):
    if not val:
        return val
    # Si es una cadena con formato DD/MM/YYYY, la convertimos a YYYY-MM-DD
    import re
    if isinstance(val, str) and re.match(r'^\d{2}/\d{2}/\d{4}$', val):
        try:
            parts = val.split('/')
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        except Exception:
            pass
    return val

def update_ghl_contact_fields(contact_id, updated_fields):
    """Sincroniza los campos modificados en el panel web de vuelta al contacto y la compañía de GHL."""
    return sync_contact_and_company_to_ghl(contact_id, updated_fields)

def sync_contact_and_company_to_ghl(contact_id, fields):
    """Consulta los detalles del contacto, actualiza sus campos principales, y crea/actualiza la compañía asociada."""
    if not contact_id:
        print("⚠️ [GHL SYNC] Falta contact_id para sincronizar.")
        return False
        
    token = os.getenv("GHL_ACCESS_TOKEN")
    location_id = os.getenv("GHL_LOCATION_ID")
    if not token or not location_id:
        print("⚠️ [GHL SYNC] Falta GHL_ACCESS_TOKEN o GHL_LOCATION_ID.")
        return False
        
    session = obtener_session_con_retries()
    headers_contact = {
        "Authorization": f"Bearer {token}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }
    headers_businesses = {
        "Authorization": f"Bearer {token}",
        "Version": "2023-02-21",
        "Content-Type": "application/json"
    }
    
    # 1. Consultamos el contacto actual para ver si ya tiene una Compañía asociada (companyId)
    company_id = None
    try:
        res_get = session.get(f"https://services.leadconnectorhq.com/contacts/{contact_id}", headers=headers_contact, timeout=20)
        if res_get.status_code == 200:
            contact_info = res_get.json().get("contact", {})
            company_id = contact_info.get("businessId") or contact_info.get("companyId")
            print(f"🔍 [GHL SYNC] ID Compañía (Business) actual: {company_id}")
    except Exception as e:
        print(f"⚠️ [GHL SYNC] Error al consultar contacto en GHL: {e}")
        
    # 2. Preparamos el payload de la Compañía (Business) y la creamos/actualizamos
    tipo_via = fields.get("tipo_via") or ""
    nombre_via = fields.get("nombre_via") or ""
    numero_via = fields.get("numero_via") or ""
    urbanizacion = fields.get("urbanizacion") or ""
    distrito = fields.get("distrito") or ""
    coordenadas = fields.get("coordenadas") or ""
    
    direccion_parts = [p for p in [tipo_via, nombre_via, numero_via, urbanizacion, distrito, coordenadas] if p]
    direccion_completa = ", ".join(direccion_parts) if direccion_parts else "No especificada"
    
    company_payload = {
        "locationId": location_id,
        "name": fields.get("nombre_proyecto") or "Proyecto sin nombre",
        "address": direccion_completa,
        "city": distrito if distrito else (fields.get("provincia") or "Lima"),
        "state": fields.get("departamento") or "Lima",
        "postalCode": fields.get("codigo_postal") or "",
        "country": "PE"
    }
    
    if fields.get("telefono_responsable"):
        company_payload["phone"] = fields["telefono_responsable"]
    if fields.get("correo_responsable"):
        company_payload["email"] = fields["correo_responsable"]
        
    new_company_id = None
    if company_id:
        # Caso A: La compañía existe, la actualizamos
        try:
            update_payload = dict(company_payload)
            update_payload.pop("locationId", None)
            print(f"🚀 [GHL SYNC] Actualizando compañía (Business) existente {company_id}: {update_payload}")
            res_comp = session.put(f"https://services.leadconnectorhq.com/businesses/{company_id}", headers=headers_businesses, json=update_payload, timeout=20)
            if res_comp.status_code == 200:
                print(f"✅ [GHL SYNC] Compañía (Business) {company_id} actualizada exitosamente.")
            else:
                print(f"❌ [GHL SYNC] Error al actualizar compañía (Business): {res_comp.text}")
        except Exception as e:
            print(f"❌ [GHL SYNC] Excepción al actualizar compañía (Business): {e}")
    else:
        # Caso B: No hay compañía, la creamos
        try:
            print(f"🚀 [GHL SYNC] Creando nueva compañía (Business) para edificio: {company_payload}")
            res_comp = session.post("https://services.leadconnectorhq.com/businesses/", headers=headers_businesses, json=company_payload, timeout=20)
            if res_comp.status_code in [200, 201]:
                resp_json = res_comp.json()
                new_company_id = resp_json.get("id") or resp_json.get("business", {}).get("id")
                print(f"✅ [GHL SYNC] Compañía (Business) creada con éxito. ID: {new_company_id}")
            else:
                print(f"❌ [GHL SYNC] Error al crear compañía (Business): {res_comp.text}")
        except Exception as e:
            print(f"❌ [GHL SYNC] Excepción al crear compañía (Business): {e}")
            
    # 3. Preparamos el payload del Contacto (Responsable)
    contact_payload = {}
    
    # Dividimos el nombre por el primer espacio
    nombre_resp = fields.get("nombre_responsable")
    if nombre_resp:
        parts = str(nombre_resp).strip().split(" ", 1)
        if len(parts) > 1:
            contact_payload["firstName"] = parts[0]
            contact_payload["lastName"] = parts[1]
        else:
            contact_payload["firstName"] = nombre_resp
            contact_payload["lastName"] = ""
            
    if "correo_responsable" in fields:
        contact_payload["email"] = fields["correo_responsable"]
    if "telefono_responsable" in fields:
        contact_payload["phone"] = fields["telefono_responsable"]
    
    # Si creamos una nueva compañía, la vinculamos al contacto
    if new_company_id:
        contact_payload["businessId"] = new_company_id
        
    # Sincronizamos campos personalizados del contacto
    ghl_raw_fields = {}
    for k, v in fields.items():
        v_normalized = normalizar_valor_para_ghl(v)
        if k in DB_COL_TO_GHL_KEY:
            ghl_raw_fields[DB_COL_TO_GHL_KEY[k]] = v_normalized
        elif k.startswith("cf_"):
            ghl_raw_fields[k] = v_normalized
            
    custom_fields = extraer_custom_fields_para_ghl(ghl_raw_fields)
    if custom_fields:
        contact_payload["customFields"] = custom_fields
        
    # Actualizamos el contacto en GHL
    contact_ok = False
    if contact_payload:
        try:
            print(f"🚀 [GHL SYNC] Actualizando contacto {contact_id}: {contact_payload}")
            res_put = session.put(f"https://services.leadconnectorhq.com/contacts/{contact_id}", headers=headers_contact, json=contact_payload, timeout=20)
            
            # Reintento por duplicado
            if res_put.status_code == 400 and "duplicated" in res_put.text.lower():
                print("⚠️ [GHL SYNC] Email/teléfono duplicado detectado. Reintentando sin email/teléfono...")
                contact_payload.pop("email", None)
                contact_payload.pop("phone", None)
                res_put = session.put(f"https://services.leadconnectorhq.com/contacts/{contact_id}", headers=headers_contact, json=contact_payload, timeout=20)
                
            if res_put.status_code == 200:
                print(f"✅ [GHL SYNC] Contacto {contact_id} actualizado exitosamente.")
                contact_ok = True
            else:
                print(f"❌ [GHL SYNC] Error al actualizar contacto: {res_put.text}")
        except Exception as e:
            print(f"❌ [GHL SYNC] Excepción al actualizar contacto: {e}")
            
    return contact_ok
