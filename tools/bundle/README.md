---
license: other
license_name: apache-2.0-and-fsl-1.1-mit
license_link: LICENSE.md
pretty_name: Cua Driver Bench for AgentEnv
tags:
- agentenv
- computer-use
- gui-agents
- cua
- benchmark
- desktop
- linux
- macos
- mcp
---

# Cua Driver Bench for AgentEnv

[trycua](https://github.com/trycua/cua)'s Cua Driver Bench as an [AgentEnv](https://www.agentenvframework.com)
bundle that `agent-env run` runs straight from this repo. An agent shares a desktop with a person: in the
**background** condition someone types in their own window the whole time, and the agent must do its task in the other
windows without taking their focus, raising a window over theirs, moving their pointer, touching their clipboard or
losing one of their keystrokes; in the **foreground** condition the desktop is the agent's alone. Either way it may use
only the GUI.

All ten tasks of trycua's Bench v2, in both conditions, five runs each: the multi-app workflows G02 to G04, and the
BenchLab tasks MB-09 to MB-11 and IR-01 to IR-04. Each trial runs on a computer AgentEnv composes for it, Ubuntu 24.04
or macOS 26, with the task's apps, a computer-use driver and the bench's sentinel, the user's window; it is graded
outside the computer by trycua's own evaluator, A22 criteria and GUI-only scan.

Our runs of it, with every recording, trajectory and grade, are in the dataset
[earakely-scale/CuaDriverBench-AgentEnv](https://huggingface.co/datasets/earakely-scale/CuaDriverBench-AgentEnv) and
its [replay Space](https://huggingface.co/spaces/earakely-scale/CuaDriverBench-AgentEnv). These are not trycua's
results.

## Run it

On Linux, with Docker and a local registry:

```bash
pip install 'agentenv-framework>=0.9.1446'
docker run -d -p 5000:5000 public.ecr.aws/docker/library/registry:2
mkdir -p .agentenv && cat > .agentenv/config.toml <<'EOF'
[model]
base_url = "https://your-litellm-or-openai-compatible-proxy"
api_key = "env:LITELLM_API_KEY"
default = "anthropic/claude-sonnet-5-5"
EOF
agent-env run hf://{{REPO}} --task cdb-g02-background   # one trial
agent-env run hf://{{REPO}} --eval bench-v2             # every task of Bench v2 once
```

On an Apple silicon Mac, the same tasks run on macOS 26, in a logged-in session with
[Lume](https://github.com/trycua/cua/tree/main/libs/lume) on the PATH and a Docker (colima will do) with the same
registry. Add a `[sandbox]` table to the config, then run the `macos-` tasks:

```bash
printf '\n[sandbox]\ndefault = "lume"\n' >> .agentenv/config.toml
agent-env run hf://{{REPO}} --task macos-ir-01-r1-foreground
agent-env run hf://{{REPO}} --eval macos-bench-v2
```

The first run builds each task's computer, a few minutes on Linux and about 7 on macOS, where it first pulls Cua's
macOS base (about 29 GB); later runs reuse it. On an amd64 Linux machine whose Docker can't emulate arm64, the build
also says it "can't build linux/arm64" for each computer: that form is skipped, and the amd64 one runs. On macOS the drivers comparison's trials name their driver:
`macos-agent-desktop-…` for Vercel Labs' agent-desktop, `macos-macos-harness-…` for browser-use's macOS harness, and
`macos-cua-driver-…` for cua-driver on its own tools alone.

To run exactly what this card describes, pin the repo's commit: `hf://{{REPO}}@<commit>`. Each commit of this repo is
the bench at one commit of its [GitHub repo](https://github.com/earakely-scale/agentenv-cua-driver-bench), where its
tooling, tests and history live: this one is
[{{COMMIT}}](https://github.com/earakely-scale/agentenv-cua-driver-bench/commit/{{COMMIT}}).

## Run another driver or tool set

With agentenv-framework 0.9.1453 or later, `--set envs/NAME.KEY=VALUE` changes one of the bench's computer envs for a
single run and leaves the bench as written. Each task deploys one computer env: `desktop-benchlab` for the precision
and interruption tasks on Linux, `desktop-s02`, `desktop-s03` and `desktop-s04` for the multi-app tasks, and the same
names ending in `-macos` on macOS. What a setting changes runs under ids ending in it, such as
`desktop-benchlab(desktop-benchlab.driver reference)`, so its trials stay apart from the bench's own.

```bash
pip install 'agentenv-framework>=0.9.1453'
# Linux: cua-driver on its own tools alone, as the dataset's macOS runs ran it
agent-env run hf://{{REPO}} --task ir-01-r1-background --set envs/desktop-benchlab.tools=driver
# Linux: AgentEnv's reference driver in cua-driver's place
agent-env run hf://{{REPO}} --task ir-01-r1-background --set envs/desktop-benchlab.driver=reference
# macOS: Vercel Labs' agent-desktop, or browser-use's macOS harness, on cua-driver's task and its own tools alone
agent-env run hf://{{REPO}} --task macos-ir-01-r1-background --set envs/desktop-benchlab-macos.driver=agent-desktop \
  --set envs/desktop-benchlab-macos.tools=driver
agent-env run hf://{{REPO}} --task macos-ir-01-r1-background --set envs/desktop-benchlab-macos.driver=macos-harness \
  --set envs/desktop-benchlab-macos.tools=driver
```

`tools` is `standard` (AgentEnv's `computer_*` tools alone), `driver` (the driver's own alone) or `both`, the default;
the Linux runs in the
[CuaDriverBench-AgentEnv dataset](https://huggingface.co/datasets/earakely-scale/CuaDriverBench-AgentEnv) ran with `both`. An eval deploys several envs, so set each one, for example
`--eval bench-v2 --set envs/desktop-benchlab.driver=reference --set envs/desktop-s02.driver=reference
--set envs/desktop-s03.driver=reference --set envs/desktop-s04.driver=reference`. The `macos-agent-desktop-…`,
`macos-macos-harness-…` and `macos-cua-driver-…` task files are these settings written out, and they are what the
dataset's macOS runs ran; in the foreground they also start agent-desktop headed, which `--set` can't. A driver that doesn't run
on the computer, such as macos-harness on Linux, is refused before any task runs.

## What's here

| Path | What it is |
|---|---|
| `bundle.toml` | The bundle, and the agentenv-framework release it needs. |
| `envs/` | The computers (`desktop*`), the apps of each task, trycua's BenchLab and the bench's sentinel. |
| `tasks/` | One trial each: deploy the task's computer and the agent, prompt it in a condition, arm the sentinel, grade. |
| `evals/` | Sets of tasks: all of Bench v2 (`bench-v2`, `macos-bench-v2`), each condition, and smoke checks without a model. |
| `artifacts/` | The grader, the GUI-only check, the sentinel's steps, the checks, and trycua's task pack (`artifacts/taskpack/`). |

`artifacts/taskpack/` is trycua's task pack as published at
[trycua/cua@{{PACK_COMMIT}}](https://github.com/trycua/cua/tree/{{PACK_COMMIT}}/libs/cua-driver-bench), each file as
it is there, sha256 `{{PACK_SHA256}}` over its `MANIFEST.sha256`, with trycua's licence beside it
(`artifacts/taskpack/LICENSE`).

## Licence

The tasks, their apps, prompts, evaluators and scoring are trycua's Cua Driver Bench, © 2026 Cua AI, Inc., under the
[Functional Source License 1.1, MIT Future License](licenses/FSL-1.1-MIT.md), redistributed here for non-commercial
research, a Permitted Purpose under it. Everything else is the bench port's, under the
[Apache License 2.0](licenses/Apache-2.0.txt). See [LICENSE.md](LICENSE.md).
