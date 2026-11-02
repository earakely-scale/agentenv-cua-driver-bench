// node shoot.mjs JOBS.json: a headless Chrome screenshot per job ({url, out, width, height, dark, mobile, seek,
// eval, measure, wait}), with page errors reported. CHROME names the browser binary; npm install first.
import puppeteer from "puppeteer-core";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const jobs = JSON.parse(readFileSync(process.argv[2], "utf8"));
const profile = mkdtempSync(join(process.env.PROFILE_ROOT || tmpdir(), "shoot-"));
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true, userDataDir: profile,
  args: ["--autoplay-policy=no-user-gesture-required", "--mute-audio", "--hide-scrollbars", "--force-color-profile=srgb"],
});
const cleanup = () => { try { rmSync(profile, { recursive: true, force: true }); } catch {} };
process.on("exit", cleanup);
try {
  for (const j of jobs) {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await page.setViewport({ width: j.width, height: j.height, deviceScaleFactor: j.scale || 1, isMobile: !!j.mobile, hasTouch: !!j.mobile });
    await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: j.dark ? "dark" : "light" }]);
    const cdp = await page.createCDPSession();
    await cdp.send("Emulation.setScrollbarsHidden", { hidden: true });
    await page.goto(j.url, { waitUntil: "networkidle0", timeout: 60000 });
    if (j.seek != null) {
      await page.waitForFunction(() => { const v = document.querySelector("video"); return v && v.readyState >= 1; }, { timeout: 30000 });
      await page.evaluate(async (t) => {
        const v = document.querySelector("video");
        v.pause();
        await new Promise((r) => { v.addEventListener("seeked", r, { once: true }); v.currentTime = t; });
        await new Promise((r) => setTimeout(r, 400));
        v.dispatchEvent(new Event("seeked"));
      }, j.seek);
    }
    if (j.eval) await page.evaluate(j.eval);
    await new Promise((r) => setTimeout(r, j.wait ?? 500));
    if (j.measure) console.log(JSON.stringify({ out: j.out, m: await page.evaluate(j.measure) }));
    await page.screenshot({ path: j.out, fullPage: false });
    if (errors.length) console.log(JSON.stringify({ out: j.out, errors }));
    await page.close();
  }
} finally {
  await browser.close();
  cleanup();
}
