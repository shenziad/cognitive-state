"""Offline checks for the frozen cycle4 study specification; never calls a model.

This is a reference gate decision and freeze verifier, not an experiment runner.
Execution still requires the separate manifest described in the protocol.
"""

from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def preflight_gate(plan, evidence):
    """Only facility validity, completeness and symmetric encoding availability gate scaling."""
    failures = []
    for check in plan["blocking_integrity_checks"]:
        if evidence.get("integrity", {}).get(check) is not True:
            failures.append(check)
    if type(evidence.get("completed_cells")) is not int or evidence["completed_cells"] != plan["stages"]["preflight"]["assigned_cells"]:
        failures.append("incomplete_assignment")
    if type(evidence.get("unknown_usage_requests")) is not int or evidence["unknown_usage_requests"] != 0:
        failures.append("unknown_usage")
    if evidence.get("execution_manifest_verified") is not True:
        failures.append("execution_manifest_unverified")
    if evidence.get("semantic_review_complete") is not True:
        failures.append("review_incomplete")
    maximum = plan["gates"]["preflight_denominator_per_condition"]
    minimum = plan["gates"]["compressed_final_valid_min_per_condition"]
    for condition in plan["conditions"]:
        if condition == "full_context":
            continue
        valid = evidence.get("final_valid", {}).get(condition)
        if type(valid) is not int or not minimum <= valid <= maximum:
            failures.append("encoding_availability:" + condition)
    # Task scores, behavioral failures and semantic annotations deliberately do
    # not decide readiness. The runner must retain and report them as outcomes.
    return {"passed": not failures, "blockers": failures}


def check_examples(schema, examples):
    variants = schema["properties"]["world"]["properties"]["operations"]["items"]["oneOf"]
    by_kind = {v["properties"]["kind"]["const"]: v for v in variants}
    assert len(examples["cases"]) == 12
    for case in examples["cases"]:
        records = case["expected_operations"]
        ids = {r["id"] for r in records}
        assert len(ids) == len(records)
        sources = {e["id"] for e in case["public_events"]}
        jobs = {r["id"] for r in records if r["kind"] == "job"}
        for record in records:
            variant = by_kind[record["kind"]]
            assert set(variant["required"]) <= record.keys() <= variant["properties"].keys()
            assert record["phase"] in variant["properties"]["phase"]["enum"]
            assert record["source_refs"] and set(record["source_refs"]) <= sources
            if record["kind"] == "submission":
                assert record["outcome"] in {"accepted", "rejected", "unknown"}
                assert (record["phase"] == "completed") == (record["outcome"] != "unknown")
                assert ("job_ref" in record) == (record["outcome"] == "accepted")
                if "job_ref" in record:
                    assert record["job_ref"] in jobs
        assert type(case["expected_finish_completed"]) is bool
    # This checks encoding/reference consistency, not automatic semantic truth.


def verify():
    manifest = read(ROOT / "docs/freezes/cycle4_protocol_v1.json")
    for relative, expected in manifest["sha256"].items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("Frozen protocol file changed: " + relative)
    plan = read(ROOT / "docs/cycle4_plan_20261003.json")
    config = read(ROOT / "configs/cycle4_protocol_v1.json")
    assert plan["protocol_id"] == config["protocol_id"] == manifest["protocol_id"]
    assert plan["execution_ready"] is False and config["execution_ready"] is False
    for name in ("settings", "conditions", "stages", "gates"):
        assert plan[name] == config[name]
    total = 0
    for name, stage in plan["stages"].items():
        per_condition = (stage["scenarios"] * stage["handoffs"] if name == "longitudinal" else stage["cases"]) * stage["repetitions"]
        assert stage["assigned_cells"] == per_condition * len(plan["conditions"])
        calls = per_condition * (6 + 3 * (2 + 6))
        assert calls == stage["max_api_calls"]
        total += calls
    assert total == plan["total_api_call_cap"] == 1380
    check_examples(read(ROOT / "docs/schemas/cognitive_state_v0.3.1.schema.json"),
                   read(ROOT / "docs/examples/cognitive_state_v0.3.1/conformance_cases.json"))
    gate_cases = read(ROOT / "docs/examples/cognitive_state_v0.3.1/gate_cases.json")["cases"]
    for case in gate_cases:
        actual = preflight_gate(plan, case["evidence"])
        assert actual == case["expected"], case["id"]
    return {"protocol_id": plan["protocol_id"], "freeze_files_verified": len(manifest["sha256"]),
            "normative_cases_checked": 12, "gate_decision_cases_checked": len(gate_cases),
            "example_check_scope": "encoding/reference consistency; semantic expectations authored, not model validated",
            "execution_ready": False, "model_calls": 0}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
