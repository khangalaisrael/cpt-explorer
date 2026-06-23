"""
Transform: read raw JSON staging files → map types → normalize fields →
dedupe on place_id → return list of venue dicts ready for upsert.

Never calls the API. Reads only from data/raw/.
"""

import json
import logging
from pathlib import Path

from category_map import map_category

log = logging.getLogger(__name__)

PRICE_LEVEL_MAP = {
    "PRICE_LEVEL_FREE":          0,
    "PRICE_LEVEL_INEXPENSIVE":   1,
    "PRICE_LEVEL_MODERATE":      2,
    "PRICE_LEVEL_EXPENSIVE":     3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}

AREA_TYPES = {"sublocality_level_1", "sublocality", "neighborhood"}


def _extract_area(address_components: list[dict] | None) -> str | None:
    if not address_components:
        return None
    for component in address_components:
        component_types = set(component.get("types", []))
        if component_types & AREA_TYPES:
            return component.get("longText") or component.get("short_text")
    return None


def _normalize_price_level(raw: str | int | None) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw if 0 <= raw <= 4 else None
    return PRICE_LEVEL_MAP.get(str(raw))


def transform_place(raw: dict, category: str, city: str) -> dict | None:
    """
    Convert one raw Places API place dict into a venue dict.
    Returns None if required fields are missing.
    """
    place_id = raw.get("id")
    name_obj = raw.get("displayName", {})
    name = name_obj.get("text") if isinstance(name_obj, dict) else name_obj
    location = raw.get("location", {})
    lat = location.get("latitude")
    lng = location.get("longitude")

    if not all([place_id, name, lat is not None, lng is not None]):
        log.warning("Skipping place with missing required fields: %s", raw.get("id"))
        return None

    return {
        "place_id":     place_id,
        "name":         name,
        "category":     category,
        "city":         city,
        "area":         _extract_area(raw.get("addressComponents")),
        "lat":          lat,
        "lng":          lng,
        "rating":       raw.get("rating"),
        "review_count": raw.get("userRatingCount"),
        "price_level":  _normalize_price_level(raw.get("priceLevel")),
        "opening_hours": raw.get("regularOpeningHours"),
        # LLM enrichment fields — left NULL at ingest, filled by Phase 2
        "cuisine":               None,
        "cuisine_confidence":    None,
        "is_date_spot":          False,
        "date_spot_confidence":  None,
        "review_summary":        None,
        "standout_items":        None,
        "common_complaints":     None,
    }


def transform_file(raw_path: Path) -> tuple[list[dict], dict]:
    """
    Transform one raw staging file.
    Returns (venues, stats) where stats has counts for logging.
    """
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    category = data.get("category", "unknown")
    city = data.get("city", "Cape Town")
    raw_places = data.get("places", [])

    venues: list[dict] = []
    stats = {"input": len(raw_places), "output": 0, "skipped_no_category": 0,
             "skipped_missing_fields": 0}

    for place in raw_places:
        types = place.get("types", [])
        name = (place.get("displayName") or {}).get("text", "")

        resolved_category = map_category(types, name)
        if resolved_category is None:
            log.debug("No category match for %r (types=%s)", name, types)
            stats["skipped_no_category"] += 1
            continue

        venue = transform_place(place, resolved_category, city)
        if venue is None:
            stats["skipped_missing_fields"] += 1
            continue

        venues.append(venue)

    stats["output"] = len(venues)
    return venues, stats


def run(raw_paths: list[Path]) -> list[dict]:
    """
    Transform all raw files, dedupe on place_id, return upsert-ready list.
    """
    all_venues: list[dict] = []
    seen_ids: set[str] = set()
    total_stats = {"input": 0, "output": 0, "skipped_no_category": 0,
                   "skipped_missing_fields": 0, "dupes_dropped": 0}

    for path in raw_paths:
        venues, stats = transform_file(path)
        for k in ("input", "output", "skipped_no_category", "skipped_missing_fields"):
            total_stats[k] += stats[k]

        for venue in venues:
            pid = venue["place_id"]
            if pid in seen_ids:
                log.debug("Duplicate place_id skipped: %s (%s)", pid, venue["name"])
                total_stats["dupes_dropped"] += 1
                continue
            seen_ids.add(pid)
            all_venues.append(venue)

    log.info(
        "Transform summary — input: %d | output: %d | "
        "skipped (no category): %d | skipped (missing fields): %d | dupes dropped: %d",
        total_stats["input"], total_stats["output"],
        total_stats["skipped_no_category"], total_stats["skipped_missing_fields"],
        total_stats["dupes_dropped"],
    )
    return all_venues


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    paths = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else []
    if not paths:
        raw_dir = Path(__file__).parent.parent / "data" / "raw"
        paths = sorted(raw_dir.glob("*.json"))
    result = run(paths)
    print(f"Transformed {len(result)} venues")
