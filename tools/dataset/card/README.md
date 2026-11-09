---
license: other
license_name: apache-2.0-and-fsl-1.1-mit
license_link: LICENSE.md
pretty_name: Cua Driver Bench on AgentEnv
language:
- en
task_categories:
- reinforcement-learning
- image-text-to-text
size_categories:
- {{SIZE}}
tags:
- agentenv
- computer-use
- gui-agents
- cua
- benchmark
- multiplayer
- desktop
- linux
- macos
- mcp
- claude-code
- codex
- openai
- anthropic
configs:
- config_name: trials
  default: true
  data_files:
  - split: eval
    path: results/trials.parquet
- config_name: calls
  data_files:
  - split: eval
    path: results/calls.parquet
- config_name: tasks
  data_files:
  - split: eval
    path: tasks/tasks.parquet
viewer: true
---

# Cua Driver Bench on AgentEnv

{{HERO}}

An agent shares a desktop with a person. In the **background** condition someone is typing in their own window,
"User activity", the whole time, and the agent has to do its task in the other windows without
taking their focus, raising a window over theirs, moving their pointer, touching their clipboard or losing one of
their keystrokes. In the **foreground** condition the desktop is the agent's alone. Either way it may use only the
GUI: no terminal, no scripts, no way round the apps.

The tasks, prompts and scoring are [trycua](https://github.com/trycua/cua)'s Cua Driver Bench, all ten tasks of
its Bench v2 (multi-app workflows, precision interactions, interruptions), run on Linux and macOS computers on the [AgentEnv Framework](https://www.agentenvframework.com) by
[earakely-scale/agentenv-cua-driver-bench](https://github.com/earakely-scale/agentenv-cua-driver-bench). Each trial
is graded by trycua's own evaluator, its A22 criteria for an undisturbed user and its GUI-only scan, run outside the
computer. This dataset holds every trial: the screen recording, the agent's full trajectory, the user's log, the
grade and the apps' final files. The [replay Space](https://huggingface.co/spaces/earakely-scale/CuaDriverBench-AgentEnv)
plays each trial with the agent's tool calls and the user's typing beside it.

It covers Linux (Ubuntu 24.04) and macOS 26: Claude Haiku, Sonnet and Opus 5.5 in Claude Code, and on Linux GPT-6
Luna, GPT-6.1 Terra and GPT-6.1 Sol in OpenAI's Codex CLI. Each run, one model through one computer-use driver on one
operating system at one commit of the bench, is a folder of its own under `runs/`, so other operating systems, models
and drivers are added beside it.

These are AgentEnv's runs of trycua's tasks, not trycua's own: trycua runs the bench with its own runner, on macOS,
Linux and Windows, and results from the two runners aren't like-for-like.

## How to run

The bench is on the Hugging Face Hub as an AgentEnv bundle,
[earakely-scale/cua-driver-bench](https://huggingface.co/datasets/earakely-scale/cua-driver-bench), so `agent-env`
runs it by name. On a Linux machine with Docker (we used an EC2 c6i.4xlarge on Ubuntu 24.04) and any
OpenAI-compatible endpoint for the model:

```bash
pip install 'agentenv-framework>=0.9.1454'
export LITELLM_BASE_URL=https://your-litellm-or-openai-compatible-proxy LITELLM_API_KEY=...
# One trial, as the board's Linux rows ran it: cua-driver on its own tools alone
agent-env run hf://earakely-scale/cua-driver-bench --task cdb-g02-background --model anthropic/claude-sonnet-5-5 \
  --set envs/desktop-s02.tools=driver
# Every task of Bench v2 once, the same way
agent-env run hf://earakely-scale/cua-driver-bench --eval bench-v2 --model anthropic/claude-sonnet-5-5 \
  --set envs/desktop-benchlab.tools=driver \
  --set envs/desktop-s02.tools=driver --set envs/desktop-s03.tools=driver --set envs/desktop-s04.tools=driver
# GPT-6 in OpenAI's Codex CLI
agent-env run hf://earakely-scale/cua-driver-bench --task codex-cdb-g02-background --model openai/gpt-6.1-sol \
  --set envs/desktop-s02.tools=driver
# Vercel Labs' agent-desktop in cua-driver's place, as the Linux drivers comparison ran it (0.9.1456 or later)
agent-env run hf://earakely-scale/cua-driver-bench --task agent-desktop-cdb-g02-background --model anthropic/claude-sonnet-5-5
```

The first run builds each task's computer, a few minutes; later runs reuse it. On an Apple silicon Mac the same tasks
run on macOS 26 (we used EC2 mac2-m2.metal hosts), in a logged-in session with
[Lume](https://github.com/trycua/cua/tree/main/libs/lume) on the PATH and a Docker (colima will do). Select the
Lume sandbox in a two-line config, `[sandbox]` with `default = "lume"` in `.agentenv/config.toml`, and run the
`macos-` tasks: `macos-cua-driver-…` for cua-driver on its own tools, `macos-agent-desktop-…` for Vercel Labs'
agent-desktop, `macos-macos-harness-…` for browser-use's macOS harness and `macos-codex-computer-use-…` for OpenAI's
Codex Computer Use (agentenv-framework 0.9.1482 or later), as the drivers comparison ran them, for
example `agent-env run hf://earakely-scale/cua-driver-bench --task macos-agent-desktop-ir-01-r1-background --model
anthropic/claude-sonnet-5-5`.

On Windows 11 the same tasks run as the `windows-` tasks, on a Linux machine with KVM (we used EC2 c8i hosts with
nested virtualization) and Docker with a registry on `localhost:5000`, with agentenv-framework 0.9.1480 or later, as the
board's Windows rows ran them, for example `agent-env run hf://earakely-scale/cua-driver-bench --task
windows-ir-01-r1-background --model anthropic/claude-sonnet-5-5 --set envs/desktop-benchlab-windows.tools=driver`. The
first run fetches Microsoft's 90-day evaluation of Windows 11 Enterprise and installs it unattended, about 13 minutes,
then composes the task's computer, 7 to 9 minutes; whether the evaluation's terms allow your use is yours to check.

Load our results:

```python
from datasets import load_dataset

trials = load_dataset("earakely-scale/CuaDriverBench-AgentEnv", "trials", split="eval")   # one row per trial
calls = load_dataset("earakely-scale/CuaDriverBench-AgentEnv", "calls", split="eval")     # one row per tool call
tasks = load_dataset("earakely-scale/CuaDriverBench-AgentEnv", "tasks", split="eval")     # prompts and settings
board = trials.filter(lambda t: t["on_board"])   # the trials the card's board and the replay Space count
```

Running from a clone of the bench, other drivers and tool sets, and the sentinel's own checks are
[further down](#running-from-a-clone).

{{PAIRS}}## Results

{{SUMMARY}}

{{RESULTS}}

{{COMPARE}}

{{DRIVERS}}

{{FAILURES}}

{{GALLERY}}

{{PARTIAL}}

## Running from a clone

The [bench's GitHub repo](https://github.com/earakely-scale/agentenv-cua-driver-bench) holds the same bundle with its
tooling and tests; `agent-env run .` in a clone takes the same arguments as `hf://` above. On Linux:

```bash
pip install 'agentenv-framework>=0.9.1412'
git clone https://github.com/earakely-scale/agentenv-cua-driver-bench && cd agentenv-cua-driver-bench
python tools/taskpack.py                       # fetch trycua's task pack at the pinned commit
export LITELLM_BASE_URL=https://your-litellm-or-openai-compatible-proxy LITELLM_API_KEY=...
agent-env run . --task cdb-g02-background --model anthropic/claude-sonnet-5-5   # one trial
agent-env run . --eval bench-v2 --model anthropic/claude-sonnet-5-5           # every task of Bench v2 once
```

The board's Linux rows run each trial with cua-driver's own tools alone, `--set envs/<computer>.tools=driver` (below).
GPT-6 runs in Codex through the `codex-` task files, each its Linux twin with AgentEnv's `codex` agent:

```bash
pip install 'agentenv-framework>=0.9.1454'
agent-env run . --task codex-cdb-g02-background --model openai/gpt-6.1-sol --set envs/desktop-s02.tools=driver
```

The first run builds each task's computer (a few minutes); later runs reuse it. `agent-env run . --eval sentinel`
checks, without a model, that every kind of disturbance is caught and scored by trycua's files.

On an Apple silicon Mac, the tasks run on macOS 26 (we used EC2 mac2-m2.metal hosts). `agent-env` must run in
a logged-in session, with [Lume](https://github.com/trycua/cua/tree/main/libs/lume) on the PATH and a Docker (colima
will do):

```bash
pip install 'agentenv-framework>=0.9.1446'
mkdir -p .agentenv && printf '[sandbox]\ndefault = "lume"\n' > .agentenv/config.toml   # only a config picks the sandbox
export LITELLM_BASE_URL=https://your-litellm-or-openai-compatible-proxy LITELLM_API_KEY=...
agent-env run . --task macos-ir-01-r1-foreground --model anthropic/claude-sonnet-5-5   # one trial
agent-env run . --eval macos-bench-v2 --model anthropic/claude-sonnet-5-5              # every task of Bench v2 once
```

The first run pulls Cua's macOS base (about 29 GB) and composes the task's computer, about 7 minutes. The drivers
comparison's trials name their driver: `macos-agent-desktop-ir-01-r1-foreground`, `macos-macos-harness-…`,
`macos-codex-computer-use-…`, and cua-driver on its own tools alone, `macos-cua-driver-…`.

On Windows 11, the tasks run in a VM of Microsoft's evaluation of Windows 11 Enterprise on a Linux amd64 machine with
KVM (`/dev/kvm`), Docker and a registry on `localhost:5000`:

```bash
pip install 'agentenv-framework>=0.9.1480'
docker run -d -p 5000:5000 public.ecr.aws/docker/library/registry:2
export LITELLM_BASE_URL=https://your-litellm-or-openai-compatible-proxy LITELLM_API_KEY=...
agent-env run . --task windows-ir-01-r1-foreground --model anthropic/claude-sonnet-5-5 \
  --set envs/desktop-benchlab-windows.tools=driver                                       # one trial
agent-env run . --eval windows-bench-v2 --model anthropic/claude-sonnet-5-5 \
  --set envs/desktop-benchlab-windows.tools=driver --set envs/desktop-s02-windows.tools=driver \
  --set envs/desktop-s03-windows.tools=driver --set envs/desktop-s04-windows.tools=driver  # every task of Bench v2 once
```

The first run fetches the evaluation's ISO and installs Windows unattended, about 13 minutes, then composes the task's
computer, 7 to 9 minutes; later runs reuse both.

### Run another driver or tool set

With agentenv-framework 0.9.1453 or later, `--set envs/NAME.KEY=VALUE` changes one of the bench's computer envs for a
single run and leaves the bench as written. Each task deploys one computer env: `desktop-benchlab` for the precision
and interruption tasks on Linux, `desktop-s02`, `desktop-s03` and `desktop-s04` for the multi-app tasks, and the same
names ending in `-macos` on macOS and `-windows` on Windows. What a setting changes runs under ids ending in it, such as
`desktop-benchlab(desktop-benchlab.driver reference)`, so its trials stay apart from the bench's own.

```bash
pip install 'agentenv-framework>=0.9.1453'
# Linux: cua-driver on its own tools alone, as every row on the board ran it
agent-env run . --task ir-01-r1-background --set envs/desktop-benchlab.tools=driver
# Linux: AgentEnv's reference driver in cua-driver's place
agent-env run . --task ir-01-r1-background --set envs/desktop-benchlab.driver=reference
# macOS: Vercel Labs' agent-desktop, or browser-use's macOS harness, on cua-driver's task and its own tools alone
agent-env run . --task macos-ir-01-r1-background --set envs/desktop-benchlab-macos.driver=agent-desktop \
  --set envs/desktop-benchlab-macos.tools=driver
agent-env run . --task macos-ir-01-r1-background --set envs/desktop-benchlab-macos.driver=macos-harness \
  --set envs/desktop-benchlab-macos.tools=driver
```

`tools` is `standard` (AgentEnv's `computer_*` tools alone), `driver` (the driver's own alone) or `both`, the default;
the Linux and Windows rows on the board ran with `driver`, and the first Linux runs, which stay in the dataset, with `both`. An eval deploys several envs, so set each one, for example
`--eval bench-v2 --set envs/desktop-benchlab.driver=reference --set envs/desktop-s02.driver=reference
--set envs/desktop-s03.driver=reference --set envs/desktop-s04.driver=reference`. The `macos-agent-desktop-…`,
`macos-macos-harness-…`, `macos-codex-computer-use-…` and `macos-cua-driver-…` task files are these settings written
out, and they are what the macOS rows ran; in the foreground they also start agent-desktop headed, and Codex's trials
name the apps it may act on, which `--set` can't. A driver that doesn't run
on the computer, such as macos-harness on Linux, is refused before any task runs.

{{BODY}}
