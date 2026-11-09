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
   drivers comparison's trials (`tasks/macos-agent-desktop-*.json`, `tasks/macos-macos-harness-*.json`,
   `tasks/macos-codex-computer-use-*.json`) are those with Vercel Labs' agent-desktop, browser-use's macOS harness or
   OpenAI's Codex Computer Use in cua-driver's place, Codex let act on the task's apps alone, and nothing else changed.
2. Deploy the agent with the computer's driver's MCP server, its own tools alone (on Linux through
   `--set envs/<computer>.tools=driver`, since the Linux task files keep the default, which adds AgentEnv's
   `computer_*` tools), AgentEnv's `peer_agents` server, which no task uses, trycua's system prompt (for "a Linux
   desktop" on Linux, as written on macOS), at most 45 turns and 360 seconds:
   - **Claude Code** for Claude Haiku, Sonnet and Opus 5.5, its built-in tools limited to `Skill` and `Read`, at its
     default effort for these models, medium (no `--effort` is passed).
   - **OpenAI's Codex CLI 0.147.0** for GPT-6 Luna, GPT-6.1 Terra and GPT-6.1 Sol, as AgentEnv's `codex` agent runs
     it (`tasks/codex-*.json`, each its Linux twin but for the agent), every tool of its own off (shell, patch, web
     search, image viewing, plan, sub-agents), which leaves the driver's tools, `peer_agents` and Codex's reads of MCP
     resources, at medium effort, set in the task. Codex has no turn limit of its own: AgentEnv's agent stops it after
     45 tool calls, each one model request, since Codex sends these models no parallel calls.
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
| GUI only | the live guard saw no way out of the GUI, and the trajectory has none of trycua's forbidden tools, no built-in tool beyond `Skill` and `Read` (Codex's own tools read as trycua's runner reads its Codex arm's: a command as `Bash`, a file change as `Edit`, a web search as `WebSearch`, a sub-agent as `Agent`, anything else as `Task`), and no `launch_app` given a command or arguments |
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
results/trials.parquet       one row per trial: model, driver, harness, condition, every half of the grade, A22 criteria, cost, turns, paths, and on_board: whether the board and the Space count it
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
  trajectory.json            Claude Code's stream-json, or Codex's `exec --json` events with the time each arrived, as recorded (screenshots included)
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
- **On macOS, Claude Haiku 5.5 ran the seven BenchLab tasks on 2026-11-05 and the three multi-app tasks on
  2026-11-06** (runs `*-haiku-5-5-2026-11-06-multiapp`), on every driver; Claude Opus 5.5 ran with cua-driver alone.
  GPT-6 ran on Linux alone. The macOS runs used agentenv-framework builds from just before its 0.9.1446 release; each
  run's manifest names its commit.
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
- MB-10 and MB-11 run in the foreground only, as trycua's task manifest lists them ([`taskpack/v2-taskset.json`](https://github.com/trycua/cua/blob/60ed3eb5f038e090629f39687ec8b937724548f9/libs/cua-driver-bench/taskpack/v2-taskset.json), added in
  [trycua/cua#6574](https://github.com/trycua/cua/pull/6574) after the commit this bench pins): a real hover and a native tooltip need the pointer, which in the
  background is the user's. MB-09 runs in both conditions, though in the background its drag keeps the user
  undisturbed only through a driver that drags without moving the user's pointer.
- **GPT-6 in Codex sees cua-driver's screens as text.** Codex sends the model a tool result's structured content
  alone when it has one, so the screenshot that cua-driver's `get_window_state` and `get_desktop_state` return beside
  their accessibility tree never reaches GPT-6; `zoom`'s image does. Every Codex release through 0.167 does this, the
  0.160 trycua's runner pins included, and these runs keep Codex as it ships. Codex 0.147 has no settings for the
  GPT-6 models either, so they run on its generic ones (no code mode, no parallel tool calls, its default
  instructions), as a warning in each trajectory says. trycua's runner has published no Codex numbers, and runs its
  Codex arms on macOS only.
- **Codex Computer Use is OpenAI's app, driven by Claude.** Its rows (run `codex-computer-use-sonnet-5-5-2026-11-09`)
  are the ChatGPT app 26.930.51102's `unified-computer-use` plugin, its `cua_repl` started as the app starts it,
  through AgentEnv's `codex-computer-use` driver, with Claude Sonnet 5.5 in Claude Code writing the JavaScript it
  runs against OpenAI's `cua` API: not OpenAI's own agent or models, and with no ChatGPT sign-in. The driver answers
  each of Codex's requests to act on an app from the task's apps, and keeps Codex's read-only sandbox on its
  JavaScript, where trycua's filter (`codex_cu_filter.py`) turns it off. The GUI-only check reads its `js` as trycua's
  scan reads any tool input, and fails a call that names a Node module, the process, or loads a module. It needs
  agentenv-framework 0.9.1482 or later: on an earlier one macOS's prompt to let Codex's helper bypass the private
  window picker takes the user's focus in the background.
- **Setup differences from trycua's runner**, found auditing these runs and not corrected in them: cua-driver's arm
  offers `run_script`, as trycua's `cc-cua-driver-script` arm does, without the short `run_script` paragraph that arm
  adds to the system prompt; agent-desktop's foreground trials run every command headed, with real pointer and keys,
  where trycua's adapter lets the model ask for that per call (`AD_HEADED=agent`, its default); and browser-use's
  adapter attaches a screenshot to every `get_app_state`, where trycua's sends one on request (`BU_SHOT=ondemand`, its
  default), and its agent spends its first turn reading the skill. Each applies to every trial of its driver.
- Claude Code's `num_turns` counts tool round trips, across a context compaction too, so it passes 45 when the model
  makes several calls in one message; the 45-turn limit holds on `model_calls`, the model's distinct messages.

## Licence and attribution

The tasks, their apps, prompts, evaluators and scoring are trycua's Cua Driver Bench, © 2026 Cua AI, Inc., under the
[Functional Source License 1.1, MIT Future License](licenses/FSL-1.1-MIT.md). Their text and files in this dataset
(the prompts in `tasks/` and wherever they appear in a trajectory, and the workspaces built from their task pack)
stay under it. Everything else (the recordings, trajectories, logs, grades, tables and figures) is under the
[Apache License 2.0](licenses/Apache-2.0.txt), like the bench port itself. See [LICENSE.md](LICENSE.md).
