import test from "node:test";
import assert from "node:assert/strict";
import { buildCarouselHtml } from "../src/carousel.js";

const sample = [
  {
    placeId: "abc123",
    name: "Trattoria Da Enzo",
    address: "Via dei Vascellari 29, Roma",
    rating: 4.5,
    userRatingsTotal: 1820,
    priceLevel: 2,
    openNow: true,
    photoUrl: "https://example.com/photo.jpg",
  },
  {
    placeId: null,
    name: "Chez <script>alert(1)</script>",
    address: 'A "quoted" street',
    rating: null,
    userRatingsTotal: null,
    priceLevel: null,
    openNow: false,
    photoUrl: null,
  },
];

test("renders one card per restaurant with the location in the heading", () => {
  const html = buildCarouselHtml({ location: "Rome", restaurants: sample });

  assert.match(html, /^<!doctype html>/);
  assert.equal(html.split('class="card"').length - 1, 2);
  assert.match(html, /Where to eat in Rome/);
  assert.match(html, /2 places/);
});

test("escapes restaurant names and addresses", () => {
  const html = buildCarouselHtml({ location: "Rome", restaurants: sample });

  assert.ok(!html.includes("<script>alert(1)</script>"), "script tag must not survive raw");
  assert.match(html, /Chez &lt;script&gt;/);
  assert.match(html, /A &quot;quoted&quot; street/);
});

test("escapes the location, which lands in the heading unfiltered otherwise", () => {
  const html = buildCarouselHtml({
    location: '"><img src=x onerror=alert(1)>',
    restaurants: [],
  });

  assert.ok(!html.includes("<img src=x"), "location must be escaped");
  assert.match(html, /&lt;img src=x/);
});

test("renders price level as repeated euro signs", () => {
  const html = buildCarouselHtml({ location: "Rome", restaurants: sample });
  assert.match(html, /<span class="price">€€<\/span>/);
});

test("shows open/closed tags only when openNow is known", () => {
  const html = buildCarouselHtml({ location: "Rome", restaurants: sample });
  assert.match(html, /Open now/);
  assert.match(html, /Closed/);

  const unknown = buildCarouselHtml({
    location: "Rome",
    restaurants: [{ ...sample[0], openNow: undefined }],
  });
  assert.ok(!unknown.includes("Open now"));
  assert.ok(!unknown.includes(">Closed<"));
});

test("links to place_id when available, falls back to a text search", () => {
  const html = buildCarouselHtml({ location: "Rome", restaurants: sample });
  assert.match(html, /place\/\?q=place_id:abc123/);
  assert.match(html, /maps\/search\/\?api=1&amp;query=/);
});

test("uses the emoji placeholder when there is no photo", () => {
  const html = buildCarouselHtml({ location: "Rome", restaurants: sample });
  assert.match(html, /class="photo ph"/);
  assert.match(html, /background-image:url\('https:\/\/example\.com\/photo\.jpg'\)/);
});

test("handles an empty restaurant list without throwing", () => {
  const html = buildCarouselHtml({ location: "Nowhere", restaurants: [] });
  assert.match(html, /0 places/);
  assert.ok(!html.includes('class="card"'));
});
