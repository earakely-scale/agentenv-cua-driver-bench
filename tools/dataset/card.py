"""card.py OUT DATASET: the dataset's README in DATASET from the card template in card/ (front matter, intro, quick
start, and the latest run's summary.md and body.md), what tools/space/build.py wrote to OUT (catalog, results and
drivers tables, hero, figures) and the runs in DATASET's tables; with the licence files, and the figures and hero under
assets/."""
import json
import os
import shutil
import sys
import urllib.parse
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = os.environ.get("HF_REPO") or "earakely-scale/CuaDriverBench-AgentEnv"
SPACE = f"https://huggingface.co/spaces/{REPO}"
RESOLVE = f"https://huggingface.co/datasets/{REPO}/resolve/main"
FIGURES = {
    "task-score": "Line chart of the mean task score, trycua's evaluator over every task, in the foreground and the "
                  "background condition, one line per model",
    "full-pass": "Line chart of the share of trials that pass every half of the grade, in the foreground and the "
                 "background condition, one line per model",
}
DRIVER_FIGURES = {
    "drivers-task-score": "Line chart of the mean task score in the foreground and the background condition, a panel "
                          "per OS and model, one line per computer-use driver",
    "drivers-full-pass": "Line chart of the share of trials that pass every half of the grade in the foreground and "
                         "the background condition, a panel per OS and model, one line per computer-use driver",
}
DRIVER = "cua-driver"
HARNESSES = {"claude-code": "Claude Code", "codex-cli": "Codex CLI"}
OSES = {"linux": "Linux", "macos": "macOS"}


def main():
    out, dataset = Path(sys.argv[1]), Path(sys.argv[2])
    catalog = json.loads((out / "space" / "data" / "catalog.json").read_text())
    trials = pd.read_parquet(dataset / "results" / "trials.parquet")
    missing = pd.read_parquet(dataset / "results" / "missing.parquet")
    (dataset / "assets" / "figures").mkdir(parents=True, exist_ok=True)
    for path in (out / "assets").iterdir():
        shutil.copy(path, dataset / "assets" / ("figures" if path.suffix == ".svg" else "") / path.name)
    shutil.copy(HERE / "LICENSE.md", dataset / "LICENSE.md")
    shutil.copytree(HERE / "licenses", dataset / "licenses", dirs_exist_ok=True)
    text = (HERE / "card" / "README.md").read_text()
    text = text.replace("{{HERO}}", _hero(catalog, trials))
    text = text.replace("{{PAIRS}}", _pairs(catalog, trials))
    text = text.replace("{{SUMMARY}}", (HERE / "card" / "summary.md").read_text().strip())
    models = json.loads((HERE.parent / "space" / "config.json").read_text())["models"]
    names = {**{k: v["name"] for k, v in models.items()}, **{m["id"]: m["name"] for m in catalog["models"]}}
    text = text.replace("{{RESULTS}}", _results(out, trials, missing, names,
                                                 {d["id"]: d["name"] for d in catalog["drivers"]}))
    drivers = _drivers(out, catalog)
    text = text.replace("{{DRIVERS}}\n\n", f"{drivers}\n\n" if drivers else "")
    text = text.replace("{{BODY}}", (HERE / "card" / "body.md").read_text().strip())
    (dataset / "README.md").write_text(text)


def _pairs(catalog, trials):
    """The card's side-by-side section: each configured task's foreground and background trials of one run, the GIF
    and what each condition came to; nothing without them."""
    rows = []
    for p in catalog.get("pairs") or []:
        got = {}
        for cond in ("foreground", "background"):
            run, trial = catalog_uid(p[cond])
            got[cond] = trials[(trials.run == run) & (trials.trial_id == trial) & (trials.os == p["os"])].iloc[0]
        fg, bg = got["foreground"], got["background"]
        model = _model(catalog, fg.model)
        osn = next((o["name"] for o in catalog["oses"] if o["id"] == p["os"]), p["os"])
        driver = next((d["name"] for d in catalog["drivers"] if d["id"] == fg.driver), fg.driver)
        lead = "" if fg.driver == DRIVER else f"{fg.driver}/"
        link = f"{SPACE}#/{lead}{p['os']}/{fg.task}/background/{urllib.parse.quote(fg.model, safe='')}/r{int(fg.run_index)}"
        said = {c: ("a pass" if r.passed else "not a pass") + (", the user undisturbed" if c == "background" and r.user_undisturbed
                                                             else "") for c, r in got.items()}
        alt = (f"{model} through {driver} on {osn}, {fg.probe} {fg.title}, run {int(fg.run_index)}: the foreground trial "
               f"and the background trial side by side, each ending on its grade")
        rows.append(f"[![{alt}](assets/{p['gif']})]({link})\n\n<sub>{osn}: {model} through {driver} on {fg.probe} "
                    f"{fg.title}, run {int(fg.run_index)}, at one speed. Foreground {said['foreground']}; background "
                    f"{said['background']}. **▶ [Replay the background trial]({link})**</sub>")
    if not rows:
        return ""
    return ("## The same task in both conditions\n\nOne run of a task in the foreground, left, and in the background, right: "
            "the same model, driver, task and seed, played at one speed.\n\n" + "\n\n".join(rows) + "\n\n")


def catalog_uid(uid):
    """A Space trial uid, ``os--run--trial_id``, as (run, trial_id)."""
    *_, run, trial = uid.split("--")
    return run, trial


def _hero(catalog, trials):
    *_, run, trial = ["", ""] + catalog["hero"].split("--")
    row = trials[(trials.trial_id == trial) & ((trials.run == run) | (run == ""))].iloc[0]
    model = _model(catalog, row.model)
    model_id = urllib.parse.quote(row.model, safe="")
    lead = "" if row.driver == DRIVER else f"{row.driver}/"
    link = f"{SPACE}#/{lead}{row.os}/{row.task}/{row.condition}/{model_id}/r{int(row.run_index)}"
    broken = ", ".join(k[4:] for k in row.index if k.startswith("a22_") and row[k] is False)
    user = "keeps the user undisturbed" if row.user_undisturbed else f"disturbs the user ({broken})"
    ended = "runs out of turns" if "maximum number of turns" in str(row.agent_error) else \
        "runs out of time" if "timed out" in str(row.agent_error) else "finishes"
    harness = HARNESSES.get(row.harness, row.harness)
    alt = (f"{model} in {harness} on {row.probe}, {row.title}, in the {row.condition} condition: the "
           f"{OSES.get(row.os, row.os)} desktop as recorded, the user's window outlined, and the agent's tool calls in "
           f"order with the current one lit")
    caption = (f"{model} in {harness} on {row.probe} {row.title}, {row.condition} condition, run "
               f"{int(row.run_index)}, sped up. It makes {int(row.tool_calls)} tool calls in "
               f"{int(row.model_calls)} model calls ({int(row.tool_errors)} refused or failed), "
               f"{'stays' if row.gui_only else 'does not stay'} inside the GUI, {user} and {ended}: task score "
               f"{row.task_score:.2f}, {'a pass' if row.passed else 'not a pass'}.")
    return (f"[![{alt}](assets/hero.gif)]({link})\n\n<sub>{caption} **▶ [Watch it in the replay Space]({link})**, "
            f"with every other trial.</sub>")


def _results(out, trials, missing, names, drivers):
    figures = "\n\n".join(_picture(name, alt) for name, alt in FIGURES.items())
    runs = trials.groupby(["run", "model", "driver"], sort=False).agg(
        trials=("trial_id", "count"), passed=("passed", "sum"), task_score=("task_score", "mean"),
        harness=("harness", "first"), version=("harness_version", "first")).reset_index()
    runs["cost"] = runs.run.map(trials.groupby("run").cost_usd.sum())
    lost = missing.groupby("run").size()
    run_rows = "\n".join(
        f"| `{r.run}` | {names.get(r.model, r.model)} | {drivers.get(r.driver, r.driver)} | {HARNESSES.get(r.harness, r.harness)} {r.version} | "
        f"{r.trials} | {_lost(lost.get(r.run, 0))} | {int(r.passed)} | {r.task_score:.2f} | ${r.cost:.2f} |"
        for r in runs.itertuples())
    per_trial = "\n".join(
        f"| {t.trial_id} | {t.os} | {t.model.rsplit('/', 1)[-1]} | {drivers.get(t.driver, t.driver)} | "
        f"{t.task_score:.2f} | {_mark(t.gui_only)} | {_mark(t.user_undisturbed)} | {_mark(t.passed)} | "
        f"{int(t.tool_calls)} | "
        f"{'' if pd.isna(t.cost_usd) else f'${t.cost_usd:.2f}'} |" for t in trials.itertuples())
    return f"""{figures}

{(out / "results.md").read_text().strip()}

| Run | Model | Driver | Harness | Trials | Missing | Passed | Mean task score | Cost |
|---|---|---|---|---:|---:|---:|---:|---:|
{run_rows}

Cost is at list price from the tokens each trial's trajectory reports: Anthropic's for Claude, OpenAI's for GPT-6
(as LiteLLM's price map lists them). Claude Code's own figure is in `cost_usd_reported`; Codex reports none. A run with missing trials, which infrastructure cut short past their re-runs
(`results/missing.parquet`), is incomplete and isn't ranked.

<details><summary>Every trial</summary>

| Trial | OS | Model | Driver | Task score | GUI only | User undisturbed | Passed | Tool calls | Cost |
|---|---|---|---|---:|---|---|---|---:|---:|
{per_trial}

</details>"""


def _drivers(out, catalog):
    """The drivers comparison under the results, its figures and table, when two drivers or more ran one OS and model:
    nothing before then."""
    path = out / "drivers.md"
    table = path.read_text().strip() if path.exists() else ""
    if not table:
        return ""
    figures = "\n\n".join(_picture(name, DRIVER_FIGURES[name]) for name in catalog.get("driver_figures") or [])
    return f"""### Drivers

The same tasks through other computer-use drivers, with the OS, the model, the tasks, their seeds and the grade held
fixed. Each driver gives the agent its own tools (below), and each also serves AgentEnv's `computer_*` tools, which the
grader and the recordings use; no driver's agents in the Space see them. cua-driver's first runs, on macOS
(`sonnet-5-5-2026-11-05`, `sonnet-5-5-2026-11-05-multiapp` and `haiku-5-5-2026-11-05`) and on Linux
(`sonnet-5-5-2026-11-03`, `haiku-5-5-2026-11-02` and the pilot `sonnet-4-5-2026-11-02`), also offered its agents seven
of them beside its own tools, and its agents made some of their calls through them. They stay in the dataset, but not
in the Space, whose cua-driver rows are its runs on its own tools alone (`cua-driver-*`).

{figures}

{table}"""


def _lost(count):
    return f"**{count}, incomplete**" if count else "0"


def _picture(name, alt):
    def one(variant, css):
        phone = f"{RESOLVE}/assets/figures/{name}-phone{variant}.svg"
        return (f'<picture><source media="(max-width: 480px)" srcset="{phone}">'
                f'<img class="{css}" src="assets/figures/{name}{variant}.svg" width="660" alt="{alt}"></picture>')
    return one("", "dark:hidden") + "\n" + one("-dark", "hidden dark:block")


def _mark(value):
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else ("✓" if value else "✗")


def _model(catalog, model_id):
    return next((m["name"] for m in catalog["models"] if m["id"] == model_id), model_id)


if __name__ == "__main__":
    main()
