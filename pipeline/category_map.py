"""
Single source of truth for Google Places types → our 7 categories.
Rules are evaluated in order; first match wins.
"""

THRIFT_KEYWORDS = {
    "thrift", "vintage", "second hand", "secondhand",
    "pre-loved", "preloved", "pre-owned", "preowned",
    "2nd hand", "2ndhand", "charity", "hospice",
    "antique", "consign", "pre loved", "pre owned",
    "nearly new", "used clothing", "second coming",
    "nevernew", "resale",
}

ADVENTURE_KEYWORDS = {
    "kayak", "kite surf", "kitesurf", "surf", "paraglid", "abseil",
    "bungee", "skydiv", "zip line", "zipline", "scuba", "dive",
    "cruise", "boat tour", "seal island", "whale watch", "shark",
    "hiking", "quad bike", "atv", "sandboard",
}

# Each entry: (our_category, set_of_places_types_that_match)
# A venue matches if ANY of its types is in the set.
TYPE_RULES = [
    ("cafe",        {"cafe", "coffee_shop"}),
    ("restaurant",  {"restaurant", "food"}),
    ("attraction",  {"tourist_attraction", "museum", "art_gallery", "church",
                     "historical_landmark", "cultural_landmark"}),
    ("outdoor",     {"park", "natural_feature", "campground", "beach",
                     "national_park", "hiking_area", "nature_reserve"}),
    ("family",      {"amusement_park", "zoo", "aquarium", "childrens_camp",
                     "playground", "water_park"}),
    ("adventure",   {"gym", "stadium", "bowling_alley", "rock_climbing_gym",
                     "ski_resort", "golf_course", "sports_complex",
                     "tour_operator", "boat_tour", "sports_activity_location",
                     "adventure_sports_center"}),
    ("thrift",      {"clothing_store", "second_hand_store", "thrift_store",
                     "vintage_store", "flea_market"}),
]


def map_category(place_types: list[str], place_name: str = "") -> str | None:
    """
    Return our category string, or None if no rule matches.
    place_types: the 'types' list from the Places API response.
    place_name: used as a fallback for thrift keyword matching.
    """
    types_set = {t.lower() for t in place_types}
    name_lower = place_name.lower()

    for category, matched_types in TYPE_RULES:
        if types_set & matched_types:
            # Extra check for thrift: clothing_store only counts if name
            # contains a thrift keyword, to avoid mapping regular shops.
            if category == "thrift" and "clothing_store" in types_set:
                if not any(kw in name_lower for kw in THRIFT_KEYWORDS):
                    continue
            return category

    # Last-chance adventure: tour operators / travel agencies whose name
    # signals an adventure activity (kayak, cruise, surf, etc.)
    if "tour_operator" in types_set or "travel_agency" in types_set:
        if any(kw in name_lower for kw in ADVENTURE_KEYWORDS):
            return "adventure"

    # Last-chance thrift: any venue whose name contains a thrift keyword
    if any(kw in name_lower for kw in THRIFT_KEYWORDS):
        return "thrift"

    return None


# City-wide search queries — used on every run (daily refresh).
CATEGORY_QUERIES = {
    "cafe":        "{city} cafes and coffee shops",
    "restaurant":  "{city} restaurants",
    "attraction":  "{city} tourist attractions and museums",
    "outdoor":     "{city} parks beaches and nature spots",
    "family":      "{city} family activities and amusement parks",
    "adventure":   "{city} adventure activities kayaking boat tours surfing",
    "thrift":      "{city} thrift vintage second hand stores",
}

# Cape Town neighbourhoods for the full/initial load.
# Each is appended to the category query template to get
# neighbourhood-level results that city-wide queries miss.
CAPE_TOWN_NEIGHBOURHOODS = [
    "V&A Waterfront Cape Town",
    "City Bowl Cape Town",
    "Bo-Kaap Cape Town",
    "De Waterkant Cape Town",
    "Green Point Cape Town",
    "Sea Point Cape Town",
    "Clifton Cape Town",
    "Camps Bay Cape Town",
    "Bakoven Cape Town",
    "Hout Bay Cape Town",
    "Constantia Cape Town",
    "Tokai Cape Town",
    "Newlands Cape Town",
    "Claremont Cape Town",
    "Kenilworth Cape Town",
    "Wynberg Cape Town",
    "Rondebosch Cape Town",
    "Observatory Cape Town",
    "Woodstock Cape Town",
    "Salt River Cape Town",
    "Muizenberg Cape Town",
    "Kalk Bay Cape Town",
    "Fish Hoek Cape Town",
    "Simon's Town Cape Town",
    "Bloubergstrand Cape Town",
    "Table View Cape Town",
    "Milnerton Cape Town",
    "Durbanville Cape Town",
    "Stellenbosch",
    "Franschhoek",
]

# Per-category query templates for neighbourhood searches.
# {area} is substituted at run time.
NEIGHBOURHOOD_TEMPLATES = {
    "cafe":        "{area} cafes coffee shops",
    "restaurant":  "{area} restaurants",
    "attraction":  "{area} attractions things to do",
    "outdoor":     "{area} parks beaches outdoor",
    "family":      "{area} family activities",
    "adventure":   "{area} adventure activities tours",
    "thrift":      "{area} thrift vintage stores",
}
