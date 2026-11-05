---
title: Cua Driver Bench on AgentEnv
emoji: 🖥️
colorFrom: blue
colorTo: yellow
sdk: static
app_file: index.html
pinned: false
license: apache-2.0
short_description: Replays of computer-use agents on Cua Driver Bench
datasets:
  - earakely-scale/CuaDriverBench-AgentEnv
---

# Cua Driver Bench on AgentEnv

Replays of computer-use agents doing trycua's [Cua Driver Bench](https://github.com/trycua/cua) tasks on
[AgentEnv](https://www.agentenvframework.com) computers: the desktop as recorded, every tool call the agent made, the
simulated user typing in their own window in the background condition, and the grade; and, where several computer-use
drivers ran the same tasks with the same model, the drivers side by side.

The trials, recordings and grades are in the dataset
[earakely-scale/CuaDriverBench-AgentEnv](https://huggingface.co/datasets/earakely-scale/CuaDriverBench-AgentEnv); this
Space streams each trial's web copy from there. The bench port is
[earakely-scale/agentenv-cua-driver-bench](https://github.com/earakely-scale/agentenv-cua-driver-bench).

trycua's tasks, apps, prompts and evaluators are © 2026 Cua AI, Inc., under the Functional Source License 1.1, MIT
Future License. These are not trycua's official results. The Space's own code is Apache-2.0; its fonts, Inter and
JetBrains Mono, are under the SIL Open Font License (`fonts/`).
