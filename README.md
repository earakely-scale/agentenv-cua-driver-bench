# Cua Driver Bench for AgentEnv

[trycua](https://github.com/trycua/cua)'s Cua Driver Bench as an [AgentEnv](https://github.com/scaleapi/agentenv-framework)
bundle: the bench's GUI tasks, run with `agent-env run` on a Linux computer that an agent drives through its
computer-use driver.

**Status:** the bench's computer and its pinned task pack. The bench's apps, its sentinel, the GUI-only guard,
grading and the bench's own tasks come next.

## What's here

| Path | What it is |
|---|---|
| `envs/desktop/` | The bench's computer: the shipped `ubuntu-24.04` base computer with the shipped `cua-driver` driver, at the 1920x1080 display the bench's tasks assume. |
| `taskpack.lock.toml`, `tools/taskpack.py` | trycua's task pack, pinned to one commit of their repo and a checksum, and the tool that fetches it into `artifacts/taskpack/`. |
| `tasks/probe.json` | Deploys the computer and runs the computer-use conformance probe at `full` against it (`artifacts/check_probe/`). |
| `tasks/taskpack.json` | Loads the task pack into the computer and checks every file arrived intact, against the pack's own manifest. |
| `evals/smoke.toml` | Both tasks. |
| `tests/` | Tests of the fetch tool, offline. |

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
pip install pytest
python -m pytest tests
```

## Licence

This repo's own files are under the Apache License 2.0 (`LICENSE`). trycua's files, fetched into
`artifacts/taskpack/`, stay under theirs.
