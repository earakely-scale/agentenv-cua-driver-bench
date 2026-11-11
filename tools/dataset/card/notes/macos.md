**On macOS the driver decides whether the user stays undisturbed.** Four computer-use drivers ran trycua's tasks
with the OS, the model, the prompts, the seeds and the grade held fixed, each driver's agent on its own tools alone
(runs `cua-driver-*`, `agent-desktop-*` and `macos-harness-*` of 2026-11-05: Claude Sonnet 5.5 in Claude Code on all
90 trials of Bench v2, Claude Haiku 5.5 on all 90 as well, its multi-app tasks run on 2026-11-06; and
`codex-computer-use-sonnet-5-5-2026-11-09`, Sonnet alone; macOS 26 on EC2 Macs). Through the four, Sonnet passes 39,
35, 32 and 26 of 50 trials in the foreground, and 23, 8, 1 and 11 of 40 in the background.

- **cua-driver (trycua): Sonnet 39 of 50 in the foreground and 23 of 40 in the background, Haiku 38 of 50 and 18 of 40.** Of 80 background trials it takes the user's keyboard in 1 and raises a window over theirs in 7.
  Its background misses are the tasks: MB-09's drag moves the user's pointer (§), and it passes 1 of the 10 G02 and
  G03 trials, five of the others ending on the 45-turn limit.
- **agent-desktop (Vercel Labs): Sonnet 35 of 50 and 8 of 40, Haiku 32 of 50 and 10 of 40.** With Sonnet it passes
  every BenchLab trial in the foreground and none of the 15 multi-app ones, running out of its 45 turns in all of
  them: it makes about 75 tool calls a trial, against cua-driver's 52 and browser-use's 43, and loses turns to
  element references that go stale after each change and to its own checks, which refuse clicks they judge covered
  and report values the Electron apps didn't take. In the background it disturbs the user in 19 of Sonnet's 40
  trials, mostly taking their keyboard or raising a window over theirs.
- **browser-use (macos-harness): Sonnet 32 of 50 and 1 of 40, Haiku 26 of 50 and 1 of 40.** With Codex Computer Use, it
  is one of two drivers to pass G04 every time in the foreground (5 of 5, chaining a few commands in each call), but it
  has no hover, so MB-10 and MB-11 fail. In the background it does the task in 32 of Sonnet's 40 trials and still
  disturbs the user in 39 of them: its set_value, click, drag and key commands bring the app forward over the user's
  window.
- **Codex Computer Use (OpenAI), driven by Claude: Sonnet 26 of 50 in the foreground and 11 of 40 in the
  background.** It is the ChatGPT app's Computer Use plugin at 26.930.51102, with no ChatGPT sign-in: Claude writes
  the JavaScript it runs against OpenAI's `cua` API, and Codex may act on the task's apps alone. In the background it
  does the task in 31 of 40 trials and still disturbs the user in 29: Codex raises the window it acts on over the
  user's, its own "ChatGPT Computer Use" window sits above theirs while it works, and GnuCash takes the user's
  keyboard in 4 of G03's 5. In the foreground it passes 19 of 20 interruption trials and G04 every time, but neither
  G02 nor G03; its API has no hover, so MB-10 and MB-11 fail, and it passes MB-09's drag 2 of 5. 21 of its 90 trials
  end on the 45-turn limit, none leaves the GUI, and a trial costs $0.34 at list price.
- **Codex Computer Use with OpenAI's model: GPT-6.1 Sol in Codex CLI passes 28 of 50 in the foreground and 8 of 40
  in the background** (run `codex-computer-use-gpt-6-1-sol-2026-11-09`, Codex CLI 0.147.0 at medium effort), against
  Sonnet's 26 and 11 through the same driver, at $0.10 a trial against $0.34. In the foreground it passes MB-09's drag
  every time, 4 of G04's 5 and 3 of G02's, but 1 of IR-02's 5: it chooses a menu item and presses Apply in one call,
  and Apply lands before the choice. It stops and reports itself blocked in 36 of its 90 trials rather than disturb
  the user or guess: wherever Codex's drag would bring BenchLab forward (all five of MB-09's background trials), where
  GnuCash shows Codex no ledger controls (all ten of G03's), and where MB-10 and MB-11 need the hover Codex hasn't. In
  the background Codex still raises a window over the user's in 24 of 40. One trial leaves the GUI: in G04's
  background GPT imports Node's `fs` through `js` and reads the task's files, and the trajectory check fails it. None
  ends on the turn limit.
- **cua-driver with the same model: GPT-6.1 Sol in Codex CLI passes 30 of 50 in the foreground and 16 of 40 in the
  background** (run `cua-driver-gpt-6-1-sol-2026-11-09`, Codex CLI 0.147.0 at medium effort), against 28 and 8
  through Codex Computer Use, at $0.18 a trial against $0.10. In the background it does the task in 25 of 40 trials
  and disturbs the user in 10, against Codex Computer Use's 18 and 24: it writes the user's clipboard in 4 of IR-04's
  5, and raises a window or takes the keyboard in 3 of G04's. In the foreground it passes all 20 interruption trials,
  MB-09's drag 4 of 5 and G04 4 of 5, but G02 2 of 5 and G03 none. Codex sends GPT cua-driver's structured results
  without their screenshots (as on Linux, below), so MB-10 and MB-11 pass none of their ten, and 19 of the 30 trials
  it stops in, reporting itself blocked, say its screenshots are empty. One trial leaves the GUI: in G04's foreground
  GPT runs a command through cua-driver's `launch_app`, and the trajectory check fails it. One ends on the turn limit.

**Claude Opus 5.5 with cua-driver** (run `cua-driver-opus-5-5-2026-11-06`) passes 44 of 50 in the foreground and 23 of 40 in the background, against Sonnet's 39 of 50 and 23 of 40.
