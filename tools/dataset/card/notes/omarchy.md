**On Omarchy, Claude Sonnet 5.5 through cua-driver passes 34 of 35 in the foreground and 18 of 25 in the background**
(run `cua-driver-sonnet-5-5-2026-11-11`: Bench v2's seven BenchLab tasks in trycua's Hyprland port, on Omarchy 4.5 under
QEMU/KVM on EC2, with cua-driver 0.47.4 on its own tools, `--set envs/<computer>.tools=driver`, and the Hyprland plugin
of the same release, built by trycua's release kit on the Hyprland 0.56.2-1 it pins; agentenv-framework 0.9.1506). The
multi-app tasks don't run on Omarchy yet, so here it is beside the same model and driver on the other OSes, over the
same 60 BenchLab trials:

| OS | Foreground | Background | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---:|---:|---:|---:|---:|---:|
| Omarchy | 34 of 35 | 18 of 25 | 15 of 15 | 19 of 20 | 0 | $0.28 |
| Windows | 33 of 35 | 11 of 25 | 15 of 15 | 18 of 20 | 0 | $0.28 |
| Linux | 35 of 35 | 5 of 25 | 15 of 15 | 20 of 20 | 0 | $0.26 |
| macOS | 35 of 35 | 18 of 25 | 15 of 15 | 20 of 20 | 0 | $0.33 |

- **With the user typing, Omarchy now ties macOS.** trycua's window rules for Hyprland keep IR-01's, IR-03's and IR-04's
  dialogs from taking the focus as they open, and its plugin keeps cua-driver's background input on seats of its own, so
  the user's keyboard and pointer stay theirs. IR-01 to IR-04 pass 18 of their 20 background trials.
- **BenchLab's dropdowns no longer take the user's keyboard.** IR-02 passes all five in the background. In the first
  Omarchy run a GTK dropdown's popup opened on the user's seat and their typing went to the menu; the plugin now opens
  it on the agent's.
- **MB-09's drag can't be done in the background (§).** cua-driver's drag reaches BenchLab through the plugin's seat but
  never drops: BenchLab reorders its rows by GTK's drag and drop, which trycua's validation of the plugin doesn't cover.
  MB-09 fails all five, and in three of them Sonnet then drags with cua-driver's desktop-scope input, the real pointer,
  disturbing the user.
- **In the foreground every precision trial passes, and 19 of 20 interruption trials.**
- **No trial leaves the GUI.** Omarchy's own launchers, its menu and Apps panel, are logged but don't fail a trial: they
  run only their own rows, and a terminal they open is caught.

**Six models ran the same 60 trials on Omarchy through cua-driver** (runs `cua-driver-*-2026-11-11`: Claude Sonnet, Opus
and Haiku 5.5 in Claude Code 2.1.280, and GPT-6.1 Sol, GPT-6.1 Terra and GPT-6 Luna in Codex CLI 0.147.0 at medium
effort, through the trials' Codex CLI twins, `tasks/codex-omarchy-*.json`):

| Model | Foreground | Background | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---:|---:|---:|---:|---:|---:|
| Claude Sonnet 5.5 | 34 of 35 | 18 of 25 | 15 of 15 | 19 of 20 | 0 | $0.28 |
| Claude Opus 5.5 | 22 of 35 | 13 of 25 | 10 of 15 | 12 of 20 | 0 | $0.45 |
| Claude Haiku 5.5 | 26 of 35 | 9 of 25 | 12 of 15 | 14 of 20 | 0 | $0.03 |
| GPT-6.1 Sol | 17 of 35 | 16 of 25 | 0 of 15 | 17 of 20 | 0 | $0.16 |
| GPT-6.1 Terra | 22 of 35 | 15 of 25 | 5 of 15 | 17 of 20 | 0 | $0.08 |
| GPT-6 Luna | 19 of 35 | 8 of 25 | 8 of 15 | 11 of 20 | 0 | $0.02 |

- **No background trial fails for the computer.** In 7 of the 150 background trials the user is disturbed, each time by
  an agent that drives cua-driver's desktop-scope input, the real pointer: after a background drag that didn't drop
  (MB-09) or a dialog it couldn't reach. Every other background failure is the task's.
- **Typed text in the background goes through accessibility.** cua-driver refuses to type at a point of a background
  window, saying the target has no focus-free input backend; fields filled with `set_value` pass.
- **IR-04's sign-up never goes through in the background for Opus, Terra and Luna.** Its cookie dialog comes up at the
  first Sign up, and none of their 15 trials submits the form; Luna doesn't refuse the cookies in 3 of its 5.
- **Opus passes 22 of 35 in the foreground, against Sonnet's 34.** It passes none of MB-10's five hover trials. In 3 of
  its 4 IR-01 misses it presses Submit, finds BenchLab's window unchanged and reports no confirmation, leaving the
  permission dialog beside it unanswered.
- **The GPT models work from cua-driver's text alone**, as on the other OSes: Codex CLI sends them no screenshots, so
  MB-11's tooltip passes for none of them. In the background Sol and Terra pass IR-01, IR-02 and IR-03 in 29 of 30
  trials.

cua-driver's first Omarchy runs stay in the dataset but not on the board (`cua-driver-*-2026-11-10`: Sonnet's 60 trials
and the other models' first ones). They ran cua-driver 0.44.0 with Omarchy's own build of the Hyprland plugin, which
predates trycua's fixes for background input on Hyprland, and offered AgentEnv's `computer_*` tools beside cua-driver's;
there Sonnet passed 5 of 25 in the background. Of the other drivers, agent-desktop's pointer and keys need X11 or GNOME
on Linux, and Codex Computer Use's Linux preview is X11's, so neither runs on Omarchy's Hyprland.
