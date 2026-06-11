import os
import sys

# Asegurar que el path del proyecto esté en sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ghl_api import sync_contact_and_company_to_ghl

def test():
    contact_id = "uoDBnPWGgxCydnRy0voA"  # ID de contacto para Antamina
    fields = {
        "nombre_responsable": "Josue Sanchez Test",
        "correo_responsable": "cesarrafsanchez@gmail.com",
        "telefono_responsable": "+51932068040",
        "nombre_proyecto": "Antamina",
        "tipo_via": "Avenida",
        "nombre_via": "Republica de Panama",
        "urbanizacion": "Las Casuarinas",
        "distrito": "Ate",
        "coordenadas": "-23423.-23423",
        "provincia": "Lima",
        "departamento": "Lima",
        "codigo_postal": "1861"
    }
    
    print("🚀 Iniciando test de sincronización manual...")
    success = sync_contact_and_company_to_ghl(contact_id, fields)
    print(f"✨ Resultado: {'SINCRO EXITOSA' if success else 'FALLÓ LA SINCRO'}")

if __name__ == "__main__":
    test()
