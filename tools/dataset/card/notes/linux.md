**Eight models on Linux, each through cua-driver on its own tools, every trial of Bench v2** (runs
`cua-driver-*-2026-11-06`, and `cua-driver-fable-5-2-2026-11-10` and `cua-driver-gpt-6-astra-2026-11-10` on
agentenv-framework 0.9.1500; Ubuntu 24.04 on EC2, `--set envs/<computer>.tools=driver`): Claude Fable 5.2 and Claude
Haiku, Sonnet and Opus 5.5 in Claude Code, at its default effort, and GPT-6 Astra, GPT-6 Luna, GPT-6.1 Terra and GPT-6.1
Sol in OpenAI's Codex CLI at medium effort.

| Model | Harness | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Fable 5.2 | Claude Code | 43 of 50 | 5 of 40 | 9 of 15 | 15 of 15 | 19 of 20 | 0 | $0.80 |
| Claude Sonnet 5.5 | Claude Code | 42 of 50 | 5 of 40 | 7 of 15 | 15 of 15 | 20 of 20 | 1 | $0.56 |
| Claude Opus 5.5 | Claude Code | 38 of 50 | 5 of 40 | 7 of 15 | 11 of 15 | 20 of 20 | 2 | $0.82 |
| Claude Haiku 5.5 | Claude Code | 34 of 50 | 5 of 40 | 0 of 15 | 14 of 15 | 20 of 20 | 3 | $0.07 |
| GPT-6.1 Sol | Codex CLI | 26 of 50 | 5 of 40 | 5 of 15 | 1 of 15 | 20 of 20 | 2 | $0.19 |
| GPT-6 Astra | Codex CLI | 25 of 50 | 5 of 40 | 4 of 15 | 1 of 15 | 20 of 20 | 0 | $1.33 |
| GPT-6.1 Terra | Codex CLI | 26 of 50 | 5 of 40 | 1 of 15 | 6 of 15 | 19 of 20 | 3 | $0.11 |
| GPT-6 Luna | Codex CLI | 26 of 50 | 5 of 40 | 1 of 15 | 10 of 15 | 15 of 20 | 1 | $0.02 |

- **On Linux the background doesn't separate the models: each passes IR-02's five background trials and no other.**
  IR-01, IR-03 and IR-04 interrupt with a modal dialog that Linux's window manager stacks over the user's window (‡),
  and in the multi-app tasks the Electron apps, Chromium and Calc refuse cua-driver's background input, so the agents
  stop and report themselves blocked, or bring a window forward and disturb the user.
- **In the foreground Claude Fable 5.2 leads with 43 of 50, then Sonnet with 42, Opus with 38 and Haiku with
  34.** Fable passes every precision trial and 9 of the 15 multi-app ones, the most of any model, and ends none on the
  turn limit, though 6 run out the 360 seconds. Sonnet, Opus and Haiku pass every interruption trial, Fable 19 of 20. Sonnet passes 15 of 15 precision trials, Haiku
  14 of 15, and Opus 11 of 15, missing MB-10's hover toolbar in 4 of
  5. On the multi-app tasks Sonnet and Opus pass 7 and 7 of 15, Haiku 0.
- **GPT-6 in Codex works from the accessibility tree alone, and it shows on the tasks that need the screen.** Codex sends
  the model cua-driver's structured results without their screenshots, so GPT-6.1 Sol passes 20 of 20
  interruption trials but 1 of 15 precision trials, where the hover toolbar, the tooltip and the drag
  targets show only on screen; GPT-6 Astra passes 1 of 15 as well, Terra 6 of 15 and Luna 10 of 15.
  Their multi-app passes: Sol 5, Astra 4, Terra 1, Luna 1.
- **12 trials leave the GUI, each through cua-driver's `launch_app`** (Haiku 3, Terra 3, Opus 2, Sol 2, Sonnet 1, Luna 1). Most open a
  file by handing it to an app on the command line: the GPT-6 models G02's workbook in LibreOffice, Claude G04's access
  log in a text editor. Two, Sonnet's and Opus's in G04's background, run a shell command with `sh -c`, copying the log
  and fetching the archive page into /tmp.
- **Cost per trial at list price** runs from $0.02 (Luna) and $0.07 (Haiku) to $0.80 (Fable), $0.82 (Opus) and $1.33
  (Astra); Sonnet costs $0.56, Sol $0.19 and Terra $0.11. Astra's cost is mostly Codex rereading its context, at $1.00
  per million cached input tokens, five times Fable's $0.20.

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

**Claude Fable 5.2 and GPT-6 Astra through both drivers on Linux, every trial of Bench v2** (runs
`cua-driver-fable-5-2-2026-11-10`, `agent-desktop-fable-5-2-2026-11-10`, `cua-driver-gpt-6-astra-2026-11-10` and
`agent-desktop-gpt-6-astra-2026-11-10`, agentenv-framework 0.9.1500; Fable in Claude Code at its default effort, Astra in
Codex CLI 0.147.0 at medium effort, agent-desktop's trials through its Codex CLI twins, `tasks/codex-agent-desktop-*.json`):

| Model | Driver | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Cost per trial |
|---|---|---:|---:|---:|---:|---:|---:|
| Claude Fable 5.2 | cua-driver | 43 of 50 | 5 of 40 | 9 of 15 | 15 of 15 | 19 of 20 | $0.80 |
| Claude Fable 5.2 | agent-desktop | 40 of 50 | 5 of 40 | 5 of 15 | 15 of 15 | 20 of 20 | $0.68 |
| GPT-6 Astra | cua-driver | 25 of 50 | 5 of 40 | 4 of 15 | 1 of 15 | 20 of 20 | $1.33 |
| GPT-6 Astra | agent-desktop | 30 of 50 | 5 of 40 | 0 of 15 | 10 of 15 | 20 of 20 | $0.59 |

- **Fable passes the most through either driver:** 43 of 50 in the foreground through cua-driver and 40 through
  agent-desktop, against Sonnet 5.5's 42 and 39. It passes every precision trial through both, and G04 every time.
- **Astra never sees the screen.** Codex sends the model a tool result's structured content alone when it has one, and
  both drivers' results do: none of Astra's 3,182 tool results reached it with an image. Through cua-driver it passes 1
  of 15 precision trials, as GPT-6.1 Sol does. agent-desktop's text answers carry enough for MB-09's drag and MB-10's
  hover toolbar, which Astra passes 5 of 5 each, but not MB-11's tooltip.
- **Through agent-desktop Astra can't find the multi-app tasks' apps.** agent-desktop's `list-apps` on Linux doesn't
  list the Electron apps or Chromium, and launching them by name fails; Fable finds their windows on agent-desktop's
  screenshots and works on, while Astra reports itself blocked in all 15 multi-app trials.
- **In the background neither driver separates them:** each passes IR-02's five and no other (‡).
- No trial leaves the GUI; Fable's 11 slowest run out the 360 seconds, and one of Astra's ends on the turn limit.

**Opus, Haiku, Sol, Terra and Luna through agent-desktop on Linux, every trial of Bench v2** (runs
`agent-desktop-opus-5-5-2026-11-11`, `agent-desktop-haiku-5-5-2026-11-11`, `agent-desktop-gpt-6.1-sol-2026-11-11`,
`agent-desktop-gpt-6.1-terra-2026-11-11` and `agent-desktop-gpt-6-luna-2026-11-11`, agentenv-framework 0.9.1502; the
GPT models through `tasks/codex-agent-desktop-*.json`). Every model on the Linux board now has a run through each driver:

| Model | Driver | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Opus 5.5 | cua-driver | 38 of 50 | 5 of 40 | 7 of 15 | 11 of 15 | 20 of 20 | 2 | $0.82 |
| Claude Opus 5.5 | agent-desktop | 37 of 50 | 5 of 40 | 2 of 15 | 15 of 15 | 20 of 20 | 0 | $0.34 |
| Claude Haiku 5.5 | cua-driver | 34 of 50 | 5 of 40 | 0 of 15 | 14 of 15 | 20 of 20 | 3 | $0.07 |
| Claude Haiku 5.5 | agent-desktop | 37 of 50 | 3 of 40 | 2 of 15 | 15 of 15 | 20 of 20 | 0 | $0.03 |
| GPT-6.1 Sol | cua-driver | 26 of 50 | 5 of 40 | 5 of 15 | 1 of 15 | 20 of 20 | 2 | $0.19 |
| GPT-6.1 Sol | agent-desktop | 30 of 50 | 5 of 40 | 0 of 15 | 10 of 15 | 20 of 20 | 0 | $0.09 |
| GPT-6.1 Terra | cua-driver | 26 of 50 | 5 of 40 | 1 of 15 | 6 of 15 | 19 of 20 | 3 | $0.11 |
| GPT-6.1 Terra | agent-desktop | 30 of 50 | 5 of 40 | 0 of 15 | 10 of 15 | 20 of 20 | 0 | $0.05 |
| GPT-6 Luna | cua-driver | 26 of 50 | 5 of 40 | 1 of 15 | 10 of 15 | 15 of 20 | 1 | $0.02 |
| GPT-6 Luna | agent-desktop | 29 of 50 | 4 of 40 | 0 of 15 | 10 of 15 | 19 of 20 | 0 | $0.01 |

- **Through agent-desktop each model but Opus passes more in the foreground**, Haiku 37 of 50 against 34 and the GPT
  models 29 or 30 against 26, and no trial leaves the GUI, where 11 of these models' cua-driver trials do.
- **The GPT models gain the precision tasks and lose the multi-app ones**, as Astra does: agent-desktop's text answers
  carry MB-09's drag and MB-10's hover toolbar, 5 of 5 each, but not MB-11's tooltip, and none of Sol, Terra and Luna
  passes a multi-app trial.
- **Claude passes fewer multi-app trials through agent-desktop:** Opus 2 of 15 (G02 and G04 once each) against
  cua-driver's 7, Haiku 2 (G04 twice). Haiku stops on the 45-turn limit in 11 of its 15.
- **In the background agent-desktop matches cua-driver:** only IR-02 passes, 5 of 5 for Opus, Sol and Terra, 4 for
  Luna and 3 for Haiku; the dialog tasks take the keyboard with either driver (‡).
- **A trial costs less than half of cua-driver's for each model**, Opus $0.34 against $0.82.
