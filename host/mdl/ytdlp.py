"""Everything about how yt-dlp is called and how its output is read."""
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Best combined format that isn't watermarked or in TikTok's unplayable codec.
TIKTOK_CLEAN = "b[format_note!*=?watermark][format_note!*=?UNPLAYABLE]"

PROGRESS_TEMPLATE = ("download:[mdl-progress]%(info.id)s|%(progress.downloaded_bytes)s|"
                     "%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|"
                     "%(progress.speed)s|%(progress.eta)s")
OUTPUT_TEMPLATE = "%(title).{}B.%(ext)s"

# Windows paths (and ffmpeg) stop at 260 characters, including the final NUL.
MAX_PATH = 259
# What yt-dlp adds after the title while working, e.g. ".f137.mp4.part-Frag12".
SUFFIX_ROOM = 25
TITLE_BYTES_MAX = 150
TITLE_BYTES_MIN = 40

_STAGE = re.compile(r"^\[(Merger|ExtractAudio|EmbedThumbnail|Metadata|Fixup\w*|VideoRemuxer|ThumbnailsConvertor)\]")


@dataclass(frozen=True)
class Tools:
    ytdlp: str
    ffmpeg: Optional[str]
    deno: Optional[str]


def load_tools(config_path, which=shutil.which):
    """Absolute tool paths written by install.ps1, falling back to PATH lookup."""
    config = {}
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        pass
    def configured(name):
        value = config.get(name)
        return value if isinstance(value, str) and value else None

    return Tools(
        ytdlp=configured("ytdlp") or which("yt-dlp") or "yt-dlp",
        ffmpeg=configured("ffmpeg") or which("ffmpeg"),
        deno=configured("deno") or which("deno"),
    )


def _common(tools):
    args = ["--ignore-config", "--no-cookies-from-browser", "--encoding", "utf-8"]
    if tools.ffmpeg:
        args += ["--ffmpeg-location", tools.ffmpeg]
    if tools.deno:
        args += ["--js-runtimes", "deno:" + tools.deno]
    return args


def probe_args(tools, url):
    return [tools.ytdlp, "-J", "--no-playlist", "--no-warnings", *_common(tools), url]


def title_byte_limit(staging_dir):
    """How many bytes of title fit in `staging_dir` without passing MAX_PATH.

    Bytes, because yt-dlp truncates in UTF-8 bytes, and no title has more UTF-16
    characters than UTF-8 bytes. A very long folder still gets a usable title.
    """
    room = MAX_PATH - len(str(staging_dir)) - 1 - SUFFIX_ROOM
    return max(TITLE_BYTES_MIN, min(TITLE_BYTES_MAX, room))


def download_args(tools, url, site, mode, mp3, staging_dir, referer, title_bytes=TITLE_BYTES_MAX):
    args = [tools.ytdlp, *_common(tools), "--newline", "--progress", "--no-playlist", "--no-mtime",
            "--progress-template", PROGRESS_TEMPLATE, "-P", staging_dir,
            "-o", OUTPUT_TEMPLATE.format(title_bytes)]
    if site == "tiktok":
        # TikTok's audio-only format is the original sound, not this video's audio.
        args += ["-f", TIKTOK_CLEAN if mode == "video" else TIKTOK_CLEAN + "/b/ba"]
    elif mode == "video":
        args += ["-f", "bv*+ba/b", "-S", "res,fps,br", "--merge-output-format", "mp4/mkv"]
    else:
        args += ["-f", "ba/b"]
    if mode == "audio":
        args += ["-x", "--embed-metadata", "--embed-thumbnail"]
        if mp3:
            args += ["--audio-format", "mp3", "--audio-quality", "0"]
    if site == "generic" and referer:
        args += ["--referer", referer]
    return args + [url]


def _has_video(fmt):
    return fmt.get("vcodec") != "none"


def _is_clean_tiktok(fmt):
    note = fmt.get("format_note") or ""
    return _has_video(fmt) and "watermark" not in note and "UNPLAYABLE" not in note


def summarize_probe(info, site):
    formats = info.get("formats") or []
    options = {}
    if site == "youtube":
        height = max((f.get("height") or 0 for f in formats if _has_video(f)), default=0)
        options["video"] = {"available": True, "label": f"Video (best · {height}p)" if height else "Video (best)"}
        options["audio"] = {"available": True, "label": "Audio only (best)"}
    elif site == "soundcloud":
        if any(f.get("format_id") == "download" for f in formats):
            options["audio"] = {"available": True, "label": "Audio (original file)"}
        elif formats and all("preview" in (f.get("format_id") or "") for f in formats):
            # Signed out, Go+ and DRM tracks only offer the 30-second snippet.
            options["audio"] = {"available": False, "label": "Audio (best stream)",
                                "note": "only a 30-second preview is available (Go+ or DRM track)"}
        else:
            options["audio"] = {"available": True, "label": "Audio (best stream)",
                                "note": "original file not offered without sign-in"}
    elif site == "tiktok":
        if any(_has_video(f) for f in formats):
            video = {"available": True, "label": "Video, no watermark (best)"}
            if not any(_is_clean_tiktok(f) for f in formats):
                video = {**video, "available": False, "note": "no watermark-free version offered"}
            options["video"] = video
        options["audio"] = {"available": True, "label": "Audio only (sound)"}
    else:
        options["video"] = {"available": True, "label": "Download"}
    return {
        "title": info.get("title") or "Untitled",
        "uploader": info.get("uploader") or info.get("channel") or info.get("creator"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "options": options,
    }


def _num(value):
    try:
        return float(value)
    except ValueError:
        return None


def parse_line(line):
    line = line.rstrip("\r\n")
    if line.startswith("[mdl-progress]"):
        media_id, done, total, estimate, speed, eta = line[len("[mdl-progress]"):].split("|")
        done, size = _num(done), _num(total) or _num(estimate)
        percent = round(done / size * 100, 1) if done is not None and size else None
        eta = _num(eta)
        return "progress", {"id": media_id, "percent": percent, "speed": _num(speed),
                            "eta": int(eta) if eta is not None else None}
    if _STAGE.match(line):
        return "stage", "processing"
    if line.startswith("ERROR: "):
        return "error", line[len("ERROR: "):]
    return None
