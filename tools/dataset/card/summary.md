**On macOS the driver decides whether the user stays undisturbed.** Three computer-use drivers ran trycua's tasks
with the OS, the model, the prompts, the seeds and the grade held fixed, each driver's agent on its own tools alone
(runs `cua-driver-*`, `agent-desktop-*` and `macos-harness-*` of 2026-11-05: Claude Sonnet 5.5 in Claude Code on all
100 trials of Bench v2, Claude Haiku 5.5 on the 70 BenchLab trials, macOS 26 on EC2 Macs). MB-10's and MB-11's
background trials aren't scored (¶). Through the three, Sonnet passes 39 of 50, 35 of 50 and 32 of 50 trials
in the foreground, and 23 of 40, 8 of 40 and 1 of 40 in the background.

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

**Claude Sonnet 5.5 in Claude Code, every trial of Bench v2 on Linux** (run `sonnet-5-5-2026-11-03`: 10 tasks, 5 runs
each, both conditions, on agentenv-framework 0.9.1412, with the tasks, limits and grade of the Haiku 5.5 run). 41 of
the 100 trials pass, as many as Claude Haiku 5.5's (`haiku-5-5-2026-11-02`), for $57.31 at list price against
Haiku's $7.46, and none leaves the GUI. Its mean task score is higher in both conditions.

- **Foreground: 36 of 50, task score 0.86 (Haiku 0.84).** 34 of the 35 precision and interruption trials pass (in
  IR-01's fifth run it submits twice), and 2 of the 15 multi-app trials, G02's fifth run and G04's third. On the
  multi-app tasks it mostly runs out of its 45 turns, with mean task scores of 0.81 (G02), 0.53 (G03) and 0.32 (G04);
  Haiku's were 0.59, 0.45 and 0.32.
- **Background: 5 of 50, all IR-02, task score 0.79 (Haiku 0.69).** It does the task in 14 of the 15 trials of IR-01,
  IR-03 and IR-04, but their modal dialog covers the user's window on Linux, so they can't pass (‡). MB-09 can't
  pass without moving the user's pointer (§), and MB-10's and MB-11's background trials aren't scored (¶); it does
  MB-09 and MB-11 every time, and on MB-10 it clicks the action twice in four runs and without hovering in one. It passes no multi-app task in the background: in 12 of the
  15 trials it stops and reports itself blocked, since the apps refuse input in the background; in 2 of G04's runs
  it brings the apps to the front and finishes the task. It disturbs the user in 9 of the 15 (Haiku 10), and its
  mean task score there is 0.38 (Haiku 0.28).

The Sonnet 4.5 pilot (`sonnet-4-5-2026-11-02`, the three multi-app tasks once per condition, none passing) is in the
tables and the Space, but not on the board.
