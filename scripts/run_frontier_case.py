"""Exploratory matched interventions on one previously observed frozen CS failure."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agents.agent import AgentExecutor
from evaluation.continuation import ContinuationEnvironment
from evaluation.controlled import equal
from evaluation.runner import dependency_versions, within
from evaluation.staged import LedgerClient, ledger_totals
from llm.client import OpenAISDKClient
from llm.environment import load_project_env
from state.representation import CognitiveState
from utils.io import digest, load_json, save_json

SOURCE_FILES = {
    "artifact": "instances/cont2_inflight_a_r0_cognitive_state_b2200.json",
    "config": "config.json", "task": "inputs/tasks/cont2_inflight_a.json",
    "environment": "inputs/environments/cont2_inflight_a.json", "executor_prompt": "prompts/executor.txt",
}
LOCKED_HASHES = {
    "artifact": "72db01aeaed5c5b6141e25d370ec854f8ed7dbb5e73e91eeb54130bd1013a33e",
    "config": "d201f5f228ef94a8d3893df0529921bc65eb739ec5fcc7d4f9cbe34fb0a53d13",
    "task": "b647655c0fa6669a0eaee7d98b92657b6159e04a67b3e8e3f55869dfce33a081",
    "environment": "5d037440aeb0c1e5baf0bd46778a687542bf46f7e65930a8407563ae45381558",
    "executor_prompt": "94731e816e020e19eea147fc9b0eb029158e21baf6ff655b2a90949c660a3068",
    "representation": "1558901a1c55cde53f5c97c5853abd47da5bcd1b5081e10ab9bdd344c07db17d",
}
VARIANTS = ["original", "remove_ledger_necessity_assumption", "neutral_next_action", "both",
            "source_supported_next_action"]
NECESSITY = "The ledger observation is necessary to confirm acceptance before consuming."
SUPPORTED_ACTION = "Execute consume_Z to consume the pending pearl notice."
TRANSPORT_KEYS = {"provider", "model", "temperature", "endpoint", "api_key_env", "output_limit_parameter",
                  "max_output_tokens", "timeout_seconds", "extra_body"}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def string_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def changed_fields(original, changed):
    return [{"path": f"{block}.{field}", "before": deepcopy(original[block][field]),
             "after": deepcopy(changed[block][field])}
            for block in original for field in original[block] if original[block][field] != changed[block][field]]


def build_variants(representation):
    original = json.loads(representation)
    CognitiveState.from_dict(original)
    if compact(original) != representation:
        raise ValueError("Source representation is not the locked canonical JSON")
    if original["world"]["assumptions"].count(NECESSITY) != 1:
        raise ValueError("The predeclared necessity assumption is not unique")
    variants = []
    allowed = {"original": set(), "remove_ledger_necessity_assumption": {"world.assumptions"},
               "neutral_next_action": {"frontier.next_action"},
               "both": {"world.assumptions", "frontier.next_action"},
               "source_supported_next_action": {"frontier.next_action"}}
    for name in VARIANTS:
        changed = deepcopy(original)
        if name in {"remove_ledger_necessity_assumption", "both"}:
            changed["world"]["assumptions"].remove(NECESSITY)
        if name in {"neutral_next_action", "both"}:
            changed["frontier"]["next_action"] = "unknown"
        if name == "source_supported_next_action":
            changed["frontier"]["next_action"] = SUPPORTED_ACTION
        CognitiveState.from_dict(changed)
        diff = changed_fields(original, changed)
        if {item["path"] for item in diff} != allowed[name]:
            raise ValueError("Intervention changed an undeclared field")
        text = compact(changed)
        variants.append({"variant": name, "representation": text, "state": changed, "diff": diff,
                         "sha256": string_digest(text), "utf8_bytes": len(text.encode("utf-8")),
                         "interpretation": "Source-supported next-action repair, not a deletion ablation" if name ==
                         "source_supported_next_action" else "Matched deletion or instruction neutralization"})
    return variants


def load_case(root, config):
    expected_keys = TRANSPORT_KEYS | {"experiment_id", "source_run", "source_sha256", "prompt_version",
                                       "max_steps", "max_api_calls", "variants", "repetitions", "selection"}
    if set(config) != expected_keys or config["source_sha256"] != LOCKED_HASHES:
        raise ValueError("Case config or immutable source locks differ")
    if config["variants"] != VARIANTS or config["repetitions"] != 1 or config["max_steps"] != 6 or config["max_api_calls"] != 30:
        raise ValueError("Only the five predeclared, single-run, six-step interventions are allowed")
    if config["selection"] != "posthoc_observed_failure_exploratory" or config["prompt_version"] != "v0.3":
        raise ValueError("Case must remain a posthoc exploratory v0.3 diagnostic")
    source = within(root, config["source_run"])
    for key, relative in SOURCE_FILES.items():
        if digest(source / relative) != LOCKED_HASHES[key]:
            raise ValueError(f"Frozen source SHA mismatch: {key}")
    source_config = load_json(source / SOURCE_FILES["config"])
    if any(config[key] != source_config[key] for key in TRANSPORT_KEYS) or source_config["max_steps"] != 6:
        raise ValueError("Transport and executor settings must match the source run")
    artifact = load_json(source / SOURCE_FILES["artifact"])
    if (artifact["result"]["instance_id"], artifact["result"]["condition"], artifact["result"]["budget"]) != (
            "cont2_inflight_a", "cognitive_state", 2200):
        raise ValueError("Unexpected source case")
    representation = artifact["representation"]
    if string_digest(representation) != LOCKED_HASHES["representation"]:
        raise ValueError("Frozen representation SHA mismatch")
    task, fixture = (load_json(source / SOURCE_FILES[key]) for key in ("task", "environment"))
    messages = {message["id"]: message for message in task["history"]}
    if "execute consume_Z: Consume the pearl broker notice" not in messages["h02"]["content"] or (
            "exactly one reservation was accepted by pearl; its notice is pending" not in messages["h04"]["content"]):
        raise ValueError("Supported action lacks the predeclared public historical source")
    prompt = (source / SOURCE_FILES["executor_prompt"]).read_text(encoding="utf-8")
    if artifact["calls"][0]["messages"][0]["content"] != prompt:
        raise ValueError("Frozen executor prompt differs from original call")
    evidence = {"messages": [messages["h02"], messages["h04"]],
                "supported_action": SUPPORTED_ACTION, "source_ids": ["h02", "h04"],
                "reasoning": "h02 maps consume_Z to pearl notice; h04 records one accepted pearl reservation with pending notice.",
                "not_added": ["future receipt", "fulfilled=true before action", "hidden rubric", "tool result prediction"],
                "limitation": "Public consume description and applied acknowledgment do not explicitly report fulfilment; unchanged in this case."}
    return source, fixture, prompt, build_variants(representation), evidence


def diagnostics(environment):
    target = environment.fixture["rubric"]["target_state"]
    before = deepcopy(environment.fixture["initial_state"])
    first_attainment, query_after = None, []
    for index, step in enumerate(environment.trace, start=1):
        if all(equal(before.get(key), value) for key, value in target.items()) and isinstance(step["action"], dict) and (
                step["action"].get("tool") == "observe"):
            query_after.append({"step": index, "action": step["action"], "cost": step["cost"]})
        if first_attainment is None and all(equal(step["state_after"].get(key), value) for key, value in target.items()):
            first_attainment = index
        before = step["state_after"]
    return {"first_action": environment.trace[0]["action"] if environment.trace else None,
            "goal_first_attained_step": first_attainment, "queries_after_goal_attained": query_after,
            "query_count_after_goal_attained": len(query_after), "steps": len(environment.trace),
            "scope": "Private offline target-state diagnostic, never fed to the model; queries are not all necessarily redundant"}


def run_case(root, config_path, output, *, client=None, progress=None):
    root, output = root.resolve(), output.resolve()
    config = load_json(config_path)
    source, fixture, prompt, variants, evidence = load_case(root, config)
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "config.json", config)
    for relative in SOURCE_FILES.values():
        target = output / "source_case" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    save_json(output / "public_source_evidence.json", evidence)
    for variant in variants:
        save_json(output / "variants" / f"{variant['variant']}.json", variant)
    code_files = list((root / "src").rglob("*.py")) + [Path(__file__).resolve()]
    hashes = {}
    for path in code_files:
        relative = path.relative_to(root).as_posix()
        target = output / "source_code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[relative] = digest(path)
    manifest = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "selection": config["selection"], "assigned_runs": 5, "repetitions": 1,
                "source_run": str(source), "source_sha256": LOCKED_HASHES, "code_sha256": hashes,
                "dependencies": dependency_versions(), "dotenv_loaded": False,
                "inference_scope": "One failure-selected synthetic case, one execution per intervention; no hypothesis confirmation.",
                "cost_scope": "Executor calls only; frozen original extraction is not billed again. No token reduction claim.",
                "variant_order": VARIANTS, "model_sampling_seeded": False,
                "interface_limitation": evidence["limitation"], "fixture_visible_to_model": False}
    rows, ledger = [], None
    save_json(output / "results.json", rows)
    save_json(output / "manifest.json", manifest)

    def flush():
        save_json(output / "results.json", rows)
        save_json(output / "call_ledger.json", ledger.attempts if ledger else [])
        manifest["saved_runs"] = len(rows)
        save_json(output / "manifest.json", manifest)

    try:
        if client is None:
            manifest["dotenv_loaded"] = load_project_env(root)
            client = OpenAISDKClient(config)
        ledger = LedgerClient(client, 30)
        executor = AgentExecutor(ledger, prompt, 6)
        for variant in variants:
            environment, calls, error = ContinuationEnvironment(fixture), [], None
            first = len(ledger.attempts)
            try:
                executor.run(variant["representation"], environment, calls)
            except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
            attempts = ledger.attempts[first:]
            metrics = environment.evaluate()
            if error:
                metrics["task_success"] = False
            row = {"variant": variant["variant"], "status": "error" if error else "completed", "error": error,
                   "termination": "error" if error else "finished" if environment.finished else "step_limit",
                   "metrics": metrics, "diagnostics": diagnostics(environment),
                   "execution_attempted": bool(attempts), "executor_response_observed": bool(calls),
                   "token_usage": ledger_totals(attempts), "representation_sha256": variant["sha256"],
                   "representation_utf8_bytes": variant["utf8_bytes"], "artifact": f"instances/{variant['variant']}.json"}
            save_json(output / row["artifact"], {"result": row, "representation": variant["representation"],
                                                 "diff": variant["diff"], "calls": calls, "attempts": attempts,
                                                 "trace": environment.trace, "final_settings": environment.settings})
            rows.append(row)
            flush()
            if progress:
                progress({"saved_runs": len(rows), "assigned_runs": 5, "variant": variant["variant"],
                          "success": metrics["task_success"], "error": error})
            if error and error["type"] in {"RuntimeError", "OSError"}:
                manifest["status"] = "aborted_api_error"
                break
        if manifest["status"] != "aborted_api_error":
            manifest["status"] = "completed_with_errors" if any(row["error"] for row in rows) else "completed"
    except BaseException:
        manifest["status"] = "interrupted"
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        flush()
        complete = len(rows) == 5 and manifest["status"] in {"completed", "completed_with_errors"}
        summary = {"status": manifest["status"], "complete": complete, "saved_runs": len(rows), "assigned_runs": 5,
                   "actual_api_usage": ledger_totals(ledger.attempts if ledger else []),
                   "evidence_type": "posthoc_matched_single_case_diagnostic", "scientific_conclusion": None,
                   "source_representation_sha256": LOCKED_HASHES["representation"], "results": rows,
                   "limitations": [manifest["inference_scope"], manifest["cost_scope"], manifest["interface_limitation"],
                       "World beliefs and other Frontier fields retain inconsistencies; neutral-next-action tests only that instruction.",
                       "The supported action is a public-source planning repair, not information deletion.",
                       "Single executions cannot distinguish sampling variation; do not pool this selected case with the frozen main grid."]}
        save_json(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    show = lambda update: print(compact(update), flush=True)
    summary = run_case(ROOT, args.config, args.output, progress=show if args.progress else None)
    print(f"Saved exploratory case: {summary['saved_runs']}/5; status={summary['status']}")
    return 0 if summary["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
