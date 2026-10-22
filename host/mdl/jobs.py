"""Runs yt-dlp for probes and downloads, one thread per request."""
import itertools
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .paths import move_unique
from .ytdlp import download_args, parse_line, probe_args, summarize_probe, title_byte_limit

HELPER_VERSION = "1.0.0"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEMP_SUFFIXES = (".part", ".ytdl", ".temp")
PROGRESS_INTERVAL = 0.25
PROBE_TIMEOUT = 60  # seconds
STALE_STAGING_SECONDS = 24 * 3600
FILE_ATTRIBUTE_HIDDEN = 0x2


def _popen(args, **kw):
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, **kw)


def _kill_tree(proc):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, creationflags=NO_WINDOW)
    else:
        proc.kill()


def _exists(path):
    return isinstance(path, str) and Path(path).exists()


def _hide(path):
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)


def finished_file(staging):
    files = [p for p in Path(staging).iterdir() if p.is_file() and not p.name.endswith(TEMP_SUFFIXES)]
    return max(files, key=lambda p: p.stat().st_size, default=None)


def _last_error(lines, returncode):
    errors = [m for kind, m in filter(None, map(parse_line, lines)) if kind == "error"]
    return errors[-1] if errors else f"yt-dlp exited with code {returncode}"


class JobRunner:
    def __init__(self, tools, media_dir, send):
        self.tools = tools
        self.media_dir = Path(media_dir)
        self.send = send
        self.procs = {}
        self.cancelled = set()
        self.lock = threading.Lock()
        self.staging_root = self.media_dir / ".incoming"
        self._remove_stale_staging()

    def _remove_stale_staging(self):
        """Clear what interrupted jobs (sleep, Chrome quitting) left behind."""
        if not self.staging_root.is_dir():
            return
        cutoff = time.time() - STALE_STAGING_SECONDS
        for entry in self.staging_root.iterdir():
            try:
                if entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
            except OSError:
                pass

    def _thread(self, target, *args):
        t = threading.Thread(target=self._guard, args=(target, args), daemon=True)
        t.start()
        return t

    def _guard(self, target, args):
        try:
            target(*args)
        except Exception as e:  # every failure must reach the popup
            self.send({"type": "error", "id": args[0], "message": f"{type(e).__name__}: {e}"})

    def ping(self, id_):
        try:
            out = subprocess.run([self.tools.ytdlp, "--version"], capture_output=True, text=True,
                                 timeout=30, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
            ytdlp = out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            ytdlp = None
        self.send({"type": "pong", "id": id_, "helper": HELPER_VERSION, "ytdlp": ytdlp,
                   "ffmpeg": _exists(self.tools.ffmpeg), "deno": _exists(self.tools.deno),
                   "media_dir": str(self.media_dir)})

    def probe(self, id_, url, site):
        return self._thread(self._probe, id_, url, site)

    def _probe(self, id_, url, site):
        proc = _popen(probe_args(self.tools, url), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = proc.communicate(timeout=PROBE_TIMEOUT)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            proc.communicate()
            self.send({"type": "error", "id": id_,
                       "message": f"Timed out reading this page (yt-dlp didn't answer in {PROBE_TIMEOUT:g} s)"})
            return
        if proc.returncode != 0:
            lines = err.decode("utf-8", "replace").splitlines()
            self.send({"type": "error", "id": id_, "message": _last_error(lines, proc.returncode)})
            return
        info = json.loads(out.decode("utf-8", "replace"))
        self.send({"type": "probe_result", "id": id_, **summarize_probe(info, site)})

    def download(self, id_, msg):
        return self._thread(self._download, id_, msg)

    def cancel(self, id_):
        with self.lock:
            self.cancelled.add(id_)
            proc = self.procs.get(id_)
        if proc and proc.poll() is None:
            _kill_tree(proc)

    def _new_staging(self, id_):
        """An empty folder for this job's partial files, named short to keep paths short."""
        if not self.staging_root.exists():
            self.staging_root.mkdir(parents=True, exist_ok=True)
            _hide(self.staging_root)
        for n in itertools.count(1):
            staging = self.staging_root / (id_[:8] if n == 1 else f"{id_[:8]}-{n}")
            try:
                staging.mkdir()
                return staging
            except FileExistsError:
                continue

    def _download(self, id_, msg):
        staging = self._new_staging(id_)
        try:
            self._run_download(id_, msg, staging)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            with self.lock:
                self.procs.pop(id_, None)
                self.cancelled.discard(id_)

    def _run_download(self, id_, msg, staging):
        args = download_args(self.tools, msg["url"], msg.get("site", "generic"), msg.get("mode", "video"),
                             bool(msg.get("mp3")), str(staging), msg.get("referer"), title_byte_limit(staging))
        proc = _popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with self.lock:
            self.procs[id_] = proc
            if id_ in self.cancelled:
                _kill_tree(proc)
        lines, media_id, stage, last_sent = [], None, "downloading", 0.0
        with proc.stdout:
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace")
                lines.append(line)
                parsed = parse_line(line)
                if not parsed:
                    continue
                kind, value = parsed
                if kind == "stage" and stage != "processing":
                    stage = "processing"
                    self.send({"type": "progress", "id": id_, "percent": 100.0, "speed": None,
                               "eta": None, "stage": stage})
                elif kind == "progress":
                    media_id = value.pop("id") or media_id
                    now = time.monotonic()
                    if now - last_sent >= PROGRESS_INTERVAL or value["percent"] == 100.0:
                        last_sent = now
                        self.send({"type": "progress", "id": id_, **value, "stage": stage})
        proc.wait()
        if id_ in self.cancelled:
            self.send({"type": "error", "id": id_, "message": "Cancelled"})
            return
        result = finished_file(staging)
        note = None
        if proc.returncode != 0:
            message = _last_error(lines, proc.returncode)
            # A file that can't take cover art (WAV, for example) is still the download.
            if not (result and message.startswith("Postprocessing:") and "thumbnail" in message.lower()):
                self.send({"type": "error", "id": id_, "message": message})
                return
            note = "cover art not added"
        if result is None:
            self.send({"type": "error", "id": id_, "message": "yt-dlp finished but produced no file"})
            return
        dest = move_unique(result, self.media_dir, media_id or id_)
        done = {"type": "done", "id": id_, "path": str(dest)}
        self.send({**done, "note": note} if note else done)
