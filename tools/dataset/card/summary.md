**Claude Sonnet 5.5 in Claude Code, every trial of Bench v2 on macOS** (runs `sonnet-5-5-2026-11-05`, the BenchLab
tasks, on agentenv-framework at PR #498's 2d4ad6fe, and `sonnet-5-5-2026-11-05-multiapp`, the multi-app tasks, on
0.9.1443, which released #498; macOS 26 on EC2 Macs, with trycua's macOS system prompt and the Linux run's tasks,
limits and grade). 63 of the 100 trials pass, against 41 on Linux, for $59.41 at list price ($57.31 on Linux). One
leaves the GUI: in G04's fifth foreground run it launches an app with a command.

- **Foreground: 40 of 50, task score 0.91 (Linux 0.86).** All 35 precision and interruption trials pass (Linux 34),
  and 5 of the 15 multi-app trials, G04's in four runs and G02's third. As on Linux it mostly runs out of its 45
  turns, with mean task scores of 0.81 (G02), 0.45 (G03, where it reaches GnuCash's reconciliation but never saves)
  and 0.83 (G04).
- **Background: 23 of 50, task score 0.75 (Linux 0.79).** 18 of the 20 interruption trials pass, IR-03 and IR-04
  every time: on macOS a background app's dialog stays behind the user's window, where on Linux it covers it (‡). In
  IR-01's and IR-02's second runs a window is raised over the user's. MB-09 to MB-11 still can't pass without moving
  the user's pointer (§). G04 passes every time, where on Linux the apps refuse input in the background; G02 and G03
  pass none, mostly running out of turns, and in G02's third run it takes the user's keyboard.

**Claude Haiku 5.5 in Claude Code, the BenchLab tasks on macOS** (run `haiku-5-5-2026-11-05`, on agentenv-framework
0.9.1443). 53 of the 70 trials pass, as many as Sonnet 5.5's on macOS, for $1.23, and none leaves the GUI. All 35
foreground trials pass. In the background 18 of the 20 interruption trials pass, as for Sonnet (task score 0.71,
Sonnet 0.81): on MB-09 it doesn't finish the reorder and the user stays undisturbed, on MB-10 it does the task in four
runs and moves the pointer, and on MB-11 it never gets the code right and moves the pointer every time.

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
