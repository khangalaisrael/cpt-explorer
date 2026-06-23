"""
Extract: call Google Places Text Search (New) for each category and write
raw API responses to data/raw/YYYY-MM-DD_<category>.json.

Safety guardrails
-----------------
1. DRY_RUN=true  — reads a fixture file instead of hitting the real API.
2. MAX_API_CALLS_PER_RUN — hard cap; script aborts if exceeded.
3. Every outgoing request is logged with timestamp, category, page, status.
4. Set a $5 billing alert on Google Cloud before enabling the real API key.
"""

import json
import logging
import os
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

from category_map import (
    CATEGORY_QUERIES,
    CAPE_TOWN_NEIGHBOURHOODS,
    NEIGHBOURHOOD_TEMPLATES,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────
API_KEY             = os.getenv("GOOGLE_PLACES_API_KEY", "")
DRY_RUN             = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_RESULTS_PER_CAT = int(os.getenv("MAX_RESULTS_PER_CATEGORY", "60"))
MAX_API_CALLS       = int(os.getenv("MAX_API_CALLS_PER_RUN", "50"))
CITY                = os.getenv("CITY", "Cape Town")

PLACES_URL  = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK  = (
    "places.id,"
    "places.displayName,"
    "places.types,"
    "places.location,"
    "places.rating,"
    "places.userRatingCount,"
    "places.priceLevel,"
    "places.regularOpeningHours,"
    "places.addressComponents,"
    "nextPageToken"
)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dry_run_response.json"

# ── call counter (shared across all requests in a run) ────────────────────
_call_count = 0


def _check_call_cap() -> None:
    global _call_count
    if _call_count >= MAX_API_CALLS:
        raise RuntimeError(
            f"Hard API call cap reached ({MAX_API_CALLS}). "
            "Aborting to prevent runaway billing. "
            "Raise MAX_API_CALLS_PER_RUN in .env if this is intentional."
        )


def _make_request(payload: dict, page_token: str | None = None) -> dict:
    """Make one Text Search request (or return fixture in dry-run mode)."""
    global _call_count
    _check_call_cap()

    # Places API (New) pagination: keep original params, add pageToken
    if page_token:
        payload = {**payload, "pageToken": page_token}

    if DRY_RUN:
        log.info("[DRY-RUN] Simulating API call (call #%d)", _call_count + 1)
        _call_count += 1
        return _load_fixture()

    _call_count += 1
    log.info("API call #%d — %s", _call_count, payload.get("textQuery", "paginate"))

    resp = requests.post(
        PLACES_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        timeout=15,
    )

    log.info(
        "  status=%d  places_returned=%d",
        resp.status_code,
        len(resp.json().get("places", [])),
    )

    resp.raise_for_status()
    return resp.json()


def _load_fixture() -> dict:
    if FIXTURE_PATH.exists():
        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    # Minimal fallback fixture so dry-run works even without a saved fixture.
    return {
        "places": [
            {
                "id": "dry_run_place_001",
                "displayName": {"text": "Dry Run Cafe"},
                "types": ["cafe"],
                "location": {"latitude": -33.9249, "longitude": 18.4241},
                "rating": 4.2,
                "userRatingCount": 120,
                "priceLevel": "PRICE_LEVEL_MODERATE",
                "regularOpeningHours": None,
                "addressComponents": [
                    {"longText": "Gardens", "types": ["sublocality_level_1"]}
                ],
            }
        ]
    }


def _fetch_query(query: str, max_results: int = MAX_RESULTS_PER_CAT) -> list[dict]:
    """Fetch one Text Search query with pagination up to max_results."""
    places: list[dict] = []
    page_token: str | None = None
    page = 0
    base_payload = {"textQuery": query}

    while True:
        page += 1
        data = _make_request(base_payload, page_token=page_token)
        batch = data.get("places", [])
        places.extend(batch)
        log.info("  page=%d  fetched=%d  running_total=%d", page, len(batch), len(places))

        page_token = data.get("nextPageToken")
        if not page_token or len(places) >= max_results:
            break

        time.sleep(2)

    return places[:max_results]


def extract_category(category: str, city: str = CITY, full: bool = False) -> list[dict]:
    """
    Fetch places for one category.
    full=True also runs neighbourhood-level queries (initial/full load).
    full=False runs city-wide query only (daily refresh).
    """
    all_places: list[dict] = []
    seen_ids: set[str] = set()

    def _add(places: list[dict]) -> None:
        for p in places:
            pid = p.get("id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_places.append(p)

    # City-wide query (always runs)
    query = CATEGORY_QUERIES[category].format(city=city)
    log.info("Extracting category=%s  query=%r", category, query)
    _add(_fetch_query(query))

    if full:
        template = NEIGHBOURHOOD_TEMPLATES[category]
        for area in CAPE_TOWN_NEIGHBOURHOODS:
            nq = template.format(area=area)
            log.info("  neighbourhood query: %r", nq)
            _add(_fetch_query(nq, max_results=60))  # up to 3 pages per neighbourhood

    log.info("category=%s  total_unique=%d", category, len(all_places))
    return all_places


def run(city: str = CITY, full: bool = False) -> dict[str, Path]:
    """
    Run extraction for all 7 categories.
    full=True: runs neighbourhood queries too (use for initial/full load).
    full=False: city-wide only (use for daily refresh).
    Returns {category: path_to_raw_file}.
    """
    if DRY_RUN:
        log.warning("DRY_RUN=true — no real API calls will be made.")
    elif not API_KEY:
        raise ValueError("GOOGLE_PLACES_API_KEY is not set in .env")

    mode = "full" if full else "refresh"
    log.info("Extract mode: %s", mode)

    today = date.today().isoformat()
    written: dict[str, Path] = {}

    for category in CATEGORY_QUERIES:
        places = extract_category(category, city=city, full=full)
        out_path = RAW_DIR / f"{today}_{category}.json"
        out_path.write_text(
            json.dumps({"category": category, "city": city, "places": places}, indent=2),
            encoding="utf-8",
        )
        log.info("Wrote %d places → %s", len(places), out_path)
        written[category] = out_path

    log.info("Extraction complete. Total API calls this run: %d", _call_count)
    return written


if __name__ == "__main__":
    import sys
    full_mode = "--full" in sys.argv
    run(full=full_mode)
