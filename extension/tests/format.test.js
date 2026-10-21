import { test } from "node:test";
import assert from "node:assert/strict";
import { formatSpeed, formatEta, fileNameFromUrl, jobText, helperProblems } from "../lib/format.js";

test("formatSpeed", () => {
  assert.equal(formatSpeed(null), "");
  assert.equal(formatSpeed(512), "512 B/s");
  assert.equal(formatSpeed(2.5 * 1024 * 1024), "2.5 MB/s");
  assert.equal(formatSpeed(300 * 1024), "300 KB/s");
});

test("formatEta", () => {
  assert.equal(formatEta(null), "");
  assert.equal(formatEta(7), "0:07");
  assert.equal(formatEta(3725), "1:02:05");
});

test("fileNameFromUrl decodes the last path segment", () => {
  assert.equal(fileNameFromUrl("https://cdn.x/a/My%20Song.mp3?sig=1"), "My Song.mp3");
  assert.equal(fileNameFromUrl("https://cdn.x/"), "cdn.x");
  assert.equal(fileNameFromUrl("blob:https://x/123-abc"), "Embedded player stream");
});

test("jobText per status", () => {
  assert.equal(jobText({ status: "running", stage: "starting" }), "Starting…");
  assert.equal(jobText({ status: "running", stage: "downloading", percent: 45.2, speed: 2 * 1048576, eta: 12 }),
    "45% · 2.0 MB/s · 0:12 left");
  assert.equal(jobText({ status: "running", stage: "downloading", percent: null, speed: null, eta: null }), "Downloading…");
  assert.equal(jobText({ status: "running", stage: "processing" }), "Processing…");
  assert.equal(jobText({ status: "done", path: "C:\\Users\\a\\Music\\media\\Song.opus" }), "Saved: Song.opus");
  assert.equal(jobText({ status: "error", message: "boom" }), "Failed: boom");
});

test("helperProblems: not installed", () => {
  assert.deepEqual(helperProblems({ ok: false, error: "Specified native messaging host not found." }),
    ["Helper not installed. Run install.ps1 (see README), then reopen this popup."]);
});

test("helperProblems: other disconnect", () => {
  assert.deepEqual(helperProblems({ ok: false, error: "Native host has exited." }),
    ["Helper problem: Native host has exited."]);
});

test("helperProblems: missing tools", () => {
  const pong = { ytdlp: null, ffmpeg: false, deno: false };
  assert.deepEqual(helperProblems({ ok: true, pong }, "youtube"), [
    "yt-dlp not found. Re-run install.ps1.",
    "ffmpeg not found, so merging video and extracting audio will fail. Re-run install.ps1.",
    "Deno not found, so some YouTube formats may be missing. Re-run install.ps1.",
  ]);
  assert.deepEqual(helperProblems({ ok: true, pong: { ytdlp: "1", ffmpeg: true, deno: false } }, "tiktok"), []);
  assert.deepEqual(helperProblems({ ok: null }), []);
});
