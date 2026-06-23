"""
Flask API wrapper around the pipeline.
Deployed on Render — n8n calls POST /run weekly to trigger the pipeline.
POST /chat — AI-powered venue search for the dashboard.
"""

import json
import logging
import math
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

API_SECRET    = os.getenv("PIPELINE_API_SECRET", "")
OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")
SUPABASE_DB   = os.getenv("SUPABASE_DB_URL", "")
oai           = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


# ── CORS ───────────────────────────────────────────────────────────────────
def _cors(response, status=200):
    if isinstance(response, str):
        from flask import make_response
        r = make_response(response, status)
    else:
        r = response
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Api-Secret"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return r

@app.after_request
def after(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Api-Secret"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# ── Auth ───────────────────────────────────────────────────────────────────
def _authorized():
    if not API_SECRET:
        return True
    return request.headers.get("X-Api-Secret") == API_SECRET


# ── Haversine ──────────────────────────────────────────────────────────────
def _km(lat1, lng1, lat2, lng2):
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLng = math.radians(lng2 - lng1)
    a = (math.sin(dLat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLng/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Intent extraction ──────────────────────────────────────────────────────
INTENT_SYSTEM = """You are a search filter extractor for a Cape Town places explorer.

The database schema:
- category: one of cafe, restaurant, attraction, outdoor, family, adventure, thrift
- cuisine: free text enrichment (e.g. "sushi", "indian", "seafood", "coffee", "italian", "african", "steakhouse")
- is_date_spot: boolean — true for romantic/date-friendly venues
- price_level: 1=R budget, 2=RR moderate, 3=RRR upscale, 4=RRRR luxury
- area: Cape Town neighbourhood (Sea Point, Camps Bay, Stellenbosch, Hout Bay, etc.)
- rating: 1.0–5.0
- review_count: integer

Given a user's natural language query, return ONLY valid JSON with these fields (all optional/nullable):
{
  "category": string|null,
  "cuisine": string|null,
  "name_terms": [string],
  "is_date_spot": boolean|null,
  "price_max": integer|null,
  "price_min": integer|null,
  "area": string|null,
  "sort": "rating"|"distance"|"reviews"|"value"|null,
  "intent_summary": string
}

Rules:
- name_terms: search terms to match against venue names, cuisines, and descriptions. Be generous — include synonyms and related words. Examples:
  * "beef" → ["steak", "beef", "burger", "braai", "grill"]
  * "ice cream" → ["ice cream", "gelato", "sorbet", "frozen yogurt", "creamery"]
  * "Nigerian food" → ["nigerian", "afro", "jollof", "suya", "african"]
  * "Zim food" → ["zimbabwe", "sadza", "nyama", "african"]
  * "breakfast" → ["breakfast", "brunch", "eggs", "morning"]
  * "I'm bored, I want adrenaline" → set category to "adventure"
- price: "cheap"/"budget" → price_max=1, "moderate"/"mid-range" → price_max=2, "expensive"/"upscale" → price_min=3
- sort: "near me"/"closest"/"nearby" → "distance", "best rated" → "rating", "most reviewed"/"popular" → "reviews"
- is_date_spot: "date"/"romantic"/"girlfriend"/"anniversary"/"intimate" → true
- Return empty array [] for name_terms if no name search needed
- intent_summary: one sentence describing what the user wants, e.g. "Adventurous outdoor activities"
"""


def extract_intent(query: str, ui_filters: dict) -> dict:
    context = f"User query: {query}"
    if ui_filters.get("category"):
        context += f"\nUI has category filter active: {ui_filters['category']}"
    if ui_filters.get("area"):
        context += f"\nUI has area filter active: {ui_filters['area']}"

    resp = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": INTENT_SYSTEM},
            {"role": "user",   "content": context},
        ],
        temperature=0,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ── DB search ──────────────────────────────────────────────────────────────
def search_venues(intent: dict, ui_filters: dict, lat=None, lng=None) -> list:
    conditions = ["1=1"]
    params = []

    # Merge AI intent with active UI filters
    category = intent.get("category") or ui_filters.get("category")
    if category:
        conditions.append("category = %s")
        params.append(category)

    is_date = intent.get("is_date_spot")
    if is_date is None and ui_filters.get("is_date_spot"):
        is_date = True
    if is_date is not None:
        conditions.append("is_date_spot = %s")
        params.append(is_date)

    price_max = intent.get("price_max") or ui_filters.get("price_max")
    if price_max:
        conditions.append("(price_level IS NULL OR price_level <= %s)")
        params.append(int(price_max))

    price_min = intent.get("price_min")
    if price_min:
        conditions.append("(price_level IS NULL OR price_level >= %s)")
        params.append(int(price_min))

    area = intent.get("area") or ui_filters.get("area")
    if area:
        conditions.append("area ILIKE %s")
        params.append(f"%{area}%")

    # Name/cuisine/summary text search
    name_terms = intent.get("name_terms") or []
    cuisine = intent.get("cuisine")
    if cuisine and cuisine not in name_terms:
        name_terms = [cuisine] + list(name_terms)

    if name_terms:
        term_clauses = []
        for term in name_terms[:8]:  # cap at 8 terms
            term_clauses.append(
                "(name ILIKE %s OR cuisine ILIKE %s OR review_summary ILIKE %s)"
            )
            pat = f"%{term}%"
            params.extend([pat, pat, pat])
        conditions.append(f"({' OR '.join(term_clauses)})")

    # SQL sort
    sort = intent.get("sort") or "rating"
    if sort == "reviews":
        order = "review_count DESC NULLS LAST"
    elif sort == "value":
        order = "(rating / NULLIF(price_level, 0)) DESC NULLS LAST"
    else:
        order = "rating DESC NULLS LAST"

    sql = f"""
        SELECT id, name, category, area, lat, lng, rating, review_count,
               price_level, cuisine, is_date_spot, review_summary, standout_items
        FROM venues
        WHERE {" AND ".join(conditions)}
        ORDER BY {order}
        LIMIT 50
    """

    conn = psycopg2.connect(SUPABASE_DB)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    # Distance sort in Python if lat/lng provided
    if sort == "distance" and lat is not None and lng is not None:
        for r in rows:
            r["distance_km"] = round(_km(lat, lng, r["lat"], r["lng"]), 1)
        rows.sort(key=lambda r: r.get("distance_km", 9999))
    elif lat is not None and lng is not None:
        for r in rows:
            r["distance_km"] = round(_km(lat, lng, r["lat"], r["lng"]), 1)

    return rows[:10]


# ── Recommendation summary ─────────────────────────────────────────────────
def generate_summary(query: str, venues: list) -> str:
    if not venues:
        return (f"No venues found for \"{query}\" in Cape Town. "
                "Try a broader search or different keywords.")

    lines = []
    for v in venues[:5]:
        dist = f", {v['distance_km']} km away" if v.get("distance_km") else ""
        summary = v.get("review_summary") or ""
        cuisine_str = f" | cuisine: {v['cuisine']}" if v.get("cuisine") else ""
        lines.append(
            f"- {v['name']} ({v.get('category','')}, {v.get('area','Cape Town')}"
            f"{dist}{cuisine_str}): {v.get('rating','?')}★. {summary}"
        )

    resp = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": (
                "You are a Cape Town places assistant. "
                "ONLY describe venues from the list provided — never invent menus, features, or facts not in the data.\n"
                "- If the venues match the query well: recommend 1-2 by name with a reason grounded strictly in the provided data.\n"
                "- If the venues are a poor match (e.g. user asked for sushi but results are Greek or unrelated restaurants): "
                "honestly say no exact match was found, then briefly describe what was found instead.\n"
                "- Never claim a venue serves food or has features not supported by its name, category, cuisine, or review_summary.\n"
                "- 2 sentences max. No filler."
            )},
            {"role": "user", "content": (
                f"User asked: \"{query}\"\n\nVenues found:\n"
                + "\n".join(lines)
                + "\n\nRespond:"
            )},
        ],
        max_tokens=180,
        temperature=0.3,
    )
    return resp.choices[0].message.content


# ── Routes ─────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/run", methods=["POST", "OPTIONS"])
def run_pipeline():
    if request.method == "OPTIONS":
        return "", 204
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    import run_pipeline as rp
    exit_code = rp.main()
    if exit_code == 0:
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "failed", "exit_code": exit_code}), 500


@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return "", 204
    if not oai:
        return jsonify({"error": "OpenAI not configured"}), 500

    body       = request.get_json(silent=True) or {}
    query      = (body.get("query") or "").strip()
    lat        = body.get("lat")
    lng        = body.get("lng")
    ui_filters = body.get("ui_filters") or {}

    if not query:
        return jsonify({"error": "query is required"}), 400

    try:
        intent  = extract_intent(query, ui_filters)
        log.info("intent: %s", intent)
        venues  = search_venues(intent, ui_filters, lat, lng)
        summary = generate_summary(query, venues)
        return jsonify({
            "summary": summary,
            "venues":  venues,
            "count":   len(venues),
            "intent":  intent.get("intent_summary", ""),
        })
    except Exception as e:
        log.exception("chat error")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
