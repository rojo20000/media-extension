import io
import json
import os
import stat
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from mdl.framing import encode_message, read_message
from mdl import jobs
from mdl.jobs import JobRunner
from mdl.ytdlp import Tools, title_byte_limit
import media_host

FAKE = textwrap.dedent("""\
    #!{python}
    import json, os, sys, time
    args = sys.argv[1:]
    url = args[-1]
    if "--version" in args:
        print("2026.08.19"); sys.exit(0)
    if "-J" in args:
        if url == "hang":
            time.sleep(30)
        if url == "fail":
            print("ERROR: [generic] Unsupported URL: fail", file=sys.stderr); sys.exit(1)
        print(json.dumps({{"title": "Song", "uploader": "Artist", "formats": [{{"format_id": "download", "vcodec": "none"}}]}}))
        sys.exit(0)
    stage = args[args.index("-P") + 1]
    if url == "args":
        os.makedirs(stage, exist_ok=True)
        open(os.path.join(stage, "Song.opus"), "w").write(json.dumps(args)); sys.exit(0)
    if url == "fail":
        print("[generic] Extracting"); print("ERROR: [generic] boom: unavailable"); sys.exit(1)
    if url == "thumbfail":
        os.makedirs(stage, exist_ok=True)
        open(os.path.join(stage, "Song.wav"), "w").write("wav")
        print("ERROR: Postprocessing: Supported filetypes for thumbnail embedding are: mp3, mkv/mka, ogg/opus/flac, m4a/mp4/m4v/mov")
        sys.exit(1)
    if url == "mergefail":
        os.makedirs(stage, exist_ok=True)
        open(os.path.join(stage, "Song.f137.mp4"), "w").write("video only")
        print("ERROR: Postprocessing: ffmpeg not found"); sys.exit(1)
    print("[mdl-progress]abc|50|100|NA|1000|1", flush=True)
    if url == "slow":
        time.sleep(30)
    os.makedirs(stage, exist_ok=True)
    open(os.path.join(stage, "Song.opus.part"), "w").close()
    os.remove(os.path.join(stage, "Song.opus.part"))
    print("[ExtractAudio] Destination: Song.opus", flush=True)
    with open(os.path.join(stage, "Song.opus"), "w") as f:
        f.write("audio")
    print("[mdl-progress]abc|100|100|NA|1000|0", flush=True)
""")


class Collector:
    def __init__(self):
        self.messages = []
        self.lock = threading.Lock()

    def __call__(self, msg):
        with self.lock:
            self.messages.append(msg)

    def of(self, type_):
        return [m for m in self.messages if m["type"] == type_]


class JobRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        fake = root / "yt-dlp"
        fake.write_text(FAKE.format(python=sys.executable))
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.media = root / "media"
        self.media.mkdir()
        self.sent = Collector()
        self.runner = JobRunner(Tools(str(fake), None, None), self.media, self.sent)

    def tearDown(self):
        self.tmp.cleanup()

    def download(self, url, id_="1"):
        return self.runner.download(id_, {"url": url, "site": "soundcloud", "mode": "audio", "mp3": False})

    def test_download_reports_progress_and_moves_file(self):
        self.download("ok").join(10)
        progress = self.sent.of("progress")
        self.assertEqual(progress[0]["percent"], 50.0)
        self.assertIn("processing", [p["stage"] for p in progress])
        [done] = self.sent.of("done")
        self.assertEqual(done, {"type": "done", "id": "1", "path": str(self.media / "Song.opus")})
        self.assertEqual((self.media / "Song.opus").read_text(), "audio")
        self.assertFalse((self.media / ".incoming" / "1").exists())

    def test_second_download_gets_id_suffix(self):
        self.download("ok", "1").join(10)
        self.download("ok", "2").join(10)
        self.assertEqual(self.sent.of("done")[1]["path"], str(self.media / "Song [abc].opus"))
        self.assertTrue((self.media / "Song.opus").exists())

    def recorded_args(self):
        [done] = self.sent.of("done")
        return json.loads(Path(done["path"]).read_text())

    def test_staging_folder_name_is_short(self):
        job_id = "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
        self.download("args", job_id).join(10)
        args = self.recorded_args()
        self.assertEqual(Path(args[args.index("-P") + 1]), self.media / ".incoming" / "1a2b3c4d")
        self.assertFalse((self.media / ".incoming" / "1a2b3c4d").exists())

    def test_title_limit_follows_the_staging_path_length(self):
        media = Path(self.tmp.name) / ("OneDrive - " + "x" * 120) / "Music" / "media"
        media.mkdir(parents=True)
        runner = JobRunner(self.runner.tools, media, self.sent)
        runner.download("1", {"url": "args", "site": "tiktok", "mode": "video"}).join(10)
        args = self.recorded_args()
        staging = args[args.index("-P") + 1]
        self.assertLess(title_byte_limit(staging), 150)
        self.assertEqual(args[args.index("-o") + 1], f"%(title).{title_byte_limit(staging)}B.%(ext)s")

    def test_leftover_staging_folder_with_the_same_name_is_left_alone(self):
        leftover = self.media / ".incoming" / "1a2b3c4d"
        leftover.mkdir(parents=True)
        (leftover / "Other.opus.part").write_text("x")
        self.download("args", "1a2b3c4d-0000").join(10)
        args = self.recorded_args()
        self.assertNotEqual(Path(args[args.index("-P") + 1]), leftover)
        self.assertTrue((leftover / "Other.opus.part").exists())

    def test_failed_download_reports_last_error(self):
        self.download("fail").join(10)
        self.assertEqual(self.sent.of("error"), [{"type": "error", "id": "1", "message": "[generic] boom: unavailable"}])
        self.assertEqual(self.sent.of("done"), [])
        self.assertFalse((self.media / ".incoming" / "1").exists())

    def test_thumbnail_embed_failure_still_saves_the_file(self):
        self.download("thumbfail").join(10)
        [done] = self.sent.of("done")
        self.assertEqual(done["path"], str(self.media / "Song.wav"))
        self.assertEqual(done["note"], "cover art not added")
        self.assertEqual(self.sent.of("error"), [])

    def test_other_postprocessing_failure_is_an_error(self):
        self.download("mergefail").join(10)
        self.assertEqual(self.sent.of("done"), [])
        self.assertEqual(self.sent.of("error")[0]["message"], "Postprocessing: ffmpeg not found")

    def test_ping_survives_bad_tool_paths(self):
        runner = JobRunner(Tools(self.runner.tools.ytdlp, ["not", "a", "path"], ["x"]), self.media, self.sent)
        runner.ping("q")
        [pong] = self.sent.of("pong")
        self.assertEqual((pong["ffmpeg"], pong["deno"]), (False, False))

    def test_stale_staging_folders_are_removed_on_start(self):
        old = self.media / ".incoming" / "old"
        fresh = self.media / ".incoming" / "fresh"
        for d in (old, fresh):
            d.mkdir(parents=True)
            (d / "x.part").write_text("x")
        os.utime(old, (time.time() - 3 * 86400,) * 2)
        JobRunner(self.runner.tools, self.media, self.sent)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_cancel_stops_download(self):
        t = self.download("slow")
        deadline = time.time() + 10
        while not self.sent.of("progress") and time.time() < deadline:
            time.sleep(0.05)
        self.runner.cancel("1")
        t.join(10)
        self.assertFalse(t.is_alive())
        self.assertEqual(self.sent.of("error"), [{"type": "error", "id": "1", "message": "Cancelled"}])
        self.assertEqual(list(self.media.glob("*.opus")), [])

    def test_probe_result(self):
        self.runner.probe("p", "ok", "soundcloud").join(10)
        [r] = self.sent.of("probe_result")
        self.assertEqual((r["id"], r["title"], r["uploader"]), ("p", "Song", "Artist"))
        self.assertEqual(r["options"]["audio"]["label"], "Audio (original file)")

    def test_probe_error(self):
        self.runner.probe("p", "fail", "generic").join(10)
        self.assertEqual(self.sent.of("error"), [{"type": "error", "id": "p", "message": "[generic] Unsupported URL: fail"}])

    def test_probe_times_out(self):
        with mock.patch.object(jobs, "PROBE_TIMEOUT", 0.5):
            t = self.runner.probe("p", "hang", "youtube")
            t.join(10)
        self.assertFalse(t.is_alive())
        self.assertEqual(self.sent.of("error"), [{"type": "error", "id": "p", "message":
                         "Timed out reading this page (yt-dlp didn't answer in 0.5 s)"}])
        self.assertEqual(self.sent.of("probe_result"), [])

    def test_ping(self):
        self.runner.ping("q")
        [pong] = self.sent.of("pong")
        self.assertEqual(pong["ytdlp"], "2026.08.19")
        self.assertFalse(pong["ffmpeg"])
        self.assertEqual(pong["media_dir"], str(self.media))


class MainLoopTest(unittest.TestCase):
    def test_ping_and_unknown_type_through_framing(self):
        with tempfile.TemporaryDirectory() as d:
            stdin = io.BytesIO(encode_message({"type": "ping", "id": "a"}) +
                               encode_message({"type": "bogus", "id": "b"}))
            stdout = io.BytesIO()
            media_host.main(stdin, stdout, Tools("/nonexistent/yt-dlp", None, None), Path(d))
            stdout.seek(0)
            out = [read_message(stdout), read_message(stdout)]
        self.assertEqual(out[0]["type"], "pong")
        self.assertIsNone(out[0]["ytdlp"])
        self.assertEqual(out[1], {"type": "error", "id": "b", "message": "Unknown message type: bogus"})

    def run_main(self, *messages, **kw):
        stdin = io.BytesIO(b"".join(encode_message(m) for m in messages))
        stdout = io.BytesIO()
        media_host.main(stdin, stdout, Tools("/nonexistent/yt-dlp", None, None), **kw)
        stdout.seek(0)
        return [read_message(stdout) for _ in messages]

    def test_media_folder_failure_is_reported_instead_of_exiting(self):
        denied = PermissionError(13, "Access is denied", "C:\\Users\\a\\Music\\media")
        with mock.patch.object(media_host, "media_dir", side_effect=denied), \
                self.assertLogs("media_host", "ERROR"):
            out = self.run_main({"type": "ping", "id": "a"}, {"type": "probe", "id": "b", "url": "u"})
        for reply, id_ in zip(out, "ab"):
            self.assertEqual(reply["type"], "error")
            self.assertEqual(reply["id"], id_)
            self.assertIn("Couldn't create the media folder", reply["message"])
            self.assertIn("Access is denied", reply["message"])

    def test_log_file_failure_is_reported_on_ping(self):
        with tempfile.TemporaryDirectory() as d:
            problem = media_host.setup_logging(Path(d) / "missing" / "media_host.log")
            self.assertIn("media_host.log", problem)
            [reply] = self.run_main({"type": "ping", "id": "a"}, media=Path(d), startup_error=problem)
        self.assertEqual(reply, {"type": "error", "id": "a", "message": problem})


if __name__ == "__main__":
    unittest.main()
