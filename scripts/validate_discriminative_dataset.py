"""Offline construction audit, not a model experiment or a gold-state evaluation."""

import argparse
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.continuation import ContinuationEnvironment
from state.representation import CognitiveState
from utils.io import digest, load_json, save_json


def replay(fixture, actions):
    env = ContinuationEnvironment(fixture)
    for act in actions:
        env.apply(deepcopy(act))
    return env.evaluate()


def audit(dataset):
    manifest = load_json(dataset / "manifest.json")
    loaded = {}
    pairs = defaultdict(list)
    results = []
    for entry in manifest["instances"]:
        ident = entry["instance_id"]
        task, fixture, reference, review = [load_json(dataset / entry[k]) for k in ("task", "environment", "reference", "review")]
        assert all(v["instance_id"] == ident for v in (task, fixture, reference, review))
        CognitiveState.from_dict(reference["state"])
        assert reference["review"]["status"] == "pending"
        ids = {h["id"] for h in task["history"]}
        assert len(ids) == len(task["history"])
        assert all(set(sources) <= ids for sources in reference["source_message_ids"].values())
        assert len(json.dumps(reference["state"], separators=(",", ":"), ensure_ascii=False).encode("utf-8")) <= 2200
        own = replay(fixture, review["accepted_example"])
        assert own["task_success"], (ident, own)
        # Reading a catalog before a correct continuation is also a valid route.
        catalog_first = [{"tool": "observe", "arguments": {"resource": "workspace/catalog.json"}}] + review["accepted_example"]
        assert replay(fixture, catalog_first)["task_success"]
        catalog = ContinuationEnvironment(fixture).catalog()
        assert set(catalog) == {"operations", "resources", "catalog_cost"}
        assert all(set(x) == {"name", "description", "cost"} for x in catalog["operations"] + catalog["resources"])
        assert "error" in ContinuationEnvironment(fixture).apply({"tool": "observe", "arguments": {"resource": "archive/checkpoint"}})
        loaded[ident] = (entry, fixture, review)
        if entry["pair_id"]:
            pairs[entry["pair_id"]].append(ident)
        results.append({"instance_id": ident, "accepted_example_metrics": own,
                        "task_sha256": digest(dataset / entry["task"]), "environment_sha256": digest(dataset / entry["environment"])})
    paired = []
    for pair, ids in sorted(pairs.items()):
        assert len(ids) == 2
        e1, f1, r1 = loaded[ids[0]]; e2, f2, r2 = loaded[ids[1]]
        assert f1["operations"] == f2["operations"] and f1["observations"] == f2["observations"] and f1["budget"] == f2["budget"]
        assert ContinuationEnvironment(f1).catalog() == ContinuationEnvironment(f2).catalog()
        t1 = load_json(dataset / e1["task"])["history"]; t2 = load_json(dataset / e2["task"])["history"]
        assert [h for h in t1 if h["id"].startswith("d")] == [h for h in t2 if h["id"].startswith("d")]
        x = replay(f1, r2["accepted_example"]); y = replay(f2, r1["accepted_example"])
        if pair == "w02":
            # A conservative policy is acceptable on the confirmed case, but incurs extra work.
            assert x["task_success"] and not y["task_success"]
            assert x["workspace_credits_spent"] > replay(f1, r1["accepted_example"])["workspace_credits_spent"]
        else:
            assert not x["task_success"] and not y["task_success"], (pair, x, y)
        paired.append({"pair_id": pair, "instances": ids,
                       "shared_operation_and_observation_definitions": True, "identical_catalog_and_distractors": True,
                       "initial_world_state_identical": f1["initial_state"] == f2["initial_state"],
                       "counterpart_on_a": x, "counterpart_on_b": y})
    return {"evidence_type": "offline_construction_audit_not_model_performance",
            "dataset_version": manifest["dataset_version"], "status": "passed",
            "tasks": len(results), "pairs": len(paired), "controls": sum(e["control"] for e in manifest["instances"]),
            "review_status": "pending_independent_researcher_review", "manifest_sha256": digest(dataset / "manifest.json"),
            "instances": results, "paired_checks": paired,
            "claim_limit": "Scripted examples validate fixture consistency; no LLM performance or CS advantage is measured."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=ROOT / "datasets/exp001/discriminative_v0.1")
    p.add_argument("--output", type=Path, default=ROOT / "results/analysis/discriminative_construction_v0.1.json")
    args = p.parse_args()
    report = audit(args.dataset)
    if args.output.exists():
        raise FileExistsError("Use a new audit output to preserve earlier records")
    save_json(args.output, report)
    print(f"Validated {report['tasks']} tasks, {report['pairs']} pairs, {report['controls']} controls; no API calls")


if __name__ == "__main__":
    main()
