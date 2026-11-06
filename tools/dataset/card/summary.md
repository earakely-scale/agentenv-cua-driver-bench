**On macOS the driver decides whether the user stays undisturbed.** Three computer-use drivers ran trycua's tasks
with the OS, the model, the prompts, the seeds and the grade held fixed, each driver's agent on its own tools alone
(runs `cua-driver-*`, `agent-desktop-*` and `macos-harness-*` of 2026-11-05: Claude Sonnet 5.5 in Claude Code on all
90 trials of Bench v2, Claude Haiku 5.5 on the 60 BenchLab trials, macOS 26 on EC2 Macs). Through the three, Sonnet
passes 39 of 50, 35 of 50 and 32 of 50 trials in the foreground, and 23 of 40, 8 of 40 and 1 of 40 in the background.

- **cua-driver (trycua): Sonnet 39 of 50 in the foreground and 23 of 40 in the background, Haiku 35 of 35 and
  16 of 25.** It never takes the user's keyboard, and raises a window over theirs in 6 of 65 background trials.
  Its background misses are the tasks: MB-09's drag moves the user's pointer (§), and it passes 1 of the 10 G02 and
  G03 trials, five of the others ending on the 45-turn limit.
- **agent-desktop (Vercel Labs): Sonnet 35 of 50 and 8 of 40, Haiku 32 of 35 and 10 of 25.** With Sonnet it passes
  every BenchLab trial in the foreground and none of the 15 multi-app ones, running out of its 45 turns in all of
  them: it makes about 75 tool calls a trial, against cua-driver's 52 and browser-use's 43, and loses turns to
  element references that go stale after each change and to its own checks, which refuse clicks they judge covered
  and report values the Electron apps didn't take. In the background it disturbs the user in 19 of Sonnet's 40
  trials, mostly taking their keyboard or raising a window over theirs.
- **browser-use (macos-harness): Sonnet 32 of 50 and 1 of 40, Haiku 21 of 35 and 1 of 25.** It is the only
  driver to pass G04 every time in the foreground (5 of 5, chaining a few commands in each call), but it has
  no hover, so MB-10 and MB-11 fail. In the background it does the task in 32 of Sonnet's 40 trials and still
  disturbs the user in 39 of them: its set_value, click, drag and key commands bring the app forward over the
  user's window.

Two macOS runs of 2026-11-06 join the board as their trials arrive, each row marked incomplete until all are in:
Claude Opus 5.5 with cua-driver on every trial (`cua-driver-opus-5-5-2026-11-06`), and Claude Haiku 5.5 on the three
multi-app tasks with each driver (`*-haiku-5-5-2026-11-06-multiapp`).

cua-driver's first macOS runs, which also offered its agents seven of AgentEnv's `computer_*` tools beside its own,
stay in the dataset (`sonnet-5-5-2026-11-05`, `sonnet-5-5-2026-11-05-multiapp`, `haiku-5-5-2026-11-05`) but not on
the board.

**Six models on Linux, each through cua-driver on its own tools, every trial of Bench v2** (runs
`cua-driver-*-2026-11-06`, Ubuntu 24.04 on EC2, `--set envs/<computer>.tools=driver`): Claude Haiku, Sonnet and Opus 5.5
in Claude Code, and GPT-6 Luna, GPT-6.1 Terra and GPT-6.1 Sol in OpenAI's Codex CLI, all at medium effort. Some GPT-6 trials are still arriving; a row is final at 90 trials.

| Model | Harness | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Sonnet 5.5 | Claude Code | 42 of 50 | 5 of 40 | 7 of 15 | 15 of 15 | 20 of 20 | 1 | $0.56 |
| Claude Opus 5.5 | Claude Code | 38 of 50 | 5 of 40 | 7 of 15 | 11 of 15 | 20 of 20 | 2 | $0.82 |
| Claude Haiku 5.5 | Claude Code | 34 of 50 | 5 of 40 | 0 of 15 | 14 of 15 | 20 of 20 | 3 | $0.07 |
| GPT-6.1 Sol | Codex CLI | 24 of 46 | 5 of 35 | 3 of 11 | 1 of 15 | 20 of 20 | 2 | $0.18 |
| GPT-6.1 Terra | Codex CLI | 24 of 44 | 5 of 33 | 1 of 11 | 6 of 15 | 17 of 18 | 2 | $0.11 |
| GPT-6 Luna | Codex CLI | 16 of 31 | 4 of 26 | 0 of 8 | 8 of 12 | 8 of 11 | 0 | $0.02 |

- **On Linux the background doesn't separate the models: each passes IR-02's five background trials and no other.**
  IR-01, IR-03 and IR-04 interrupt with a modal dialog that Linux's window manager stacks over the user's window (‡),
  and in the multi-app tasks the Electron apps, Chromium and Calc refuse cua-driver's background input, so the agents
  stop and report themselves blocked, or bring a window forward and disturb the user.
- **In the foreground Claude Sonnet 5.5 leads with 42 of 50, then Opus with 38 and Haiku with
  34.** All three pass every interruption trial. Sonnet passes 15 of 15 precision trials, Haiku
  14 of 15, and Opus 11 of 15, missing MB-10's hover toolbar in 4 of
  5. On the multi-app tasks Sonnet and Opus pass 7 and 7 of 15, Haiku 0.
- **GPT-6 in Codex works from the accessibility tree alone, and it shows on the tasks that need the screen.** Codex sends
  the model cua-driver's structured results without their screenshots, so GPT-6.1 Sol passes 20 of 20
  interruption trials but 1 of 15 precision trials, where the hover toolbar, the tooltip and the drag
  targets show only on screen; Terra passes 6 of 15 of those and Luna 8 of 12. Their multi-app
  passes: Sol 3, Terra 1, Luna 0.
- **10 trials leave the GUI, each through cua-driver's `launch_app`** (Haiku 3, Opus 2, Sol 2, Terra 2, Sonnet 1). Most open a
  file by handing it to an app on the command line: the GPT-6.1 models G02's workbook in LibreOffice, Claude G04's access
  log in a text editor. Two, Sonnet's and Opus's in G04's background, run a shell command with `sh -c`, copying the log
  and fetching the archive page into /tmp.
- **Cost per trial at list price** runs from $0.02 (Luna) and $0.07 (Haiku) to $0.82 (Opus); Sonnet
  costs $0.56, Sol $0.18 and Terra $0.11.

cua-driver's first Linux runs, which also offered its agents AgentEnv's seven `computer_*` tools beside its own 66,
stay in the dataset but not on the board: Claude Sonnet 5.5 (`sonnet-5-5-2026-11-03`) passed 36 of 50 in the
foreground, 2 of them multi-app, and 5 of 40 in the background, Claude Haiku 5.5 (`haiku-5-5-2026-11-02`) 36 of 50
and 5 of 40, and the Claude Sonnet 4.5 pilot (`sonnet-4-5-2026-11-02`, the three multi-app tasks once per condition)
none.
