import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('GHL_ACCESS_TOKEN')
loc = os.getenv('GHL_LOCATION_ID')

headers = {
    'Authorization': f'Bearer {token}',
    'Version': '2021-04-15'
}

url = f"https://services.leadconnectorhq.com/locations/{loc}/customFields"
response = requests.get(url, headers=headers)

if response.status_code == 200:
    fields = response.json().get("customFields", [])
    print(f"Total custom fields found: {len(fields)}")
    for f in fields:
        print(f"ID: {f.get('id'):25} | Name: {f.get('name'):30} | Key: {f.get('fieldKey'):30}")
else:
    print("Error:", response.status_code, response.text)
