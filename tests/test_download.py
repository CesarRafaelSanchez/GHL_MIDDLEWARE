import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ficha_service import descargar_imagen
import os
import sys

# Forzar carga de variables de entorno (por si acaso)
os.environ["GHL_ACCESS_TOKEN"] = "pit-91efad56-ae58-41d7-85f6-6b66504b7e16"
os.environ["GHL_LOCATION_ID"] = "dHdydlGzW0HODg6XDQe7"

url = "https://services.leadconnectorhq.com/documents/download/7ZeNqNpB7XXlxRMSEinp"
print("=== TESTING IMAGE DOWNLOAD ===")
print("URL:", url)
path = descargar_imagen(url, "TEST_DOWNLOAD_EDIFICIO")
print("RESULT PATH:", path)
print("=== TEST COMPLETED ===")
