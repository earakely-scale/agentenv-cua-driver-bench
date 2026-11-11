## By operating system

The same four models through the same driver, cua-driver, on each operating system, over the BenchLab tasks every one of
them ran (MB-09 to IR-04: 35 foreground and 25 background trials a model). The models stay the same from row to row, so
where the rows part, the operating system decides.

- **With the user typing, Linux is the weakest.** All four models pass the same 5 of 25 background trials there, IR-02's
  five and no other: Linux's window manager puts IR-01's, IR-03's and IR-04's dialogs over the user's window whatever
  the agent does. Windows passes 8 to 11, macOS 14 to 18 and Omarchy 9 to 18.
- **Each OS fails the background in its own place.** Windows is the only one where MB-09's drag passes in the
  background, all five for every model, but there IR-01's and IR-03's dialogs take the user's keyboard as they open, so
  they pass none. macOS and Omarchy keep the dialogs off the user: IR-01 to IR-04 pass most of the time there. MB-09's
  drag passes on neither: on macOS it moves the user's pointer, and on Omarchy cua-driver's drag never drops into
  BenchLab's list.
- **With the desktop to itself the OSes hardly part for Claude Sonnet 5.5**, who passes 33 to 35 of 35 on each. Opus and
  Haiku pass 30 to 35 on Linux, macOS and Windows but 22 and 26 on Omarchy. There Opus passes none of MB-10's five hover
  trials. In 3 of its 4 IR-01 misses it presses Submit, finds BenchLab's window unchanged and reports no confirmation,
  leaving the permission dialog that opened beside it unanswered.
- **GPT-6.1 Sol's spread is its harness's, not the OS's.** Codex CLI hands it cua-driver's text without the screenshots,
  so MB-10 and MB-11 pass nowhere except MB-10 on Windows, and its foreground runs from 17 of 35 on Omarchy to 29 on
  Windows. In the background it passes 16 of 25 on Omarchy, its best.

{{FIGURE}}
