"""
Multi-source user data parsers for CityScout.
Each parser extracts preference signals from a data export and returns
a list of text chunks with metadata, ready for embedding into Pinecone.

Chunk format:
{
    "text": "...",
    "metadata": {
        "source_type": "spotify" | "youtube" | "google_maps" | "instagram",
        "category": "...",
        "signal_type": "...",
    }
}
"""

from collections import Counter
from typing import Any


def _chunk(text: str, source_type: str, category: str, signal_type: str) -> dict:
    """Create a standardized parsed chunk."""
    return {
        "text": text.strip(),
        "metadata": {
            "source_type": source_type,
            "category": category,
            "signal_type": signal_type,
        },
    }


# ── Spotify Parser ──


def parse_spotify(data: dict) -> list[dict]:
    """
    Parse Spotify streaming history / top artists export.
    Extracts: top genres, favorite artists, listening mood/energy.
    """
    chunks = []

    # ── Top artists by play time ──
    artist_playtime: Counter = Counter()
    for entry in data.get("streaming_history", []):
        artist = entry.get("master_metadata_album_artist_name", "")
        ms = entry.get("ms_played", 0)
        if artist and ms > 30000:
            artist_playtime[artist] += ms

    if artist_playtime:
        top = artist_playtime.most_common(10)
        artist_list = ", ".join(f"{name} ({ms // 60000} min)" for name, ms in top)
        chunks.append(_chunk(
            f"User's top Spotify artists by listening time: {artist_list}. "
            f"Total unique artists: {len(artist_playtime)}.",
            source_type="spotify",
            category="music_taste",
            signal_type="top_artists",
        ))

    # ── Genres ──
    genre_count: Counter = Counter()
    for artist_info in data.get("top_artists", []):
        for genre in artist_info.get("genres", []):
            genre_count[genre] += 1

    if genre_count:
        top_genres = genre_count.most_common(15)
        genre_list = ", ".join(f"{g} ({c}x)" for g, c in top_genres)
        chunks.append(_chunk(
            f"User's top music genres from Spotify: {genre_list}. "
            f"This reveals aesthetic preferences and cultural affinities "
            f"that map to travel experiences (e.g., jazz → jazz bars, tango → milongas).",
            source_type="spotify",
            category="genre_preferences",
            signal_type="genres",
        ))

    # ── Mood signals from genres ──
    mood_keywords = {
        "relaxed": ["bossa nova", "cool jazz", "ambient", "chill", "lounge"],
        "energetic": ["rock", "punk", "electronic", "dance", "hip hop"],
        "romantic": ["tango", "bossa nova", "soul", "r&b", "bolero"],
        "intellectual": ["jazz", "classical", "experimental", "art rock"],
        "melancholic": ["blues", "folk", "indie", "singer-songwriter"],
    }

    detected_moods: Counter = Counter()
    all_genres = [g.lower() for g in genre_count.keys()]
    for mood, keywords in mood_keywords.items():
        for genre in all_genres:
            for kw in keywords:
                if kw in genre:
                    detected_moods[mood] += genre_count.get(genre, 0)

    if detected_moods:
        mood_list = ", ".join(mood for mood, _ in detected_moods.most_common(5))
        chunks.append(_chunk(
            f"User's listening mood profile: primarily {mood_list}. "
            f"This suggests preference for venues and experiences with "
            f"matching atmosphere and energy levels.",
            source_type="spotify",
            category="mood_energy",
            signal_type="listening_mood",
        ))

    # ── Listening time patterns ──
    hours: Counter = Counter()
    for entry in data.get("streaming_history", []):
        ts = entry.get("ts", "")
        if "T" in ts:
            try:
                hour = int(ts.split("T")[1][:2])
                hours[hour] += 1
            except (ValueError, IndexError):
                pass

    if hours:
        late_night = sum(hours.get(h, 0) for h in range(22, 24)) + sum(hours.get(h, 0) for h in range(0, 4))
        morning = sum(hours.get(h, 0) for h in range(6, 12))
        afternoon = sum(hours.get(h, 0) for h in range(12, 18))
        evening = sum(hours.get(h, 0) for h in range(18, 22))

        peak = max([("late night", late_night), ("morning", morning),
                     ("afternoon", afternoon), ("evening", evening)], key=lambda x: x[1])
        chunks.append(_chunk(
            f"User listens to music most during {peak[0]} hours. "
            f"This suggests they are a {peak[0]} person, relevant for "
            f"recommending activities and venues at matching times.",
            source_type="spotify",
            category="lifestyle_patterns",
            signal_type="time_patterns",
        ))

    return chunks


# ── YouTube Parser ──


def parse_youtube(data: dict) -> list[dict]:
    """
    Parse YouTube subscriptions / watch history export.
    Extracts: content interests, channel categories, watch patterns.
    """
    chunks = []

    # ── Subscription categories ──
    sub_categories: Counter = Counter()
    channel_names: list[str] = []

    for sub in data.get("subscriptions", []):
        cat = sub.get("category", "other")
        sub_categories[cat] += 1
        name = sub.get("channel_name", "")
        if name:
            channel_names.append(name)

    if sub_categories:
        cat_list = ", ".join(f"{cat} ({n})" for cat, n in sub_categories.most_common(10))
        chunks.append(_chunk(
            f"User's YouTube subscription categories: {cat_list}. "
            f"Total subscriptions: {len(channel_names)}.",
            source_type="youtube",
            category="content_interests",
            signal_type="subscription_categories",
        ))

    if channel_names:
        chunks.append(_chunk(
            f"User subscribes to YouTube channels including: {', '.join(channel_names[:15])}.",
            source_type="youtube",
            category="content_interests",
            signal_type="channels",
        ))

    # ── Watch history ──
    watch_categories: Counter = Counter()
    watch_titles: list[str] = []

    for entry in data.get("watch_history", []):
        cat = entry.get("category", "")
        if cat:
            watch_categories[cat] += 1
        title = entry.get("title", "")
        if title:
            watch_titles.append(title)

    if watch_categories:
        cat_list = ", ".join(f"{cat} ({n})" for cat, n in watch_categories.most_common(10))
        chunks.append(_chunk(
            f"User's YouTube watch history categories: {cat_list}.",
            source_type="youtube",
            category="watch_patterns",
            signal_type="watch_categories",
        ))

    # ── Travel-related content ──
    travel_keywords = ["travel", "food", "restaurant", "coffee", "city", "guide", "tour",
                       "street food", "culture", "architecture", "nightlife", "bar", "music"]
    travel_related = [t for t in watch_titles if any(kw in t.lower() for kw in travel_keywords)]

    if travel_related:
        chunks.append(_chunk(
            f"User has watched travel/food/culture related videos including: "
            f"{'; '.join(travel_related[:8])}.",
            source_type="youtube",
            category="travel_interests",
            signal_type="travel_content",
        ))

    return chunks


# ── Google Maps Parser ──


def parse_google_maps(data: dict) -> list[dict]:
    """
    Parse Google Maps saved/starred places export.
    Extracts: place types, cuisine preferences, neighborhood vibes.
    """
    chunks = []

    places = data.get("saved_places", [])
    if not places:
        return chunks

    # ── Place types ──
    type_count: Counter = Counter()
    for place in places:
        ptype = place.get("type", "other")
        type_count[ptype] += 1

    if type_count:
        type_list = ", ".join(f"{t} ({n})" for t, n in type_count.most_common(10))
        chunks.append(_chunk(
            f"User's saved Google Maps place types: {type_list}. "
            f"Total saved places: {len(places)}.",
            source_type="google_maps",
            category="place_preferences",
            signal_type="place_types",
        ))

    # ── Cuisine preferences ──
    cuisine_count: Counter = Counter()
    for place in places:
        cuisine = place.get("cuisine", "")
        if cuisine:
            cuisine_count[cuisine] += 1

    if cuisine_count:
        cuisine_list = ", ".join(f"{c} ({n})" for c, n in cuisine_count.most_common(10))
        chunks.append(_chunk(
            f"User's cuisine preferences from saved restaurants: {cuisine_list}.",
            source_type="google_maps",
            category="food_preferences",
            signal_type="cuisines",
        ))

    # ── Neighborhood vibes ──
    neighborhoods: Counter = Counter()
    for place in places:
        hood = place.get("neighborhood", "")
        if hood:
            neighborhoods[hood] += 1

    if neighborhoods:
        hood_list = ", ".join(f"{h} ({n})" for h, n in neighborhoods.most_common(10))
        chunks.append(_chunk(
            f"Neighborhoods the user frequents: {hood_list}.",
            source_type="google_maps",
            category="neighborhood_vibes",
            signal_type="neighborhoods",
        ))

    # ── Price level ──
    price_levels: Counter = Counter()
    for place in places:
        pl = place.get("price_level")
        if pl is not None:
            price_levels[pl] += 1

    if price_levels:
        avg_price = sum(pl * c for pl, c in price_levels.items()) / sum(price_levels.values())
        price_desc = {1: "budget-friendly", 2: "moderate", 3: "upscale", 4: "luxury"}
        avg_label = price_desc.get(round(avg_price), "moderate")
        chunks.append(_chunk(
            f"User's average price level preference: {avg_label} (avg {avg_price:.1f}/4).",
            source_type="google_maps",
            category="budget_signals",
            signal_type="price_level",
        ))

    # ── Tags / features ──
    tag_count: Counter = Counter()
    for place in places:
        for tag in place.get("tags", []):
            tag_count[tag] += 1

    if tag_count:
        tag_list = ", ".join(f"{t} ({n})" for t, n in tag_count.most_common(12))
        chunks.append(_chunk(
            f"Frequently tagged features in saved places: {tag_list}.",
            source_type="google_maps",
            category="venue_features",
            signal_type="tags",
        ))

    return chunks


# ── Instagram Parser ──


def parse_instagram(data: dict) -> list[dict]:
    """
    Parse Instagram liked/saved posts export.
    Extracts: aesthetic preferences, interest categories, lifestyle signals.
    """
    chunks = []

    all_posts = data.get("saved_posts", []) + data.get("liked_posts", [])
    if not all_posts:
        return chunks

    # ── Categories ──
    category_count: Counter = Counter()
    for post in all_posts:
        cat = post.get("category", "")
        if cat:
            category_count[cat] += 1

    if category_count:
        cat_list = ", ".join(f"{c} ({n})" for c, n in category_count.most_common(10))
        chunks.append(_chunk(
            f"User's Instagram interest categories (saved + liked): {cat_list}. "
            f"Total posts analyzed: {len(all_posts)}.",
            source_type="instagram",
            category="aesthetic_preferences",
            signal_type="post_categories",
        ))

    # ── Hashtags ──
    hashtag_count: Counter = Counter()
    for post in all_posts:
        for tag in post.get("hashtags", []):
            hashtag_count[tag.lower().strip("#")] += 1

    if hashtag_count:
        tag_list = ", ".join(f"#{t} ({n})" for t, n in hashtag_count.most_common(15))
        chunks.append(_chunk(
            f"Most frequent hashtags in user's Instagram posts: {tag_list}.",
            source_type="instagram",
            category="interest_signals",
            signal_type="hashtags",
        ))

    # ── Locations ──
    location_count: Counter = Counter()
    for post in all_posts:
        loc = post.get("location", "")
        if loc:
            location_count[loc] += 1

    if location_count:
        loc_list = ", ".join(f"{l} ({n})" for l, n in location_count.most_common(10))
        chunks.append(_chunk(
            f"Locations tagged in user's Instagram posts: {loc_list}.",
            source_type="instagram",
            category="location_preferences",
            signal_type="locations",
        ))

    # ── Lifestyle signals ──
    lifestyle_keywords = {
        "foodie": ["restaurant", "food", "brunch", "dinner", "chef", "cuisine"],
        "coffee_culture": ["coffee", "café", "latte", "espresso", "barista"],
        "nightlife": ["bar", "cocktail", "wine", "club", "dj", "party"],
        "art_culture": ["gallery", "museum", "art", "exhibition", "architecture"],
        "outdoor": ["hiking", "beach", "park", "nature", "sunset", "trail"],
    }

    lifestyle_signals: Counter = Counter()
    combined = " ".join(
        p.get("caption", "").lower() + " " + " ".join(t.lower() for t in p.get("hashtags", []))
        for p in all_posts
    )
    for signal, keywords in lifestyle_keywords.items():
        count = sum(combined.count(kw) for kw in keywords)
        if count > 0:
            lifestyle_signals[signal] = count

    if lifestyle_signals:
        signal_list = ", ".join(s for s, _ in lifestyle_signals.most_common(6))
        chunks.append(_chunk(
            f"User's lifestyle signals from Instagram: {signal_list}.",
            source_type="instagram",
            category="lifestyle_signals",
            signal_type="lifestyle",
        ))

    return chunks


# ── Router ──

PARSERS = {
    "spotify": parse_spotify,
    "youtube": parse_youtube,
    "google_maps": parse_google_maps,
    "instagram": parse_instagram,
}


def parse_user_data(source_type: str, data: dict) -> list[dict]:
    """Route to the correct parser based on source type."""
    parser = PARSERS.get(source_type)
    if not parser:
        raise ValueError(f"Unknown source type: {source_type}. Supported: {list(PARSERS.keys())}")
    return parser(data)
