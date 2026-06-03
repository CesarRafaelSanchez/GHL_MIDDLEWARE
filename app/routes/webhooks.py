import os
from flask import Blueprint, request, jsonify

# Importamos tus herramientas y servicios modularizados
from app.utils.helpers import obtener_campo, extraer_custom_fields_para_ghl, obtener_session_con_retries
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

USERS_GHL = {
    "JEAN": "UzEVMjDvEHlw6YUAj3aJ",
    "YASMIN": "bVGkAziqy6vwDoFbqvr6",
    "STEFANO_BO": "6u8iZhDXnxp0xSp7XfDl"
}


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

    res_search = requests.get(
        f"https://services.leadconnectorhq.com/opportunities/search?location_id={LOCATION_ID}&q={nombre_proyecto}",
        headers=HEADERS_GHL
    )
    if res_search.status_code == 200:
        resultados = res_search.json().get("opportunities", [])
        opp_existente = next((opp for opp in resultados if opp.get("pipelineId") == PIPELINE_ID), None)
        if opp_existente:
            print(f"⚠️ [FORM 1] El proyecto '{nombre_proyecto}' ya existe. Evitando creación duplicada.")
            return jsonify({"status": "ignored", "message": "El proyecto ya existe"}), 200

    owner_id = USERS_GHL["JEAN"] if "JEAN" in ejecutivo_str else USERS_GHL["YASMIN"]

    tags_contacto = [
        "NUEVO HUNTING",
        f"Origen: {tipo_ingreso}" if tipo_ingreso != "None" else "Origen: No Especificado",
        f"Distrito: {distrito}" if distrito != "None" else "Distrito: No Especificado",
        "Hunter: Jean" if owner_id == USERS_GHL["JEAN"] else "Hunter: Yasmin",
        "Trigger_Notificacion_BO"
    ]

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
            json={"followers": [USERS_GHL["STEFANO_BO"]]}
        )

    print(f"✅ [FORM 1] Setup completado. Asignado a: {'Jean' if owner_id == USERS_GHL['JEAN'] else 'Yasmin'}")
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
    company_id = res_get_contact.json().get("contact", {}).get("companyId") if res_get_contact.status_code == 200 else None

    if company_id:
        company_payload = {
            "locationId": LOCATION_ID,
            "name": nombre_proyecto,
            "address": direccion_completa,
            "city": ciudad,
            "state": estado,
            "postalCode": codigo_postal,
            "country": "Peru"
        }
        if resp_tel:
            company_payload["phone"] = resp_tel
        requests.put(
            f"https://services.leadconnectorhq.com/companies/{company_id}",
            headers=HEADERS_GHL,
            json=company_payload
        )

    res_opp_update = requests.put(
        f"https://services.leadconnectorhq.com/opportunities/{opp_id}",
        headers=HEADERS_GHL,
        json={"pipelineId": PIPELINE_ID, "pipelineStageId": STAGE_FORM_2, "name": nombre_proyecto, "customFields": custom_fields_nuevos}
    )
    print(f"🔄 [FORM 2] Oportunidad {opp_id} actualizada. Status: {res_opp_update.status_code}")

    # Intentamos actualizar el contacto original omitiendo campos vacíos para evitar error 422
    contact_payload = {
        "firstName": resp_nombre if resp_nombre else "Administración:",
        "lastName": nombre_proyecto,
        "customFields": custom_fields_nuevos
    }
    if resp_correo:
        contact_payload["email"] = resp_correo
    if resp_tel:
        contact_payload["phone"] = resp_tel

    res_contact = requests.put(
        f"https://services.leadconnectorhq.com/contacts/{contacto_original_id}",
        headers=HEADERS_GHL,
        json=contact_payload
    )

    # Si GHL rechaza por duplicados (400), reintentamos la actualización sin los campos de identidad
    if res_contact.status_code == 400 and "duplicated" in res_contact.text.lower():
        print("⚠️ [FORM 2] GHL bloqueó actualización por duplicación de email/teléfono. Reintentando actualización sin campos de identidad...")
        contact_payload.pop("email", None)
        contact_payload.pop("phone", None)
        res_contact = requests.put(
            f"https://services.leadconnectorhq.com/contacts/{contacto_original_id}",
            headers=HEADERS_GHL,
            json=contact_payload
        )

    print(f"🔄 [FORM 2] Contacto original {contacto_original_id} actualizado. Status: {res_contact.status_code}")

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
    from app.services.ficha_service import cargar_cache_fichas, normalizar_clave_proyecto
    try:
        cache = cargar_cache_fichas()
        posibles_claves = [
            f"opp::{identifier}",
            f"contact::{identifier}",
            f"nombre::{normalizar_clave_proyecto(identifier)}"
        ]
        for clave in posibles_claves:
            if clave in cache:
                print(f"[OK] [API CACHE] Enviando datos a bot para clave: {clave}", flush=True)
                return jsonify(cache[clave]), 200
        return jsonify({"error": "No encontrado en caché"}), 404
    except Exception as e:
        print("[ERROR] [API CACHE] Error:", str(e), flush=True)
        return jsonify({"error": str(e)}), 500