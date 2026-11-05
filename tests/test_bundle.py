"""The bench's bundle on the Hugging Face Hub: what publish.py stages is the bundle's committed files and trycua's task
pack, checked against the lock, with both licences and the card filled in, and none of the repo's tooling."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_hub_bundle_is_the_bundles_files_and_the_task_pack_with_their_licences_and_card(tmp_path):
    pytest.importorskip("huggingface_hub")
    publish = _module(ROOT / "tools" / "bundle" / "publish.py")

    names = set(publish.staged(tmp_path, "c" * 40, "org/repo"))

    assert {"bundle.toml", "README.md", "LICENSE.md", "evals/bench-v2.toml", "tasks/cdb-g02-background.json",
            "artifacts/taskpack/LICENSE", "artifacts/taskpack/MANIFEST.sha256"} <= names
    assert not any(name.startswith(("tools/", "tests/", ".github/")) or "__pycache__" in name for name in names)
    assert {p.name for p in (tmp_path / "licenses").iterdir()} == {"Apache-2.0.txt", "FSL-1.1-MIT.md"}
    card = (tmp_path / "README.md").read_text()
    assert "agent-env run hf://org/repo --task cdb-g02-background" in card and "{{" not in card
    assert f"agentenv-cua-driver-bench/commit/{'c' * 40}" in card
