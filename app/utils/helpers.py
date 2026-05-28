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