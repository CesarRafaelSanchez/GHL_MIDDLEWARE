import os
import sqlite3
import json
from datetime import datetime

# Resolviendo rutas del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "storage", "ghl_system.db")
ARCHIVO_CACHE_FICHAS = os.path.join(BASE_DIR, "storage", "cache_fichas_datos.json")

def normalizar_clave_proyecto(nombre):
    return str(nombre or "").strip().upper()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa la base de datos SQLite con la estructura de oportunidades_ficha."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS oportunidades_ficha (
        oportunidad_id TEXT PRIMARY KEY,
        contacto_id TEXT,
        nombre_proyecto TEXT,
        tipo_proyecto TEXT,
        fuente_origen TEXT,
        clasificacion TEXT,
        tipo_construccion TEXT,
        fecha_entrega_edificio TEXT,
        fecha_termino_montantes TEXT,
        fecha_termino_mecha TEXT,
        junta_directiva TEXT,
        cargo_responsable TEXT,
        nombre_responsable TEXT,
        telefono_responsable TEXT,
        correo_responsable TEXT,
        hogares_por_piso_torre1 TEXT,
        hogares_por_piso_torre2 TEXT,
        hogares_por_piso_torre3 TEXT,
        visita_inspeccion_tecnica TEXT,
        rango_horario_visita TEXT,
        departamento TEXT,
        provincia TEXT,
        distrito TEXT,
        urbanizacion TEXT,
        codigo_postal TEXT,
        tipo_via TEXT,
        nombre_via TEXT,
        numero_via TEXT,
        coordenadas TEXT,
        total_torres TEXT,
        total_hogares TEXT,
        nombre_torre1 TEXT,
        pisos_torre1 TEXT,
        hogares_torre1 TEXT,
        nombre_torre2 TEXT,
        pisos_torre2 TEXT,
        hogares_torre2 TEXT,
        nombre_torre3 TEXT,
        pisos_torre3 TEXT,
        hogares_torre3 TEXT,
        clientes_interesados TEXT,
        nombre_canal TEXT,
        gestor TEXT,
        celular_gestor TEXT,
        foto_edificio TEXT,
        foto_montantes TEXT,
        foto_edificio_path TEXT,
        foto_montantes_path TEXT,
        actualizado_el TEXT,
        raw_json TEXT
    );
    """)
    conn.commit()
    conn.close()
    print("🗄️ [DB INIT] Base de datos y tablas verificadas.")
    
    # Ejecutar la migración si es necesaria
    migrar_json_a_sqlite()

def migrar_json_a_sqlite():
    """Migra los datos del antiguo archivo cache_fichas_datos.json a SQLite si la base de datos está vacía."""
    if not os.path.exists(ARCHIVO_CACHE_FICHAS):
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Validamos si la tabla ya tiene registros
    cursor.execute("SELECT COUNT(*) FROM oportunidades_ficha")
    count = cursor.fetchone()[0]
    
    if count > 0:
        conn.close()
        return
        
    print("🚚 [MIGRACION] Iniciando migración de cache_fichas_datos.json a SQLite...")
    try:
        with open(ARCHIVO_CACHE_FICHAS, "r", encoding="utf-8") as f:
            cache = json.load(f)
            
        from app.services.ficha_service import construir_datos_ficha_desde_webhook
        
        migrados = 0
        for clave, raw_datos in cache.items():
            # Solo procesamos los registros indexados por oportunidad para no duplicar por contacto/nombre
            if not clave.startswith("opp::"):
                continue
                
            opp_id = clave.split("::")[1]
            contacto_id = raw_datos.get("_contact_id")
            
            # Mapeamos los datos simulando el flujo del webhook
            datos_mapeados = construir_datos_ficha_desde_webhook(raw_datos)
            
            # Incorporamos los campos de imágenes que se guardaron en la caché
            datos_mapeados["foto_edificio_path"] = raw_datos.get("foto_edificio_path")
            datos_mapeados["foto_montantes_path"] = raw_datos.get("foto_montantes_path")
            
            guardar_oportunidad_db_internal(cursor, opp_id, contacto_id, datos_mapeados, raw_datos)
            migrados += 1
            
        conn.commit()
        print(f"✅ [MIGRACION] Se migraron exitosamente {migrados} registros a SQLite.")
    except Exception as e:
        print(f"❌ [MIGRACION] Error al migrar caché JSON: {e}")
    finally:
        conn.close()

def guardar_oportunidad_db_internal(cursor, opp_id, contact_id, datos_mapeados, raw_datos):
    """Guarda o actualiza de manera interna una oportunidad en la base de datos usando el cursor provisto."""
    query = """
    INSERT INTO oportunidades_ficha (
        oportunidad_id, contacto_id, nombre_proyecto, tipo_proyecto, fuente_origen, clasificacion,
        tipo_construccion, fecha_entrega_edificio, fecha_termino_montantes, fecha_termino_mecha,
        junta_directiva, cargo_responsable, nombre_responsable, telefono_responsable, correo_responsable,
        hogares_por_piso_torre1, hogares_por_piso_torre2, hogares_por_piso_torre3, visita_inspeccion_tecnica,
        rango_horario_visita, departamento, provincia, distrito, urbanizacion, codigo_postal,
        tipo_via, nombre_via, numero_via, coordenadas, total_torres, total_hogares,
        nombre_torre1, pisos_torre1, hogares_torre1, nombre_torre2, pisos_torre2, hogares_torre2,
        nombre_torre3, pisos_torre3, hogares_torre3, clientes_interesados, nombre_canal, gestor,
        celular_gestor, foto_edificio, foto_montantes, foto_edificio_path, foto_montantes_path,
        actualizado_el, raw_json
    ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
    ) ON CONFLICT(oportunidad_id) DO UPDATE SET
        contacto_id = excluded.contacto_id,
        nombre_proyecto = excluded.nombre_proyecto,
        tipo_proyecto = excluded.tipo_proyecto,
        fuente_origen = excluded.fuente_origen,
        clasificacion = excluded.clasificacion,
        tipo_construccion = excluded.tipo_construccion,
        fecha_entrega_edificio = excluded.fecha_entrega_edificio,
        fecha_termino_montantes = excluded.fecha_termino_montantes,
        fecha_termino_mecha = excluded.fecha_termino_mecha,
        junta_directiva = excluded.junta_directiva,
        cargo_responsable = excluded.cargo_responsable,
        nombre_responsable = excluded.nombre_responsable,
        telefono_responsable = excluded.telefono_responsable,
        correo_responsable = excluded.correo_responsable,
        hogares_por_piso_torre1 = excluded.hogares_por_piso_torre1,
        hogares_por_piso_torre2 = excluded.hogares_por_piso_torre2,
        hogares_por_piso_torre3 = excluded.hogares_por_piso_torre3,
        visita_inspeccion_tecnica = excluded.visita_inspeccion_tecnica,
        rango_horario_visita = excluded.rango_horario_visita,
        departamento = excluded.departamento,
        provincia = excluded.provincia,
        distrito = excluded.distrito,
        urbanizacion = excluded.urbanizacion,
        codigo_postal = excluded.codigo_postal,
        tipo_via = excluded.tipo_via,
        nombre_via = excluded.nombre_via,
        numero_via = excluded.numero_via,
        coordenadas = excluded.coordenadas,
        total_torres = excluded.total_torres,
        total_hogares = excluded.total_hogares,
        nombre_torre1 = excluded.nombre_torre1,
        pisos_torre1 = excluded.pisos_torre1,
        hogares_torre1 = excluded.hogares_torre1,
        nombre_torre2 = excluded.nombre_torre2,
        pisos_torre2 = excluded.pisos_torre2,
        hogares_torre2 = excluded.hogares_torre2,
        nombre_torre3 = excluded.nombre_torre3,
        pisos_torre3 = excluded.pisos_torre3,
        hogares_torre3 = excluded.hogares_torre3,
        clientes_interesados = excluded.clientes_interesados,
        nombre_canal = excluded.nombre_canal,
        gestor = excluded.gestor,
        celular_gestor = excluded.celular_gestor,
        foto_edificio = excluded.foto_edificio,
        foto_montantes = excluded.foto_montantes,
        foto_edificio_path = COALESCE(excluded.foto_edificio_path, oportunidades_ficha.foto_edificio_path),
        foto_montantes_path = COALESCE(excluded.foto_montantes_path, oportunidades_ficha.foto_montantes_path),
        actualizado_el = excluded.actualizado_el,
        raw_json = excluded.raw_json;
    """
    
    cursor.execute(query, (
        opp_id,
        contact_id,
        datos_mapeados.get("nombre_proyecto"),
        datos_mapeados.get("tipo_proyecto"),
        datos_mapeados.get("fuente_origen"),
        datos_mapeados.get("clasificacion"),
        datos_mapeados.get("tipo_construccion"),
        datos_mapeados.get("fecha_entrega_edificio"),
        datos_mapeados.get("fecha_termino_montantes"),
        datos_mapeados.get("fecha_termino_mecha"),
        datos_mapeados.get("junta_directiva"),
        datos_mapeados.get("cargo_responsable"),
        datos_mapeados.get("nombre_responsable"),
        datos_mapeados.get("telefono_responsable"),
        datos_mapeados.get("correo_responsable"),
        datos_mapeados.get("hogares_por_piso_torre1"),
        datos_mapeados.get("hogares_por_piso_torre2"),
        datos_mapeados.get("hogares_por_piso_torre3"),
        datos_mapeados.get("visita_inspeccion_tecnica"),
        datos_mapeados.get("rango_horario_visita"),
        datos_mapeados.get("departamento"),
        datos_mapeados.get("provincia"),
        datos_mapeados.get("distrito"),
        datos_mapeados.get("urbanizacion"),
        datos_mapeados.get("codigo_postal"),
        datos_mapeados.get("tipo_via"),
        datos_mapeados.get("nombre_via"),
        datos_mapeados.get("numero_via"),
        datos_mapeados.get("coordenadas"),
        datos_mapeados.get("total_torres"),
        datos_mapeados.get("total_hogares"),
        datos_mapeados.get("nombre_torre1"),
        datos_mapeados.get("pisos_torre1"),
        datos_mapeados.get("hogares_torre1"),
        datos_mapeados.get("nombre_torre2"),
        datos_mapeados.get("pisos_torre2"),
        datos_mapeados.get("hogares_torre2"),
        datos_mapeados.get("nombre_torre3"),
        datos_mapeados.get("pisos_torre3"),
        datos_mapeados.get("hogares_torre3"),
        datos_mapeados.get("clientes_interesados"),
        datos_mapeados.get("nombre_canal"),
        datos_mapeados.get("gestor"),
        datos_mapeados.get("celular_gestor"),
        datos_mapeados.get("foto_edificio"),
        datos_mapeados.get("foto_montantes"),
        datos_mapeados.get("foto_edificio_path"),
        datos_mapeados.get("foto_montantes_path"),
        datetime.now().isoformat(),
        json.dumps(raw_datos, ensure_ascii=False)
    ))

def guardar_oportunidad_db(opp_id, contact_id, datos_mapeados, raw_datos):
    """Interfaz pública para guardar o actualizar una oportunidad en la base de datos SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        guardar_oportunidad_db_internal(cursor, opp_id, contact_id, datos_mapeados, raw_datos)
        conn.commit()
    except Exception as e:
        print(f"❌ [DB SAVE] Error al guardar oportunidad {opp_id}: {e}")
    finally:
        conn.close()

def obtener_oportunidad_db(opp_id=None, contact_id=None, nombre_proyecto=None):
    """Busca una oportunidad en la base de datos SQLite por opp_id, contact_id o nombre_proyecto."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = None
    
    try:
        if opp_id:
            cursor.execute("SELECT * FROM oportunidades_ficha WHERE oportunidad_id = ?", (opp_id,))
            row = cursor.fetchone()
        elif contact_id:
            cursor.execute("SELECT * FROM oportunidades_ficha WHERE contacto_id = ?", (contact_id,))
            row = cursor.fetchone()
        elif nombre_proyecto:
            clave = normalizar_clave_proyecto(nombre_proyecto)
            # Para buscar por nombre, comparamos en mayúsculas sin espacios
            cursor.execute("SELECT * FROM oportunidades_ficha WHERE UPPER(TRIM(nombre_proyecto)) = ?", (clave,))
            row = cursor.fetchone()
    except Exception as e:
        print(f"❌ [DB READ] Error al leer oportunidad: {e}")
    finally:
        conn.close()
        
    return dict(row) if row else None
