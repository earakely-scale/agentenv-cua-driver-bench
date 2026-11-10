"""CU6 discovery: inside a Windows computer, as the session user, start Codex's cua_repl as the driver does, list its
apps and windows, and get each window as an app, recording the name each approval request shows: allowed_apps' names."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

INNER = r'''
import asyncio, importlib.util, json, sys
folder = sys.argv[1]
spec = importlib.util.spec_from_file_location("drv", folder + "\\driver.py")
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import ElicitResult
asks = []
async def approve(ctx, params):
    asks.append({"message": getattr(params, "message", None),
                 "meta": params.meta.model_dump() if getattr(params, "meta", None) else None})
    return ElicitResult(action="accept", content={})
def meta(profile):
    return {d.SANDBOX_KEY: {"sandboxCwd": d._workspace().as_uri(), "permissionProfile": profile}}
CALLS = [
    ("docs", "await cua.getState();"),
    ("apps", "const apps = await cua.listApps(); nodeRepl.write(JSON.stringify(apps.filter(a => a.isRunning)));"),
    ("windows", "const wins = await cua.listWindows(); nodeRepl.write(JSON.stringify(wins));"),
    ("each", "const out = []; for (const w of await cua.listWindows()) { try { await cua.getApp({ windowId: w.id }); out.push([w.title, 'ok']); } catch (e) { out.push([w.title, String(e).slice(0, 120)]); } } nodeRepl.write(JSON.stringify(out));"),
]
async def main():
    server = StdioServerParameters(command=str(d._resources() / d.OS.node), args=[str(d._launcher())],
                                   env=d._environment(), cwd=str(d._workspace()))
    out = {"node": str(d._resources() / d.OS.node), "results": {}}
    async with stdio_client(server) as (r, w), ClientSession(r, w, elicitation_callback=approve) as s:
        init = await s.initialize()
        tools = (await s.list_tools()).tools
        out["tools"] = [t.name for t in tools]
        for label, profile in (("disabled", {"type": "disabled"}),):
            for name, code in CALLS:
                try:
                    res = await asyncio.wait_for(s.call_tool("js", {"code": code}, meta=meta(profile)), 120)
                    out["results"][f"{label}:{name}"] = {
                        "isError": res.isError,
                        "text": " ".join(c.text for c in res.content if getattr(c, "type", "") == "text")[:(200 if name == "docs" else 8000)],
                        "images": sum(1 for c in res.content if getattr(c, "type", "") == "image")}
                except Exception as e:
                    out["results"][f"{label}:{name}"] = {"exception": f"{type(e).__name__}: {e}"[:800]}
            if all(not v.get("isError") and "exception" not in v for k, v in out["results"].items() if k.startswith(label)):
                break
    out["asks"] = asks
    print("CU6JSON" + json.dumps(out))
asyncio.run(main())
'''


def find_driver() -> Path | None:
    for root in (Path("C:/opt"), Path("C:/ProgramData"), Path("C:/agentenv"), Path.home(), Path("C:/")):
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if dirpath.count(os.sep) - str(root).count(os.sep) > 5:
                dirnames[:] = []
                continue
            dirnames[:] = [n for n in dirnames if n not in ("Windows", "$Recycle.Bin", "node_modules", "ChatGPT")]
            if "unpack-msix.py" in filenames and "driver.py" in filenames:
                return Path(dirpath)
    return None


def run(input):
    folder = find_driver()
    result = {"folder": str(folder) if folder else None}
    if not folder:
        return result
    result["files"] = sorted(p.name for p in folder.iterdir())
    res = folder / "ChatGPT" / "resources"
    result["resources"] = sorted(p.name for p in res.iterdir())[:40] if res.exists() else None
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(INNER)
    python = folder / "venv" / "Scripts" / "python.exe"
    proc = subprocess.run([str(python), f.name, str(folder)], capture_output=True, text=True, timeout=900)
    line = next((l for l in proc.stdout.splitlines() if l.startswith("CU6JSON")), None)
    result["inner"] = json.loads(line[7:]) if line else None
    result["stderr_tail"] = proc.stderr[-3000:]
    result["returncode"] = proc.returncode
    return result
