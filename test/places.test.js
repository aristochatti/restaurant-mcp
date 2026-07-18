import test from "node:test";
import assert from "node:assert/strict";

// places.js reads GOOGLE_MAPS_API_KEY at module load, so set it before importing.
process.env.GOOGLE_MAPS_API_KEY = "test-key";
const { searchRestaurants } = await import("../src/places.js");

function stubFetch(response) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return response;
  };
  return calls;
}

const ok = (body) => ({
  ok: true,
  status: 200,
  json: async () => body,
  text: async () => JSON.stringify(body),
});

const realFetch = globalThis.fetch;
test.afterEach(() => {
  globalThis.fetch = realFetch;
});

test("maps a Places response into the carousel's restaurant shape", async () => {
  stubFetch(
    ok({
      places: [
        {
          id: "place-1",
          displayName: { text: "Osteria Fernanda" },
          formattedAddress: "Via Crescenzo del Monte 18, Roma",
          rating: 4.6,
          userRatingCount: 900,
          priceLevel: "PRICE_LEVEL_EXPENSIVE",
          currentOpeningHours: { openNow: true },
          photos: [{ name: "places/place-1/photos/xyz" }],
        },
      ],
    })
  );

  const [r] = await searchRestaurants("Rome", 5);

  assert.equal(r.placeId, "place-1");
  assert.equal(r.name, "Osteria Fernanda");
  assert.equal(r.address, "Via Crescenzo del Monte 18, Roma");
  assert.equal(r.rating, 4.6);
  assert.equal(r.userRatingsTotal, 900);
  assert.equal(r.priceLevel, 3);
  assert.equal(r.openNow, true);
  assert.match(r.photoUrl, /places\/place-1\/photos\/xyz\/media\?maxWidthPx=500/);
});

test("fills in defaults for sparse places", async () => {
  stubFetch(ok({ places: [{ id: "place-2" }] }));

  const [r] = await searchRestaurants("Rome");

  assert.equal(r.name, "Unnamed");
  assert.equal(r.address, "");
  assert.equal(r.rating, null);
  assert.equal(r.priceLevel, null);
  assert.equal(r.photoUrl, null);
});

test("returns an empty array when Places returns no results", async () => {
  stubFetch(ok({}));
  assert.deepEqual(await searchRestaurants("Atlantis"), []);
});

test("caps maxResultCount at 20 and scopes the query to restaurants", async () => {
  const calls = stubFetch(ok({ places: [] }));

  await searchRestaurants("Tokyo", 50);

  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.maxResultCount, 20);
  assert.equal(body.includedType, "restaurant");
  assert.equal(body.textQuery, "restaurants in Tokyo");
  assert.equal(calls[0].init.headers["X-Goog-Api-Key"], "test-key");
});

test("throws with the API status when Places rejects the request", async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 403,
    text: async () => "PERMISSION_DENIED: Places API is not enabled",
  });

  await assert.rejects(searchRestaurants("Rome"), /Places API 403.*PERMISSION_DENIED/s);
});
