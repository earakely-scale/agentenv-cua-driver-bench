**On Windows, Claude Sonnet 5.5 through cua-driver passes 35 of 50 in the foreground and 11 of 40 in the background**
(run `cua-driver-sonnet-5-5-2026-11-09`: every trial of Bench v2 on Windows 11 Enterprise evaluation, 25H2, under
QEMU/KVM on EC2, cua-driver on its own tools, `--set envs/<computer>.tools=driver`), beside the same model and driver
on Linux and macOS:

| OS | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---:|---:|---:|---:|---:|---:|---:|
| Windows | 35 of 50 | 11 of 40 | 2 of 15 | 15 of 15 | 18 of 20 | 1 | $0.66 |
| Linux | 42 of 50 | 5 of 40 | 7 of 15 | 15 of 15 | 20 of 20 | 1 | $0.56 |
| macOS | 39 of 50 | 23 of 40 | 4 of 15 | 15 of 15 | 20 of 20 | 0 | $0.65 |

- **In the background Windows falls between Linux and macOS.** IR-01's, IR-03's and IR-04's modal dialogs take the
  user's keyboard and activation when they open, as on Linux, so IR-01 and IR-03 pass none of their five and IR-04
  one. MB-09's drag passes all five, where on Linux and macOS it moves the user's pointer (§), and IR-02 passes all
  five. No multi-app trial passes in the background.
- **The multi-app tasks run out of turns.** 23 of the 30 end on trycua's 45-turn limit. Sonnet makes about 44 model
  calls a multi-app trial on Windows against 37 on Linux, at about 1.4 tool calls a call on both. G04 passes 2 of 5 in
  the foreground and G02 none; G03 scores 0.45 every time, as on Linux and macOS.
- **In the foreground every precision trial passes, and 18 of 20 interruption trials**: IR-04 fails its task twice.
- **One trial leaves the GUI**: G04's third background run opens the access log by handing it to Notepad on the
  command line through cua-driver's `launch_app`.

Before the run, LibreOffice's welcome dialog and GnuCash's tip of the day were turned off on Windows, as Linux's are;
the macOS cua-driver run above still opened LibreOffice's welcome dialog in 6 of its 30 multi-app trials. cua-driver's
first Windows run, which also offered its agents AgentEnv's `computer_*` tools beside its own, stays in the dataset
but not on the board (`sonnet-5-5-2026-11-09`, 63 trials).

**On macOS the driver decides whether the user stays undisturbed.** Four computer-use drivers ran trycua's tasks
with the OS, the model, the prompts, the seeds and the grade held fixed, each driver's agent on its own tools alone
(runs `cua-driver-*`, `agent-desktop-*` and `macos-harness-*` of 2026-11-05: Claude Sonnet 5.5 in Claude Code on all
90 trials of Bench v2, Claude Haiku 5.5 on all 90 as well, its multi-app tasks run on 2026-11-06; and
`codex-computer-use-sonnet-5-5-2026-11-09`, Sonnet alone; macOS 26 on EC2 Macs). Through the four, Sonnet passes 39,
35, 32 and 26 of 50 trials in the foreground, and 23, 8, 1 and 11 of 40 in the background.

- **cua-driver (trycua): Sonnet 39 of 50 in the foreground and 23 of 40 in the background, Haiku 38 of 50 and 18 of 40.** Of 80 background trials it takes the user's keyboard in 1 and raises a window over theirs in 7.
  Its background misses are the tasks: MB-09's drag moves the user's pointer (§), and it passes 1 of the 10 G02 and
  G03 trials, five of the others ending on the 45-turn limit.
- **agent-desktop (Vercel Labs): Sonnet 35 of 50 and 8 of 40, Haiku 32 of 50 and 10 of 40.** With Sonnet it passes
  every BenchLab trial in the foreground and none of the 15 multi-app ones, running out of its 45 turns in all of
  them: it makes about 75 tool calls a trial, against cua-driver's 52 and browser-use's 43, and loses turns to
  element references that go stale after each change and to its own checks, which refuse clicks they judge covered
  and report values the Electron apps didn't take. In the background it disturbs the user in 19 of Sonnet's 40
  trials, mostly taking their keyboard or raising a window over theirs.
- **browser-use (macos-harness): Sonnet 32 of 50 and 1 of 40, Haiku 26 of 50 and 1 of 40.** With Codex Computer Use, it
  is one of two drivers to pass G04 every time in the foreground (5 of 5, chaining a few commands in each call), but it
  has no hover, so MB-10 and MB-11 fail. In the background it does the task in 32 of Sonnet's 40 trials and still
  disturbs the user in 39 of them: its set_value, click, drag and key commands bring the app forward over the user's
  window.
- **Codex Computer Use (OpenAI), driven by Claude: Sonnet 26 of 50 in the foreground and 11 of 40 in the
  background.** It is the ChatGPT app's Computer Use plugin at 26.930.51102, with no ChatGPT sign-in: Claude writes
  the JavaScript it runs against OpenAI's `cua` API, and Codex may act on the task's apps alone. In the background it
  does the task in 31 of 40 trials and still disturbs the user in 29: Codex raises the window it acts on over the
  user's, its own "ChatGPT Computer Use" window sits above theirs while it works, and GnuCash takes the user's
  keyboard in 4 of G03's 5. In the foreground it passes 19 of 20 interruption trials and G04 every time, but neither
  G02 nor G03; its API has no hover, so MB-10 and MB-11 fail, and it passes MB-09's drag 2 of 5. 21 of its 90 trials
  end on the 45-turn limit, none leaves the GUI, and a trial costs $0.34 at list price.
- **Codex Computer Use with OpenAI's model: GPT-6.1 Sol in Codex CLI passes 28 of 50 in the foreground and 8 of 40
  in the background** (run `codex-computer-use-gpt-6-1-sol-2026-11-09`, Codex CLI 0.147.0 at medium effort), against
  Sonnet's 26 and 11 through the same driver, at $0.10 a trial against $0.34. In the foreground it passes MB-09's drag
  every time, 4 of G04's 5 and 3 of G02's, but 1 of IR-02's 5: it chooses a menu item and presses Apply in one call,
  and Apply lands before the choice. It stops and reports itself blocked in 36 of its 90 trials rather than disturb
  the user or guess: wherever Codex's drag would bring BenchLab forward (all five of MB-09's background trials), where
  GnuCash shows Codex no ledger controls (all ten of G03's), and where MB-10 and MB-11 need the hover Codex hasn't. In
  the background Codex still raises a window over the user's in 24 of 40. One trial leaves the GUI: in G04's
  background GPT imports Node's `fs` through `js` and reads the task's files, and the trajectory check fails it. None
  ends on the turn limit.

**Claude Opus 5.5 with cua-driver** (run `cua-driver-opus-5-5-2026-11-06`) passes 44 of 50 in the foreground and 23 of 40 in the background, against Sonnet's 39 of 50 and 23 of 40.

cua-driver's first macOS runs, which also offered its agents seven of AgentEnv's `computer_*` tools beside its own,
stay in the dataset (`sonnet-5-5-2026-11-05`, `sonnet-5-5-2026-11-05-multiapp`, `haiku-5-5-2026-11-05`) but not on
the board.

**Six models on Linux, each through cua-driver on its own tools, every trial of Bench v2** (runs
`cua-driver-*-2026-11-06`, Ubuntu 24.04 on EC2, `--set envs/<computer>.tools=driver`): Claude Haiku, Sonnet and Opus 5.5
in Claude Code, and GPT-6 Luna, GPT-6.1 Terra and GPT-6.1 Sol in OpenAI's Codex CLI, all at medium effort.

| Model | Harness | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Sonnet 5.5 | Claude Code | 42 of 50 | 5 of 40 | 7 of 15 | 15 of 15 | 20 of 20 | 1 | $0.56 |
| Claude Opus 5.5 | Claude Code | 38 of 50 | 5 of 40 | 7 of 15 | 11 of 15 | 20 of 20 | 2 | $0.82 |
| Claude Haiku 5.5 | Claude Code | 34 of 50 | 5 of 40 | 0 of 15 | 14 of 15 | 20 of 20 | 3 | $0.07 |
| GPT-6.1 Sol | Codex CLI | 26 of 50 | 5 of 40 | 5 of 15 | 1 of 15 | 20 of 20 | 2 | $0.19 |
| GPT-6.1 Terra | Codex CLI | 26 of 50 | 5 of 40 | 1 of 15 | 6 of 15 | 19 of 20 | 3 | $0.11 |
| GPT-6 Luna | Codex CLI | 26 of 50 | 5 of 40 | 1 of 15 | 10 of 15 | 15 of 20 | 1 | $0.02 |

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
  targets show only on screen; Terra passes 6 of 15 of those and Luna 10 of 15. Their multi-app
  passes: Sol 5, Terra 1, Luna 1.
- **12 trials leave the GUI, each through cua-driver's `launch_app`** (Haiku 3, Terra 3, Opus 2, Sol 2, Sonnet 1, Luna 1). Most open a
  file by handing it to an app on the command line: the GPT-6 models G02's workbook in LibreOffice, Claude G04's access
  log in a text editor. Two, Sonnet's and Opus's in G04's background, run a shell command with `sh -c`, copying the log
  and fetching the archive page into /tmp.
- **Cost per trial at list price** runs from $0.02 (Luna) and $0.07 (Haiku) to $0.82 (Opus); Sonnet
  costs $0.56, Sol $0.19 and Terra $0.11.

**Two drivers on Linux, Claude Sonnet 5.5 through each on its own tools, every trial of Bench v2** (runs
`cua-driver-sonnet-5-5-2026-11-06` and `agent-desktop-sonnet-5-5-2026-11-06`; Vercel Labs' agent-desktop 1.2.0 headed
in the foreground and headless in the background, as on macOS):

| Driver | Foreground | Background | Multi-app (fg) | Cost per trial |
|---|---:|---:|---:|---:|
| cua-driver | 42 of 50 | 5 of 40 | 7 of 15 | $0.56 |
| agent-desktop | 39 of 50 | 5 of 40 | 4 of 15 | $0.29 |

- **In the background the window manager decides, not the driver: both pass IR-02's five trials and no other.**
  agent-desktop disturbs the user only in the three dialog tasks (‡), where every driver does; elsewhere, unable to
  reach an app without bringing it forward, it stops and reports itself blocked (18 trials, 9 of them after
  agent-desktop refused background input). cua-driver, beside those dialogs, disturbs the user 7 times and leaves the
  GUI once.
- **In the foreground cua-driver passes 42 of 50 and agent-desktop 39.** Both pass every precision and interruption
  trial; on the multi-app tasks agent-desktop runs out of turns, passing CDB-G04 4 of 5 and neither G02 nor G03, where
  cua-driver passes G02 3 of 5 and G04 4 of 5.
- **agent-desktop costs about half as much a trial**, $0.29 against $0.56.

cua-driver's first Linux runs, which also offered its agents AgentEnv's seven `computer_*` tools beside its own 66,
stay in the dataset but not on the board: Claude Sonnet 5.5 (`sonnet-5-5-2026-11-03`) passed 36 of 50 in the
foreground, 2 of them multi-app, and 5 of 40 in the background, Claude Haiku 5.5 (`haiku-5-5-2026-11-02`) 36 of 50
and 5 of 40, and the Claude Sonnet 4.5 pilot (`sonnet-4-5-2026-11-02`, the three multi-app tasks once per condition)
none.
