"""
Orchestrator: extract → transform → load.
Exits 0 on success, 1 on failure.
Run this file from n8n's Execute Command node.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Allow running from project root or pipeline/ directory
sys.path.insert(0, str(Path(__file__).parent))

import extract
import transform
import load


def main() -> int:
    city = os.getenv("CITY", "Cape Town")
    full = "--full" in sys.argv
    log.info("=== Pipeline start  city=%s  dry_run=%s  mode=%s ===",
             city, extract.DRY_RUN, "full" if full else "refresh")

    # ── 1. Extract ──────────────────────────────────────────────────────────
    try:
        raw_paths = extract.run(city=city, full=full)
        log.info("Extract done — %d category files written", len(raw_paths))
    except Exception as exc:
        log.error("Extract failed: %s", exc)
        return 1

    # ── 2. Transform ────────────────────────────────────────────────────────
    try:
        venues = transform.run(list(raw_paths.values()))
        log.info("Transform done — %d venues ready to load", len(venues))
    except Exception as exc:
        log.error("Transform failed: %s", exc)
        return 1

    if not venues:
        log.warning("No venues produced by transform — nothing to load.")
        return 0

    # ── 3. Load ─────────────────────────────────────────────────────────────
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    if dry_run:
        log.warning("DRY_RUN=true — skipping database load. Set DRY_RUN=false to load real data.")
        log.info("Sample venue that would be loaded: %s", venues[0])
        return 0

    try:
        affected, submitted = load.run(venues)
        log.info("Load done — submitted=%d  affected=%d", submitted, affected)
    except Exception as exc:
        log.error("Load failed: %s", exc)
        return 1

    log.info("=== Pipeline complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
