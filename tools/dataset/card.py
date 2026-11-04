"""card.py OUT DATASET: the dataset's README in DATASET from the card template in card/ (front matter, intro, quick
start, and the latest run's summary.md and body.md), what tools/space/build.py wrote to OUT (catalog, results table,
hero, figures) and the runs in DATASET's tables; with the licence files, and the figures and hero under assets/."""
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
    text = text.replace("{{SUMMARY}}", (HERE / "card" / "summary.md").read_text().strip())
    text = text.replace("{{RESULTS}}", _results(out, trials, missing, {m["id"]: m["name"] for m in catalog["models"]}))
    text = text.replace("{{BODY}}", (HERE / "card" / "body.md").read_text().strip())
    (dataset / "README.md").write_text(text)


def _hero(catalog, trials):
    *_, run, trial = ["", ""] + catalog["hero"].split("--")
    row = trials[(trials.trial_id == trial) & ((trials.run == run) | (run == ""))].iloc[0]
    model = _model(catalog, row.model)
    model_id = urllib.parse.quote(row.model, safe="")
    link = f"{SPACE}#/{row.os}/{row.task}/{row.condition}/{model_id}/r{int(row.run_index)}"
    broken = ", ".join(k[4:] for k in row.index if k.startswith("a22_") and row[k] is False)
    user = "keeps the user undisturbed" if row.user_undisturbed else f"disturbs the user ({broken})"
    ended = "runs out of turns" if "maximum number of turns" in str(row.agent_error) else \
        "runs out of time" if "timed out" in str(row.agent_error) else "finishes"
    alt = (f"{model} in Claude Code on {row.probe}, {row.title}, in the {row.condition} condition: the Linux desktop "
           f"as recorded, the user's window outlined, and the agent's tool calls in order with the current one lit")
    caption = (f"{model} in Claude Code on {row.probe} {row.title}, {row.condition} condition, run "
               f"{int(row.run_index)}, sped up. It makes {int(row.tool_calls)} tool calls in "
               f"{int(row.model_calls)} model calls ({int(row.tool_errors)} refused or failed), "
               f"{'stays' if row.gui_only else 'does not stay'} inside the GUI, {user} and {ended}: task score "
               f"{row.task_score:.2f}, {'a pass' if row.passed else 'not a pass'}.")
    return (f"[![{alt}](assets/hero.gif)]({link})\n\n<sub>{caption} **▶ [Watch it in the replay Space]({link})**, "
            f"with every other trial.</sub>")


def _results(out, trials, missing, names):
    figures = "\n\n".join(_picture(name, alt) for name, alt in FIGURES.items())
    runs = trials.groupby(["run", "model"], sort=False).agg(
        trials=("trial_id", "count"), passed=("passed", "sum"), task_score=("task_score", "mean"),
        cost=("cost_usd", "sum"), harness=("harness_version", "first")).reset_index()
    lost = missing.groupby("run").size()
    run_rows = "\n".join(
        f"| `{r.run}` | {names.get(r.model, r.model)} | Claude Code {r.harness} | {r.trials} | "
        f"{_lost(lost.get(r.run, 0))} | {int(r.passed)} | {r.task_score:.2f} | ${r.cost:.2f} |" for r in runs.itertuples())
    per_trial = "\n".join(
        f"| {t.trial_id} | {t.model.rsplit('/', 1)[-1]} | {t.task_score:.2f} | {_mark(t.gui_only)} | "
        f"{_mark(t.user_undisturbed)} | {_mark(t.passed)} | {int(t.tool_calls)} | "
        f"{'' if pd.isna(t.cost_usd) else f'${t.cost_usd:.2f}'} |" for t in trials.itertuples())
    return f"""{figures}

{(out / "results.md").read_text().strip()}

| Run | Model | Harness | Trials | Missing | Passed | Mean task score | Cost |
|---|---|---|---:|---:|---:|---:|---:|
{run_rows}

Cost is at list price from the tokens each trial's trajectory reports (Claude Code's own figure is in
`cost_usd_reported`). A run with missing trials, which infrastructure cut short past their re-runs
(`results/missing.parquet`), is incomplete and isn't ranked.

<details><summary>Every trial</summary>

| Trial | Model | Task score | GUI only | User undisturbed | Passed | Tool calls | Cost |
|---|---|---:|---|---|---|---:|---:|
{per_trial}

</details>"""


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
