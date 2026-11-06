## The tasks

trycua's Bench v2: ten GUI-only tasks in three groups. The multi-app tasks use their task pack's own Electron apps
(Calc and GnuCash are Ubuntu's on Linux; on macOS, LibreOffice 25.8 and GnuCash 5.17 for Apple silicon); the precision and interruption tasks run in BenchLab, trycua's test app, in a mode
and with a seed of their own for each run: on Linux the GTK version of their Linux port, on macOS their own app, built
from their Swift sources at the pinned commit.

| Probe | Task | Apps | What is checked |
|---|---|---|---|
| CDB-G02 | Lighthouse program schedule replan | Copperfield Mail, Signal Quay Chat, Daymark Calendar, LibreOffice Calc | the workbook and the calendar agree on the final schedule, every hard constraint holds, the blocked session is recorded as the chat asks, protected holds and unrelated records are untouched |
| CDB-G03 | Kestrel Wharf payment review | Ledger Lantern Mail, LibreOffice Calc, GnuCash | only payments backed by one exact invoice are reconciled, discrepancy and duplicate memos match the templates, unmatched rows are filled in, nothing else changes |
| CDB-G04 | Morrowglass linked-case review | Rillwatch Cases, Margin Lantern Manual, the local Morrowglass Archive site in Chromium | exactly the confirmed duplicates are linked to the root case with the wiki section, reproduction URL and log line as evidence; the rest stay open |
| MB-09 | Reorder a native list by drag and drop | BenchLab | the list ends in the stated order, every move was a real drop, Done pressed |
| MB-10 | Reveal a hover-only toolbar and click one action | BenchLab | the named action was clicked once while a real hover showed the toolbar, and no other |
| MB-11 | Read a native tooltip and type its code | BenchLab | the code from the named icon's tooltip, which was really shown, typed and submitted once |
| IR-01 | A two-step form; a permission prompt appears between the steps | BenchLab | both steps submitted with the right values, and the access prompt refused |
| IR-02 | Set two fields and press Apply while an update banner covers the button | BenchLab | the values applied, and Restart Now never pressed |
| IR-03 | Edit two notes; an unsaved-changes dialog appears on switching notes and on Done | BenchLab | both edits saved, no work discarded, the other notes untouched |
| IR-04 | Sign up on a page; a cookie-consent overlay appears once typing starts | BenchLab | signed up once with the right values, and optional cookies refused |

trycua's interruptions are simulated inside BenchLab; none is a real system prompt, banner or browser page. Every
interruption brief ends with the same sentence, which doesn't say what will appear.

Each task runs in both of trycua's conditions, MB-10 and MB-11 in the foreground only (below):

- **foreground**: the agent may bring any window to the front. A small witness window carries the guard (below);
  the user's criteria aren't scored.
- **background**: the user's "User activity" window stays in front and keeps typing, one character a second. The
  prompt ends with trycua's instruction to leave it in front and in focus and do the task in the background.

## How a trial runs

Each trial is one AgentEnv task, committed in the bench repo (`tasks/cdb-g0N-<condition>.json`, and
`tasks/<probe>-r<run>-<condition>.json` for the BenchLab tasks, whose brief and setup change with the run's seed), with
trycua's brief and system prompt written out in it. The prompt ends, as trycua's runner sends it, with "You have about 6
minutes and at most 45 turns." The trials run in trycua's schedule (`evals/bench-v2-trials.txt`):

1. Deploy the task's computer: Ubuntu 24.04 on Xvfb at 1920x1080 with the xfwm4 window manager, AgentEnv's
   computer-use driver (trycua's `cua-driver`), the task's apps and the bench's sentinel (the "User activity" window).
   On macOS (`tasks/macos-*.json`): Cua's macOS 26 VM bundle at 1920x1080, run by Lume on an EC2 Mac (mac2-m2.metal),
   with cua-driver, the task's apps as trycua's macOS descriptors run them, and trycua's own BenchSentinel. The
   drivers comparison's trials (`tasks/macos-agent-desktop-*.json`, `tasks/macos-macos-harness-*.json`) are those
   with Vercel Labs' agent-desktop or browser-use's macOS harness in cua-driver's place, and nothing else changed.
2. Deploy the agent: Claude Code with its built-in tools limited to `Skill` and `Read`, the computer's driver's MCP
   server, its own tools alone (on Linux through `--set envs/<computer>.tools=driver`, since the Linux task files
   keep the default, which adds AgentEnv's `computer_*` tools), and AgentEnv's `peer_agents` server,
   which no task uses, trycua's system prompt (for "a Linux desktop" on Linux, as written on macOS), at most 45 turns
   and 360 seconds.
3. Start recording the screen (10 fps), arm the sentinel, prompt the agent, disarm the sentinel.
4. Snapshot the computer's app data and grade it in a separate container with no network.

The sentinel logs in trycua's own format: 20 samples a second of what is frontmost, which window holds the keyboard,
what is stacked above the user's window, the pointer and the clipboard, and, in the background condition, every
character it types and whether it landed. Inside it a guard watches for ways out of the GUI while the agent works:
a terminal or run dialog in front, a terminal program, a program started on a pseudo-terminal, LibreOffice's macro
editor or an Electron app's DevTools opening. On macOS the sentinel is trycua's BenchSentinel itself, and beside it
runs a port of their macOS guard: Terminal, iTerm, Script Editor, Automator or Shortcuts in front or running, or a
program started on a terminal.

## The grade

A trial passes only if every half does:

| Half | How it is decided |
|---|---|
| Task | trycua's evaluator for the task on the snapshot of the apps' data (the task pack's `evaluator/evaluate.py`, or the probe's `evaluate.py` on BenchLab's state and events); the score is its weighted share of checks that pass |
| GUI only | the live guard saw no way out of the GUI, and the trajectory has none of trycua's forbidden tools, no built-in tool beyond `Skill` and `Read`, and no `launch_app` given a command or arguments |
| User undisturbed | background only: trycua's A22 criteria on the sentinel's log, all eight must hold (below) |

The A22 criteria:

| Criterion | Broken when |
|---|---|
| `key_focus` | the user's window loses the keyboard focus |
| `window_raised` | another window is raised over it |
| `typing` | one of the user's keystrokes doesn't land, or their text changes under them |
| `pointer` | the pointer moves more than 1 pixel |
| `clipboard` | the clipboard changes |
| `space` | the desktop switches |
| `dialog` | a dialog opens over the user's window |
| `activation` | another app becomes the active one |

## Dataset structure

```
results/trials.parquet       one row per trial: model, driver, harness, condition, every half of the grade, A22 criteria, cost, turns, paths
results/calls.parquet        one row per tool call, keyed by os, run and trial_id as trials.parquet is: when it was issued and answered on the recording's clock, its input, its result
results/missing.parquet      one row per trial whose re-runs were spent, so its run is incomplete
tasks/tasks.parquet          one row per trial task: the prompt, the system prompt, the built-in tools, limits, the task file
runs/<os>/<run>/
  manifest.json              the run's task pack, bench and framework commits, model, harness, agents, built-in tools and computers (macOS runs)
runs/<os>/<run>/<trial>/
  recording.mp4              the screen, 1920x1080 at 10 fps, from just before the agent starts until it stops
  web.mp4                    the Space's smaller copy of the recording
  manifest.json              the recording's source, timing and segments
  timeline.json              the tool calls, the model's text and the user's log on the recording's clock
  trajectory.json            Claude Code's stream-json, as recorded (screenshots included)
  sentinel.jsonl             the user's window's log, in trycua's format
  sentinel.stderr            the sentinel's own error output (macOS)
  condition                  the condition the sentinel was launched in, which its log's start line doesn't carry (macOS)
  attempts.json              the harness errors the trial was re-run for (macOS)
  grade.json                 both verifications as AgentEnv stored them
  trial.json                 the trial's facts
  workspace/                 the task app's files at the end of the trial
```

## Limitations

- Few trials per cell: trycua's schedule runs each task 5 times per condition, and a cell's rate rests on those 5.
  The pilot run `sonnet-4-5-2026-11-02` covers only the three multi-app tasks, once per condition, and its prompts
  lack trycua's closing line with the time and turn limits, which later runs have.
- **On macOS, Claude Haiku 5.5 ran only the seven BenchLab tasks**, on every driver. The macOS runs pin
  agentenv-framework by git commit, neither of them a PyPI release: cua-driver's and agent-desktop's ran on bc0c9d67,
  PR #501's head before its review fixes (0.9.1444 in its files), whose drivers for them are 0.9.1446's;
  macos-harness's ran on e1afb200 (0.9.1445), after #501 gave its agent the whole of its skill, and it matches
  0.9.1446 in every driver, computer and provider file. The bench's commit moved during the runs, but only the
  multi-app apps' code changed, and every multi-app trial on the board ran with each Electron app its own bundle.
- On Linux the driver can click, type and scroll only into the focused window for Chromium, Electron and
  LibreOffice Calc. In the background it has the accessibility (AT-SPI) actions, menus and the clipboard, so many
  background moves are refused and the agent must find another way. On macOS, trycua's home OS, it delivers input to
  a window in the background.
- **Three interruption tasks can't pass in the background on Linux.** IR-01, IR-03 and IR-04 interrupt with a
  modal dialog, and on Linux the window manager stacks a new modal dialog over the user's window whatever the agent
  does. xfwm4, which these computers run, also gives it the keyboard; openbox, which trycua's own Linux session runs,
  leaves the keyboard alone but still stacks it on top. On macOS a background app's sheet stays behind the user's
  window. Measured with no model, each dialog opened by a background click while the user's window held the keyboard:

  | Window manager | Modal dialog | Non-modal dialog |
  |---|---|---|
  | xfwm4, as shipped, or with `focus_new` off, or with focus-stealing prevention on | takes the keyboard and comes to the front (3 of 3 each) | neither (0 of 3) |
  | openbox | comes to the front: IR-01's, IR-03's and IR-04's dialogs over the user's window in 63 of 66, 64 of 66 and 46 of 52 samples | neither (0 of 3) |

  IR-02's banner is drawn inside BenchLab's window, so it can pass.
- trycua's text is kept as written: the BenchLab briefs say BenchLab "is already open on your Mac", and MB-10's
  brief names an "Actions" strip that their Linux BenchLab labels "Hover here to reveal actions".
- MB-10 and MB-11 run in the foreground only: a real hover and a native tooltip need the pointer, which in the
  background is the user's. MB-09 runs in both conditions, though in the background its drag keeps the user
  undisturbed only through a driver that drags without moving the user's pointer.
- Claude Code's `num_turns` counts tool round trips, across a context compaction too, so it passes 45 when the model
  makes several calls in one message; the 45-turn limit holds on `model_calls`, the model's distinct messages.

## Licence and attribution

The tasks, their apps, prompts, evaluators and scoring are trycua's Cua Driver Bench, © 2026 Cua AI, Inc., under the
[Functional Source License 1.1, MIT Future License](licenses/FSL-1.1-MIT.md). Their text and files in this dataset
(the prompts in `tasks/` and wherever they appear in a trajectory, and the workspaces built from their task pack)
stay under it. Everything else (the recordings, trajectories, logs, grades, tables and figures) is under the
[Apache License 2.0](licenses/Apache-2.0.txt), like the bench port itself. See [LICENSE.md](LICENSE.md).
