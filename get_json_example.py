import json
import requests

ACCESS_TOKEN = "pit-91efad56-ae58-41d7-85f6-6b66504b7e16"
LOCATION_ID = "dHdydlGzW0HODg6XDQe7"

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Version": "2021-04-15",
    "Accept": "application/json",
    "Content-Type": "application/json"
}


def obtener_json_oportunidad():
    search_url = "https://services.leadconnectorhq.com/opportunities/search"
    payload = {
        "locationId": LOCATION_ID,
        "limit": 1
    }

    try:
        search_response = requests.post(search_url, headers=HEADERS, json=payload)

        # GHL devuelve 201 en este endpoint, aceptamos ambos estatus de éxito
        if search_response.status_code in [200, 201]:
            search_data = search_response.json()
            opportunities = search_data.get("opportunities", [])

            if not opportunities:
                print(json.dumps({"error": "No se encontraron oportunidades."}, indent=2))
                return

            # Extraemos y mostramos únicamente el primer lead del arreglo
            lead_real_json = opportunities[0]
            print(json.dumps(lead_real_json, indent=2, ensure_ascii=False))

        else:
            print(json.dumps({"error": f"API Error {search_response.status_code}", "detail": search_response.text},
                             indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))


if __name__ == "__main__":
    obtener_json_oportunidad()