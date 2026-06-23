import psycopg2, os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
term = sys.argv[1] if len(sys.argv) > 1 else "mykonos"
conn = psycopg2.connect(os.getenv("SUPABASE_DB_URL"))
cur = conn.cursor()
cur.execute("SELECT name, category, area, rating FROM venues WHERE name ILIKE %s", (f"%{term}%",))
rows = cur.fetchall()
print(f"Found {len(rows)} venues matching '{term}':")
for r in rows:
    print(f"  {r[0]} | {r[1]} | {r[2]} | rating={r[3]}")
conn.close()
