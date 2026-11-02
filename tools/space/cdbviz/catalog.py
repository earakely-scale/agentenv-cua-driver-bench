import re
from collections import defaultdict
from datetime import datetime, timezone

CONDITIONS = ("foreground", "background")
FAMILY_RE = re.compile(r"^(?:CDB-)?([A-Z]+)")


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


def board(metas, cfg):
    cells = defaultdict(list)
    for m in metas:
        if on_board(m["model"], cfg):
            cells[(m["os"], m["model"], m["condition"])].append(m)
    rows = []
    for (os_, model, cond), ms in cells.items():
        tasks = defaultdict(list)
        for m in ms:
            tasks[m["task"]].append(m)
        per = {}
        for task, tms in sorted(tasks.items()):
            tms.sort(key=run_order)
            per[task] = {"score": mean([(m["grade"]["task"] or {}).get("score") for m in tms]),
                         "pass": mean([1.0 if m["passed"] else 0.0 for m in tms]),
                         "passed": sum(m["passed"] for m in tms), "n": len(tms), "trials": [m["uid"] for m in tms]}
        rows.append({"os": os_, "model": model, "condition": cond, "n_tasks": len(per), "n_trials": len(ms),
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
        cells[(m["os"], m["task"], m["condition"], m["model"])].append(m)
    out = {}
    for ms in cells.values():
        ms.sort(key=run_order)
        idx = [m.get("run_index") for m in ms]
        unique = None not in idx and len(set(idx)) == len(idx)
        for n, m in enumerate(ms, 1):
            out[m["uid"]] = (f"r{m['run_index']}" if unique else m["uid"], n, len(ms))
    return out


def build(metas, cfg, hero, files):
    oses = ordered({m["os"] for m in metas}, list(cfg.get("oses") or {}))
    tasks = ordered({m["task"] for m in metas}, list(cfg.get("tasks") or {}))
    fams = list(cfg.get("families") or {})
    entries = {k: task_entry(k, metas, cfg) for k in tasks}
    pos = {k: i for i, k in enumerate(tasks)}
    tasks.sort(key=lambda k: (fams.index(entries[k]["family"]) if entries[k]["family"] in fams else len(fams), pos[k]))
    models = ordered({m["model"] for m in metas}, list(cfg.get("models") or {}))
    conds = ordered({m["condition"] for m in metas}, list(CONDITIONS))
    names = {m["model"]: m["model_name"] for m in metas}
    board_models = [k for k in models if on_board(k, cfg)]
    ks = keys(metas)
    rank = {k: i for i, k in enumerate(tasks)}
    trials = sorted(metas, key=lambda m: (oses.index(m["os"]), rank[m["task"]], conds.index(m["condition"]),
                                         models.index(m["model"]), run_order(m)))
    return {
        "title": cfg["title"], "links": cfg["links"], "hero": hero,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "screen": cfg["screen"], "user_frame": cfg["user_frame"], "user_script": cfg["user_script"],
        "oses": [{"id": k, **((cfg.get("oses") or {}).get(k) or {"name": k, "detail": ""})} for k in oses],
        "tasks": [entries[k] for k in tasks],
        "conditions": [{"id": k, **((cfg.get("conditions") or {}).get(k) or {"name": k})} for k in conds],
        "models": [{"id": k, "name": names[k], "board": k in board_models,
                    "slot": board_models.index(k) if k in board_models else None} for k in models],
        "criteria": [{"id": k, "short": v[0], "held": v[1], "broken": v[2]} for k, v in (cfg.get("criteria") or {}).items()],
        "trials": [{**m, "key": ks[m["uid"]][0], "nth": ks[m["uid"]][1], "of": ks[m["uid"]][2], **files[m["uid"]]}
                   for m in trials],
        "board": board(metas, cfg),
        "caveats": cfg.get("caveats") or [],
        "figures": ["task-score", "full-pass"],
    }


def pct(x):
    return "–" if x is None else f"{round(100 * x)}%"


def results_md(cat):
    tasks = [t["id"] for t in cat["tasks"]]
    names = {m["id"]: m["name"] for m in cat["models"]}
    probes = {t["id"]: (t.get("probe") or t["id"]).replace("CDB-", "") for t in cat["tasks"]}
    osn = {o["id"]: o["name"] for o in cat["oses"]}
    head = "| OS | Model | Condition | Task score | Full pass | " + " | ".join(probes[t] for t in tasks) + " |"
    lines = [head, "|" + "---|" * (5 + len(tasks))]
    order = {c: i for i, c in enumerate(CONDITIONS)}
    used = []
    for r in sorted(cat["board"], key=lambda r: (r["os"], r["model"], order.get(r["condition"], 9))):
        cells = []
        for t in tasks:
            p = r["tasks"].get(t)
            cv = caveat(cat, r["os"], r["condition"], t)
            if cv and cv not in used:
                used.append(cv)
            cells.append("–" if not p else f"{pct(p['score'])} · {p['passed']}/{p['n']}{cv['mark'] if cv else ''}")
        lines.append(f"| {osn.get(r['os'], r['os'])} | {names.get(r['model'], r['model'])} | {r['condition']} | "
                     f"{pct(r['task_score'])} | {pct(r['full_pass'])} ({r['passed']}/{r['n_trials']}) | "
                     + " | ".join(cells) + " |")
    lines += ["", "Task score: trycua's evaluator (weighted checks), mean over runs, then over tasks. Full pass: every "
              "half of the grade held (the task, GUI only, the sentinel's log, and in the background the user "
              "undisturbed), as the share of runs per task averaged over tasks, with the count of passing trials. "
              "Each task cell: mean task score · passing runs / runs."]
    lines += [f"{cv['mark']} {cv['short']}: {cv['reason']}" for cv in used]
    return "\n".join(lines) + "\n"


def caveat(cat, os_, condition, task):
    return next((cv for cv in cat.get("caveats") or [] if cv.get("os") in (None, os_) and cv["condition"] == condition
                 and task in cv["tasks"]), None)
