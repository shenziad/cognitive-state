"""Validate offline and freeze execution assets once. Never calls the API."""

from pathlib import Path
from datetime import datetime, timezone
import importlib.util
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.cycle4 import dependencies, release_paths, RELEASE, PROTOCOL, verify_release
from utils.io import save_json, digest


def freeze():
    if RELEASE.exists():
        raise ValueError("Execution version already exists; verify it or create a new version")
    spec = importlib.util.spec_from_file_location("cycle4_protocol", ROOT / "scripts/check_cycle4_protocol.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    protocol_check = module.verify()
    deps = dependencies()
    (ROOT / "requirements-cycle4.txt").write_text(
        "# Frozen cycle4 direct and transport dependency versions; Python >=3.10.\n" +
        "\n".join(f"{k}=={v}" for k, v in sorted(deps.items())) + "\n", encoding="utf-8", newline="\n")
    completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    output = completed.stdout + completed.stderr
    count = re.search(r"Ran (\d+) tests?", output)
    report = {"passed": completed.returncode == 0 and count is not None,
              "unit_tests_run": int(count.group(1)) if count else None,
              "protocol_check": protocol_check, "command": "python -m unittest discover -s tests -v",
              "test_output": output, "model_calls": 0,
              "mock_scope": "All 96 preflight, 56 regression and 32 longitudinal slots executed and independently replayed with a privileged offline oracle. This validates plumbing/fixtures, NOT model behavior or compression quality.",
              "python": sys.version, "dependencies": deps}
    save_json(ROOT / "docs/freezes/cycle4_offline_validation_v2.json", report)
    if not report["passed"]:
        print(output)
        raise ValueError("Offline checks failed; execution not released")
    release = {"execution_version": "cycle4-execution-v2", "protocol_id": "cycle4-scoped-lifecycle-v1",
               "status": "execution_frozen", "created_at": datetime.now(timezone.utc).isoformat(),
               "protocol_sha256": digest(PROTOCOL), "dependencies": deps, "python_observed": sys.version,
               "model_calls_at_release": 0, "sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in release_paths()},
               "notes": "Protocol launch-closed config is historical. New stage configs plus this execution manifest unlock preflight; regression and longitudinal additionally need matching real reviewed gates."}
    save_json(RELEASE, release)
    verify_release()
    print(json.dumps({"status": release["status"], "tests": report["unit_tests_run"], "hashed_files": len(release["sha256"]), "model_calls": 0}))


if __name__ == "__main__":
    freeze()
