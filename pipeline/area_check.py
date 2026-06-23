import psycopg2, os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
area = sys.argv[1] if len(sys.argv) > 1 else "Sea Point"
conn = psycopg2.connect(os.getenv("SUPABASE_DB_URL"))
cur = conn.cursor()
cur.execute("SELECT category, COUNT(*) FROM venues WHERE area ILIKE %s GROUP BY category ORDER BY COUNT(*) DESC", (f"%{area}%",))
rows = cur.fetchall()
total = sum(r[1] for r in rows)
print(f"Venues in '{area}' — total: {total}")
for r in rows:
    print(f"  {r[0]}: {r[1]}")
conn.close()
