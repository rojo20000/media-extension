import json
import tempfile
import unittest
from pathlib import Path

from mdl.ytdlp import (TIKTOK_CLEAN, Tools, download_args, load_tools, parse_line,
                       probe_args, summarize_probe)

TOOLS = Tools(ytdlp="C:\\bin\\yt-dlp.exe", ffmpeg="C:\\bin\\ffmpeg.exe", deno="C:\\bin\\deno.exe")


def fmt_arg(args):
    return args[args.index("-f") + 1]


def dl(site, mode, mp3=False, referer=None, tools=TOOLS):
    return download_args(tools, "https://x/item", site, mode, mp3, "C:\\stage\\1", referer)


class ToolsTest(unittest.TestCase):
    def test_load_tools_reads_config(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps({"ytdlp": "Y", "ffmpeg": "F", "deno": "D"}))
            self.assertEqual(load_tools(p), Tools("Y", "F", "D"))

    def test_load_tools_without_config_uses_path_lookup(self):
        tools = load_tools(Path("/nonexistent/config.json"), which=lambda name: f"/usr/bin/{name}")
        self.assertEqual(tools, Tools("/usr/bin/yt-dlp", "/usr/bin/ffmpeg", "/usr/bin/deno"))


class ProbeArgsTest(unittest.TestCase):
    def test_probe_args(self):
        args = probe_args(TOOLS, "https://x/item")
        self.assertEqual(args[0], TOOLS.ytdlp)
        self.assertEqual(args[-1], "https://x/item")
        for flag in ["-J", "--no-playlist", "--ignore-config", "--no-cookies-from-browser"]:
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--ffmpeg-location") + 1], TOOLS.ffmpeg)
        self.assertEqual(args[args.index("--js-runtimes") + 1], "deno:" + TOOLS.deno)

    def test_missing_optional_tools_are_omitted(self):
        args = probe_args(Tools("yt-dlp", None, None), "u")
        self.assertNotIn("--ffmpeg-location", args)
        self.assertNotIn("--js-runtimes", args)


class DownloadArgsTest(unittest.TestCase):
    def test_common_download_flags(self):
        args = dl("youtube", "video")
        self.assertEqual(args[-1], "https://x/item")
        for flag in ["--newline", "--progress", "--no-playlist", "--no-mtime", "--ignore-config"]:
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("-P") + 1], "C:\\stage\\1")
        self.assertEqual(args[args.index("-o") + 1], "%(title).150B.%(ext)s")
        self.assertTrue(args[args.index("--progress-template") + 1].startswith("download:[mdl-progress]"))

    def test_youtube_video_merges_best_without_reencode(self):
        args = dl("youtube", "video")
        self.assertEqual(fmt_arg(args), "bv*+ba/b")
        self.assertEqual(args[args.index("-S") + 1], "res,fps,br")
        self.assertEqual(args[args.index("--merge-output-format") + 1], "mp4/mkv")
        self.assertNotIn("-x", args)

    def test_soundcloud_audio_keeps_original_codec(self):
        args = dl("soundcloud", "audio")
        self.assertEqual(fmt_arg(args), "ba/b")
        self.assertIn("-x", args)
        self.assertIn("--embed-metadata", args)
        self.assertIn("--embed-thumbnail", args)

    def test_tiktok_video_never_falls_back_to_watermarked(self):
        self.assertEqual(fmt_arg(dl("tiktok", "video")), TIKTOK_CLEAN)
        self.assertIn("watermark", TIKTOK_CLEAN)

    def test_tiktok_audio_comes_from_the_video_not_the_music_track(self):
        args = dl("tiktok", "audio")
        self.assertEqual(fmt_arg(args), TIKTOK_CLEAN + "/b/ba")
        self.assertIn("-x", args)

    def test_mp3_only_when_asked(self):
        for site in ["youtube", "soundcloud", "tiktok", "generic"]:
            for mode in ["video", "audio"]:
                self.assertNotIn("--audio-format", dl(site, mode))
        args = dl("youtube", "audio", mp3=True)
        self.assertEqual(args[args.index("--audio-format") + 1], "mp3")
        self.assertEqual(args[args.index("--audio-quality") + 1], "0")

    def test_generic_passes_referer(self):
        args = dl("generic", "video", referer="https://page/")
        self.assertEqual(args[args.index("--referer") + 1], "https://page/")
        self.assertEqual(fmt_arg(args), "bv*+ba/b")
        self.assertNotIn("--referer", dl("youtube", "video", referer="https://page/"))


def f(fid, vcodec="h264", height=None, note=None):
    d = {"format_id": fid, "vcodec": vcodec, "acodec": "aac"}
    if height:
        d["height"] = height
    if note:
        d["format_note"] = note
    return d


class SummarizeProbeTest(unittest.TestCase):
    def info(self, formats, **kw):
        return {"title": "T", "uploader": "U", "thumbnail": "https://t/1.jpg", "duration": 61,
                "formats": formats, **kw}

    def test_youtube_offers_video_with_height_and_audio(self):
        s = summarize_probe(self.info([f("1", height=1080), f("2", height=2160), f("3", "none")]), "youtube")
        self.assertEqual((s["title"], s["uploader"], s["thumbnail"], s["duration"]), ("T", "U", "https://t/1.jpg", 61))
        self.assertEqual(s["options"]["video"], {"available": True, "label": "Video (best · 2160p)"})
        self.assertEqual(s["options"]["audio"], {"available": True, "label": "Audio only (best)"})

    def test_soundcloud_original_file(self):
        s = summarize_probe(self.info([f("hls_opus", "none"), f("download", "none")]), "soundcloud")
        self.assertEqual(s["options"], {"audio": {"available": True, "label": "Audio (original file)"}})

    def test_soundcloud_stream_only_is_labelled(self):
        s = summarize_probe(self.info([f("hls_opus", "none")]), "soundcloud")
        self.assertEqual(s["options"]["audio"], {"available": True, "label": "Audio (best stream)",
                                                 "note": "original file not offered without sign-in"})

    def test_tiktok_clean_video_available(self):
        s = summarize_probe(self.info([f("play_addr", note="Direct video"),
                                       f("download_addr", note="Download video, watermarked"),
                                       f("audio", "none")]), "tiktok")
        self.assertEqual(s["options"]["video"], {"available": True, "label": "Video, no watermark (best)"})
        self.assertEqual(s["options"]["audio"], {"available": True, "label": "Audio only (sound)"})

    def test_tiktok_only_watermarked_disables_video(self):
        s = summarize_probe(self.info([f("download", note="watermarked"),
                                       f("bytevc2", note="(UNPLAYABLE)")]), "tiktok")
        self.assertEqual(s["options"]["video"], {"available": False, "label": "Video, no watermark (best)",
                                                 "note": "no watermark-free version offered"})
        self.assertTrue(s["options"]["audio"]["available"])

    def test_tiktok_photo_post_offers_audio_only(self):
        s = summarize_probe(self.info([f("audio", "none")]), "tiktok")
        self.assertEqual(list(s["options"]), ["audio"])

    def test_generic_offers_download(self):
        s = summarize_probe(self.info([f("0")]), "generic")
        self.assertEqual(s["options"], {"video": {"available": True, "label": "Download"}})

    def test_uploader_falls_back_to_channel(self):
        s = summarize_probe({"title": "T", "channel": "C", "formats": []}, "generic")
        self.assertEqual(s["uploader"], "C")


class ParseLineTest(unittest.TestCase):
    def test_progress(self):
        kind, p = parse_line("[mdl-progress]abc|500|1000|NA|2048.5|7\n")
        self.assertEqual(kind, "progress")
        self.assertEqual(p, {"id": "abc", "percent": 50.0, "speed": 2048.5, "eta": 7})

    def test_progress_uses_estimate_and_tolerates_na(self):
        self.assertEqual(parse_line("[mdl-progress]x|250|NA|1000|NA|NA")[1],
                         {"id": "x", "percent": 25.0, "speed": None, "eta": None})
        self.assertIsNone(parse_line("[mdl-progress]x|250|NA|NA|NA|NA")[1]["percent"])

    def test_postprocessing_stage(self):
        for line in ['[Merger] Merging formats into "a.mkv"', "[ExtractAudio] Destination: a.opus",
                     "[EmbedThumbnail] ffmpeg: Adding thumbnail", "[Metadata] Adding metadata"]:
            self.assertEqual(parse_line(line), ("stage", "processing"))

    def test_error(self):
        self.assertEqual(parse_line("ERROR: [youtube] abc: This video is DRM protected"),
                         ("error", "[youtube] abc: This video is DRM protected"))

    def test_other_lines_ignored(self):
        self.assertIsNone(parse_line("[youtube] Extracting URL"))


if __name__ == "__main__":
    unittest.main()
