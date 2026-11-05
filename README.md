# Cua Driver Bench for AgentEnv

[trycua](https://github.com/trycua/cua)'s Cua Driver Bench as an [AgentEnv](https://github.com/scaleapi/agentenv-framework)
bundle: the bench's GUI tasks, run with `agent-env run` on a Linux computer that an agent drives through its
computer-use driver.

**Status:** all of trycua's Bench v2, its ten GUI-only tasks in both conditions, five runs each: the three multi-app
tasks G02 to G04, each on a computer of its own with its shared task's apps, s04's browser included (Chrome for Testing
at the build agentenv's `chromium` app pins, pinned again here so the bench's browser stays the same whatever a
framework release ships), and the seven BenchLab tasks, MB-09 to MB-11 and IR-01 to IR-04, in trycua's own Linux
BenchLab. Beside each task's app, the bench's sentinel, with trycua's GUI-only guard in it, and the grade, which scores
a trial outside the computer with trycua's own evaluator, A22 criteria and GUI-only scan.

## What's here

| Path | What it is |
|---|---|
| `envs/desktop/` | The bench's computer: the shipped `ubuntu-24.04` base computer with the shipped `cua-driver` driver, at the 1920x1080 display the bench's tasks assume. |
| `taskpack.lock.toml`, `tools/taskpack.py` | trycua's task pack, pinned to one commit of their repo and a checksum, and the tool that fetches it into `artifacts/taskpack/`. |
| `tasks/probe.json` | Deploys the computer and runs the computer-use conformance probe at `full` against it (`artifacts/check_probe/`). |
| `tasks/taskpack.json` | Loads the task pack into the computer and checks every file arrived intact, against the pack's own manifest. |
| `evals/smoke.toml` | Both tasks. |
| `envs/cdb-s02/`, `envs/cdb-s03/`, `envs/cdb-s04/` | Each shared task as one computer app: its windows, its workspace and how it resets (below). |
| `envs/desktop-s02/` .. `envs/desktop-s04/` | Each task's computer: `desktop`'s base and driver, with that task's app. |
| `tasks/app-s02.json` .. `tasks/app-s04.json`, `evals/apps.toml` | Each deploys a task's computer and checks its app inside it (`artifacts/check_app/`), then snapshots it. |
| `envs/bench-sentinel/` | The bench's sentinel, on every task's computer: the user's window, logging all that disturbs that user, with the GUI-only guard in it (below). |
| `artifacts/sentinel/` | Arms the sentinel just before the agent starts and disarms it just after, as `run_code` steps. |
| `artifacts/grader/`, `artifacts/gui_only/` | The grade of a trial: its grading container, and the trajectory's GUI-only check (below). |
| `tasks/sentinel-background.json`, `tasks/sentinel-foreground.json`, `evals/sentinel.toml` | Each causes every disturbance on purpose inside s02's computer and checks trycua's scoring finds it (`artifacts/check_sentinel/`). |
| `tasks/cdb-g02-background.json` .. `tasks/cdb-g04-foreground.json`, `evals/trials.toml` | The bench's GUI-only tasks, each in both of trycua's conditions, with a model (below). |
| `envs/benchlab/`, `envs/desktop-benchlab/` | trycua's BenchLab as a computer app, in a task's mode and seed, and its computer, with the sentinel (below). |
| `tasks/benchlab-listdrag.json` .. `tasks/benchlab-irconsent.json`, `tasks/benchlab-solve-*.json`, `evals/benchlab.toml` | BenchLab in each mode in its computer (`artifacts/check_benchlab/`), and three of its tasks done through the driver and graded with no model. |
| `tasks/mb-09-r1-background.json` .. `tasks/ir-04-r5-foreground.json` | The BenchLab tasks, five runs each, each run with its seed, in both conditions, with a model (below). |
| `evals/bench-v2.toml`, `evals/bench-v2-trials.txt` | All of Bench v2: each of its task files once, and its 100 trials in trycua's schedule (below). |
| `evals/foreground.toml`, `evals/background.toml` | Bench v2's task files in one condition each. |
| `tools/fleet/` | Runs the trials on a fleet of EC2 VMs, each trial exported and uploaded to the dataset as it finishes (below). |
| `tools/dataset/` | The dataset's exporter, tables, card and licences, and `publish.sh`, which rebuilds and uploads them (below). |
| `tools/space/` | The replay Space, the card's hero GIF and figures, and each trial's web video, from a folder of trials (below). |
| `tests/` | Tests of the fetch tool, of the apps as a computer reads them, of the sentinel and the guard on a fake desktop, of the grade, of the fleet's plan and gates, and of the dataset's pricing, timelines and tables, offline. |

## Run it

You need Python 3.11 or newer, Docker, and an OCI registry on `localhost:5000`. No model is needed yet.

```bash
pip install 'agentenv-framework>=0.9.1406'
docker run -d -p 5000:5000 public.ecr.aws/docker/library/registry:2
python tools/taskpack.py            # fetch the task pack into artifacts/taskpack/
agent-env run . --eval smoke
agent-env run . --eval apps         # each task's app in its computer
agent-env run . --eval sentinel     # the sentinel and its guard in s02's computer, scored by trycua's files
agent-env run . --eval benchlab     # BenchLab in each mode, and three of its tasks done through the driver and graded
```

The first run composes the computer: it builds an image of the base with the driver installed, then probes it. That
takes a few minutes; later runs reuse the image. It builds for each arch your Docker can: on an amd64 machine without
arm64 emulation it says it can't build linux/arm64 and goes on with amd64.

### On macOS

The BenchLab tasks run on macOS too, on trycua's own BenchLab and BenchSentinel apps, built from their Swift sources at
the pinned commit. The computer is Cua's public macOS 26 VM bundle, run by Lume, with cua-driver and the two apps
installed. The agent and the grade run in containers beside it.

You need:

- an Apple silicon Mac;
- `agent-env` running in a logged-in session, since Virtualization.framework runs a VM only there;
- [Lume](https://github.com/trycua/cua/tree/main/libs/lume) on the PATH;
- a Docker (`brew install colima docker && colima start` will do) with a registry on `localhost:5000`;
- a model endpoint.

```bash
pip install 'agentenv-framework>=0.9.1443'
docker run -d -p 5000:5000 public.ecr.aws/docker/library/registry:2
python tools/taskpack.py
mkdir -p .agentenv && cat > .agentenv/config.toml <<'EOF'
[sandbox]
default = "lume"

[model]
base_url = "https://your-model-proxy"
api_key = "env:LITELLM_API_KEY"
default = "anthropic/claude-sonnet-5-5"
EOF
agent-env run . --task macos-ir-01-r1-foreground
agent-env run . --eval macos-bench-v2     # all 70 trials, one after another
```

**The first run takes a while.** It pulls Cua's base (about 29 GB), then composes the computer, about 7 minutes:
trycua's apps build in a VM of the base, and the probe checks the result. Later runs reuse the composed computer. A trial
then takes 2 to 6 minutes.

An eval runs its trials one after another. Apple's licence allows two macOS VMs on a Mac.

**What differs from Linux:** the macOS trial files (`tasks/macos-*.json`) carry trycua's system prompt as written, for
"a macOS desktop", and grade on the Mac's own Docker.

## The task apps

Each shared task (`cdb-s02`, `cdb-s03`, `cdb-s04`) is one computer app, so that every window it opens stops and starts
with its data, as the bench stops its apps before it resets a task:

- Its install brings the task's own files, at the pinned commit (`files.json`, each by URL and sha256, written by
  `python tools/taskpack.py apps`), Electron 43.8.1 and, for s04, Node 22 at their official checksums, and the Ubuntu
  packages its windows need: LibreOffice Calc for s02 and s03, GnuCash for s03.
- Its install then builds the task's workspace in the session user's home (`~/cdb-s02`, ...) with the task's
  `reset/setup.py`, and the build fails unless the task's `reset/verify.py` passes on it, byte for byte.
- That workspace is its data: `data/get` returns it, `data/add` writes into it, and `data/reset` puts it back as
  `setup.py` built it, with the windows closed and opened again.
- It opens the task's windows at boot as the task's `platform/launch.linux.json` says, Electron without Chromium's
  sandbox, which a container can't give it, and places each at the bench's bounds; it's ready once every one shows.

## BenchLab

trycua's precision and interruption tasks, MB-09 to MB-11 and IR-01 to IR-04, run in their BenchLab, one window with a
mode per task. `envs/benchlab` is their Linux port of it, a GTK app, as a computer app:

- Its install brings their `linux/benchlab.py` and `benchlab_common.py` at the pinned commit, by URL and sha256
  (`files.json`, written by `python tools/taskpack.py apps`), and GTK's Python bindings.
- Its app settings `mode` and `seed` pick the task's mode and the run's seed, from which BenchLab draws the task's
  values. It starts BenchLab as their runner does, `/usr/bin/python3 benchlab.py --mode M --seed S --state ...
  --events ...` with a throwaway home, and places its window where their macOS BenchLab puts its own, the outer frame's
  top left at 60,80; their Linux port leaves that to the window manager. In the background condition the user's window
  covers part of it, on purpose, as in theirs.
- Its data is `~/.benchlab`, the state and events BenchLab writes, which trycua's evaluator for the task grades.
- `artifacts/check_benchlab` checks it in its computer: the window in its mode, placed, its state and `app_start` for
  that mode and seed, its data plane; and with `solve`, does the task as an agent does, through the driver over its MCP
  endpoint, element by element, with the values trycua's files derive from the seed; and with `background`
  (`tasks/benchlab-background-ir-0{1,3,4}.json`), brings up and answers IR-01's, IR-03's and IR-04's interruption by
  background actions alone, and reports what the user's window went through.

### A background app's modal dialog on Linux

IR-01, IR-03 and IR-04 interrupt with a modal dialog, and on Linux the window manager puts a new modal dialog over the
user's window whatever the agent does, so in the background condition those three tasks can't keep the user
undisturbed. On macOS, where trycua's bench comes from, a background app's sheet stays behind the active window. This
computer's window manager, xfwm4, also gives the dialog the keyboard. Openbox, which trycua's own Linux session runs,
leaves the keyboard with the user's window but still stacks the dialog over it. Measured with no model, each dialog
opened by a background click while the user's window held the keyboard:

| Window manager | Modal dialog | Non-modal dialog |
|---|---|---|
| xfwm4, as shipped, or with `focus_new` off, or with focus-stealing prevention on | takes the keyboard and comes to the front (3 of 3 each) | neither (0 of 3) |
| openbox | comes to the front: IR-01's, IR-03's and IR-04's dialogs over the user's window in 63 of 66, 64 of 66 and 46 of 52 samples | neither (0 of 3) |

The bench stays on xfwm4: openbox wouldn't let those tasks pass either, and it made the computers' conformance probe
fail at random (P6, a chord that selects all, then Backspace). IR-02's banner is drawn inside BenchLab's window, so it
can pass. The `background` checks report `user_kept_focus` and `user_window_on_top`, both "no" here.

## The sentinel and the GUI-only guard

trycua's bench measures, besides whether the task got done, whether the agent disturbed the computer's user and whether
it stayed in the GUI. On macOS their `BenchSentinel` plays the user; `envs/bench-sentinel` is that sentinel for Linux:

- Its app setting `condition` picks trycua's two windows: `background`, the "User activity" window at 420,340 (900x520)
  that types one character a second while it's active and holds the focus, or `foreground`, the "Bench Sentinel"
  witness at the bottom right.
- It writes trycua's log, line for line, to `~/.bench-sentinel/sentinel.jsonl`, its data: a 20 Hz sample and every
  focus, activation, desktop and clipboard change and every key, click and scroll delivered to it, read through X11
  (the input focus for the key window, `_NET_ACTIVE_WINDOW` for the active app, WM_CLASS for an app's name, the window
  manager's stacking for the windows above, CLIPBOARD's owner for the pasteboard, the desktop for the Space). So
  trycua's own `summarize_sentinel.py` and A22 criteria score it, unchanged.
- While armed, its guard samples every 0.5 s as trycua's does: a terminal or run dialog in front three samples in a
  row, a terminal's program, or a program started on a pseudo-terminal is a `gui_only_violation`.
- `artifacts/sentinel` arms it just before the agent starts (empty clipboard, first desktop, the sentinel active with
  the focus) and disarms it after, by signal, as trycua's runner does.

## The grade

A trial is graded as trycua's runner grades one, in two halves, and passes when both do:

- **In a container of its own.** After the agent, `snapshot_env` exports the computer's apps' files. A `deploy_sandbox`
  sandbox runs the bench's grading container (`artifacts/grader/`: Python 3 and Node 22, no network), and
  `load_artifact` stages trycua's task pack and the snapshot in it. There `run_container_unit_tests_verifier` runs
  `grade.py`, which scores its reward: `sentinel`, its log shows the whole trial; `task`, trycua's evaluator passed,
  for a BenchLab task (`grade.py PROBE SEED`) theirs for that probe on BenchLab's state and events, with the run's seed;
  `gui_only`, the guard logged no violation and no Electron app's DevTools opened; and in the background condition
  `user_undisturbed`, all eight of trycua's A22 criteria measured and held. The files the agent left are parsed only
  there.
- **Outside, from the trajectory.** `artifacts/gui_only/verify.py`, an `env_outcome_verifier`, runs trycua's scan on
  claude-code's tool calls: no built-in tool offered but Skill and Read, none trycua forbids tried, no code in a tool
  input, no command run through cua-driver's `launch_app`. trycua's scan is fetched at the lock's commit by URL and
  sha256 (`python tools/taskpack.py grader` writes it). A verifier is handed the agent's trajectory from
  agentenv-framework's [#439](https://github.com/scaleapi/agentenv-framework/pull/439) on; before it, this half fails,
  since the tool calls can't be checked.

## The trials

`tasks/cdb-g02-background.json` .. `tasks/cdb-g04-foreground.json` are trycua's GUI-only tasks G02, G03 and G04, each
in both conditions, as their runner runs them: the task's computer with the sentinel in that condition; claude-code with
no built-in tools but Skill and Read, trycua's set less the tool search its CLI hasn't, and trycua's system prompt, for a
Linux desktop; the sentinel armed just before the prompt and
disarmed just after, under a recording; the prompt their runner gives, within the task's time and turns; and the grade,
which runs whatever became of the agent. The prompts and the system prompt quote trycua's text, which
`tests/test_trials.py` checks against the pinned task pack. They need a model endpoint (`[model]` in the config).

`tasks/mb-09-r1-background.json` .. `tasks/ir-04-r5-foreground.json` are the BenchLab tasks the same way, one file per
run: trycua seeds run `r` of a task with `probe_seed(task, r - 1)`, and the run's brief and BenchLab's values come from
that seed. A G task's runs share one file, since its seed changes nothing.

Each prompt is the one trycua's runner sends: the task's brief, in the background their background brief, and the line
their runner adds by default, "You have about 6 minutes and at most 45 turns." trycua's BenchLab briefs say BenchLab
"is already open on your Mac"; the trials keep their text as it is. MB-10's brief speaks of a toolbar strip whose
"Actions" area reveals the buttons; their Linux BenchLab's zone reads "Hover here to reveal actions".

`evals/bench-v2-trials.txt` lists Bench v2's 100 trials, one task file per line, in trycua's schedule: the v2 tasks in
order, runs 1 to 3, then runs 4 and 5, a whole run in one condition, the foreground's then the background's.
`evals/bench-v2.toml` runs each of those task files once, since an eval runs a task once; a runner that repeats a G
task's file per line runs them all. `evals/foreground.toml` and `evals/background.toml` are its two halves, one
condition each.

```bash
agent-env run . --task cdb-g02-background
agent-env run . --task ir-01-r1-background
```

## Run at scale and publish

The published runs are on Hugging Face: the dataset
[earakely-scale/CuaDriverBench-AgentEnv](https://huggingface.co/datasets/earakely-scale/CuaDriverBench-AgentEnv),
every trial's recording, trajectory, sentinel log, grade and final files with the `trials`, `calls` and `tasks`
tables, and the replay Space of the same name. `tools/` makes them.

**Configure.** `tools/fleet/fleet.env` (git-ignored; copy `fleet.env.example`), or the same names in the environment:

- `FLEET_REGION`, `FLEET_SUBNET`, `FLEET_SECURITY_GROUPS`: where the workers start; AWS credentials come as the AWS
  CLI and boto3 find them (`AWS_PROFILE`).
- `FLEET_INSTANCE_PROFILE`: an instance profile whose role lets SSM manage the VM. Every command reaches the
  workers through SSM, so they need no inbound port.
- `FLEET_MODEL_BASE_URL`: the OpenAI-compatible endpoint the agents call, a LiteLLM proxy for instance. Its key goes in
  `FLEET_MODEL_KEY`, in the shell only.
- Optional: `FLEET_NAME` and `FLEET_TAGS` (the VMs' tags), `FLEET_MAX_HOURS` (a worker shuts itself down, and is
  terminated, after that many hours; 12), `FLEET_FRAMEWORK` (the framework the workers install), `FLEET_BENCH_REPO`
  (the bench they clone), `HF_REPO` (the dataset and Space; `earakely-scale/CuaDriverBench-AgentEnv`).

The Hugging Face token is huggingface_hub's login (`hf auth login`).

**Run.** pip install `boto3 huggingface_hub` where you drive the fleet; nothing heavy runs there.

```bash
python tools/fleet/plan.py evals/bench-v2-trials.txt plan 10   # 100 trials, 10 workers, each on one computer
tools/fleet/launch.sh 10 c6i.2xlarge > instances.txt           # the workers set themselves up in a few minutes
tar czf taskpack.tgz -C artifacts taskpack                     # the task pack, fetched once here
export FLEET_MODEL_KEY=...
python tools/fleet/start.py <instance> haiku-5-5-2026-11-02 anthropic/claude-haiku-5-5 plan/worker-01.txt \
    --taskpack taskpack.tgz                                    # once per worker, each with its own plan file
python tools/fleet/watch.py instances.txt                      # each worker's trials, until they're done
```

- `start.py` hands the worker its trials and, encrypted to a key the VM makes for the job, the model key and the
  Hugging Face token. The worker decrypts them into its own environment and deletes them.
- `--taskpack` ships the task pack you fetched. Ten VMs behind one address run out of GitHub's API calls fetching it
  themselves.
- `tools/fleet/worker.py` runs on the VM. It first uploads the run's manifest (`tools/fleet/manifest.py`) to
  `runs/<os>/<run>/manifest.json`: the task pack's commit and sha256, the framework's version, the model and agent,
  each computer with its driver and the sha256 of the driver's tool list, the host, the limits, conditions and seeds,
  and the re-run policy. It refuses a framework older than 0.9.1412, whose verifiers get the graded trajectory.
  A run made elsewhere, such as on a Mac, writes the same manifest with
  `python tools/fleet/manifest.py . RUN OS MODEL SPECS --image image.json`, `image.json` being the identity its image
  records (a macOS image's `/etc/agentenv/image.json`).
- It runs each trial with `agent-env run . --task`. A trial infrastructure cut short is a harness error, never a score:
  - a rate limit is re-run after a backoff, up to six times;
  - an API 5xx or overload, up to three times;
  - a failed setup or health-check step, up to twice, each on a fresh deploy.
- Past that, the trial is missing: its record goes to the dataset as `missing.json` in its folder, and its run counts
  as incomplete. Everything else counts.
- `tools/dataset/export.py` then exports each graded trial, with `attempts.json` holding the harness errors it was
  re-run for. The worker uploads it to `runs/<os>/<run>/<task>-r<run>-<condition>/`, replacing what was there.
  `start.py --os macos` puts a run under `runs/macos/`; `linux` is the default.
- A worker restarted with `start.py` resumes from its progress; `--fresh` starts it over.
- A file `~/fleet/stop` on a worker stops it before its next trial and lets the one running finish, to stop a run
  at a budget; `start.py` removes it.
- Terminate the workers when `watch.py` says they're done; each trial is on the dataset by then.

**Publish.** Then rebuild the tables, figures, hero, web videos, card and Space from every trial the dataset holds,
on one of the workers, which has ffmpeg and room for the recordings:

```bash
python tools/fleet/hfjob.py <instance> tools/dataset/publish.sh --pull --wait
```

`publish.sh` downloads the runs (not their trajectories), then writes:
- the tables (`tools/dataset/tables.py`);
- the Space, the figures, the hero and the web videos (`tools/space/build.py`);
- the card (`tools/dataset/card.py`);
- and uploads them all.

The card is `tools/dataset/card/README.md` with its slots filled: the latest run's summary (`card/summary.md`, written
by hand for each run), the hero and its caption, the figures, the results, and `card/body.md`.

**Another model or OS.** A new run is a new run id, so its trials go beside the others under `runs/<os>/<run>/`, and
`publish.sh` puts them on the board.

- Give the model's name and price to `tools/space/config.json` (`models`) and to `tools/dataset/export.py`
  (`PRICES`, or `TIERED` for a price that depends on the prompt's size).
- Write the run's `summary.md`.
- A new OS adds its name to `config.json` (`oses`), and any cells that can't pass there to `caveats`.

`tools/space/checks/` holds the headless screenshots used to check the Space in light and dark, at desktop and phone
widths (`npm install`, then `node shoot.mjs jobs.json`), and a static server that serves byte ranges, so videos seek
locally as they do on Hugging Face (`python serve.py <built space> 8000`).

## The task pack

The task pack and the bench's GUI-only task variants are trycua's, under their licence (FSL-1.1-MIT), which travels
with them as `artifacts/taskpack/LICENSE`. This repo holds no copy of them:

- `taskpack.lock.toml` names trycua's repo, a commit, the folders to take and where each lands, and a sha256 over
  them all.
- `python tools/taskpack.py` fetches those files at that commit, checks each against the commit's git tree, and
  checks them all against the lock's sha256 before it replaces `artifacts/taskpack/`. A mismatch changes nothing.
  It writes `MANIFEST.sha256` beside them, in `sha256sum` form.
- `python tools/taskpack.py verify` checks the copy you have against the lock.
- `python tools/taskpack.py pin <commit>` moves the pin to another commit and writes its sha256 to the lock.

The tool uses GitHub's API, which allows few calls without a token; set `GITHUB_TOKEN` if you run it often.

## Tests

```bash
pip install pytest python-xlib==0.33 'agentenv-framework-protocol>=0.1.421' -r tools/dataset/requirements.txt
python tools/taskpack.py            # the sentinel's and the grade's tests score with trycua's files
python -m pytest tests artifacts/taskpack/scoring/tests
```

The sentinel's tests need tkinter.

## Licence

This repo's own files are under the Apache License 2.0 (`LICENSE`). trycua's files, fetched into
`artifacts/taskpack/`, stay under theirs, as do the briefs and system prompt the trials quote. The Space's fonts, Inter
and JetBrains Mono (`tools/space/fonts/`), are under the SIL Open Font License, which travels with them.
`tools/dataset/LICENSE.md` and `licenses/` are the published dataset's licence files.
