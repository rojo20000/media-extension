// Works out which supported site a tab is on, and whether it shows one item.

const YT_ID = /^[A-Za-z0-9_-]{11}$/;
const YT_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"]);
const SC_HOSTS = new Set(["soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"]);
const TT_HOSTS = new Set(["tiktok.com", "www.tiktok.com", "m.tiktok.com"]);

const SC_TOP_LEVEL = new Set([
  "discover", "feed", "you", "search", "stream", "upload", "charts", "stations",
  "pages", "settings", "messages", "notifications", "people", "tags", "terms-of-use", "mobile",
]);
const SC_ARTIST_TABS = new Set([
  "sets", "tracks", "albums", "reposts", "likes", "followers", "following",
  "popular-tracks", "comments", "spotlight", "toptracks",
]);

const youtube = (id) => ({ site: "youtube", item: true, url: `https://www.youtube.com/watch?v=${id}` });

export function classifyUrl(raw) {
  let u;
  try {
    u = new URL(raw);
  } catch {
    return { site: "generic", item: false, url: raw };
  }
  const host = u.hostname.toLowerCase();
  const parts = u.pathname.split("/").filter(Boolean);

  if (host === "youtu.be" && YT_ID.test(parts[0] || "")) return youtube(parts[0]);
  if (YT_HOSTS.has(host)) {
    const v = u.searchParams.get("v");
    if (parts[0] === "watch" && YT_ID.test(v || "")) return youtube(v);
    if (parts[0] === "shorts" && YT_ID.test(parts[1] || "")) return youtube(parts[1]);
    return { site: "youtube", item: false, url: raw };
  }

  if (SC_HOSTS.has(host)) {
    const isTrack =
      (parts.length === 2 || (parts.length === 3 && parts[2].startsWith("s-"))) &&
      !SC_TOP_LEVEL.has(parts[0]) && !SC_ARTIST_TABS.has(parts[1]);
    return isTrack
      ? { site: "soundcloud", item: true, url: `https://soundcloud.com/${parts.join("/")}` }
      : { site: "soundcloud", item: false, url: raw };
  }

  if (TT_HOSTS.has(host)) {
    const isPost = parts.length === 3 && parts[0].startsWith("@") &&
      (parts[1] === "video" || parts[1] === "photo") && /^\d+$/.test(parts[2]);
    return isPost
      // yt-dlp only recognises /video/ links; photo posts come back as audio through them.
      ? { site: "tiktok", item: true, url: `https://www.tiktok.com/${parts[0]}/video/${parts[2]}` }
      : { site: "tiktok", item: false, url: raw };
  }

  return { site: "generic", item: false, url: raw };
}
