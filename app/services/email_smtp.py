import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.message import EmailMessage
from datetime import datetime

# Importamos tu herramienta
from app.utils.helpers import obtener_campo


def enviar_correo_win(datos_contacto):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    email_emisor = os.getenv("EMAIL_EMISOR")
    email_password = os.getenv("EMAIL_PASSWORD")

    email_destino = os.getenv("EMAIL_DESTINO")
    email_cc = os.getenv("EMAIL_CC_ASIGNACION", "")

    tipo_predio = obtener_campo(datos_contacto, "cf_tipo_edificio") or "EDIFICIO"
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

    ejecutivo = obtener_campo(datos_contacto, "cf_ejecutivo_principal") or datos_contacto.get("owner",
                                                                                              "NO ESPECIFICADO")
    asignar_reasignar = obtener_campo(datos_contacto, "cf_tipo_gestion") or "ASIGNAR"

    fecha_actual = datetime.now().strftime("%d/%m/%Y")

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Solicitud de asignación - {nombre_predio.upper()}"
    msg['From'] = f"Vertical Futura <{email_emisor}>"
    msg['To'] = email_destino

    if email_cc:
        msg['Cc'] = email_cc

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
        lista_destinos = [correo.strip() for correo in email_destino.split(',')]
        lista_cc = [correo.strip() for correo in email_cc.split(',')] if email_cc else []
        todos_los_destinatarios = lista_destinos + lista_cc

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(email_emisor, email_password)
            server.sendmail(email_emisor, todos_los_destinatarios, msg.as_string())

        print(f"📧 Correo enviado con éxito para {nombre_predio.upper()} (Con copias a {len(lista_cc)} destinatarios)")
        return True
    except Exception as e:
        print(f"❌ Error al enviar el correo a WIN: {e}")
        return False


def enviar_correo_ficha_datos_win(archivo_excel, datos):
    proyecto = datos.get("nombre_proyecto", "PROYECTO")
    asunto = f"Ficha de Datos - {proyecto}"

    email_emisor = os.getenv("EMAIL_EMISOR")
    email_destino = os.getenv("EMAIL_DESTINO")
    email_password = os.getenv("EMAIL_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    email_cc = os.getenv("EMAIL_CC_FICHA", "")

    cuerpo = f"""
    Buen día,<br><br>
    Se adjunta la ficha de datos correspondiente al proyecto:<br><br>
    <b>{proyecto}</b><br><br>
    Datos principales:<br>
    - Distrito: {datos.get("distrito", "")}<br>
    - Dirección: {datos.get("tipo_via", "")} {datos.get("nombre_via", "")} {datos.get("numero_via", "")}<br>
    - Responsable: {datos.get("nombre_responsable", "")}<br>
    - Teléfono: {datos.get("telefono_responsable", "")}<br><br>
    Saludos,<br>
    Futura
    """

    msg = EmailMessage()
    msg["From"] = email_emisor
    msg["To"] = email_destino
    msg["Subject"] = asunto

    if email_cc:
        msg["Cc"] = email_cc

    msg.set_content(f"Se adjunta la ficha de datos del proyecto {proyecto}.")
    msg.add_alternative(cuerpo, subtype="html")

    with open(archivo_excel, "rb") as f:
        contenido_excel = f.read()

    nombre_adjunto = os.path.basename(archivo_excel)
    msg.add_attachment(
        contenido_excel,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=nombre_adjunto
    )

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as smtp:
            smtp.login(email_emisor, email_password)
            smtp.send_message(msg)
        print(f"📧 [FICHA DATOS WIN] Correo enviado con adjunto: {nombre_adjunto}")
        return True
    except Exception as e:
        print(f"❌ Error al enviar correo de Ficha a WIN: {e}")
        return False