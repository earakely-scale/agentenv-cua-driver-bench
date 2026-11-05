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
- n<1K
tags:
- agentenv
- computer-use
- gui-agents
- cua
- benchmark
- multiplayer
- desktop
- linux
- mcp
- claude-code
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

It covers Linux (Ubuntu 24.04) and macOS 26, with Claude in Claude Code. Each run, one model on one operating system at one
commit of the bench, is a folder of its own under `runs/`, so other operating systems and models are added beside it.

These are not trycua's results and are not comparable with them: trycua runs the bench with its own runner, on macOS
and, since 31 October 2026, on Linux too.

## Results

{{SUMMARY}}

{{RESULTS}}

## Quick start

Load the tables:

```python
from datasets import load_dataset

trials = load_dataset("earakely-scale/CuaDriverBench-AgentEnv", "trials", split="eval")   # one row per trial
calls = load_dataset("earakely-scale/CuaDriverBench-AgentEnv", "calls", split="eval")     # one row per tool call
tasks = load_dataset("earakely-scale/CuaDriverBench-AgentEnv", "tasks", split="eval")     # prompts and settings
```

Run a trial yourself, on a Linux machine with Docker (we used an EC2 c6i.4xlarge on Ubuntu 24.04):

```bash
pip install 'agentenv-framework>=0.9.1412'
docker run -d -p 5000:5000 public.ecr.aws/docker/library/registry:2
git clone https://github.com/earakely-scale/agentenv-cua-driver-bench && cd agentenv-cua-driver-bench
python tools/taskpack.py                       # fetch trycua's task pack at the pinned commit
mkdir -p .agentenv && cat > .agentenv/config.toml <<'EOF'
[model]
base_url = "https://your-litellm-or-openai-compatible-proxy"
api_key = "env:LITELLM_API_KEY"
default = "anthropic/claude-sonnet-5-5"
EOF
agent-env run . --task cdb-g02-background      # one trial
agent-env run . --eval bench-v2                # every task of Bench v2 once (76 task files)
```

The first run builds each task's computer (a few minutes); later runs reuse it. `agent-env run . --eval sentinel`
checks, without a model, that every kind of disturbance is caught and scored by trycua's files.

{{BODY}}
