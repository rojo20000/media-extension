// Injected into every frame of the tab by the popup. Its value is the list of
// media this frame shows: <video>/<audio> sources and links to media files.
(() => {
  const MEDIA_LINK = /\.(mp4|webm|mov|mkv|m4v|ogv|mp3|m4a|aac|ogg|oga|opus|wav|flac|m3u8|mpd)(\?|#|$)/i;
  const AUDIO_LINK = /\.(mp3|m4a|aac|ogg|oga|opus|wav|flac)(\?|#|$)/i;
  const items = [];

  const add = (raw, kind) => {
    if (!raw) return;
    let url;
    try {
      url = new URL(raw, document.baseURI).href;
    } catch {
      return;
    }
    if (url.startsWith("data:")) return;
    items.push({ url, kind: url.startsWith("blob:") ? "blob" : kind, source: "page", pageUrl: location.href });
  };

  for (const el of document.querySelectorAll("video, audio")) {
    const kind = el.tagName === "AUDIO" ? "audio" : "video";
    add(el.currentSrc || el.src, kind);
    for (const source of el.querySelectorAll("source")) add(source.src, kind);
  }
  for (const a of document.querySelectorAll("a[href]")) {
    if (MEDIA_LINK.test(a.href)) add(a.href, AUDIO_LINK.test(a.href) ? "audio" : "video");
  }
  return items;
})();
