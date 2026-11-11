### What we found

- **With someone typing, the setup decides, not the model.** Through cua-driver on Linux all eight models pass the same
  5 of 40 background trials, and through agent-desktop on Windows all six pass none; through cua-driver on macOS,
  Claude Opus and Sonnet 5.5 pass 23. On Linux and Windows three of the tasks open a dialog that takes the user's
  keyboard almost whatever the agent does, and no multi-app trial passes.
- **With the desktop to itself the model matters, and so can the driver.** Claude Opus 5.5 passes 45 of 50 on Windows
  through agent-desktop, the most of any setup that ran every task, but 37 through cua-driver. The best on macOS is Opus with 44, on Linux
  Claude Fable 5.2 with 43.
- **A small model can match a big one.** Through agent-desktop on Linux, Claude Haiku 5.5 passes 37 of 50 in the
  foreground, as many as Opus, at $0.03 a trial against Opus's $0.34.
- **What a model sees depends on its harness.** Codex CLI hands GPT-6 the drivers' text without their screenshots, so
  no GPT model reads MB-11's tooltip through cua-driver or agent-desktop on any OS; through OpenAI's own Codex Computer
  Use on Windows, the GPT models read it in 14 of their 15 trials.

{{FIGURE}}
