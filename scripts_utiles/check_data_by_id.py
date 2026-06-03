import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

GHL_TOKEN = os.getenv("GHL_ACCESS_TOKEN")
LOCATION_ID = os.getenv("GHL_LOCATION_ID")

headers = {
    'Authorization': f'Bearer {GHL_TOKEN}',
    'Version': '2021-04-15',
    'Content-Type': 'application/json',
}

def check_contact(contact_id):
    url = f"https://services.leadconnectorhq.com/contacts/{contact_id}"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        c_data = resp.json().get("contact", {})
        print(f"Contact ID: {contact_id}")
        print(f"Name: {c_data.get('firstName')} {c_data.get('lastName')}")
        print(f"Email: {c_data.get('email')}")
        print(f"Phone: {c_data.get('phone')}")
        print(f"Tags: {c_data.get('tags')}")
        print(f"Custom Fields:")
        for cf in c_data.get("customFields", []):
            print(f"  - ID: {cf.get('id')} | Value: {cf.get('value')}")
    else:
        print(f"Error fetching contact {contact_id}: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    import sys
    cid = sys.argv[1] if len(sys.argv) > 1 else "lzZMhpJc2YJij9yt3j8s"
    check_contact(cid)
