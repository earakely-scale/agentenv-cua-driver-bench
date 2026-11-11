### What we found

- **With someone typing, the setup decides, not the model.** Through cua-driver on Linux all eight models pass the same
  5 of 40 background trials, and through agent-desktop on Windows all six pass none; through cua-driver on macOS
  seven models pass 14 to 23, and through Aside Computer Use on macOS the same seven 27 to 38, Claude Opus 5.5 the
  most. On Linux and Windows three of the tasks open a dialog that takes the user's keyboard almost
  whatever the agent does, and no multi-app trial passes.
- **With the desktop to itself the model matters, and so can the driver.** Through Aside Computer Use on macOS, Claude
  Opus and Sonnet 5.5 pass all 50, the only setups that do, against Opus's 44 through cua-driver there and GPT-6 Luna's
  41 through Aside. On Windows Opus passes 45 through agent-desktop but 37 through cua-driver, and the best on Linux is
  Claude Fable 5.2 with 43.
- **A small model can match a big one.** Through agent-desktop on Linux, Claude Haiku 5.5 passes 37 of 50 in the
  foreground, as many as Opus, at $0.03 a trial against Opus's $0.34; through Aside on macOS it passes 46 at $0.01,
  against Opus's 50 at $0.29.
- **What a model sees depends on its harness.** Codex CLI hands GPT-6 cua-driver's and agent-desktop's structured
  results without their screenshots, so no GPT model reads MB-11's tooltip through either on any OS; through OpenAI's
  own Codex Computer Use on Windows the GPT models read it in 14 of their 15 trials, and through Aside on macOS, whose
  screenshots reach Codex as plain images, in all 20.

{{FIGURE}}
