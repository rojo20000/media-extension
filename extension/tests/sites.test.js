import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyUrl } from "../lib/sites.js";

const items = [
  ["https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&index=2", "youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
  ["https://youtu.be/dQw4w9WgXcQ?t=10", "youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
  ["https://www.youtube.com/shorts/abcDEF12345", "youtube", "https://www.youtube.com/watch?v=abcDEF12345"],
  ["https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=RD", "youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
  ["https://m.youtube.com/watch?v=dQw4w9WgXcQ", "youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
  ["https://soundcloud.com/artist/some-track?in=x/sets/y", "soundcloud", "https://soundcloud.com/artist/some-track"],
  ["https://www.tiktok.com/@user.name/video/7234567890123456789?lang=en", "tiktok", "https://www.tiktok.com/@user.name/video/7234567890123456789"],
  // yt-dlp only recognises /video/ links; photo posts extract through them as audio.
  ["https://www.tiktok.com/@user/photo/7234567890123456789", "tiktok", "https://www.tiktok.com/@user/video/7234567890123456789"],
];

for (const [input, site, url] of items) {
  test(`item: ${input}`, () => {
    assert.deepEqual(classifyUrl(input), { site, item: true, url });
  });
}

const nonItems = [
  ["https://www.youtube.com/", "youtube"],
  ["https://www.youtube.com/results?search_query=x", "youtube"],
  ["https://soundcloud.com/artist", "soundcloud"],
  ["https://soundcloud.com/artist/sets/x", "soundcloud"],
  ["https://soundcloud.com/discover", "soundcloud"],
  ["https://soundcloud.com/artist/tracks", "soundcloud"],
  ["https://www.tiktok.com/foryou", "tiktok"],
  ["https://www.tiktok.com/@user", "tiktok"],
];

for (const [input, site] of nonItems) {
  test(`non-item: ${input}`, () => {
    const r = classifyUrl(input);
    assert.equal(r.site, site);
    assert.equal(r.item, false);
  });
}

test("generic site", () => {
  assert.deepEqual(classifyUrl("https://example.com/x"), { site: "generic", item: false, url: "https://example.com/x" });
});

test("non-http page is generic non-item", () => {
  assert.equal(classifyUrl("chrome://extensions").site, "generic");
});
