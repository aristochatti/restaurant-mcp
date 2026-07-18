// Builds a self-contained HTML carousel string from a list of restaurants.
// Returned to the host as an mcp-ui rawHtml resource — no external JS/CSS deps,
// so it renders identically in Le Chat, Claude, and any mcp-ui host.

const esc = (s = "") =>
  String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

function stars(rating) {
  if (!rating) return "";
  const full = Math.round(rating);
  let out = "";
  for (let i = 1; i <= 5; i++) out += i <= full ? "★" : "☆";
  return `<span class="stars">${out}</span><span class="rnum">${rating.toFixed(1)}</span>`;
}

function card(r) {
  const img = r.photoUrl
    ? `<div class="photo" style="background-image:url('${esc(r.photoUrl)}')"></div>`
    : `<div class="photo ph">🍽️</div>`;
  const price = r.priceLevel ? "€".repeat(r.priceLevel) : "";
  const mapsUrl =
    r.placeId
      ? `https://www.google.com/maps/place/?q=place_id:${encodeURIComponent(r.placeId)}`
      : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(r.name + " " + (r.address || ""))}`;
  return `
  <div class="card">
    ${img}
    <div class="body">
      <div class="row1">
        <h3>${esc(r.name)}</h3>
        ${price ? `<span class="price">${price}</span>` : ""}
      </div>
      <p class="meta">${esc(r.address || "")}</p>
      <div class="rrow">${stars(r.rating)}${r.userRatingsTotal ? `<span class="cnt">(${r.userRatingsTotal})</span>` : ""}</div>
      <div class="actions">
        ${r.openNow === true ? `<span class="tag open">Open now</span>` : r.openNow === false ? `<span class="tag closed">Closed</span>` : ""}
        <a class="book" href="${esc(mapsUrl)}" target="_blank" rel="noopener">View & book ↗</a>
      </div>
    </div>
  </div>`;
}

export function buildCarouselHtml({ location, restaurants }) {
  const cards = restaurants.map(card).join("");
  return `<!doctype html><html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
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
          box-shadow:0 4px 16px rgba(0,0,0,.08); overflow:hidden; display:flex; flex-direction:column; }
  .photo { height:150px; background-size:cover; background-position:center; }
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
</style></head>
<body><div class="wrap">
  <div class="head">
    <p class="eyebrow">Restaurants near you</p>
    <h2>Where to eat in ${esc(location)}</h2>
    <p class="sub">${restaurants.length} places · scroll to browse →</p>
  </div>
  <div class="track">${cards}</div>
</div></body></html>`;
}
