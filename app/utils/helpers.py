def obtener_campo(payload, key):
    if key in payload: return payload[key]
    cf = payload.get("customFields", {})
    if isinstance(cf, dict) and key in cf: return cf[key]
    return None


def limpiar_valor_campo_para_ghl(val):
    if not val:
        return val

    # Si es una lista
    if isinstance(val, list):
        if len(val) == 0:
            return val
        limpios = []
        for v in val:
            if isinstance(v, dict):
                url = v.get("url") or v.get("value") or v.get("downloadUrl")
                if url:
                    limpios.append(url)
            elif isinstance(v, str):
                limpios.append(v)
        return limpios if limpios else val

    # Si es un diccionario (como el formato de archivo de GHL: {'uuid': {'url': '...'}})
    if isinstance(val, dict):
        limpios = []
        for k, v in val.items():
            if isinstance(v, dict):
                url = v.get("url") or v.get("value") or v.get("downloadUrl")
                if url:
                    limpios.append(url)
            elif k == "url" and isinstance(v, str):
                return [v]
        if limpios:
            return limpios

    return val


MAPA_KEYS_A_IDS = {}

def obtener_mapa_keys_a_ids():
    global MAPA_KEYS_A_IDS
    if MAPA_KEYS_A_IDS:
        return MAPA_KEYS_A_IDS

    import os
    token = os.getenv("GHL_ACCESS_TOKEN")
    location_id = os.getenv("GHL_LOCATION_ID")

    if not token or not location_id:
        print("⚠️ [MAPEO GHL] Falta GHL_ACCESS_TOKEN o GHL_LOCATION_ID en variables de entorno.", flush=True)
        return {}

    try:
        url = f"https://services.leadconnectorhq.com/locations/{location_id}/customFields"
        headers = {
            "Authorization": f"Bearer {token}",
            "Version": "2021-04-15",
            "Content-Type": "application/json"
        }
        session = obtener_session_con_retries()
        res = session.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            fields = res.json().get("customFields", [])
            mapa = {}
            for f in fields:
                field_id = f.get("id")
                name = f.get("name") or ""
                field_key = f.get("fieldKey") or ""
                if "." in field_key:
                    field_key = field_key.split(".")[-1]

                if name:
                    mapa[name] = field_id
                if field_key:
                    mapa[field_key] = field_id
            MAPA_KEYS_A_IDS = mapa
            print(f"📦 [MAPEO GHL] Mapa de custom fields construido con {len(mapa)} campos.", flush=True)
            return MAPA_KEYS_A_IDS
        else:
            print(f"⚠️ [MAPEO GHL] Error API GHL ({res.status_code}): {res.text}", flush=True)
    except Exception as e:
        print(f"⚠️ [MAPEO GHL] Error al obtener custom fields: {e}", flush=True)
    return {}


def extraer_custom_fields_para_ghl(datos_formulario):
    cf_array = []
    fuente = datos_formulario.get("customFields", datos_formulario)

    # Obtener el mapa de traducción de GHL
    mapa_ids = obtener_mapa_keys_a_ids()

    if isinstance(fuente, dict):
        for k, v in fuente.items():
            if k.startswith("cf_") and v is not None and v != "":
                # Traducir la clave al ID real
                field_id = mapa_ids.get(k)
                if not field_id:
                    field_id = k

                valor_limpio = limpiar_valor_campo_para_ghl(v)
                cf_array.append({"id": field_id, "value": valor_limpio})
    return cf_array

def obtener_session_con_retries():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util import Retry

    class TimeoutSession(requests.Session):
        def request(self, *args, **kwargs):
            if 'timeout' not in kwargs:
                kwargs['timeout'] = 20
            return super().request(*args, **kwargs)

    session = TimeoutSession()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504, 520, 521, 522, 524],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
