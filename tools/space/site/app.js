"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const SVGNS = "http://www.w3.org/2000/svg";

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") {
      for (const [p, x] of Object.entries(v)) p.startsWith("--") ? el.style.setProperty(p, x) : (el.style[p] = x);
    } else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function sv(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) el.setAttribute(k, v);
  for (const kid of kids) if (kid) el.append(kid);
  return el;
}

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

const fmt = (t) => {
  if (t == null || !isFinite(t)) return "–";
  t = Math.max(0, t);
  return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
};
const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);
const mins = (s) => (s == null ? "–" : s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${Math.round(s)} s`);
const ICON_PLAY = '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 2.5v11l9-5.5z"/></svg>';
const ICON_PAUSE = '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z"/></svg>';
const ICON_LOCK = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="7" width="10" height="7.5" rx="1.8"/><path d="M5.4 7V5.1a2.6 2.6 0 0 1 5.2 0V7"/></svg>';
const SPEEDS = [1, 2, 4, 8, 16];

let CAT = null;
let PLAYER = null;
const byId = (list) => Object.fromEntries(list.map((x) => [x.id, x]));
let TASKS = {}, CONDS = {}, MODELS = {}, OSES = {}, DRIVERS = {}, CRIT = [];
// The board's state for this visit: the grid's driver, the comparison's OS and model, and where the board was left.
const VIEW = { board: false, ready: false, driver: null, compare: null, y: null };
const settled = (el) => Promise.all([...el.querySelectorAll(".fig img")].map((img) =>
  img.complete ? null : new Promise((r) => { img.addEventListener("load", r, { once: true }); img.addEventListener("error", r, { once: true }); })));

async function boot() {
  try {
    CAT = await (await fetch("data/catalog.json", { cache: "no-cache" })).json();
  } catch (e) {
    $("#app").replaceChildren(h("div", { class: "wrap loading" }, "Could not load data/catalog.json."));
    return;
  }
  TASKS = byId(CAT.tasks); CONDS = byId(CAT.conditions); MODELS = byId(CAT.models); OSES = byId(CAT.oses);
  DRIVERS = byId(CAT.drivers);
  CRIT = CAT.criteria;
  VIEW.driver = CAT.driver;
  const L = CAT.links || {};
  $("#links").replaceChildren(
    L.dataset && h("a", { href: L.dataset, target: "_blank", rel: "noopener", class: "keep" }, "Dataset"),
    L.port && h("a", { href: L.port, target: "_blank", rel: "noopener" }, "Bench port"),
    L.trycua && h("a", { href: L.trycua, target: "_blank", rel: "noopener" }, "trycua/cua"),
    L.agentenv && h("a", { href: L.agentenv, target: "_blank", rel: "noopener" }, "AgentEnv"),
  );
  $("#foot").replaceChildren(
    h("p", {}, "The tasks, their apps, prompts and evaluators are trycua's ",
      h("a", { href: L.trycua, target: "_blank", rel: "noopener" }, "Cua Driver Bench"),
      " (© 2026 Cua AI, Inc., FSL-1.1-MIT), run here through the bench port ",
      h("a", { href: L.port, target: "_blank", rel: "noopener" }, "earakely-scale/agentenv-cua-driver-bench"),
      " on ", h("a", { href: L.agentenv, target: "_blank", rel: "noopener" }, "AgentEnv"),
      " (agentenv-framework on PyPI). These are not trycua's official results."),
    h("p", {}, "Recordings, trajectories, sentinel logs and grades: Apache-2.0. Generated ", CAT.generated.replace("T", " ").replace("Z", " UTC"), "."),
  );
  window.addEventListener("hashchange", route);
  route();
}

const enc = encodeURIComponent;
function hashOf(t) {
  const lead = t.driver === CAT.driver ? "" : enc(t.driver) + "/";
  return "#/" + lead + [t.os, t.task, t.condition, t.model].map(enc).join("/") + (t.of > 1 ? "/" + enc(t.key) : "");
}

const sameCell = (a, b) => a.driver === b.driver && a.os === b.os && a.task === b.task && a.condition === b.condition && a.model === b.model;

function best(sel) {
  const keys = ["os", "task", "condition", "model", "driver"];
  const pool = CAT.trials.slice().sort((a, b) => (MODELS[b.model]?.board ? 1 : 0) - (MODELS[a.model]?.board ? 1 : 0));
  if (sel.key) {
    const hit = pool.find((t) => sameCell(t, sel) && t.key === sel.key) || pool.find((t) => t.uid === sel.key);
    if (hit) return hit;
  }
  for (let n = keys.length; n >= 0; n--) {
    const want = keys.slice(0, n).filter((k) => sel[k]);
    const hits = pool.filter((t) => want.every((k) => t[k] === sel[k]));
    if (hits.length) return sel.run != null ? (hits.find((t) => t.run_index === sel.run) || hits[0]) : hits[0];
  }
  return pool[0];
}

function route() {
  if (PLAYER) { PLAYER.destroy(); PLAYER = null; }
  const raw = location.hash;
  const parts = raw.startsWith("#/") ? raw.slice(2).split("/").filter(Boolean).map(decodeURIComponent) : [];
  if (!parts.length || parts[0] === "drivers") {
    const [section, ...args] = parts.length ? parts : [raw.slice(1)];
    const back = VIEW.y != null && !VIEW.board;
    if (args.length) VIEW.compare = { os: args[0], model: args[1] };
    if (!VIEW.board || args.length) boardView();
    settled($("#app")).then(() => {
      const el = section && document.getElementById(section);
      const glide = VIEW.ready && !matchMedia("(prefers-reduced-motion: reduce)").matches ? "smooth" : "auto";
      if (back) window.scrollTo(0, VIEW.y);
      else if (el) el.scrollIntoView({ behavior: glide });
      else window.scrollTo({ top: 0, behavior: glide });
      VIEW.ready = true;
    });
    return;
  }
  const driver = DRIVERS[parts[0]] || (OSES[parts[1]] && !OSES[parts[0]]) ? parts.shift() : CAT.driver;
  const [os, task, condition, model, key] = parts;
  const t = best({ driver, os, task, condition, model, key, run: /^r\d+$/.test(key || "") ? +key.slice(1) : null });
  if (!t) { boardView(); return; }
  const canon = hashOf(t);
  if (canon !== location.hash) history.replaceState(null, "", canon);
  if (VIEW.board) VIEW.y = window.scrollY;
  trialView(t);
}

function resultsNote() {
  const n = new Set(CAT.trials.filter((t) => MODELS[t.model]?.board).map((t) => t.of));
  const runs = [...n].sort((a, b) => a - b);
  const r = runs.length === 1 ? `${runs[0]} run${runs[0] > 1 ? "s" : ""}` : `${runs[0]}–${runs[runs.length - 1]} runs`;
  return `${r} per task and condition. Every run is listed; click one to replay it.`;
}

function verdict(t) {
  return h("span", { class: `verdict ${t.passed ? "pass" : "fail"}` }, t.passed ? "✓ Pass" : "✗ Fail");
}

function badge(ok, label) {
  const cls = ok == null ? "na" : ok ? "ok" : "no";
  return h("span", { class: `badge ${cls}` }, h("i", {}, ok == null ? "–" : ok ? "✓" : "✗"), label);
}

function userBox(cls) {
  const [x, y, w, hh] = CAT.user_frame;
  const [W, H] = CAT.screen;
  return h("span", { class: cls, style: { left: `${(100 * x) / W}%`, top: `${(100 * y) / H}%`, width: `${(100 * w) / W}%`, height: `${(100 * hh) / H}%` } });
}

const HARNESSES = { "claude-code": "the claude-code CLI", "codex-cli": "OpenAI's Codex CLI" };

function harnessPhrase() {
  const by = {};
  CAT.models.filter((m) => m.board).forEach((m) => (by[m.harness] ||= []).push(m.name));
  return Object.entries(by).map(([harness, names]) => `${names.join(", ")} in ${HARNESSES[harness] || harness}`).join("; ");
}

function osPhrase() {
  const names = CAT.oses.map((o) => o.name);
  return names.length === 1 ? `a ${names[0]} desktop` : `a ${names.slice(0, -1).join(", ")} or ${names[names.length - 1]} desktop`;
}

const listOf = (xs) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
const osesOf = (driver) => CAT.oses.filter((o) => CAT.trials.some((t) => t.driver === driver && t.os === o.id));
const driverName = (id) => DRIVERS[id]?.name || id;
const driverLabel = (id) => DRIVERS[id]?.label || driverName(id);
const driverDot = (id) => h("span", { class: "dot", style: { background: `var(--s${(DRIVERS[id]?.slot ?? 0) % 8})` } });

function driverClause() {
  const arms = CAT.drivers.filter((d) => d.id !== CAT.driver);
  if (!arms.length) return "the computer-use driver's clicks, keys and window reads";
  const where = [...new Set(arms.flatMap((d) => osesOf(d.id).map((o) => o.name)))];
  const on = where.length < CAT.oses.length ? `on ${listOf(where)} ` : "";
  return `the clicks, keys and window reads of a computer-use driver: ${driverName(CAT.driver)}, and ${on}also ${listOf(arms.map((d) => d.name))}, to compare them`;
}

function boardView() {
  document.title = CAT.title;
  VIEW.board = true;
  const os = osSection();
  const wrap = h("div", { class: "wrap" },
    !os && (CAT.pairs || []).length ? pairsSection() : null,
    resultsSection(), costSection(),
    CAT.comparisons.length ? driversSection() : null,
    os, modelsSection(), failuresSection(), partialSection(), trialsSection(), howSection());
  $("#app").replaceChildren(h("div", { class: "wrap" }, landing()), sectionNav(wrap), wrap);
}

function sectionNav(root) {
  const heads = [...root.querySelectorAll("[data-nav]")];
  const links = heads.map((el) => h("a", { href: `#${el.id}` }, el.dataset.nav));
  const row = h("div", { class: "wrap" }, links);
  const nav = h("nav", { class: "snav", "aria-label": "Sections" }, row);
  let cur = -1;
  const spy = () => {
    if (!nav.isConnected) {
      window.removeEventListener("scroll", spy);
      return;
    }
    const line = nav.getBoundingClientRect().bottom + 32;
    const i = heads.reduce((at, el, k) => (el.getBoundingClientRect().top <= line ? k : at), -1);
    if (i === cur) return;
    links[cur]?.removeAttribute("aria-current");
    cur = i;
    if (i < 0) return;
    links[i].setAttribute("aria-current", "true");
    row.scrollTo({ left: links[i].offsetLeft - (row.clientWidth - links[i].offsetWidth) / 2, behavior: "smooth" });
  };
  window.addEventListener("scroll", spy, { passive: true });
  requestAnimationFrame(spy);
  return nav;
}

function landing() {
  const hero = CAT.trials.find((t) => t.uid === CAT.hero);
  return h("section", { class: "landing" },
    h("p", { class: "kicker" }, "trycua's Cua Driver Bench · run on AgentEnv computers"),
    h("h1", {}, "Can an AI agent do the office work without getting in your way?"),
    h("p", { class: "lede" },
      `An agent gets real office tasks on ${osPhrase()} (mail, chat, a calendar, a spreadsheet, a ledger, a browser) and may work `,
      h("b", {}, "only through the GUI"), `, with ${driverClause()}. `,
      "In the ", h("b", {}, "background"), " runs a person is typing in their own window the whole time, and the agent must finish ",
      h("b", {}, "without disturbing them"), ": no stolen focus, no window over theirs, no moved pointer, no touched clipboard."),
    h("div", { class: "cta" },
      hero && h("a", { class: "btn primary", href: hashOf(hero) }, h("span", { html: ICON_PLAY, style: { width: "14px", display: "inline-flex" } }), "Watch a background replay"),
      h("a", { class: "btn", href: "#results" }, "See the results"),
      CAT.comparisons.length ? h("a", { class: "btn", href: "#/drivers" }, "Compare drivers") : null),
    reelFigure(),
    h("div", { class: "players" },
      h("div", { class: "player-card" }, h("h3", {}, h("span", { class: "dot agent" }), "The agent"),
        h("p", {}, `${harnessPhrase() || "A model"}. It reads windows and acts through its computer-use driver's tools: click, type, press a key, open a menu. No terminal, no scripts, no side doors.`)),
      h("div", { class: "player-card" }, h("h3", {}, h("span", { class: "dot user" }), "The user"),
        h("p", {}, "In the background condition a simulated user types into their own window, “User activity”, one character a second. A sentinel logs everything that reaches them.")),
      h("div", { class: "player-card" }, h("h3", {}, h("span", { class: "dot judge" }), "The grade"),
        h("p", {}, "Every half must hold: the task, by trycua's own evaluator; GUI only, no way out of the GUI; and in the background, the user undisturbed on all eight of trycua's criteria."))));
}

function reelFigure() {
  const scenes = (CAT.reel?.scenes || []).map((s) => ({ ...s, fg: CAT.trials.find((t) => t.uid === s.foreground),
    bg: CAT.trials.find((t) => t.uid === s.background) })).filter((s) => s.fg && s.bg);
  if (!scenes.length) return null;
  const first = scenes[0].bg, task = TASKS[first.task] || {};
  const setup = (s) => `${OSES[s.os]?.name || s.os} · ${driverLabel(s.driver)}`;
  const video = h("video", { src: CAT.reel.video, autoplay: true, muted: true, loop: true, playsinline: true, preload: "metadata",
    "aria-label": `${first.model_name} on ${task.probe || first.task} ${task.title || ""}, run ${first.run_index}, through ${scenes.map(setup).join(", ")}: each setup's foreground trial beside its background one, then each setup's passes over the whole bench` });
  video.muted = true;
  return h("figure", { class: "pair reel" }, video,
    h("figcaption", {}, h("b", {}, `${task.probe || first.task} ${task.title || ""}, run ${first.run_index}`),
      ` — ${first.model_name} on each operating system and driver, the desktop to itself beside a person typing in their own window. Background replays: `,
      ...scenes.flatMap((s, i) => [i ? " · " : "", h("a", { href: hashOf(s.bg) }, setup(s))])));
}

function pairsSection() {
  return h("section", { class: "pairs", "aria-labelledby": "pairs-h" },
    h("div", { class: "section-head", id: "pairs" }, h("h2", { id: "pairs-h" }, "The same task in both conditions"),
      h("p", {}, "One run of a task in the foreground, left, and in the background, right: the same model, driver, task and seed, at one speed.")),
    pairList());
}

function pairList() {
  return h("div", { class: "pair-list" }, CAT.pairs.map((p) => {
    const fg = CAT.trials.find((t) => t.uid === p.foreground), bg = CAT.trials.find((t) => t.uid === p.background);
    if (!fg || !bg) return null;
    const task = TASKS[fg.task] || {};
    const said = (t) => (t.passed ? "pass" : "not a pass") + (t.condition === "background" && t.grade?.user_undisturbed?.result ? ", the user undisturbed" : "");
    const video = h("video", { src: p.video, autoplay: true, muted: true, loop: true, playsinline: true, preload: "metadata",
      "aria-label": `${fg.model_name} through ${driverName(fg.driver)} on ${OSES[p.os]?.name || p.os}, ${task.probe || fg.task} ${task.title || ""}: the foreground and background trials side by side` });
    video.muted = true;
    return h("figure", { class: "pair" }, video,
      h("figcaption", {}, h("b", {}, `${OSES[p.os]?.name || p.os} · ${(task.probe || fg.task).replace("CDB-", "")} ${task.title || ""}`),
        ` — ${fg.model_name} through ${driverName(fg.driver)}, run ${p.run_index}. Foreground ${said(fg)}; background ${said(bg)}. `,
        h("a", { href: hashOf(fg) }, "Replay the foreground"), " · ", h("a", { href: hashOf(bg) }, "Replay the background")));
  }));
}

function figures(keys, alt) {
  return h("div", { class: "figs" }, keys.map((f) => h("div", { class: "fig" }, h("picture", {},
    h("source", { media: "(max-width: 480px) and (prefers-color-scheme: dark)", srcset: `figures/${f}-phone-dark.svg` }),
    h("source", { media: "(max-width: 480px)", srcset: `figures/${f}-phone.svg` }),
    h("source", { media: "(prefers-color-scheme: dark)", srcset: `figures/${f}-dark.svg` }),
    h("img", { src: `figures/${f}.svg`, alt: alt(f) })),
    CAT.compare_notes?.[f] ? h("p", { class: "fnote" }, CAT.compare_notes[f].join(" ")) : null)));
}

function resultsSection() {
  const lines = CAT.models.filter((m) => m.board).length > 1 ? ", a line per model" : "";
  return h("section", { class: "results", "aria-labelledby": "results-h" },
    h("div", { class: "section-head", id: "results", "data-nav": "Results" }, h("h2", { id: "results-h" }, "Results"),
      h("p", {}, `The share of trials that fully pass: the task done, through the GUI only, and in the background with the user undisturbed. All through ${driverName(CAT.driver)}: a panel per OS${lines}.`)),
    figures(CAT.figures.filter((f) => f !== "task-score"), () => "Full pass by condition"));
}

// The cost section's filters for this visit: the condition counted and the OSes, drivers and models hidden.
const COST = { cond: "background", off: new Set() };
const SHAPES = ["circle", "square", "triangle", "diamond"];
const shapeOf = (id) => SHAPES[Math.max(0, CAT.drivers.findIndex((d) => d.id === id)) % SHAPES.length];
const slotOf = (id) => `var(--s${(MODELS[id]?.slot ?? 0) % 8})`;
const shortModel = (id) => (MODELS[id]?.name || id).replace(/^(Claude|GPT-[\d.]+)\s+/, "");
const usd = (v) => (v == null || !isFinite(v) ? "–" : `$${v < 0.095 ? v.toFixed(3) : v.toFixed(2)}`);
const fx = (v) => v.toFixed(1);

function glyph(shape, r) {
  const f = (v) => +v.toFixed(2);
  if (shape === "square") return `M${f(-r * 0.86)},${f(-r * 0.86)}H${f(r * 0.86)}V${f(r * 0.86)}H${f(-r * 0.86)}Z`;
  if (shape === "triangle") return `M0,${f(-r * 1.2)}L${f(r * 1.12)},${f(r * 0.8)}L${f(-r * 1.12)},${f(r * 0.8)}Z`;
  if (shape === "diamond") return `M0,${f(-r * 1.2)}L${f(r * 1.2)},0L0,${f(r * 1.2)}L${f(-r * 1.2)},0Z`;
  return `M${-r},0A${r},${r} 0 1,0 ${r},0A${r},${r} 0 1,0 ${-r},0Z`;
}

const markIcon = (shape, color) => sv("svg", { class: "mk", viewBox: "-8 -8 16 16", width: 14, height: 14, "aria-hidden": "true" },
  sv("path", { d: glyph(shape, 5.4), style: `fill: ${color}` }));

/** Each shown OS's setups (a driver and a model) in the chosen condition as the share of trials that fully pass against
 * their mean cost at list price, over the tasks every shown setup of that OS ran, so a panel's points count the same
 * trials; a point is on the frontier when no cheaper one passes as large a share. */
function costPanels() {
  const on = (k) => !COST.off.has(k);
  return CAT.oses.filter((o) => on(`os:${o.id}`)).map((o) => {
    const by = new Map();
    for (const t of CAT.trials) {
      if (t.os !== o.id || !MODELS[t.model]?.board || !on(`driver:${t.driver}`) || !on(`model:${t.model}`)) continue;
      if (COST.cond !== "all" && t.condition !== COST.cond) continue;
      const k = `${t.driver}|${t.model}`, c = `${t.task}|${t.condition}`;
      if (!by.has(k)) by.set(k, new Map());
      if (!by.get(k).has(c)) by.get(k).set(c, []);
      by.get(k).get(c).push(t);
    }
    const sets = [...by.values()];
    const cells = sets.length ? [...sets[0].keys()].filter((c) => sets.every((m) => m.has(c))) : [];
    const points = [...by.entries()].map(([k, m]) => {
      const [driver, model] = k.split("|");
      const trials = cells.flatMap((c) => m.get(c));
      const costs = trials.map((t) => t.cost).filter((v) => v != null);
      const passed = trials.filter((t) => t.passed).length;
      return { key: `${o.id}|${k}`, os: o.id, driver, model, trials, n: trials.length, passed,
        share: trials.length ? passed / trials.length : 0, cost: costs.length ? costs.reduce((a, b) => a + b, 0) / costs.length : null, frontier: false };
    }).filter((p) => p.n && p.cost > 0);
    let top = 0;
    for (const p of points.slice().sort((a, b) => a.cost - b.cost || b.share - a.share)) {
      if (p.share > top) { p.frontier = true; top = p.share; }
    }
    return { os: o, points, tasks: new Set(cells.map((c) => c.split("|")[0])).size };
  }).filter((p) => p.points.length);
}

function costSection() {
  const priced = CAT.trials.filter((t) => MODELS[t.model]?.board && t.cost != null);
  if (new Set(priced.map((t) => `${t.os}|${t.driver}|${t.model}`)).size < 2) return null;
  const ran = (key) => new Set(priced.map((t) => t[key]));
  const oses = CAT.oses.filter((o) => ran("os").has(o.id));
  const drivers = CAT.drivers.filter((d) => ran("driver").has(d.id));
  const models = CAT.models.filter((m) => m.board && ran("model").has(m.id));
  const host = h("div", { class: "pgrid" });
  const tip = h("div", { class: "ptip", hidden: true, role: "tooltip" });
  const stage = h("div", { class: "pstage" }, host, tip);
  const table = h("div", { class: "ptable-wrap" });
  const prev = new Map();
  let panels = [], pinned = null, sort = { key: "share", dir: -1 };
  const ctx = document.createElement("canvas").getContext("2d");
  const measure = (s, weight, size) => { ctx.font = `${weight} ${size}px Inter, system-ui, sans-serif`; return ctx.measureText(s).width; };

  const highlight = (match) => {
    stage.classList.toggle("dim", !!match);
    for (const el of stage.querySelectorAll("[data-key]")) el.classList.toggle("hl", !!match && match(el.dataset.key));
    for (const el of table.querySelectorAll("tr[data-key]")) el.classList.toggle("hl", !!match && match(el.dataset.key));
  };
  const find = (key) => panels.flatMap((p) => p.points).find((q) => q.key === key);
  const showTip = (key, pin) => {
    const q = find(key), el = stage.querySelector(`.pt[data-key="${CSS.escape(key)}"]`);
    if (!q || !el) return;
    pinned = pin ? key : null;
    tip.replaceChildren(...tipBody(q, panels.find((p) => p.os.id === q.os), pin));
    tip.classList.toggle("pinned", !!pin);
    tip.hidden = false;
    const r = el.querySelector("path").getBoundingClientRect(), box = stage.getBoundingClientRect();
    const half = tip.offsetWidth / 2, x = Math.min(Math.max(r.left + r.width / 2 - box.left, half + 4), box.width - half - 4);
    const below = r.top - box.top < tip.offsetHeight + 16;
    tip.classList.toggle("below", below);
    tip.style.left = `${x}px`;
    tip.style.top = `${(below ? r.bottom : r.top) - box.top}px`;
    highlight((k) => k === key);
  };
  const hideTip = () => { pinned = null; tip.hidden = true; highlight(null); };

  stage.addEventListener("pointerover", (e) => {
    const el = e.target.closest("[data-key]");
    if (el && !pinned && e.pointerType !== "touch") showTip(el.dataset.key, false);
  });
  stage.addEventListener("pointerout", (e) => {
    if (!pinned && e.target.closest("[data-key]") && !e.relatedTarget?.closest?.("[data-key]")) hideTip();
  });
  stage.addEventListener("click", (e) => {
    if (e.target.closest(".ptip")) return;
    const el = e.target.closest("[data-key]");
    if (el && pinned !== el.dataset.key) showTip(el.dataset.key, true);
    else hideTip();
  });
  stage.addEventListener("focusin", (e) => { const el = e.target.closest(".pt"); if (el && !pinned) showTip(el.dataset.key, false); });
  stage.addEventListener("focusout", (e) => { if (!pinned && !stage.contains(e.relatedTarget)) hideTip(); });
  stage.addEventListener("keydown", (e) => {
    const el = e.target.closest(".pt");
    if (e.key === "Escape") hideTip();
    else if (el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); showTip(el.dataset.key, true); }
  });

  const paint = (force) => {
    const all = panels.flatMap((p) => p.points);
    if (!all.length) return;
    const costs = all.map((q) => q.cost);
    const lo = Math.min(...costs) / 1.6, hi = Math.max(...costs) * 1.6;
    for (const [i, fig] of [...host.children].entries()) {
      const plot = fig.querySelector(".pplot");
      if (!plot?.clientWidth || (!force && +plot.dataset.w === plot.clientWidth)) continue;
      plot.dataset.w = plot.clientWidth;
      plot.replaceChildren(costPlane(panels[i], lo, hi, plot.clientWidth, prev, measure));
    }
    requestAnimationFrame(() => {
      for (const g of stage.querySelectorAll(".pt")) { g.style.transform = g.dataset.to; prev.set(g.dataset.key, g.dataset.to); }
    });
  };
  const draw = () => {
    hideTip();
    panels = costPanels();
    host.replaceChildren(...panels.map((p) => h("figure", { class: "ppanel" },
      h("figcaption", { class: "pcap" }, h("b", {}, p.os.name), h("span", {}, COST.cond === "all" ? "both conditions" : COST.cond),
        h("small", {}, `${p.tasks} task${p.tasks === 1 ? "" : "s"} · ${[...new Set(p.points.map((q) => q.n))].join("–")} trials a point`)),
      h("div", { class: "pplot" }),
      h("p", { class: "pline" }, frontierLine(p)))));
    host.classList.toggle("one", panels.length === 1);
    paint(true);
    table.replaceChildren(costTable(panels, sort, (key) => {
      sort = key === sort.key ? { key, dir: -sort.dir } : { key, dir: key === "name" || key === "cost" || key === "per" ? 1 : -1 };
      draw();
    }));
    sync.forEach((f) => f());
  };
  new ResizeObserver(() => requestAnimationFrame(() => paint(false))).observe(host);
  table.addEventListener("pointerover", (e) => { const tr = e.target.closest("tr[data-key]"); if (tr && !pinned) highlight((k) => k === tr.dataset.key); });
  table.addEventListener("pointerleave", () => { if (!pinned) highlight(null); });

  const sync = [];
  const conds = h("div", { class: "tabs", role: "group", "aria-label": "Condition" },
    [["background", "Background"], ["foreground", "Foreground"], ["all", "Both"]].map(([id, label]) =>
      h("button", { "data-id": id, onclick: () => { COST.cond = id; draw(); } }, label)));
  sync.push(() => { for (const b of conds.children) b.setAttribute("aria-pressed", String(b.dataset.id === COST.cond)); });
  const part = (key, i) => key.split("|")[i];
  const chips = (label, items, kind, at, icon) => {
    if (items.length < 2) return null;
    const row = h("div", { class: "pchips", role: "group", "aria-label": label }, h("span", { class: "plab" }, label),
      items.map((x) => h("button", { class: "pchip", "data-id": `${kind}:${x.id}`,
        onclick: () => {
          const k = `${kind}:${x.id}`;
          if (!COST.off.has(k) && items.filter((y) => !COST.off.has(`${kind}:${y.id}`)).length === 1) return;
          COST.off.has(k) ? COST.off.delete(k) : COST.off.add(k);
          draw();
        },
        onpointerenter: () => { if (!pinned) highlight((key) => part(key, at) === x.id); },
        onpointerleave: () => { if (!pinned) highlight(null); } }, icon(x), x.short || x.name)));
    sync.push(() => { for (const b of row.querySelectorAll(".pchip")) b.setAttribute("aria-pressed", String(!COST.off.has(b.dataset.id))); });
    return row;
  };
  const reset = h("button", { class: "preset", onclick: () => { COST.off.clear(); draw(); } }, "Show all");
  sync.push(() => { reset.hidden = !COST.off.size; });
  const controls = h("div", { class: "pcontrols" },
    h("div", { class: "pchips" }, h("span", { class: "plab" }, "Trials"), conds),
    chips("OS", oses, "os", 0, () => null),
    chips("Driver", drivers.map((d) => ({ ...d, short: driverLabel(d.id) })), "driver", 1, (d) => markIcon(shapeOf(d.id), "var(--ink-2)")),
    chips("Model", models, "model", 2, (m) => h("span", { class: "dot", style: { background: slotOf(m.id) } })),
    reset);
  draw();

  return h("section", { class: "cost", "aria-labelledby": "cost-h" },
    h("div", { class: "section-head", id: "cost", "data-nav": "Cost" }, h("h2", { id: "cost-h" }, "What a pass costs"),
      h("p", {}, "Each point is one setup, an operating system, a driver and a model: its full pass against what a trial costs. Hover or tap a point for its replays; filter with the chips.")),
    controls, stage,
    h("div", { class: "pkey" },
      drivers.length > 1 ? drivers.map((d) => h("span", {}, markIcon(shapeOf(d.id), "var(--ink-2)"), driverLabel(d.id))) : null,
      h("span", {}, h("i", { class: "pk on" }), "on the frontier"), h("span", {}, h("i", { class: "pk off" }), "passes no more than a cheaper point"),
      h("span", {}, h("i", { class: "pk line" }), "the frontier: the most any point passes at that cost or less")),
    h("p", { class: "dnote" }, "Cost is the mean a trial at list price, from the tokens each trial's trajectory reports (Anthropic's prices for Claude, OpenAI's for GPT-6), on a log scale. In a panel every point counts the same tasks and runs: those every shown setup ran."),
    table);
}

function costPlane(p, lo, hi, W, prev, measure) {
  const H = Math.round(Math.max(300, Math.min(430, W * 0.64)));
  const M = { l: 56, r: 12, t: 14, b: 44 };
  const L = Math.log10;
  const X = (c) => M.l + ((L(c) - L(lo)) / (L(hi) - L(lo))) * (W - M.l - M.r);
  const Y = (v) => M.t + (1 - v) * (H - M.t - M.b);
  const svg = sv("svg", { class: "psvg", viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
    "aria-label": `${p.os.name}: ${p.points.map((q) => `${MODELS[q.model]?.name} through ${driverLabel(q.driver)}, ${pct(q.share)} full pass at ${usd(q.cost)} a trial${q.frontier ? ", on the frontier" : ""}`).join("; ")}` });
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    svg.append(sv("line", { class: "pgl", x1: M.l, x2: W - M.r, y1: fx(Y(v)), y2: fx(Y(v)) }));
    svg.append(sv("text", { class: "ptick", x: M.l - 8, y: fx(Y(v) + 4), "text-anchor": "end" }, pct(v)));
  }
  for (const c of logTicks(lo, hi)) {
    svg.append(sv("line", { class: "pgl", x1: fx(X(c)), x2: fx(X(c)), y1: M.t, y2: H - M.b }));
    svg.append(sv("text", { class: "ptick", x: fx(X(c)), y: H - M.b + 17, "text-anchor": "middle" }, `$${c}`));
  }
  svg.append(sv("text", { class: "paxis", x: fx((M.l + W - M.r) / 2), y: H - 6, "text-anchor": "middle" }, "cost per trial, log scale"));
  svg.append(sv("text", { class: "paxis", transform: `translate(13 ${fx((M.t + H - M.b) / 2)}) rotate(-90)`, "text-anchor": "middle" }, "full pass"));
  const front = p.points.filter((q) => q.frontier).sort((a, b) => a.cost - b.cost);
  if (front.length) {
    const steps = front.slice(1).map((q) => `H${fx(X(q.cost))}V${fx(Y(q.share))}`).join("") + `H${W - M.r}`;
    const start = `M${fx(X(front[0].cost))},${fx(Y(0))}V${fx(Y(front[0].share))}`;
    svg.append(sv("path", { class: "parea", d: `${start}${steps}V${fx(Y(0))}Z` }));
    svg.append(sv("path", { class: "pfront", d: `${start}${steps}` }));
  }
  const multi = new Set(p.points.map((q) => q.driver)).size > 1;
  const at = (q) => [X(q.cost), Y(q.share)];
  const dots = p.points.map((q) => { const [x, y] = at(q); return [x - 10, y - 10, x + 10, y + 10]; });
  const bounds = [M.l - 4, 0, W, H - M.b + 4];
  const placed = [];
  for (const q of p.points.slice().sort((a, b) => b.frontier - a.frontier || b.share - a.share || a.cost - b.cost)) {
    const [x, y] = at(q);
    const l1 = multi ? `${shortModel(q.model)} · ${driverLabel(q.driver)}` : shortModel(q.model);
    const l2 = `${pct(q.share)} · ${usd(q.cost)}`;
    const w = Math.max(measure(l1, 650, 12.5), measure(l2, 500, 11.5)) + 2, ht = 29, R = 12;
    let best = null;
    for (const D of [R, R * 2.6]) {
      for (let [bx, by, anchor] of [[x + D, y - ht / 2, "start"], [x - D - w, y - ht / 2, "end"], [x - w / 2, y - D - ht, "middle"],
        [x - w / 2, y + D, "middle"], [x + D * 0.7, y - D * 0.7 - ht, "start"], [x + D * 0.7, y + D * 0.7, "start"],
        [x - D * 0.7 - w, y - D * 0.7 - ht, "end"], [x - D * 0.7 - w, y + D * 0.7, "end"]]) {
        if (anchor === "middle") bx = Math.min(Math.max(bx, bounds[0]), bounds[2] - w);
        const r = [bx, by, bx + w, by + ht];
        const cost = dots.reduce((s, b) => s + overlap(r, b) * 3, 0) + placed.reduce((s, b) => s + overlap(r, b.r) * 6, 0)
          + (area(r) - overlap(r, bounds)) * 10 + (D > R ? 40 : 0);
        if (!best || cost < best.cost) best = { cost, r, anchor, far: D > R };
      }
    }
    if (placed.some((b) => overlap(best.r, b.r) > 0) || area(best.r) > overlap(best.r, bounds)) continue;
    placed.push(best);
    const tx = { start: best.r[0], end: best.r[2], middle: (best.r[0] + best.r[2]) / 2 }[best.anchor];
    if (best.far) {
      const ex = Math.min(Math.max(x, best.r[0]), best.r[2]), ey = Math.min(Math.max(y, best.r[1] + 2), best.r[3] - 2);
      svg.append(sv("line", { class: "plead", "data-key": q.key, x1: fx(x), y1: fx(y), x2: fx(ex), y2: fx(ey) }));
    }
    svg.append(sv("g", { class: `pl${q.frontier ? " on" : ""}`, "data-key": q.key, transform: `translate(${fx(tx)} ${fx(best.r[1])})` },
      sv("text", { y: 12, "text-anchor": best.anchor, class: "pl1" }, l1),
      sv("text", { y: 26, "text-anchor": best.anchor, class: "pl2" }, l2)));
  }
  for (const q of p.points) {
    const [x, y] = at(q);
    const to = `translate(${fx(x)}px, ${fx(y)}px)`;
    svg.append(sv("g", { class: `pt${q.frontier ? " on" : ""}${prev.has(q.key) ? "" : " new"}`, "data-key": q.key, "data-to": to,
      style: `transform: ${prev.get(q.key) || to}; --c: ${slotOf(q.model)}`, tabindex: "0", role: "button",
      "aria-label": `${MODELS[q.model]?.name} through ${driverLabel(q.driver)} on ${p.os.name}: ${q.passed} of ${q.n} trials pass, ${usd(q.cost)} a trial` },
    sv("circle", { r: 16, class: "phit" }), sv("path", { d: glyph(shapeOf(q.driver), q.frontier ? 7.5 : 6.5) })));
  }
  return svg;
}

const area = (r) => Math.max(0, r[2] - r[0]) * Math.max(0, r[3] - r[1]);
const overlap = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));

function logTicks(lo, hi) {
  const steps = hi / lo > 30 ? [1, 3] : [1, 2, 3, 5];
  const out = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
    for (const m of steps) { const v = +(m * 10 ** e).toPrecision(6); if (v >= lo && v <= hi) out.push(v); }
  }
  return out;
}

const setupName = (q, multi) => `${MODELS[q.model]?.name || q.model}${multi ? ` through ${driverLabel(q.driver)}` : ""}`;

/** A panel's frontier in a sentence: where it starts and ends, and what the dearer end buys over the cheaper. */
function frontierLine(p) {
  const multi = new Set(p.points.map((q) => q.driver)).size > 1;
  const front = p.points.filter((q) => q.frontier).sort((a, b) => a.cost - b.cost);
  const said = (q) => [h("b", {}, setupName(q, multi)), ` (${pct(q.share)} at ${usd(q.cost)})`];
  if (!front.length) return "No setup shown here passes a trial.";
  if (p.points.length > 1 && new Set(p.points.map((q) => q.share)).size === 1) {
    return [`Every setup shown here passes ${pct(front[0].share)}, so the cheapest, `, h("b", {}, setupName(front[0], multi)), ` at ${usd(front[0].cost)} a trial, is the whole frontier.`];
  }
  const off = p.points.length - front.length;
  const rest = off ? ` The other ${off === 1 ? "point passes" : `${off} pass`} no more than a cheaper one.` : "";
  if (front.length === 1) return [...said(front[0]), p.points.length > 1 ? " passes the most, and nothing passes as much for less." : ".", rest];
  const a = front[0], b = front[front.length - 1];
  return ["The frontier runs from ", ...said(a), " to ", ...said(b),
    `: ${(b.cost / a.cost).toFixed(1)}× the cost a trial for ${Math.round((b.share - a.share) * 100)} points more.`, rest];
}

function tipBody(q, p, pin) {
  const multi = new Set(p.points.map((x) => x.driver)).size > 1;
  const beat = q.frontier ? null : p.points.filter((x) => x.frontier && x.cost <= q.cost && x.share >= q.share).sort((a, b) => a.cost - b.cost)[0];
  const pass = q.trials.find((t) => t.passed), fail = q.trials.find((t) => !t.passed);
  const row = (k, v) => h("div", { class: "trow" }, h("span", {}, k), h("b", {}, v));
  return [
    h("div", { class: "thead" }, h("span", { class: "dot", style: { background: slotOf(q.model) } }), MODELS[q.model]?.name || q.model),
    h("div", { class: "tsub" }, [driverLabel(q.driver), p.os.name, COST.cond === "all" ? "both conditions" : COST.cond, HARNESS_NAMES[MODELS[q.model]?.harness]].filter(Boolean).join(" · ")),
    row("Full pass", `${q.passed} of ${q.n} · ${pct(q.share)}`),
    row("A trial", usd(q.cost)),
    row("A full pass", q.passed ? usd(q.cost / q.share) : "no pass"),
    h("div", { class: "tfoot" }, q.frontier ? "On the frontier: nothing cheaper passes as much."
      : beat ? `Off the frontier: ${setupName(beat, multi)} passes ${beat.share > q.share ? "more" : "as much"} for less.` : "No pass, so off the frontier."),
    pin ? h("div", { class: "tlinks" }, pass ? h("a", { href: hashOf(pass) }, "Replay a pass →") : null, fail ? h("a", { href: hashOf(fail) }, "Replay a failure →") : null)
      : h("div", { class: "thint" }, "Click for its replays"),
  ];
}

function costTable(panels, sort, onsort) {
  const multiOs = panels.length > 1;
  const rows = panels.flatMap((p) => p.points.map((q) => ({ q, p })));
  const val = { name: ({ q }) => `${q.os} ${MODELS[q.model]?.name} ${driverLabel(q.driver)}`, share: ({ q }) => q.share,
    cost: ({ q }) => q.cost, per: ({ q }) => (q.passed ? q.cost / q.share : Infinity) };
  rows.sort((a, b) => {
    const x = val[sort.key](a), y = val[sort.key](b);
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * sort.dir || a.q.cost - b.q.cost;
  });
  const th = (key, label, cls) => h("th", { class: cls, "aria-sort": sort.key === key ? (sort.dir > 0 ? "ascending" : "descending") : null },
    h("button", { onclick: () => onsort(key) }, label, h("span", { class: "sarr", "aria-hidden": "true" }, sort.key === key ? (sort.dir > 0 ? "▲" : "▼") : "")));
  return h("table", { class: "ptable" },
    h("thead", {}, h("tr", {}, th("name", "Setup", "l"), th("share", "Full pass"), th("cost", "A trial"), th("per", "A full pass"), h("th", {}, "Frontier"))),
    h("tbody", {}, rows.map(({ q, p }) => h("tr", { "data-key": q.key },
      h("td", { class: "l" }, h("span", { class: "psetup" }, markIcon(shapeOf(q.driver), slotOf(q.model)),
        h("span", {}, h("b", {}, MODELS[q.model]?.name || q.model), h("small", {}, [driverLabel(q.driver), multiOs ? p.os.name : null].filter(Boolean).join(" · "))))),
      h("td", {}, h("span", { class: "pbar" }, h("i", { style: { width: pct(q.share) } })), h("b", {}, pct(q.share)), h("small", {}, ` ${q.passed}/${q.n}`)),
      h("td", {}, usd(q.cost)),
      h("td", {}, q.passed ? usd(q.cost / q.share) : "–"),
      h("td", {}, q.frontier ? h("span", { class: "fyes", "aria-label": "on the frontier" }, "✓") : "")))));
}

/** How trycua's task score, its partial credit, differs from a full pass: the three levels, where the credit goes from
 * one to the next on each OS and condition, how the trials that fail still score, and the task-score figures. */
function partialSection() {
  const runs = CAT.trials.filter((t) => MODELS[t.model]?.board && t.grade?.task);
  if (!runs.length) return null;
  const rows = CAT.oses.flatMap((o) => CAT.conditions.map((c) => {
    const r = runs.filter((t) => t.os === o.id && t.condition === c.id);
    if (!r.length) return null;
    const share = (f) => r.filter(f).length / r.length;
    const done = (t) => t.grade.task.result;
    return { label: `${o.name} · ${c.name.toLowerCase()}`, n: r.length, bg: c.id === "background", steps: [
      meanOf(r.map((t) => t.grade.task.score)), share(done), share((t) => t.passed)] };
  })).filter(Boolean);
  const heads = ["Task score, mean", "Task done", "Full pass"];
  const ladder = h("div", { class: "ladder", role: "table", "aria-label": "Mean task score, task done and full pass, per OS and condition" },
    h("div", { class: "lrow lhead", role: "row" }, h("span", { role: "columnheader" }), heads.map((x, i) => h("span", { role: "columnheader", class: `l${i}` }, x))),
    rows.map((r) => h("div", { class: "lrow", role: "row" }, h("span", { class: "lname", role: "rowheader" }, r.label, h("small", {}, `${r.n} trials`)),
      r.steps.map((v, i) => h("span", { class: `lcell l${i}`, role: "cell", "data-k": heads[i] },
        h("span", { class: "lbar" }, h("i", { style: { width: pct(v) } })), h("b", {}, pct(v)))))));
  const hist = h("div");
  const histTabs = h("div", { class: "tabs", role: "group", "aria-label": "Condition" });
  const pickHist = (cond) => {
    for (const b of histTabs.children) b.setAttribute("aria-pressed", String(b.dataset.id === cond));
    hist.replaceChildren(scoreHist(runs.filter((t) => cond === "all" || t.condition === cond), cond));
  };
  histTabs.append(...[["all", "Both"], ["foreground", "Foreground"], ["background", "Background"]].map(([id, label]) =>
    h("button", { "data-id": id, onclick: () => pickHist(id) }, label)));
  pickHist("all");
  const figs = [...CAT.figures, ...(CAT.driver_figures || [])].filter((f) => f.endsWith("task-score"));
  return h("section", { class: "partial", "aria-labelledby": "partial-h" },
    h("div", { class: "section-head", id: "partial", "data-nav": "Partial credit" }, h("h2", { id: "partial-h" }, "Partial credit"),
      h("p", {}, "trycua's task score, how it differs from a full pass, and where the gap comes from.")),
    h("div", { class: "levels" },
      h("article", {}, h("span", { class: "lvl" }, "Partial credit"), h("h3", {}, "Task score"),
        h("p", {}, "trycua's evaluator runs weighted checks on the files the apps left. The task score is the share of points that held, from 0 to 100%: a run that fixed the calendar but not the workbook still scores.")),
      h("article", {}, h("span", { class: "lvl" }, "trycua's success"), h("h3", {}, "Task done"),
        h("p", {}, "Every one of the task's checks held: a task score of 100%. Anything less is partial credit and counts as the task not done.")),
      h("article", { class: "full" }, h("span", { class: "lvl" }, "What this page counts"), h("h3", {}, "Full pass"),
        h("p", {}, "The task done, through the GUI only, and in the background with the user undisturbed on all eight of trycua's criteria. A trial can score 100% on the task and still fail."))),
    h("div", { class: "subhead" }, h("h3", {}, "Where the credit goes"), h("p", {}, "Every trial on the board, each OS and condition, from the mean task score down to the full pass.")),
    ladder,
    h("div", { class: "subhead" }, h("h3", {}, "How the trials that fail still score"), h("p", {}, "Every trial that didn't fully pass, by its task score, a column per tenth."), histTabs),
    hist,
    figs.length ? [h("div", { class: "subhead" }, h("h3", {}, "Task score by condition and by driver"), h("p", {}, "The results and drivers figures, scored by partial credit instead of full pass.")),
      figures(figs, (f) => (f.startsWith("drivers") ? "Task score by driver" : "Task score by condition"))] : null);
}

function scoreHist(runs, cond) {
  const failed = runs.filter((t) => !t.passed);
  const kind = (t) => (t.grade.task.result ? "done" : "short");
  const bins = Array.from({ length: 11 }, () => ({ done: 0, short: 0 }));
  for (const t of failed) bins[Math.min(10, Math.floor((t.grade.task.score ?? 0) * 10 + 1e-9))][kind(t)]++;
  const top = Math.max(1, ...bins.map((b) => b.done + b.short));
  const half = failed.filter((t) => (t.grade.task.score ?? 0) >= 0.5).length, done = failed.filter((t) => t.grade.task.result).length;
  const NAMES = { short: "task not done", done: cond === "foreground" ? "task done, then left the GUI" : "task done, then left the GUI or disturbed the user" };
  return h("div", { class: "hist" },
    tips(h("div", { class: "hbars" }, bins.map((b, i) => h("div", { class: "hcol" },
      h("div", { class: "hstack" }, ["short", "done"].map((k) => b[k] ? h("i", { class: `h${k}`, style: { height: `${(b[k] / top) * 100}%` },
        "data-tip": `${b[k]} trial${b[k] === 1 ? "" : "s"} scoring ${i === 10 ? "100%" : `${i * 10}–${i * 10 + 9}%`}: ${NAMES[k]}` }) : null)),
      h("span", { class: "hlab" }, i === 10 ? "100%" : `${i * 10}`))))),
    h("div", { class: "okey" }, Object.entries(NAMES).map(([k, v]) => h("span", {}, h("i", { class: `hk h${k}` }), v))),
    failed.length ? h("p", { class: "dnote" }, `Of the ${failed.length} trials here that didn't fully pass, `, h("b", {}, `${half} (${pct(half / failed.length)})`),
      " still scored half the task's points or more, and ", h("b", {}, `${done}`), ` did the whole task but ${NAMES.done.replace("task done, then ", "")}. Both count toward the task score and not toward a full pass.`) : null);
}

function driversSection() {
  const c = CAT.comparisons.find((x) => x.model === leadModel() && x.tasks.length === CAT.comparisons[0].tasks.length) || CAT.comparisons[0];
  const runs = CAT.trials.filter((t) => t.os === c.os && t.model === c.model && c.tasks.includes(t.task) && c.drivers.some((d) => d.id === t.driver));
  const depth = Math.max(...runs.map((t) => t.of));
  const cards = tips(h("div", { class: "xcards" }, c.drivers.map((d) => driverCard(d, runs.filter((t) => t.driver === d.id), c.tasks, depth))));
  const extra = (CAT.failure_figures || []).filter((f) => f === "disturbances");
  return h("section", { class: "drivers", "aria-labelledby": "drivers-h" },
    h("div", { class: "section-head", id: "drivers", "data-nav": "Drivers" }, h("h2", { id: "drivers-h" }, "How the drivers differ"),
      h("p", {}, `${OSES[c.os]?.name || c.os} · ${MODELS[c.model]?.name || c.model} · the same ${c.tasks.length} tasks and seeds; only the computer-use driver changes.`)),
    cards, outcomeKey(cards),
    figures(CAT.driver_figures.filter((f) => !f.endsWith("task-score")), () => "Full pass by driver"),
    extra.length ? h("div", { class: "solo" }, figures(extra, () => "Which of the user's eight criteria each driver broke in the background")) : null,
    h("p", { class: "dnote" }, "Every driver also serves AgentEnv's ", h("code", {}, "computer_*"),
      " tools, which the grader and the recordings use; no driver's agents here see them. cua-driver's first runs on ",
      "macOS and Linux, which offered seven of them too, are in the dataset but not here."),
    compareView());
}

function driverCard(d, runs, tasks, depth) {
  const dv = DRIVERS[d.id] || { name: d.id };
  const bg = runs.filter((t) => t.condition === "background" && t.grade?.user_undisturbed);
  const hurt = bg.filter((t) => !t.grade.user_undisturbed.result);
  const broke = CRIT.map((c) => [c, hurt.filter((t) => t.grade.user_undisturbed.criteria[c.id] === false).length])
    .filter(([, n]) => n).sort((a, b) => b[1] - a[1]).slice(0, 3);
  return h("article", { class: "xcard", style: { "--dc": `var(--s${(dv.slot ?? 0) % 8})` } },
    h("h3", {}, h("span", { class: "dot" }), dv.name),
    dv.detail && h("p", { class: "what", title: dv.detail }, dv.detail.split(";")[0]),
    waffles(runs, tasks, depth),
    bg.length ? h("div", { class: "xline" }, h("span", {}, "Disturbed the user in ", h("b", {}, `${hurt.length} of ${bg.length}`), " background trials"),
      broke.map(([c, n]) => h("span", { class: "cchip", title: `${c.broken} in ${n} of them` }, c.short, h("b", {}, n)))) : null,
    topFailure(runs), pace(runs));
}

function topFailure(runs) {
  const F = CAT.failures;
  const failed = runs.filter((t) => F?.by_trial[t.uid] && F.by_trial[t.uid] !== "pass");
  if (!failed.length) return null;
  const tally = {};
  for (const t of failed) tally[F.by_trial[t.uid]] = (tally[F.by_trial[t.uid]] || 0) + 1;
  const [id, n] = Object.entries(tally).reduce((a, b) => (b[1] > a[1] ? b : a));
  const mode = F.modes.find((m) => m.id === id) || { name: id };
  const ex = (F.examples?.[id] || []).map((uid) => failed.find((t) => t.uid === uid)).find(Boolean) || failed.find((t) => F.by_trial[t.uid] === id);
  return h("p", { class: "xline" }, "Most common failure: ", h("b", { title: mode.description || null }, mode.name),
    ` in ${n} of its ${failed.length} failed trials. `, h("a", { href: hashOf(ex) }, "Watch one"));
}

/** The landing replay's model, which the drivers cards and the OS facts follow when it ran there too, so the page
 * keeps to one model where it can. */
const leadModel = () => CAT.trials.find((t) => t.uid === CAT.hero)?.model;

const KEY = { pass: "Pass", user: "User disturbed", task: "Task not done", gui: "Left the GUI", other: "Grade incomplete", gap: "No trial yet" };
const SAID = { pass: "pass", user: "fail, the user was disturbed", task: "fail, the task wasn't done", gui: "fail, it left the GUI", other: "not a full pass" };
const probeOf = (id) => (TASKS[id]?.probe || id).replace("CDB-", "");

function outcome(t) {
  const g = t.grade || {};
  if (t.passed) return "pass";
  if (g.gui_only && !g.gui_only.result) return "gui";
  if (t.condition === "background" && g.user_undisturbed && !g.user_undisturbed.result) return "user";
  return g.task && !g.task.result ? "task" : "other";
}

function waffles(runs, tasks, depth) {
  return h("div", { class: "wpair" }, CAT.conditions.map((k) => {
    const ids = tasks.filter((id) => TASKS[id]?.conditions.includes(k.id));
    if (!ids.length) return null;
    const mine = runs.filter((t) => t.condition === k.id);
    const pass = mine.filter((t) => t.passed).length;
    return h("div", { class: "wblk" },
      h("div", { class: "wlab" }, h("span", {}, k.name), h("b", {}, mine.length ? pct(pass / mine.length) : "–"), h("small", {}, `${pass}/${mine.length}`)),
      waffle(mine, ids, depth, `${k.name}: ${pass} of ${mine.length} trials pass`));
  }));
}

function waffle(runs, ids, depth, label) {
  const fams = [];
  for (const id of ids) {
    if (fams[fams.length - 1]?.id !== TASKS[id].family) fams.push({ id: TASKS[id].family, ids: [] });
    fams[fams.length - 1].ids.push(id);
  }
  return h("div", { class: "wf", role: "group", "aria-label": label }, fams.map((f) => h("div", { class: "wfg" },
    h("div", { class: "wcols" }, f.ids.map((id) => {
      const col = runs.filter((t) => t.task === id);
      return h("div", { class: "wc" }, col.map(square),
        Array.from({ length: Math.max(0, depth - col.length) }, () => h("i", { class: "sq gap", "data-tip": `${probeOf(id)}: no trial yet` })));
    })),
    h("span", { class: "wfam" }, f.id))));
}

function square(t) {
  const k = outcome(t);
  const mode = CAT.failures?.modes.find((m) => m.id === CAT.failures.by_trial[t.uid]);
  const say = `${probeOf(t.task)} ${TASKS[t.task]?.title || ""}, run ${t.run_index ?? t.nth}: ${SAID[k]}${mode ? ` (${mode.name})` : ""}`;
  return h("a", { class: `sq ${k}`, href: hashOf(t), "data-tip": say, "aria-label": `${say}. Replay it`, tabindex: "-1" });
}

function tips(root) {
  const tip = h("div", { class: "tip", hidden: true });
  root.append(tip);
  root.addEventListener("pointerover", (e) => {
    const el = e.target.closest("[data-tip]");
    if (!el) return;
    tip.textContent = el.dataset.tip;
    tip.hidden = false;
    const r = el.getBoundingClientRect(), box = root.getBoundingClientRect(), half = tip.offsetWidth / 2;
    tip.style.left = `${Math.min(Math.max(r.left + r.width / 2 - box.left, half), box.width - half)}px`;
    tip.style.top = `${r.top - box.top}px`;
  });
  root.addEventListener("pointerout", (e) => {
    if (e.target.closest("[data-tip]")) tip.hidden = true;
  });
  return root;
}

function outcomeKey(cards) {
  return h("div", { class: "okey" },
    Object.entries(KEY).filter(([k]) => cards.querySelector(`.sq.${k}`)).map(([k, label]) => h("span", {}, h("i", { class: `sq ${k}` }), label)),
    h("span", { class: "okey-note" }, "A square per trial: a column per task, a row per run. A trial that broke several halves shows the first of GUI only, the user and the task. Click one to replay it."));
}

function osSection() {
  const gap = osGap();
  if (!gap) return null;
  const label = gap.oses.map((o) => o.name).join(" vs ");
  const figs = (CAT.compare_figures || []).filter((f) => f === "os-gap");
  return h("section", { class: "oses", "aria-labelledby": "os-h" },
    h("div", { class: "section-head", id: "os", "data-nav": label }, h("h2", { id: "os-h" }, label),
      h("p", {}, `The same driver, model and tasks on two desktops: ${driverName(CAT.driver)} and ${gap.model.name}.`)),
    h("div", { class: `os-top${figs.length ? "" : " bare"}` },
      h("div", { class: "facts" }, gapFact(gap), taskFact(gap.oses)),
      figs.length ? figures(figs, () => `Full pass on ${label}, in the foreground and the background`) : null),
    (CAT.pairs || []).length ? [h("div", { class: "subhead" }, h("h3", {}, "One run on each, foreground beside background"),
      h("p", {}, "The same model, driver, task and seed in both conditions, at one speed.")), pairList()] : null);
}

function osGap() {
  const rows = CAT.board.filter((r) => r.driver === CAT.driver);
  const oses = CAT.oses.filter((o) => rows.some((r) => r.os === o.id));
  if (oses.length !== 2) return null;
  const row = (os, model, cond) => rows.find((r) => r.os === os.id && r.model === model && r.condition === cond);
  const shared = CAT.models.filter((m) => CAT.conditions.every((k) => oses.every((o) => row(o, m.id, k.id))));
  if (!shared.length) return null;
  const size = (m) => rows.filter((r) => r.model === m.id).reduce((s, r) => s + r.n_trials, 0);
  const model = shared.find((m) => m.id === leadModel()) || shared.reduce((a, b) => (size(b) > size(a) ? b : a));
  const conds = Object.fromEntries(CAT.conditions.map((k) => {
    const both = oses.map((o) => row(o, model.id, k.id));
    const tasks = Object.keys(both[0].tasks).filter((t) => t in both[1].tasks);
    return [k.id, { tasks, by: both.map((r) => ({ k: tasks.reduce((s, t) => s + r.tasks[t].passed, 0), n: tasks.reduce((s, t) => s + r.tasks[t].n, 0) })) }];
  }));
  return { oses, model, conds };
}

function gapFact({ oses, model, conds }) {
  const share = (x) => (x.n ? x.k / x.n : null);
  const { background: bg, foreground: fg } = conds;
  return h("article", { class: "fact" },
    h("h3", {}, "Background full pass"),
    h("p", { class: "fsub" }, `${model.name} through ${driverName(CAT.driver)}, the same ${bg.tasks.length} tasks while a user types`),
    h("div", { class: "fnums" }, oses.map((o, i) => h("div", { class: "fnum" },
      h("small", {}, o.name), h("b", {}, pct(share(bg.by[i]))),
      h("span", { class: "meter" }, h("i", { style: { width: pct(share(bg.by[i]) || 0) } })),
      h("span", {}, `${bg.by[i].k} of ${bg.by[i].n} trials`)))),
    h("p", { class: "fnote" }, `In the foreground, the desktop to itself: ${oses.map((o, i) => `${pct(share(fg.by[i]))} on ${o.name}`).join(", ")}.`));
}

function taskFact(oses) {
  const rows = CAT.board.filter((r) => r.driver === CAT.driver && r.condition === "background");
  const tasks = CAT.tasks.filter((k) => oses.every((o) => rows.some((r) => r.os === o.id && r.tasks[k.id])));
  const lines = oses.map((o) => {
    const mine = rows.filter((r) => r.os === o.id);
    return { o, models: mine.length, cells: tasks.map((k) => mine.map((r) => r.tasks[k.id]).filter(Boolean)) };
  });
  const marks = new Map();
  const cell = (l, k, i) => {
    const passed = l.cells[i].reduce((s, p) => s + p.passed, 0), n = l.cells[i].reduce((s, p) => s + p.n, 0);
    const cv = caveatOf(l.o.id, "background", k.id);
    if (cv && !passed) marks.set(cv.mark, cv);
    return h("span", { class: `tc ${passed ? "ok" : "no"}`, "data-tip": `${probeOf(k.id)} on ${l.o.name}: ${passed} of ${n} background trials pass${cv ? `. ${cv.short}` : ""}` },
      passed ? "✓" : cv ? cv.mark : "");
  };
  const grid = tips(h("div", { class: "tstrip", style: { "--n": tasks.length } },
    h("span"), tasks.map((k) => h("span", { class: "th" }, probeOf(k.id))), h("span"),
    lines.map((l) => [h("span", { class: "rl" }, l.o.name), tasks.map((k, i) => cell(l, k, i)),
      h("b", { class: "rc" }, `${l.cells.filter((ps) => ps.some((p) => p.passed)).length} of ${tasks.length}`)])));
  return h("article", { class: "fact" },
    h("h3", {}, "Background tasks any model passed"),
    h("p", { class: "fsub" }, `Through ${driverName(CAT.driver)}: ${lines.map((l) => `${l.models} model${l.models === 1 ? "" : "s"} on ${l.o.name}`).join(", ")}`),
    grid,
    [...marks.values()].map((cv) => h("p", { class: "fnote", title: cv.reason }, h("b", {}, `${cv.mark} ${cv.short}. `),
      cv.reason.replace(/\s*\([^)]*\)/g, "").split(/(?<=\.)\s+/).slice(0, 2).join(" "))));
}

const HARNESS_NAMES = { "claude-code": "Claude Code", "codex-cli": "Codex CLI" };

function modelsSection() {
  const rows = CAT.board.filter((r) => r.driver === CAT.driver);
  const on = (o) => CAT.models.filter((m) => m.board && rows.some((r) => r.os === o.id && r.model === m.id));
  const oses = CAT.oses.filter((o) => on(o).length >= 2).sort((a, b) => on(b).length - on(a).length);
  if (!oses.length) return null;
  const sub = h("p", {});
  const body = h("div", {});
  const tabs = oses.length > 1 ? h("div", { class: "tabs", role: "group", "aria-label": "Operating system" },
    oses.map((o) => h("button", { "aria-pressed": "false", onclick: () => show(o) }, o.name))) : null;
  const show = (os) => {
    VIEW.modelsOs = os.id;
    if (tabs) [...tabs.children].forEach((b, i) => b.setAttribute("aria-pressed", String(oses[i] === os)));
    const models = on(os);
    const runs = CAT.trials.filter((t) => t.os === os.id && t.driver === CAT.driver && models.some((m) => m.id === t.model));
    const tasks = CAT.tasks.filter((k) => runs.some((t) => t.task === k.id)).map((k) => k.id);
    const depth = Math.max(...runs.map((t) => t.of));
    const cards = tips(h("div", { class: "xcards" }, models.map((m) => modelCard(m, runs.filter((t) => t.model === m.id), tasks, depth))));
    const key = os === oses[0] ? "models-tasks" : `models-tasks-${os.id}`;
    const figs = (CAT.compare_figures || []).filter((f) => f === key);
    sub.textContent = `${os.name} · ${driverName(CAT.driver)} · the same ${tasks.length} tasks; only the model and its harness change.`;
    body.replaceChildren(...[cards, outcomeKey(cards),
      models.some((m) => m.harness === "codex-cli") ? h("p", { class: "dnote" }, "Codex CLI hands the model a tool's structured result alone, so GPT never sees ",
        `${driverName(CAT.driver)}'s window screenshots, only its accessibility tree.`) : null,
      figs.length ? figures(figs, () => "Passes by task and model: a row per task and a column per model, foreground and background") : null].filter(Boolean));
  };
  show(oses.find((o) => o.id === VIEW.modelsOs) || oses[0]);
  return h("section", { class: "models", "aria-labelledby": "models-h" },
    h("div", { class: "section-head", id: "models", "data-nav": "Models" }, h("h2", { id: "models-h" }, "How the models differ"), sub),
    tabs, body);
}

function modelCard(m, runs, tasks, depth) {
  const effort = runs.find((t) => t.effort)?.effort || (m.harness === "claude-code" ? "medium" : null);
  return h("article", { class: "xcard", style: { "--dc": `var(--s${(m.slot ?? 0) % 8})` } },
    h("h3", {}, h("span", { class: "dot" }), m.name),
    h("p", { class: "what" }, [HARNESS_NAMES[m.harness] || m.harness, effort && `${effort} effort`].filter(Boolean).join(" · ")),
    waffles(runs, tasks, depth), pace(runs));
}

function pace(runs) {
  const times = runs.map((t) => t.duration).filter((v) => v != null).sort((a, b) => a - b);
  const capped = runs.filter((t) => /^Hit the \d+-turn limit/.test(t.ending || "")).length;
  return h("p", { class: "xline pace" }, `Median trial ${mins(times[times.length >> 1])} · ${Math.round(meanOf(runs.map((t) => t.tool_calls)))} tool calls on average`,
    capped ? ` · out of turns in ${capped} of ${runs.length}` : "");
}

function failuresSection() {
  const F = CAT.failures;
  const figs = (CAT.failure_figures || []).filter((f) => f === "failure-modes");
  const clips = CAT.gallery || [];
  if (!F && !figs.length && !clips.length) return null;
  return h("section", { class: "failures", "aria-labelledby": "failures-h" },
    h("div", { class: "section-head", id: "failures", "data-nav": "Failures" }, h("h2", { id: "failures-h" }, "Where trials fail"),
      h("p", {}, "What broke in the trials that failed, and a clip of each kind.")),
    figs.length ? figures(figs, () => "How every trial ended: a pass, or the gravest way it failed, a bar per OS, driver and model in each condition") : null,
    gallery(F, clips));
}

function gallery(F, clips) {
  const outcomes = F ? CAT.trials.map((t) => F.by_trial[t.uid]).filter(Boolean) : [];
  const count = (id) => outcomes.filter((x) => x === id).length;
  const modes = (F?.modes || []).filter((m) => count(m.id) || clips.some((g) => outcomeOf(g) === m.id))
    .sort((a, b) => (a.id === "pass") - (b.id === "pass") || count(b.id) - count(a.id));
  const grid = h("div", { class: "fgrid" }, clips.map(clip));
  const desc = h("p", { class: "mdesc" });
  const chips = h("div", { class: "tabs modes", role: "group", "aria-label": "Failure modes" },
    [null, ...modes].map((m) => h("button", { "aria-pressed": "false", onclick: () => pick(m) }, m ? m.name : "All", h("small", {}, m ? count(m.id) : clips.length))));
  const pick = (m) => {
    [null, ...modes].forEach((x, i) => chips.children[i].setAttribute("aria-pressed", String(x === m)));
    for (const el of grid.children) el.hidden = !!m && el.dataset.mode !== m.id;
    const none = m && !clips.some((g) => outcomeOf(g) === m.id);
    const ex = none ? (F.examples?.[m.id] || []).map((uid) => CAT.trials.find((t) => t.uid === uid)).filter(Boolean).slice(0, 4) : [];
    desc.replaceChildren(h("span", {}, m?.description, ex.length ? [" No clip of this one yet; replay ", ex.map((t, i) => [i ? " · " : "",
      h("a", { href: hashOf(t) }, `${probeOf(t.task)} on ${OSES[t.os]?.name || t.os}, ${driverLabel(t.driver)}, ${t.model_name}`)]), "."] : null));
    desc.hidden = !m;
  };
  pick(null);
  playWhenSeen(grid.querySelectorAll("video"));
  return h("div", { class: "gallery" }, modes.length ? chips : null, desc, grid);
}

function clip(g) {
  const t = CAT.trials.find((x) => x.uid === g.uid);
  const mode = CAT.failures?.modes.find((m) => m.id === outcomeOf(g));
  const video = h("video", { src: g.video, muted: true, loop: true, playsinline: true, preload: "none", "aria-label": `${g.title}: ${g.caption}` });
  video.muted = true;
  return h("figure", { class: `fclip${t?.passed ? " pass" : ""}`, "data-mode": outcomeOf(g) }, video,
    h("figcaption", {}, h("b", {}, g.title), g.caption ? h("p", {}, g.caption) : null,
      h("div", { class: "fclip-foot" },
        mode ? h("span", { class: "chip mode" }, mode.name) : null,
        h("span", { class: "chip" }, OSES[g.os]?.name || g.os),
        h("span", { class: "chip", title: driverName(g.driver) }, driverDot(g.driver), driverLabel(g.driver)),
        h("span", { class: "chip" }, h("span", { class: "dot", style: { background: `var(--s${(MODELS[g.model]?.slot ?? 0) % 8})` } }), MODELS[g.model]?.name || g.model),
        t ? h("a", { class: "fclip-go", href: hashOf(t) }, "Replay the trial →") : null)));
}

const outcomeOf = (g) => CAT.failures?.by_trial[g.uid] || g.mode;

function playWhenSeen(videos) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    for (const v of videos) v.controls = true;
    return;
  }
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) e.target.play().catch(() => {});
      else e.target.pause();
    }
  }, { threshold: 0.35 });
  for (const v of videos) io.observe(v);
}

function trialsSection() {
  const head = h("div", { class: "section-head", id: "trials", "data-nav": "Trials" }, h("h2", {}, "Every trial"), h("p", {}, resultsNote()));
  const ranOn = (driver, os) => osesOf(driver).some((o) => o.id === os);
  let osSel = store.get("cdb-os", CAT.oses[0]?.id);
  if (!OSES[osSel]) osSel = CAT.oses[0]?.id;
  if (!osesOf(VIEW.driver).length) VIEW.driver = CAT.driver;
  if (!ranOn(VIEW.driver, osSel)) osSel = osesOf(VIEW.driver)[0]?.id ?? osSel;
  const boardModels = CAT.models.filter((m) => m.board).map((m) => m.id);
  let shown = boardModels.slice();
  const gridHost = h("div");
  const controls = h("div", { class: "controls" });
  const groups = [];
  const sync = () => {
    for (const [g, cur] of groups) for (const b of g.children) b.setAttribute("aria-pressed", String(b.dataset.id === cur()));
    gridHost.replaceChildren(boardGrid(osSel, shown, VIEW.driver));
  };
  const group = (label, items, cur, onpick, cls = "") => {
    const g = h("div", { class: `tabs ${cls}`, role: "group", "aria-label": label },
      items.map(([id, ...kids]) => h("button", { "data-id": id, onclick: () => { onpick(id); sync(); } }, ...kids)));
    groups.push([g, cur]);
    controls.append(g);
  };
  if (CAT.drivers.length > 1) {
    group("Driver", CAT.drivers.map((d) => [d.id, driverDot(d.id), d.name]), () => VIEW.driver, (id) => {
      VIEW.driver = id;
      if (!ranOn(id, osSel)) osSel = osesOf(id)[0].id;
    }, "drivers-tabs");
  }
  if (boardModels.length > 1) {
    const chips = h("div", { class: "tabs models", role: "group", "aria-label": "Models" });
    for (const mid of boardModels) {
      chips.append(h("button", { "aria-pressed": "true", onclick: (e) => {
        const on = shown.includes(mid);
        if (on && shown.length === 1) return;
        shown = on ? shown.filter((x) => x !== mid) : boardModels.filter((x) => x === mid || shown.includes(x));
        e.currentTarget.setAttribute("aria-pressed", String(!on));
        sync();
      } }, h("span", { class: "dot", style: { background: `var(--s${(MODELS[mid].slot ?? 0) % 8})` } }), MODELS[mid].name));
    }
    controls.append(chips);
  }
  if (CAT.oses.length > 1) {
    group("Operating system", CAT.oses.map((o) => [o.id, o.name]), () => osSel, (id) => {
      osSel = id;
      store.set("cdb-os", id);
      if (!ranOn(VIEW.driver, id)) VIEW.driver = CAT.driver;
    });
  }
  if (controls.children.length) head.append(controls);
  sync();
  return h("section", {}, head, gridHost);
}

function howSection() {
  return h("section", {},
    h("div", { class: "section-head" }, h("h2", {}, "How a trial is graded")),
    h("div", { class: "how" },
      h("article", {}, h("h3", {}, "Task"),
        h("p", {}, "trycua's evaluator for the task reads the files the apps left (the calendar, the workbook, the ledger, the cases) and runs weighted checks. The score is the share of points; the half holds only if every check passes.")),
      h("article", {}, h("h3", {}, "GUI only"),
        h("p", {}, "The sentinel's guard watches live for a terminal, a run dialog or a script, and a scan of the trajectory checks every tool call. Any way out of the GUI fails the trial.")),
      h("article", {}, h("h3", {}, "User undisturbed · background only"),
        h("ul", { class: "crit-list" }, CRIT.map((c) => h("li", {}, h("b", {}, c.short), " ", h("code", {}, c.id)))))));
}

function boardGrid(os, shown, driver) {
  const conds = CAT.conditions;
  const multi = shown.length > 1;
  const grid = h("div", { class: "board", style: { "--cols": conds.length } });
  grid.append(h("div", { class: "bh" }, h("b", {}, "Task")));
  for (const c of conds) grid.append(h("div", { class: "bh" }, h("b", {}, c.name), h("span", {}, c.short)));
  let fam = null;
  const fams = new Set(CAT.tasks.map((t) => t.family));
  for (const task of CAT.tasks) {
    const ts = CAT.trials.filter((t) => t.driver === driver && t.os === os && t.task === task.id && shown.includes(t.model));
    if (!ts.length) continue;
    if (fams.size > 1 && task.family !== fam) {
      fam = task.family;
      grid.append(h("div", { class: "fam" }, task.family_name || task.family));
    }
    grid.append(h("div", { class: "task-cell" },
      h("div", { class: "probe" }, (task.probe || task.id).replace("CDB-", "")),
      h("h3", {}, task.title),
      task.summary && h("p", {}, task.summary),
      (task.apps || []).length ? h("div", { class: "apps" }, task.apps.map((a) => h("span", { class: "app" }, a))) : null));
    for (const c of conds) {
      const cell = h("div", { class: "cond-cell", "data-cond": `${c.name} · ${c.short}` });
      let any = false;
      for (const mid of shown) {
        const runs = ts.filter((t) => t.condition === c.id && t.model === mid);
        if (!runs.length) continue;
        any = true;
        cell.append(cellBlock(runs, multi));
      }
      const lost = missingOf(driver, os, task.id, c.id, shown);
      if (!any && !lost) cell.append(h("div", { class: "empty-cell" }, task.conditions.includes(c.id) ? "No trial." : onlyIn(task)));
      if (lost) cell.append(h("div", { class: "caveat" }, h("b", {}, "Incomplete"),
        ` ${lost} trial${lost > 1 ? "s" : ""} missing: infrastructure cut ${lost > 1 ? "them" : "it"} short past the re-runs, so this isn't ranked.`));
      const cv = caveatOf(os, c.id, task.id);
      if (cv) cell.append(h("div", { class: "caveat" }, h("b", {}, cv.short), " ", cv.reason));
      grid.append(cell);
    }
  }
  return grid;
}

function missingOf(driver, os, task, cond, models) {
  const runs = new Set(CAT.trials.filter((t) => t.driver === driver && models.includes(t.model)).map((t) => t.run));
  return (CAT.missing || []).filter((x) => x.driver === driver && x.os === os && x.task === task && x.condition === cond && runs.has(x.run)).length;
}

function compareView() {
  const host = h("div", { class: "compare", role: "region", "aria-label": "Compare drivers" });
  const pick = () => {
    const all = CAT.comparisons;
    const want = VIEW.compare || {};
    return all.find((c) => c.os === want.os && c.model === want.model) || all.find((c) => c.os === want.os) || all[0];
  };
  const select = (patch) => {
    const cur = pick();
    VIEW.compare = { os: cur.os, model: cur.model, ...patch };
    const next = pick();
    VIEW.compare = { os: next.os, model: next.model };
    if (location.hash.startsWith("#/drivers")) history.replaceState(null, "", `#/drivers/${enc(next.os)}/${enc(next.model)}`);
    render();
  };
  const render = () => {
    const c = pick();
    host.replaceChildren(compareHead(c, select), compareGrid(c), ...compareWhy(c), compareFoot(c));
  };
  render();
  return host;
}

function compareHead(c, select) {
  const oses = [...new Set(CAT.comparisons.map((x) => x.os))];
  const models = CAT.comparisons.filter((x) => x.os === c.os).map((x) => x.model);
  const tabs = (label, ids, cur, name, patch) => h("div", { class: "tabs", role: "group", "aria-label": label },
    ids.map((id) => h("button", { "aria-pressed": String(id === cur), onclick: () => select(patch(id)) }, name(id))));
  const n = Math.round(Math.max(...c.drivers.map((d) => (d.foreground || d.background).n / c.tasks.length)));
  return h("div", { class: "cmp-head" },
    h("div", { class: "cmp-row" },
      h("span", { class: "cmp-k" }, h("span", { html: ICON_LOCK, "aria-hidden": "true", style: { display: "inline-flex" } }), "Held fixed"),
      h("div", { class: "cmp-pick" }, h("small", {}, "OS"), tabs("Operating system", oses, c.os, (id) => OSES[id]?.name || id, (id) => ({ os: id }))),
      h("div", { class: "cmp-pick" }, h("small", {}, "Model"), tabs("Model", models, c.model, (id) => MODELS[id]?.name || id, (id) => ({ model: id }))),
      h("span", { class: "cmp-scope" }, `${c.tasks.length} task${c.tasks.length === 1 ? "" : "s"}${c.tasks.length < c.of ? ` of ${c.of}` : ""} · ${n} run${n === 1 ? "" : "s"} each · same seeds, prompts and grade`)),
    h("div", { class: "cmp-row" },
      h("span", { class: "cmp-k" }, "Compared"),
      h("div", { class: "cmp-drivers" }, c.drivers.map((d) => h("span", { class: "dchip" }, driverDot(d.id), driverName(d.id))))));
}

const cellRuns = (c, driver, task, cond) => CAT.trials.filter((t) => t.driver === driver && t.os === c.os && t.model === c.model && t.task === task && t.condition === cond);
const meanOf = (xs) => { xs = xs.filter((v) => v != null); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; };
const tone = (k, n) => (!n ? "na" : k === n ? "ok" : k ? "mid" : "no");

function rank(results) {
  const key = (r) => (r && r.n ? [r.k / r.n, r.score ?? -1] : null);
  const keys = results.map(key);
  const top = keys.filter(Boolean).reduce((a, b) => (!a || b[0] > a[0] || (b[0] === a[0] && b[1] > a[1]) ? b : a), null);
  const same = (k) => k && top && Math.abs(k[0] - top[0]) < 1e-9 && Math.abs(k[1] - top[1]) < 1e-9;
  const lead = keys.map(same);
  return lead.every((x, i) => x || !keys[i]) ? keys.map(() => false) : lead;
}

function compareGrid(c) {
  const conds = CAT.conditions.filter((k) => c.drivers.some((d) => d[k.id]));
  const grid = h("div", { class: "cmp-grid" });
  grid.append(h("div", { class: "ch" }, "Task"), h("div", { class: "ch" }, "Driver"),
    ...conds.map((k) => h("div", { class: "ch cond" }, h("b", {}, k.name), h("span", {}, k.short))));
  const fams = new Set(CAT.tasks.map((t) => t.family));
  let fam = null;
  const ran = CAT.tasks.filter((t) => c.drivers.some((d) => conds.some((k) => cellRuns(c, d.id, t.id, k.id).length)));
  for (const task of ran) {
    if (fams.size > 1 && task.family !== fam) {
      fam = task.family;
      grid.append(h("div", { class: "fam" }, task.family_name || task.family));
    }
    const inTotals = c.tasks.includes(task.id);
    const cvs = conds.map((k) => [k, caveatOf(c.os, k.id, task.id)]).filter(([, cv]) => cv);
    grid.append(h("div", { class: `ct${inTotals ? "" : " out"}`, style: { gridRow: `span ${c.drivers.length}` } },
      h("div", { class: "probe" }, (task.probe || task.id).replace("CDB-", "")),
      h("h3", {}, task.title),
      cvs.map(([k, cv]) => h("p", { class: "ct-note cv", title: cv.reason }, `${cv.mark} ${k.name}: ${cv.short.toLowerCase()}`)),
      inTotals ? null : h("p", { class: "ct-note" }, "Not in the totals: not every driver has it in both conditions yet.")));
    const results = Object.fromEntries(conds.map((k) => [k.id, c.drivers.map((d) => {
      const runs = cellRuns(c, d.id, task.id, k.id);
      return runs.length ? { runs, k: runs.filter((t) => t.passed).length, n: runs.length, score: meanOf(runs.map((t) => t.grade?.task?.score)) } : null;
    })]));
    const leads = Object.fromEntries(conds.map((k) => [k.id, rank(results[k.id])]));
    c.drivers.forEach((d, i) => {
      const first = i === 0 ? " first" : "";
      grid.append(h("div", { class: `cd${first}`, title: driverName(d.id) }, driverDot(d.id), h("span", {}, driverLabel(d.id))));
      for (const k of conds) {
        const lost = missingOf(d.id, c.os, task.id, k.id, [c.model]);
        grid.append(cmpCell(results[k.id][i], leads[k.id][i], lost, d.id, first, !d[k.id] ? ranOnly(d) : task.conditions.includes(k.id) ? null : onlyIn(task)));
      }
    });
  }
  grid.append(...totalsRows(c, conds));
  return grid;
}

/** What a comparison's driver that didn't run every condition says in the cells of the others: "Foreground only". */
const ranOnly = (d) => `${CAT.conditions.filter((k) => d[k.id]).map((k) => k.name).join(" and ")} only`;

function cmpCell(r, lead, lost, driver, first, only) {
  const style = { "--dc": `var(--s${(DRIVERS[driver]?.slot ?? 0) % 8})` };
  if (!r) return h("div", { class: `cc empty${first}`, style }, lost ? `${lost} missing` : only || "Not run");
  const rep = r.runs.slice().sort((a, b) => (b.grade?.task?.score ?? -1) - (a.grade?.task?.score ?? -1))[0];
  const runName = (t) => (t.run_index != null ? `Run ${t.run_index}` : `#${t.nth}`);
  return h("div", { class: `cc${lead ? " lead" : ""}${first}`, style },
    h("a", { class: `pc ${tone(r.k, r.n)}`, href: hashOf(rep), title: `${r.k} of ${r.n} runs pass. Replay ${r.n > 1 ? "the best run, " : ""}${runName(rep).toLowerCase()}` },
      h("b", {}, `${r.k}/${r.n}`), h("span", {}, "pass")),
    h("span", { class: "pips" }, r.runs.map((t) => h("a", { class: `pip ${t.passed ? "ok" : "no"}`, href: hashOf(t),
      title: `${runName(t)}: ${t.passed ? "pass" : "fail"}, ${pct(t.grade?.task?.score)} task score`,
      "aria-label": `${runName(t)}, ${t.passed ? "pass" : "fail"}, ${pct(t.grade?.task?.score)} task score: replay` }))),
    h("span", { class: "sc", title: "Mean task score" }, h("span", { class: "bar" }, h("i", { style: { width: pct(r.score ?? 0) } })), h("b", {}, pct(r.score))),
    lead ? h("span", { class: "lead-tag" }, "Best") : null,
    lost ? h("span", { class: "miss", title: `${lost} trial${lost > 1 ? "s" : ""} missing: infrastructure cut ${lost > 1 ? "them" : "it"} short past the re-runs` }, `+${lost} missing`) : null);
}

function totalsRows(c, conds) {
  const base = c.drivers.find((d) => d.id === CAT.driver) || c.drivers[0];
  const out = [h("div", { class: "ct total", style: { gridRow: `span ${c.drivers.length}` } },
    h("div", { class: "probe" }, "Totals"),
    h("h3", {}, c.tasks.length < c.of ? `The ${c.tasks.length} tasks every driver ran` : `All ${c.tasks.length} tasks`),
    h("p", { class: "ct-note" }, "Full pass and mean task score over the same tasks, so the rows compare like with like."))];
  const leads = Object.fromEntries(conds.map((k) => [k.id, rank(c.drivers.map((d) => (d[k.id] ? { k: d[k.id].passed, n: d[k.id].n, score: d[k.id].score } : null)))]));
  c.drivers.forEach((d, i) => {
    const first = i === 0 ? " first" : "";
    const style = { "--dc": `var(--s${(DRIVERS[d.id]?.slot ?? 0) % 8})` };
    out.push(h("div", { class: `cd total${first}`, title: driverName(d.id) }, driverDot(d.id), h("span", {}, driverLabel(d.id))));
    for (const k of conds) {
      const v = d[k.id];
      if (!v) {
        out.push(h("div", { class: `cc total empty${first}`, style }, ranOnly(d)));
        continue;
      }
      const delta = (a, b) => {
        if (d.id === base.id || a == null || b == null) return null;
        const pts = Math.round(100 * a) - Math.round(100 * b);
        return h("span", { class: `delta ${pts > 0 ? "up" : pts < 0 ? "down" : "flat"}` }, pts > 0 ? "▲ " : pts < 0 ? "▼ " : "", `${pts > 0 ? "+" : pts < 0 ? "−" : "±"}${Math.abs(pts)} pts`);
      };
      out.push(h("div", { class: `cc total${leads[k.id][i] ? " lead" : ""}${first}`, style },
        h("div", { class: "tl" }, h("b", { class: "big" }, pct(v.pass)), h("span", {}, "full pass"), delta(v.pass, base[k.id]?.pass)),
        h("div", { class: "tl sub" }, h("span", { class: `pc ${tone(v.passed, v.n)}` }, h("b", {}, `${v.passed}/${v.n}`), h("span", {}, "trials")),
          h("span", {}, `${pct(v.score)} task score`), delta(v.score, base[k.id]?.score)),
        leads[k.id][i] ? h("span", { class: "lead-tag" }, "Best") : null));
    }
  });
  return out;
}

/** The config's account of why two drivers differ on this OS, when both are in the comparison: each point with the
 * trials that show it, whatever the model held fixed. */
function compareWhy(c) {
  const ids = c.drivers.map((d) => d.id);
  const notes = (CAT.driver_why || []).filter((w) => w.os === c.os && w.drivers.every((d) => ids.includes(d)));
  return notes.map((w) => h("div", { class: "cmp-why" },
    h("h3", {}, w.title),
    h("p", { class: "why-lead" }, w.lead),
    h("ul", {}, w.points.map((p) => h("li", {}, h("b", {}, p.head), " ", codeText(p.text),
      p.examples.length ? h("span", { class: "why-ex" }, " Replay ", p.examples.map((uid, i) => {
        const t = CAT.trials.find((x) => x.uid === uid);
        return t ? [i ? " · " : "", h("a", { href: hashOf(t) }, `${probeOf(t.task)} ${t.condition} r${t.run_index ?? t.nth}, ${driverLabel(t.driver)}, ${t.model_name}`)] : null;
      }), ".") : null)))));
}

/** Text with `code` spans, as the config writes tool and field names. */
const codeText = (s) => s.split("`").map((part, i) => (i % 2 ? h("code", {}, part) : part));

function compareFoot(c) {
  const used = [...new Map(c.tasks.flatMap((t) => CAT.conditions.map((k) => caveatOf(c.os, k.id, t))).filter(Boolean).map((cv) => [cv.mark, cv])).values()];
  const base = driverName(c.drivers.some((d) => d.id === CAT.driver) ? CAT.driver : c.drivers[0].id);
  return h("div", { class: "cmp-foot" },
    h("p", {}, h("b", {}, "Reading it. "), "Each cell is one driver on one task in one condition: how many of its runs passed every half of the grade, a square per run (each opens its replay), and the mean task score. ",
      h("span", { class: "lead-tag" }, "Best"), " marks the driver with the most passes there, then the higher task score, and each driver tied with it; when all of them tie, none. The totals' arrows compare each driver with ", base, "."),
    used.map((cv) => h("p", {}, h("b", {}, `${cv.mark} ${cv.short}. `), cv.reason)));
}

function rate(runs, f) {
  const xs = runs.map(f).filter((v) => v != null);
  return xs.length ? { k: xs.filter(Boolean).length, n: xs.length } : null;
}

function cellBlock(runs, multi) {
  const scores = runs.map((t) => t.grade?.task?.score).filter((v) => v != null);
  const mean = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  const rep = runs.slice().sort((a, b) => (b.grade?.task?.score ?? -1) - (a.grade?.task?.score ?? -1))[0];
  const bg = runs[0].condition === "background";
  const passed = runs.filter((t) => t.passed).length;
  const one = runs.length === 1;
  const bdg = (r, label) => {
    if (!r) return badge(null, label);
    if (one) return badge(r.k === 1, label);
    return h("span", { class: `badge ${r.k === r.n ? "ok" : r.k === 0 ? "no" : "mid"}` }, h("i", {}, `${r.k}/${r.n}`), label);
  };
  return h("div", { class: "mblock" },
    h("a", { class: "thumb", href: hashOf(rep), title: `Replay ${one ? "" : "the best run, "}${rep.key}` },
      rep.poster && h("img", { src: rep.poster, alt: "", loading: "lazy" }),
      bg && userBox("ubox"),
      h("span", { class: "play" }, "▶ ", mins(rep.duration))),
    h("div", { class: "tmeta" },
      multi && h("div", { class: "tmodel" }, h("span", { class: "dot", style: { background: `var(--s${(MODELS[runs[0].model]?.slot ?? 0) % 8})` } }), runs[0].model_name),
      h("div", { class: "tscore" }, h("b", {}, pct(mean)), one ? "task score" : `mean task score · ${runs.length} runs`),
      h("div", { class: "badges" },
        bdg(rate(runs, (t) => t.grade?.task?.result), "Task"),
        bdg(rate(runs, (t) => t.grade?.gui_only?.result), "GUI only"),
        bg && bdg(rate(runs, (t) => t.grade?.user_undisturbed ? t.grade.user_undisturbed.result : null), "User undisturbed")),
      one ? verdict(runs[0]) : h("div", { class: "runs" },
        h("span", { class: `verdict ${passed ? (passed === runs.length ? "pass" : "some") : "fail"}` }, `${passed}/${runs.length} pass`),
        runs.map((t) => h("a", { class: `run ${t.passed ? "ok" : "no"}`, href: hashOf(t), title: `Run ${t.run_index ?? t.nth}${t.seed != null ? ` · seed ${t.seed}` : ""}: ${pct(t.grade?.task?.score)} task score, ${t.passed ? "pass" : "fail"}` },
          t.run_index != null ? `r${t.run_index}` : `#${t.nth}`, h("i", {}, pct(t.grade?.task?.score)))))));
}

function picker(label, value, options, onchange) {
  const opt = ([v, text]) => h("option", { value: v, selected: v === value }, text);
  const groups = [];
  for (const o of options) {
    const g = o[2] || "";
    if (!groups.length || groups[groups.length - 1][0] !== g) groups.push([g, []]);
    groups[groups.length - 1][1].push(o);
  }
  const kids = groups.length > 1 ? groups.map(([g, os]) => h("optgroup", { label: g }, os.map(opt))) : options.map(opt);
  const sel = h("select", { "aria-label": label, onchange: (e) => onchange(e.target.value) }, kids);
  return h("label", { class: "pick" }, h("small", {}, label), sel);
}

function crumbs(t) {
  const all = CAT.trials;
  const go = (patch) => { location.hash = hashOf(best({ driver: t.driver, os: t.os, task: t.task, condition: t.condition, model: t.model, run: t.run_index, ...patch })); };
  const uniq = (xs) => [...new Set(xs)];
  const oses = uniq(all.map((x) => x.os));
  const tasks = uniq(all.filter((x) => x.os === t.os).map((x) => x.task));
  const conds = uniq(all.filter((x) => x.os === t.os && x.task === t.task).map((x) => x.condition));
  const models = uniq(all.filter((x) => x.os === t.os && x.task === t.task && x.condition === t.condition).map((x) => x.model));
  const drivers = uniq(all.filter((x) => x.os === t.os && x.task === t.task && x.condition === t.condition && x.model === t.model).map((x) => x.driver));
  const runs = all.filter((x) => sameCell(x, t));
  const order = (ids, ref) => ids.sort((a, b) => ref.findIndex((r) => r.id === a) - ref.findIndex((r) => r.id === b));
  return h("div", { class: "crumbs" },
    h("a", { class: "back", href: "#/" }, "← All trials"),
    picker("OS", t.os, order(oses, CAT.oses).map((o) => [o, OSES[o]?.name || o]), (v) => go({ os: v })),
    picker("Task", t.task, order(tasks, CAT.tasks).map((k) => [k, `${(TASKS[k]?.probe || k).replace("CDB-", "")} · ${TASKS[k]?.title || k}`, TASKS[k]?.family_name]), (v) => go({ task: v })),
    picker("Condition", t.condition, order(conds, CAT.conditions).map((k) => [k, CONDS[k]?.name || k]), (v) => go({ condition: v })),
    picker("Model", t.model, order(models, CAT.models).map((k) => [k, MODELS[k]?.name || k]), (v) => go({ model: v })),
    CAT.drivers.length > 1 && picker("Driver", t.driver, order(drivers, CAT.drivers).map((k) => [k, driverName(k)]), (v) => go({ driver: v })),
    runs.length > 1 && picker("Run", t.key, runs.map((r) => [r.key, `${r.run_index != null ? `Run ${r.run_index}` : `#${r.nth}`} · ${pct(r.grade?.task?.score)} · ${r.passed ? "pass" : "fail"}${r.seed != null ? ` · seed ${r.seed}` : ""}`]), (v) => go({ key: v })));
}

function trialView(t) {
  const task = TASKS[t.task] || { title: t.task };
  const cond = CONDS[t.condition] || { name: t.condition };
  document.title = `${task.title} · ${cond.name} · ${t.model_name}${t.driver === CAT.driver ? "" : ` · ${driverName(t.driver)}`}`;
  VIEW.board = false;
  VIEW.driver = t.driver;
  const app = $("#app");
  const wrap = h("div", { class: "wrap replay" });
  wrap.append(crumbs(t));
  wrap.append(h("div", { class: "rtitle" },
    h("span", { class: `cond-chip ${t.condition}` }, cond.name),
    h("h1", {}, task.title),
    h("p", { class: "sub" }, cond.detail || "", " ", h("span", { style: { color: "var(--ink-3)" } }, `${t.model_name} through ${driverName(t.driver)} · ${OSES[t.os]?.name || t.os}${OSES[t.os]?.detail ? " (" + OSES[t.os].detail + ")" : ""}`))));
  const player = h("div", { class: "player" },
    h("div", { class: "screen" }, h("div", { class: "stage" }), h("div", { class: "nowbar" })),
    h("div", { class: "transport" }), h("div", { class: "userbar" }), h("aside", { class: "lane" }));
  wrap.append(player);
  wrap.append(gradeSection(t));
  wrap.append(askSection(t, task, cond));
  app.replaceChildren(wrap);
  window.scrollTo(0, 0);
  fetch(t.timeline).then((r) => r.json()).then((tl) => {
    if (!document.body.contains(player)) return;
    PLAYER = createPlayer(player, t, tl);
  }).catch(() => player.replaceChildren(h("div", { class: "loading" }, "Could not load this trial's timeline.")));
}

function mark(ok) {
  return h("span", { class: `mark ${ok == null ? "na" : ok ? "ok" : "no"}` }, ok == null ? "–" : ok ? "✓" : "✗");
}

function gradeSection(t) {
  const g = t.grade || {};
  const task = TASKS[t.task] || {};
  const checks = task.checks || {};
  const names = [...Object.keys(checks), ...Object.keys(g.task?.checks || {}).filter((k) => !(k in checks))];
  const passedW = names.reduce((s, k) => s + (g.task?.checks?.[k] === true ? (checks[k]?.[0] || 0) : 0), 0);
  const totalW = names.reduce((s, k) => s + (checks[k]?.[0] || 0), 0);
  const nPass = names.filter((k) => g.task?.checks?.[k] === true).length;
  const taskCard = h("article", { class: "gcard" },
    h("h3", {}, mark(g.task?.result), "Task"),
    h("p", { class: "gsub" }, "trycua's evaluator: weighted checks on the files the apps left."),
    h("div", { class: "gbig" }, pct(g.task?.score)),
    h("div", { class: "bar" }, h("i", { style: { width: pct(g.task?.score || 0) } })),
    h("p", { class: "gsub", style: { margin: "4px 0 0" } }, `${nPass} of ${names.length} checks · ${totalW ? `${passedW} of ${totalW} points` : ""}`),
    h("ul", { class: "checks" }, names.map((k) => {
      const v = g.task?.checks?.[k];
      const cls = v === true ? "ok" : v === false ? "no" : "na";
      return h("li", { class: cls }, h("span", { class: "s" }, v === true ? "✓" : v === false ? "✗" : "–"),
        h("span", {}, checks[k]?.[1] || k, h("code", {}, k)), h("span", { class: "w" }, checks[k] ? `${checks[k][0]} pts` : ""));
    })));
  const gu = g.gui_only;
  const guiCard = h("article", { class: "gcard" },
    h("h3", {}, mark(gu?.result), "GUI only"),
    h("p", { class: "gsub" }, "No way out of the GUI, live or in the agent's tool calls."),
    gu ? h("ul", { class: "checks" },
      gu.live && h("li", { class: gu.violations.some((v) => !v.startsWith("builtin:")) ? "no" : "ok" }, h("span", { class: "s" }, gu.violations.some((v) => !v.startsWith("builtin:")) ? "✗" : "✓"), h("span", {}, "Live guard: no terminal, run dialog or script in front")),
      gu.trajectory && h("li", { class: gu.result ? "ok" : "no" }, h("span", { class: "s" }, gu.result ? "✓" : "✗"), h("span", {}, `Trajectory scan: only ${driverName(t.driver)}'s tools`)),
      gu.violations.map((v) => h("li", { class: "no" }, h("span", { class: "s" }, "✗"), h("span", {}, "Violation", h("code", {}, v)))),
      gu.transient.map((v) => h("li", { class: "na" }, h("span", { class: "s" }, "!"), h("span", {}, "Briefly in front", h("code", {}, v)))),
      Object.entries(gu.refused || {}).map(([k, n]) => h("li", { class: "na" }, h("span", { class: "s" }, "·"), h("span", {}, `Refused by the harness, never ran: ${k}${n > 1 ? ` ×${n}` : ""}`)))) : h("p", { class: "gsub" }, "Not graded."),
    g.sentinel && h("p", { class: "gsub", style: { margin: "12px 0 0" } }, g.sentinel.result ? "✓ The sentinel's log covers the whole trial." : `✗ The sentinel's log is incomplete: ${g.sentinel.problems.join("; ")}`));
  const u = g.user_undisturbed;
  const userCard = h("article", { class: "gcard" },
    h("h3", {}, mark(t.condition === "background" ? (u ? u.result : null) : null), "User undisturbed"),
    t.condition !== "background"
      ? h("p", { class: "gsub" }, "Graded in the background condition only. Here the agent owns the desktop.")
      : u ? [h("p", { class: "gsub" }, "trycua's A22: the user could have kept working, undisturbed. All eight must hold."),
        h("ul", { class: "checks" }, CRIT.map((c) => {
          const v = u.criteria[c.id];
          const cls = v === true ? "ok" : v === false ? "no" : "na";
          return h("li", { class: cls }, h("span", { class: "s" }, v === true ? "✓" : v === false ? "✗" : "–"),
            h("span", {}, v === false ? `${c.short}: ${c.broken}` : `${c.short}: ${c.held}`, h("code", {}, c.id)), h("span", { class: "w" }, ""));
        })),
        u.close_refused ? h("p", { class: "gsub", style: { margin: "8px 0 0" } }, `✗ Something tried to close the user's window ${u.close_refused}×.`) : null]
      : h("p", { class: "gsub" }, "Not graded for this trial."));
  const facts = h("article", { class: "gcard" },
    h("h3", {}, "Run"),
    h("dl", { class: "kv" },
      h("dt", {}, "Model"), h("dd", {}, t.model_name),
      h("dt", {}, "Driver"), h("dd", {}, driverName(t.driver)),
      h("dt", {}, "Harness"), h("dd", {}, `${t.harness || "–"} ${t.harness_version || ""}`),
      h("dt", {}, "Effort"), h("dd", {}, t.effort || (t.harness === "claude-code" ? "medium (Claude Code's default)" : "–")),
      h("dt", {}, "Computer"), h("dd", {}, t.computer || "–"),
      h("dt", {}, "Turns"), h("dd", {}, t.turns ?? "–"),
      h("dt", {}, "Tool calls"), h("dd", {}, `${t.tool_calls ?? "–"}${t.tool_errors ? ` · ${t.tool_errors} errors` : ""}`),
      h("dt", {}, "Agent time"), h("dd", {}, mins(t.duration)),
      h("dt", {}, "Cost"), h("dd", {}, t.cost == null ? "–" : `$${t.cost.toFixed(2)}`),
      h("dt", {}, "Ended"), h("dd", {}, t.ending || "–"),
      h("dt", {}, "Reward"), h("dd", {}, t.reward ?? "–"),
      h("dt", {}, "Trial"), h("dd", { class: "mono", style: { fontSize: "11.5px" } }, t.id)));
  const cards = h("div", { class: "gcards" }, taskCard, guiCard, userCard, facts);
  const veil = h("div", { class: "veil" }, h("div", {}, h("p", {}, "The grade appears when the replay reaches the end."),
    h("button", { class: "btn", onclick: () => revealGrade(sec) }, "Reveal now")));
  cards.append(veil);
  const sec = h("section", { class: "grade", id: "grade" },
    h("div", { class: "grade-head" }, h("h2", {}, "Grade"), h("span", { class: "gv", hidden: true }, verdict(t),
      h("span", { style: { color: "var(--ink-3)", fontSize: "13.5px", marginLeft: "8px" } }, whyLine(t)))),
    cards);
  return sec;
}

function revealGrade(sec) {
  sec = sec || $("#grade");
  if (!sec) return;
  sec.querySelector(".veil")?.remove();
  const gv = sec.querySelector(".gv");
  if (gv) gv.hidden = false;
}

function caveatOf(os, condition, task) {
  return (CAT.caveats || []).find((cv) => (cv.os == null || cv.os === os) && cv.condition === condition && cv.tasks.includes(task));
}

function onlyIn(task) {
  return `${CAT.conditions.filter((k) => task.conditions.includes(k.id)).map((k) => k.name).join(", ")} only`;
}

function whyLine(t) {
  const g = t.grade || {};
  const cv = caveatOf(t.os, t.condition, t.task);
  if (t.passed) return "Every half held.";
  if (cv && g.task?.result && (!g.gui_only || g.gui_only.result)) return `The task was done in the GUI, but the user was disturbed. ${cv.short}: ${cv.reason}`;
  const why = [];
  if (g.task && !g.task.result) why.push("the task checks failed");
  if (g.gui_only && !g.gui_only.result) why.push("it left the GUI");
  if (t.condition === "background" && g.user_undisturbed && !g.user_undisturbed.result) why.push("the user was disturbed");
  if (g.sentinel && !g.sentinel.result) why.push("the sentinel's log is incomplete");
  if (!why.length) why.push("a half of the grade is missing");
  const s = why.join(", ");
  return s.charAt(0).toUpperCase() + s.slice(1) + ".";
}

function askSection(t, task, cond) {
  const L = CAT.links || {};
  const body = h("div", { class: "body" });
  if (t.prompt) body.append(h("pre", {}, t.prompt));
  else {
    body.append(h("p", { style: { margin: "0 0 8px" } }, task.summary || ""));
    if (cond.detail) body.append(h("p", { style: { margin: "0 0 8px" } }, cond.detail));
    if (L.port) body.append(h("p", { style: { margin: 0, color: "var(--ink-3)", fontSize: "13px" } }, "The exact prompt (trycua's brief plus the condition's paragraph) and trycua's system prompt for Linux are in ",
      h("a", { href: `${L.port}/blob/main/tasks/${t.task}-${t.condition}.json`, target: "_blank", rel: "noopener" }, `tasks/${t.task}-${t.condition}.json`), "."));
  }
  return h("details", { class: "ask" }, h("summary", {}, "What the agent was asked", h("span", {}, `${(task.probe || t.task)} · ${t.condition}`)), body);
}

function once(el, key, fn) {
  if (el._k !== key) { el._k = key; fn(); }
}

function lowerBound(arr, t, key) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid][key] <= t) lo = mid + 1; else hi = mid; }
  return lo - 1;
}

function createPlayer(root, trial, tl) {
  const [SW, SH] = tl.screen || CAT.screen;
  const calls = tl.calls || [];
  const texts = tl.texts || [];
  const user = tl.user;
  const guard = tl.guard || [];
  const dur = tl.duration || 1;
  const armed = tl.armed || [0, dur];
  let end = armed[1] ?? dur;
  const critById = Object.fromEntries(CRIT.map((c) => [c.id, c]));
  const userEvents = (user?.events || []).filter((e) => e.c in critById || e.c === "close");
  const moments = [];
  for (const e of userEvents) {
    const last = moments[moments.length - 1];
    if (last && e.t - last.items[last.items.length - 1].t < 0.3) last.items.push(e); else moments.push({ t: e.t, items: [e] });
  }
  const pctX = (x) => `${(100 * x) / SW}%`;
  const pctY = (y) => `${(100 * y) / SH}%`;
  const listeners = [];
  const on = (el, ev, fn, opt) => { el.addEventListener(ev, fn, opt); listeners.push([el, ev, fn, opt]); };
  let destroyed = false, raf = 0, prevT = -1, curIdx = -2, endShown = false, endDismissed = false, lastUserScroll = -Infinity;
  let overlays = store.get("cdb-overlays", true);
  let speed = store.get("cdb-speed", 4);
  if (!SPEEDS.includes(speed)) speed = 4;

  const stage = root.querySelector(".stage");
  const video = h("video", { playsinline: true, muted: true, preload: "auto", poster: trial.poster || null, src: trial.video || trial.video_local || null, "aria-label": "Screen recording of the trial" });
  video.muted = true;
  let fellBack = false;
  video.addEventListener("error", () => {
    if (!fellBack && trial.video_local && video.currentSrc && !video.currentSrc.endsWith(trial.video_local)) {
      fellBack = true;
      video.src = trial.video_local;
    }
  });
  const ov = sv("svg", { class: "ov", viewBox: `0 0 ${SW} ${SH}`, preserveAspectRatio: "xMidYMid meet" });
  const winRect = sv("rect", { class: "wrect", rx: 3, visibility: "hidden" });
  ov.append(winRect);
  let uRect = null, uFill = null, uHalo = null;
  if (trial.condition === "background" && user !== undefined) {
    const [x, y, w, hh] = (user && user.frame) || CAT.user_frame;
    uFill = sv("rect", { class: "ufill", x, y, width: w, height: hh, rx: 4 });
    uHalo = sv("rect", { class: "urect-halo", x, y, width: w, height: hh, rx: 4 });
    uRect = sv("rect", { class: "urect", x, y, width: w, height: hh, rx: 4 });
    ov.append(uFill, uHalo, uRect);
  }
  const ovh = h("div", { class: "ovh" });
  const winTag = h("span", { class: "tag win", hidden: true });
  const uTag = uRect ? h("span", { class: "tag user", style: { left: pctX(((user && user.frame) || CAT.user_frame)[0]), top: pctY(((user && user.frame) || CAT.user_frame)[1]) } }) : null;
  const marker = h("div", { class: "marker", hidden: true }, h("i"), h("span", { class: "mtag" }));
  const hud = root.querySelector(".nowbar");
  hud.replaceChildren(h("div", { class: "who" }, h("span", { class: "dot agent" }), "AGENT", h("span", { class: "n" })), h("div", { class: "what" }, "Waiting for the agent's first call…"), h("div", { class: "err", hidden: true }));
  const speedTag = h("div", { class: "speed-tag" });
  const say = h("div", { class: "say", hidden: true });
  const bigplay = h("button", { class: "bigplay", hidden: true, "aria-label": "Play", html: ICON_PLAY });
  const endcard = h("div", { class: "endcard", hidden: true });
  ovh.append(winTag, ...(uTag ? [uTag] : []), marker, speedTag, say, bigplay, endcard);
  stage.replaceChildren(video, ov, ovh);

  const transport = root.querySelector(".transport");
  const pbtn = h("button", { class: "pbtn", "aria-label": "Play", html: ICON_PLAY });
  const speeds = h("div", { class: "speeds", role: "group", "aria-label": "Speed" }, SPEEDS.map((s) => h("button", { "aria-pressed": String(s === speed), "data-s": s }, `${s}×`)));
  const clock = h("div", { class: "clock" });
  const ovBtn = h("button", { class: "tbtn", "aria-pressed": String(overlays), title: "Show or hide the overlays on the video" }, "Overlays");
  const tools = h("div", { class: "tools" }, ovBtn);
  const timeline = buildTimeline();
  transport.replaceChildren(pbtn, speeds, tools, clock, timeline.el);

  const userbar = root.querySelector(".userbar");
  const ub = buildUserbar();
  const lane = root.querySelector(".lane");
  const ln = buildLane();

  function buildTimeline() {
    const W = 1000;
    const x = (t) => ((t / dur) * W).toFixed(2);
    const mk = (cls, label) => {
      const svg = sv("svg", { viewBox: `0 0 ${W} 26`, preserveAspectRatio: "none", "aria-hidden": "true" });
      svg.append(sv("rect", { class: "armed", x: x(armed[0] || 0), y: 0, width: Math.max(0, x(end) - x(armed[0] || 0)), height: 26 }));
      return { row: h("div", { class: `track ${cls}` }, h("span", {}, label), h("div", { style: { position: "relative" } }, svg)), svg };
    };
    const a = mk("agent", "AGENT");
    for (const c of calls) {
      const err = !!c.err;
      a.svg.append(sv("line", { class: `tick ${err ? "err" : c.kind}`, x1: x(c.t0), x2: x(c.t0), y1: err ? 3 : 7, y2: err ? 23 : 19 }));
    }
    for (const s of texts) a.svg.append(sv("line", { class: "tick say", x1: x(s.t), x2: x(s.t), y1: 1, y2: 5 }));
    for (const g of guard) a.svg.append(sv("line", { class: "tick guard", x1: x(g.t), x2: x(g.t), y1: 1, y2: 25 }));
    const rows = [a.row];
    if (trial.condition === "background") {
      const u = mk("user", "USER");
      if (user) {
        for (const t of user.typed) u.svg.append(sv("line", { class: "tick type", x1: x(t), x2: x(t), y1: 9, y2: 17 }));
        for (const t of user.blocked) u.svg.append(sv("line", { class: "tick blocked", x1: x(t), x2: x(t), y1: 4, y2: 22 }));
        for (const m of moments) u.svg.append(sv("line", { class: "tick dist", x1: x(m.t), x2: x(m.t), y1: 2, y2: 24 }));
      }
      if (!user) u.row.lastChild.append(h("span", { class: "tnote" }, "not recorded for this trial"));
      rows.push(u.row);
    }
    const head = h("div", { class: "phead" });
    const tip = h("div", { class: "ttip", hidden: true });
    const area = h("div", { style: { position: "absolute", top: 0, bottom: 0, right: 0, pointerEvents: "none" } }, head, tip);
    const el = h("div", { class: "timeline", role: "slider", tabindex: "0", "aria-label": "Seek", "aria-valuemin": "0", "aria-valuemax": String(Math.round(dur)) }, rows, area);
    const axis = h("div", {});
    const ticks = () => {
      const px = rows[0].lastChild.getBoundingClientRect().width || 600;
      const want = Math.max(2, Math.floor(px / 64));
      const step = [1, 2, 5, 10, 15, 30, 60, 120, 300].find((st) => dur / st <= want) || 600;
      axis.replaceChildren();
      for (let t = 0; t <= dur; t += step) axis.append(h("span", { style: { left: `${(100 * t) / dur}%` } }, fmt(t)));
    };
    const axisRow = h("div", { class: "tl-axis" }, h("span"), axis);
    const wrapEl = h("div", { style: { gridColumn: "1 / -1" } }, el, axisRow);
    const layout = () => {
      const lab = rows[0].firstChild.getBoundingClientRect().width;
      area.style.left = `${lab}px`;
      ticks();
    };
    requestAnimationFrame(layout);
    on(window, "resize", layout);
    const tAt = (ev) => {
      const r = rows[0].lastChild.getBoundingClientRect();
      return Math.min(dur, Math.max(0, ((ev.clientX - r.left) / r.width) * dur));
    };
    let drag = false;
    on(el, "pointerdown", (ev) => { drag = true; el.setPointerCapture(ev.pointerId); seek(tAt(ev)); });
    on(el, "pointermove", (ev) => {
      const t = tAt(ev);
      if (drag) seek(t);
      const near = nearest(t);
      if (near && ev.pointerType === "mouse") {
        tip.hidden = false;
        tip.textContent = near;
        tip.style.left = `${(100 * t) / dur}%`;
      }
    });
    on(el, "pointerup", () => { drag = false; });
    on(el, "pointerleave", () => { tip.hidden = true; });
    on(el, "keydown", (ev) => {
      if (ev.key === "ArrowRight") { stepCall(1); ev.preventDefault(); }
      if (ev.key === "ArrowLeft") { stepCall(-1); ev.preventDefault(); }
    });
    return { el: wrapEl, head, area };
  }

  function nearest(t) {
    const tol = dur * 0.012;
    let bestItem = null, bd = Infinity;
    for (const m of moments) { const d = Math.abs(m.t - t); if (d < tol && d < bd) { bd = d; bestItem = `${fmt(m.t)} · USER · ${m.items.map((e) => critById[e.c]?.short || "Close").join(", ")}: ${m.items[0].what}`; } }
    if (bestItem) return bestItem;
    for (const c of calls) { const d = Math.abs(c.t0 - t); if (d < tol && d < bd) { bd = d; bestItem = `${fmt(c.t0)} · ${c.verb}${c.obj ? " " + c.obj : ""}${c.err ? " ✗" : ""}`; } }
    return bestItem || fmt(t);
  }

  function buildUserbar() {
    if (trial.condition !== "background") {
      userbar.replaceChildren(h("div", { class: "ub-note" }, h("b", {}, "Foreground. "), "The agent owns the desktop; the bench's small witness window at the bottom right only watches, and its guard looks for any way out of the GUI.",
        guard.length ? h("span", { style: { color: "var(--bad-ink)" } }, ` The guard logged ${guard.length} event${guard.length > 1 ? "s" : ""}.`) : " The guard logged nothing."));
      return null;
    }
    if (!user) {
      const u = trial.grade?.user_undisturbed;
      userbar.replaceChildren(
        h("div", { class: "ub-top" }, h("span", { class: "ub-who" }, h("span", { class: "dot user" }), "USER · User activity"),
          h("span", { class: "ub-note" }, "This trial was exported without the sentinel's log, so the user's lane can't be replayed; the video still shows them typing in the outlined window. The eight criteria fill in from the grade at the end.")),
        h("div", { class: "crits" }, CRIT.map((c) => h("div", { class: "crit na", "data-c": c.id }, h("b", {}, h("i", {}, "–"), c.short), h("span", {}, c.held)))));
      return { final: true, crits: [...userbar.querySelectorAll(".crit")] };
    }
    const field = h("div", { class: "ub-field", title: "The user's text, as the simulated user typed it" }, h("span"), h("i"));
    const count = h("span", { class: "ub-count" });
    const crits = CRIT.map((c) => h("div", { class: "crit", title: `${c.id}: ${c.held}` }, h("b", {}, h("i", {}, "✓"), c.short), h("span", {}, c.held)));
    const last = h("div", { class: "ub-last" });
    userbar.replaceChildren(
      h("div", { class: "ub-top" }, h("span", { class: "ub-who" }, h("span", { class: "dot user" }), "USER · User activity"), field, count),
      h("div", { class: "crits" }, crits), last);
    return { field: field.firstChild, count, crits, last };
  }

  function buildLane() {
    const items = [];
    for (const c of calls) items.push({ t: c.t0, kind: "call", c });
    for (const s of texts) items.push({ t: s.t, kind: "say", s });
    for (const m of moments) items.push({ t: m.t, kind: "user", m });
    for (const g of guard) items.push({ t: g.t, kind: "guard", g });
    items.sort((a, b) => a.t - b.t || (a.kind === "call" ? 1 : -1));
    const list = h("ol", { class: "calls" });
    for (const it of items) {
      let el;
      if (it.kind === "call") {
        const c = it.c;
        el = h("li", { class: `call ${c.kind}${c.err ? " err" : ""}`, "data-i": c.i },
          h("span", { class: "t" }, fmt(c.t0)), h("span", { class: "k" }),
          h("div", {},
            h("div", { class: "l" }, h("b", {}, c.verb), c.obj ? h("span", { class: "o" }, " ", c.obj) : null, c.where ? h("span", { class: "w" }, " · ", c.where) : null),
            c.err ? h("div", { class: "e" }, c.err) : null,
            h("code", {}, c.tool)));
      } else if (it.kind === "say") {
        el = h("li", { class: "saying" }, h("span", { class: "t" }, fmt(it.t)), h("q", { "data-who": trial.model_name || "Agent" }, it.s.text));
      } else if (it.kind === "user") {
        const m = it.m;
        el = h("li", { class: "ev user-ev bad" }, h("span", { class: "t" }, fmt(m.t)),
          h("div", {}, h("b", {}, "USER · ", [...new Set(m.items.map((e) => critById[e.c]?.short || "Close"))].join(", ")), ": ", m.items[0].what, m.items.length > 1 ? ` (+${m.items.length - 1})` : ""));
      } else {
        el = h("li", { class: "ev" }, h("span", { class: "t" }, fmt(it.t)), h("div", {}, h("b", {}, it.g.violation ? "GUI-only violation: " : "Briefly in front: "), it.g.what));
      }
      el._t = it.t;
      on(el, "click", () => seek(Math.max(0, it.t - 0.25), true));
      it.el = el;
      list.append(el);
    }
    on(list, "wheel", () => { lastUserScroll = performance.now(); }, { passive: true });
    on(list, "touchmove", () => { lastUserScroll = performance.now(); }, { passive: true });
    const nErr = calls.filter((c) => c.err).length;
    const harness = trial.harness ? `${trial.harness}` : "";
    lane.replaceChildren(
      h("div", { class: "lane-head" }, h("div", { class: "who" }, h("span", { class: "dot agent" }), "AGENT"),
        h("div", { class: "m" }, `${trial.model_name}${harness ? " in " + harness : ""}`, h("span", { class: "via" }, ` · ${driverName(trial.driver)}`)),
        h("div", { class: "c" }, `${calls.length} tool calls${nErr ? ` · ${nErr} errors` : ""}${trial.turns ? ` · ${trial.turns} turns` : ""}${texts.length ? ` · ${texts.length} remarks` : ""}`)),
      h("div", { class: "lane-scroll" }, list));
    const callEls = Object.fromEntries(items.filter((it) => it.kind === "call").map((it) => [it.c.i, it.el]));
    return { list, items, callEls };
  }

  function setSpeed(s) {
    speed = s;
    store.set("cdb-speed", s);
    video.defaultPlaybackRate = s;
    video.playbackRate = s;
    for (const b of speeds.children) b.setAttribute("aria-pressed", String(+b.dataset.s === s));
    speedTag.textContent = `${s}× speed`;
  }

  function setOverlays(v) {
    overlays = v;
    store.set("cdb-overlays", v);
    ov.classList.toggle("off", !v);
    ovh.classList.toggle("off", !v);
    ovBtn.setAttribute("aria-pressed", String(v));
  }

  function seek(t, play) {
    prevT = -1;
    video.currentTime = Math.min(Math.max(0, t), Math.max(0, (video.duration || dur) - 0.05));
    if (t < end - 0.2) { endcard.hidden = true; endShown = false; endDismissed = false; }
    update(t, true);
    if (play && video.paused) video.play().catch(() => {});
  }

  function stepCall(d) {
    const t = video.currentTime;
    let i = lowerBound(calls, t + 0.01, "t0");
    i = Math.min(calls.length - 1, Math.max(0, i + (d > 0 ? 1 : (calls[i] && t - calls[i].t0 < 0.6 ? -1 : 0))));
    if (calls[i]) seek(Math.max(0, calls[i].t0 - 0.1));
  }

  function typedText(n) {
    const s = user.script || CAT.user_script || "";
    if (!s || n <= 0) return "";
    let out = s.repeat(Math.ceil(n / s.length)).slice(0, n);
    return out.length > 64 ? out.slice(-64) : out;
  }

  function showEnd() {
    if (endShown || endDismissed) return;
    endShown = true;
    revealGrade();
    const g = trial.grade || {};
    const u = g.user_undisturbed;
    const broken = u ? CRIT.filter((c) => u.criteria[c.id] === false) : [];
    const halves = [
      ["Task", g.task?.result, `trycua's evaluator · ${pct(g.task?.score)} of the points`, pct(g.task?.score)],
      ["GUI only", g.gui_only?.result, g.gui_only?.result ? "no way out of the GUI" : `violation: ${(g.gui_only?.violations || []).join(", ") || "see the grade"}`, ""],
    ];
    if (trial.condition === "background") halves.push(["User undisturbed", u ? u.result : null, u ? (broken.length ? `broken: ${broken.map((c) => c.short).join(", ")}` : "all eight criteria held") : "not graded", u ? `${8 - broken.length} of 8 held` : ""]);
    const card = h("div", { class: "card" },
      h("h2", {}, "The grade"),
      h("div", { class: "vline" }, h("span", { class: `big ${trial.passed ? "pass" : "fail"}` }, trial.passed ? "Pass" : "Fail"), h("span", { class: "why" }, whyLine(trial))),
      h("div", { class: "halves" }, halves.map(([name, ok, sub, val]) => h("div", { class: "half" },
        h("span", { class: `ic ${ok == null ? "na" : ok ? "ok" : "no"}` }, ok == null ? "–" : ok ? "✓" : "✗"),
        h("div", {}, h("b", {}, name), h("span", {}, sub)), h("em", {}, val)))),
      h("div", { class: "facts" }, [trial.model_name, driverName(trial.driver), `${trial.harness || ""} ${trial.harness_version || ""}`.trim(), trial.turns != null && `${trial.turns} turns`, trial.tool_calls != null && `${trial.tool_calls} tool calls`, mins(trial.duration), trial.cost != null && `$${trial.cost.toFixed(2)}`, trial.ending].filter(Boolean).join(" · ")),
      h("div", { class: "row" },
        h("button", { class: "btn primary", onclick: () => { endDismissed = false; seek(Math.max(0, (armed[0] || 0) - 0.5), true); } }, "↺ Replay"),
        h("button", { class: "btn", onclick: () => $("#grade")?.scrollIntoView({ behavior: "smooth" }) }, "Full grade ↓"),
        h("button", { class: "btn", onclick: () => { endcard.hidden = true; endDismissed = true; } }, "Hide")));
    endcard.replaceChildren(card);
    endcard.hidden = false;
  }

  function scrollList(el) {
    if (!el || performance.now() - lastUserScroll < 4000) return;
    const list = ln.list;
    const top = el.offsetTop - list.clientHeight * 0.32;
    list.scrollTo({ top: Math.max(0, top), behavior: Math.abs(list.scrollTop - top) > 1200 ? "auto" : "smooth" });
  }

  function update(t, jumped) {
    const playing = !video.paused;
    const i = lowerBound(calls, t, "t0");
    const c = calls[i];
    const next = calls[i + 1];
    if (i !== curIdx) {
      const old = ln.callEls[calls[curIdx]?.i];
      if (old) old.classList.remove("cur");
      const el = c && ln.callEls[c.i];
      if (el) el.classList.add("cur");
      for (const it of ln.items) it.el.classList.toggle("future", it.t > t + 0.001);
      scrollList(el || ln.items.find((it) => it.t > t)?.el);
      if (c && !jumped && i > curIdx && (c.pt || c.near)) {
        const r = h("span", { class: "ripple" });
        marker.append(r);
        setTimeout(() => r.remove(), 950);
      }
      curIdx = i;
    } else if (jumped || Math.floor(t * 2) !== Math.floor(prevT * 2)) {
      for (const it of ln.items) it.el.classList.toggle("future", it.t > t + 0.001);
    }
    const fresh = c && t - c.t0 < Math.max(3, Math.min(8, (next ? next.t0 : end) - c.t0));
    const p = c && (c.pt || c.near);
    if (fresh && p) {
      marker.hidden = false;
      marker.style.left = pctX(p[0]);
      marker.style.top = pctY(p[1]);
      marker.classList.toggle("err", !!c.err);
      marker.classList.toggle("kbd", !c.pt && !!c.near);
      marker.classList.toggle("flip", p[0] > SW * 0.72);
      once(marker.lastChild, c.i, () => { marker.lastChild.textContent = `${c.verb}${c.obj && c.obj.length < 34 ? " " + c.obj : ""}`; });
    } else marker.hidden = true;
    if (fresh && c.win && c.kind !== "setup") {
      const [x, y, w, hh] = c.win;
      const cx = Math.max(0, x), cy = Math.max(0, y);
      const cw = Math.min(SW, x + w) - cx, ch = Math.min(SH, y + hh) - cy;
      if (cw > 20 && ch > 20) {
        winRect.setAttribute("x", cx); winRect.setAttribute("y", cy); winRect.setAttribute("width", cw); winRect.setAttribute("height", ch);
        winRect.setAttribute("visibility", "visible");
        winTag.hidden = false;
        winTag.style.left = pctX(cx);
        winTag.style.top = pctY(cy);
        once(winTag, c.where, () => { winTag.textContent = `AGENT → ${c.where || "window"}`; });
      } else { winRect.setAttribute("visibility", "hidden"); winTag.hidden = true; }
    } else { winRect.setAttribute("visibility", "hidden"); winTag.hidden = true; }

    if (c) {
      const after = c.t1 ?? c.t0;
      const thinking = t - after > 1.6 && (!next || t < next.t0);
      hud.classList.toggle("thinking", thinking);
      const nEl = hud.querySelector(".n");
      once(nEl, c.i, () => { nEl.textContent = `call ${c.i + 1} of ${calls.length}${c.turn ? ` · turn ${c.turn}` : ""}`; });
      const what = hud.querySelector(".what");
      const errEl = hud.querySelector(".err");
      const mode = t >= end - 0.05 && trial.ending ? "end" : thinking ? `think${Math.round(t - after)}` : `call${c.i}`;
      once(what, mode, () => {
        if (mode === "end") { what.textContent = `Ended · ${trial.ending}`; errEl.hidden = true; }
        else if (thinking) { what.textContent = `Thinking · ${Math.round(t - after)} s`; errEl.hidden = true; }
        else {
          what.replaceChildren(c.verb, c.obj ? " " + c.obj : "", c.where ? h("span", {}, " · " + c.where) : "");
          errEl.hidden = !c.err;
          errEl.textContent = c.err ? `✗ ${c.err}` : "";
        }
      });
      hud.classList.toggle("bad", !!c.err && !thinking);
    }

    const si = lowerBound(texts, t, "t");
    const s = texts[si];
    if (s && t - s.t < 9 && (!texts[si + 1] || t < texts[si + 1].t)) {
      say.hidden = false;
      if (say._i !== si) { say.replaceChildren(h("b", {}, trial.model_name || "Agent"), `“${s.text.length > 220 ? s.text.slice(0, 219) + "…" : s.text}”`); say._i = si; }
    } else say.hidden = true;

    if (ub && ub.final) {
      const u = trial.grade?.user_undisturbed;
      const done = t >= end - 0.05;
      if (ub._done !== done) {
        CRIT.forEach((cr, k) => {
          const v = done ? u?.criteria?.[cr.id] : undefined;
          const el = ub.crits[k];
          el.className = `crit ${v === true ? "" : v === false ? "no" : "na"}`;
          el.firstChild.replaceChildren(h("i", {}, v === true ? "✓" : v === false ? "✗" : "–"), cr.short);
          el.lastChild.textContent = v === false ? cr.broken : cr.held;
        });
        ub._done = done;
      }
    }
    if (user && ub) {
      const n = lowerBound(user.typed.map((x) => ({ t: x })), t, "t") + 1;
      if (ub._n !== n) {
        ub.field.textContent = typedText(n);
        const nb = user.blocked.filter((x) => x <= t).length;
        ub.count.replaceChildren(h("b", {}, n), ` keystroke${n === 1 ? "" : "s"} landed`, nb ? h("span", { style: { color: "var(--bad-ink)" } }, ` · ${nb} blocked`) : "");
        ub._n = n;
      }
      const broken = new Set(userEvents.filter((e) => e.t <= t && e.c in critById).map((e) => e.c));
      const final = t >= end - 0.05 ? trial.grade?.user_undisturbed?.criteria : null;
      if (final) for (const [k, v] of Object.entries(final)) if (v === false) broken.add(k);
      const key = [...broken].sort().join(",");
      if (ub._key !== key) {
        CRIT.forEach((cr, k) => {
          const el = ub.crits[k];
          const no = broken.has(cr.id);
          if (no && !el.classList.contains("no") && playing && !jumped) { el.classList.remove("pulse"); void el.offsetWidth; el.classList.add("pulse"); }
          el.classList.toggle("no", no);
          el.firstChild.replaceChildren(h("i", {}, no ? "✗" : "✓"), cr.short);
          el.lastChild.textContent = no ? cr.broken : cr.held;
        });
        ub._key = key;
      }
      const mi = lowerBound(moments, t, "t");
      const m = moments[mi];
      const started = t >= (armed[0] ?? 0);
      once(ub.last, `${mi}|${started}`, () => ub.last.replaceChildren(m ? h("span", {}, h("b", {}, `${fmt(m.t)} · `), m.items.map((e) => e.what).filter((v, k, a) => a.indexOf(v) === k).slice(0, 3).join("; ")) : h("span", { style: { color: "var(--good-ink)" } }, started ? "Undisturbed so far: every keystroke landed." : "Waiting for the agent to start.")));
      const hurt = broken.size > 0;
      uRect.classList.toggle("hurt", hurt);
      uTag.classList.toggle("hurt", hurt);
      const recent = m && t - m.t < Math.max(1.6, 0.45 * speed);
      const label = recent ? `${critById[m.items[0].c]?.short || "Window"}: ${critById[m.items[0].c]?.broken || m.items[0].what}` : hurt ? `disturbed · ${broken.size} of 8 broken` : (started ? "typing · undisturbed" : "User activity");
      once(uTag, label, () => uTag.replaceChildren(h("b", {}, "USER"), " ", label));
      if (playing && !jumped && prevT >= 0 && t > prevT && t - prevT < 2 * speed) {
        for (const mm of moments) {
          if (mm.t > prevT && mm.t <= t) {
            for (const el of [uRect, uFill, uTag]) { el.classList.remove("flash"); void el.getBoundingClientRect(); el.classList.add("flash"); }
          }
        }
      }
    } else if (uRect && uTag) {
      const u = trial.grade?.user_undisturbed;
      const hurt = t >= end - 0.05 && u && !u.result;
      uRect.classList.toggle("hurt", !!hurt);
      uTag.classList.toggle("hurt", !!hurt);
      once(uTag, String(!!hurt), () => uTag.replaceChildren(h("b", {}, "USER"), " ", hurt ? "disturbed (from the grade)" : "User activity"));
    }

    timeline.head.style.left = `${(100 * t) / dur}%`;
    once(clock, fmt(t), () => clock.replaceChildren(h("b", {}, fmt(t)), ` / ${fmt(dur)}`));
    if (t >= end - 0.05 && (playing || jumped)) showEnd();
    prevT = t;
  }

  function loop() {
    if (destroyed) return;
    update(video.currentTime, false);
    if (!video.paused) raf = requestAnimationFrame(loop);
  }

  function syncButton() {
    const paused = video.paused;
    pbtn.innerHTML = paused ? ICON_PLAY : ICON_PAUSE;
    pbtn.setAttribute("aria-label", paused ? "Play" : "Pause");
    bigplay.hidden = !paused || endShown;
  }

  function toggle() {
    if (video.paused) {
      if (video.currentTime >= Math.min(video.duration || dur, end) - 0.1) seek(Math.max(0, (armed[0] || 0) - 0.5));
      video.play().catch(() => {});
    } else video.pause();
  }

  on(pbtn, "click", toggle);
  on(bigplay, "click", toggle);
  on(video, "click", toggle);
  on(speeds, "click", (e) => { const s = +e.target?.dataset?.s; if (s) setSpeed(s); });
  on(ovBtn, "click", () => setOverlays(!overlays));
  on(video, "play", () => { syncButton(); cancelAnimationFrame(raf); raf = requestAnimationFrame(loop); });
  on(video, "pause", () => { syncButton(); update(video.currentTime, true); });
  on(video, "seeked", () => update(video.currentTime, true));
  on(video, "timeupdate", () => { if (video.paused) update(video.currentTime, true); });
  on(video, "ended", () => { syncButton(); showEnd(); });
  on(video, "ratechange", () => { if (video.playbackRate !== speed) video.playbackRate = speed; });
  on(document, "keydown", (e) => {
    if (e.target.closest && e.target.closest("select, input, textarea")) return;
    if (e.key === " " || e.key === "k") { toggle(); e.preventDefault(); }
    else if (e.key === "ArrowRight" && e.target === document.body) { stepCall(1); e.preventDefault(); }
    else if (e.key === "ArrowLeft" && e.target === document.body) { stepCall(-1); e.preventDefault(); }
    else if (e.key === "Escape") { endcard.hidden = true; endDismissed = true; }
  });
  on(video, "loadedmetadata", () => {
    if (isFinite(video.duration) && video.duration > 1) end = Math.min(end, video.duration - 0.25);
    setSpeed(speed);
    const params = new URLSearchParams(location.search);
    const at = params.has("t") ? parseFloat(params.get("t")) : Math.max(0, (armed[0] || 0) - 0.5);
    video.currentTime = Math.min(at, (video.duration || dur) - 0.05);
    update(at, true);
    if (!params.has("paused")) video.play().then(syncButton).catch(() => { bigplay.hidden = false; });
    else syncButton();
  });

  setSpeed(speed);
  setOverlays(overlays);
  update(0, true);
  syncButton();
  if (!trial.video && !trial.video_local) stage.append(h("div", { class: "loading", style: { position: "absolute", inset: 0, color: "#fff" } }, "No recording for this trial."));

  return {
    destroy() {
      destroyed = true;
      cancelAnimationFrame(raf);
      for (const [el, ev, fn, opt] of listeners) el.removeEventListener(ev, fn, opt);
      video.pause();
      video.removeAttribute("src");
      video.load();
    },
    seek, video,
  };
}

boot();
