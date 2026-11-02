// Loaded into each of a bench task's Electron apps by bench_app.py, before the app's own main script: it logs each
// opening of an app's DevTools to the bench's sentinel folder, for the bench's grade, which fails GUI-only on one
// while the sentinel is armed. DevTools open docked in the app's own window, where the sentinel's guard can't see them.
const fs = require("fs");
const os = require("os");
const path = require("path");

const LOG = path.join(os.homedir(), ".bench-sentinel", "devtools.jsonl");

// A module loaded through NODE_OPTIONS runs before Electron gives its own "electron" module, which the app's main
// script, run next, has; its windows come later still, once the app is ready.
setImmediate(() => {
  const { app } = require("electron");
  app.on("web-contents-created", (_, contents) => {
    contents.on("devtools-opened", () => {
      const line = { ev: "devtools_opened", t: Date.now(), title: contents.getTitle(), app: app.getName() };
      try {
        fs.mkdirSync(path.dirname(LOG), { recursive: true });
        fs.appendFileSync(LOG, JSON.stringify(line) + "\n");
      } catch (error) {
        console.error(`bench: couldn't log DevTools opening: ${error}`);
      }
    });
  });
});
