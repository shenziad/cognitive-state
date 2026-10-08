"""Independent offline replay of a frozen stage run, with unique API usage checks."""

import argparse
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.continuation import ContinuationEnvironment
from utils.io import digest, load_json, save_json


def verify(run):
    manifest, rows, attempts = [load_json(run / f"{n}.json") for n in ("manifest", "results", "call_ledger")]
    assert manifest["status"] in {"completed", "completed_with_errors"}
    assert len(rows) == manifest["assigned_runs"]
    entries = {e["instance_id"]: e for e in load_json(run / "inputs/manifest.json")["instances"]}
    checked = 0
    for field, directory in (("input_sha256", "inputs"), ("code_sha256", "source")):
        for relative, expected in manifest[field].items():
            assert digest(run / directory / relative) == expected
            checked += 1
    for name, expected in manifest["prompt_sha256"].items():
        assert digest(run / "prompts" / f"{name}.txt") == expected
        checked += 1
    # A replay must use precisely the environment implementation saved with this run.
    for name in ("src/evaluation/continuation.py", "src/evaluation/controlled.py"):
        assert digest(ROOT / name) == manifest["code_sha256"][name]
    indices = []
    for extraction in load_json(run / "extraction_records.json"):
        assert load_json(run / extraction["artifact"]) == extraction
        indices.extend(extraction["request_indices"])
        for index, call in zip(extraction["request_indices"], extraction["calls"], strict=True):
            ledger = attempts[index]
            assert all(ledger[k] == call[k] for k in ("messages", "response", "metadata"))
    for row in rows:
        artifact = load_json(run / row["artifacts"][0]); assert artifact["result"] == row
        env = ContinuationEnvironment(load_json(run / "inputs" / entries[row["instance_id"]]["environment"]))
        for saved in artifact["trace"]:
            env.apply(saved["action"]); assert env.trace[-1] == saved
        assert env.settings == artifact["final_settings"]
        expected = env.evaluate()
        if row["error"]:
            expected["task_success"] = False
        assert row["metrics"] == expected
        indices.extend(artifact["request_indices"])
        for index, call in zip(artifact["request_indices"], artifact["calls"], strict=True):
            ledger = attempts[index]
            assert all(ledger[k] == call[k] for k in ("messages", "response", "metadata"))
    assert Counter(indices) == Counter(range(len(attempts)))
    tokens = 0; models = set()
    for attempt in attempts:
        meta = attempt["metadata"]
        assert attempt["status"] == "response" and meta["source"] == "api" and meta["transport"] == "openai_sdk"
        total = meta["input_tokens"] + meta["output_tokens"]
        assert total == meta["usage_details"]["total_tokens"]
        models.add(meta["model"]); tokens += total
    assert models == {load_json(run / "config.json")["model"]}
    return {"status": "passed", "replayed_runs": len(rows), "trace_final_state_and_metrics_match": True,
            "frozen_hash_checks": checked, "actual_requests_unique": True,
            "api_responses": len(attempts), "api_total_tokens": tokens, "models": sorted(models),
            "results_sha256": digest(run / "results.json"), "verifier_sha256": digest(Path(__file__)),
            "verification_model_calls": 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Use a new verification file")
    result = verify(a.run.resolve()); save_json(a.output, result); print(result)


if __name__ == "__main__":
    main()
