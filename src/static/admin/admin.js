"use strict";
// Admin page of the print server. Server data reaches the DOM only through textContent and createElement.

const POLL_MS = 3000;
const JOB_LIMIT = 60;
const TOKEN_KEY = "thermal-admin-token";
const NOTICE_MS = 6000;
const TIME = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const SECONDS = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
const DAY = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" });
const KIND = { receipt: "Receipt", image: "Image", template: "Ticket" };
const ROUTE = { tunnel: "Cloudflare tunnel", direct: "Direct" };
const EVENT = {
  received: "Received", rendered: "Rendered", sending: "Sending", sent: "Sent", printed: "Printed",
  released: "Released", failed: "Failed", expired: "Expired", cancelled: "Cancelled", moved: "Moved",
  reprinted: "Reprinted",
};
const EVENT_TONE = { printed: "ok", sending: "busy", sent: "busy", released: "warn", expired: "warn", failed: "down" };
const FINAL_BAD = new Set(["failed", "expired", "cancelled"]);

const $ = (id) => document.getElementById(id);
const wide = matchMedia("(min-width: 900px)");
const state = {
  token: readToken(),
  gate: null,
  view: "rail",
  jobId: null,
  printers: [],
  jobs: [],
  stats: null,
  clients: [],
  server: null,
  job: null,
  jobMissing: false,
  filter: "all",
  showStats: false,
  allDetails: false,
  problem: "",
  loaded: false,
};
const nodes = new WeakMap();
const images = new Map();
let timer = null;
let sequence = 0;
let noticeTimer = null;

class Halt extends Error {}
class Problem extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function readToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}

function saveToken(token) {
  state.token = token;
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch { /* Storage blocked: the token lives in memory for this page only. */ }
}

// ---------- Network ----------

async function api(path, { method = "GET", body, blob = false } = {}) {
  const headers = { Accept: blob ? "image/png" : "application/json" };
  if (state.token) headers.Authorization = "Bearer " + state.token;
  const options = { method, headers, redirect: "manual", cache: "no-store" };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body || {});
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Problem("Could not reach the server.", 0);
  }
  if (state.gate) throw new Halt(state.gate);
  if (response.type === "opaqueredirect") throw lock("expired");
  if (response.status === 401) throw lock(state.token ? "bad-token" : "token");
  if (response.status === 403) throw lock("forbidden");
  if (!response.ok) {
    let data = null;
    try { data = await response.json(); } catch { /* not JSON */ }
    const detail = data && typeof data.error === "string" ? data.error : "";
    throw new Problem(detail ? sentence(detail) : "The server refused this (HTTP " + response.status + ").", response.status);
  }
  return blob ? response.blob() : response.json();
}

function sentence(text) {
  return text.charAt(0).toUpperCase() + text.slice(1) + (/[.!?]$/.test(text) ? "" : ".");
}

async function refresh() {
  if (state.gate) return;
  const mine = ++sequence;
  const jobsPath = "/api/jobs?limit=" + JOB_LIMIT + (state.filter === "all" ? "" : "&printer=" + encodeURIComponent(state.filter));
  const fleet = state.view === "connections";
  const requests = [api("/api/printers"), api(jobsPath), api("/api/stats")];
  if (fleet) requests.push(api("/api/clients"), api("/api/server"));
  if (state.view === "job") {
    requests.push(api("/api/jobs/" + encodeURIComponent(state.jobId)).catch((error) => {
      if (error instanceof Problem && error.status === 404) return null;
      throw error;
    }));
  }
  let results;
  try {
    results = await Promise.all(requests);
  } catch (error) {
    if (error instanceof Halt || mine !== sequence) return;
    state.problem = error.status ? "Server error (HTTP " + error.status + "), retrying" : "Server unreachable, retrying";
    if (state.loaded) renderHealth();
    else showGate("Can't reach the server", "The print server did not answer. This page tries again every few seconds.", false);
    return;
  }
  if (mine !== sequence || state.gate) return;
  const [printers, jobs, stats] = results;
  state.printers = printers.printers;
  state.jobs = jobs.jobs;
  state.stats = stats;
  if (fleet) {
    state.clients = results[3].clients;
    state.server = results[4];
  }
  if (state.view === "job") {
    state.job = results[3];
    state.jobMissing = results[3] === null;
  }
  state.problem = "";
  state.loaded = true;
  render();
}

function schedule() {
  clearTimeout(timer);
  timer = null;
  if (!document.hidden && !state.gate) timer = setTimeout(tick, POLL_MS);
}

async function tick() {
  clearTimeout(timer);
  timer = null;
  if (document.hidden || state.gate) return;
  await refresh();
  schedule();
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    clearTimeout(timer);
    timer = null;
  } else {
    tick();
  }
});

// ---------- Sign-in gate ----------

const GATES = {
  token: ["Sign in", "Paste the admin token from the server config. Behind Cloudflare Access, an admin email needs no token."],
  "bad-token": ["Sign in", "The server did not accept that token. Check admin_token in the server config."],
  forbidden: ["Not an admin", "You are signed in, but your email is not in admin_emails in the server config."],
  expired: ["Signed out", "Your sign-in expired. Reload the page to sign in again."],
};

function lock(gate) {
  if (gate === "bad-token") saveToken("");
  state.gate = gate;
  clearTimeout(timer);
  timer = null;
  forget();
  const [title, text] = GATES[gate];
  showGate(title, text, gate === "token" || gate === "bad-token");
  if (!$("token-form").hidden) $("token").focus();
  return new Halt(gate);
}

function showGate(title, text, form) {
  $("loading").hidden = true;
  $("gate-title").textContent = title;
  $("gate-text").textContent = text;
  $("token-form").hidden = !form;
  $("gate").hidden = false;
  for (const id of ["view-rail", "view-job", "view-connections", "tabs", "tabbar"]) $(id).hidden = true;
  $("health").replaceChildren();
  document.title = title + " - Thermal";
}

function forget() {
  Object.assign(state, { printers: [], jobs: [], stats: null, clients: [], server: null, job: null, loaded: false });
  for (const id of ["track", "filters", "stats", "fleet-strip", "printer-grid", "client-list", "routes",
    "server-card", "job-events", "job-raw"]) {
    $(id).replaceChildren();
    nodes.delete($(id));
  }
  for (const id of ["rail-title", "rail-summary", "job-title", "job-kicker", "job-status", "job-caption"]) $(id).textContent = "";
  $("job-image").removeAttribute("src");
  for (const entry of images.values()) entry.then((url) => url && URL.revokeObjectURL(url));
  images.clear();
}

$("token-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const token = $("token").value.trim();
  if (!token) {
    $("gate-text").textContent = "Paste the token first.";
    return;
  }
  $("token").value = "";
  saveToken(token);
  state.gate = null;
  $("gate").hidden = true;
  tick();
});

// ---------- Helpers ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function dot(tone) {
  return el("span", "dot" + (tone ? " " + tone : ""));
}

function setDot(node, tone) {
  node.className = "dot" + (tone ? " " + tone : "");
}

// Reuses one node per key, so polling keeps scroll position, focus and open <details>.
function keyed(container, items, keyOf, create, update) {
  const old = nodes.get(container) || new Map();
  const next = new Map();
  for (const item of items) {
    const key = keyOf(item);
    next.set(key, old.get(key) || create(item));
  }
  for (const [key, node] of old) if (!next.has(key)) node.remove();
  let index = 0;
  for (const item of items) {
    const node = next.get(keyOf(item));
    update(node, item);
    if (container.children[index] !== node) container.insertBefore(node, container.children[index] || null);
    index++;
  }
  nodes.set(container, next);
}

function now() {
  return Date.now() / 1000;
}

function clock(seconds) {
  return TIME.format(new Date(seconds * 1000));
}

function dayKey(seconds) {
  return new Date(seconds * 1000).toDateString();
}

function when(seconds) {
  const date = new Date(seconds * 1000);
  if (date.toDateString() === new Date().toDateString()) return TIME.format(date);
  return DAY.format(date) + ", " + TIME.format(date);
}

function span(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return s + " s";
  const m = Math.floor(s / 60);
  if (m < 60) return m + " min";
  const h = Math.floor(m / 60);
  if (h < 24) return h + "h" + (m % 60 ? " " + (m % 60) + "m" : "");
  const d = Math.floor(h / 24);
  return d + "d" + (h % 24 ? " " + (h % 24) + "h" : "");
}

function paper(mm) {
  return mm >= 1000 ? (mm / 1000).toFixed(1) + " m" : (mm / 10).toFixed(1) + " cm";
}

function kindLabel(kind) {
  return KIND[kind] || kind;
}

function jobName(job) {
  return job.title || kindLabel(job.kind);
}

function printer(id) {
  return state.printers.find((p) => p.id === id);
}

function printerName(id) {
  const found = printer(id);
  return found ? found.name : id;
}

function plural(count, word) {
  return count + " " + word + (count === 1 ? "" : "s");
}

function printerStatus(p) {
  if (p.current_job) return { tone: "busy", text: "Printing " + p.current_job.frames_sent + "/" + p.current_job.frames };
  if (p.online && p.paused_until) return { tone: "warn", text: "Paused until " + clock(p.paused_until) };
  if (p.online) return { tone: "ok", text: p.queued ? "Online" : "Idle" };
  if (p.last_seen) return { tone: "down", text: "Offline " + span(now() - p.last_seen) };
  return { tone: "down", text: "Never connected" };
}

function notice(text, bad) {
  const box = $("notice");
  box.textContent = text;
  box.classList.toggle("bad", !!bad);
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { box.textContent = ""; }, NOTICE_MS);
}

// ---------- Images ----------

function imageUrl(id) {
  if (!images.has(id)) {
    const entry = api("/api/jobs/" + encodeURIComponent(id) + "/image", { blob: true })
      .then((blob) => URL.createObjectURL(blob))
      .catch((error) => {
        if (!(error instanceof Problem && error.status === 404)) images.delete(id);
        return null;
      });
    images.set(id, entry);
  }
  return images.get(id);
}

function showImage(img, id) {
  if (img.dataset.job === id) return;
  img.dataset.job = id;
  img.removeAttribute("src");
  img.closest(".paper").classList.remove("missing");
  imageUrl(id).then((url) => {
    if (img.dataset.job !== id) return;
    if (url) {
      img.src = url;
    } else {
      delete img.dataset.job;
      if (images.has(id)) img.closest(".paper").classList.add("missing");
    }
  });
}

function dropImages(keep) {
  for (const [id, entry] of images) {
    if (keep.has(id)) continue;
    images.delete(id);
    entry.then((url) => url && URL.revokeObjectURL(url));
  }
}

const seen = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    seen.unobserve(entry.target);
    entry.target.dataset.seen = "1";
    showImage(entry.target, entry.target.dataset.want);
  }
}, { rootMargin: "400px" });

function lazyImage(img, id) {
  img.dataset.want = id;
  if (img.dataset.seen) showImage(img, id);
  else seen.observe(img);
}

// ---------- Render ----------

function render() {
  $("loading").hidden = true;
  $("gate").hidden = true;
  $("tabs").hidden = false;
  $("tabbar").hidden = false;
  $("view-rail").hidden = state.view !== "rail";
  $("view-job").hidden = state.view !== "job";
  $("view-connections").hidden = state.view !== "connections";
  const section = state.view === "job" ? "rail" : state.view;
  for (const link of document.querySelectorAll("[data-view]")) {
    if (link.dataset.view === section) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  renderHealth();
  if (state.view === "rail") renderRail();
  if (state.view === "job") renderJob();
  if (state.view === "connections") renderFleet();
  const keep = new Set(state.jobs.map((job) => job.id));
  if (state.jobId) keep.add(state.jobId);
  if (state.job) keep.add(state.job.id);
  dropImages(keep);
}

function renderHealth() {
  $("clock").textContent = TIME.format(new Date());
  const health = $("health");
  if (state.gate || !state.loaded) return;
  if (state.problem) {
    health.replaceChildren(dot("down"), el("span", "", state.problem));
    return;
  }
  const down = state.printers.filter((p) => !p.online).length;
  if (!state.printers.length) health.replaceChildren(dot(), el("span", "", "No printers configured"));
  else if (down) health.replaceChildren(dot("down"), el("span", "", plural(down, "printer") + " offline"));
  else health.replaceChildren(dot("ok"), el("span", "", "All printers online"));
}

function headline() {
  const busy = state.printers.filter((p) => p.current_job);
  if (busy.length === 1) {
    const job = state.jobs.find((j) => j.id === busy[0].current_job.id);
    return busy[0].name + " is printing " + (job ? jobName(job) : "a job");
  }
  if (busy.length > 1) return busy.length + " printers are printing";
  const queued = state.stats ? state.stats.queued : 0;
  if (queued) return plural(queued, "job") + " waiting";
  return "Nothing waiting to print";
}

function renderRail() {
  document.title = "Rail - Thermal";
  const stats = state.stats;
  $("rail-title").textContent = headline();
  const waiting = state.printers.filter((p) => !p.online).reduce((sum, p) => sum + p.queued, 0);
  let summary = stats.printed_today + " printed today · " + stats.queued + " queued";
  if (waiting) summary += " · " + waiting + " waiting for an offline printer";
  $("rail-summary").textContent = summary;

  const filters = [{ id: "all", name: "All" }, ...state.printers];
  keyed($("filters"), filters, (f) => f.id, (f) => {
    const button = el("button");
    button.type = "button";
    button.append(el("span", "dot"), el("span"));
    button.addEventListener("click", () => {
      state.filter = f.id;
      $("track").replaceChildren();
      nodes.delete($("track"));
      tick();
    });
    return button;
  }, (button, f) => {
    button.setAttribute("aria-pressed", String(state.filter === f.id));
    const [mark, label] = button.children;
    mark.hidden = f.id === "all";
    if (f.id !== "all") setDot(mark, printerStatus(f).tone);
    label.textContent = f.name;
  });

  $("stats").hidden = !state.showStats;
  if (state.showStats) {
    const tiles = [
      ["Printed today", String(stats.printed_today)],
      ["In queue", String(stats.queued)],
      ["Median job time", stats.median_job_seconds === null ? "-" : stats.median_job_seconds.toFixed(1) + " s"],
      ["Failed, last 24 h", String(stats.failed_24h)],
      ["Paper today", paper(stats.paper_today_mm)],
    ];
    keyed($("stats"), tiles, (t) => t[0], () => {
      const tile = el("div");
      tile.append(el("dt"), el("dd"));
      return tile;
    }, (tile, [label, value]) => {
      tile.children[0].textContent = label;
      tile.children[1].textContent = value;
    });
  }

  const entries = railEntries();
  keyed($("track"), entries, (e) => e.key, createEntry, updateEntry);
  const empty = !state.jobs.length;
  $("rail").hidden = empty;
  $("rail-empty").hidden = !empty;
  $("rail-empty").textContent = state.filter === "all"
    ? "No jobs yet. Send one with printctl or the web form, and it appears here."
    : "No jobs for this printer yet.";

  keyed($("fleet-strip"), state.printers, (p) => p.id, () => {
    const item = el("li");
    const link = el("a");
    link.href = "#/connections";
    link.append(el("span", "dot"), el("span"), el("span", "muted"));
    item.append(link);
    return item;
  }, (item, p) => {
    const [mark, name, status] = item.firstChild.children;
    const info = printerStatus(p);
    setDot(mark, info.tone);
    name.textContent = p.name;
    status.textContent = info.text;
  });
}

function railEntries() {
  const queued = state.jobs.filter((job) => job.status === "queued");
  const rest = state.jobs.filter((job) => job.status !== "queued");
  const next = new Set();
  const firstSeen = new Set();
  for (let i = queued.length - 1; i >= 0; i--) {
    if (!firstSeen.has(queued[i].printer)) {
      firstSeen.add(queued[i].printer);
      next.add(queued[i].id);
    }
  }
  const entries = queued.map((job) => ({ key: job.id, job, next: next.has(job.id) }));
  if (state.jobs.length) entries.push({ key: "now", now: true });
  // The wide rail marks where a day starts, on its left, as in the design.
  // The phone list puts each day's label on top of it, except today's, which "now" already heads.
  const today = new Date().toDateString();
  let day = null;
  const label = (key) => {
    const text = DAY.format(new Date(key));
    entries.push({ key: "day " + key, label: key === today ? "Today · " + text : text });
  };
  for (const job of rest) {
    const key = dayKey(job.created_at);
    if (key !== day) {
      if (wide.matches && day !== null) label(day);
      if (!wide.matches && key !== today) label(key);
    }
    day = key;
    entries.push({ key: job.id, job });
  }
  if (wide.matches && day !== null) label(day);
  return entries;
}

function createEntry(entry) {
  if (!entry.job) {
    const marker = el("li", "marker" + (entry.now ? " now" : ""));
    marker.append(el("span"));
    return marker;
  }
  const item = el("li", "ticket");
  const link = el("a");
  const wrap = el("div", "paper-wrap thumb");
  const sheet = el("div", "paper");
  const cut = el("div", "feed");
  const img = el("img");
  img.alt = "";
  img.decoding = "async";
  cut.append(img);
  sheet.append(cut);
  const headLine = el("div", "head-line");
  const unprinted = el("div", "unprinted");
  wrap.append(sheet, headLine, unprinted);
  const meta = el("div", "meta");
  const whenRow = el("div", "when");
  whenRow.append(el("span", "time"), el("span", "printer"));
  const progress = el("div", "progress");
  const bar = el("div", "bar");
  bar.append(el("span"));
  progress.append(bar, el("small"));
  meta.append(whenRow, el("div", "title"), el("div", "note"), progress);
  link.append(wrap, meta);
  item.append(link);
  return item;
}

function updateEntry(node, entry) {
  if (!entry.job) {
    node.firstChild.textContent = entry.now ? "now " + TIME.format(new Date()) : entry.label;
    return;
  }
  const job = entry.job;
  const p = printer(job.printer);
  const link = node.firstChild;
  link.href = "#/job/" + encodeURIComponent(job.id);
  const [wrap, meta] = link.children;
  const [sheet, headLine, unprinted] = wrap.children;
  const cut = sheet.firstChild;
  const img = cut.firstChild;
  img.width = job.width;
  img.height = job.height;
  lazyImage(img, job.id);

  const current = p && p.current_job && p.current_job.id === job.id ? p.current_job : null;
  const printing = job.status === "sending";
  const fraction = printing && current ? current.frames_sent / Math.max(1, current.frames) : 0;
  if (printing) {
    cut.style.aspectRatio = job.width + " / " + Math.max(1, Math.round(job.height * fraction));
    unprinted.style.aspectRatio = job.width + " / " + Math.max(1, Math.round(job.height * (1 - fraction)));
  } else {
    cut.style.removeProperty("aspect-ratio");
  }
  headLine.hidden = !printing;
  unprinted.hidden = !printing || fraction >= 1;

  const note = noteFor(job, p, entry, current);
  node.className = "ticket " + job.status + (note.stalled ? " stalled" : "") + (FINAL_BAD.has(job.status) ? " final-bad" : "");
  meta.style.setProperty("--pin", "var(--" + (note.pin || "muted") + ")");
  const [whenRow, title, noteLine, progress] = meta.children;
  const time = job.status === "printed" && job.printed_at ? clock(job.printed_at)
    : job.status === "queued" ? (entry.next ? "next" : "queued") : clock(job.created_at);
  whenRow.children[0].textContent = time;
  whenRow.children[1].textContent = p ? p.name : job.printer;
  title.textContent = jobName(job);
  noteLine.textContent = note.text;
  noteLine.className = "note" + (note.tone ? " tone-" + note.tone : "");
  progress.hidden = !printing;
  if (printing) {
    progress.firstChild.firstChild.style.width = Math.round(fraction * 100) + "%";
    progress.lastChild.textContent = current
      ? current.frames_sent + " of " + current.frames + " chunks sent"
      : "starting";
  }
}

function noteFor(job, p, entry, current) {
  switch (job.status) {
    case "queued":
      if (p && !p.online) return { text: "waiting, printer offline", tone: "warn", stalled: true, pin: "faint" };
      if (p && p.paused_until) return { text: "paused after an error until " + clock(p.paused_until), tone: "warn", stalled: true, pin: "faint" };
      return { text: entry.next ? "up next" : "in the queue", pin: "faint" };
    case "sending":
      return { text: current && current.frames_sent >= current.frames ? "waiting for the printer to confirm" : "printing", tone: "busy", pin: "busy" };
    case "printed":
      if (job.attempts > 1) return { text: "printed on attempt " + job.attempts, tone: "warn" };
      return { text: "" };
    case "failed":
      return { text: "failed after " + plural(job.attempts, "attempt"), tone: "down", pin: "down" };
    case "expired":
      return { text: "expired before it printed", tone: "warn" };
    case "cancelled":
      return { text: "cancelled" };
  }
  return { text: job.status };
}

function renderJob() {
  if (state.jobMissing) {
    document.title = "Job not found - Thermal";
    $("job-title").textContent = "This job does not exist";
    $("job-kicker").textContent = "";
    $("job-status").textContent = "Check the link, or go back to the rail.";
    $("job-actions").hidden = true;
    $("job-paper").hidden = true;
    $("job-events").replaceChildren();
    $("job-raw").replaceChildren();
    $("job-caption").textContent = "";
    pager(null);
    return;
  }
  const job = state.job;
  $("job-actions").hidden = !job;
  $("job-paper").hidden = !job;
  if (!job) {
    for (const id of ["job-kicker", "job-status", "job-caption"]) $(id).textContent = "";
    $("job-title").textContent = "Loading…";
    $("job-events").replaceChildren();
    nodes.delete($("job-events"));
    return;
  }
  document.title = jobName(job) + " - Thermal";
  const p = printer(job.printer);
  const name = p ? p.name : job.printer;
  $("job-kicker").textContent = kindLabel(job.kind) + " from " + job.source;
  $("job-title").textContent = jobName(job);

  const img = $("job-image");
  img.width = job.width;
  img.height = job.height;
  img.alt = "The printed image of " + jobName(job);
  showImage(img, job.id);
  $("job-caption").textContent = job.width + " × " + job.height + " dots, 1-bit, as sent to the printer";

  const line = [];
  if (job.status === "printed") {
    line.push(dot("ok"), el("strong", "", "Printed on " + name));
    line.push(el("span", "", SECONDS.format(new Date(job.printed_at * 1000)) + " · " + (job.printed_at - job.created_at).toFixed(1) + " s"));
  } else if (job.status === "sending") {
    const current = p && p.current_job && p.current_job.id === job.id ? p.current_job : null;
    line.push(dot("busy"), el("strong", "", "Printing on " + name));
    if (current) line.push(el("span", "", current.frames_sent + " of " + current.frames + " chunks sent"));
  } else if (job.status === "queued") {
    const info = p ? printerStatus(p) : { tone: "", text: "" };
    line.push(dot(info.tone === "down" ? "warn" : ""), el("strong", "", "Queued for " + name));
    if (p && !p.online) line.push(el("span", "tone-warn", "printer offline"));
    else if (p && p.paused_until) line.push(el("span", "tone-warn", "paused after an error until " + clock(p.paused_until)));
    line.push(el("span", "", "expires " + when(job.expires_at)));
  } else {
    const tone = job.status === "failed" ? "down" : job.status === "expired" ? "warn" : "";
    line.push(dot(tone), el("strong", "", sentence(job.status).slice(0, -1) + " on " + name));
  }
  $("job-status").replaceChildren(...line);

  const live = job.status === "queued" || job.status === "sending";
  $("act-reprint").disabled = live;
  $("act-print-on").disabled = live || state.printers.length < 2;
  $("act-cancel").hidden = !live;
  $("act-reprint").title = live ? "A job can be reprinted once it is no longer queued or printing" : "";

  const events = job.events.map((event, index) => ({ ...event, index }));
  keyed($("job-events"), events, (e) => e.index, () => {
    const item = el("li");
    const rail = el("span", "rail-dot");
    rail.append(dot());
    item.append(el("time"), rail, el("span", "what"));
    return item;
  }, (item, event) => {
    item.children[0].textContent = SECONDS.format(new Date(event.at * 1000));
    setDot(item.children[1].firstChild, EVENT_TONE[event.event] || "");
    const what = item.children[2];
    const parts = [el("strong", "", EVENT[event.event] || event.event)];
    const detail = eventDetail(job, event);
    if (event.event === "reprinted" && event.detail) {
      const target = el("a", "", "job " + event.detail);
      target.href = "#/job/" + encodeURIComponent(event.detail);
      parts.push(el("span", "", " as "), target);
    } else if (detail) {
      parts.push(el("span", "", " " + detail));
    }
    what.replaceChildren(...parts);
  });

  const raw = [
    ["Job", job.id],
    ["Kind", job.kind],
    ["Status", job.status + ", " + plural(job.attempts, "attempt")],
    ["From", job.source + " via " + job.ingress],
    ["Printer", job.printer],
    ["Created", when(job.created_at)],
    ["Expires", when(job.expires_at)],
    ["Image", job.width + " × " + job.height + " dots, " + paper(job.paper_mm)],
    ["Render", job.render_ms + " ms"],
    ["ESC/POS", (job.size_bytes / 1024).toFixed(1) + " KB in " + plural(job.frames, "chunk")],
  ];
  if (p) raw.push(["Printer client", [p.address, p.client_version].filter(Boolean).join(", ") || "-"]);
  keyed($("job-raw"), raw, (r) => r[0], () => {
    const holder = el("div");
    holder.append(el("dt"), el("dd"));
    return holder;
  }, (holder, [key, value]) => {
    holder.children[0].textContent = key;
    holder.children[1].textContent = value;
  });

  pager(job);
}

function eventDetail(job, event) {
  switch (event.event) {
    case "received": return event.detail ? "from " + event.detail : "";
    case "sent": return "all " + plural(job.frames, "chunk");
    case "printed": return "paper " + paper(job.paper_mm);
  }
  return event.detail || "";
}

function pager(job) {
  const list = railEntries().filter((e) => e.job).map((e) => e.job);
  const index = job ? list.findIndex((j) => j.id === job.id) : -1;
  const place = (id, neighbour, label) => {
    const link = $(id);
    link.hidden = !neighbour;
    if (!neighbour) return;
    link.href = "#/job/" + encodeURIComponent(neighbour.id);
    const at = neighbour.status === "queued" ? "queued" : clock(neighbour.printed_at || neighbour.created_at);
    link.textContent = label === "older" ? "← " + at : at + " →";
    link.setAttribute("aria-label", (label === "older" ? "Older job, " : "Newer job, ") + jobName(neighbour));
  };
  place("job-older", index >= 0 ? list[index + 1] : null, "older");
  place("job-newer", index > 0 ? list[index - 1] : null, "newer");
}

function renderFleet() {
  document.title = "Connections - Thermal";
  const server = state.server;
  if (!server) return;
  const card = $("server-card");
  const name = el("div", "name");
  name.append(dot("ok"), el("span", "", "Server"), el("span", "muted", "version " + server.version));
  const renders = server.renders_in_progress;
  card.replaceChildren(name, el("div", "muted small",
    "up " + span(server.uptime_seconds) + " · " + (renders ? "rendering " + plural(renders, "job") : "nothing rendering")));

  const groups = new Map();
  for (const p of state.printers) {
    const key = p.route || "none";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(p);
  }
  keyed($("routes"), [...groups], ([key]) => key, () => el("li"), (item, [key, list]) => {
    const parts = [el("strong", "", ROUTE[key] || (key === "none" ? "Not connected yet" : key))];
    parts.push(el("span", "muted", list.map((p) => p.name).join(", ")));
    const latencies = list.filter((p) => p.online && p.latency_ms !== null).map((p) => p.latency_ms);
    if (latencies.length) {
      const low = Math.round(Math.min(...latencies));
      const high = Math.round(Math.max(...latencies));
      parts.push(el("span", "muted", (low === high ? low : low + "-" + high) + " ms"));
    }
    const down = list.filter((p) => !p.online).length;
    if (down && key !== "none") parts.push(el("span", "tone-down", down + " down"));
    item.replaceChildren(...parts);
  });

  keyed($("printer-grid"), state.printers, (p) => p.id, createPrinterCard, updatePrinterCard);
  $("details-toggle").textContent = state.allDetails ? "Hide all details" : "Show all details";
  $("details-toggle").setAttribute("aria-expanded", String(state.allDetails));

  const clients = state.clients.length ? state.clients : [null];
  keyed($("client-list"), clients, (c) => (c ? c.kind + " " + c.id : "empty"), (c) => {
    const item = el("li");
    if (!c) {
      item.className = "empty-row";
      item.textContent = "No clients in the config, and no web sender has printed yet.";
      return item;
    }
    const who = el("div", "who");
    const text = el("div");
    text.append(el("div"), el("div", "muted small"));
    who.append(dot(), text);
    const last = el("div", "last");
    last.append(el("span"), el("span", "count"));
    item.append(who, last);
    return item;
  }, (item, c) => {
    if (!c) return;
    const [who, last] = item.children;
    setDot(who.firstChild, c.jobs_today ? "ok" : "");
    who.lastChild.children[0].textContent = c.id;
    who.lastChild.children[1].textContent = c.kind === "web" ? "Web sender" : "API client";
    const recent = c.last_job;
    if (recent) {
      const link = el("a", "", jobName(recent) + " · " + when(recent.created_at));
      link.href = "#/job/" + encodeURIComponent(recent.id);
      last.firstChild.replaceChildren(link);
    } else {
      last.firstChild.replaceChildren(el("span", "muted", "no jobs yet"));
    }
    const count = last.lastChild;
    count.replaceChildren(el("span", "mono", String(c.jobs_today)), el("span", "muted small", " today"));
  });
}

function createPrinterCard(p) {
  const card = el("article", "printer-card");
  const head = el("div", "head");
  const title = el("div");
  title.append(el("div", "name"), el("div", "muted small"));
  const status = el("span", "state");
  status.append(dot(), el("span"));
  head.append(title, status);
  const chart = el("div");
  const hours = el("div", "hours");
  hours.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 24; i++) hours.append(el("span"));
  const scale = el("div", "hours-scale");
  scale.append(el("span", "", "24h ago"), el("span"), el("span", "", "now"));
  chart.append(hours, scale);
  const facts = el("div", "facts");
  facts.append(el("span"), el("span"));
  const row = el("div", "row");
  const move = el("button", "button", "Move jobs…");
  move.type = "button";
  move.addEventListener("click", () => moveJobs(p.id));
  const clear = el("button", "button danger", "Clear queue");
  clear.type = "button";
  clear.addEventListener("click", () => clearQueue(p.id));
  row.append(move, clear);
  const details = el("details");
  details.open = state.allDetails;
  details.append(el("summary", "", "Details"), el("dl", "pairs"));
  card.append(head, chart, facts, row, details);
  return card;
}

function updatePrinterCard(card, p) {
  const [head, chart, facts, row, details] = card.children;
  head.firstChild.children[0].textContent = p.name;
  head.firstChild.children[1].textContent = p.place;
  const info = printerStatus(p);
  setDot(head.lastChild.firstChild, info.tone);
  head.lastChild.lastChild.textContent = info.text;

  const counts = (state.stats && state.stats.hourly[p.id]) || new Array(24).fill(0);
  [...chart.firstChild.children].forEach((bar, i) => {
    const n = counts[i] || 0;
    bar.style.height = (n ? Math.min(28, 6 + n * 5) : 2) + "px";
    bar.className = n === 0 ? "zero" : i === 23 ? "last" : "";
  });
  chart.lastChild.children[1].textContent = p.printed_today + " today";

  const route = p.route ? (ROUTE[p.route] || p.route) + (p.online && p.latency_ms !== null ? " · " + Math.round(p.latency_ms) + " ms" : "") : "never connected";
  facts.children[0].textContent = route;
  const lastBit = facts.children[1];
  if (p.queued && !p.online) {
    lastBit.textContent = plural(p.queued, "job") + " waiting";
    lastBit.className = "tone-warn";
  } else {
    lastBit.className = "";
    lastBit.textContent = p.online && p.connected_since ? "connected since " + when(p.connected_since)
      : p.last_seen ? "last seen " + when(p.last_seen) : "";
  }

  row.hidden = !p.queued;
  row.children[0].textContent = "Move " + plural(p.queued, "job") + "…";
  row.children[0].hidden = state.printers.length < 2;

  const pairs = [
    ["Printer id", p.id],
    ["Status", info.text],
    ["Route", p.route ? ROUTE[p.route] || p.route : "-"],
    ["Latency", p.latency_ms === null ? "-" : Math.round(p.latency_ms) + " ms"],
    ["Address", p.address || "-"],
    ["Client", p.client_version || "-"],
    ["Connected", p.connected_since ? when(p.connected_since) : "-"],
    ["Last seen", p.last_seen ? when(p.last_seen) : "-"],
    ["Web form", p.public ? "offered to senders" : "admin and clients only"],
  ];
  if (p.paused_until) pairs.splice(2, 0, ["Paused", "after an error, until " + clock(p.paused_until)]);
  keyed(details.lastChild, pairs, (pair) => pair[0], () => {
    const holder = el("div");
    holder.append(el("dt"), el("dd"));
    return holder;
  }, (holder, [key, value]) => {
    holder.children[0].textContent = key;
    holder.children[1].textContent = value;
  });
}

// ---------- Actions ----------

function ask({ title, text, ok, choices }) {
  const dialog = $("dialog");
  $("dialog-title").textContent = title;
  $("dialog-text").textContent = text || "";
  $("dialog-ok").textContent = ok;
  const box = $("dialog-choices");
  box.replaceChildren(box.firstElementChild);
  box.hidden = !choices;
  (choices || []).forEach((choice, index) => {
    const label = el("label");
    const input = el("input");
    input.type = "radio";
    input.name = "dialog-choice";
    input.value = choice.value;
    input.checked = index === 0;
    const words = el("span");
    words.append(el("span", "", choice.label));
    if (choice.hint) words.append(el("br"), el("small", "", choice.hint));
    label.append(input, words);
    box.append(label);
  });
  return new Promise((resolve) => {
    let answer = null;
    const done = () => {
      dialog.removeEventListener("close", done);
      resolve(answer);
    };
    $("dialog-ok").onclick = () => {
      const picked = box.querySelector("input:checked");
      answer = choices ? (picked ? picked.value : null) : true;
      dialog.close();
    };
    $("dialog-back").onclick = () => dialog.close();
    dialog.addEventListener("close", done);
    dialog.showModal();
  });
}

function otherPrinters(id) {
  return state.printers.filter((p) => p.id !== id).map((p) => ({
    value: p.id, label: p.name, hint: [p.place, printerStatus(p).text].filter(Boolean).join(" · "),
  }));
}

async function act(work) {
  try {
    const message = await work();
    if (message) notice(message);
  } catch (error) {
    if (error instanceof Halt) return;
    notice(error.message, true);
  }
  tick();
}

function reprint(target) {
  const job = state.job;
  return act(async () => {
    const copy = await api("/api/jobs/" + encodeURIComponent(job.id) + "/reprint", {
      method: "POST", body: target ? { printer: target } : {},
    });
    return "Reprint queued on " + printerName(copy.printer);
  });
}

$("act-reprint").addEventListener("click", () => reprint(null));

$("act-print-on").addEventListener("click", async () => {
  const job = state.job;
  const target = await ask({
    title: "Print on another printer", text: jobName(job) + " is printed again on the printer you pick.",
    ok: "Print", choices: otherPrinters(job.printer),
  });
  if (target) reprint(target);
});

$("act-cancel").addEventListener("click", async () => {
  const job = state.job;
  const sure = await ask({
    title: "Cancel this job?", text: jobName(job) + " will not print on " + printerName(job.printer) + ".", ok: "Cancel job",
  });
  if (!sure) return;
  act(async () => {
    await api("/api/jobs/" + encodeURIComponent(job.id) + "/cancel", { method: "POST" });
    return "Job cancelled";
  });
});

$("act-download").addEventListener("click", async () => {
  const job = state.job;
  const url = await imageUrl(job.id);
  if (!url) {
    notice("The image is gone: images are kept for 30 days.", true);
    return;
  }
  const link = el("a");
  link.href = url;
  link.download = "job-" + job.id + ".png";
  document.body.append(link);
  link.click();
  link.remove();
});

async function clearQueue(id) {
  const p = printer(id);
  const sure = await ask({
    title: "Clear the queue of " + p.name + "?",
    text: plural(p.queued, "queued job") + (p.current_job ? " and the job printing now" : "")
      + " will be cancelled and will not print.",
    ok: "Clear queue",
  });
  if (!sure) return;
  act(async () => {
    const result = await api("/api/printers/" + encodeURIComponent(id) + "/clear", { method: "POST" });
    return plural(result.cancelled, "job") + " cancelled";
  });
}

async function moveJobs(id) {
  const p = printer(id);
  const target = await ask({
    title: "Move the queue of " + p.name,
    text: plural(p.queued, "queued job") + " will print on the printer you pick instead.",
    ok: "Move jobs", choices: otherPrinters(id),
  });
  if (!target) return;
  act(async () => {
    const result = await api("/api/printers/" + encodeURIComponent(id) + "/move", { method: "POST", body: { to: target } });
    return plural(result.moved, "job") + " moved to " + printerName(target);
  });
}

$("stats-toggle").addEventListener("click", () => {
  state.showStats = !state.showStats;
  $("stats-toggle").textContent = state.showStats ? "Hide stats" : "Show stats";
  $("stats-toggle").setAttribute("aria-expanded", String(state.showStats));
  if (state.loaded) renderRail();
});

$("details-toggle").addEventListener("click", () => {
  state.allDetails = !state.allDetails;
  for (const details of $("printer-grid").querySelectorAll("details")) details.open = state.allDetails;
  if (state.loaded) renderFleet();
});

// ---------- Routing ----------

function route() {
  const hash = location.hash || "#/";
  const match = hash.match(/^#\/job\/([^/]+)$/);
  const before = state.view + " " + state.jobId;
  let jobId = null;
  try {
    jobId = match ? decodeURIComponent(match[1]) : null;
  } catch {
    jobId = null;
  }
  if (jobId) {
    state.view = "job";
    state.jobId = jobId;
  } else if (["#/connections", "#/printers", "#/clients"].includes(hash)) {
    state.view = "connections";
    state.jobId = null;
  } else {
    state.view = "rail";
    state.jobId = null;
  }
  if (before !== state.view + " " + state.jobId) {
    state.job = null;
    state.jobMissing = false;
    window.scrollTo(0, 0);
    if (state.loaded) {
      render();
      $("main").focus({ preventScroll: true });
    }
  }
  tick();
}

window.addEventListener("hashchange", route);
$("rail").addEventListener("focusin", (event) => event.target.scrollIntoView({ inline: "nearest", block: "nearest" }));
wide.addEventListener("change", () => { if (state.loaded && !state.gate) render(); });
setInterval(() => { if (!document.hidden) renderHealth(); }, 10000);
route();
