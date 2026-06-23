# CLAUDE.md — Cape Town / South Africa Explorer

## Project goal

Build an end-to-end data engineering + applied data science project: a curated
places-explorer for South African cities (starting with Cape Town), covering
restaurants, cafes, attractions, outdoor/nature spots, family activities,
adventure activities, and thrift/vintage stores — plus a cross-cutting
"date idea" tag, a natural-language chat assistant, and a simple ratings
prediction model.

This is a portfolio project for a 3rd-year Computer Science + Statistics &
Data Science double-major student targeting Data Scientist / Data Engineer
roles. The point is to demonstrate a genuinely working, deployed, end-to-end
pipeline — not a UI mockup with fake data. Every feature listed below must
work against real data sources before it counts as done.

**Owner's real-world constraints:** the owner is balancing this project
alongside a demanding CS course (CSC3003S) this semester. Build in the phase
order below. Do not skip ahead to later phases before earlier phases are
fully working, tested, and deployed. A finished Phase 1 is worth more than
a half-built Phase 1–3.

## Tech stack (confirmed, do not substitute without asking)

- **Languages:** Python (ETL, transform, ML), SQL (Postgres)
- **Database:** PostgreSQL via Supabase (owner already has Supabase experience)
- **Data source:** Google Places API (primary), OpenWeatherMap API (Phase 4, optional)
- **LLM:** OpenAI API (paid account already available) — used for:
  - structured intent extraction from chat queries
  - cuisine / vibe / "good for" tag enrichment from review text
  - review summarization
- **Orchestration:** n8n, self-hosted (NOT n8n Cloud — owner does not want recurring cost)
- **Deployment:** Render or Railway (n8n + any Python microservice), Vercel or
  Netlify (frontend dashboard) — owner already has deployment experience
- **Frontend:** HTML/CSS/JS or React + Chart.js, browser Geolocation API for
  distance features
- **Dev tooling:** Claude Code, git/GitHub for version control

Do not introduce n8n Cloud, paid Postgres tiers, or any other recurring-cost
service without explicitly flagging the cost to the owner first.

## Geographic scope

South Africa-wide architecture (city is a first-class field), but only
**Cape Town** needs to be fully populated with real data for v1. Other
cities can be added later by re-running the same ingestion pipeline with
different search queries — do not hardcode Cape Town-only assumptions
into the schema or pipeline logic.

## Data categories

Seven categories, derived from Google Places `types` field, mapped to:
`cafe`, `restaurant`, `attraction`, `outdoor`, `family`, `adventure`, `thrift`.

Plus a cross-cutting boolean-ish concept: **date idea fit** — this is NOT
a category, it's a tag that can apply to any venue regardless of category,
and it must be derived from real signals (review text mentioning
date/romantic/sunset/anniversary language), not hardcoded guesses.

## Schema (starting point — refine as needed, but keep these concerns)

```sql
CREATE TABLE venues (
    id SERIAL PRIMARY KEY,
    place_id TEXT UNIQUE NOT NULL,        -- Google Places place_id, for dedup
    name TEXT NOT NULL,
    category TEXT NOT NULL,               -- cafe/restaurant/attraction/outdoor/family/adventure/thrift
    city TEXT NOT NULL,
    area TEXT,                            -- neighbourhood, e.g. "Camps Bay"
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    rating NUMERIC,
    review_count INT,
    price_level INT,                      -- 1-4, nullable (Places doesn't always have it)
    cuisine TEXT,                         -- nullable, LLM-inferred from name+reviews
    cuisine_confidence TEXT,              -- 'high' | 'low' | 'unclear'
    is_date_spot BOOLEAN DEFAULT FALSE,
    date_spot_confidence TEXT,
    review_summary TEXT,                  -- LLM-generated, 1-2 sentences
    standout_items TEXT[],                -- e.g. dishes/experiences reviewers praise
    common_complaints TEXT[],
    opening_hours JSONB,
    last_enriched_at TIMESTAMP,           -- when LLM enrichment last ran for this venue
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE venue_tags (                 -- many-to-many, for vibe tags beyond date/cuisine
    venue_id INT REFERENCES venues(id),
    tag TEXT NOT NULL,
    PRIMARY KEY (venue_id, tag)
);

CREATE TABLE favourites (                 -- no-login, device-based
    device_id TEXT NOT NULL,
    venue_id INT REFERENCES venues(id),
    saved_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (device_id, venue_id)
);

CREATE TABLE pipeline_runs (              -- Phase 3, observability
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    venues_processed INT,
    venues_failed INT,
    status TEXT                            -- 'success' | 'partial_failure' | 'failed'
);

CREATE TABLE pipeline_errors (             -- Phase 3, observability
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES pipeline_runs(id),
    venue_name TEXT,
    error_message TEXT,
    occurred_at TIMESTAMP DEFAULT now()
);
```

Adjust types/constraints as you implement, but preserve: dedup on
`place_id`, nullable enrichment fields with confidence flags (never silently
assert something the data doesn't support), and the device-based favourites
pattern (no user accounts required).

## Build phases — work through these IN ORDER

### Phase 1 — Core pipeline (must finish first, this is the floor)
1. Postgres schema (above), deployed on Supabase
2. Extract: Python script calling Google Places API for Cape Town, across
   all 7 categories, writing raw results to a staging area before transform
3. Transform: map Places `types` → category, normalize price/rating,
   dedupe on `place_id`
4. Load: upsert into `venues` table
5. n8n workflow: schedule the above to run daily, self-hosted
6. A basic dashboard (can reuse/adapt the demo widgets built during planning)
   that reads real data from Postgres — NOT hardcoded arrays

**Definition of done for Phase 1:** running the n8n workflow actually
populates real Cape Town venues into Postgres, and the dashboard displays
that real data. No fake/hardcoded data anywhere in the running app.

### Phase 2 — Enrichment, chatbot, detail view
1. LLM enrichment script: for each venue, call OpenAI once to infer
   `cuisine`, `cuisine_confidence`, `is_date_spot`, `date_spot_confidence`,
   `review_summary`, `standout_items`, `common_complaints`. Run once per
   venue at ingest time, cache results — never re-run this per user query.
2. Chatbot: natural language query → OpenAI structured extraction (intent,
   filters) → SQL query against enriched `venues` table → OpenAI-generated
   natural language summary of results. Must correctly handle:
   - explicit queries ("cheap date spot near the beach")
   - vague/indirect queries ("somewhere fun with my girlfriend")
   - specific cuisine queries ("sushi spots")
   Test against all three patterns before considering this phase done.
3. Detail view: venue page showing rating, hours, review summary, standout
   tags, directions (real Google Maps deep link), favourite toggle
   (device-based, no login)

**Definition of done for Phase 2:** typing a vague natural-language query
into the real chatbot returns real, sensible venues from the real database,
not a keyword-matching stub.

### Phase 3 — Observability (do not skip this, it was explicitly requested)
1. Add `pipeline_runs` / `pipeline_errors` logging around every pipeline
   stage in the n8n workflow and/or Python scripts
2. Wrap per-venue processing in try/except — one venue failing must not
   crash the whole run
3. Add an alert (Slack webhook or email via n8n) that fires if a run's
   failure count exceeds a threshold
4. Add a simple "pipeline health" view (last run time, success/failure
   counts) to the dashboard

**Definition of done for Phase 3:** intentionally breaking one venue's data
(bad coordinates, missing fields) should produce a logged error and an
alert, while the rest of the pipeline keeps running successfully.

### Phase 4 — Stretch goals (only attempt after Phases 1-3 are solid)
- Ratings prediction model: predict a venue's expected `rating` from
  `price_level`, `category`, `review_count`, `area`, and review-derived
  sentiment features. Use scikit-learn, start with linear regression,
  compare against a naive baseline (mean rating), report MAE and R² honestly.
  Be explicit about small-sample-size limitations in any write-up.
- Multi-city expansion (Johannesburg, Durban, Pretoria) using the same
  pipeline with different search queries
- Weather-aware recommendations (merge in OpenWeatherMap data)
- Review-velocity "trending now" signal

## Open question — resolve before Phase 1 ingestion runs

Google Places API pricing changed in 2025/2026: the old universal $200/month
free credit is gone, replaced by per-SKU free caps (~10,000 Essentials
events/month), and some sources describe paid subscription tiers starting
around $275/month. It's unclear whether this project's actual usage (a few
hundred venues, daily refresh) stays comfortably inside the free cap or not,
and whether a paid plan is genuinely optional or effectively required for
the fields we need (ratings, reviews, hours, price level).

Before writing or running any real ingestion code against Google Places:
research current pricing yourself (official Google Cloud pricing pages,
the Places API pricing calculator), reason about which SKU tier this
project's specific fields/volume would fall into, and propose a safe path
forward. If Google Places carries real cost risk for this project's scale,
propose and default to a free alternative (e.g. OpenStreetMap's Overpass
API, or another free POI data source you find) instead — don't assume
either way. If you do proceed with Google Places, set up a budget alert at
a low threshold (e.g. $5) before making any real calls, and confirm with
the owner before enabling billing on a Google Cloud project. Use your own
judgment here in addition to this plan — this is explicitly an open
decision, not a fixed instruction.

## Hard constraints — do not violate these

1. **No fake data in the deployed app.** Demo/mock data is fine during local
   development before the pipeline works, but anything presented as "done"
   or "deployed" must be backed by real API calls and real Postgres rows.
2. **No recurring costs without explicit confirmation.** Self-host n8n.
   Use free tiers (Supabase, Render/Railway, Vercel/Netlify free tiers).
   Flag any unavoidable cost (e.g. OpenAI API usage) clearly, with an
   estimate, before running anything that scales beyond a few cents.
3. **No silent enrichment failures.** If an LLM call can't confidently
   classify something, store `confidence: 'unclear'` rather than guessing
   and presenting it as fact.
4. **Device-based favourites, not full auth.** Do not build a login system
   for this project — that complexity was explicitly deferred (it belongs
   to a separate, future multi-user project, not this one).
5. **Respect Google Places API terms and rate limits.** Do not scrape
   retailer/grocery sites (Pick n Pay, Checkers, Spar) for this or any
   related project — this was explicitly ruled out due to ToS/legal risk.

## Verification workflow — REQUIRED after every implementation step

After implementing any phase, step, or feature from this file, you must:

1. **Re-read this CLAUDE.md file** and explicitly check your implementation
   against the relevant phase's "Definition of done" criteria.
2. **State explicitly, in writing, which criteria are met and which are not.**
   Do not mark something as done if you have not actually run it against
   real data/APIs and observed real output.
3. **If something doesn't fully meet the goal**, identify specifically what's
   missing or wrong, then refine your implementation — do not move on to
   the next phase with known gaps left unaddressed.
4. **If you had to deviate from this file's instructions** (different
   library, different schema field, different approach), explain why, and
   confirm the deviation still satisfies the underlying goal in this file.
5. Only report a phase as complete once you have verified it end-to-end
   against real data — not "this should work," but "I ran it and confirmed
   it produced X."

Repeat this verification loop — implement, check against CLAUDE.md, refine —
until the current phase's definition of done is genuinely satisfied before
moving to the next phase.
