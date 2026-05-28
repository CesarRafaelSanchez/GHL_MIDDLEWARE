import os
import requests
from flask import Blueprint, request, jsonify

# Importamos tus herramientas y el servicio de correo modularizados
from app.utils.helpers import obtener_campo, extraer_custom_fields_para_ghl
from app.services.email_smtp import enviar_correo_win

# 1. CREAMOS EL BLUEPRINT (La habitación de las rutas)
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
# RUTAS DE WEBHOOKS
# =========================================================

@webhooks_bp.route('/webhook-formulario1-enviado', methods=['POST'])
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
            return jsonify({"status": "partial", "message": "Correo enviado pero fallo al mover la tarjeta"}), 500
    elif not correo_enviado:
        return jsonify({"status": "error", "message": "Fallo el servidor de correos"}), 500

    return jsonify({"status": "error", "message": "Faltan IDs para mover la tarjeta"}), 400


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
        return jsonify({"error": "Oportunidad no encontrada"}), 404

    if oportunidad_correcta.get("pipelineStageId") == STAGE_FORM_2:
        return jsonify({"status": "ignored", "message": "Ficha ya procesada"}), 200

    opp_id = oportunidad_correcta.get("id")
    contacto_original_id = oportunidad_correcta.get("contactId")
    custom_fields_nuevos = extraer_custom_fields_para_ghl(datos)

    contacto_fantasma_id = datos.get("contact_id") or datos.get("contact", {}).get("id")
    if contacto_fantasma_id and contacto_fantasma_id != contacto_original_id:
        requests.delete(f"https://services.leadconnectorhq.com/contacts/{contacto_fantasma_id}", headers=HEADERS_GHL)

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
        requests.put(
            f"https://services.leadconnectorhq.com/companies/{company_id}",
            headers=HEADERS_GHL,
            json={"locationId": LOCATION_ID, "name": nombre_proyecto, "phone": resp_tel, "address": direccion_completa, "city": ciudad, "state": estado, "postalCode": codigo_postal, "country": "Peru"}
        )

    requests.put(
        f"https://services.leadconnectorhq.com/opportunities/{opp_id}",
        headers=HEADERS_GHL,
        json={"pipelineId": PIPELINE_ID, "pipelineStageId": STAGE_FORM_2, "name": nombre_proyecto, "customFields": custom_fields_nuevos}
    )

    requests.put(
        f"https://services.leadconnectorhq.com/contacts/{contacto_original_id}",
        headers=HEADERS_GHL,
        json={"firstName": resp_nombre if resp_nombre else "Administración:", "lastName": nombre_proyecto, "email": resp_correo, "phone": resp_tel, "customFields": custom_fields_nuevos}
    )

    print(f"✅ [FORM 2] Proyecto '{nombre_proyecto}' actualizado.")
    return jsonify({"status": "success"}), 200