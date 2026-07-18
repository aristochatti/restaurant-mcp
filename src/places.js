// Thin wrapper over Google Places API (Text Search v1).
// Requires GOOGLE_MAPS_API_KEY in env with "Places API (New)" enabled.

const KEY = process.env.GOOGLE_MAPS_API_KEY;

export async function searchRestaurants(query, limit = 8) {
  if (!KEY) throw new Error("GOOGLE_MAPS_API_KEY is not set");

  const res = await fetch("https://places.googleapis.com/v1/places:searchText", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Goog-Api-Key": KEY,
      "X-Goog-FieldMask": [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.currentOpeningHours.openNow",
        "places.photos",
      ].join(","),
    },
    body: JSON.stringify({
      textQuery: `restaurants in ${query}`,
      includedType: "restaurant",
      maxResultCount: Math.min(limit, 20),
    }),
  });

  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Places API ${res.status}: ${t.slice(0, 300)}`);
  }

  const data = await res.json();
  const priceMap = {
    PRICE_LEVEL_INEXPENSIVE: 1,
    PRICE_LEVEL_MODERATE: 2,
    PRICE_LEVEL_EXPENSIVE: 3,
    PRICE_LEVEL_VERY_EXPENSIVE: 4,
  };

  return (data.places || []).map((p) => {
    const photoName = p.photos?.[0]?.name;
    const photoUrl = photoName
      ? `https://places.googleapis.com/v1/${photoName}/media?maxWidthPx=500&key=${KEY}`
      : null;
    return {
      placeId: p.id,
      name: p.displayName?.text || "Unnamed",
      address: p.formattedAddress || "",
      rating: p.rating || null,
      userRatingsTotal: p.userRatingCount || null,
      priceLevel: priceMap[p.priceLevel] || null,
      openNow: p.currentOpeningHours?.openNow,
      photoUrl,
    };
  });
}
