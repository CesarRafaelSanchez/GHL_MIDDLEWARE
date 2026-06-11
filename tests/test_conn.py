import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import socket
import urllib.request
import urllib.error
import sys

print("=== CONTAINER CONNECTIVITY TEST ===")
try:
    ip = socket.gethostbyname('services.leadconnectorhq.com')
    print(f"DNS RESOLUTION: SUCCESS (services.leadconnectorhq.com resolved to {ip})")
except Exception as e:
    print(f"DNS RESOLUTION: FAILED: {e}")
    sys.exit(1)

try:
    url = 'https://services.leadconnectorhq.com'
    req = urllib.request.urlopen(url, timeout=5)
    print(f"HTTP GET: SUCCESS (status code {req.status})")
except urllib.error.HTTPError as e:
    print(f"HTTP GET: SUCCESS (status code {e.code})")
except Exception as e:
    print(f"HTTP GET: FAILED: {e}")
    sys.exit(1)

print("=== TEST COMPLETED ===")
