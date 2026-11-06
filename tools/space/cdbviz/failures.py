"""Each board trial's outcome, a pass or the way it failed, as the catalog's ``failures`` and the card's findings.

A trial that failed several ways counts under the gravest, MODES' last: the bench's two rules first, since breaking
either fails a trial whatever it left behind (most background trials that disturbed the user had done their task),
then how a run that kept them ended, which the agent's last word makes exclusive: it stopped and said it was blocked,
it hit a limit, or it finished with the task wrong."""
import re
from collections import Counter, defaultdict

from . import catalog

#: The outcomes in the order the figures stack them, a pass first, then mildest to gravest, each with its colour: a
#: figures.SERIES slot, and for a tint its strength in the light and the dark theme. A pass and the dialog over the user
#: are tints, so the failures the agent made stand out; the full hues, in this order, keep neighbours apart for
#: colour-blind readers.
MODES = [
    {"id": "pass", "slot": 2, "tint": [0.3, 0.42], "name": "Passed",
     "description": "Every half of the grade held: the task, GUI only, and in the background the user undisturbed."},
    {"id": "wrong", "slot": 7, "name": "Done, but wrong",
     "description": "The agent finished, most often replying DONE, but trycua's evaluator found the task wrong or "
                    "unfinished."},
    {"id": "out_of_turns", "slot": 0, "name": "Ran out of turns",
     "description": "The agent hit the bench's limit, 45 turns or 6 minutes, before it finished."},
    {"id": "blocked", "slot": 1, "name": "Stopped, blocked",
     "description": "The agent stopped and replied BLOCKED: a step its tools couldn't do (browser-use has no hover; "
                    "GPT-6 in Codex never sees a screenshot), an app that stopped responding, or a result it couldn't "
                    "confirm."},
    {"id": "no_background", "slot": 6, "name": "No background input",
     "description": "In the background, the driver refused to reach the app without bringing it forward, and the agent "
                    "stopped (BLOCKED) rather than disturb the user."},
    {"id": "dialog", "slot": 3, "tint": [0.35, 0.45], "name": "Dialog over the user",
     "description": "Disturbed the user in a task that can't pass in the background on this OS: on Linux the task's "
                    "own dialog covers the user's window whatever the agent does (‡)."},
    {"id": "disturbed", "slot": 3, "name": "Disturbed the user",
     "description": "In the background, the agent took the user's keyboard focus, raised a window over theirs, moved "
                    "their pointer, changed their clipboard or lost one of their keystrokes: trycua's A22 criteria."},
    {"id": "left_gui", "slot": 4, "name": "Left the GUI",
     "description": "The agent got round the GUI, such as running a command through cua-driver's launch_app, which "
                    "fails the trial whatever else it did."},
]
#: A driver refusing input it can't deliver without bringing the app forward, as the replay's lane shows the error.
REFUSED = re.compile(r"(?i)background (delivery|input|pixel click|scroll)[^.]{0,40}(not available|refused|unavailable)"
                     r"|background drag\b.{0,60}drag-and-drop session|moves the cursor and is disabl")
#: The model whose trials the examples show first, the one every driver ran.
SHOWN_FIRST = "anthropic/claude-sonnet-5-5"
HARNESSES = {"claude-code": "Claude Code", "codex-cli": "Codex CLI"}


def build(loaded, cat):
    """The catalog's ``failures``: the modes, each board trial's, and up to three trials of each failure mode, those that
    show it soonest, SHOWN_FIRST's and a spread of setups and tasks first."""
    board = {m["id"] for m in cat["models"] if m["board"]}
    trials = [t for t in loaded if t["meta"]["model"] in board]
    by_trial = {t["meta"]["uid"]: outcome(t["meta"], t["web"]["calls"], cat) for t in trials}
    return {"modes": MODES, "by_trial": by_trial, "examples": examples(trials, by_trial)}


def outcome(meta, calls, cat):
    """``pass``, or the id of the gravest way the trial failed."""
    g = meta["grade"]
    if meta["passed"]:
        return "pass"
    if not g["gui_only"]["result"]:
        return "left_gui"
    if g["user_undisturbed"] and not g["user_undisturbed"]["result"]:
        cv = catalog.caveat(cat, meta["os"], meta["condition"], meta["task"])
        return "dialog" if cv and cv.get("passable") is False else "disturbed"
    ending = meta["ending"] or ""
    if ending.startswith("Replied BLOCKED"):
        refused = meta["condition"] == "background" and any(REFUSED.search(c["err"] or "") for c in calls)
        return "no_background" if refused else "blocked"
    if ending.startswith(("Hit the", "Ran out of time")):
        return "out_of_turns"
    return "wrong"


def examples(trials, by_trial):
    out = {}
    for mode in MODES[1:]:
        pool = sorted((t for t in trials if by_trial[t["meta"]["uid"]] == mode["id"]),
                      key=lambda t: (t["meta"]["model"] != SHOWN_FIRST, shown_at(t, mode["id"])))
        picked = []
        while pool and len(picked) < 3:
            seen = lambda t, k: t["meta"][k] in {p["meta"][k] for p in picked}
            best = min(pool, key=lambda t: (t["meta"]["model"] != SHOWN_FIRST, seen(t, "driver") and seen(t, "os"),
                                            seen(t, "task"), shown_at(t, mode["id"])))
            picked.append(best)
            pool.remove(best)
        if picked:
            out[mode["id"]] = [t["meta"]["uid"] for t in picked]
    return out


def shown_at(t, mode):
    """Seconds into the agent's window when the trial first shows ``mode``: the user's first disturbance, the first
    refusal or the first call to the tool that left the GUI; the run's end for the rest."""
    web, g = t["web"], t["meta"]["grade"]
    start = web["armed"][0] or 0
    if mode in ("disturbed", "dialog") and (web["user"] or {}).get("events"):
        return web["user"]["events"][0]["t"] - start
    if mode == "no_background":
        return next((c["t0"] for c in web["calls"] if REFUSED.search(c["err"] or "")), web["duration"]) - start
    if mode == "left_gui":
        tools = {v.split("__")[-1].split(":")[0] for v in g["gui_only"]["violations"]}
        return next((c["t0"] for c in web["calls"] if c["tool"] in tools), web["duration"]) - start
    return (t["meta"]["duration"] or web["duration"] or 0) - start


def setups(cat):
    """Each board OS, driver and model that ran, in the catalog's order: (os, driver, model)."""
    rank = {k: {x["id"]: i for i, x in enumerate(cat[k])} for k in ("oses", "drivers", "models")}
    found = {(r["os"], r["driver"], r["model"]) for r in cat["board"]}
    return sorted(found, key=lambda s: (rank["oses"][s[0]], rank["drivers"][s[1]], rank["models"][s[2]]))


def tally(cat):
    """{(os, driver, model, condition): Counter of mode ids} over the board's trials."""
    by_trial = cat["failures"]["by_trial"]
    out = defaultdict(Counter)
    for t in cat["trials"]:
        if t["uid"] in by_trial:
            out[(t["os"], t["driver"], t["model"], t["condition"])][by_trial[t["uid"]]] += 1
    return out


def markdown(cat):
    """The card's findings and table of each setup's outcomes, from the catalog."""
    lines = [f"- {f}" for f in findings(cat)]
    return "\n".join(lines + [""] + table(cat)) + "\n"


def table(cat):
    counts = tally(cat)
    names = {k: {x["id"]: x.get("label") or x["name"] for x in cat[k]} for k in ("oses", "drivers", "models")}
    used = [m for m in MODES if any(c[m["id"]] for c in counts.values())]
    lines = ["| OS | Driver | Model | " + " | ".join(m["name"] for m in used) + " | Trials |",
             "|---|---|---|" + "---:|" * (len(used) + 1)]
    for os_, driver, model in setups(cat):
        fg, bg = counts[(os_, driver, model, "foreground")], counts[(os_, driver, model, "background")]
        lines.append(f"| {names['oses'][os_]} | {names['drivers'][driver]} | {names['models'][model]} | "
                     + " | ".join(f"{fg[m['id']]} · {bg[m['id']]}" for m in used)
                     + f" | {sum(fg.values())} · {sum(bg.values())} |")
    return lines + ["", "Each cell counts foreground · background trials, each trial under the gravest way it failed."]


def findings(cat):
    trials = [t for t in cat["trials"] if t["uid"] in cat["failures"]["by_trial"]]
    mode_of = cat["failures"]["by_trial"]
    out = [overall(trials, mode_of)]
    out += [s for o in cat["oses"] if (s := drivers_disturb(cat, trials, mode_of, o))]
    out += [s for o in cat["oses"] if (s := background_walls(cat, trials, mode_of, o))]
    out += [s for s in (turns(cat, trials, mode_of), stops(cat, trials, mode_of), escapes(cat, trials, mode_of)) if s]
    return out


def overall(trials, mode_of):
    modes = Counter(mode_of[t["uid"]] for t in trials)
    names = {m["id"]: m["name"] for m in MODES}
    top = [f"*{names[m]}* ({n})" for m, n in modes.most_common() if m != "pass"][:3]
    return (f"**{modes['pass']} of the {len(trials)} board trials pass.** Of the {len(trials) - modes['pass']} that "
            f"fail, the largest groups are " + join(top) + ".")


def drivers_disturb(cat, trials, mode_of, o):
    """How often each driver an OS ran disturbs the user in the background, and the criterion it breaks most."""
    parts = []
    for d in cat["drivers"]:
        bg = [t for t in trials if t["os"] == o["id"] and t["driver"] == d["id"] and t["condition"] == "background"]
        hit = [t for t in bg if mode_of[t["uid"]] == "disturbed"]
        if not bg:
            continue
        broke = Counter(k for t in hit for k, v in t["grade"]["user_undisturbed"]["criteria"].items() if v is False)
        how = "".join(f", most often by {BROKE[k]} ({n})" for k, n in broke.most_common(1))
        parts.append((-len(hit) / len(bg), d.get("label") or d["name"], len(hit), len(bg), how))
    if len(parts) < 2:
        return None
    (_, name, hit, n, how), *rest = sorted(parts)
    rates = [-p[0] for p in parts]
    lead = ("the driver decides whether the user is disturbed" if max(rates) - min(rates) >= 0.3
            else "its drivers disturb the user about as often")
    return (f"**On {o['name']} {lead}.** In the background, {name} disturbs "
            f"them in {hit} of its {n} trials{how}; " + "; ".join(f"{name} in {hit} of {n}{how}"
                                                                for _, name, hit, n, how in rest) + ".")


def background_walls(cat, trials, mode_of, o):
    """The background tasks an OS lets any model pass, when they are few, and what stops the rest: the task's dialog
    over the user, or a driver that can't reach the app without bringing it forward."""
    bg = [t for t in trials if t["os"] == o["id"] and t["condition"] == "background"]
    short = {t["id"]: catalog.short(t) for t in cat["tasks"]}
    order = [t["id"] for t in cat["tasks"]]
    passing = [short[k] for k in order if any(t["task"] == k and mode_of[t["uid"]] == "pass" for t in bg)]
    walls = []
    for mode, what in (("dialog", "the task's dialog covers the user's window in {n} trials (‡)"),
                       ("no_background", "the driver refuses background input and the agent stops in {n}")):
        hit = [t for t in bg if mode_of[t["uid"]] == mode]
        if hit:
            tasks = catalog.ranges([short[k] for k in order if any(t["task"] == k for t in hit)]).rsplit(", ", 1)
            walls.append(f"in {' and '.join(tasks)} " + what.format(n=len(hit)))
    if not walls or len(passing) * 2 > len({t["task"] for t in bg}):
        return None
    some = (f"the only background task{'s' if len(passing) > 1 else ''} any model passes "
            f"{'are' if len(passing) > 1 else 'is'} {join(passing)}" if passing else "no model passes a background task")
    text = "; ".join(walls)
    return f"**On {o['name']} {some}.** {text[0].upper()}{text[1:]}."


def turns(cat, trials, mode_of):
    """Where trials run out of turns: the task family most of them are in, and the setup that runs out most there."""
    out = [t for t in trials if mode_of[t["uid"]] == "out_of_turns"]
    if not out:
        return None
    family = {t["id"]: t["family_name"] for t in cat["tasks"]}
    fam, n = Counter(family[t["task"]] for t in out).most_common(1)[0]
    by = defaultdict(list)
    for t in trials:
        if family[t["task"]] == fam:
            by[(t["os"], t["driver"], t["model"])].append(mode_of[t["uid"]] == "out_of_turns")
    (os_, driver, model), hits = max(by.items(), key=lambda kv: (sum(kv[1]) / len(kv[1]), len(kv[1])))
    names = {k: {x["id"]: x.get("label") or x["name"] for x in cat[k]} for k in ("oses", "drivers", "models")}
    many = "trials run" if len(out) != 1 else "trial runs"
    return (f"**{len(out)} {many} out of turns, {'all' if n == len(out) else n} of them in {fam.lower()}.** "
            f"{names['models'][model]} through {names['drivers'][driver]} on {names['oses'][os_]} runs out most "
            f"there, in {sum(hits)} of its {len(hits)}.")


def stops(cat, trials, mode_of):
    """How often the agent stops, reporting itself blocked, in the foreground, where only its tools hold it back: per
    harness, and the tasks a driver stops on every time."""
    harness = {m["id"]: m["harness"] for m in cat["models"]}
    by = defaultdict(list)
    for t in trials:
        if t["condition"] == "foreground":
            by[harness[t["model"]]].append(mode_of[t["uid"]] == "blocked")
    stopped = sum(sum(v) for v in by.values())
    if not stopped:
        return None
    parts = [f"{sum(v)} of {HARNESSES.get(h, h)}'s {len(v)}"
             for h, v in sorted(by.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))]
    short = {t["id"]: catalog.short(t) for t in cat["tasks"]}
    always = []
    for d in cat["drivers"]:
        tasks = [k for k in short if (fg := [t for t in trials if t["driver"] == d["id"] and t["task"] == k
                                             and t["condition"] == "foreground"]) and
                 all(mode_of[t["uid"]] == "blocked" for t in fg)]
        if tasks:
            always.append(f"{d.get('label') or d['name']} stops in every {join([short[k] for k in tasks])} trial")
    return (f"**In the foreground, {stopped} trials end with the agent reporting itself blocked:** " + join(parts)
            + (f"; {join(always)}" if always else "") + ".")


def escapes(cat, trials, mode_of):
    """The trials that left the GUI: how many, on which OS, and through which tools and fields."""
    out = [t for t in trials if mode_of[t["uid"]] == "left_gui"]
    if not out:
        return None
    ways = {v.split("__")[-1] for t in out for v in t["grade"]["gui_only"]["violations"]}
    tools = sorted({w.split(":")[0] for w in ways})
    fields = sorted({w.split(":")[1].replace("_", " ") for w in ways if ":" in w})
    oses = {t["os"] for t in out}
    where = {o["id"]: o["name"] for o in cat["oses"]}
    return (f"**{len(out)} trial{'s' if len(out) != 1 else ''} leave the GUI**, "
            + (f"all on {where[next(iter(oses))]}, " if len(oses) == 1 else "")
            + f"by giving {join([f'`{x}`' for x in tools])} "
            + join([f if f.endswith("s") else f"a {f}" for f in fields], "or") + ".")


#: What breaking each of trycua's A22 criteria does to the user, as a sentence says it.
BROKE = {"key_focus": "taking their keyboard focus", "window_raised": "raising a window over theirs",
         "typing": "losing their keystrokes", "pointer": "moving their pointer", "clipboard": "changing their clipboard",
         "space": "switching their desktop", "dialog": "opening a dialog over their window",
         "activation": "making another app active"}


def join(items, word="and"):
    items = list(items)
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {word} {items[-1]}" if items else ""
