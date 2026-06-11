import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import os
print("=== CONTAINER ENVIRONMENT VARIABLES ===")
print("GHL_ACCESS_TOKEN:", os.getenv("GHL_ACCESS_TOKEN"))
print("GHL_LOCATION_ID:", os.getenv("GHL_LOCATION_ID"))
print("PIPELINE_ID:", os.getenv("PIPELINE_ID"))
print("=== END ===")
