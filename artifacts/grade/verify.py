"""The bench's grade of a trial, outside the computer, as trycua's runner grades one: their evaluator for the task on the
task's workspace as its app's data plane returns it, with the evaluator, its oracle and the task's fixture never in the
computer; their A22 criteria on the sentinel's log; and their GUI-only checks, the sentinel's guard during the run and
their scan of the agent's tool calls after it. Each of trycua's files is fetched at the lock's commit and checked
against its sha256 (``TRYCUA``, written by ``python tools/taskpack.py grader``), and kept in a cache by its sha256.

All of its results must hold: ``sentinel``, its log shows the whole trial (a condition, armed, disarmed, no sample
lost); ``task``, their evaluator passed; ``gui_only``, the guard logged no violation, and claude-code was offered and
called no tool but the computer env's and its skill tool, with no code in an input and no command run through
cua-driver's ``launch_app``; and in the background condition ``user_undisturbed``, all eight A22 criteria measured and
held and the user's window not asked to close. Together they are trycua's background completion, and in the
foreground their GUI-only pass. A trial whose agent's trajectory the verifier isn't given, or isn't claude-code's
stream-json, isn't GUI-only, since its tool calls can't be checked."""
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from agentenv_protocol import client

SENTINEL = "bench-sentinel"
LOG = Path(".bench-sentinel/sentinel.jsonl")
DATA_OBJECTS = "urn:agentenv:data-objects/v1"
#: The built-in tools besides the computer env's that a GUI-only claude-code keeps: its skills.
ALLOWED_BUILTINS = ("Skill",)
CACHE = Path.home() / ".cache" / "agentenv-cua-driver-bench"
DATA_TIMEOUT_S = 300
#: Node for the evaluators that serve the task's site, at the version and checksums cdb-s04's own app pins.
NODE = "22.23.4"
NODE_SHA256 = {"amd64": "1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce",
               "arm64": "6287aa46b6c375d816e63ae66d024fbbfd70404825aabdfdf898a970871d2f4b"}
NEEDS_NODE = ("cdb-s04",)
_ARCHES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
#: A launch_app name that a shell would read as more than an app's name.
_COMMAND = re.compile(r"[;|&$`<>]|^[/.~]")

TRYCUA = {
 "commit": "6c0a8c3bb2d32580c3231592f60739c33edc567a",
 "scoring": {
  "summarize_sentinel.py": {
   "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/automated-eval/macos_bench/swift/summarize_sentinel.py",
   "sha256": "9bc2592befaf4158cd928da36d97a67ec4cda05f82a3520ae489078ce4800732"
  },
  "bench_v2.py": {
   "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/automated-eval/macos_bench/bench_v2.py",
   "sha256": "c3f73c0360dd4369c5e21458e23c0098f36a27b21d948e8c3bd25aabe6223a49"
  }
 },
 "tasks": {
  "cdb-s02": {
   "evaluator/evaluate.py": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s02/evaluator/evaluate.py",
    "sha256": "4b66001d1c7051d565959fe2d1e5c3f078bc2a3e430ab81c2db7e0890bf62de9"
   },
   "evaluator/ods.py": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s02/evaluator/ods.py",
    "sha256": "27f8cd5c532493f59e0f515c6e24bcd286c70bc57bd1f43a58df69e384454a37"
   },
   "evaluator/oracle.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s02/evaluator/oracle.json",
    "sha256": "828cfebc9d919bac11811d045dabb03d3975aa4a67d9e6a36450d967a679655e"
   },
   "fixture/calendar/events.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s02/fixture/calendar/events.json",
    "sha256": "9bffa18e42aa77d1c35c685c0bf321cbb5a4543b3855620740e1866bd94d0878"
   },
   "fixture/chat/audit.ndjson": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s02/fixture/chat/audit.ndjson",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
   },
   "fixture/chat/blockers.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s02/fixture/chat/blockers.json",
    "sha256": "0b433ce2b65a3936d1f4783cd04cbab9afe51b62f5aebbb92833eb5f7fc39e3b"
   },
   "fixture/chat/messages.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s02/fixture/chat/messages.json",
    "sha256": "9019a563fcd4d54368a1ddbac137e057fdac2ab3046ad0020fa994da1ac3f277"
   },
   "fixture/mail/messages.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s02/fixture/mail/messages.json",
    "sha256": "371b2eb4e409a793138f86edd9dcb038cf81d6de3b560fef47f06006b7ee189e"
   },
   "fixture/planning/lighthouse-replan.ods": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s02/fixture/planning/lighthouse-replan.ods",
    "sha256": "e233cae7c58a9f32dc9e05530437e6d30a0ef363ee67d7d5dd883eefe3760c85"
   }
  },
  "cdb-s03": {
   "evaluator/evaluate.py": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/evaluator/evaluate.py",
    "sha256": "e24a52be87ccff2d8aef0b2d284f180c7e486fba59ff8569a50bd0cfd8b8878b"
   },
   "evaluator/gnucash.py": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/evaluator/gnucash.py",
    "sha256": "d34e0de2a1e2966554393991916d37f638d0070025dc002f147bb976d6c47c72"
   },
   "evaluator/ods.py": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/evaluator/ods.py",
    "sha256": "b979a545fefec8f1a977fc8b326df506fe45b1fd073c10cdc6403c95b7ca01c8"
   },
   "evaluator/oracle.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/evaluator/oracle.json",
    "sha256": "cc8bf14d377698158ff967db6a8e92a14189ed2b8f03fcd482e75a242c39d466"
   },
   "fixture/book/kestrel-wharf.gnucash": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/fixture/book/kestrel-wharf.gnucash",
    "sha256": "4b00c64d3a6acd84fba4f67ad2285bc341485f6b1aed2957645c341ed2594cad"
   },
   "fixture/mail/attachments/NAR-773.txt": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/fixture/mail/attachments/NAR-773.txt",
    "sha256": "f9e0fa484e987541859e74a07f75ba1c1f3f0d578c43d7cd24dd6a9b07cd037a"
   },
   "fixture/mail/attachments/OCP-4821.txt": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/fixture/mail/attachments/OCP-4821.txt",
    "sha256": "b7d001fac2f68cacc32aeb40db79c77f39852b4cc24b5b54c1dfb425ea3f163a"
   },
   "fixture/mail/attachments/OCP-4827.txt": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/fixture/mail/attachments/OCP-4827.txt",
    "sha256": "d762c979a453e1767685c6fef4516eaac94a288b9b2069a0a993d1fd60eba102"
   },
   "fixture/mail/attachments/SVL-119.txt": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/fixture/mail/attachments/SVL-119.txt",
    "sha256": "7e0fcfecc10a5a7432253ae3cf34b07c37ebaacdd32743a7319debb142ea7d85"
   },
   "fixture/mail/attachments/open-house-menu.txt": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/fixture/mail/attachments/open-house-menu.txt",
    "sha256": "522b33f445606ff24364052dfec0e3a709c3b50246655b058223124ef7928241"
   },
   "fixture/mail/attachments/receiving-log-october.txt": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/fixture/mail/attachments/receiving-log-october.txt",
    "sha256": "63bb2e90dd210a9f6a81431d551feacc0d58f613ab2e9d5fc112ae37d4ec4795"
   },
   "fixture/mail/messages.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/fixture/mail/messages.json",
    "sha256": "2617f8ad065e159c877fe0c1435c0c3b0b24eba6a3a46e7b0fff9b4e1a7b6bef"
   },
   "fixture/planning/kestrel-wharf-reconciliation.ods": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s03/fixture/planning/kestrel-wharf-reconciliation.ods",
    "sha256": "ef7c420e61c58bec3a7ca1ca80d647b0e289d561d9248bec573fe0bf1c8f3f9b"
   }
  },
  "cdb-s04": {
   "evaluator/evaluate.py": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/evaluator/evaluate.py",
    "sha256": "b476b17ddd09d0be656b719d98ccaf65ef0d76e0ff0f842498cd20e37d2285e2"
   },
   "evaluator/oracle.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/evaluator/oracle.json",
    "sha256": "430149bd80461daf90ff36254a36848e4b9cad2f6e5e8cecf029a179ced90330"
   },
   "fixture/archive-site/data/records.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/archive-site/data/records.json",
    "sha256": "234fc0ea495a8a2da8cf9f2c03352bd8952c2c1d6aa2a2158a01ce61a4ff5030"
   },
   "fixture/archive-site/package-lock.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/archive-site/package-lock.json",
    "sha256": "b87ec74af811b4d536cc9e4811172cbe29d801357fab3d470e095cb75cdaec2a"
   },
   "fixture/archive-site/package.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/archive-site/package.json",
    "sha256": "82a76e1243f64ffc2dc2220031a035a77bf8c11ccbd7b8d9c4f50a3ddfc55562"
   },
   "fixture/archive-site/public/app.js": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/archive-site/public/app.js",
    "sha256": "c7e14bd87d27d6518fba930f47e359de687abdf959e51fdd97b6d6afa22d1a9c"
   },
   "fixture/archive-site/public/styles.css": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/archive-site/public/styles.css",
    "sha256": "f10aa07002f774b1ac2325ae31f1a594fd12dbc5a977638d2af5e2bf3759eab5"
   },
   "fixture/archive-site/server.js": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/archive-site/server.js",
    "sha256": "baaef12b833c44ec5d6ef60b266b3c98c1441c526d8b512aa9028aaf2ee41fa1"
   },
   "fixture/archive-site/tests/server.test.js": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/archive-site/tests/server.test.js",
    "sha256": "241308209cf8b7810d4da70419423f151ccab63e7e006c6d6dfc0c1a9ac01602"
   },
   "fixture/cases/cases.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/cases/cases.json",
    "sha256": "eb7d46828aefd90acae0bb6985c8e354079d941159bcc9ddc94748451595cd38"
   },
   "fixture/cdb-s04.workspace.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/cdb-s04.workspace.json",
    "sha256": "ad608cc8bb8b016f588dc8a7e135ee8e84cb035cc91c8d70bc49abb18cb2425f"
   },
   "fixture/logs/archive-access.log": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/logs/archive-access.log",
    "sha256": "327fa081130d1271ae11ce0013eb0de82055794b492196acf0865eb898bcdfa4"
   },
   "fixture/wiki/articles.json": {
    "url": "https://raw.githubusercontent.com/trycua/cua/6c0a8c3bb2d32580c3231592f60739c33edc567a/libs/cua-driver-bench/taskpack/tasks/shared/cdb-s04/fixture/wiki/articles.json",
    "sha256": "f437a1ad19212573c27629233b23ba06240ad5e50c199ff15208275a856fbae9"
   }
  }
 }
}


async def verify(mcp_url, env_url, trajectory=None):
    card = await client.get_card(env_url)
    [task] = sorted({child["name"] for child in card.get("children_environments") or []} & set(TRYCUA["tasks"]))
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        for app in (task, SENTINEL):
            _write(home, (await client.get_data(f"{env_url}/svc/{app}", timeout=DATA_TIMEOUT_S)).parts)
        return await asyncio.to_thread(grade, task, home, Path(tmp), trajectory)


def grade(task, home, scratch, trajectory):
    """The results of a trial of ``task`` whose computer's home, as its apps' data planes returned it, is ``home``."""
    evaluation = _evaluate(task, home / task, scratch)
    summarize, v2 = _scoring(scratch)
    lines = _armed(home / LOG)
    summary = summarize.summarize(str(home / LOG))
    condition = next((line.get("condition") for line in reversed(lines) if line["ev"] == "start"), None)
    window = [line for line in lines if line["armed"] or line["ev"] == "disarmed"]
    armed = next((line for line in window if line["ev"] == "armed"), {})
    problems = _problems(window, condition)
    live = {line["detail"] for line in window if line["ev"] == "gui_only_violation"}
    events = _events(trajectory)
    scanned, mentions = _scan(v2, events or [])
    violations = sorted({*live, *scanned})
    gui_only = bool(events) and not violations and not problems
    passed = bool(evaluation.get("passed")) and gui_only
    multiplayer = v2.multiplayer_score(summary, bool(summary["available"] and armed.get("active") and armed.get("key")),
                                       passed, condition)
    closes = sum(line["ev"] == "close_refused" for line in window)
    results = [
        {"id": "sentinel", "result": not problems, "problems": problems,
         "description": "the sentinel's log shows the whole trial"},
        {"id": "task", "result": evaluation.get("passed") is True, "score": evaluation.get("score"),
         "description": f"trycua's evaluator for {task}",
         "checks": {name: check.get("passed") for name, check in (evaluation.get("detail") or {}).get("checks", {}).items()}},
        {"id": "gui_only", "result": gui_only, "violations": violations, "trajectory_checked": bool(events),
         "transient": sorted({line["detail"] for line in window if line["ev"] == "gui_only_transient"}),
         "mentions": mentions, "description": "no way out of the GUI, live or in the agent's tool calls"},
    ]
    if condition == "background":
        undisturbed = multiplayer["user_undisturbed"] is True and not closes and not problems
        results.append({"id": "user_undisturbed", "result": undisturbed, "criteria": multiplayer["criteria"],
                        "unmeasured": multiplayer["unmeasured"], "close_refused": closes,
                        "background_completion": bool(multiplayer["background_completion"]) and undisturbed,
                        "description": "trycua's A22: the user could have kept working, undisturbed"})
    return results


def _problems(window, condition):
    """What keeps the sentinel's log from showing the whole trial: no condition, never armed, not disarmed (it stopped
    while armed), or samples that failed while armed."""
    problems = [] if condition in ("background", "foreground") else [f"the sentinel's condition is {condition!r}"]
    if not any(line["ev"] == "armed" for line in window):
        problems.append("the sentinel was never armed")
    elif not any(line["ev"] == "disarmed" for line in window):
        problems.append("the sentinel stopped before it was disarmed")
    errors = sorted({line.get("error") for line in window if line["ev"] == "sample_error"})
    return problems + [f"a sample failed: {error}" for error in errors[:5]]


def _evaluate(task, workspace, scratch):
    """trycua's evaluator for ``task`` on ``workspace``: its JSON result. Node is on its path for a task that serves
    a site."""
    folder = scratch / "trycua" / task
    for name, pinned in TRYCUA["tasks"][task].items():
        _fetched(pinned, folder / name)
    result = scratch / "result.json"
    (scratch / "artifacts").mkdir(exist_ok=True)
    env = {**os.environ, "PATH": f"{_node(scratch)}{os.pathsep}{os.environ.get('PATH', '')}"} if task in NEEDS_NODE \
        else None
    subprocess.run([sys.executable, "evaluator/evaluate.py", "--workspace", str(workspace), "--artifacts",
                    str(scratch / "artifacts"), "--result", str(result), "--agent-exit-code", "0"], cwd=folder,
                   env=env, check=True, timeout=300)
    return json.loads(result.read_text())


def _node(scratch):
    """The folder of a node binary: on Linux the pinned one, fetched; elsewhere the one on the path."""
    if sys.platform != "linux":
        if (found := shutil.which("node")) is None:
            raise RuntimeError(f"this task's evaluator needs node {NODE.split('.')[0]} on the path")
        return Path(found).parent
    arch = _ARCHES[platform.machine().lower()]
    name = f"node-v{NODE}-linux-{'x64' if arch == 'amd64' else 'arm64'}"
    archive = _fetched({"url": f"https://nodejs.org/dist/v{NODE}/{name}.tar.xz", "sha256": NODE_SHA256[arch]},
                       scratch / f"{name}.tar.xz")
    with tarfile.open(archive, "r:xz") as tar:
        tar.extractall(scratch / "node", filter="data")
    return scratch / "node" / name / "bin"


def _scoring(scratch):
    """trycua's summarizer and bench_v2, which scores a sentinel's log and holds their GUI-only scan."""
    modules = []
    for name in ("summarize_sentinel", "bench_v2"):
        path = _fetched(TRYCUA["scoring"][f"{name}.py"], scratch / "scoring" / f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"trycua_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def _events(trajectory):
    """claude-code's stream-json events, every turn's document a list of them that opens with the CLI's init; None
    without one, since the scan reads claude-code's tool calls and can't vouch for a turn it can't read."""
    documents = list(trajectory or [])
    if not documents or not all(isinstance(document, list) and document and isinstance(document[0], dict)
                                and (document[0].get("type"), document[0].get("subtype")) == ("system", "init")
                                for document in documents):
        return None
    return [event for document in documents for event in document]


def _scan(v2, events):
    """trycua's scan of the agent's tool calls, a forbidden built-in or code in a tool input; any built-in the CLI
    offered or the agent called beside the computer env's tools; and cua-driver's launch_app running a command, which
    on Linux it does where macOS's opens apps only: with arguments, a launch path that isn't an app's .desktop file, or
    a name a shell would read as more than an app's. The violations, and the side doors merely named."""
    hard, soft = v2.scan_events(events)
    offered = {f"offered:{name}" for event in events if (event.get("type"), event.get("subtype")) == ("system", "init")
               for name in event.get("tools") or [] if not name.startswith("mcp__") and name not in ALLOWED_BUILTINS}
    calls = [(name, tool_input) for event in events for name, tool_input in v2.tool_uses(event)]
    outside = {f"builtin:{name}" for name, _ in calls if not name.startswith("mcp__") and name not in ALLOWED_BUILTINS}
    launches = set()
    for name, tool_input in calls:
        if name.endswith("__launch_app") and isinstance(tool_input, dict):
            if tool_input.get("additional_arguments"):
                launches.add(f"{name}:arguments")
            if tool_input.get("launch_path") and not str(tool_input["launch_path"]).endswith(".desktop"):
                launches.add(f"{name}:launch_path")
            if _COMMAND.search(str(tool_input.get("name") or "")):
                launches.add(f"{name}:command")
    return sorted({*hard, *offered, *outside, *launches}), soft


def _armed(log):
    """The log's lines from the last start on: the sentinel that ran the trial, a reset having started it afresh."""
    lines = [json.loads(raw) for raw in log.read_text().splitlines() if raw.strip().endswith("}")]
    start = max((i for i, line in enumerate(lines) if line["ev"] == "start"), default=0)
    return lines[start:]


def _write(home, parts):
    for part in parts:
        part = part.model_dump(mode="json")
        path = home / part["metadata"][DATA_OBJECTS]["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(part["file"]["bytes"]))


def _fetched(pinned, path):
    """``pinned``'s file at ``path``, from the cache or its URL, checked against its sha256 either way; the cache is
    written whole, under its name only once complete, so trials grading at once read it whole."""
    cached = CACHE / pinned["sha256"]
    data = cached.read_bytes() if cached.exists() else b""
    if hashlib.sha256(data).hexdigest() != pinned["sha256"]:
        with urllib.request.urlopen(pinned["url"], timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != pinned["sha256"]:
            raise RuntimeError(f"{pinned['url']} isn't the file the lock pins")
        CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=CACHE, delete=False) as part:
            part.write(data)
        os.replace(part.name, cached)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
