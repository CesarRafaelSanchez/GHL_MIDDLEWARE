import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests
import sys

print("=== CONTAINER REQUESTS TEST ===")
try:
    headers = {
        "Authorization": "Bearer pit-91efad56-ae58-41d7-85f6-6b66504b7e16",
        "Version": "2021-04-15"
    }
    url = "https://services.leadconnectorhq.com/opportunities/search?location_id=dHdydlGzW0HODg6XDQe7&pipeline_id=LPfxv2sqrrNOTtjbWZ3h&q=CONNECT"
    print("Sending request to GoHighLevel...")
    res = requests.get(url, headers=headers, timeout=10)
    print(f"Response status: {res.status_code}")
    print(f"Response JSON keys: {list(res.json().keys()) if res.status_code == 200 else res.text[:200]}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

print("=== TEST COMPLETED ===")
