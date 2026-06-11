import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import os
import requests

GHL_TOKEN = os.getenv("GHL_ACCESS_TOKEN") or "pit-91efad56-ae58-41d7-85f6-6b66504b7e16"

headers = {
    "Authorization": f"Bearer {GHL_TOKEN}",
    "Version": "2021-04-15"
}

contact_id = "uoDBnPWGgxCydnRy0voA"
url = f"https://services.leadconnectorhq.com/contacts/{contact_id}"

print("Fetching contact details from GHL...")
res = requests.get(url, headers=headers)
print(f"Status Code: {res.status_code}")
if res.status_code == 200:
    import json
    print(json.dumps(res.json(), indent=2))
else:
    print(res.text)
