"""driver_versions.py FRAMEWORK [REPO]: the upstream driver version every run on the dataset REPO ran, read from the
framework repository's history at the commit (or release tag) its manifest records, written to
tools/dataset/driver_versions.json as {"<os>/<run>": "<version>"}. A run whose manifest records `driver_version` itself
(tools/fleet/manifest.py writes it) needs no entry; this file backs the runs before it did."""
import json
import subprocess
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fleet"))
from manifest import driver_version  # noqa: E402

OUT = Path(__file__).with_name("driver_versions.json")


def reader(framework: Path, ref: str, driver: str):
    """A function that returns the text of a file in ``driver``'s folder at ``ref``, None where it isn't."""
    def read(name: str):
        done = subprocess.run(["git", "-C", str(framework), "show", f"{ref}:src/agent_env/drivers/envs/{driver}/{name}"],
                              capture_output=True, text=True)
        return done.stdout if done.returncode == 0 else None
    return read


def main():
    framework = Path(sys.argv[1])
    repo = sys.argv[2] if len(sys.argv) > 2 else "earakely-scale/CuaDriverBench-AgentEnv"
    subprocess.run(["git", "-C", str(framework), "fetch", "-q", "--tags", "origin"], check=True)
    known = json.loads(OUT.read_text()) if OUT.exists() else {}
    files = [f for f in HfApi().list_repo_files(repo, repo_type="dataset") if f.count("/") == 3 and f.endswith("/manifest.json")]
    for path in sorted(files):
        _, os_name, run, _ = path.split("/")
        manifest = json.loads(Path(hf_hub_download(repo, path, repo_type="dataset")).read_text())
        framework_pin = manifest.get("framework") or {}
        ref = framework_pin.get("commit") or (f"v{framework_pin['agentenv-framework']}" if framework_pin.get("agentenv-framework") else None)
        drivers = {c.get("driver") for c in (manifest.get("computers") or {}).values() if c.get("driver")}
        if not ref or len(drivers) != 1:
            print(f"{os_name}/{run}: skipped (framework {ref}, drivers {sorted(drivers)})")
            continue
        driver = drivers.pop()
        version = driver_version(driver, os_name, reader(framework, ref, driver))
        print(f"{os_name}/{run}: {driver} {version} (framework {ref[:12]})")
        if version:
            known[f"{os_name}/{run}"] = version
    OUT.write_text(json.dumps(dict(sorted(known.items())), indent=1) + "\n")


if __name__ == "__main__":
    main()
