# Media Downloader Chrome Extension — Design

Date: 2026-10-17
Status: Draft, awaiting owner approval

## Intent

The owner wants to save media they come across while browsing, mainly:

- a song from YouTube or SoundCloud, as audio
- a TikTok video **without the watermark**
- the sound from a TikTok, as audio

They click the extension's toolbar icon, see what media is on the current
page, and download it. **Quality matters most:** every download should be the
best quality the site serves.

It's a personal tool. It runs on the owner's own Windows PC, installed with
"Load unpacked" in developer mode. It will never be published to the Chrome Web
Store, whose policies forbid YouTube downloaders.

## Goals

1. One click on the toolbar icon opens a popup listing the downloadable media on
   the current tab.
2. First-class support for **YouTube**, **SoundCloud** and **TikTok**:
   - YouTube: "Video (best)" (highest resolution, picture and sound merged into
     one file) and "Audio only (best)".
   - SoundCloud: "Audio (best)". When the artist allows downloads, this is the
     original uploaded file. Otherwise it's the best stream served.
   - TikTok: "Video, no watermark (best)" and "Audio only (sound)".
3. **Fallback for other sites:** list the `<video>`/`<audio>` elements and
   direct media URLs found on the page (sources the page's DOM exposes, plus
   media requests seen on the tab), each with a download button.
4. Show download progress and a done/failed state in the popup.
5. Save files to a `media` folder inside the owner's **actual** Music folder,
   creating it if it's missing. Resolve the folder through Windows' known-folder
   lookup (`FOLDERID_Music`), not a hard-coded `%USERPROFILE%\Music`, so it
   still works if Music has been moved to OneDrive or another drive. Name files after the media
   title, made safe for Windows file names.
6. Keep working over time with little maintenance. The fix for "a site changed"
   should usually be updating yt-dlp.

## Non-goals (v1)

- Playlists, channels, albums or bulk downloads. Only the single item the page
  is about.
- Publishing to the Chrome Web Store, or supporting browsers other than Chrome.
- macOS or Linux support.
- Breaking DRM. Tracks protected by DRM (some SoundCloud Go+ tracks, for
  example) show up as not downloadable with a clear message.
- Members-only, age-restricted or private content that needs a signed-in
  session. The owner's Chrome cookies are not passed to the helper in v1.
- In-popup playback, a library view, or download history beyond the current
  session.

## Anti-goals (a failure even if it technically works)

- **Silently lower quality.** Re-encoding to a lossy format when the owner didn't
  ask, or picking a lower resolution or bitrate than the best available, is a
  failure. Audio is saved in its original codec (e.g. `.opus` or `.m4a`) by
  default. Video streams are merged without re-encoding.
- A TikTok "no watermark" button that actually delivers the watermarked file.
- Saving anywhere other than `Music\media` without telling the owner.
- Failing silently. Every failure shows the reason in the popup.

## Architecture (decided)

The design has two parts, connected by Chrome **native messaging**:

```
[Chrome extension: popup + background service worker + content script]
        |  chrome.runtime.connectNative("<host name>")
        v
[Native helper on Windows]  --runs-->  yt-dlp  --uses-->  ffmpeg
        |
        v
%USERPROFILE%\Music\media\<title>.<ext>
```

The owner chose this over an extension-only build (which would need
ffmpeg.wasm and its own site-specific extractors) because it's more reliable at
the highest quality and is maintained by updating yt-dlp.

### Extension (Manifest V3)

- **Popup.** Opens on icon click. It shows the page's media: title, a thumbnail
  when available, and one button per download option. Each button shows a
  progress bar while downloading and a "done" or error state afterwards. It
  includes a small "Convert to MP3" option for audio, unchecked by default,
  for when a device can't play `.opus` or `.m4a`.
- **Site detection.** The extension works out from the tab URL whether the page
  is YouTube, SoundCloud or TikTok. For those three, the popup offers the
  site-specific options above and hands the **page URL** to the helper. The
  helper and yt-dlp handle extraction. The extension does not try to extract
  stream URLs itself on these sites.
  - Supported page types: YouTube `watch`, `shorts` and `youtu.be` links;
    SoundCloud track pages; TikTok video pages (`/@user/video/<id>`).
  - On a supported site but a non-item page (a home feed or search results,
    for example), the popup says "Open a specific video or track".
- **Fallback scan (other sites).** A content script collects `<video>`/`<audio>`
  `src` and `<source>` URLs plus media links on the page. The background
  worker notes media-looking network responses for the tab (by content type
  or extension: mp4, webm, m4a, mp3, ogg, wav, m3u8, mpd). The popup lists
  them deduplicated. Clicking one passes that URL to the helper, which runs it
  through yt-dlp (yt-dlp handles direct files and HLS/DASH manifests). `blob:`
  URLs can't be downloaded by URL. For those, the popup offers to try the page
  URL with yt-dlp's generic extractor.
- **Helper not installed.** If connecting to the native host fails, the popup
  says so and points to the setup steps in the README.

### Native helper (Windows)

- Speaks the Chrome native messaging protocol over stdin/stdout (4-byte
  little-endian length prefix, then UTF-8 JSON).
- **Messages from the extension:**
  - `probe {url}`: returns the title, thumbnail and which options are
    available (e.g. whether an original SoundCloud download exists, or DRM
    blocks the track).
  - `download {url, mode, mp3}`: `mode` is `video` or `audio`.
  - `cancel {id}`: stops a running download.
  - `ping`: returns the helper, yt-dlp and ffmpeg versions, so the popup can
    tell a missing dependency from a missing helper.
- **Messages to the extension:** `progress {id, percent, speed, eta}`,
  `done {id, path}`, `error {id, message}`.
- **Format choices** (all yt-dlp flags):
  - Video: `-f "bv*+ba/b"`, merged by ffmpeg into `.mkv` when the codecs need
    it and `.mp4` when they're compatible (yt-dlp's
    `--merge-output-format`/remux; no re-encode). Sort for best quality, so
    resolution, then fps, then bitrate.
  - Audio: `-f "ba/b" -x` with **no** `--audio-format`, so the original codec
    is kept. With `mp3: true`: `--audio-format mp3 --audio-quality 0`.
  - SoundCloud: yt-dlp prefers the original `download` format when the track
    allows it, and the best-format choice must not override that.
  - TikTok: choose formats that have no watermark (yt-dlp's TikTok extractor
    exposes these). The implementation must check this against a real TikTok
    and not assume it.
- **Output template:** `<Music folder>\media\%(title)s.%(ext)s`, with
  yt-dlp's Windows-safe file names. Add the ID when names collide.
- **Embed metadata and thumbnail** in audio files where the format supports it
  (`--embed-metadata --embed-thumbnail`), so songs show title, artist and
  artwork in music apps.

### Setup (one time)

A PowerShell `install.ps1` that:

1. Checks for, and if missing installs via `winget`: Python 3 (if the helper
   is written in Python), yt-dlp and ffmpeg.
2. Writes the native messaging host manifest JSON (host name, path to the
   helper launcher, and `allowed_origins` with the extension's ID).
3. Registers it under
   `HKCU\Software\Google\Chrome\NativeMessagingHosts\<host name>`.
4. Creates `%USERPROFILE%\Music\media`.

The extension ID has to be stable so `allowed_origins` matches. Pin it with a
`key` in `manifest.json`.

A README covering: load unpacked, run `install.ps1`, how to update yt-dlp
(`yt-dlp -U` or `winget upgrade yt-dlp`), and troubleshooting.

## Constraints

- Windows 10/11, Google Chrome, Manifest V3.
- Personal use, loaded unpacked. No store policies apply, but nothing that
  breaks DRM.
- Highest-quality output, with no silent re-encoding.

## Left to the builder

- The helper's language. Python is the default, with a `.bat` launcher because
  Chrome on Windows needs an executable path. PowerShell is acceptable if it
  makes setup simpler.
- Popup visual design, icons and layout, within the description above.
- How progress is parsed (`--progress-template` / `--newline` output, or using
  yt-dlp as a Python library).
- The native host name, and the exact project folder layout.
- How much automated testing is practical. At minimum, unit tests for message
  framing, URL/site classification and yt-dlp argument building, plus a
  manual test checklist for each of the three sites.

## Default decisions (check these)

- Audio is kept in its original codec by default, with MP3 as an opt-in
  checkbox.
- Playlists are out of scope for v1.
- Signed-in content (age-restricted, members-only) is out of scope for v1.
- The Music folder is resolved from Windows, so OneDrive or relocated folders
  work.
- Downloads keep running in the helper if the popup closes. Reopening the
  popup on the same tab shows the current progress, because the background
  worker owns the native port.
- If a file with the same name already exists, the new file gets the ID
  appended instead of overwriting the old one.
- TikTok photo/slideshow posts offer "Audio only".
- If TikTok has no watermark-free format for a video, the button is disabled
  with that reason, and no watermarked file is saved under that label.
- The YouTube video container is mkv or mp4, whichever avoids re-encoding.
- Audio files get embedded metadata and thumbnails.
