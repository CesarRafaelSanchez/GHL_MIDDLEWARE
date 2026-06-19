import requests

GHL_TOKEN = "pit-91efad56-ae58-41d7-85f6-6b66504b7e16"
LOCATION_ID = "dHdydlGzW0HODg6XDQe7"

url = f"https://services.leadconnectorhq.com/opportunities/pipelines?locationId={LOCATION_ID}"
headers = {
    "Authorization": f"Bearer {GHL_TOKEN}",
    "Version": "2021-04-15"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    pipelines = response.json().get("pipelines", [])
    for pipe in pipelines:
        print(f"\n[PIPELINE] {pipe.get('name')} | ID: {pipe.get('id')}")
        print("-" * 50)
        for stage in pipe.get("stages", []):
            print(f"   -> STAGE: {stage.get('name')} | ID: {stage.get('id')}")
else:
    print("Error:", response.text)