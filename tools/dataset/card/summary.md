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
  them: it makes about 75 tool calls a trial, against cua-driver's 52 and macos-harness's 43, and loses turns to
  element references that go stale after each change and to its own checks, which refuse clicks they judge covered
  and report values the Electron apps didn't take. In the background it disturbs the user in 19 of Sonnet's 40
  trials, mostly taking their keyboard or raising a window over theirs.
- **macos-harness (browser-use): Sonnet 32 of 50 and 1 of 40, Haiku 21 of 35 and 1 of 25.** It is the only
  driver to pass G04 every time in the foreground (5 of 5, chaining a few commands in each call), but it has
  no hover, so MB-10 and MB-11 fail. In the background it does the task in 32 of Sonnet's 40 trials and still
  disturbs the user in 39 of them: its set_value, click, drag and key commands bring the app forward over the
  user's window.

cua-driver's first macOS runs, which also offered its agents seven of AgentEnv's `computer_*` tools beside its own,
stay in the dataset (`sonnet-5-5-2026-11-05`, `sonnet-5-5-2026-11-05-multiapp`, `haiku-5-5-2026-11-05`) but not on
the board.

**cua-driver on its own tools, every trial of Bench v2 on Linux** (run `cua-driver-sonnet-5-5-2026-11-06`: Claude
Sonnet 5.5 in Claude Code, 10 tasks, 5 runs each, on agentenv-framework 0.9.1453 with
`--set envs/<computer>.tools=driver`, Ubuntu 24.04 on EC2). 47 of its 90 trials pass, for $50.14 at list price, and
none leaves the GUI.

- **Foreground: 42 of 50, task score 0.92.** Every precision and interruption trial passes (35 of 35), and 7 of the
  15 multi-app trials: G02 3 of 5, G03 none, G04 4 of 5. Its 8 misses all end on the 45-turn limit.
- **Background: 5 of 40, all IR-02, task score 0.63.** It does the task in all 15 trials of IR-01, IR-03 and IR-04,
  but their modal dialog covers the user's window on Linux, so they can't pass (‡). cua-driver's drag on Linux needs
  the focus: in MB-09 the agent stops and reports itself blocked in 4 of 5 runs, and in the fifth drags in the
  foreground and disturbs the user (§). It passes no multi-app task and reports itself blocked in all 15, since the
  apps refuse background input, though it raises a window over the user's in all five G04 runs. It disturbs the user
  in 23 of the 40 trials.

cua-driver's first Linux runs, which also offered its agents AgentEnv's seven `computer_*` tools beside its own 66,
stay in the dataset but not on the board: Claude Sonnet 5.5 (`sonnet-5-5-2026-11-03`) passed 36 of 50 in the
foreground, 2 of them multi-app, and 5 of 40 in the background, Claude Haiku 5.5 (`haiku-5-5-2026-11-02`) 36 of 50
and 5 of 40, and the Claude Sonnet 4.5 pilot (`sonnet-4-5-2026-11-02`, the three multi-app tasks once per condition)
none.
