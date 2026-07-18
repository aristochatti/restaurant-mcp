"""Module 3: Visualizer - Carousel HTML Renderer

Builds a self-contained HTML carousel string from a list of restaurants.

Returned to the host as an mcp-ui rawHtml resource — no external JS/CSS deps,
so it renders identically in Le Chat, Claude, and any mcp-ui host.

FEATURES:
- Basic view: name, photo, location, rating, price, open/closed status
- Google Maps button for each restaurant
- TODO: Expanded view with hours, menu, direct booking (future enhancement)
"""

from html import escape
from typing import Any
from urllib.parse import quote
import random

_STYLE = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; color:#1c1917; background:#fafaf9; }
  .wrap { padding:16px; }
  .head { margin:0 4px 12px; }
  .eyebrow { font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#047857; margin:0; }
  h2 { margin:2px 0 0; font-size:20px; }
  .sub { margin:2px 0 0; color:#78716c; font-size:13px; }
  .track { display:flex; gap:14px; overflow-x:auto; padding:6px 4px 14px; scroll-snap-type:x mandatory; }
  .track::-webkit-scrollbar { height:8px; }
  .track::-webkit-scrollbar-thumb { background:#d6d3d1; border-radius:4px; }
  .card { flex:0 0 260px; scroll-snap-align:start; background:#fff; border-radius:16px;
          box-shadow:0 4px 16px rgba(0,0,0,.08); overflow:hidden; display:flex; flex-direction:column; cursor:pointer; }
  .photo { height:150px; background-size:cover; background-position:center; overflow:hidden; position:relative; }
  .photo img { width:100%; height:100%; object-fit:cover; display:block; }
  .photo.ph { display:flex; align-items:center; justify-content:center; font-size:48px;
              background:linear-gradient(135deg,#059669,#065f46); }
  .body { padding:12px 14px 14px; display:flex; flex-direction:column; gap:6px; }
  .row1 { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; }
  h3 { margin:0; font-size:16px; line-height:1.2; }
  .price { color:#78716c; font-weight:600; font-size:14px; white-space:nowrap; }
  .meta { margin:0; font-size:12px; color:#78716c; line-height:1.3;
          display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .rrow { display:flex; align-items:center; gap:6px; font-size:13px; }
  .stars { color:#f59e0b; letter-spacing:1px; }
  .rnum { font-weight:600; }
  .cnt { color:#a8a29e; font-size:12px; }
  .actions { margin-top:4px; display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .tag { font-size:11px; font-weight:600; padding:2px 8px; border-radius:999px; }
  .tag.open { background:#dcfce7; color:#166534; }
  .tag.closed { background:#fee2e2; color:#991b1b; }
  .book { margin-left:auto; font-size:13px; font-weight:600; color:#047857; text-decoration:none;
          padding:6px 10px; border-radius:8px; background:#ecfdf5; }
  .book:hover { background:#d1fae5; }
  .map-btn { font-size:13px; font-weight:600; color:#1485ee; text-decoration:none;
             padding:6px 10px; border-radius:8px; background:#eef4ff; border:1px solid #bae6fd; }
  .map-btn:hover { background:#d9efff; }
  .dist { font-size:11px; font-weight:600; color:#6366f1; background:#eef2ff;
          padding:2px 8px; border-radius:999px; white-space:nowrap; }
"""

# List of food emojis to use instead of images
FOOD_EMOJIS = [
    "\U0001f355",  # Pizza
    "\U0001f354",  # Hamburger
    "\U0001f35f",  # French fries
    "\U0001f35d",  # Spaghetti
    "\U0001f371",  # Bacon
    "\U0001f372",  # Pot of food
    "\U0001f373",  # Cooking
    "\U0001f356",  # Meat on bone
    "\U0001f357",  # Poultry leg
    "\U0001f358",  # Rice cracker
    "\U0001f359",  # Rice ball
    "\U0001f35a",  # Cooked rice
    "\U0001f35b",  # Curry rice
    "\U0001f35c",  # Steaming bowl
    "\U0001f35e",  # Bread
    "\U0001f360",  # Roasted sweet potato
    "\U0001f361",  # Dango
    "\U0001f362",  # Oden
    "\U0001f363",  # Sushi
    "\U0001f364",  # Fried shrimp
    "\U0001f365",  # Fish cake with swirl
    "\U0001f366",  # Soft ice cream
    "\U0001f367",  # Shaved ice
    "\U0001f368",  # Ice cream
    "\U0001f369",  # Doughnut
    "\U0001f36a",  # Cookie
    "\U0001f36b",  # Chocolate bar
    "\U0001f36c",  # Candy
    "\U0001f36d",  # Lollipop
    "\U0001f36e",  # Custard
    "\U0001f36f",  # Honey pot
    "\U0001f370",  # Shortcake
    "\U0001f950",  # Croissant
    "\U0001f951",  # Avocado
    "\U0001f952",  # Cucumber
    "\U0001f953",  # Bacon
    "\U0001f954",  # Potato
    "\U0001f955",  # Carrot
    "\U0001f956",  # Baguette bread
    "\U0001f957",  # Green salad
    "\U0001f958",  # Pancakes
    "\U0001f959",  # Stuffed flatbread
    "\U0001f95a",  # Egg
    "\U0001f95b",  # Glass of milk
    "\U0001f95c",  # Peanuts
    "\U0001f95d",  # Kiwi fruit
    "\U0001f95e",  # Pomegranate
    "\U0001f95f",  # Dumpling
    "\U0001f960",  # Fortune cookie
    "\U0001f961",  # Takeout box
    "\U0001f9c0",  # Cheese wedge
    "\U0001f9c1",  # Cupcake
    "\U0001f9c2",  # Salt
    "\U0001f9c3",  # Beverage box
    "\U0001f9c4",  # Garlic
    "\U0001f9c5",  # Onion
    "\U0001f9c6",  # Falafel
    "\U0001f9c7",  # Waffle
    "\U0001f9c8",  # Butter
    "\U0001f9c9",  # Mate
    "\U0001f9ca",  # Ice
]


def _esc(value: Any) -> str:
    """HTML-escape, matching the JS original's handling of None as empty."""
    return escape("", quote=True) if value is None else escape(str(value), quote=True)


def _esc_url(value: Any) -> str:
    """Escape URL for HTML attribute, but don't escape base64 data URLs."""
    if not value:
        return ""
    
    url_str = str(value)
    # If it's a data URL (base64 encoded), don't escape the data part
    if url_str.startswith("data:"):
        # Split into the data URL prefix and the actual data
        # Format: data:[<mediatype>][;base64],<data>
        parts = url_str.split(",", 1)
        if len(parts) == 2:
            # Escape the prefix (before comma) and leave data as-is
            return escape(parts[0], quote=True) + "," + parts[1]
    
    # For regular URLs, use normal escaping
    return escape(url_str, quote=True)


def _stars(rating: float | None) -> str:
    if not rating:
        return ""
    full = round(rating)
    out = "".join("[33m[0m" if i <= full else "" for i in range(1, 6))
    return f'<span class="stars">{out}</span><span class="rnum">{rating:.1f}</span>'


def _get_random_food_emoji() -> str:
    """Return a random food emoji."""
    return random.choice(FOOD_EMOJIS)


def _build_maps_url(address: str | None) -> str:
    """Build a Google Maps search URL for the given address."""
    if not address:
        return "#"
    # URL encode the address for the query parameter
    encoded_address = quote(address)
    return f"https://www.google.com/maps/search/?api=1&query={encoded_address}"


def _card(r: dict[str, Any]) -> str:
    """
    Render a single restaurant card.
    
    Basic view (always shown):
    - Photo (replaced with random food emoji)
    - Name
    - Address
    - Rating
    - Price level
    - Open/closed status
    - Google Maps button
    
    TODO: Expanded view (click to show):
    - Hours
    - Menu
    - Direct booking
    """
    # Use random food emoji instead of photo URL
    food_emoji = _get_random_food_emoji()
    img = f'<div class="photo ph">{food_emoji}</div>'

    price_level = r.get("priceLevel")
    # Handle both numeric and string price levels (e.g., "$$" or 2)
    if isinstance(price_level, (int, float)):
        price = "\u20ac" * int(price_level) if price_level else ""
    elif isinstance(price_level, str):
        # Map common string formats to numeric
        price_map = {"$": 1, "$$": 2, "$$$": 3, "$$$$": 4,
                     "inexpensive": 1, "moderate": 2, "expensive": 3, "very_expensive": 4,
                     "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2,
                     "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4}
        price_int = price_map.get(price_level.lower().strip("$ "), None)
        price = "\u20ac" * price_int if price_int else ""
    else:
        price = ""

    open_now = r.get("openNow")
    if open_now is True:
        tag = '<span class="tag open">Open now</span>'
    elif open_now is False:
        tag = '<span class="tag closed">Closed</span>'
    else:
        tag = ""

    total = r.get("userRatingsTotal")
    count = f'<span class="cnt">({total})</span>' if total else ""
    price_span = f'<span class="price">{price}</span>' if price else ""

    # Build Google Maps URL
    maps_url = _build_maps_url(r.get("address"))
    maps_btn = f'<a href="{_esc_url(maps_url)}" class="map-btn" target="_blank" rel="noopener noreferrer">Map</a>'

    # Distance badge (only shown for list results sorted by distance)
    distance_km = r.get("distanceKm")
    if distance_km is not None:
        try:
            dist_val = float(distance_km)
            dist_label = f"{dist_val:.1f} km away"
        except (TypeError, ValueError):
            dist_label = f"{distance_km} km away"
        dist_badge = f'<span class="dist">📍 {dist_label}</span>'
    else:
        dist_badge = ""

    return f"""
  <div class="card">
    {img}
    <div class="body">
      <div class="row1">
        <h3>{_esc(r.get("name"))}</h3>
        {price_span}
      </div>
      <p class="meta">{_esc(r.get("address") or "")}</p>
      <div class="rrow">{_stars(r.get("rating"))}{count}</div>
      <div class="actions">
        {dist_badge}{tag}
        {maps_btn}
      </div>
    </div>
  </div>"""



def build_carousel_html(location: str, restaurants: list[dict[str, Any]]) -> str:
    """
    Build complete carousel HTML from a list of restaurants.
    
    Args:
        location: The location/title to display in the header
        restaurants: List of restaurant dicts with:
            - name: Restaurant name
            - address: Full address
            - rating: Float rating (1-5)
            - userRatingsTotal: Number of ratings
            - priceLevel: Integer (1-4) for \u20ac symbols
            - openNow: Boolean for open/closed tag
            - photoUrl: URL for restaurant photo (not used anymore, replaced with emoji)
            - placeId: Google Places ID (for deep links)
    
    Returns:
        Complete HTML string for mcp-ui rendering
    """
    cards = "".join(_card(r) for r in restaurants)
    header_note = f"{len(restaurants)} places \u00b7 scroll to browse \u2192"
    
    return f"""<!doctype html><html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>{_STYLE}</style></head>
<body><div class="wrap">
  <div class="head">
    <p class="eyebrow">Restaurants near you</p>
    <h2>Where to eat in {_esc(location)}</h2>
    <p class="sub">{header_note}</p>
  </div>
  <div class="track">{cards}</div>
</div></body></html>"""
