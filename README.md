# Cua Driver Bench for AgentEnv

[trycua](https://github.com/trycua/cua)'s Cua Driver Bench as an [AgentEnv](https://github.com/scaleapi/agentenv-framework)
bundle: the bench's GUI tasks, run with `agent-env run` on a Linux computer that an agent drives through its
computer-use driver.

**Status:** the bench's computer, its pinned task pack, and the apps of its three shared tasks, each on a computer of
its own, s04's browser included: Chrome for Testing at the build agentenv's `chromium` app pins, pinned again here so
the bench's browser stays the same whatever a framework release ships. Beside each task's app, the bench's sentinel,
with trycua's GUI-only guard in it, and the grade, which scores a trial outside the computer with trycua's own
evaluator, A22 criteria and GUI-only scan. The bench's own tasks come next.

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
| `tests/` | Tests of the fetch tool, of the apps as a computer reads them, of the sentinel and the guard on a fake desktop, and of the grade, offline. |

## Run it

You need Python 3.11 or newer, Docker, and an OCI registry on `localhost:5000`. No model is needed yet.

```bash
pip install 'agentenv-framework>=0.9.1406'
docker run -d -p 5000:5000 public.ecr.aws/docker/library/registry:2
python tools/taskpack.py            # fetch the task pack into artifacts/taskpack/
agent-env run . --eval smoke
agent-env run . --eval apps         # each task's app in its computer
agent-env run . --eval sentinel     # the sentinel and its guard in s02's computer, scored by trycua's files
```

The first run composes the computer: it builds an image of the base with the driver installed, then probes it. That
takes a few minutes; later runs reuse the image. It builds for each arch your Docker can: on an amd64 machine without
arm64 emulation it says it can't build linux/arm64 and goes on with amd64.

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
  `grade.py`, which scores its reward: `sentinel`, its log shows the whole trial; `task`, trycua's evaluator passed;
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

```bash
agent-env run . --task cdb-g02-background
```

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
pip install pytest python-xlib==0.33 'agentenv-framework-protocol>=0.1.421'
python tools/taskpack.py            # the sentinel's and the grade's tests score with trycua's files
python -m pytest tests artifacts/taskpack/scoring/tests
```

The sentinel's tests need tkinter.

## Licence

This repo's own files are under the Apache License 2.0 (`LICENSE`). trycua's files, fetched into
`artifacts/taskpack/`, stay under theirs, as do the briefs and system prompt the trials quote.
