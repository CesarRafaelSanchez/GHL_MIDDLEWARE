import os
import sqlite3
import requests

GHL_TOKEN = "pit-91efad56-ae58-41d7-85f6-6b66504b7e16"
HEADERS = {
    "Authorization": f"Bearer {GHL_TOKEN}",
    "Version": "2021-04-15"
}

def clean():
    db_path = "storage/ghl_system.db"
    if not os.path.exists(db_path):
        print("Database not found locally.")
        return
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT oportunidad_id, nombre_proyecto FROM oportunidades_ficha WHERE nombre_proyecto LIKE 'GENESIS TEST%'")
    rows = cursor.fetchall()
    
    if not rows:
        print("No test projects found to clean.")
        conn.close()
        return
        
    for row in rows:
        opp_id = row["oportunidad_id"]
        name = row["nombre_proyecto"]
        print(f"Cleaning test project: {name} (ID: {opp_id})")
        
        # Delete from GHL
        try:
            res = requests.delete(f"https://services.leadconnectorhq.com/opportunities/{opp_id}", headers=HEADERS)
            print(f"  GHL delete status: {res.status_code}")
        except Exception as e:
            print(f"  Error deleting from GHL: {e}")
            
        # Delete from SQLite
        try:
            cursor.execute("DELETE FROM oportunidades_ficha WHERE oportunidad_id = ?", (opp_id,))
            print("  Deleted from local cache SQLite database.")
        except Exception as e:
            print(f"  Error deleting from SQLite: {e}")
            
    conn.commit()
    conn.close()

if __name__ == "__main__":
    clean()
