-- Enable moddatetime extension for auto-updating updated_at
CREATE EXTENSION IF NOT EXISTS moddatetime;

-- ============================================================
-- venues
-- ============================================================
CREATE TABLE IF NOT EXISTS venues (
    id              SERIAL PRIMARY KEY,
    place_id        TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN (
                        'cafe','restaurant','attraction',
                        'outdoor','family','adventure','thrift'
                    )),
    city            TEXT NOT NULL,
    area            TEXT,
    lat             DOUBLE PRECISION NOT NULL,
    lng             DOUBLE PRECISION NOT NULL,
    rating          NUMERIC,
    review_count    INT,
    price_level     INT,
    cuisine         TEXT,
    cuisine_confidence      TEXT CHECK (cuisine_confidence IN ('high','low','unclear')),
    is_date_spot            BOOLEAN DEFAULT FALSE,
    date_spot_confidence    TEXT CHECK (date_spot_confidence IN ('high','low','unclear')),
    review_summary          TEXT,
    standout_items          TEXT[],
    common_complaints       TEXT[],
    opening_hours           JSONB,
    last_enriched_at        TIMESTAMP,
    created_at              TIMESTAMP DEFAULT now(),
    updated_at              TIMESTAMP DEFAULT now()
);

CREATE TRIGGER venues_updated_at
    BEFORE UPDATE ON venues
    FOR EACH ROW
    EXECUTE PROCEDURE moddatetime(updated_at);

-- ============================================================
-- venue_tags  (many-to-many vibe tags)
-- ============================================================
CREATE TABLE IF NOT EXISTS venue_tags (
    venue_id    INT REFERENCES venues(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (venue_id, tag)
);

-- ============================================================
-- favourites  (device-based, no login)
-- ============================================================
CREATE TABLE IF NOT EXISTS favourites (
    device_id   TEXT NOT NULL,
    venue_id    INT REFERENCES venues(id) ON DELETE CASCADE,
    saved_at    TIMESTAMP DEFAULT now(),
    PRIMARY KEY (device_id, venue_id)
);

-- ============================================================
-- pipeline_runs  (Phase 3 observability — schema created now)
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                  SERIAL PRIMARY KEY,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    venues_processed    INT,
    venues_failed       INT,
    status              TEXT CHECK (status IN ('success','partial_failure','failed'))
);

-- ============================================================
-- pipeline_errors  (Phase 3 observability — schema created now)
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_errors (
    id              SERIAL PRIMARY KEY,
    run_id          INT REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    venue_name      TEXT,
    error_message   TEXT,
    occurred_at     TIMESTAMP DEFAULT now()
);
