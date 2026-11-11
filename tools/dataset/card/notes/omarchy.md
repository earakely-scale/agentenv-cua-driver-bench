**On Omarchy, Claude Sonnet 5.5 through cua-driver passes 34 of 35 in the foreground and 5 of 25 in the background**
(run `cua-driver-sonnet-5-5-2026-11-10`: Bench v2's seven BenchLab tasks in trycua's Hyprland port, on Omarchy 4.5
under QEMU/KVM on EC2, agentenv-framework 0.9.1500). The multi-app tasks don't run on Omarchy yet, so here it is beside
the same model and driver on the other OSes, over the same 60 BenchLab trials:

| OS | Foreground | Background | Precision (fg) | Interruption (fg) | Left the GUI | Cost per trial |
|---|---:|---:|---:|---:|---:|---:|
| Omarchy | 34 of 35 | 5 of 25 | 15 of 15 | 19 of 20 | 0 | $0.30 |
| Windows | 33 of 35 | 11 of 25 | 15 of 15 | 18 of 20 | 0 | $0.28 |
| Linux | 35 of 35 | 5 of 25 | 15 of 15 | 20 of 20 | 0 | $0.26 |
| macOS | 35 of 35 | 18 of 25 | 15 of 15 | 20 of 20 | 0 | $0.33 |

- **BenchLab's dialogs leave the user alone on Omarchy, and its dropdowns don't.** trycua's window rules for Hyprland
  keep IR-01's, IR-03's and IR-04's dialogs from taking the focus as they open, so IR-01 passes 3 of its 5 background
  trials, against none on Linux and Windows.
- **In 14 of the 20 background failures the agent opened one of BenchLab's dropdowns with a click** (Team, Priority,
  Status or Plan). GTK opens it as a popup that grabs the keyboard, so the user's typing goes to the menu until the
  agent picks an item. `set_value` picks one with no popup: in each of the 4 times an agent used it, the user kept the
  keyboard. That's why IR-02 passes 1 of 5 here against 5 of 5 on Linux and Windows. On Linux, the one IR-02 trial whose
  agent clicked the dropdown stayed undisturbed: the X11 sentinel reads the window's input focus, which a keyboard
  grab leaves where it was.
- **MB-09's drag needs the pointer (§).** cua-driver's background drag never drops on Hyprland. In the background,
  agents dragged with the real pointer, doing the task but disturbing the user (2 trials), or stopped (3).
- **In the foreground every precision trial passes, and 19 of 20 interruption trials.** In IR-01's second run a
  dialog took a click meant for the Email field, and the email went into the Name field.
- **No trial leaves the GUI.** Omarchy's own launchers, its menu and Apps panel, are logged but don't fail a trial:
  they run only their own rows, and a terminal they open is caught.

Every failure was checked against the sentinel's log and the agent's calls for a cause in the computer rather than in
the agent and its driver, and none was found.
