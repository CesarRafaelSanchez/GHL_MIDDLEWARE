import requests

# Tus credenciales
GHL_ACCESS_TOKEN = "pit-91efad56-ae58-41d7-85f6-6b66504b7e16"
GHL_LOCATION_ID = "dHdydlGzW0HODg6XDQe7"

# Endpoint de la API V2 para obtener usuarios por Location
url = f"https://services.leadconnectorhq.com/users/?locationId={GHL_LOCATION_ID}"

headers = {
    "Authorization": f"Bearer {GHL_ACCESS_TOKEN}",
    "Version": "2021-07-28",
    "Accept": "application/json"
}


def obtener_usuarios():
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        users = data.get("users", [])

        print(f"Total de usuarios encontrados: {len(users)}\n")
        print("-" * 50)

        for user in users:
            nombre = f"{user.get('firstName', '')} {user.get('lastName', '')}".strip()
            user_id = user.get('id')
            email = user.get('email')

            # Imprimimos los datos de cada usuario
            print(f"Nombre: {nombre}")
            print(f"ID:     {user_id}")
            print(f"Email:  {email}")
            print("-" * 50)

    else:
        print(f"Error en la petición: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    obtener_usuarios()