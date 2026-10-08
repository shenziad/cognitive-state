"""Run the frozen v0.3 preflight, matched regression, or genuine four-handoff study."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import random
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agents.agent import AgentExecutor
from evaluation.evidence_interface import EvidenceEnvironment
from evaluation.staged import LedgerClient, ledger_totals
from evaluation.longitudinal import repeated_attempts
from llm.client import OpenAISDKClient
from llm.environment import load_project_env
from state.v03r2 import ExtractorV03, compact, state_delta
from utils.io import digest, load_json, save_json, parse_json


def code_paths():
    return sorted([p for p in (ROOT / "src").rglob("*.py")] +
                  [ROOT / "scripts/run_v03_cycle_r2.py", ROOT / "scripts/build_v03_cycle_r2.py"])


def source_hashes():
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in code_paths()}


def protocol_paths():
    return [ROOT / "docs/cycle3_r2_plan_20261003.json", ROOT / "docs/schemas/cognitive_state_v0.3r2.schema.json"] + [
        ROOT / f"datasets/cycle3_v03r2/{stage}.json" for stage in ("preflight", "regression", "longitudinal")] + [
        ROOT / f"configs/cycle3_{stage}_v03r2.json" for stage in ("preflight", "regression", "longitudinal")]


def validate_config(c):
    required = {"stage", "dataset", "model", "temperature", "provider", "endpoint", "api_key_env",
                "output_limit_parameter", "max_output_tokens", "timeout_seconds", "max_api_calls", "extra_body",
                "conditions", "repetitions", "seed", "max_steps", "representation_budget", "repair_attempts",
                "prompts", "gate", "state_schema", "interface_version"}
    if set(c) != required or c["stage"] not in {"preflight", "regression", "longitudinal"}:
        raise ValueError("Use the explicit cycle3 config")
    expected = {"full_context", "cs_v03"} if c["stage"] == "preflight" else {"full_context", "summary", "cs_v02", "cs_v03"}
    if set(c["conditions"]) != expected or len(c["conditions"]) != len(expected):
        raise ValueError("Unexpected conditions")
    if c["model"] != "deepseek-ai/DeepSeek-V4-Flash" or c["provider"] != "openai_sdk" or c["temperature"] != 0:
        raise ValueError("Transport/model settings differ from this bounded pilot")
    if c["endpoint"] != "https://api.siliconflow.cn/v1/chat/completions":
        raise ValueError("Unexpected endpoint")
    if c["repetitions"] != (2 if c["stage"] == "preflight" else 1):
        raise ValueError("Unexpected repetitions")
    if c["representation_budget"] != 6000 or c["repair_attempts"] != 1 or c["max_steps"] != 6:
        raise ValueError("Protocol budget differs from frozen pilot")
    cap = {"preflight": 350, "regression": 450, "longitudinal": 260}[c["stage"]]
    if c["max_api_calls"] != cap or c["max_output_tokens"] != 4096:
        raise ValueError("Unexpected request/output cap")
    if c["state_schema"] != "v0.3-minimal-2" or c["interface_version"] != "evidence-interface-v0.3":
        raise ValueError("Version mismatch")
    if c["gate"] != {"v03_usable": 23, "v03_success": 22, "full_success": 23, "critical_errors": 0, "denominator_per_condition": 24}:
        raise ValueError("Predeclared gate changed")
    for field in ("dataset",):
        if not (ROOT / c[field]).resolve().is_relative_to(ROOT):
            raise ValueError("Input path escapes project")


def gate_results(rows, complete, config):
    if config["stage"] != "preflight":
        return None
    groups = {cond: [r for r in rows if r["condition"] == cond] for cond in config["conditions"]}
    v3, full = groups["cs_v03"], groups["full_context"]
    checks = {"complete_48": complete and len(rows) == 48,
              "v03_usable_at_least_23_of_24": sum(r["representation_valid"] is True for r in v3) >= 23,
              "v03_success_at_least_22_of_24": sum(r["success"] for r in v3) >= 22,
              "full_success_at_least_23_of_24": sum(r["success"] for r in full) >= 23,
              "no_critical_behavior_errors": not any(r["critical_errors"] for r in rows)}
    return {"automatic_checks": checks, "automatic_pass": all(checks.values()),
            "semantic_review_required_before_comparison": True,
            "semantic_review_rule": "Read every v0.3 preflight state against public inputs. Zero fabricated completed/verified operations or added hard user requirements; at most two states with unsupported reopened information needs. Review is assistant audit, not independent researcher gold."}


def summary(rows, complete, config, attempts):
    groups = {}
    for condition in config["conditions"]:
        items = [r for r in rows if r["condition"] == condition]
        groups[condition] = {"saved": len(items), "successes": sum(r["success"] for r in items) if complete else None,
            "executed": sum(r["executed"] for r in items), "representation_errors": sum(r["status"] == "representation_error" for r in items),
            "skipped": sum(r["status"] == "skipped_chain_error" for r in items),
            "first_attempt_valid": sum(bool(r["extraction_attempts"]) and r["extraction_attempts"][0]["valid"] for r in items),
            "repair_calls": sum(max(0, len(r["extraction_attempts"]) - 1) for r in items),
            "usage": ledger_totals([a for r in items for a in attempts[r["request_start"]:r["request_end"]]])}
    return {"stage": config["stage"], "complete": complete, "conditions": groups,
            "actual_usage": ledger_totals(attempts), "gate": gate_results(rows, complete, config),
            "scientific_conclusion": None}


def run(root, config_path, output, gate_path=None, client=None, progress=None):
    config = load_json(config_path); validate_config(config)
    hashes = source_hashes()
    protocol_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in protocol_paths()}
    gate_evidence = None
    if config["stage"] != "preflight":
        if gate_path is None:
            raise ValueError("A completed preflight gate and semantic review are required")
        gate_evidence = load_json(gate_path)
        if gate_evidence.get("status") != "passed" or gate_evidence.get("source_code_sha256") != hashes:
            raise ValueError("Gate missing, failed, or code changed since preflight")
        source_run = Path(gate_evidence["source_run"])
        if load_json(source_run / "manifest.json")["evidence_type"] != "unreviewed_synthetic_api_pilot":
            raise ValueError("Mock runs cannot pass the real-model gate")
        if gate_evidence["cycle_protocol_sha256"] != protocol_hashes:
            raise ValueError("Frozen plan, config, schema or dataset changed since preflight")
        if digest(source_run / "results.json") != gate_evidence["results_sha256"] or not load_json(source_run / "summary.json")["gate"]["automatic_pass"]:
            raise ValueError("Gate evidence does not match preflight results")
        if not gate_evidence.get("semantic_review", {}).get("passed"):
            raise ValueError("Semantic review did not pass")
        expected_prompts = {k: digest(ROOT / p) for k, p in config["prompts"].items()}
        if gate_evidence["prompt_sha256"] != expected_prompts:
            raise ValueError("Prompts changed since preflight")
    dataset = load_json(ROOT / config["dataset"])
    prompts = {name: (ROOT / path).read_text(encoding="utf-8") for name, path in config["prompts"].items()}
    output.mkdir(parents=True, exist_ok=False)
    for relative in hashes:
        dest = output / "source" / relative
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / relative, dest)
    for relative in protocol_hashes:
        dest = output / "protocol" / relative
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / relative, dest)
    for name, path in config["prompts"].items():
        dest = output / "prompts" / f"{name}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / path, dest)
    save_json(output / "config.json", config); save_json(output / "inputs.json", dataset)
    shutil.copyfile(ROOT / "docs/cycle3_r2_plan_20261003.json", output / "plan.json")
    if gate_evidence:
        save_json(output / "gate_evidence.json", gate_evidence)
    manifest = {"stage": config["stage"], "status": "running", "evidence_type": "mock_protocol_validation" if client is not None else "unreviewed_synthetic_api_pilot", "started_at": datetime.now(timezone.utc).isoformat(),
                "config_sha256": digest(output / "config.json"), "input_sha256": digest(output / "inputs.json"),
                "plan_sha256": digest(output / "plan.json"), "source_code_sha256": hashes, "cycle_protocol_sha256": protocol_hashes,
                "prompt_sha256": {k: digest(output / "prompts" / f"{k}.txt") for k in prompts}}
    rows, attempts = [], []
    expected = 32 if config["stage"] == "longitudinal" else len(dataset["cases"]) * len(config["conditions"]) * config["repetitions"]
    manifest["assigned_cells"] = expected
    ledger = None

    def flush():
        actual = ledger.attempts if ledger else attempts
        save_json(output / "results.json", rows); save_json(output / "call_ledger.json", actual)
        save_json(output / "manifest.json", manifest)
        save_json(output / "summary.json", summary(rows, manifest["status"] in {"completed", "completed_with_errors"} and len(rows) == expected, config, actual))

    def cell(ident, family, condition, repetition, handoff, history, fixture, skipped=False, control=False):
        env = EvidenceEnvironment(fixture)
        interface = env.public_interface(f"{ident}:checkpoint_{handoff}")
        available = deepcopy(history) + [{"id": f"runtime_{handoff}", "role": "runtime",
                 "content": compact({"remaining_credits": interface["remaining_credits"], "credit_scope": interface["credit_scope"]})},
                 {"id": f"interface_{handoff}", "role": "tool", "source_type": "public_tool_contract", "content": "The current public_interface supplies the authoritative catalog, operation contracts and receipt semantics for this checkpoint; its preconditions are definitions, not evidence that any action occurred."}]
        start = len(ledger.attempts)
        calls, diagnostics, error = [], [], None
        representation, status = None, "skipped_chain_error" if skipped else "completed"
        if not skipped:
            try:
                if condition == "full_context":
                    representation = compact(available)
                else:
                    representation, diagnostics = ExtractorV03(ledger, config["representation_budget"], config["repair_attempts"]).extract(
                        available, interface, condition, prompts[condition], calls)
                    if representation is None:
                        status = "representation_error"
                if representation is not None:
                    payload = compact({"retained_context": representation, "public_interface": interface})
                    AgentExecutor(ledger, prompts["executor"], config["max_steps"]).run(payload, env, calls)
            except (RuntimeError, OSError) as exc:
                error = {"kind": "api_error", "type": type(exc).__name__, "message": str(exc)[:400]}
                status = "api_error"
            except (ValueError, TypeError, KeyError) as exc:
                error = {"kind": "executor_error", "type": type(exc).__name__, "message": str(exc)[:400]}
                status = "executor_error"
        metrics = env.evaluate()
        executed = any(c["metadata"]["purpose"] == "executor" for c in calls)
        critical = [] if executed else None
        if executed:
            if env.finish_status == "completed" and not all(metrics["goal_checks"].values()):
                critical.append("premature_completed")
            if any(v in {"forbidden_action", "action_without_required_evidence"} for t in env.trace for v in t["policy_violations"]):
                critical.append("prohibited_or_unsupported_action")
        name = f"{ident}_{condition}_r{repetition}_h{handoff}"
        row = {"instance_id": ident, "family": family, "control": control, "condition": condition,
               "repetition": repetition, "handoff": handoff, "status": status, "error": error,
               "success": status == "completed" and metrics["task_success"], "executed": executed,
               "representation_valid": None if condition == "full_context" or skipped else representation is not None,
               "representation_bytes": len(representation.encode("utf-8")) if representation is not None else None,
               "extraction_attempts": diagnostics, "critical_errors": critical,
               "metrics": metrics if executed else None, "repeat_attempts": repeated_attempts(env) if executed else None,
               "request_start": start, "request_end": len(ledger.attempts), "artifact": f"instances/{name}.json"}
        delta = None
        if condition == "cs_v03" and representation is not None:
            old = next((parse_json(e["content"]) for e in history if e.get("retained_schema") == "v0.3"), None)
            delta = state_delta(old, parse_json(representation))
        save_json(output / row["artifact"], {"result": row, "history": available if not skipped else None, "update_delta": delta,
            "public_interface": interface, "representation": representation, "calls": calls,
            "environment": fixture, "trace": env.trace, "final_settings": env.settings})
        rows.append(row); flush()
        if progress:
            progress({"saved": len(rows), "assigned": expected, "case": ident, "condition": condition, "handoff": handoff,
                      "success": row["success"], "status": status, "extraction_attempts": len(diagnostics)})
        return env, representation, status

    flush()
    try:
        if client is None:
            load_project_env(ROOT); client = OpenAISDKClient(config)
        ledger = LedgerClient(client, config["max_api_calls"])
        rng = random.Random(config["seed"])
        if config["stage"] == "longitudinal":
            for scenario in dataset["scenarios"]:
                conditions = list(config["conditions"]); rng.shuffle(conditions)
                for condition in conditions:
                    world = deepcopy(scenario["initial_state"])
                    memory = [deepcopy(scenario["public_goal"])]
                    failed = False
                    for h, stage in enumerate(scenario["handoffs"], 1):
                        world.update(deepcopy(stage["external_state_patch"]))
                        fixture = deepcopy(stage["environment"]); fixture["initial_state"] = deepcopy(world)
                        public_history = deepcopy(memory) + deepcopy(stage["public_events"])
                        env, rep, status = cell(scenario["scenario_id"], "longitudinal", condition, 0, h, public_history, fixture, failed)
                        world = deepcopy(env.settings)
                        if status == "api_error":
                            manifest["status"] = "aborted_api_error"; return
                        if status in {"representation_error", "executor_error", "skipped_chain_error"}:
                            failed = True
                        else:
                            events = []
                            for i, trace in enumerate(env.trace):
                                events += [{"id": f"h{h}_a{i}", "role": "assistant", "content": compact(trace["action"])},
                                           {"id": f"h{h}_o{i}", "role": "tool", "content": compact(trace["observation"])}]
                            memory = public_history + events if condition == "full_context" else [
                                {"id": f"retained_h{h}", "role": "assistant", "content": rep,
                                 "retained_schema": "v0.3" if condition == "cs_v03" else condition}] + events
        else:
            grid = [(case, condition, r) for case in dataset["cases"] for condition in config["conditions"] for r in range(config["repetitions"])]
            rng.shuffle(grid)
            for case, condition, repetition in grid:
                _, _, status = cell(case["instance_id"], case["family"], condition, repetition, 1, case["history"], case["environment"], control=case.get("control", False))
                if status == "api_error":
                    manifest["status"] = "aborted_api_error"; return
        manifest["status"] = "completed_with_errors" if any(r["status"] != "completed" for r in rows) else "completed"
    except BaseException:
        manifest["status"] = "interrupted"; raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat(); flush()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--gate", type=Path)
    p.add_argument("--progress", action="store_true")
    a = p.parse_args()
    run(ROOT, a.config, a.output, a.gate, progress=(lambda x: print(compact(x), flush=True)) if a.progress else None)
    result = load_json(a.output / "summary.json")
    print(compact({"complete": result["complete"], "usage": result["actual_usage"], "gate": result["gate"]}))
    raise SystemExit(0 if result["complete"] else 1)
