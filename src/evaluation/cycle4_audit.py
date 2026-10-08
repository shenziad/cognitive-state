"""Offline reconstruction, source-first review packets and cycle4 gates."""

from copy import deepcopy
from pathlib import Path
import importlib.util
import sys

from evaluation.cycle4 import ROOT, RELEASE, PLAN, verify_release, available_input, next_memory, executor_context
from agents.agent import AgentExecutor
from evaluation.staged import ledger_totals
from llm.client import Completion
from state.v031 import ExtractorV031, compact
from utils.io import load_json, save_json, digest

DIMENSIONS = ["entity_phase_confusion", "unsupported_completion", "invented_requirement",
              "missing_pending_job", "unsupported_reopened_question", "missing_decision_dependency"]


class ReplayClient:
    """Recorded replies only, requiring exactly the same actual public messages."""
    def __init__(self, calls):
        self.calls, self.position = calls, 0

    def complete(self, messages, *, purpose):
        call = self.calls[self.position]
        if messages != call["messages"] or purpose != call["metadata"]["purpose"]:
            raise ValueError("Actual model input differs from reconstructed public input")
        self.position += 1
        return Completion(call["response"], deepcopy(call["metadata"]))


def audit(run):
    if sys.flags.optimize:
        raise ValueError("Integrity replay requires assertions enabled")
    run = Path(run).resolve()
    config, data, schedule, manifest, rows, ledger = [load_json(run / p) for p in
        ("config.json", "inputs.json", "schedule.json", "manifest.json", "results.json", "call_ledger.json")]
    for filename, key in (("config.json", "config_sha256"), ("inputs.json", "inputs_sha256"), ("schedule.json", "schedule_sha256")):
        assert digest(run / filename) == manifest[key]
    if manifest["evidence_type"] == "api":
        verify_release()
        assert manifest["execution_release_sha256"] == digest(RELEASE) == digest(run / "execution_release.json")
        for relative, sha in load_json(RELEASE)["sha256"].items():
            assert digest(run / "snapshot" / relative) == sha
        if config["stage"] != "preflight":
            verify_gate(run / "incoming_gate.json", config["stage"])
    assert config == load_json(ROOT / f"configs/cycle4_{config['stage']}_v1.json")
    assert data == load_json(ROOT / config["dataset"])
    assert schedule == load_json(ROOT / config["schedule"])
    complete = manifest["status"] == "completed" and len(rows) == len(schedule)
    assert len(rows) <= len(schedule)
    if manifest["status"] == "completed":
        assert complete
    cases = {c["instance_id"]: c for c in data.get("cases", [])}
    scenarios = {s["scenario_id"]: s for s in data.get("scenarios", [])}
    worlds, memory, stopped = {}, {}, set()
    indices, response_ids, artifacts = [], [], {}
    prompts = {c: (ROOT / p).read_text(encoding="utf-8") for c, p in config["prompts"].items()}
    for row, slot in zip(rows, schedule):
        assert all(row[k] == v for k, v in slot.items())
        a = load_json(run / row["artifact"])
        assert a["result"] == row
        artifacts[row["artifact"]] = digest(run / row["artifact"])
        ident, cond, h = slot["instance_id"], slot["condition"], slot["handoff"]
        key = (ident, cond)
        if scenarios:
            s = scenarios[ident]; stage = s["handoffs"][h - 1]
            if key not in worlds:
                assert h == 1
                worlds[key] = deepcopy(s["initial_state"]); memory[key] = [deepcopy(s["public_goal"])]
            worlds[key].update(deepcopy(stage["external_state_patch"]))
            fixture = deepcopy(stage["environment"]); fixture["initial_state"] = deepcopy(worlds[key])
            history = deepcopy(memory[key]) + deepcopy(stage["public_events"])
        else:
            fixture, history = cases[ident]["environment"], cases[ident]["history"]
        env, available, interface = available_input(history, fixture, ident, h)
        assert a["environment"] == fixture and a["public_interface"] == interface
        assert a["history"] == (None if key in stopped else available)
        assert (row["status"] == "skipped_chain_error") == (key in stopped)
        selected = ledger[row["request_start"]:row["request_end"]]
        indices.extend(range(row["request_start"], row["request_end"]))
        responses = [r for r in selected if r["status"] == "response"]
        # An unknown-usage response is recorded but deliberately not passed to
        # the extractor/executor. Such a run cannot pass a complete-run gate.
        delivered = [r for r in responses if all(type(r["metadata"].get(k)) is int for k in ("input_tokens", "output_tokens"))]
        assert len(delivered) == len(a["calls"])
        for call, attempt in zip(a["calls"], delivered):
            assert all(call[k] == attempt[k] for k in ("messages", "response", "metadata"))
        extraction = [c for c in a["calls"] if c["metadata"]["purpose"] != "executor"]
        execution = [c for c in a["calls"] if c["metadata"]["purpose"] == "executor"]
        if row["status"] != "api_error":
            if extraction:
                rc = ReplayClient(extraction)
                rep, diag = ExtractorV031(rc, config["representation_budget"]).extract(available, interface, cond, prompts[cond], [])
                assert rc.position == len(extraction) and rep == a["representation"] and diag == row["extraction_attempts"]
            elif cond == "full_context" and key not in stopped:
                assert a["representation"] == compact(available)
            if execution:
                rc = ReplayClient(execution)
                try:
                    AgentExecutor(rc, prompts["executor"], config["max_steps"]).run(executor_context(a["representation"], cond, interface), env, [])
                except (ValueError, TypeError, KeyError):
                    assert row["status"] == "executor_error"
                assert rc.position == len(execution)
                assert env.trace == a["trace"]
        else:
            for t in a["trace"]:
                env.apply(t["action"])
                assert env.trace[-1] == t
        assert env.settings == a["final_settings"]
        assert row["metrics"] == (env.evaluate() if execution else None)
        assert row["success"] == bool(execution and row["status"] == "completed" and env.evaluate()["task_success"])
        assert row["premature_completed"] == (env.finish_status == "completed" and not all(env.evaluate()["goal_checks"].values()))
        if scenarios:
            worlds[key] = deepcopy(env.settings)
            if row["status"] in {"representation_error", "executor_error", "skipped_chain_error"}:
                stopped.add(key)
            elif row["status"] != "api_error":
                memory[key] = next_memory(history, available, env, a["representation"], cond, h)
    assert sorted(indices) == list(range(len(ledger)))
    for index, attempt in enumerate(ledger):
        assert attempt["request_index"] == index
        if attempt["status"] != "response":
            continue
        m = attempt["metadata"]
        if manifest["evidence_type"] == "api":
            assert m["source"] == "api" and m["transport"] == "openai_sdk" and m["model"] == config["model"]
            if all(type(m.get(k)) is int for k in ("input_tokens", "output_tokens")):
                assert m["input_tokens"] + m["output_tokens"] == m["usage_details"]["total_tokens"]
            response_ids.append(m["response_id"])
    assert all(response_ids) and len(set(response_ids)) == len(response_ids)
    plan = load_json(PLAN)
    evidence = {"integrity": {k: True for k in plan["blocking_integrity_checks"]},
        "completed_cells": len(rows) if complete else -1, "unknown_usage_requests": ledger_totals(ledger)["unknown_usage_attempts"],
        "execution_manifest_verified": manifest["evidence_type"] == "api", "semantic_review_complete": False,
        "final_valid": {c: sum(r["condition"] == c and r["representation_valid"] is True for r in rows) for c in config["conditions"] if c != "full_context"}}
    evidence["integrity"]["no_unresolved_provider_error"] = complete and all(a["status"] == "response" for a in ledger)
    groups = {}
    for condition in config["conditions"]:
        groups[condition] = {}
        for scope in ("all", "main", "controls"):
            selected = [r for r in rows if r["condition"] == condition and
                        (scope == "all" or r["control"] == (scope == "controls"))]
            calls = [a for r in selected for a in ledger[r["request_start"]:r["request_end"]]]
            metas = [a.get("metadata", {}) for a in calls]
            def total(field):
                values = [m.get(field) for m in metas]
                return sum(values) if all(type(v) in (int, float) for v in values) else None
            cached = [(m.get("usage_details", {}).get("prompt_tokens_details") or {}).get("cached_tokens") for m in metas]
            groups[condition][scope] = {"saved": len(selected),
                "successes": sum(r["success"] for r in selected) if complete else None,
                "representation_errors": sum(r["status"] == "representation_error" for r in selected),
                "skipped": sum(r["status"] == "skipped_chain_error" for r in selected),
                "premature_completed": sum(r["premature_completed"] for r in selected),
                "usage": ledger_totals(calls), "input_tokens": total("input_tokens"), "output_tokens": total("output_tokens"),
                "cached_input_tokens": sum(cached) if all(type(v) is int for v in cached) else None,
                "response_latency_seconds": total("latency_seconds"),
                "first_valid": sum(bool(r["extraction_attempts"]) and r["extraction_attempts"][0]["valid"] for r in selected),
                "repair_calls": sum(max(0, len(r["extraction_attempts"]) - 1) for r in selected)}
    chains = []
    for ident in scenarios:
        for cond in config["conditions"]:
            selected = [r for r in rows if r["instance_id"] == ident and r["condition"] == cond]
            chains.append({"scenario": ident, "condition": cond, "success": all(r["success"] for r in selected) if complete and len(selected) == 4 else None})
    pairs = []
    full = {(r["instance_id"], r["repetition"], r["handoff"]): r for r in rows if r["condition"] == "full_context"}
    for r in rows:
        b = full.get((r["instance_id"], r["repetition"], r["handoff"]))
        if r["condition"] == "full_context" or b is None:
            continue
        usage = [ledger_totals(ledger[x["request_start"]:x["request_end"]])["total_tokens"] for x in (r, b)]
        comparable = complete and all(x["representation_bytes"] is not None and x["executed"] and
                                     x["status"] in {"completed", "step_limit"} for x in (r, b))
        pairs.append({"instance_id": r["instance_id"], "condition": r["condition"], "repetition": r["repetition"], "handoff": r["handoff"],
                      "comparable": comparable, "token_reduction": 1 - usage[0] / usage[1] if comparable and all(type(v) is int for v in usage) and usage[1] else None})
    return {"complete": complete, "evidence_type": manifest["evidence_type"], "stage": config["stage"],
        "source_run": str(run), "results_sha256": digest(run / "results.json"), "ledger_sha256": digest(run / "call_ledger.json"),
        "manifest_sha256": digest(run / "manifest.json"), "artifact_sha256": artifacts,
        "usage": ledger_totals(ledger), "conditions": groups, "chains": chains, "paired_costs": pairs,
        "gate_evidence": evidence, "verification": "public inputs, authority, world carry, messages, scores and unique requests replayed"}


def review_packet(run):
    run = Path(run).resolve()
    entries = []
    for row in load_json(run / "results.json"):
        if row["condition"] == "full_context":
            continue
        a = load_json(run / row["artifact"])
        entries.append({"artifact": row["artifact"], "artifact_sha256": digest(run / row["artifact"]),
            "condition": row["condition"], "instance_id": row["instance_id"], "repetition": row["repetition"], "handoff": row["handoff"],
            "history": a["history"], "public_interface": a["public_interface"], "representation": a["representation"],
            "assessment": {k: None for k in DIMENSIONS}, "evidence_notes": ""})
    return {"source_run": str(run), "results_sha256": digest(run / "results.json"), "reviewer": "",
            "review_method": "public_sources_before_behavior; assistant_not_independent_gold; condition_not_blinded",
            "entries": entries}


def validate_review(run, review):
    expected = review_packet(run)
    assert review["source_run"] == expected["source_run"] and review["results_sha256"] == expected["results_sha256"]
    assert isinstance(review.get("reviewer"), str) and review["reviewer"].strip()
    assert review.get("review_method") == expected["review_method"]
    assert len(review["entries"]) == len(expected["entries"])
    for actual, source in zip(review["entries"], expected["entries"]):
        for k in source.keys() - {"assessment", "evidence_notes"}:
            assert actual[k] == source[k]
        assert set(actual["assessment"]) == set(DIMENSIONS)
        assert all(v in {"correct", "incorrect", "ambiguous", "not_observed"} for v in actual["assessment"].values())
        assert actual["evidence_notes"].strip()
        if source["representation"] is None:
            assert set(actual["assessment"].values()) == {"not_observed"}
    return True


def make_gate(run, review_path):
    result = audit(run)
    validate_review(run, load_json(review_path))
    evidence = result["gate_evidence"]; evidence["semantic_review_complete"] = True
    if result["stage"] == "preflight":
        spec = importlib.util.spec_from_file_location("cycle4_protocol", ROOT / "scripts/check_cycle4_protocol.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        decision = module.preflight_gate(load_json(PLAN), evidence)
    else:
        decision = {"passed": result["complete"] and result["evidence_type"] == "api" and
                    all(evidence["integrity"].values()) and evidence["unknown_usage_requests"] == 0,
                    "blockers": []}
    return {"status": "passed" if decision["passed"] else "failed", "stage": result["stage"],
            "execution_release_sha256": digest(RELEASE) if RELEASE.exists() else None,
            "audit": result, "review_path": str(Path(review_path).resolve()), "review_sha256": digest(review_path), "decision": decision}


def verify_gate(path, next_stage):
    gate = load_json(path)
    expected = "preflight" if next_stage == "regression" else "regression"
    if gate.get("status") != "passed" or gate.get("stage") != expected or gate.get("execution_release_sha256") != digest(RELEASE):
        raise ValueError("Missing, failed, stale or wrong-stage cycle4 gate")
    if digest(Path(gate["review_path"])) != gate["review_sha256"]:
        raise ValueError("Reviewed annotations changed")
    fresh = make_gate(Path(gate["audit"]["source_run"]), Path(gate["review_path"]))
    if fresh != gate or fresh["audit"]["evidence_type"] != "api":
        raise ValueError("Gate cannot be reproduced from complete real-model evidence")
    return gate
