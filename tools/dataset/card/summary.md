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
