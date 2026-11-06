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
  const wrap = h("div", { class: "wrap" });
  wrap.append(landing());
  if ((CAT.pairs || []).length) wrap.append(pairsSection());
  wrap.append(resultsSection());
  if (CAT.comparisons.length) wrap.append(driversSection());
  wrap.append(trialsSection(), howSection());
  $("#app").replaceChildren(wrap);
}

function landing() {
  const hero = CAT.trials.find((t) => t.uid === CAT.hero);
  const models = CAT.models.filter((m) => m.board).map((m) => m.name);
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
    h("div", { class: "players" },
      h("div", { class: "player-card" }, h("h3", {}, h("span", { class: "dot agent" }), "The agent"),
        h("p", {}, `${models.join(", ") || "A model"} in the claude-code CLI. It reads windows and acts through its computer-use driver's tools: click, type, press a key, open a menu. No terminal, no scripts, no side doors.`)),
      h("div", { class: "player-card" }, h("h3", {}, h("span", { class: "dot user" }), "The user"),
        h("p", {}, "In the background condition a simulated user types into their own window, “User activity”, one character a second. A sentinel logs everything that reaches them.")),
      h("div", { class: "player-card" }, h("h3", {}, h("span", { class: "dot judge" }), "The grade"),
        h("p", {}, "Every half must hold: the task, by trycua's own evaluator; GUI only, no way out of the GUI; and in the background, the user undisturbed on all eight of trycua's criteria."))));
}

function pairsSection() {
  return h("section", { class: "pairs", "aria-labelledby": "pairs-h" },
    h("div", { class: "section-head", id: "pairs" }, h("h2", { id: "pairs-h" }, "The same task in both conditions"),
      h("p", {}, "One run of a task in the foreground, left, and in the background, right: the same model, driver, task and seed, at one speed.")),
    h("div", { class: "pair-list" }, CAT.pairs.map((p) => {
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
    })));
}

function figures(keys, alt) {
  return h("div", { class: "figs" }, keys.map((f) => h("div", { class: "fig" }, h("picture", {},
    h("source", { media: "(max-width: 480px) and (prefers-color-scheme: dark)", srcset: `figures/${f}-phone-dark.svg` }),
    h("source", { media: "(max-width: 480px)", srcset: `figures/${f}-phone.svg` }),
    h("source", { media: "(prefers-color-scheme: dark)", srcset: `figures/${f}-dark.svg` }),
    h("img", { src: `figures/${f}.svg`, alt: alt(f) })))));
}

function resultsSection() {
  const lines = CAT.models.filter((m) => m.board).length > 1 ? ", a line per model" : "";
  return h("section", { "aria-labelledby": "results-h" },
    h("div", { class: "section-head", id: "results" }, h("h2", { id: "results-h" }, "Results"),
      h("p", {}, `All through ${driverName(CAT.driver)}: a panel per OS${lines}.`)),
    figures(CAT.figures, (f) => (f === "task-score" ? "Task score by condition" : "Full pass by condition")));
}

function driversSection() {
  return h("section", { class: "drivers", "aria-labelledby": "drivers-h" },
    h("div", { class: "section-head", id: "drivers" }, h("h2", { id: "drivers-h" }, "Drivers"),
      h("p", {}, "The same OS, model and tasks; only the computer-use driver changes.")),
    h("div", { class: "dcards" }, CAT.drivers.map((d) => h("article", { class: "dcard", style: { "--dc": `var(--s${d.slot % 8})` } },
      h("h3", {}, h("span", { class: "dot" }), d.name),
      h("p", {}, d.detail || ""),
      h("div", { class: "apps" }, osesOf(d.id).map((o) => h("span", { class: "app" }, o.name)))))),
    h("p", { class: "dnote" }, "Every driver also serves AgentEnv's ", h("code", {}, "computer_*"),
      " tools, which the grader and the recordings use; no driver's agents here see them. cua-driver's first runs on ",
      "macOS and Linux, which offered seven of them too, are in the dataset but not here."),
    figures(CAT.driver_figures, (f) => (f.endsWith("task-score") ? "Task score by driver" : "Full pass by driver")),
    compareView());
}

function trialsSection() {
  const head = h("div", { class: "section-head", id: "trials" }, h("h2", {}, "Every trial"), h("p", {}, resultsNote()));
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
    host.replaceChildren(compareHead(c, select), compareGrid(c), compareFoot(c));
  };
  render();
  return host;
}

function compareHead(c, select) {
  const oses = [...new Set(CAT.comparisons.map((x) => x.os))];
  const models = CAT.comparisons.filter((x) => x.os === c.os).map((x) => x.model);
  const tabs = (label, ids, cur, name, patch) => h("div", { class: "tabs", role: "group", "aria-label": label },
    ids.map((id) => h("button", { "aria-pressed": String(id === cur), onclick: () => select(patch(id)) }, name(id))));
  const n = Math.round(Math.max(...c.drivers.map((d) => d.foreground.n / c.tasks.length)));
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
  const conds = CAT.conditions.filter((k) => c.drivers.every((d) => d[k.id]));
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
        grid.append(cmpCell(results[k.id][i], leads[k.id][i], lost, d.id, first, task.conditions.includes(k.id) ? null : onlyIn(task)));
      }
    });
  }
  grid.append(...totalsRows(c, conds));
  return grid;
}

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
  const leads = Object.fromEntries(conds.map((k) => [k.id, rank(c.drivers.map((d) => ({ k: d[k.id].passed, n: d[k.id].n, score: d[k.id].score })))]));
  c.drivers.forEach((d, i) => {
    const first = i === 0 ? " first" : "";
    const style = { "--dc": `var(--s${(DRIVERS[d.id]?.slot ?? 0) % 8})` };
    out.push(h("div", { class: `cd total${first}`, title: driverName(d.id) }, driverDot(d.id), h("span", {}, driverLabel(d.id))));
    for (const k of conds) {
      const v = d[k.id];
      const delta = (a, b) => {
        if (d.id === base.id || a == null || b == null) return null;
        const pts = Math.round(100 * a) - Math.round(100 * b);
        return h("span", { class: `delta ${pts > 0 ? "up" : pts < 0 ? "down" : "flat"}` }, pts > 0 ? "▲ " : pts < 0 ? "▼ " : "", `${pts > 0 ? "+" : pts < 0 ? "−" : "±"}${Math.abs(pts)} pts`);
      };
      out.push(h("div", { class: `cc total${leads[k.id][i] ? " lead" : ""}${first}`, style },
        h("div", { class: "tl" }, h("b", { class: "big" }, pct(v.pass)), h("span", {}, "full pass"), delta(v.pass, base[k.id].pass)),
        h("div", { class: "tl sub" }, h("span", { class: `pc ${tone(v.passed, v.n)}` }, h("b", {}, `${v.passed}/${v.n}`), h("span", {}, "trials")),
          h("span", {}, `${pct(v.score)} task score`), delta(v.score, base[k.id].score)),
        leads[k.id][i] ? h("span", { class: "lead-tag" }, "Best") : null));
    }
  });
  return out;
}

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
        el = h("li", { class: "saying" }, h("span", { class: "t" }, fmt(it.t)), h("q", {}, it.s.text));
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
      if (say._i !== si) { say.replaceChildren(h("b", {}, "Claude"), `“${s.text.length > 220 ? s.text.slice(0, 219) + "…" : s.text}”`); say._i = si; }
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
