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
the macOS cua-driver run still opened LibreOffice's welcome dialog in 6 of its 30 multi-app trials. cua-driver's
first Windows run, which also offered its agents AgentEnv's `computer_*` tools beside its own, stays in the dataset
but not on the board (`sonnet-5-5-2026-11-09`, 63 trials).

**Opus 5.5 and Haiku 5.5 ran the same 90 Windows trials through cua-driver** (runs `cua-driver-opus-5-5-2026-11-09`
and `cua-driver-haiku-5-5-2026-11-09`):

| Model | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---:|---:|---:|---:|---:|---:|---:|
| Opus 5.5 | 37 of 50 | 10 of 40 | 7 of 15 | 15 of 15 | 15 of 20 | 2 | $0.87 |
| Sonnet 5.5 | 35 of 50 | 11 of 40 | 2 of 15 | 15 of 15 | 18 of 20 | 1 | $0.66 |
| Haiku 5.5 | 35 of 50 | 8 of 40 | 0 of 15 | 15 of 15 | 20 of 20 | 8 | $0.09 |

- **Opus finishes the multi-app tasks within their turns.** It ends 4 of its 30 multi-app trials on the 45-turn limit,
  against Sonnet's 23 and Haiku's 25, and passes 7 of the 15 in the foreground.
- **Haiku leaves the GUI in 8 trials, all G04's:** it opens the access log by handing it to an app on the command line
  through cua-driver's `launch_app`.
- **Haiku's 30 multi-app trials ran again on agentenv-framework 0.9.1494.** That release's Windows base drops OneDrive's
  per-user setup. On 0.9.1480's base, OneDrive's sign-in cleanup opened two console windows at every boot. On the slower
  host Haiku ran on, they opened during each multi-app trial, and the guard counted them as leaving the GUI. None of
  those 30 trials had passed its task.

**GPT-6.1 Sol, GPT-6.1 Terra and GPT-6 Luna ran the same 90 Windows trials in Codex CLI** (runs
`cua-driver-gpt-6.1-sol-2026-11-10`, `cua-driver-gpt-6.1-terra-2026-11-10` and `cua-driver-gpt-6-luna-2026-11-10`:
Codex CLI 0.147.0 at medium effort with its own tools off, through cua-driver on its own tools, on agentenv-framework
0.9.1494):

| Model | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---:|---:|---:|---:|---:|---:|---:|
| GPT-6.1 Sol | 34 of 50 | 10 of 40 | 5 of 15 | 10 of 15 | 19 of 20 | 1 | $0.18 |
| GPT-6.1 Terra | 32 of 50 | 11 of 40 | 2 of 15 | 10 of 15 | 20 of 20 | 5 | $0.10 |
| GPT-6 Luna | 28 of 50 | 11 of 40 | 0 of 15 | 10 of 15 | 18 of 20 | 3 | $0.02 |

- **MB-11 fails all five times for each of them**, as it does for every GPT model on Linux and macOS, while every Claude
  model passes all five on each OS: the agent never brings up the target icon's tooltip, so it never submits a code.
- **Sol finishes its multi-app trials within their turns.** It ends 1 of its 30 on the 45-turn limit, against Terra's 24
  and Luna's 22, and passes 5 of the 15 in the foreground.
- **Every trial that leaves the GUI does it through cua-driver's `launch_app`,** handing a file to an app on the command
  line.

**On Windows, agent-desktop and cua-driver part in the background** (run `agent-desktop-sonnet-5-5-2026-11-10`: Claude
Sonnet 5.5 on the same 90 trials through Vercel Labs' agent-desktop 1.2.0, its own tools alone, headed in the
foreground, on agentenv-framework 0.9.1494):

| Driver | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---:|---:|---:|---:|---:|---:|---:|
| cua-driver | 35 of 50 | 11 of 40 | 2 of 15 | 15 of 15 | 18 of 20 | 1 | $0.66 |
| agent-desktop | 37 of 50 | 0 of 40 | 3 of 15 | 14 of 15 | 20 of 20 | 1 | $0.36 |

- **In the background, agent-desktop does the task but takes the user's keyboard.** It finishes all 20 interruption
  trials' tasks, but in each of the 35 background trials other than MB-09's the user's window loses keyboard focus and
  activation to the window agent-desktop acts on. On IR-02, which opens no dialog, cua-driver leaves the user
  undisturbed in all five; IR-01's, IR-03's and IR-04's dialogs take the keyboard with either driver (†).
- **MB-09's drag can't be done headless.** In the background agent-desktop acts through UI Automation alone and refuses
  physical input, so MB-09 fails its task in all five, with the user undisturbed.
- **In the foreground it passes 37 of 50:** all 20 interruption trials, 14 of the 15 precision trials (MB-10's first
  fails) and 3 of the 15 multi-app ones. 23 of its 30 multi-app trials end on the 45-turn limit, as 23 of cua-driver's
  do, and a trial costs about half as much.
- **With Haiku 5.5 the pattern holds** (run `agent-desktop-haiku-5-5-2026-11-10`): agent-desktop passes 35 of 50 in the
  foreground and 0 of 40 in the background, all 20 background interruption tasks done but the user's keyboard taken each
  time, and MB-09 failed headless with the user undisturbed. Through cua-driver Haiku passes 35 of 50 and 8 of 40. A
  trial costs $0.04, against cua-driver's $0.09.

**Opus 5.5 and the GPT models through agent-desktop on Windows, every trial of Bench v2** (runs
`agent-desktop-opus-5-5-2026-11-11`, `agent-desktop-gpt-6.1-sol-2026-11-11`, `agent-desktop-gpt-6.1-terra-2026-11-11` and
`agent-desktop-gpt-6-luna-2026-11-11`, agentenv-framework 0.9.1502; Opus in Claude Code at its default effort, the GPT
models in Codex CLI 0.147.0 at medium effort through agent-desktop's Codex CLI twins,
`tasks/codex-windows-agent-desktop-*.json`). Every model on the Windows board now has a run through each driver:

| Model | Driver | Foreground | Background | Multi-app (fg) | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Opus 5.5 | cua-driver | 37 of 50 | 10 of 40 | 7 of 15 | 15 of 15 | 15 of 20 | 2 | $0.87 |
| Opus 5.5 | agent-desktop | 45 of 50 | 0 of 40 | 10 of 15 | 15 of 15 | 20 of 20 | 0 | $0.64 |
| GPT-6.1 Sol | cua-driver | 34 of 50 | 10 of 40 | 5 of 15 | 10 of 15 | 19 of 20 | 1 | $0.18 |
| GPT-6.1 Sol | agent-desktop | 38 of 50 | 0 of 40 | 8 of 15 | 10 of 15 | 20 of 20 | 0 | $0.13 |
| GPT-6.1 Terra | cua-driver | 32 of 50 | 11 of 40 | 2 of 15 | 10 of 15 | 20 of 20 | 5 | $0.10 |
| GPT-6.1 Terra | agent-desktop | 30 of 50 | 0 of 40 | 0 of 15 | 10 of 15 | 20 of 20 | 0 | $0.06 |
| GPT-6 Luna | cua-driver | 28 of 50 | 11 of 40 | 0 of 15 | 10 of 15 | 18 of 20 | 3 | $0.02 |
| GPT-6 Luna | agent-desktop | 30 of 50 | 0 of 40 | 0 of 15 | 10 of 15 | 20 of 20 | 0 | $0.01 |

- **Opus through agent-desktop passes 45 of 50 in the foreground, the most of any model and driver on Windows**: every
  precision and interruption trial, and 10 of the 15 multi-app ones (G04 5 of 5, G02 3, G03 2).
- **In the background no model passes a trial through agent-desktop**, as with Sonnet and Haiku: the window it acts on
  takes the user's keyboard focus and activation. Opus still does the task in 24 of its 40 background trials.
- **On the multi-app tasks Sol passes 8 of 15** (G02 and G04 4 of 5 each) against 5 through cua-driver, while Terra and
  Luna end all 15 on the 45-turn limit.
- **MB-11's tooltip fails all five times for each GPT model**, as through every driver on every OS.
- No trial leaves the GUI; these four models' cua-driver runs leave it 11 times through `launch_app`. Two trials, Sol's
  G02 and Opus's G03, were run again after the task's app wasn't ready within 210 seconds in each of three deploys.

**On Windows, Codex Computer Use ties cua-driver in the foreground** (runs `codex-computer-use-sonnet-5-5-2026-11-10`
and `codex-computer-use-gpt-6-1-sol-2026-11-10`: the 50 foreground trials of Bench v2 through OpenAI's Codex Computer
Use, the Codex app 26.1103.7773.0's plugin with no ChatGPT sign-in, driven by Claude Sonnet 5.5 in Claude Code and by
GPT-6.1 Sol in Codex CLI 0.147.0 at medium effort, on agentenv-framework 0.9.1500). On Windows, Codex acts only on the
app in front, so these runs have no background trials. Each column counts foreground trials alone:

| Driver | Model | Foreground | Multi-app | Precision | Interruption | Left the GUI | Cost per trial |
|---|---|---:|---:|---:|---:|---:|---:|
| cua-driver | Sonnet 5.5 | 35 of 50 | 2 of 15 | 15 of 15 | 18 of 20 | 0 | $0.63 |
| agent-desktop | Sonnet 5.5 | 37 of 50 | 3 of 15 | 14 of 15 | 20 of 20 | 0 | $0.34 |
| Codex Computer Use | Sonnet 5.5 | 35 of 50 | 2 of 15 | 13 of 15 | 20 of 20 | 0 | $0.32 |
| Codex Computer Use | GPT-6.1 Sol | 35 of 50 | 2 of 15 | 13 of 15 | 20 of 20 | 0 | $0.13 |

- **Without a ChatGPT sign-in, G04 can't pass.** Before it acts on a browser window, Codex asks OpenAI whether the
  page's site is allowed. Unsigned, it stops the turn the first time the agent reaches Chromium, and both models report
  themselves blocked in all five of G04's trials, which cua-driver and agent-desktop pass 2 of 5. These runs keep Codex
  as it ships.
- **G02 passes 2 of 5 for each model**, against cua-driver's none and agent-desktop's 1, and **G03 none**. Sonnet's
  three G02 failures and five G03 failures all end on the 45-turn limit, with 21% of its multi-app calls erring,
  most of them in Codex: an element no longer in Codex's cached state, a point outside the window it acts on,
  coordinate input without the window's geometry, or a window Codex failed to activate. GPT ends one trial on the
  limit; it reports itself blocked in all five of G03's, after Codex's input fails in GnuCash and its dialogs, and two
  of its G02 trials end done without the blocker recorded.
- **Every interruption trial passes, and 13 of 15 precision trials.** MB-09's drag passes all five for each model. Codex's
  API has no hover, and MB-10 fails 2 of 5 for each model: the overlay its click needs isn't showing when the click lands.
- No trial leaves the GUI, though Codex runs its JavaScript outside its sandbox on Windows (see the notes).
