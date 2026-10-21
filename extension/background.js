// Owns the connection to the native helper, the download jobs, and the media
// responses seen on each tab (for pages without dedicated support).
import { mediaKindFromResponse } from "./lib/media.js";

const HOST = "com.media_extension.host";
const MAX_SNIFFED = 50;

let nativePort = null;
let helper = { ok: null };
const popups = new Set();
const pending = new Map(); // request id -> popup port waiting for the reply
const jobs = new Map(); // job id -> Job
const sniffed = new Map(); // tabId -> Item[]

const ready = chrome.storage.session.get("jobs").then(({ jobs: saved }) => {
  // Anything still "running" from an earlier worker lost its helper process.
  for (const job of saved || []) {
    jobs.set(job.id, job.status === "running" ? { ...job, status: "error", message: "Interrupted" } : job);
  }
});

function saveJobs() {
  chrome.storage.session.set({ jobs: [...jobs.values()] });
}

function post(port, msg) {
  try {
    port.postMessage(msg);
  } catch {
    popups.delete(port);
  }
}

function broadcast(msg) {
  for (const port of popups) post(port, msg);
}

function native() {
  if (nativePort) return nativePort;
  nativePort = chrome.runtime.connectNative(HOST);
  nativePort.onMessage.addListener(onNativeMessage);
  nativePort.onDisconnect.addListener(() => {
    const message = chrome.runtime.lastError?.message || "The helper stopped unexpectedly";
    nativePort = null;
    helper = { ok: false, error: message };
    // Popups learn the helper state before the errors it causes.
    broadcast({ type: "helper", helper });
    for (const job of jobs.values()) {
      if (job.status === "running") updateJob(job.id, { status: "error", message });
    }
    for (const [id, port] of pending) if (port) post(port, { type: "error", reqId: id, message });
    pending.clear();
  });
  return nativePort;
}

function sendNative(msg) {
  try {
    native().postMessage(msg);
    return true;
  } catch (e) {
    helper = { ok: false, error: String(e.message || e) };
    broadcast({ type: "helper", helper });
    return false;
  }
}

function closeIfIdle() {
  const busy = [...jobs.values()].some((j) => j.status === "running");
  if (nativePort && !busy && popups.size === 0 && pending.size === 0) {
    nativePort.disconnect();
    nativePort = null;
  }
}

function updateJob(id, changes) {
  const job = jobs.get(id);
  if (!job) return;
  const next = { ...job, ...changes };
  jobs.set(id, next);
  if (changes.status) saveJobs();
  broadcast({ type: "job", job: next });
  if (changes.status && changes.status !== "running") closeIfIdle();
}

function onNativeMessage(msg) {
  if (msg.type === "pong") {
    helper = { ok: true, pong: msg };
    pending.delete(msg.id);
    broadcast({ type: "helper", helper });
    return;
  }
  if (pending.has(msg.id)) {
    const port = pending.get(msg.id);
    pending.delete(msg.id);
    if (port) post(port, { ...msg, reqId: msg.id });
    return;
  }
  if (msg.type === "progress") {
    updateJob(msg.id, { percent: msg.percent, speed: msg.speed, eta: msg.eta, stage: msg.stage });
  } else if (msg.type === "done") {
    updateJob(msg.id, { status: "done", percent: 100, path: msg.path });
  } else if (msg.type === "error") {
    updateJob(msg.id, { status: "error", message: msg.message });
  }
}

async function onPopupMessage(port, msg) {
  await ready;
  if (msg.type === "init") {
    port.tabId = msg.tabId;
    post(port, {
      type: "state",
      helper,
      jobs: [...jobs.values()].filter((j) => j.tabId === msg.tabId),
      sniffed: await getSniffed(msg.tabId),
    });
    const id = `ping-${crypto.randomUUID()}`;
    pending.set(id, null);
    sendNative({ type: "ping", id });
  } else if (msg.type === "probe") {
    pending.set(msg.reqId, port);
    if (!sendNative({ type: "probe", id: msg.reqId, url: msg.url, site: msg.site })) {
      pending.delete(msg.reqId);
      post(port, { type: "error", reqId: msg.reqId, message: helper.error });
    }
  } else if (msg.type === "download") {
    const job = {
      id: crypto.randomUUID(), tabId: msg.tabId, key: msg.key, label: msg.label, url: msg.url,
      mode: msg.mode, status: "running", percent: null, speed: null, eta: null, stage: "starting",
    };
    jobs.set(job.id, job);
    saveJobs();
    broadcast({ type: "job", job });
    const { url, site, mode, mp3, referer } = msg;
    if (!sendNative({ type: "download", id: job.id, url, site, mode, mp3, referer })) {
      updateJob(job.id, { status: "error", message: helper.error });
    }
  } else if (msg.type === "cancel") {
    sendNative({ type: "cancel", id: msg.id });
  } else if (msg.type === "dismiss") {
    jobs.delete(msg.id);
    saveJobs();
  }
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "popup") return;
  popups.add(port);
  port.onMessage.addListener((msg) => onPopupMessage(port, msg));
  port.onDisconnect.addListener(() => {
    popups.delete(port);
    for (const [id, p] of pending) if (p === port) pending.delete(id);
    closeIfIdle();
  });
});

// --- Media seen on the network, for the fallback list -----------------------

async function getSniffed(tabId) {
  if (!sniffed.has(tabId)) {
    const key = `sniffed:${tabId}`;
    sniffed.set(tabId, (await chrome.storage.session.get(key))[key] || []);
  }
  return sniffed.get(tabId);
}

function clearSniffed(tabId) {
  sniffed.set(tabId, []);
  chrome.storage.session.remove(`sniffed:${tabId}`);
}

chrome.webRequest.onBeforeRequest.addListener(
  (details) => { if (details.tabId >= 0) clearSniffed(details.tabId); },
  { urls: ["<all_urls>"], types: ["main_frame"] },
);

chrome.webRequest.onHeadersReceived.addListener(
  async (details) => {
    if (details.tabId < 0 || details.statusCode >= 400) return;
    const header = (details.responseHeaders || []).find((h) => h.name.toLowerCase() === "content-type");
    const kind = mediaKindFromResponse({ url: details.url, contentType: header?.value || "" });
    if (!kind) return;
    const list = await getSniffed(details.tabId);
    if (list.some((item) => item.url === details.url) || list.length >= MAX_SNIFFED) return;
    list.push({ url: details.url, kind, source: "network" });
    chrome.storage.session.set({ [`sniffed:${details.tabId}`]: list });
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"],
);

chrome.tabs.onRemoved.addListener((tabId) => {
  sniffed.delete(tabId);
  chrome.storage.session.remove(`sniffed:${tabId}`);
  for (const job of jobs.values()) if (job.tabId === tabId && job.status !== "running") jobs.delete(job.id);
  saveJobs();
});
