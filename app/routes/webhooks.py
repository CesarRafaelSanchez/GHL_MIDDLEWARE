import os
import json
import hmac
import hashlib
from flask import Blueprint, request, jsonify

# Importamos tus herramientas y servicios modularizados
from app.utils.helpers import obtener_campo, extraer_custom_fields_para_ghl, obtener_session_con_retries, obtener_mapa_keys_a_ids
from app.services.email_smtp import enviar_correo_win, enviar_correo_ficha_datos_win
from app.services.ficha_service import (
    guardar_datos_ficha_en_cache,
    recuperar_datos_ficha_de_cache,
    construir_datos_ficha_desde_webhook,
    limpiar_nombre_archivo,
    obtener_primera_url,
    descargar_imagen,
    generar_excel_ficha_datos
)

# Creamos la sesión robusta con reintentos para evitar caídas por errores 520/5xx de Cloudflare/GHL
requests = obtener_session_con_retries()

# 1. CREAMOS EL BLUEPRINT
webhooks_bp = Blueprint('webhooks', __name__)

# =========================================================
# Credenciales y Configuración GHL
# =========================================================
GHL_TOKEN = os.getenv("GHL_ACCESS_TOKEN")
LOCATION_ID = os.getenv("GHL_LOCATION_ID")
PIPELINE_ID = os.getenv("PIPELINE_ID")
STAGE_FORM_1 = os.getenv("STAGE_FORM_1_COMPLETADO")
STAGE_FORM_2 = os.getenv("STAGE_FORM_2_COMPLETADO")

HEADERS_GHL = {
    "Authorization": f"Bearer {GHL_TOKEN}",
    "Version": "2021-04-15",
    "Content-Type": "application/json"
}

def cargar_usuarios_ghl():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ruta_json = os.path.join(base_dir, "usuarios.json")
    try:
        with open(ruta_json, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error cargando usuarios.json: {e}", flush=True)
        return {}

ID_STEFANO = "6u8iZhDXnxp0xSp7XfDl"

EQUIPO_NOVACORE = [
    "Carmen Yanagui Uribe",
    "Karlo Gabriel Dominguez Chavez",
    "Rubén Dario Bastardo Rivera",
    "Lorena Lizet Segura Solis",
    "Alex Aldair Correa Peralta",
    "Victor Enrique Urrunaga Solis",
    "Mario Eugenio Murgado Blas",
    "Isabel Milagros Miranda Castillo",
    "Stephany Anthuaneth Arias Quiroz"
]


# =========================================================
# RUTA 1: EL GÉNESIS (Formulario de Asignación)
# =========================================================
@webhooks_bp.route('/webhook-formulario1', methods=['POST'])
def webhook_formulario1():
    datos = request.json
    if not datos:
        return jsonify({"error": "No data"}), 400

    nombre_proyecto_raw = obtener_campo(datos, "cf_nombre_proyecto")
    if not nombre_proyecto_raw:
        return jsonify({"error": "Falta el nombre del proyecto"}), 400

    nombre_proyecto = str(nombre_proyecto_raw).strip().upper()
    custom_fields = extraer_custom_fields_para_ghl(datos)

    ejecutivo_str = str(obtener_campo(datos, "cf_ejecutivo_principal")).upper()
    tipo_ingreso = str(obtener_campo(datos, "cf_tipo_ingreso")).capitalize()
    distrito = str(obtener_campo(datos, "cf_distrito")).capitalize()

    print(f"🚀 [FORM 1] Iniciando creación Génesis para: {nombre_proyecto}")

    opp_existente = None
    try:
        res_search = requests.get(
            f"https://services.leadconnectorhq.com/opportunities/search?location_id={LOCATION_ID}&q={nombre_proyecto}",
            headers=HEADERS_GHL
        )
        if res_search.status_code == 200:
            resultados = res_search.json().get("opportunities", [])
            opp_existente = next((opp for opp in resultados if opp.get("pipelineId") == PIPELINE_ID), None)
    except Exception as e:
        print(f"⚠️ [FORM 1] Error o timeout al buscar oportunidad '{nombre_proyecto}': {e}. Continuamos con la creación...")
    if opp_existente:
        print(f"⚠️ [FORM 1] El proyecto '{nombre_proyecto}' ya existe. Evitando creación duplicada.")
        return jsonify({"status": "ignored", "message": "El proyecto ya existe"}), 200

    mapa_usuarios = cargar_usuarios_ghl()
    owner_id = None
    ejecutivo_limpio = ejecutivo_str.strip().upper()

    # 1. Determinar el Tipo de Ingreso y agregar tags de Origen correspondientes
    tipo_ingreso_raw = str(obtener_campo(datos, "cf_tipo_ingreso")).strip().upper()
    
    tag_origen = None
    if "FUTURA" in tipo_ingreso_raw:
        tag_origen = "FUTURA"
    elif "NOVACORE" in tipo_ingreso_raw:
        tag_origen = "NOVACORE"
    elif "REFERIDO" in tipo_ingreso_raw:
        tag_origen = "REFERIDO"

    tags_contacto = [
        "NUEVO HUNTING",
        f"Origen: {tipo_ingreso}" if tipo_ingreso != "None" else "Origen: No Especificado",
        f"Distrito: {distrito}" if distrito != "None" else "Distrito: No Especificado",
        "Trigger_Notificacion_BO"
    ]
    
    if tag_origen:
        tags_contacto.append(tag_origen)

    # 2. Determinar el Ejecutivo y manejo de Fallback BO / Asignación
    is_bo_fallback = "BO (" in ejecutivo_limpio

    if is_bo_fallback:
        if tag_origen == "NOVACORE":
            owner_id = "jIX0i1eicDNv2KQDAmRq" # Alexander Watson Huamani (BO Novacore)
            ejecutivo_str = "Alexander Watson Huamani"
            print(f"💼 [FORM 1] Ejecutivo BO detectado para Novacore. Asignando a Alexander Watson Huamani.")
        else:
            owner_id = ID_STEFANO # Stefano Sotomarino Goche (BO Futura / Fallback)
            ejecutivo_str = "Stefano Sotomarino Goche Back Office"
            print(f"💼 [FORM 1] Ejecutivo BO detectado. Asignando a Stefano Sotomarino Goche.")
        tags_contacto.append("BO Revision")
    else:
        # Búsqueda tolerante en usuarios.json
        for nombre_key, ghl_id in mapa_usuarios.items():
            nombre_key_limpio = nombre_key.strip().upper()
            if nombre_key_limpio == ejecutivo_limpio or ejecutivo_limpio in nombre_key_limpio or nombre_key_limpio in ejecutivo_limpio:
                owner_id = ghl_id
                # Corregimos el ejecutivo_str para que tenga el casing correcto del JSON
                ejecutivo_str = nombre_key 
                break

        if not owner_id:
            print(f"⚠️ [FORM 1] Ejecutivo '{ejecutivo_str}' no encontrado en usuarios.json. Asignando a Fallback (Stefano).")
            owner_id = ID_STEFANO
            tags_contacto.append("⚠️ Usuario No Encontrado")
        else:
            # Fallback secundario si el origen no se seleccionó en el dropdown, pero el ejecutivo es de Novacore
            if not tag_origen:
                for miembro in EQUIPO_NOVACORE:
                    if miembro.lower() in ejecutivo_str.lower() or ejecutivo_str.lower() in miembro.lower():
                        tags_contacto.append("NOVACORE")
                        break

    # 3. Sincronizar el Ejecutivo y Gestor Real resueltos en customFields para GHL
    mapa_ids = obtener_mapa_keys_a_ids()
    id_gestor_real = mapa_ids.get("cf_gestor_real") or "cf_gestor_real"
    id_ejecutivo = mapa_ids.get("cf_ejecutivo_principal") or "cf_ejecutivo_principal"
    
    # Remove existing entries for these two custom fields if they exist
    custom_fields = [cf for cf in custom_fields if cf.get("id") not in [id_gestor_real, id_ejecutivo]]
    # Add resolved/mapped values
    custom_fields.append({"id": id_ejecutivo, "value": ejecutivo_str})
    custom_fields.append({"id": id_gestor_real, "value": ejecutivo_str})

    contact_id = datos.get("contact_id") or datos.get("contact", {}).get("id")

    if contact_id:
        res_contact = requests.put(
            f"https://services.leadconnectorhq.com/contacts/{contact_id}",
            headers=HEADERS_GHL,
            json={
                "firstName": "Administración:",
                "lastName": nombre_proyecto,
                "assignedTo": owner_id,
                "tags": tags_contacto,
                "customFields": custom_fields
            }
        )
    else:
        res_contact = requests.post(
            "https://services.leadconnectorhq.com/contacts/",
            headers=HEADERS_GHL,
            json={
                "locationId": LOCATION_ID,
                "firstName": "Administración:",
                "lastName": nombre_proyecto,
                "assignedTo": owner_id,
                "tags": tags_contacto,
                "customFields": custom_fields
            }
        )
        contact_id = res_contact.json().get("contact", {}).get("id")

    if res_contact.status_code not in [200, 201]:
        print(f"❌ Error al procesar contacto: {res_contact.text}")
        return jsonify({"error": "Fallo al procesar contacto"}), 500

    res_company = requests.post(
        "https://services.leadconnectorhq.com/companies/",
        headers=HEADERS_GHL,
        json={"locationId": LOCATION_ID, "name": nombre_proyecto}
    )
    company_id = res_company.json().get("company", {}).get("id") if res_company.status_code in [200, 201] else None

    if company_id:
        requests.post(f"https://services.leadconnectorhq.com/contacts/{contact_id}/companies/{company_id}", headers=HEADERS_GHL)

    res_opp = requests.post(
        "https://services.leadconnectorhq.com/opportunities/",
        headers=HEADERS_GHL,
        json={
            "locationId": LOCATION_ID,
            "contactId": contact_id,
            "pipelineId": PIPELINE_ID,
            "pipelineStageId": STAGE_FORM_1,
            "name": nombre_proyecto,
            "status": "open",
            "assignedTo": owner_id,
            "customFields": custom_fields
        }
    )

    if res_opp.status_code not in [200, 201]:
        print(f"❌ Error al crear la oportunidad en GHL: {res_opp.text}")
        return jsonify({"error": "Fallo al crear oportunidad"}), 500

    opp_id = res_opp.json().get("opportunity", {}).get("id")
    if opp_id:
        requests.post(
            f"https://services.leadconnectorhq.com/opportunities/{opp_id}/followers",
            headers=HEADERS_GHL,
            json={"followers": [ID_STEFANO]}
        )
        
        try:
            datos_db = dict(datos)
            datos_db["opportunity_name"] = nombre_proyecto
            datos_db["cf_nombre_proyecto"] = nombre_proyecto
            datos_db["cf_gestor_real"] = ejecutivo_str
            datos_db["cf_ejecutivo_principal"] = ejecutivo_str
            
            from app.database import guardar_oportunidad_db
            from app.services.ficha_service import construir_datos_ficha_desde_webhook
            datos_mapeados = construir_datos_ficha_desde_webhook(datos_db)
            
            # Mapear campos de dirección si están presentes en la entrada
            if obtener_campo(datos, "cf_distrito"):
                datos_mapeados["distrito"] = obtener_campo(datos, "cf_distrito")
            if obtener_campo(datos, "cf_tipo_via"):
                datos_mapeados["tipo_via"] = obtener_campo(datos, "cf_tipo_via")
            if obtener_campo(datos, "cf_nombre_via"):
                datos_mapeados["nombre_via"] = obtener_campo(datos, "cf_nombre_via")
            if obtener_campo(datos, "cf_numeracion_via"):
                datos_mapeados["numero_via"] = obtener_campo(datos, "cf_numeracion_via")
            if obtener_campo(datos, "cf_coordenadas"):
                datos_mapeados["coordenadas"] = obtener_campo(datos, "cf_coordenadas")
                
            # Sobrescribimos el gestor con el ejecutivo_str mapeado
            datos_mapeados["gestor"] = ejecutivo_str
                
            guardar_oportunidad_db(opp_id, contact_id, datos_mapeados, datos_db)
            print(f"💾 [DB SAVE] Oportunidad Genesis guardada en SQLite: {nombre_proyecto}", flush=True)
        except Exception as e:
            print(f"⚠️ [DB SAVE] Error guardando oportunidad Genesis: {e}", flush=True)

    print(f"✅ [FORM 1] Setup completado. Asignado a: {ejecutivo_str}")
    return jsonify({"status": "success"}), 200


# =========================================================
# RUTA 2: LA ACTUALIZACIÓN (Formulario de Ficha de Datos)
# =========================================================
@webhooks_bp.route('/webhook-formulario2', methods=['POST'])
def webhook_formulario2():
    datos = request.json
    if not datos: return jsonify({"error": "No data"}), 400

    nombre_proyecto_raw = obtener_campo(datos, "cf_nombre_proyecto")
    if not nombre_proyecto_raw:
        return jsonify({"error": "Falta el nombre del proyecto"}), 400

    nombre_proyecto = str(nombre_proyecto_raw).strip().upper()
    print(f"🔍 [FORM 2] Buscando oportunidad para actualizar: '{nombre_proyecto}'")

    res_search = requests.get(f"https://services.leadconnectorhq.com/opportunities/search?location_id={LOCATION_ID}&q={nombre_proyecto}", headers=HEADERS_GHL)
    resultados = res_search.json().get("opportunities", []) if res_search.status_code == 200 else []
    oportunidad_correcta = next((opp for opp in resultados if opp.get("pipelineId") == PIPELINE_ID), None)

    if not oportunidad_correcta:
        print(f"⚠️ [FORM 2] Oportunidad no encontrada.")
        return jsonify({"error": "Oportunidad no encontrada"}), 404

    if oportunidad_correcta.get("pipelineStageId") == STAGE_FORM_2:
        print(f"⚠️ [FORM 2] La ficha de '{nombre_proyecto}' ya fue procesada previamente.")
        return jsonify({"status": "ignored", "message": "Ficha ya procesada"}), 200

    opp_id = oportunidad_correcta.get("id")
    contacto_original_id = oportunidad_correcta.get("contactId")
    custom_fields_nuevos = extraer_custom_fields_para_ghl(datos)

    # Generamos enlace de edición y lo añadimos a los custom fields
    enlace_edicion = generar_enlace_edicion(opp_id)
    mapa_ids = obtener_mapa_keys_a_ids()
    field_id_enlace = mapa_ids.get("cf_enlace_edicion_ficha") or "cf_enlace_edicion_ficha"
    
    custom_fields_nuevos = [cf for cf in custom_fields_nuevos if cf.get("id") != field_id_enlace]
    custom_fields_nuevos.append({"id": field_id_enlace, "value": enlace_edicion})

    contacto_fantasma_id = datos.get("contact_id") or datos.get("contact", {}).get("id")
    eliminar_fantasma = False
    if contacto_fantasma_id and contacto_fantasma_id != contacto_original_id:
        print(f"👻 [FORM 2] Contacto fantasma detectado para eliminación posterior: {contacto_fantasma_id}")
        eliminar_fantasma = True

    # --- DESCARGA INMEDIATA DE IMÁGENES ANTES DE ELIMINAR EL CONTACTO FANTASMA ---
    url_foto_edificio = obtener_primera_url(obtener_campo(datos, "cf_foto_edificio"))
    url_foto_montantes = obtener_primera_url(obtener_campo(datos, "cf_foto_montantes"))
    
    nombre_limpio = limpiar_nombre_archivo(nombre_proyecto)
    print(f"📸 [FORM 2] Descargando imágenes previas a la eliminación del fantasma...")
    foto_edificio_path = descargar_imagen(url_foto_edificio, f"{nombre_limpio}_foto_edificio")
    foto_montantes_path = descargar_imagen(url_foto_montantes, f"{nombre_limpio}_foto_montantes")

    # Almacenamos las rutas locales en datos para que persistan en caché
    datos["foto_edificio_path"] = foto_edificio_path
    datos["foto_montantes_path"] = foto_montantes_path
    # ----------------------------------------------------------------------------

    resp_nombre = obtener_campo(datos, "cf_nombre_responsable_edificio") or ""
    resp_tel = obtener_campo(datos, "cf_telefono_responsable_edificio") or ""
    resp_correo = obtener_campo(datos, "cf_correo_responsable_edificio") or ""
    distrito = obtener_campo(datos, "cf_distrito") or ""
    urb = obtener_campo(datos, "cf_urbanizacion_edificio") or ""
    tipo_via = obtener_campo(datos, "cf_tipo_via") or ""
    nombre_via = obtener_campo(datos, "cf_nombre_via") or ""
    coords = obtener_campo(datos, "cf_coordenadas") or ""
    direccion_completa = f"{tipo_via} {nombre_via}, {urb}, {distrito} {coords}".strip(" ,")
    ciudad = obtener_campo(datos, "cf_departamento_edificio") or "Lima"
    estado = obtener_campo(datos, "cf_provincia_edificio") or "Lima"
    codigo_postal = obtener_campo(datos, "cf_codigo_postal_edificio") or ""

    res_get_contact = requests.get(f"https://services.leadconnectorhq.com/contacts/{contacto_original_id}", headers=HEADERS_GHL)
    company_id = (res_get_contact.json().get("contact", {}).get("businessId") or res_get_contact.json().get("contact", {}).get("companyId")) if res_get_contact.status_code == 200 else None

    # Preparamos payload de la compañía (Business)
    company_payload = {
        "locationId": LOCATION_ID,
        "name": nombre_proyecto,
        "address": direccion_completa,
        "city": distrito if distrito else (ciudad if ciudad else "Lima"),
        "state": estado if estado else "Lima",
        "postalCode": codigo_postal,
        "country": "PE"
    }
    if resp_tel:
        company_payload["phone"] = resp_tel
    if resp_correo:
        company_payload["email"] = resp_correo

    HEADERS_GHL_BUSINESSES = {
        "Authorization": f"Bearer {GHL_TOKEN}",
        "Version": "2023-02-21",
        "Content-Type": "application/json"
    }

    new_company_id = None
    if company_id:
        # Actualizamos la compañía (Business) existente
        try:
            update_payload = dict(company_payload)
            update_payload.pop("locationId", None)
            requests.put(
                f"https://services.leadconnectorhq.com/businesses/{company_id}",
                headers=HEADERS_GHL_BUSINESSES,
                json=update_payload
            )
        except Exception as e:
            print(f"⚠️ [FORM 2] Error al actualizar compañía (Business): {e}")
    else:
        # Creamos la compañía nueva (Business)
        try:
            res_comp = requests.post(
                "https://services.leadconnectorhq.com/businesses/",
                headers=HEADERS_GHL_BUSINESSES,
                json=company_payload
            )
            if res_comp.status_code in [200, 201]:
                resp_json = res_comp.json()
                new_company_id = resp_json.get("id") or resp_json.get("business", {}).get("id")
                print(f"👻 [FORM 2] Nueva compañía (Business) creada para contacto {contacto_original_id}. ID: {new_company_id}")
        except Exception as e:
            print(f"⚠️ [FORM 2] Error al crear compañía: {e}")

    res_opp_update = requests.put(
        f"https://services.leadconnectorhq.com/opportunities/{opp_id}",
        headers=HEADERS_GHL,
        json={"pipelineId": PIPELINE_ID, "pipelineStageId": STAGE_FORM_2, "name": nombre_proyecto, "customFields": custom_fields_nuevos}
    )
    print(f"🔄 [FORM 2] Oportunidad {opp_id} actualizada. Status: {res_opp_update.status_code}")

    # Dividimos el nombre del responsable para guardar Nombre y Apellidos estándar
    if resp_nombre:
        parts = resp_nombre.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
    else:
        first_name = "Administración:"
        last_name = ""

    # Intentamos actualizar el contacto original omitiendo campos vacíos para evitar error 422
    contact_payload = {
        "firstName": first_name,
        "lastName": last_name,
        "customFields": custom_fields_nuevos
    }
    if resp_correo:
        contact_payload["email"] = resp_correo
    if resp_tel:
        contact_payload["phone"] = resp_tel
    if new_company_id:
        contact_payload["businessId"] = new_company_id

    res_contact = requests.put(
        f"https://services.leadconnectorhq.com/contacts/{contacto_original_id}",
        headers=HEADERS_GHL,
        json=contact_payload
    )

    # Si GHL rechaza por duplicados (400), reintentamos la actualización sin los campos de identidad
    if res_contact.status_code == 400 and "duplicated" in res_contact.text.lower():
        print("⚠️ [FORM 2] GHL bloqueó actualización por duplicación de email/teléfono. Reintentando actualización sin campos de identidad...", flush=True)
        contact_payload.pop("email", None)
        contact_payload.pop("phone", None)
        res_contact = requests.put(
            f"https://services.leadconnectorhq.com/contacts/{contacto_original_id}",
            headers=HEADERS_GHL,
            json=contact_payload
        )

    if res_contact.status_code == 422:
        print(f"⚠️ [FORM 2] GHL rechazó el payload del contacto (422). Respuesta: {res_contact.text}", flush=True)
        print("⚠️ [FORM 2] Intentando actualizar contacto SIN custom fields...", flush=True)
        contact_payload.pop("customFields", None)
        res_contact = requests.put(
            f"https://services.leadconnectorhq.com/contacts/{contacto_original_id}",
            headers=HEADERS_GHL,
            json=contact_payload
        )

    if res_contact.status_code in [200, 201]:
        print(f"✅ [FORM 2] Contacto {contacto_original_id} actualizado. Status: {res_contact.status_code}", flush=True)
    else:
        print(f"❌ [FORM 2] Falló al actualizar contacto {contacto_original_id}. Status: {res_contact.status_code}, Error: {res_contact.text}", flush=True)
    if res_contact.status_code not in [200, 201]:
        print(f"❌ [FORM 2] Error al actualizar contacto: {res_contact.text}", flush=True)

    guardar_datos_ficha_en_cache(
        nombre_proyecto=nombre_proyecto,
        opp_id=opp_id,
        contact_id=contacto_original_id,
        datos=datos
    )

    # Eliminar contacto fantasma si se marcó
    if eliminar_fantasma:
        try:
            res_del = requests.delete(
                f"https://services.leadconnectorhq.com/contacts/{contacto_fantasma_id}",
                headers=HEADERS_GHL
            )
            print(f"🗑️ [FORM 2] Contacto fantasma {contacto_fantasma_id} eliminado de GHL. Status: {res_del.status_code}")
        except Exception as e:
            print(f"⚠️ [FORM 2] Error al eliminar contacto fantasma {contacto_fantasma_id}: {e}")

    print(f"✅ [FORM 2] Proyecto '{nombre_proyecto}' actualizado. Empresa y Contacto sincronizados.")
    return jsonify({"status": "success"}), 200


# =========================================================
# RUTA 3: EL AUTO-AVANCE (Envío de Correo y Cambio de Etapa)
# =========================================================
@webhooks_bp.route('/webhook--enviar-correo-asignacion', methods=['POST'])
def webhook_enviar_correo():
    datos = request.json
    if not datos: return jsonify({"error": "No data"}), 400

    opp_id = datos.get("id")
    contact_id = datos.get("contact_id")

    if contact_id:
        res_contact = requests.get(f"https://services.leadconnectorhq.com/contacts/{contact_id}", headers=HEADERS_GHL)
        if res_contact.status_code == 200:
            cfs = res_contact.json().get("contact", {}).get("customFields", [])
            for cf in cfs:
                datos[cf["id"]] = cf.get("value")

    nombre_proyecto = obtener_campo(datos, "cf_nombre_proyecto") or datos.get("opportunity_name", "Desconocido")
    print(f"🚀 [FORM 3] Iniciando envío de correo WIN para: {nombre_proyecto}")

    correo_enviado = enviar_correo_win(datos)

    if correo_enviado and opp_id:
        STAGE_ESPERANDO = os.getenv("STAGE_ESPERANDO_WIN")
        res_update = requests.put(
            f"https://services.leadconnectorhq.com/opportunities/{opp_id}",
            headers=HEADERS_GHL,
            json={"pipelineId": os.getenv("PIPELINE_ID"), "pipelineStageId": STAGE_ESPERANDO}
        )
        if res_update.status_code == 200:
            print(f"✅ [FORM 3] Tarjeta movida automáticamente a 'Esperando Respuesta WIN'.")
            return jsonify({"status": "success", "message": "Correo enviado y tarjeta movida"}), 200
        else:
            print(f"❌ Error al mover la tarjeta: {res_update.text}")
            return jsonify({"status": "partial", "message": "Correo enviado pero fallo al mover la tarjeta"}), 500
    elif not correo_enviado:
        return jsonify({"status": "error", "message": "Fallo el servidor de correos"}), 500

    return jsonify({"status": "error", "message": "Faltan IDs para mover la tarjeta"}), 400


# =========================================================
# RUTA 4: GENERAR EXCEL Y ENVIAR FICHA DE DATOS
# =========================================================
@webhooks_bp.route("/webhook-enviar-ficha-datos-win", methods=["POST"])
def webhook_enviar_ficha_datos_win():
    try:
        data = request.get_json(silent=True) or request.form.to_dict()

        # Recuperamos la ficha completa guardada desde el webhook 2
        data = recuperar_datos_ficha_de_cache(data)

        print("\n📩 [FICHA DATOS WIN] Webhook recibido")
        print("=====================================")
        print("Proyecto:", data.get("cf_nombre_proyecto") or data.get("opportunity_name"))
        print("Contacto ID:", data.get("contact_id"))
        print("Oportunidad ID:", data.get("id"))
        print("=====================================\n")

        datos_excel = construir_datos_ficha_desde_webhook(data)

        nombre_limpio = limpiar_nombre_archivo(
            datos_excel.get("nombre_proyecto", "proyecto")
        )

        url_foto_edificio = obtener_primera_url(datos_excel.get("foto_edificio"))
        url_foto_montantes = obtener_primera_url(datos_excel.get("foto_montantes"))

        print("📸 URL FOTO EDIFICIO:", url_foto_edificio)
        print("📸 URL FOTO MONTANTES:", url_foto_montantes)

        # Verificamos si los archivos ya fueron descargados previamente en el webhook 2
        foto_edificio_path = data.get("foto_edificio_path")
        foto_montantes_path = data.get("foto_montantes_path")

        # Normalizar rutas locales para compatibilidad cruzada entre Windows y Linux (Docker)
        from app.services.ficha_service import CARPETA_TEMP
        if foto_edificio_path:
            filename_edificio = foto_edificio_path.replace('\\', '/').split('/')[-1]
            foto_edificio_path = os.path.join(CARPETA_TEMP, filename_edificio)
        if foto_montantes_path:
            filename_montantes = foto_montantes_path.replace('\\', '/').split('/')[-1]
            foto_montantes_path = os.path.join(CARPETA_TEMP, filename_montantes)

        if not foto_edificio_path or not os.path.exists(foto_edificio_path):
            print("📸 Foto Edificio no encontrada en caché local o eliminada, descargando...")
            foto_edificio_path = descargar_imagen(
                url_foto_edificio,
                f"{nombre_limpio}_foto_edificio"
            )
        else:
            print("📸 Foto Edificio recuperada directamente del caché local:", foto_edificio_path)

        if not foto_montantes_path or not os.path.exists(foto_montantes_path):
            print("📸 Foto Montantes no encontrada en caché local o eliminada, descargando...")
            foto_montantes_path = descargar_imagen(
                url_foto_montantes,
                f"{nombre_limpio}_foto_montantes"
            )
        else:
            print("📸 Foto Montantes recuperada directamente del caché local:", foto_montantes_path)

        datos_excel["foto_edificio_path"] = foto_edificio_path
        datos_excel["foto_montantes_path"] = foto_montantes_path

        archivo_generado = generar_excel_ficha_datos(datos_excel)

        print(f"✅ [FICHA DATOS WIN] Excel generado: {archivo_generado}")

        enviar_correo_ficha_datos_win(archivo_generado, datos_excel)

        return jsonify({
            "status": "ok",
            "mensaje": "Excel generado y correo enviado correctamente",
            "archivo": archivo_generado
        }), 200

    except Exception as e:
        print("❌ [FICHA DATOS WIN] Error:", str(e))
        return jsonify({
            "status": "error",
            "mensaje": str(e)
        }), 500


# =========================================================
# API DE CACHÉ PARA EL BOT DOCKERIZADO
# =========================================================
@webhooks_bp.route('/api/cache/<identifier>', methods=['GET'])
def obtener_cache_api(identifier):
    from app.database import obtener_oportunidad_db
    import json
    try:
        # Intentamos obtener por oportunidad_id
        row = obtener_oportunidad_db(opp_id=identifier)
        # Si no, por contacto_id
        if not row:
            row = obtener_oportunidad_db(contact_id=identifier)
        # Si no, por nombre_proyecto
        if not row:
            row = obtener_oportunidad_db(nombre_proyecto=identifier)
            
        if row:
            resp_dict = {}
            if row.get("raw_json"):
                try:
                    resp_dict = json.loads(row["raw_json"])
                except Exception:
                    pass
            # Incorporamos las columnas de la base de datos al diccionario de respuesta
            for k, v in row.items():
                if k != "raw_json":
                    resp_dict[k] = v
                    if k == "foto_edificio" and v:
                        resp_dict["cf_foto_edificio"] = v
                    if k == "foto_montantes" and v:
                        resp_dict["cf_foto_montantes"] = v
                        
            print(f"[OK] [API CACHE DB] Enviando datos a bot para identificador: {identifier}", flush=True)
            return jsonify(resp_dict), 200
            
        return jsonify({"error": "No encontrado en caché de base de datos"}), 404
    except Exception as e:
        print("[ERROR] [API CACHE DB] Error:", str(e), flush=True)
        return jsonify({"error": str(e)}), 500


@webhooks_bp.route('/api/cache/files/<filename>', methods=['GET'])
def obtener_archivo_cache(filename):
    from flask import send_from_directory
    from app.services.ficha_service import CARPETA_TEMP
    try:
        return send_from_directory(CARPETA_TEMP, filename)
    except Exception as e:
        print(f"[ERROR] [API CACHE FILE] Error al servir {filename}: {e}", flush=True)
        return jsonify({"error": "Archivo no encontrado"}), 404


@webhooks_bp.route('/api/disponibilidad', methods=['GET'])
def consultar_disponibilidad_api():
    query_str = request.args.get("q", "").strip()
    if not query_str:
        return jsonify([]), 200
        
    from app.database import get_db_connection
    import json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Búsqueda parcial (case-insensitive LIKE) en nombre y dirección
        sql_query = """
            SELECT nombre_proyecto, tipo_via, nombre_via, numero_via, urbanizacion, distrito, gestor, raw_json 
            FROM oportunidades_ficha 
            WHERE nombre_proyecto LIKE ? 
               OR nombre_via LIKE ? 
               OR urbanizacion LIKE ? 
               OR distrito LIKE ?
        """
        like_pattern = f"%{query_str}%"
        cursor.execute(sql_query, (like_pattern, like_pattern, like_pattern, like_pattern))
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            raw_data = {}
            if row["raw_json"]:
                try:
                    raw_data = json.loads(row["raw_json"])
                except Exception:
                    pass
            # Extraemos supervisor y ejecutivo de raw_json
            supervisor = raw_data.get("cf_supervisor_hunting") or raw_data.get("cf_supervisor") or ""
            ejecutivo = raw_data.get("cf_ejecutivo_principal") or raw_data.get("cf_ejecutivo") or ""
            
            results.append({
                "nombre_proyecto": row["nombre_proyecto"],
                "tipo_via": row["tipo_via"],
                "nombre_via": row["nombre_via"],
                "numero_via": row["numero_via"],
                "urbanizacion": row["urbanizacion"],
                "distrito": row["distrito"],
                "gestor": row["gestor"],
                "supervisor": supervisor,
                "ejecutivo": ejecutivo
            })
        return jsonify(results), 200
    except Exception as e:
        print(f"❌ [API DISPONIBILIDAD] Error: {e}", flush=True)
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# =========================================================
# RUTAS DE EDICIÓN DEL PANEL WEB PARA BACKOFFICE
# =========================================================

def generar_enlace_edicion(oportunidad_id):
    import hmac, hashlib
    secret = os.getenv("FLASK_SECRET_KEY") or os.getenv("GHL_ACCESS_TOKEN") or "super-secret-key-fallback"
    token = hmac.new(secret.encode('utf-8'), oportunidad_id.encode('utf-8'), hashlib.sha256).hexdigest()
    base_url = os.getenv("MIDDLEWARE_URL") or "https://webhook.novacoresac.com"
    return f"{base_url}/ficha/editar/{oportunidad_id}?token={token}"

def verificar_enlace_edicion(oportunidad_id, token_recibido):
    import hmac, hashlib
    if not token_recibido:
        return False
    secret = os.getenv("FLASK_SECRET_KEY") or os.getenv("GHL_ACCESS_TOKEN") or "super-secret-key-fallback"
    expected_token = hmac.new(secret.encode('utf-8'), oportunidad_id.encode('utf-8'), hashlib.sha256).hexdigest()
    return hmac.compare_digest(token_recibido, expected_token)


@webhooks_bp.route('/ficha/editar/<opp_id>', methods=['GET'])
def render_editar_ficha(opp_id):
    from flask import render_template
    from app.database import obtener_oportunidad_db
    
    token = request.args.get("token")
    if not verificar_enlace_edicion(opp_id, token):
        return "⚠️ Acceso Denegado: Enlace expirado o firma inválida.", 403
        
    opp_data = obtener_oportunidad_db(opp_id=opp_id)
    if not opp_data:
        return "⚠️ Oportunidad no encontrada en el sistema.", 404
        
    return render_template("edit_ficha.html", opp=opp_data)


@webhooks_bp.route('/ficha/editar/<opp_id>', methods=['POST'])
def procesar_editar_ficha(opp_id):
    from app.database import obtener_oportunidad_db, guardar_oportunidad_db
    from app.services.ghl_api import update_ghl_contact_fields
    from app.services.ficha_service import descargar_imagen, limpiar_nombre_archivo
    
    token = request.args.get("token")
    if not verificar_enlace_edicion(opp_id, token):
        return jsonify({"status": "error", "message": "Acceso Denegado: Token inválido."}), 403
        
    opp_data = obtener_oportunidad_db(opp_id=opp_id)
    if not opp_data:
        return jsonify({"status": "error", "message": "Oportunidad no encontrada."}), 404
        
    # Leemos todos los campos del formulario post
    campos_editados = request.form.to_dict()
    
    # Procesamos las nuevas fotos si fueron cargadas
    foto_edificio_file = request.files.get("foto_edificio")
    foto_montantes_file = request.files.get("foto_montantes")
    
    nombre_limpio = limpiar_nombre_archivo(campos_editados.get("nombre_proyecto") or opp_data.get("nombre_proyecto") or "proyecto")
    
    # Si subió una foto de edificio nueva
    if foto_edificio_file and foto_edificio_file.filename:
        from app.services.ficha_service import CARPETA_TEMP
        path_local = os.path.join(CARPETA_TEMP, f"{nombre_limpio}_foto_edificio.jpg")
        foto_edificio_file.save(path_local)
        
        opp_data["foto_edificio_path"] = path_local
        base_url = os.getenv("MIDDLEWARE_URL") or "https://webhook.novacoresac.com"
        opp_data["foto_edificio"] = f"{base_url}/api/cache/files/{nombre_limpio}_foto_edificio.jpg"
        print(f"📸 [POST EDIT] Reemplazada foto edificio local: {path_local}", flush=True)
        
    # Si subió una foto de montantes nueva
    if foto_montantes_file and foto_montantes_file.filename:
        from app.services.ficha_service import CARPETA_TEMP
        path_local = os.path.join(CARPETA_TEMP, f"{nombre_limpio}_foto_montantes.jpg")
        foto_montantes_file.save(path_local)
        
        opp_data["foto_montantes_path"] = path_local
        base_url = os.getenv("MIDDLEWARE_URL") or "https://webhook.novacoresac.com"
        opp_data["foto_montantes"] = f"{base_url}/api/cache/files/{nombre_limpio}_foto_montantes.jpg"
        print(f"📸 [POST EDIT] Reemplazada foto montantes local: {path_local}", flush=True)

    # Actualizamos el resto de los campos de texto
    for k, v in campos_editados.items():
        opp_data[k] = v
        
    # Recuperamos el raw_json original y lo actualizamos con los nuevos campos para consistencia de fallback
    raw_json_str = opp_data.get("raw_json")
    raw_json_dict = {}
    if raw_json_str:
        try:
            raw_json_dict = json.loads(raw_json_str)
        except Exception:
            pass
            
    # Mapeamos los campos del formulario de vuelta al raw_json con el prefijo cf_
    from app.services.ghl_api import DB_COL_TO_GHL_KEY
    for k, v in campos_editados.items():
        if k in DB_COL_TO_GHL_KEY:
            raw_json_dict[DB_COL_TO_GHL_KEY[k]] = v
            
    # Guardamos en base de datos SQLite
    guardar_oportunidad_db(opp_id, opp_data.get("contacto_id"), opp_data, raw_json_dict)
    
    # 🚀 SINCRONIZACIÓN INVERSA A GHL
    campos_sincronizar = dict(campos_editados)
    campos_sincronizar.pop("foto_edificio", None)
    campos_sincronizar.pop("foto_montantes", None)
    
    sync_exito = update_ghl_contact_fields(opp_data.get("contacto_id"), campos_sincronizar)
    
    if sync_exito:
        return jsonify({"status": "success", "message": "Cambios guardados localmente y sincronizados con GHL exitosamente."}), 200
    else:
        return jsonify({"status": "success", "message": "Cambios guardados localmente pero falló la sincronización visual inmediata con GHL (se reintentará en el Paso 4)."}), 200