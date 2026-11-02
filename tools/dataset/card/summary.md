**Claude Haiku 5.5 in Claude Code, every trial of Bench v2 on Linux** (run `haiku-5-5-2026-11-02`: 10 tasks, 5 runs
each, both conditions, on bench e6bc0aa and agentenv-framework 0.9.1412). 41 of the 100 trials pass, for $7.46 at
list price, and none leaves the GUI.

- **Foreground: 36 of 50.** Every precision and interruption trial passes (35 of 35), and 1 of the 15 multi-app
  trials, G04's fifth run. On the multi-app tasks it mostly runs out of its 45 turns, with mean task scores of 0.59
  (G02), 0.45 (G03) and 0.32 (G04).
- **Background: 5 of 50, all IR-02.** It does the task in all 15 trials of IR-01, IR-03 and IR-04, but their modal
  dialog covers the user's window on Linux, so they can't pass (‡). MB-09 to MB-11 can't pass without moving the
  user's pointer (§); on MB-10 it clicks the action without hovering, which trycua's check refuses. It passes no
  multi-app task in the background: it disturbs the user in 10 of the 15 trials, and its mean task score is 0.28.

The Sonnet 4.5 pilot (`sonnet-4-5-2026-11-02`, the three multi-app tasks once per condition, none passing) is in the
tables and the Space, but not on the board.
