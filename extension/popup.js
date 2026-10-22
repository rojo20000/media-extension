import { classifyUrl } from "./lib/sites.js";
import { dedupeMedia } from "./lib/media.js";
import { fileNameFromUrl, helperProblems, jobText } from "./lib/format.js";
import { latestByKey, unmatchedJobs } from "./lib/jobs.js";

const $ = (id) => document.getElementById(id);
const port = chrome.runtime.connect({ name: "popup" });

let tab;
let page;
let helper = { ok: null };
const jobs = new Map();
const jobSlots = new Map(); // job key -> element that shows that key's latest job
const jobButtons = new Map(); // job key -> its option row's Download button

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  el.append(...children.filter((c) => c !== null && c !== undefined));
  return el;
}

function readMp3() {
  try {
    return localStorage.getItem("mp3") === "1";
  } catch {
    return false;
  }
}

function writeMp3(on) {
  try {
    localStorage.setItem("mp3", on ? "1" : "0");
  } catch {
    // Not remembering the checkbox is fine.
  }
}

// --- Helper status ----------------------------------------------------------

function renderHelper() {
  $("status").className = `dot ${helper.ok === true ? "ok" : helper.ok === false ? "bad" : ""}`;
  const problems = helperProblems(helper, page?.site);
  const banner = $("banner");
  banner.replaceChildren(...problems.map((p) => h("p", {}, p)));
  banner.hidden = problems.length === 0;
  if (helper.ok) $("dest").textContent = `Saving to ${helper.pong.media_dir}`;
}

// --- Jobs -------------------------------------------------------------------

function latestJob(key) {
  return latestByKey(jobs.values()).get(key) ?? null;
}

function renderJob(key) {
  const slot = jobSlots.get(key);
  const job = latestJob(key);
  if (!slot) {
    if (job) $("main").append(jobRow(job));
    return;
  }
  const button = jobButtons.get(key);
  if (button) button.disabled = button.dataset.unavailable === "1" || job?.status === "running";
  if (!job) {
    if (button) {
      slot.replaceChildren();
    } else {
      // A job-only row has nothing left to show.
      slot.closest(".row").remove();
      jobSlots.delete(key);
    }
    return;
  }
  const bar = h("div", { class: `bar${job.status === "running" && job.percent == null ? " indeterminate" : ""}` }, h("div"));
  bar.firstChild.style.width = job.status === "running" ? `${job.percent ?? 0}%` : "100%";
  const action = job.status === "running"
    ? h("button", { class: "ghost", title: "Cancel", onclick: () => port.postMessage({ type: "cancel", id: job.id }) }, "✕")
    : h("button", { class: "ghost", title: "Clear", onclick: () => { port.postMessage({ type: "dismiss", id: job.id }); jobs.delete(job.id); renderJob(key); } }, "✕");
  slot.replaceChildren(h("div", { class: `job ${job.status}` },
    job.status === "running" ? bar : null,
    h("div", { class: "line" }, h("span", { title: jobText(job) }, jobText(job)), action)));
}

function startDownload(key, request) {
  port.postMessage({ type: "download", tabId: tab.id, key, mp3: $("mp3").checked, ...request });
}

// A row for a job whose option row isn't shown: one for another URL on this
// tab, or any job while the page is still loading or couldn't be read.
function jobRow(job) {
  const slot = h("div");
  jobSlots.set(job.key, slot);
  const row = h("div", { class: "row" },
    h("div", { class: "row-head" },
      h("div", { class: "row-text" }, h("div", { class: "name", title: job.label }, job.label))),
    slot);
  renderJob(job.key);
  return row;
}

// Forgets the current rows, before main is rebuilt.
function resetRows() {
  jobSlots.clear();
  jobButtons.clear();
}

// Shows `nodes` in main, then a row for each of this tab's jobs that no option row shows.
function showMain(...nodes) {
  const rest = unmatchedJobs(jobs.values(), jobButtons.keys()).map(jobRow);
  $("main").replaceChildren(...nodes, ...rest);
}

// A row with a label, an optional note, a download button and its job status.
function optionRow({ key, label, note, kind, available = true, request }) {
  const slot = h("div");
  jobSlots.set(key, slot);
  const button = h("button", { onclick: () => startDownload(key, { label, ...request }) }, "Download");
  button.dataset.unavailable = available ? "0" : "1";
  jobButtons.set(key, button);
  const row = h("div", { class: "row" },
    h("div", { class: "row-head" },
      kind ? h("span", { class: "kind" }, kind) : null,
      h("div", { class: "row-text" },
        h("div", { class: "name", title: label }, label),
        note ? h("div", { class: "muted small" }, note) : null),
      button),
    slot);
  renderJob(key);
  return row;
}

// --- Supported sites ----------------------------------------------------------

function renderProbe(result) {
  const card = h("div", { class: "card" },
    result.thumbnail ? h("img", { src: result.thumbnail, alt: "" }) : null,
    h("div", {},
      h("div", { class: "title", title: result.title }, result.title),
      result.uploader ? h("div", { class: "muted" }, result.uploader) : null));
  resetRows();
  const rows = Object.entries(result.options).map(([mode, opt]) => optionRow({
    key: `${page.url}|${mode}`,
    label: opt.label,
    note: opt.note,
    available: opt.available,
    request: { url: page.url, site: page.site, mode },
  }));
  showMain(card, ...rows);
  $("footer").hidden = false;
  $("mp3").closest("label").hidden = !("audio" in result.options);
}

const pendingProbes = new Map();

function probe() {
  const reqId = `probe-${crypto.randomUUID()}`;
  pendingProbes.set(reqId, true);
  port.postMessage({ type: "probe", reqId, url: page.url, site: page.site });
}

function showMessage(text, extra) {
  resetRows();
  showMain(h("p", { class: "muted" }, text), ...(extra ? [extra] : []));
}

// --- Other sites ----------------------------------------------------------------

async function scanPage() {
  try {
    const results = await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, files: ["content/scan.js"] });
    return results.flatMap((r) => r.result || []);
  } catch {
    return []; // chrome:// pages, the Web Store, and similar can't be scanned.
  }
}

async function renderGeneric(sniffed) {
  const found = dedupeMedia([...(await scanPage()), ...sniffed]);
  resetRows();
  const pageRow = optionRow({
    key: `${tab.url}|page`,
    label: "Try this page with yt-dlp",
    note: "Works on many other video sites too",
    request: { url: tab.url, site: "generic", mode: "video" },
  });
  const rows = found.map((item) => item.kind === "blob"
    ? null
    : optionRow({
      key: `${item.url}|file`,
      kind: item.kind,
      label: fileNameFromUrl(item.url),
      note: new URL(item.url).hostname,
      request: { url: item.url, site: "generic", mode: item.kind === "audio" ? "audio" : "video", referer: item.pageUrl || tab.url },
    })).filter(Boolean);
  const hasBlob = found.some((item) => item.kind === "blob");
  const intro = rows.length
    ? null
    : h("p", { class: "muted" }, hasBlob
      ? "This page plays media from an embedded stream that can't be saved by its address."
      : "No media found on this page.");
  showMain(...[intro, ...rows, pageRow].filter(Boolean));
  $("footer").hidden = false;
  $("mp3").closest("label").hidden = !found.some((item) => item.kind === "audio");
}

// --- Messages from the background worker ----------------------------------------

port.onMessage.addListener((msg) => {
  if (msg.type === "state") {
    helper = msg.helper;
    for (const job of msg.jobs) jobs.set(job.id, job);
    renderHelper();
    showMessage("Loading…"); // shows this tab's jobs straight away
    if (page.site === "generic") renderGeneric(msg.sniffed);
    else if (!page.item) showMessage("Open a specific video or track to download it.");
    else probe();
  } else if (msg.type === "helper") {
    helper = msg.helper;
    renderHelper();
  } else if (msg.type === "job") {
    if (msg.job.tabId !== tab?.id) return;
    jobs.set(msg.job.id, msg.job);
    renderJob(msg.job.key);
  } else if (pendingProbes.has(msg.reqId)) {
    pendingProbes.delete(msg.reqId);
    if (msg.type === "probe_result") renderProbe(msg);
    else if (helper.ok === false) showMessage("Can't look up this page until the helper problem above is fixed.");
    else showMessage(`Couldn't read this page: ${msg.message}`, h("button", { onclick: () => { showMessage("Loading…"); probe(); } }, "Try again"));
  }
});

async function start() {
  const tabId = Number(new URLSearchParams(location.search).get("tabId"));
  [tab] = tabId ? [await chrome.tabs.get(tabId)] : await chrome.tabs.query({ active: true, currentWindow: true });
  page = classifyUrl(tab.url || "");
  const mp3 = $("mp3");
  mp3.checked = readMp3();
  mp3.addEventListener("change", () => writeMp3(mp3.checked));
  port.postMessage({ type: "init", tabId: tab.id });
}

start();
