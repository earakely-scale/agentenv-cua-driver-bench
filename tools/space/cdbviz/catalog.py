import re
from collections import defaultdict
from datetime import datetime, timezone

CONDITIONS = ("foreground", "background")
FAMILY_RE = re.compile(r"^(?:CDB-)?([A-Z]+)")
#: The bench's first driver, which a trial naming none ran on: the board's default and the results figures' driver.
DRIVER = "cua-driver"


def ordered(keys, preferred):
    pref = [k for k in preferred if k in keys]
    return pref + sorted(k for k in keys if k not in pref)


def on_board(model, cfg):
    return ((cfg.get("models") or {}).get(model) or {}).get("board", True)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def run_order(m):
    return (m["run_index"] if m.get("run_index") is not None else 10**6, m.get("started_at") or "", m["uid"])


def board(metas, cfg, missing=()):
    """A row per OS, driver, model and condition; ``missing`` counts toward the row whose runs they're of, a run being
    one model's on one driver, and a row with any is incomplete."""
    cells = defaultdict(list)
    for m in metas:
        if on_board(m["model"], cfg):
            cells[(m["os"], m["driver"], m["model"], m["condition"])].append(m)
    rows = []
    for (os_, driver, model, cond), ms in cells.items():
        tasks = defaultdict(list)
        for m in ms:
            tasks[m["task"]].append(m)
        per = {}
        for task, tms in sorted(tasks.items()):
            tms.sort(key=run_order)
            per[task] = {"score": mean([(m["grade"]["task"] or {}).get("score") for m in tms]),
                         "pass": mean([1.0 if m["passed"] else 0.0 for m in tms]),
                         "passed": sum(m["passed"] for m in tms), "n": len(tms), "trials": [m["uid"] for m in tms]}
        runs = {m["run"] for m in ms}
        rows.append({"os": os_, "driver": driver, "model": model, "condition": cond, "n_tasks": len(per),
                     "n_trials": len(ms),
                     "missing": sum(x["os"] == os_ and x["condition"] == cond and x["run"] in runs for x in missing),
                     "passed": sum(m["passed"] for m in ms),
                     "task_score": mean([p["score"] for p in per.values()]),
                     "full_pass": mean([p["pass"] for p in per.values()]), "tasks": per})
    return rows


def task_entry(k, metas, cfg):
    known = (cfg.get("tasks") or {}).get(k)
    probe = next((m["probe"] for m in metas if m["task"] == k and m.get("probe")), None)
    t = {"id": k, "probe": probe or k.upper(), "title": probe or k.upper(), "apps": [], "summary": "", "checks": {},
         **(known or {})}
    fam = t.get("family") or (FAMILY_RE.match(t["probe"] or "") or [None, "?"])[1]
    t["family"] = fam
    t["family_name"] = (cfg.get("families") or {}).get(fam, fam)
    return t


def keys(metas):
    cells = defaultdict(list)
    for m in metas:
        cells[(m["driver"], m["os"], m["task"], m["condition"], m["model"])].append(m)
    out = {}
    for ms in cells.values():
        ms.sort(key=run_order)
        idx = [m.get("run_index") for m in ms]
        unique = None not in idx and len(set(idx)) == len(idx)
        for n, m in enumerate(ms, 1):
            out[m["uid"]] = (f"r{m['run_index']}" if unique else m["uid"], n, len(ms))
    return out


def build(metas, cfg, hero, files, missing=()):
    oses = ordered({m["os"] for m in metas}, list(cfg.get("oses") or {}))
    tasks = ordered({m["task"] for m in metas}, list(cfg.get("tasks") or {}))
    fams = list(cfg.get("families") or {})
    entries = {k: task_entry(k, metas, cfg) for k in tasks}
    pos = {k: i for i, k in enumerate(tasks)}
    tasks.sort(key=lambda k: (fams.index(entries[k]["family"]) if entries[k]["family"] in fams else len(fams), pos[k]))
    models = ordered({m["model"] for m in metas}, list(cfg.get("models") or {}))
    drivers = ordered({m["driver"] for m in metas}, list(cfg.get("drivers") or {}))
    conds = ordered({m["condition"] for m in metas}, list(CONDITIONS))
    names = {m["model"]: m["model_name"] for m in metas}
    board_models = [k for k in models if on_board(k, cfg)]
    ks = keys(metas)
    rank = {k: i for i, k in enumerate(tasks)}
    trials = sorted(metas, key=lambda m: (oses.index(m["os"]), drivers.index(m["driver"]), rank[m["task"]],
                                         conds.index(m["condition"]), models.index(m["model"]), run_order(m)))
    rows = board(metas, cfg, missing)
    return {
        "title": cfg["title"], "links": cfg["links"], "hero": hero,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "screen": cfg["screen"], "user_frame": cfg["user_frame"], "user_script": cfg["user_script"],
        "oses": [{"id": k, **((cfg.get("oses") or {}).get(k) or {"name": k, "detail": ""})} for k in oses],
        "tasks": [entries[k] for k in tasks],
        "conditions": [{"id": k, **((cfg.get("conditions") or {}).get(k) or {"name": k})} for k in conds],
        "models": [{"id": k, "name": names[k], "board": k in board_models,
                    "slot": board_models.index(k) if k in board_models else None} for k in models],
        "driver": DRIVER,
        "drivers": driver_entries(drivers, cfg),
        "criteria": [{"id": k, "short": v[0], "held": v[1], "broken": v[2]} for k, v in (cfg.get("criteria") or {}).items()],
        "trials": [{**m, "key": ks[m["uid"]][0], "nth": ks[m["uid"]][1], "of": ks[m["uid"]][2], **files[m["uid"]]}
                   for m in trials],
        "board": rows,
        "comparisons": comparisons(rows, oses, board_models, drivers, tasks),
        "missing": list(missing),
        "caveats": cfg.get("caveats") or [],
    }


def comparisons(rows, oses, models, drivers, tasks):
    """Each OS and model that two drivers or more ran in both conditions, over the tasks every one of them ran in both,
    so that the drivers figures, the Space's comparison and the card's table each compare like with like; an OS's
    widest first."""
    by = defaultdict(dict)
    for r in rows:
        by[(r["os"], r["model"], r["driver"])][r["condition"]] = r
    out = []
    for os_ in oses:
        for model in models:
            ran = [d for d in drivers if all(c in by.get((os_, model, d), {}) for c in CONDITIONS)]
            sets = [set(by[(os_, model, d)][c]["tasks"]) for d in ran for c in CONDITIONS]
            common = [t for t in tasks if all(t in s for s in sets)]
            if len(ran) < 2 or not common:
                continue
            out.append({"os": os_, "model": model, "tasks": common, "of": len(set().union(*sets)),
                        "drivers": [{"id": d, **{c: summary(by[(os_, model, d)][c], common) for c in CONDITIONS}}
                                    for d in ran]})
    return sorted(out, key=lambda c: (oses.index(c["os"]), -len(c["tasks"]), models.index(c["model"])))


def summary(row, tasks):
    per = [row["tasks"][t] for t in tasks]
    return {"score": mean([p["score"] for p in per]), "pass": mean([p["pass"] for p in per]),
            "passed": sum(p["passed"] for p in per), "n": sum(p["n"] for p in per), "missing": row["missing"]}


def driver_entries(drivers, cfg):
    """Each driver with its name, what it is and its colour's slot, from config; one config doesn't know yet takes a
    slot no known driver holds, so two drivers never share a colour."""
    known = cfg.get("drivers") or {}
    spare = [s for s in range(8) if s not in {d["slot"] for d in known.values()}]
    return [{"id": k, **(known.get(k) or {"name": k, "detail": "", "slot": spare.pop(0)})} for k in drivers]


def pct(x):
    return "–" if x is None else f"{round(100 * x)}%"


def ranges(probes):
    items = []
    for raw in probes:
        m = re.match(r"^([A-Z]+)-?(\d+)$", raw)
        items.append((m[1], int(m[2]), raw) if m else (raw, None, raw))
    out, run = [], []
    for it in items:
        if run and it[1] is not None and run[-1][0] == it[0] and run[-1][1] is not None and it[1] == run[-1][1] + 1:
            run.append(it)
            continue
        if run:
            out.append(run)
        run = [it]
    if run:
        out.append(run)
    return ", ".join(", ".join(it[2] for it in r) if len(r) < 3 else f"{r[0][2]}–{r[-1][2]}" for r in out)


def short(task):
    return (task.get("probe") or task["id"]).replace("CDB-", "")


def results_md(cat):
    tasks = [t["id"] for t in cat["tasks"]]
    names = {m["id"]: m["name"] for m in cat["models"]}
    drivers = {d["id"]: (i, d["name"]) for i, d in enumerate(cat["drivers"])}
    probes = {t["id"]: short(t) for t in cat["tasks"]}
    osn = {o["id"]: o["name"] for o in cat["oses"]}
    head = "| OS | Model | Driver | Condition | Task score | Full pass | " + " | ".join(probes[t] for t in tasks) + " |"
    lines = [head, "|" + "---|" * (6 + len(tasks))]
    order = {c: i for i, c in enumerate(CONDITIONS)}
    used = []
    for r in sorted(cat["board"], key=lambda r: (r["os"], r["model"], drivers[r["driver"]][0],
                                                 order.get(r["condition"], 9))):
        cells = []
        for t in tasks:
            p = r["tasks"].get(t)
            cv = caveat(cat, r["os"], r["condition"], t)
            if cv and cv not in used:
                used.append(cv)
            cells.append("–" if not p else f"{pct(p['score'])} · {p['passed']}/{p['n']}{cv['mark'] if cv else ''}")
        lost = f" (incomplete: {r['missing']} missing)" if r.get("missing") else ""
        lines.append(f"| {osn.get(r['os'], r['os'])} | {names.get(r['model'], r['model'])}{lost} | "
                     f"{drivers[r['driver']][1]} | {r['condition']} | "
                     f"{pct(r['task_score'])} | {pct(r['full_pass'])} ({r['passed']}/{r['n_trials']}) | "
                     + " | ".join(cells) + " |")
    lines += ["", "Task score: trycua's evaluator (weighted checks), mean over runs, then over tasks. Full pass: every "
              "half of the grade held (the task, GUI only, the sentinel's log, and in the background the user "
              "undisturbed), as the share of runs per task averaged over tasks, with the count of passing trials. "
              "Each task cell: mean task score · passing runs / runs."]
    if any(r.get("missing") for r in cat["board"]):
        lines += ["", "Incomplete: some of the row's trials are missing, cut short by infrastructure (a rate limit, an API "
                  "error, a failed setup or health check) past their re-runs, so the row isn't ranked."]
    lines += [f"{cv['mark']} {cv['short']}: {cv['reason']}" for cv in used]
    return "\n".join(lines) + "\n"


def drivers_md(cat):
    """The card's drivers table: a row per driver of each OS and model that several drivers ran, over the tasks they
    all ran in both conditions, each condition's best full pass and task score among a model's drivers in bold."""
    if not cat["comparisons"]:
        return ""
    names = {m["id"]: m["name"] for m in cat["models"]}
    drivers = {d["id"]: d for d in cat["drivers"]}
    osn = {o["id"]: o["name"] for o in cat["oses"]}
    probes = {t["id"]: short(t) for t in cat["tasks"]}
    lines = ["| OS | Model | Driver | Foreground full pass | Foreground task score | Background full pass "
             "| Background task score | n |", "|---|---|---|---:|---:|---:|---:|---:|"]
    for c in cat["comparisons"]:
        for d in c["drivers"]:
            cells = []
            for cond in CONDITIONS:
                for k in ("pass", "score"):
                    shown = [round(100 * (x[cond][k] or 0)) for x in c["drivers"]]
                    text = pct(d[cond][k]) + (f" ({d[cond]['passed']}/{d[cond]['n']})" if k == "pass" else "")
                    best = round(100 * (d[cond][k] or 0)) == max(shown) > min(shown)
                    cells.append(f"**{text}**" if best else text)
            lost = sum(d[cond]["missing"] for cond in CONDITIONS)
            lines.append(f"| {osn[c['os']]} | {names[c['model']]} | {drivers[d['id']]['name']}"
                         f"{f' (incomplete: {lost} missing)' if lost else ''} | " + " | ".join(cells)
                         + f" | {sum(d[cond]['n'] for cond in CONDITIONS)} |")
    spans = "; ".join(f"{names[c['model']]} on {osn[c['os']]}, {ranges([probes[t] for t in c['tasks']])}"
                      + (f" (the {len(c['tasks'])} of {c['of']} every driver has finished)" if len(c["tasks"]) < c["of"]
                         else "") for c in cat["comparisons"])
    lines += ["", f"Each model's rows average the same tasks, the ones every driver ran in both conditions: {spans}. "
              "The OS, the model, the tasks, their seeds and the grade are the same; only the computer-use driver "
              "changes. In bold, the best of a model's drivers in each condition; n counts the trials."]
    lines += [""] + [f"- **{d['name']}**: {escaped(d['detail'])}" for d in cat["drivers"] if d.get("detail")]
    return "\n".join(lines) + "\n"


def escaped(text):
    return re.sub(r"([*_`])", r"\\\1", text)


def caveat(cat, os_, condition, task):
    return next((cv for cv in cat.get("caveats") or [] if cv.get("os") in (None, os_) and cv["condition"] == condition
                 and task in cv["tasks"]), None)
