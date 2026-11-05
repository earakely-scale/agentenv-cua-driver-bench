**Claude Sonnet 5.5 in Claude Code, the BenchLab tasks on macOS** (run `sonnet-5-5-2026-11-05`: the seven precision
and interruption tasks, 5 runs each, both conditions, on macOS 26 on EC2 Macs, on agentenv-framework at PR #498's
2d4ad6fe, released in 0.9.1443, with trycua's macOS system prompt and the Linux run's tasks, limits and grade). 53 of
the 70 trials pass, against 39 of the same 70 on Linux, for $18.77 at list price ($18.76 on Linux), and none leaves the
GUI.

- **Foreground: 35 of 35, task score 1.00.** On Linux 34 of 35.
- **Background: 18 of 35, task score 0.81.** 18 of the 20 interruption trials pass, IR-03 and IR-04 every time. On
  macOS a background app's dialog stays behind the user's window, where on Linux it covers it (‡). In IR-01's and
  IR-02's second runs it does the task but a window is raised over the user's. MB-09 to MB-11 still can't pass
  without moving the user's pointer (§): on MB-09 it doesn't finish the reorder in 4 of 5 runs and the user stays
  undisturbed, and in the fifth it finishes at the user's expense; on MB-10 it does the task every time and moves the
  pointer; on MB-11 it submits the right code in 2 of 5 and moves the pointer in all 5.

**Claude Sonnet 5.5 in Claude Code, every trial of Bench v2 on Linux** (run `sonnet-5-5-2026-11-03`: 10 tasks, 5 runs
each, both conditions, on agentenv-framework 0.9.1412, with the tasks, limits and grade of the Haiku 5.5 run). 41 of
the 100 trials pass, as many as Claude Haiku 5.5's (`haiku-5-5-2026-11-02`), for $57.31 at list price against
Haiku's $7.46, and none leaves the GUI. Its mean task score is higher in both conditions.

- **Foreground: 36 of 50, task score 0.86 (Haiku 0.84).** 34 of the 35 precision and interruption trials pass (in
  IR-01's fifth run it submits twice), and 2 of the 15 multi-app trials, G02's fifth run and G04's third. On the
  multi-app tasks it mostly runs out of its 45 turns, with mean task scores of 0.81 (G02), 0.53 (G03) and 0.32 (G04);
  Haiku's were 0.59, 0.45 and 0.32.
- **Background: 5 of 50, all IR-02, task score 0.79 (Haiku 0.69).** It does the task in 14 of the 15 trials of IR-01,
  IR-03 and IR-04, but their modal dialog covers the user's window on Linux, so they can't pass (‡). MB-09 to MB-11
  can't pass without moving the user's pointer (§); it does MB-09 and MB-11 every time, and on MB-10 it clicks the
  action twice in four runs and without hovering in one. It passes no multi-app task in the background: in 12 of the
  15 trials it stops and reports itself blocked, since the apps refuse input in the background; in 2 of G04's runs
  it brings the apps to the front and finishes the task. It disturbs the user in 9 of the 15 (Haiku 10), and its
  mean task score there is 0.38 (Haiku 0.28).

The Sonnet 4.5 pilot (`sonnet-4-5-2026-11-02`, the three multi-app tasks once per condition, none passing) is in the
tables and the Space, but not on the board.
