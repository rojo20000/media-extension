# Media Downloader Implementation Plan

**Goal:** A Chrome (MV3) extension that lists the media on the current tab and downloads it at the best quality available without signing in, through a Windows native-messaging helper that runs yt-dlp and ffmpeg.

**Architecture:** The popup talks to a background service worker. The worker owns the single native port (`chrome.runtime.connectNative`), tracks download state per tab, and sniffs media responses for the fallback list. The Python helper (stdlib only) frames messages, runs `yt-dlp -J` for probes, runs `yt-dlp` subprocesses for downloads into a per-job staging folder, and moves finished files into `<Music>\media` without overwriting anything.

**Tech Stack:** Chrome MV3 (ES modules, no bundler). Python 3.9+ stdlib (unittest). Node 22 `node --test` for the JS pure modules. PowerShell 5.1+ installer. Dependencies installed with winget: yt-dlp, ffmpeg, Deno.

**Spec:** `docs/specs/2026-10-17-media-downloader-design.md`

## Global Constraints

- Windows 10/11, Google Chrome, Manifest V3, loaded unpacked.
- No re-encoding unless the owner ticks MP3. Audio keeps its original codec. Video is merged and remuxed only, with `--merge-output-format mp4/mkv`.
- Never sign in or pass cookies.
- Output goes to `<FOLDERID_Music>\media`, and an existing file is never overwritten.
- The TikTok "no watermark" option must never deliver a format whose `format_note` contains `watermark`.
- TikTok audio is the video's own audio track: the best non-watermarked combined format, with `-x`. Never use the audio-only `format_id: audio` / "Music track" format, which is the original sound.
- Every failure reaches the popup as readable text.
- Native host name: `com.media_extension.host`.
- The extension ID is pinned by `key` in `extension/manifest.json`. `install.ps1` uses that same ID.

## Review Focus

1. **A popup opened on YouTube home, a SoundCloud profile, or the TikTok For You feed.** It should show "Open a specific video or track", not a broken probe (Task 2 tests).
2. **Helper not registered, or yt-dlp/ffmpeg missing from the PATH Chrome inherited.** The popup should say which one is missing (Task 4 `ping`, Task 6 UI). The installer writes absolute tool paths to `host/config.json` so Chrome's stale PATH doesn't matter (Task 7).
3. **Downloading the same item twice.** The second copy gets ` [<id>]`, then ` (2)` and so on, and is never overwritten (Task 3 test).
4. **Closing the popup mid-download, then reopening it.** The worker keeps the job going and the popup shows its live progress (Task 5).
5. **A TikTok with only watermarked formats, or DRM or an error during probe.** The option is disabled with a reason, or the error text is shown (Task 3 `summarize_probe` tests).

---

### Task 1: Python helper core — framing and paths

**Files:**
- Create: `host/mdl/__init__.py`, `host/mdl/framing.py`, `host/mdl/paths.py`
- Test: `host/tests/test_framing.py`, `host/tests/test_paths.py`

**Interfaces:**
- Produces: `read_message(stream) -> dict | None` (returns None on EOF); `encode_message(obj: dict) -> bytes`; `write_message(stream, obj, lock)`.
- Produces: `music_dir(known_folder=None) -> Path`, which uses `SHGetKnownFolderPath(FOLDERID_Music {4BD8D571-6D19-48D3-BE97-422220080E43})` through ctypes on Windows and falls back to `~/Music`. Also `media_dir() -> Path` (`music_dir()/"media"`, created if missing) and `unique_destination(directory: Path, filename: str, media_id: str) -> Path`.

- [ ] Write the tests:
  - Round-trip: a 4-byte little-endian length, then UTF-8 JSON (including non-ASCII titles).
  - EOF returns None, and a truncated body raises.
  - `unique_destination`: a free name is kept. If `Song.opus` exists, the result is `Song [abc].opus`. If that exists too, the result is `Song [abc] (2).opus`.
  - `music_dir` uses the injected `known_folder` result, and falls back to `Path.home()/"Music"` when it returns None.
- [ ] Run `python3 -m unittest discover -s host/tests -v` and see it FAIL.
- [ ] Implement. On Windows, set stdin and stdout to binary with `msvcrt.setmode`.
- [ ] Run the tests and see them PASS. Commit.

### Task 2: URL classification and fallback media helpers (JS)

**Files:**
- Create: `package.json` (`{"type":"module","private":true,"scripts":{"test":"node --test extension/tests/"}}`), `extension/lib/sites.js`, `extension/lib/media.js`
- Test: `extension/tests/sites.test.js`, `extension/tests/media.test.js`

**Interfaces:**
- Produces: `classifyUrl(url: string) -> {site: "youtube"|"soundcloud"|"tiktok"|"generic", item: boolean, url: string}`. `url` is canonical: YouTube becomes `https://www.youtube.com/watch?v=ID` with playlist parameters dropped.
- Produces: `mediaKindFromResponse({url, contentType}) -> "video"|"audio"|"stream"|null` and `dedupeMedia(items: {url, kind, source}[]) -> items` (deduplicated by URL without the fragment, keeping the first).

- [ ] Write the tests.
  - Items: `youtube.com/watch?v=…&list=…`, `youtu.be/ID`, `youtube.com/shorts/ID`, `music.youtube.com/watch?v=…`, `m.youtube.com/watch?v=…`, `soundcloud.com/artist/track`, `tiktok.com/@u/video/123`, `tiktok.com/@u/photo/123`.
  - Not items: `youtube.com/`, `youtube.com/results?search_query=x`, `soundcloud.com/artist`, `soundcloud.com/artist/sets/x`, `soundcloud.com/discover`, `soundcloud.com/artist/tracks`, `tiktok.com/foryou`, `tiktok.com/@u`.
  - Generic: `example.com/x`.
  - Media kinds: `video/mp4` gives video, `audio/mpeg` gives audio, `application/vnd.apple.mpegurl` and `.m3u8` give stream, `.mpd` gives stream, a `.m4s` segment gives null, `text/html` gives null.
- [ ] Run `npm test` and see it FAIL. Implement. Run it again and see it PASS. Commit.

### Task 3: yt-dlp argument building, probe summary, progress parsing (Python)

**Files:**
- Create: `host/mdl/ytdlp.py`
- Test: `host/tests/test_ytdlp.py`

**Interfaces:**
- Produces: `Tools(ytdlp: str, ffmpeg: str|None, deno: str|None)`, loaded from `host/config.json` by `load_tools(config_path) -> Tools`, falling back to `shutil.which`.
- Produces: `probe_args(tools, url) -> list[str]` = `[ytdlp, "-J", "--no-playlist", "--no-warnings", *common, url]`.
- Produces: `download_args(tools, url, site, mode: "video"|"audio", mp3: bool, staging_dir: str, referer: str|None) -> list[str]`.
- Produces: `summarize_probe(info: dict, site: str) -> {title, uploader, thumbnail, duration, options: {video?: Opt, audio?: Opt}}`, where `Opt = {available: bool, label: str, note?: str}`.
- Produces: `parse_line(line: str) -> ("progress", {percent, speed, eta}) | ("stage", "processing") | ("done", {id, filepath}) | ("error", str) | None`.
- Constants: `TIKTOK_CLEAN = "b[format_note!*=?watermark][format_note!*=?UNPLAYABLE]"`.

`common` = `--ffmpeg-location <ffmpeg>` (if set), `--js-runtimes deno:<deno>` (if set), `--no-cookies-from-browser`. Download args always include `--newline --progress --no-playlist --no-mtime`, `--progress-template "download:[mdl-progress]%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s"`, `--print "after_move:[mdl-done]%(id)s|%(filepath)s"`, `-P <staging_dir>` and `-o "%(title).150B.%(ext)s"`.

| site / mode | format args |
|---|---|
| tiktok video | `-f TIKTOK_CLEAN` (no fallback) |
| tiktok audio | `-f TIKTOK_CLEAN + "/b" -x` |
| any other video | `-f "bv*+ba/b" -S "res,fps,br" --merge-output-format mp4/mkv` |
| any other audio | `-f "ba/b" -x` |
| audio, all sites | `--embed-metadata --embed-thumbnail`; if `mp3`: `--audio-format mp3 --audio-quality 0` |
| generic | add `--referer <referer>` when given |

`summarize_probe` rules:
- YouTube gives `video` and `audio`. The video label includes the best height, e.g. "Video (best · 2160p)".
- SoundCloud gives `audio`. The label is "Audio (original file)" if any format has `format_id == "download"`. Otherwise it's "Audio (best stream)" with the note "original file not offered without sign-in".
- TikTok gives `video` only if a video-bearing format exists whose `format_note` doesn't contain "watermark" or "UNPLAYABLE". If none exists, `available: false` with the note "no watermark-free version offered". It also gives `audio`. Photo posts (no video-bearing format) give `audio` only.
- Generic gives `video` ("Download").

- [ ] Write table-driven tests for every row above. Also assert that no arg list contains `--audio-format` unless `mp3=True`. Use parse tests for progress lines (including `NA` fields → percent None), `[Merger]`/`[ExtractAudio]` → stage, the done line with `|` inside the path, and `ERROR: …` → error.
- [ ] Run and see it FAIL. Implement. Run and see it PASS. Commit.

### Task 4: Helper host loop and jobs

**Files:**
- Create: `host/media_host.py` (entry), `host/mdl/jobs.py`
- Test: `host/tests/test_host.py`. Use a fake `yt-dlp` Python script, written by the test, that prints progress, error and done lines and creates the file in `-P`.

**Interfaces:**
- Consumes: Tasks 1 and 3.
- Protocol, with every message carrying `id` (a string chosen by the extension):
  - In: `{type:"ping"}`, `{type:"probe", url, site}`, `{type:"download", url, site, mode, mp3, referer?}`, `{type:"cancel"}`.
  - Out: `{type:"pong", helper:"1.0.0", ytdlp: str|null, ffmpeg: bool, deno: bool, media_dir}`, `{type:"probe_result", ...summarize_probe}`, `{type:"progress", percent, speed, eta, stage}`, `{type:"done", path}`, `{type:"error", message}`.
- `JobRunner(tools, media_dir, send)` with `.probe(id, url, site)`, `.download(id, msg)`, `.cancel(id)`. Each job runs in a thread.
  - Downloads stage into `media_dir/.incoming/<id>/` and, on done, move to `unique_destination(media_dir, basename, media_id)`.
  - The staging folder is always removed afterwards.
  - Cancel kills the process tree: `taskkill /PID n /T /F` on Windows, `proc.kill()` elsewhere. It then sends an `error` with "Cancelled".
  - A non-zero exit sends the last `ERROR:` line, or "yt-dlp exited with code N".
  - Use `CREATE_NO_WINDOW` on Windows so no console flashes.
- `main()`: read messages until EOF, dispatch, and catch per-message exceptions into an `error` reply.

- [ ] Write tests that drive `JobRunner` with the fake tool:
  - progress → done, with the file moved and the collision suffix applied
  - error exit
  - cancel
  - a framed `ping` through `main()` with in-memory streams
- [ ] Run and see it FAIL. Implement. Run and see it PASS. Commit.

### Task 5: Extension manifest, background worker, scan script

**Files:**
- Create: `extension/manifest.json`, `extension/background.js`, `extension/content/scan.js`, `extension/icons/icon{16,32,48,128}.png` (generated), `tools/make_key.sh` (generates the key, prints `key` and the ID; the private key is not committed)

**Interfaces:**
- Manifest: MV3. Permissions `nativeMessaging`, `scripting`, `activeTab`, `tabs`, `webRequest`, `storage`. `host_permissions: ["<all_urls>"]`. `background.service_worker: "background.js"` with `type: "module"`. `action.default_popup: "popup.html"`. Plus `key`.
- Worker port protocol (popup ↔ worker, `chrome.runtime.connect({name:"popup"})`):
  - Popup → worker: `{type:"init", tabId}`, `{type:"probe", url, site}`, `{type:"download", url, site, mode, mp3, referer}`, `{type:"cancel", id}`.
  - Worker → popup: `{type:"state", helper: {ok, error?, pong?}, jobs: Job[], sniffed: Item[]}`, `{type:"probe_result"|"error", reqId, ...}`, `{type:"job", job}`.
  - `Job = {id, tabId, url, mode, label, status:"running"|"done"|"error", percent, speed, eta, stage, path?, message?}`.
- The worker connects to the native port lazily and keeps it open while any job runs. On `onDisconnect` it marks running jobs as errors with `chrome.runtime.lastError.message`. The helper status is the result of `ping`.
- Sniffing: `webRequest.onHeadersReceived` with `tabId >= 0` is classified by `mediaKindFromResponse` and stored per tab in `chrome.storage.session`. It is cleared when a top-level navigation starts (`tabs.onUpdated` with a changed `url`) and on `tabs.onRemoved`.
- `content/scan.js`: an IIFE whose value is `{url, kind, source:"page"}[]`, built from `video`/`audio` `currentSrc`/`src`, `<source src>`, and `<a href>` with media extensions. Relative URLs are resolved, `data:` is skipped, and `blob:` is kept as `kind:"blob"`.

- [ ] Run `tools/make_key.sh` and paste the `key` into the manifest. Record the ID for Task 7.
- [ ] Check: `node -e` JSON-parses the manifest. `node --check extension/background.js` and `node --check extension/content/scan.js` pass. The ID derived from `key` (sha256 of the DER key, first 32 hex digits mapped 0-f→a-p) matches the recorded one.
- [ ] Commit.

### Task 6: Popup UI

**Files:**
- Create: `extension/popup.html`, `extension/popup.css`, `extension/popup.js`

Behaviour:
1. The popup gets the active tab and runs `classifyUrl`.
   - Site item: send `probe`, then show a header with the title, uploader and thumbnail, a button for each `Opt` (disabled with its note when unavailable), and an "Convert audio to MP3" checkbox (unchecked).
   - Site non-item: show "Open a specific video or track".
   - Generic: inject `content/scan.js` (all frames), merge with the sniffed items through `dedupeMedia`, and list them with a "Download" button each. Blob items get a "Try this page with yt-dlp" button. Show "No media found on this page" when the list is empty.
2. Jobs for this tab render under their button: a progress bar, then a "processing…" stage, then "Saved: <filename>" or the error text. Running jobs get a cancel ✕.
3. Helper problems show a banner. Not connected: "Helper not installed — run install.ps1 (see README)". `pong.ytdlp` null: "yt-dlp not found". `pong.ffmpeg` false: "ffmpeg not found".
4. Use light and dark themes through `prefers-color-scheme`, at about 360px wide.

- [ ] Check: `node --check extension/popup.js`. Manually load the extension in Chromium here with a stub host to see the generic list and the banner render (headless screenshot via Playwright).
- [ ] Commit.

### Task 7: Windows installer and README

**Files:**
- Create: `install.ps1`, `uninstall.ps1`
- Modify: `README.md`

`install.ps1`:
1. Install whatever is missing using `winget install -e --id`: `Python.Python.3.12`, `yt-dlp.yt-dlp`, `Gyan.FFmpeg`, `DenoLand.Deno`, all with `--accept-source-agreements --accept-package-agreements`.
2. Refresh `$env:Path` from the Machine and User registry values, then resolve absolute paths with `Get-Command`. Python is resolved through `py -3 -c "import sys;print(sys.executable)"`, falling back to `python`.
3. Write `host/config.json` with `{python, ytdlp, ffmpeg, deno}`.
4. Write `host/media_host.bat`: `@echo off` followed by `"<python>" -u "%~dp0media_host.py" %*`.
5. Write `host/com.media_extension.host.json` with `{name, description, path: <abs bat>, type:"stdio", allowed_origins:["chrome-extension://<ID>/"]}`. The `-ExtensionId` parameter defaults to the Task 5 ID.
6. Set the default value of `HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.media_extension.host` to that JSON's path.
7. Create the `media` folder in `[Environment]::GetFolderPath('MyMusic')`.
8. Print a summary.

`uninstall.ps1` removes the registry key.

The README covers:
- loading unpacked
- running the installer (`powershell -ExecutionPolicy Bypass -File install.ps1`)
- updating with `winget upgrade yt-dlp.yt-dlp`
- troubleshooting (the banner messages)
- a manual test checklist: a YouTube song as audio, a 4K video, SoundCloud with and without the original file, a TikTok video without watermark, TikTok audio, a TikTok photo post, a generic page with `<video>`, a duplicate download, closing the popup mid-download

- [ ] Check: PowerShell isn't available here, so review the script carefully against the steps. Check that `host/config.json`, `media_host.bat` and the host JSON are git-ignored.
- [ ] Commit.

### Task 8: End-to-end smoke test (Linux, here)

- [ ] Run the real `host/media_host.py` with the real yt-dlp (pip, in a scratch venv) and ffmpeg against a local HTTP server serving a generated mp4. The flow is framed `ping` → `probe` → `download` (video, generic). Assert that the file lands in `media_dir` and that a second run applies the collision suffix.
- [ ] Run all unit tests (`python3 -m unittest`, `npm test`). Push.
