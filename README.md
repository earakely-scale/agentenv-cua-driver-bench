# Cua Driver Bench for AgentEnv

[trycua](https://github.com/trycua/cua)'s Cua Driver Bench as an [AgentEnv](https://github.com/scaleapi/agentenv-framework)
bundle: the bench's GUI tasks, run with `agent-env run` on a Linux computer that an agent drives through its
computer-use driver.

**Status:** the bench's computer, its pinned task pack, and the apps of its three shared tasks, each on a computer of
its own. The bench's sentinel, the GUI-only guard, grading and the bench's own tasks come next, and s04's browser joins
once the computer has one.

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
| `tests/` | Tests of the fetch tool and of the apps as a computer reads them, offline. |

## Run it

You need Python 3.11 or newer, Docker, and an OCI registry on `localhost:5000`. No model is needed yet.

```bash
pip install 'agentenv-framework>=0.9.1406'
docker run -d -p 5000:5000 public.ecr.aws/docker/library/registry:2
python tools/taskpack.py            # fetch the task pack into artifacts/taskpack/
agent-env run . --eval smoke
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
pip install pytest 'agentenv-framework-protocol>=0.1.421'
python -m pytest tests
```

## Licence

This repo's own files are under the Apache License 2.0 (`LICENSE`). trycua's files, fetched into
`artifacts/taskpack/`, stay under theirs.
