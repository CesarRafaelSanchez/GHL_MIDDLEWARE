import os
import json
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from PIL import Image as PILImage
from io import BytesIO
from dotenv import load_dotenv
from app.utils.helpers import obtener_session_con_retries

requests = obtener_session_con_retries()

#load_dotenv()

# =========================================================
# RUTAS ABSOLUTAS (A prueba de balas)
# =========================================================
# Esto encuentra la ruta de tu proyecto GHL_System automáticamente
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CARPETA_SALIDAS = os.path.join(BASE_DIR, "archivos_datos", "salidas")
CARPETA_TEMP = os.path.join(BASE_DIR, "archivos_datos", "temp")
ARCHIVO_CACHE_FICHAS = os.path.join(BASE_DIR, "archivos_datos", "cache_fichas_datos.json")
RUTA_PLANTILLA_FICHA_DATOS = os.path.join(BASE_DIR, "archivos_datos", "plantillas", "Ficha de Datos NOMBRE DEL PROYECTO.xlsx")

# Creamos las carpetas si no existen
os.makedirs(CARPETA_SALIDAS, exist_ok=True)
os.makedirs(CARPETA_TEMP, exist_ok=True)
# =========================================================


def normalizar_clave_proyecto(nombre):
    return str(nombre or "").strip().upper()


def cargar_cache_fichas():
    if not os.path.exists(ARCHIVO_CACHE_FICHAS):
        return {}
    try:
        with open(ARCHIVO_CACHE_FICHAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def guardar_cache_fichas(cache):
    with open(ARCHIVO_CACHE_FICHAS, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def guardar_datos_ficha_en_cache(nombre_proyecto, opp_id, contact_id, datos):
    cache = cargar_cache_fichas()
    clave_nombre = normalizar_clave_proyecto(nombre_proyecto)

    datos_guardar = dict(datos)
    datos_guardar["_opp_id"] = opp_id
    datos_guardar["_contact_id"] = contact_id
    datos_guardar["_nombre_proyecto"] = clave_nombre
    datos_guardar["_guardado_en"] = datetime.now().isoformat()

    if clave_nombre:
        cache[f"nombre::{clave_nombre}"] = datos_guardar
    if opp_id:
        cache[f"opp::{opp_id}"] = datos_guardar
    if contact_id:
        cache[f"contact::{contact_id}"] = datos_guardar

    guardar_cache_fichas(cache)
    print(f"💾 [CACHE FICHA] Datos guardados para: {clave_nombre}")


def recuperar_datos_ficha_de_cache(data):
    cache = cargar_cache_fichas()
    opp_id = data.get("id")
    contact_id = data.get("contact_id") or data.get("contact", {}).get("id")
    nombre = data.get("cf_nombre_proyecto") or data.get("opportunity_name")
    clave_nombre = normalizar_clave_proyecto(nombre)

    posibles_claves = []
    if opp_id:
        posibles_claves.append(f"opp::{opp_id}")
    if contact_id:
        posibles_claves.append(f"contact::{contact_id}")
    if clave_nombre:
        posibles_claves.append(f"nombre::{clave_nombre}")

    for clave in posibles_claves:
        if clave in cache:
            print(f"✅ [CACHE FICHA] Datos recuperados usando clave: {clave}")
            datos_cache = cache[clave]
            data_mezclada = dict(data)
            data_mezclada.update(datos_cache)
            data_mezclada["id"] = opp_id or datos_cache.get("_opp_id")
            data_mezclada["contact_id"] = contact_id or datos_cache.get("_contact_id")
            return data_mezclada

    print("⚠️ [CACHE FICHA] No se encontraron datos completos en cache.")
    return data


def escribir_excel(ws, celda, valor):
    if valor is None:
        return
    valor = str(valor).strip()
    if valor == "":
        return
    ws[celda] = valor.upper()


def marcar_excel(ws, celda, condicion):
    if condicion:
        ws[celda] = "X"


def obtener_primera_url(valor):
    if not valor:
        return ""

    if isinstance(valor, list) and len(valor) > 0:
        val = valor[0]
    else:
        val = valor

    if isinstance(val, dict):
        # Caso de diccionario anidado con UUID como clave: {'uuid': {'url': '...'}}
        if len(val) == 1 and isinstance(list(val.values())[0], dict):
            inner = list(val.values())[0]
            url = inner.get("url") or inner.get("value") or inner.get("downloadUrl")
            if url:
                return url
        url = val.get("url") or val.get("value") or val.get("downloadUrl")
        if url:
            return url

    if isinstance(val, str):
        return val.strip()

    return str(val)


def limpiar_nombre_archivo(nombre):
    nombre = str(nombre or "archivo")
    caracteres_invalidos = '<>:"/\\|?*'
    for c in caracteres_invalidos:
        nombre = nombre.replace(c, "_")
    return nombre.strip().replace(" ", "_")


# === TU FUNCIÓN ORIGINAL EXACTA DE DESCARGA ===
def descargar_imagen(url, nombre_archivo):
    if not url:
        print("⚠️ No llegó URL de imagen.")
        return None
    try:
        nombre_archivo = limpiar_nombre_archivo(nombre_archivo)
        token = os.getenv('GHL_ACCESS_TOKEN')
        location_id = os.getenv('GHL_LOCATION_ID')

        # EL PASE VIP: Agregamos alt=media y el locationId al final del link de GHL
        url = url.strip()
        separador = "&" if "?" in url else "?"
        url_final = f"{url}{separador}alt=media&locationId={location_id}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Version": "2021-04-15",
            "Accept": "*/*"
        }

        print(f"📸 Intentando descargar imagen GHL con Pase VIP: {url_final}")
        response = requests.get(url_final, headers=headers, timeout=30, allow_redirects=True)

        print("📸 Status descarga imagen:", response.status_code)

        if response.status_code != 200:
            print(f"❌ Error descargando imagen ({response.status_code}): {response.text[:200]}")
            return None

        # Convertimos la imagen asegurando compatibilidad con Excel
        imagen = PILImage.open(BytesIO(response.content))
        if imagen.mode in ("RGBA", "P"):
            imagen = imagen.convert("RGB")
        else:
            imagen = imagen.convert("RGB")

        ruta = os.path.join(CARPETA_TEMP, f"{nombre_archivo}.jpg")
        imagen.save(ruta, format="JPEG", quality=90)

        print(f"✅ Imagen descargada y convertida correctamente: {ruta}")
        return ruta

    except Exception as e:
        print(f"❌ Error descargando/convirtiendo imagen GHL: {e}")
        return None

def insertar_imagen_excel(ws, ruta_imagen, celda, ancho=330, alto=260):
    if not ruta_imagen:
        print(f"⚠️ No hay imagen para insertar en {celda}")
        return
    if not os.path.exists(ruta_imagen):
        print(f"⚠️ No existe la imagen local: {ruta_imagen}")
        return
    try:
        img = ExcelImage(ruta_imagen)
        img.width = ancho
        img.height = alto
        ws.add_image(img, celda)
        print(f"✅ Imagen insertada en Excel: {ruta_imagen} -> {celda}")
    except Exception as e:
        print(f"❌ Error insertando imagen en Excel: {e}")


def generar_excel_ficha_datos(datos):
    wb = load_workbook(RUTA_PLANTILLA_FICHA_DATOS)
    ws = wb["Ficha"]

    escribir_excel(ws, "C5", datos.get("nombre_proyecto"))
    tipo_proyecto = (datos.get("tipo_proyecto") or "").upper()
    marcar_excel(ws, "E8", tipo_proyecto == "NUEVO PREDIO")
    marcar_excel(ws, "I8", tipo_proyecto == "AMPLIACION DE TORRE")
    fuente = (datos.get("fuente_origen") or "").upper()
    marcar_excel(ws, "E12", fuente == "PROPIO")
    clasificacion = (datos.get("clasificacion") or "").upper()
    marcar_excel(ws, "E16", clasificacion == "CONDOMINIO")
    marcar_excel(ws, "I16", clasificacion == "EDIFICIO")
    tipo_construccion = (datos.get("tipo_construccion") or "").upper()
    marcar_excel(ws, "E22", tipo_construccion == "ESTRENO")
    marcar_excel(ws, "I22", tipo_construccion == "MODERNO")
    marcar_excel(ws, "L22", tipo_construccion == "ANTIGUO")
    escribir_excel(ws, "E23", datos.get("fecha_entrega_edificio"))
    escribir_excel(ws, "E25", datos.get("fecha_termino_montantes"))
    escribir_excel(ws, "E26", datos.get("fecha_termino_mecha"))
    junta = (datos.get("junta_directiva") or "").upper()
    marcar_excel(ws, "E31", junta == "SI")
    marcar_excel(ws, "I31", junta == "NO")
    escribir_excel(ws, "D34", datos.get("cargo_responsable"))
    escribir_excel(ws, "I34", datos.get("nombre_responsable"))
    escribir_excel(ws, "D35", datos.get("telefono_responsable"))
    escribir_excel(ws, "I35", datos.get("correo_responsable"))
    operador = (datos.get("operador_actual") or "").upper()
    marcar_excel(ws, "E39", operador == "MOVISTAR")
    marcar_excel(ws, "I39", operador == "NUBYX")
    marcar_excel(ws, "L39", operador == "ENTEL")
    marcar_excel(ws, "E40", operador == "CLARO")
    marcar_excel(ws, "I40", operador == "WOW")
    marcar_excel(ws, "L40", operador == "BITEL")
    marcar_excel(ws, "E42", operador == "NINGUNO")
    escribir_excel(ws, "D46", datos.get("visita_inspeccion_tecnica"))
    horario = (datos.get("rango_horario_visita") or "").upper()
    marcar_excel(ws, "I46", horario in ["9 AM A 12 AM", "9AM A 12M", "9 AM A 12M"])
    marcar_excel(ws, "L46", horario == "1 PM A 4 PM")
    escribir_excel(ws, "C50", datos.get("departamento"))
    escribir_excel(ws, "I50", datos.get("provincia"))
    escribir_excel(ws, "C51", datos.get("distrito"))
    escribir_excel(ws, "I51", datos.get("urbanizacion"))
    escribir_excel(ws, "C52", datos.get("codigo_postal"))
    escribir_excel(ws, "C53", datos.get("tipo_via"))
    escribir_excel(ws, "C54", datos.get("nombre_via"))
    escribir_excel(ws, "C55", datos.get("numero_via"))
    escribir_excel(ws, "C56", datos.get("coordenadas"))
    escribir_excel(ws, "C60", datos.get("total_torres"))
    escribir_excel(ws, "C61", datos.get("total_hogares"))
    escribir_excel(ws, "A63", f"TORRE {datos.get('nombre_torre1', '')}")
    escribir_excel(ws, "D63", datos.get("pisos_torre1"))
    escribir_excel(ws, "D64", datos.get("hogares_torre1"))
    escribir_excel(ws, "A66", f"TORRE {datos.get('nombre_torre2', '')}")
    escribir_excel(ws, "D66", datos.get("pisos_torre2"))
    escribir_excel(ws, "D67", datos.get("hogares_torre2"))
    escribir_excel(ws, "A69", f"TORRE {datos.get('nombre_torre3', '')}")
    escribir_excel(ws, "D69", datos.get("pisos_torre3"))
    escribir_excel(ws, "D70", datos.get("hogares_torre3"))
    escribir_excel(ws, "C77", datos.get("clientes_interesados"))
    escribir_excel(ws, "C81", datos.get("nombre_canal"))
    escribir_excel(ws, "C84", datos.get("gestor"))
    escribir_excel(ws, "I84", datos.get("celular_gestor"))

    insertar_imagen_excel(ws, datos.get("foto_edificio_path"), "A89", 330, 260)
    insertar_imagen_excel(ws, datos.get("foto_montantes_path"), "F89", 330, 260)

    nombre_proyecto = limpiar_nombre_archivo(datos.get("nombre_proyecto", "PROYECTO")).replace("_", " ")
    nombre_archivo = f"Ficha de Datos - {nombre_proyecto}.xlsx"
    ruta_salida = os.path.join(CARPETA_SALIDAS, nombre_archivo)
    wb.save(ruta_salida)
    return ruta_salida


def formatear_fecha(fecha):
    if not fecha: return ""
    try:
        return datetime.strptime(str(fecha), "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return str(fecha)


def construir_datos_ficha_desde_webhook(data):
    datos = {
        "nombre_proyecto": data.get("cf_nombre_proyecto") or data.get("opportunity_name"),
        "tipo_proyecto": data.get("cf_tipo_proyecto"),
        "fuente_origen": data.get("cf_fuente_hunting"),
        "clasificacion": "Condominio" if "condominio" in str(
            data.get("cf_clasificacion_proyecto", "")).lower() else "Edificio",
        "tipo_construccion": (
            "Estreno" if "estreno" in str(data.get("cf_tipo_construccion_edificio", "")).lower()
            else "Moderno" if "moderno" in str(data.get("cf_tipo_construccion_edificio", "")).lower()
            else "Antiguo" if "antiguo" in str(data.get("cf_tipo_construccion_edificio", "")).lower()
            else data.get("cf_tipo_construccion_edificio")
        ),
        "fecha_entrega_edificio": formatear_fecha(
            data.get("cf_fecha_entrega_edificio_estreno") or data.get("cf_fecha_entrega_edificio")),
        "fecha_termino_montantes": formatear_fecha(data.get("cf_fecha_termino_montantes_edificio_estreno")),
        "fecha_termino_mecha": formatear_fecha(data.get("cf_fecha_termino_mecha_edificio_estreno")),
        "junta_directiva": data.get("cf_junta_directiva"),
        "cargo_responsable": data.get("cf_cargo_responsable_edificio") or data.get("cf_cargo_responsable"),
        "nombre_responsable": data.get("cf_nombre_responsable_edificio"),
        "telefono_responsable": data.get("cf_telefono_responsable_edificio"),
        "correo_responsable": data.get("cf_correo_responsable_edificio"),
        "operador_actual": data.get("cf_operador_actual"),
        "visita_inspeccion_tecnica": formatear_fecha(data.get("cf_visita_inspeccion_tecnica_win")),
        "rango_horario_visita": data.get("cf_rango_horario_visita_tecnica"),
        "departamento": data.get("cf_departamento_edificio"),
        "provincia": data.get("cf_provincia_edificio"),
        "distrito": data.get("cf_distrito"),
        "urbanizacion": data.get("cf_urbanizacion_edificio"),
        "codigo_postal": data.get("cf_codigo_postal_edificio"),
        "tipo_via": data.get("cf_tipo_via"),
        "nombre_via": data.get("cf_nombre_via"),
        "numero_via": data.get("cf_numeracion_via"),
        "coordenadas": data.get("cf_coordenadas"),
        "total_torres": data.get("cf_total_torres_proyecto"),
        "total_hogares": data.get("cf_total_hogares_proyecto"),
        "nombre_torre1": data.get("cf_nombre_torre1_proyecto"),
        "pisos_torre1": data.get("cf_pisos_torre1_proyecto"),
        "hogares_torre1": data.get("cf_hogares_torre1_proyecto"),
        "nombre_torre2": data.get("cf_nombre_torre2_proyecto"),
        "pisos_torre2": data.get("cf_pisos_torre2_proyecto"),
        "hogares_torre2": data.get("cf_hogares_torre2_proyecto"),
        "nombre_torre3": data.get("cf_nombre_torre3_proyecto"),
        "pisos_torre3": data.get("cf_pisos_torre3_proyecto"),
        "hogares_torre3": data.get("cf_hogares_torre3_proyecto"),
        "clientes_interesados": data.get("cf_cantidad_clientes_interesados"),
        "nombre_canal": data.get("cf_nombre_cancal_hunting") or data.get("cf_nombre_canal_hunting"),
        "gestor": data.get("cf_gestor_real"),
        "celular_gestor": data.get("user", {}).get("phone", ""),
        "foto_edificio": obtener_primera_url(data.get("cf_foto_edificio")),
        "foto_montantes": obtener_primera_url(data.get("cf_foto_montantes")),
    }
    print("📸 [MAPEO] cf_foto_edificio:", data.get("cf_foto_edificio"))
    print("📸 [MAPEO] cf_foto_montantes:", data.get("cf_foto_montantes"))
    return datos