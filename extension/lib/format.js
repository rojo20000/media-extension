// Text shown in the popup for jobs, sizes and helper problems.

export function formatSpeed(bytesPerSecond) {
  if (bytesPerSecond == null) return "";
  if (bytesPerSecond < 1024) return `${Math.round(bytesPerSecond)} B/s`;
  if (bytesPerSecond < 1024 * 1024) return `${Math.round(bytesPerSecond / 1024)} KB/s`;
  return `${(bytesPerSecond / 1048576).toFixed(1)} MB/s`;
}

export function formatEta(seconds) {
  if (seconds == null) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

export function fileNameFromUrl(url) {
  if (url.startsWith("blob:")) return "Embedded player stream";
  try {
    const u = new URL(url);
    const last = u.pathname.split("/").filter(Boolean).pop();
    return last ? decodeURIComponent(last) : u.hostname;
  } catch {
    return url;
  }
}

export function jobText(job) {
  if (job.status === "done") return `Saved: ${job.path.split(/[\\/]/).pop()}`;
  if (job.status === "error") return `Failed: ${job.message}`;
  if (job.stage === "starting") return "Starting…";
  if (job.stage === "processing") return "Processing…";
  if (job.percent == null) return "Downloading…";
  return [`${Math.floor(job.percent)}%`, formatSpeed(job.speed), job.eta != null ? `${formatEta(job.eta)} left` : ""]
    .filter(Boolean).join(" · ");
}

export function helperProblems(helper, site) {
  if (helper.ok === false) {
    return /not found/i.test(helper.error || "")
      ? ["Helper not installed. Run install.ps1 (see README), then reopen this popup."]
      : [`Helper problem: ${helper.error}`];
  }
  if (!helper.ok) return [];
  const { pong } = helper;
  const problems = [];
  if (!pong.ytdlp) problems.push("yt-dlp not found. Re-run install.ps1.");
  if (!pong.ffmpeg) problems.push("ffmpeg not found, so merging video and extracting audio will fail. Re-run install.ps1.");
  if (!pong.deno && site === "youtube") problems.push("Deno not found, so some YouTube formats may be missing. Re-run install.ps1.");
  return problems;
}
