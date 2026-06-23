import psycopg2, os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
conn = psycopg2.connect(os.getenv("SUPABASE_DB_URL"))
cur = conn.cursor()
cur.execute("SELECT name, category, area FROM venues WHERE name ILIKE %s OR name ILIKE %s OR name ILIKE %s ORDER BY name", ("%kayak%", "%seal%", "%cruise%"))
rows = cur.fetchall()
print(f"Found {len(rows)} venues:")
for row in rows:
    print(f"  {row[0]} | {row[1]} | {row[2]}")
conn.close()
