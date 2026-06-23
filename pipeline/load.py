"""
Load: upsert venue dicts into Postgres via psycopg2.

ON CONFLICT (place_id) DO UPDATE updates all pipeline-sourced fields but
intentionally excludes LLM-enrichment fields so a re-run never overwrites
Phase 2 work.
"""

import json
import logging
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO venues (
    place_id, name, category, city, area,
    lat, lng, rating, review_count, price_level,
    opening_hours
)
VALUES %s
ON CONFLICT (place_id) DO UPDATE SET
    name            = EXCLUDED.name,
    category        = EXCLUDED.category,
    city            = EXCLUDED.city,
    area            = EXCLUDED.area,
    lat             = EXCLUDED.lat,
    lng             = EXCLUDED.lng,
    rating          = EXCLUDED.rating,
    review_count    = EXCLUDED.review_count,
    price_level     = EXCLUDED.price_level,
    opening_hours   = EXCLUDED.opening_hours,
    updated_at      = now()
-- cuisine, is_date_spot, review_summary etc. are NOT in this UPDATE
-- so Phase 2 enrichment is never overwritten by a re-run.
"""


def _venue_to_row(v: dict) -> tuple:
    opening = v.get("opening_hours")
    return (
        v["place_id"],
        v["name"],
        v["category"],
        v["city"],
        v.get("area"),
        v["lat"],
        v["lng"],
        v.get("rating"),
        v.get("review_count"),
        v.get("price_level"),
        json.dumps(opening) if opening else None,
    )


def run(venues: list[dict]) -> tuple[int, int]:
    """
    Upsert venues into Postgres.
    Returns (rows_affected, len(venues)) — rows_affected from psycopg2.
    """
    if not venues:
        log.info("No venues to load.")
        return 0, 0

    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL is not set in .env")

    rows = [_venue_to_row(v) for v in venues]

    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, UPSERT_SQL, rows, page_size=100)
            rows_affected = cur.rowcount
        conn.commit()

    log.info("Load complete — venues submitted: %d | rows affected: %d",
             len(venues), rows_affected)
    return rows_affected, len(venues)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    # Quick smoke-test: load a single dummy venue to verify DB connection.
    test_venue = {
        "place_id": "smoke_test_001",
        "name": "Smoke Test Venue",
        "category": "cafe",
        "city": "Cape Town",
        "area": "City Bowl",
        "lat": -33.9249,
        "lng": 18.4241,
        "rating": 4.0,
        "review_count": 10,
        "price_level": 2,
        "opening_hours": None,
    }
    affected, total = run([test_venue])
    print(f"Smoke test done — affected={affected}, submitted={total}")
