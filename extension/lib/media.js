// Helpers for the fallback list on sites without dedicated support.

const VIDEO_EXT = /\.(mp4|webm|mov|mkv|m4v|ogv)$/i;
const AUDIO_EXT = /\.(mp3|m4a|aac|ogg|oga|opus|wav|flac|weba)$/i;
const STREAM_EXT = /\.(m3u8|mpd)$/i;
const STREAM_TYPES = ["mpegurl", "dash+xml"];

function pathOf(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return url.split(/[?#]/)[0];
  }
}

export function mediaKindFromResponse({ url, contentType = "" }) {
  const type = contentType.toLowerCase().split(";")[0].trim();
  const path = pathOf(url);
  if (STREAM_TYPES.some((t) => type.includes(t)) || STREAM_EXT.test(path)) return "stream";
  // Segments of an adaptive stream are useless on their own.
  if (/\.(m4s|ts)$/i.test(path) || type.includes("segment")) return null;
  if (type.startsWith("video/") || VIDEO_EXT.test(path)) return "video";
  if (type.startsWith("audio/") || AUDIO_EXT.test(path)) return "audio";
  return null;
}

export function mediaKindFromUrl(url) {
  return mediaKindFromResponse({ url });
}

export function dedupeMedia(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item.url.split("#")[0];
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
