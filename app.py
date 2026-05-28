import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import json

load_dotenv()

app = Flask(__name__)


# Credenciales y Configuración
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


def obtener_campo(payload, key):
    if key in payload: return payload[key]
    cf = payload.get("customFields", {})
    if isinstance(cf, dict) and key in cf: return cf[key]
    return None


def extraer_custom_fields_para_ghl(datos_formulario):
    cf_array = []
    fuente = datos_formulario.get("customFields", datos_formulario)
    if isinstance(fuente, dict):
        for k, v in fuente.items():
            if k.startswith("cf_") and v is not None and v != "":
                cf_array.append({"id": k, "value": v})
    return cf_array


# =========================================================
# RUTA 1: EL GÉNESIS (Formulario de Asignación)
# =========================================================
@app.route('/webhook-formulario1', methods=['POST'])
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

    # --- ESCUDO ANTI-DUPLICADOS ---
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

    # 1. ATRAPAR Y TRANSFORMAR AL CONTACTO FANTASMA NATIVO
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

    # 2. Crear Company (El activo físico)
    res_company = requests.post(
        "https://services.leadconnectorhq.com/companies/",
        headers=HEADERS_GHL,
        json={
            "locationId": LOCATION_ID,
            "name": nombre_proyecto
        }
    )
    company_id = res_company.json().get("company", {}).get("id") if res_company.status_code in [200, 201] else None

    # 3. Vincular Company con Contacto
    if company_id:
        requests.post(
            f"https://services.leadconnectorhq.com/contacts/{contact_id}/companies/{company_id}",
            headers=HEADERS_GHL
        )

    # 4. Crear Oportunidad (SIN el array de followers aquí)
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

    # 5. Agregar el Seguidor (Follower) en la ruta correcta
    opp_id = res_opp.json().get("opportunity", {}).get("id")
    if opp_id:
        res_follower = requests.post(
            f"https://services.leadconnectorhq.com/opportunities/{opp_id}/followers",
            headers=HEADERS_GHL,
            json={
                "followers": [USERS_GHL["STEFANO_BO"]]
            }
        )
        if res_follower.status_code not in [200, 201]:
            print(f"⚠️ Aviso: No se pudo agregar el seguidor. {res_follower.text}")

    print(f"✅ [FORM 1] Setup completado. Asignado a: {'Jean' if owner_id == USERS_GHL['JEAN'] else 'Yasmin'}")
    return jsonify({"status": "success"}), 200


# =========================================================
# RUTA 2: LA ACTUALIZACIÓN (Formulario de Ficha de Datos)
# =========================================================
@app.route('/webhook-formulario2', methods=['POST'])
def webhook_formulario2():
    datos = request.json
    if not datos: return jsonify({"error": "No data"}), 400

    nombre_proyecto_raw = obtener_campo(datos, "cf_nombre_proyecto")
    if not nombre_proyecto_raw:
        return jsonify({"error": "Falta el nombre del proyecto"}), 400

    nombre_proyecto = str(nombre_proyecto_raw).strip().upper()
    print(f"🔍 [FORM 2] Buscando oportunidad para actualizar: '{nombre_proyecto}'")

    # Búsqueda de Oportunidad
    res_search = requests.get(
        f"https://services.leadconnectorhq.com/opportunities/search?location_id={LOCATION_ID}&q={nombre_proyecto}",
        headers=HEADERS_GHL
    )
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

    # 1. ELIMINAR CONTACTO FANTASMA
    contacto_fantasma_id = datos.get("contact_id") or datos.get("contact", {}).get("id")
    if contacto_fantasma_id and contacto_fantasma_id != contacto_original_id:
        requests.delete(f"https://services.leadconnectorhq.com/contacts/{contacto_fantasma_id}", headers=HEADERS_GHL)

    # 2. EXTRACCIÓN Y MAPEO ESPECÍFICO (Responsable y Dirección)
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

    # 3. ACTUALIZAR COMPANY
    # Obtener el companyId del contacto original para actualizarlo
    res_get_contact = requests.get(f"https://services.leadconnectorhq.com/contacts/{contacto_original_id}",
                                   headers=HEADERS_GHL)
    company_id = res_get_contact.json().get("contact", {}).get(
        "companyId") if res_get_contact.status_code == 200 else None

    if company_id:
        requests.put(
            f"https://services.leadconnectorhq.com/companies/{company_id}",
            headers=HEADERS_GHL,
            json={
                "locationId": LOCATION_ID,
                "name": nombre_proyecto,
                "phone": resp_tel,
                "address": direccion_completa,
                "city": ciudad,
                "state": estado,
                "postalCode": codigo_postal,
                "country": "Peru"
            }
        )

    # 4. ACTUALIZAR OPORTUNIDAD (Mover de etapa e inyectar CFs restantes)
    requests.put(
        f"https://services.leadconnectorhq.com/opportunities/{opp_id}",
        headers=HEADERS_GHL,
        json={
            "pipelineId": PIPELINE_ID,
            "pipelineStageId": STAGE_FORM_2,
            "name": nombre_proyecto,
            "customFields": custom_fields_nuevos
        }
    )

    # 5. ACTUALIZAR CONTACTO (Nativo + Custom Fields)
    requests.put(
        f"https://services.leadconnectorhq.com/contacts/{contacto_original_id}",
        headers=HEADERS_GHL,
        json={
            "firstName": resp_nombre if resp_nombre else "Administración:",
            "lastName": nombre_proyecto,
            "email": resp_correo,
            "phone": resp_tel,
            "customFields": custom_fields_nuevos
        }
    )

    print(f"✅ [FORM 2] Proyecto '{nombre_proyecto}' actualizado. Empresa y Contacto sincronizados.")
    return jsonify({"status": "success"}), 200


# =========================================================
# FUNCIÓN INTERNA: ENVÍO DE CORREO SMTP
# =========================================================
def enviar_correo_win(datos_contacto):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    email_emisor = os.getenv("EMAIL_EMISOR")
    email_password = os.getenv("EMAIL_PASSWORD")
    email_destino = os.getenv("EMAIL_DESTINO")

    # Extracción segura de los campos (Priorizando los Custom Fields inyectados)
    tipo_predio = obtener_campo(datos_contacto, "cf_tipo_edificio") or "EDIFICIO"
    # Si no hay campo cf_nombre_proyecto, usamos el opportunity_name nativo del webhook
    nombre_predio = obtener_campo(datos_contacto, "cf_nombre_proyecto") or datos_contacto.get("opportunity_name",
                                                                                              "NO ESPECIFICADO")
    tipo_via = obtener_campo(datos_contacto, "cf_tipo_via") or ""
    nombre_via = obtener_campo(datos_contacto, "cf_nombre_via") or ""
    direccion = f"{tipo_via} {nombre_via}".strip() or "NO ESPECIFICADO"

    numeracion = obtener_campo(datos_contacto, "cf_numeracion_via") or "No especificado"
    distrito = obtener_campo(datos_contacto, "cf_distrito") or "NO ESPECIFICADO"
    coordenadas = obtener_campo(datos_contacto, "cf_coordenadas") or "No especificado"
    estreno = obtener_campo(datos_contacto, "cf_es_estreno") or "SI"
    inmobiliaria = obtener_campo(datos_contacto, "cf_inmobiliaria") or "NO ESPECIFICADO"

    # Si no hay cf_ejecutivo, usamos el owner nativo del webhook
    ejecutivo = obtener_campo(datos_contacto, "cf_ejecutivo_principal") or datos_contacto.get("owner",
                                                                                              "NO ESPECIFICADO")
    asignar_reasignar = obtener_campo(datos_contacto, "cf_tipo_gestion") or "ASIGNAR"

    fecha_actual = datetime.now().strftime("%d/%m/%Y")

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Solicitud de asignación - {nombre_predio.upper()}"
    msg['From'] = f"Vertical Futura <{email_emisor}>"
    msg['To'] = email_destino

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.4;">
        <p>Estimados,</p>
        <p>Solicitamos la asignación del predio en mención.</p>
        <br>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 600px; border-color: #cccccc;">
          <tr style="background-color: #f2f2f2;">
            <th align="left" style="width: 40%; font-size: 14px;">FORMATO DE ASIGNACION</th>
            <th style="width: 60%;"></th>
          </tr>
          <tr><td><strong>Tipo de Predio:</strong></td><td>{str(tipo_predio).upper()}</td></tr>
          <tr><td><strong>Nombre del predio:</strong></td><td>{str(nombre_predio).upper()}</td></tr>
          <tr><td><strong>Direccion:</strong></td><td>{str(direccion).upper()}</td></tr>
          <tr><td><strong>Numeracion:</strong></td><td>{numeracion}</td></tr>
          <tr><td><strong>Distrito:</strong></td><td>{str(distrito).upper()}</td></tr>
          <tr><td><strong>Coordenadas:</strong></td><td>{coordenadas}</td></tr>
          <tr><td><strong>Cobertura Si/no:</strong></td><td>SI</td></tr>
          <tr><td><strong>Asignar/Reasignar:</strong></td><td>{str(asignar_reasignar).upper()}</td></tr>
          <tr><td><strong>Estreno:</strong></td><td>{str(estreno).upper()}</td></tr>
          <tr><td><strong>Fecha:</strong></td><td>{fecha_actual}</td></tr>
          <tr><td><strong>Inmobiliaria:</strong></td><td>{str(inmobiliaria).upper()}</td></tr>
          <tr><td><strong>Ejecutivo:</strong></td><td>{str(ejecutivo).upper()}</td></tr>
        </table>
        <p style="margin-top: 25px;">Saludos,</p>
        <p><strong>Stefano Sotomarino Goche</strong><br>Back Office - Futura</p>
      </body>
    </html>
    """
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(email_emisor, email_password)
            server.sendmail(email_emisor, [email_destino], msg.as_string())
        print(f"📧 Correo enviado a WIN para: {nombre_predio.upper()}")
        return True
    except Exception as e:
        print(f"❌ Error al enviar el correo a WIN: {e}")
        return False


# =========================================================
# RUTA 3: EL AUTO-AVANCE (Envío de Correo y Cambio de Etapa)
# =========================================================
@app.route('/webhook--enviar-correo-asignacion', methods=['POST'])
def webhook_enviar_correo():
    datos = request.json
    if not datos: return jsonify({"error": "No data"}), 400

    opp_id = datos.get("id")
    contact_id = datos.get("contact_id")

    # 1. RECUPERAR LOS CAMPOS PERSONALIZADOS QUE GHL OCULTA EN EL WEBHOOK LIGERO
    if contact_id:
        res_contact = requests.get(
            f"https://services.leadconnectorhq.com/contacts/{contact_id}",
            headers=HEADERS_GHL
        )
        if res_contact.status_code == 200:
            cfs = res_contact.json().get("contact", {}).get("customFields", [])
            for cf in cfs:
                # Inyectamos los campos ocultos directamente en nuestro diccionario de datos
                datos[cf["id"]] = cf.get("value")

    nombre_proyecto = obtener_campo(datos, "cf_nombre_proyecto") or datos.get("opportunity_name", "Desconocido")
    print(f"🚀 [FORM 3] Iniciando envío de correo WIN para: {nombre_proyecto}")

    # 2. Enviar el correo SMTP con todos los datos completos
    correo_enviado = enviar_correo_win(datos)

    # 3. Si el correo sale con éxito, mover la tarjeta automáticamente
    if correo_enviado and opp_id:
        STAGE_ESPERANDO = os.getenv("STAGE_ESPERANDO_WIN")

        res_update = requests.put(
            f"https://services.leadconnectorhq.com/opportunities/{opp_id}",
            headers=HEADERS_GHL,
            json={
                "pipelineId": os.getenv("PIPELINE_ID"),
                "pipelineStageId": STAGE_ESPERANDO
            }
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


if __name__ == '__main__':
    app.run(port=5001, debug=True)