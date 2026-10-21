import { test } from "node:test";
import assert from "node:assert/strict";
import { mediaKindFromResponse, dedupeMedia } from "../lib/media.js";

const cases = [
  [{ url: "https://cdn.x/a", contentType: "video/mp4" }, "video"],
  [{ url: "https://cdn.x/a", contentType: "audio/mpeg; charset=x" }, "audio"],
  [{ url: "https://cdn.x/a", contentType: "application/vnd.apple.mpegurl" }, "stream"],
  [{ url: "https://cdn.x/live/index.m3u8?token=1", contentType: "" }, "stream"],
  [{ url: "https://cdn.x/manifest.mpd", contentType: "" }, "stream"],
  [{ url: "https://cdn.x/seg-12.m4s", contentType: "video/iso.segment" }, null],
  [{ url: "https://cdn.x/clip.webm", contentType: "" }, "video"],
  [{ url: "https://cdn.x/song.mp3", contentType: "" }, "audio"],
  [{ url: "https://x/page", contentType: "text/html" }, null],
];

for (const [input, kind] of cases) {
  test(`kind ${input.url} ${input.contentType} -> ${kind}`, () => {
    assert.equal(mediaKindFromResponse(input), kind);
  });
}

test("dedupeMedia drops repeats ignoring fragment, keeps first", () => {
  const out = dedupeMedia([
    { url: "https://a/v.mp4#t=3", kind: "video", source: "page" },
    { url: "https://a/v.mp4", kind: "video", source: "network" },
    { url: "https://a/s.mp3", kind: "audio", source: "network" },
  ]);
  assert.deepEqual(out, [
    { url: "https://a/v.mp4#t=3", kind: "video", source: "page" },
    { url: "https://a/s.mp3", kind: "audio", source: "network" },
  ]);
});
