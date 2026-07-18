"""Module 3: Visualizer - Carousel HTML Renderer

Builds a self-contained HTML carousel string from a list of restaurants.

Returned to the host as an mcp-ui rawHtml resource — no external JS/CSS deps,
so it renders identically in Le Chat, Claude, and any mcp-ui host.

FEATURES:
- Basic view: name, photo, location, rating, price, open/closed status
- Booking: External link to Google Maps or restaurant website
- TODO: Expanded view with hours, menu, direct booking (future enhancement)
"""

from html import escape
from typing import Any
from urllib.parse import quote, urlencode

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
"""


def _esc(value: Any) -> str:
    """HTML-escape, matching the JS original's handling of None as empty."""
    return escape("", quote=True) if value is None else escape(str(value), quote=True)


def _stars(rating: float | None) -> str:
    if not rating:
        return ""
    full = round(rating)
    out = "".join("★" if i <= full else "☆" for i in range(1, 6))
    return f'<span class="stars">{out}</span><span class="rnum">{rating:.1f}</span>'


def _get_booking_url(r: dict[str, Any]) -> str:
    """
    Get booking URL for a restaurant.
    Priority: websiteUrl > placeId (Google Maps) > name+address search
    TODO: Future 4th tool will handle direct booking API integration
    """
    # 1. If websiteUrl is provided (from enriched list data), use it directly
    if r.get("websiteUrl"):
        return r["websiteUrl"]
    
    # 2. If placeId exists, use Google Maps deep link
    if r.get("placeId"):
        return f"https://www.google.com/maps/place/?q=place_id:{quote(str(r['placeId']), safe='')}"
    
    # 3. Fallback: search query
    query = f"{r.get('name', '')} {r.get('address') or ''}"
    return "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query})


def _card(r: dict[str, Any]) -> str:
    """
    Render a single restaurant card.
    
    Basic view (always shown):
    - Photo
    - Name
    - Address
    - Rating
    - Price level
    - Open/closed status
    - Booking link (external)
    
    TODO: Expanded view (click to show):
    - Hours
    - Menu
    - Direct booking
    """
    photo_url = r.get("photoUrl")
    if photo_url:
        # Use img tag with crossorigin and fallback for CORS/Mistral rendering issues
        img = f'<div class="photo"><img src="{_esc(photo_url)}" alt="{_esc(r.get("name", ""))}" crossorigin="anonymous" onerror="this.parentElement.className=\'photo ph\';this.remove()"></div>'
    else:
        img = '<div class="photo ph">🍽️</div>'

    price_level = r.get("priceLevel")
    price = "€" * price_level if price_level else ""

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

    # Get booking URL (supports websiteUrl for direct links)
    booking_url = _get_booking_url(r)

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
        {tag}
        <a class="book" href="{_esc(booking_url)}" target="_blank" rel="noopener">View &amp; book ↗</a>
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
            - priceLevel: Integer (1-4) for € symbols
            - openNow: Boolean for open/closed tag
            - photoUrl: URL for restaurant photo
            - placeId: Google Places ID (for deep links)
            - websiteUrl: Direct website URL (optional, for booking)
    
    Returns:
        Complete HTML string for mcp-ui rendering
    """
    cards = "".join(_card(r) for r in restaurants)
    header_note = f"{len(restaurants)} places · scroll to browse →"
    
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
