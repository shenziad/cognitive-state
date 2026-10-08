"""Frozen stage runs with a single baseline and shared CS extraction per budget.

This runner deliberately does not alter the original exp001 protocol. Byte budgets
are representation constraints; API token counts always come from the provider.
"""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
from typing import Any, Callable

from agents.agent import AgentExecutor
from llm.client import Client, OpenAISDKClient
from llm.environment import load_project_env
from llm.tokens import RepresentationCounter
from state.extractor import StateExtractor
from state.representation import CognitiveState
from utils.io import digest, load_json, save_json
from .continuation import ContinuationEnvironment
from .runner import CONFIG_KEYS, OPTIONAL_CONFIG_KEYS, dependency_versions, usage_total, within
from .runner import validate_config as validate_original_config


ABLATIONS = {"cs_no_frontier", "cs_no_uncertainty", "cs_no_progress_facts", "cs_no_progress"}
CONDITIONS = {"full_context", "no_history", "summary", "cognitive_state"} | ABLATIONS
EXTRA_KEYS = {"condition_budgets", "stage"}


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def validate_config(config: dict[str, Any]) -> dict[str, list[int | None]]:
    if not isinstance(config, dict):
        raise ValueError("Config must be an object")
    required = CONFIG_KEYS - {"representation_budget"}
    allowed = CONFIG_KEYS | OPTIONAL_CONFIG_KEYS | EXTRA_KEYS
    if required - set(config) or set(config) - allowed:
        raise ValueError(f"Config keys differ: missing={required - set(config)}, extra={set(config) - allowed}")
    conditions = config["conditions"]
    if (not isinstance(conditions, list) or not conditions or any(c not in CONDITIONS for c in conditions)
            or len(set(conditions)) != len(conditions) or "full_context" not in conditions):
        raise ValueError("Choose unique staged conditions including full_context")
    if {"cs_no_progress", "cs_no_progress_facts"} <= set(conditions):
        raise ValueError("Use only the canonical cs_no_progress_facts condition")
    if config["provider"] != "openai_sdk" or config["representation_counter"] != "utf8_bytes":
        raise ValueError("Staged runs use openai_sdk and explicit utf8_bytes budgets")
    if "stage" in config and (not isinstance(config["stage"], str) or not config["stage"].strip()):
        raise ValueError("stage must be a nonempty string")
    default = config.get("representation_budget")
    if default is not None and (type(default) is not int or default <= 0):
        raise ValueError("representation_budget must be a positive integer")
    explicit = config.get("condition_budgets", {})
    if not isinstance(explicit, dict) or set(explicit) - set(conditions):
        raise ValueError("condition_budgets must refer only to selected conditions")
    budgets: dict[str, list[int | None]] = {}
    for condition in conditions:
        if condition in {"full_context", "no_history"}:
            if condition in explicit:
                raise ValueError("Full context and no history each run once, without a budget grid")
            budgets[condition] = [None]
            continue
        values = explicit.get(condition, [default] if default is not None else None)
        if (not isinstance(values, list) or not values or any(type(v) is not int or v <= 0 for v in values)
                or len(set(values)) != len(values)):
            raise ValueError(f"{condition} needs a unique positive UTF8 byte budget list")
        budgets[condition] = values
    # Reuse original safety validation, substituting only its old condition shape.
    original = {k: v for k, v in config.items() if k in CONFIG_KEYS | OPTIONAL_CONFIG_KEYS}
    original["conditions"] = ["full_context"]
    original["representation_budget"] = default or next(
        (v for values in budgets.values() for v in values if v is not None), 1)
    validate_original_config(original)
    return budgets


def load_instances(root: Path, config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
    dataset = within(root, config["dataset"])
    manifest = load_json(dataset / "manifest.json")
    if manifest.get("dataset_version") != config["benchmark"]:
        raise ValueError("Dataset version and benchmark differ")
    entries = manifest["instances"]
    ids = [e["instance_id"] for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate dataset IDs")
    selected = config["instance_ids"]
    if selected is not None and set(selected) - set(ids):
        raise ValueError("Unknown selected instance")
    instances = []
    for entry in entries:
        ident = entry["instance_id"]
        if selected is not None and ident not in selected:
            continue
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", ident):
            raise ValueError("Unsafe instance ID")
        item = {"entry": entry}
        for kind in ("task", "environment"):
            item[kind] = load_json(within(dataset, entry[kind]))
            if item[kind].get("instance_id") != ident:
                raise ValueError("Fixture ID mismatch")
        if item["environment"].get("environment_type") != "continuation":
            raise ValueError("Staged runner accepts continuation environments only")
        if not isinstance(item["task"].get("history"), list):
            raise ValueError("Public task history must be a list")
        if "no_history" in config["conditions"]:
            recovery = item["task"].get("recovery_context")
            if not isinstance(recovery, (str, dict)) or not recovery:
                raise ValueError("no_history needs explicit nonempty task.recovery_context")
            # Do not construct recovery context from history, hidden initial state or rubric.
            if isinstance(recovery, dict) and set(recovery) & {"history", "rubric", "initial_state", "target_state"}:
                raise ValueError("Recovery context must not embed history or hidden scoring fields")
        if set(config["conditions"]) & {"cs_no_progress", "cs_no_progress_facts"}:
            terms = item["task"].get("ablation_progress_terms")
            if not isinstance(terms, list) or not terms or any(not isinstance(t, str) or not t.strip() for t in terms):
                raise ValueError("Progress-facts ablation needs explicit task.ablation_progress_terms")
        instances.append(item)
    if not instances:
        raise ValueError("No selected instances")
    return manifest, instances, dataset


def ablate(representation: str, condition: str, terms: list[str] | None = None) -> tuple[str, dict[str, Any]]:
    """Delete fields offline from one validated source; never mutate source state."""
    state = CognitiveState.from_dict(load_string(representation)).to_dict()
    original = deepcopy(state)
    rule: dict[str, Any] = {"condition": condition, "removed": {}, "diagnostic_only": True}
    if condition == "cs_no_frontier":
        rule["removed"]["frontier"] = deepcopy(state["frontier"])
        state["frontier"] = {"current_focus": "unknown", "information_needs": ["unknown"], "next_action": "unknown"}
    elif condition == "cs_no_uncertainty":
        for field in ("beliefs", "assumptions"):
            rule["removed"][field] = deepcopy(state["world"][field])
            state["world"][field] = []
    elif condition in {"cs_no_progress", "cs_no_progress_facts"}:
        if not terms:
            raise ValueError("Missing explicit progress-facts terms")
        removed = [fact for fact in state["world"]["facts"] if any(t.casefold() in fact.casefold() for t in terms)]
        state["world"]["facts"] = [fact for fact in state["world"]["facts"] if fact not in removed]
        rule.update({"match": "case-insensitive literal substring in world.facts only", "terms": terms,
                     "scope_limitation": "Other fields may still encode progress; this is not full progress removal"})
        rule["removed"]["facts"] = removed
    else:
        raise ValueError("Unknown ablation")
    rule["removed_item_count"] = (1 if condition == "cs_no_frontier" else sum(len(v) for v in rule["removed"].values()))
    rule["changed"] = state != original
    rule["no_op"] = not rule["changed"]
    CognitiveState.from_dict(state)
    return compact(state), rule


def load_string(value: str) -> Any:
    from utils.io import parse_json
    return parse_json(value)


class LedgerClient:
    """Log every attempt, including an unknown-cost failed request, with a hard cap."""
    def __init__(self, client: Client, maximum: int):
        self.client, self.maximum = client, maximum
        self.attempts: list[dict[str, Any]] = []

    def complete(self, messages: list[dict[str, str]], *, purpose: str):
        if len(self.attempts) >= self.maximum:
            raise RuntimeError("Configured API call limit reached; no request sent")
        attempt = {"request_index": len(self.attempts), "messages": deepcopy(messages), "purpose": purpose,
                   "status": "pending"}
        self.attempts.append(attempt)
        try:
            completion = self.client.complete(messages, purpose=purpose)
        except RuntimeError as exc:
            attempt.update({"status": "api_error", "error": {"type": "RuntimeError", "message": str(exc)},
                            "metadata": {"input_tokens": None, "output_tokens": None}})
            raise
        attempt.update({"status": "response", "response": completion.text, "metadata": completion.metadata})
        return completion


def ledger_totals(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    values = [a.get("metadata", {}).get(k) for a in attempts for k in ("input_tokens", "output_tokens")]
    known = [v for v in values if type(v) is int]
    return {"request_attempts": len(attempts), "successful_responses": sum(a["status"] == "response" for a in attempts),
            "total_tokens": sum(known) if len(known) == len(values) else None,
            "known_reported_tokens": sum(known), "unknown_usage_attempts": sum(
                any(type(a.get("metadata", {}).get(k)) is not int for k in ("input_tokens", "output_tokens"))
                for a in attempts),
            "shared_extraction_counted_once": True}


def add_usage(a: int | None, b: int | None) -> int | None:
    return a + b if type(a) is int and type(b) is int else None


def behavior_diagnostics(env: ContinuationEnvironment, started: bool) -> dict[str, Any]:
    if not started:
        return {k: None for k in ("steps", "credits", "invalid_actions", "unavailable_resources", "repeat_attempts")}
    repeated = 0
    before = deepcopy(env.fixture["initial_state"])
    for step in env.trace:
        action = step["action"]
        if isinstance(action, dict) and isinstance(action.get("arguments"), dict):
            key = "operations" if action.get("tool") == "execute" else "observations" if action.get("tool") == "observe" else None
            name = action["arguments"].get("operation" if key == "operations" else "resource")
            definition = env.fixture.get(key, {}).get(name, {}) if key and isinstance(name, str) else {}
            if definition.get("repeat_key") and before.get(definition["repeat_key"]) is True:
                repeated += 1
        before = step["state_after"]
    return {"steps": len(env.trace), "credits": env.spent, "invalid_actions": sum(not t["valid"] for t in env.trace),
            "unavailable_resources": sum(t["observation"].get("error") == "Resource unavailable in this continuation" for t in env.trace),
            "repeat_attempts": repeated,
            "repeat_scope": "Configured repeat_key only, including budget-blocked attempts; not all redundant queries"}


def summarize(results: list[dict[str, Any]], complete: bool, planned: int, attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Repeated baselines are never manufactured for budget-grid denominators."""
    baselines = {(r["instance_id"], r["repetition"]): r for r in results if r["condition"] == "full_context"}
    groups = sorted({(r["condition"], r["budget"]) for r in results}, key=lambda t: (t[0], t[1] or 0))
    output: dict[str, Any] = {"performance_evaluation_available": complete,
                            "evidence_type": "staged_synthetic_validation" if complete else "incomplete_run",
                            "planned_runs": planned, "saved_runs": len(results), "actual_suite_usage": ledger_totals(attempts),
                            "baseline_scope": "One full_context execution per task/repetition, reused only for paired comparison",
                            "conditions": {}, "scientific_conclusion": None}
    for condition, budget in groups:
        name = condition if budget is None else f"{condition}@{budget}"
        rows = [r for r in results if (r["condition"], r["budget"]) == (condition, budget)]
        stats: dict[str, Any] = {"condition": condition, "budget": budget, "assigned_runs": len(rows),
                                "errors": sum(r["error"] is not None for r in rows), "diagnostic_only": condition in ABLATIONS,
                                "scopes": {}}
        for scope in ("all", "main", "controls"):
            selected = [r for r in rows if scope == "all" or bool(r["control"]) == (scope == "controls")]
            n = len(selected)
            successes = sum(r["metrics"]["task_success"] for r in selected)
            scoped: dict[str, Any] = {"runs": n, "successes": successes if complete else None,
                                     "task_success_rate": successes / n if complete and n else None}
            comparisons = [(r, baselines[(r["instance_id"], r["repetition"])]) for r in selected
                           if (r["instance_id"], r["repetition"]) in baselines]
            scoped["paired_vs_full"] = {"runs": len(comparisons), "wins": None, "losses": None, "both_success": None,
                                        "success_rate_delta": None}
            if complete and comparisons:
                wins = sum(r["metrics"]["task_success"] and not b["metrics"]["task_success"] for r, b in comparisons)
                losses = sum(not r["metrics"]["task_success"] and b["metrics"]["task_success"] for r, b in comparisons)
                scoped["paired_vs_full"].update({"wins": wins, "losses": losses,
                    "both_success": sum(r["metrics"]["task_success"] and b["metrics"]["task_success"] for r, b in comparisons),
                    "success_rate_delta": (wins - losses) / len(comparisons)})
            pairs: dict[tuple[str, int], list[dict[str, Any]]] = {}
            for r in selected:
                if r["pair_id"] and not r["control"]:
                    pairs.setdefault((r["pair_id"], r["repetition"]), []).append(r)
            valid_pairs = [rs for rs in pairs.values() if len(rs) == 2 and len({r["variant"] for r in rs}) == 2]
            scoped["paired_variant_joint_success"] = {"pairs": len(valid_pairs), "successes": sum(
                all(r["metrics"]["task_success"] for r in rs) for rs in valid_pairs) if complete else None}
            scoped["paired_variant_joint_success"]["rate"] = (scoped["paired_variant_joint_success"]["successes"] / len(valid_pairs)
                if complete and valid_pairs else None)
            scoped["end_to_end_token_reduction"] = None
            scoped["token_reduction_observed_runs"] = 0
            if complete and condition not in ABLATIONS:
                reductions = [1 - r["deployment_token_usage"]["total_tokens"] / b["deployment_token_usage"]["total_tokens"]
                              for r, b in comparisons if r["status"] != "error" and b["status"] != "error"
                              and type(r["deployment_token_usage"]["total_tokens"]) is int
                              and type(b["deployment_token_usage"]["total_tokens"]) is int and b["deployment_token_usage"]["total_tokens"] > 0]
                scoped["end_to_end_token_reduction"] = sum(reductions) / len(reductions) if reductions else None
                scoped["token_reduction_observed_runs"] = len(reductions)
            scoped["deployment_reported_tokens"] = sum(r["deployment_token_usage"]["total_tokens"] for r in selected) if all(
                type(r["deployment_token_usage"]["total_tokens"]) is int for r in selected) else None
            scoped["deployment_cost_scope"] = "Each scenario includes entire shared extraction plus its executor; do not sum scenarios as suite charges"
            scoped["cost_failure_scope"] = "Known usage includes representation/execution failures; incomplete API runs have no performance or reductions"
            scoped["token_reduction_scope"] = "Both paired statuses must be non-error and usage observable; task_success is not used as a filter"
            scoped["token_reduction_error_excluded_pairs"] = sum(r["status"] == "error" or b["status"] == "error" for r, b in comparisons)
            scoped["unique_instances"] = len({r["instance_id"] for r in selected})
            scoped["repetitions"] = sorted({r["repetition"] for r in selected})
            scoped["representation_errors"] = sum(r["error"] is not None and r["error"]["stage"] == "representation" for r in selected)
            scoped["representation_error_rate"] = scoped["representation_errors"] / n if complete and n else None
            scoped["byte_budget_errors"] = sum(r["error"] is not None and r["error"]["stage"] == "representation"
                                               and "exceeds" in r["error"]["message"].lower() and "budget" in r["error"]["message"].lower()
                                               for r in selected)
            scoped["executor_errors"] = sum(r["error"] is not None and r["error"]["stage"] == "executor" for r in selected)
            effective = [r.get("ablation_removed_item_count") for r in selected if r.get("ablation_removed_item_count") is not None]
            scoped["ablation_applied_runs"] = len(effective)
            scoped["ablation_removed_items"] = sum(effective) if effective else None
            changes = [r["ablation_changed"] for r in selected if r.get("ablation_changed") is not None]
            scoped["ablation_changed_runs"] = sum(changes) if changes else None
            scoped["ablation_no_op_runs"] = sum(not changed for changed in changes) if changes else None
            scoped["ablation_zero_removed_runs"] = sum(n == 0 for n in effective) if effective else None
            scoped["ablation_effect_scope"] = "Zero removed items is a no-op and cannot test the necessity of the absent field"
            for metric in ("steps", "credits", "invalid_actions", "repeat_attempts"):
                values = [r["diagnostics"].get(metric) for r in selected if r["diagnostics"].get(metric) is not None]
                scoped[metric + "_mean"] = sum(values) / len(values) if complete and values else None
                scoped[metric + "_observed_runs"] = len(values)
            stats["scopes"][scope] = scoped
        output["conditions"][name] = stats
    return output


def run_staged_experiment(root: Path, config_path: Path, output: Path,
                          progress: Callable[[dict[str, Any]], None] | None = None,
                          *, client: Client | None = None) -> dict[str, Any]:
    """Client injection is solely for offline tests; CLI always uses configured SDK."""
    root, output = root.resolve(), output.resolve()
    config = load_json(config_path)
    budgets = validate_config(config)
    manifest, instances, dataset = load_instances(root, config)
    prompts_dir = root / "prompts" / config["prompt_version"]
    prompts = {name: (prompts_dir / f"{name}.txt").read_text(encoding="utf-8") for name in ("summary", "cognitive_state", "executor")}
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "config.json", config)
    files = {"manifest.json": dataset / "manifest.json"}
    for item in instances:
        for kind in ("task", "environment"):
            files[item["entry"][kind]] = within(dataset, item["entry"][kind])
    for relative, path in files.items():
        target = output / "inputs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copytree(prompts_dir, output / "prompts")
    source_hashes = {}
    for directory in (root / "src", root / "scripts"):
        for path in directory.rglob("*.py"):
            relative = path.relative_to(root).as_posix()
            target = output / "source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            source_hashes[relative] = digest(target)
    try:
        git = ["git", "-c", f"safe.directory={root.as_posix()}"]
        commit = subprocess.check_output(git + ["rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(git + ["status", "--porcelain"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    planned = len(instances) * config["repetitions"] * sum(len(values) for values in budgets.values())
    provenance = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat(), "assigned_runs": planned,
                  "git_commit": commit, "git_dirty": dirty, "python_version": platform.python_version(),
                  "dependencies": dependency_versions(), "dataset_version": manifest["dataset_version"],
                  "input_sha256": {name: digest(output / "inputs" / name) for name in files},
                  "prompt_sha256": {name: digest(output / "prompts" / f"{name}.txt") for name in prompts},
                  "code_sha256": source_hashes, "source_snapshot": "source/", "seed_scope": "Execution order only; not model sampling",
                  "condition_budgets": budgets, "client_source": "injected_offline_test" if client else "configured_openai_sdk",
                  "extraction_scope": "One full automatic CS per task/repetition/budget, reused by all CS ablations",
                  "baseline_scope": "Full context and no history once per task/repetition, no manufactured budget repeats"}
    save_json(output / "manifest.json", provenance)
    results: list[dict[str, Any]] = []
    extractions: list[dict[str, Any]] = []
    counter = RepresentationCounter("utf8_bytes")
    rng = random.Random(config["randomization_seed"])
    ledger: LedgerClient | None = None

    def flush() -> None:
        save_json(output / "results.json", results)
        save_json(output / "extraction_records.json", extractions)
        save_json(output / "call_ledger.json", ledger.attempts if ledger else [])
        provenance["saved_runs"] = len(results)
        save_json(output / "manifest.json", provenance)

    try:
        if client is None:
            provenance["dotenv_loaded"] = load_project_env(root)
            client = OpenAISDKClient(config)
        else:
            provenance["dotenv_loaded"] = False
        ledger = LedgerClient(client, config["max_api_calls"])
        executor = AgentExecutor(ledger, prompts["executor"], config["max_steps"])
        for item in instances:
            ident, history = item["entry"]["instance_id"], item["task"]["history"]
            full = compact(history)
            for repetition in range(config["repetitions"]):
                shared: dict[tuple[str, int], dict[str, Any]] = {}
                order = [(condition, budget) for condition, values in budgets.items() for budget in values]
                rng.shuffle(order)
                for order_index, (condition, budget) in enumerate(order):
                    env = ContinuationEnvironment(item["environment"])
                    representation, rule, error, extraction = None, None, None, None
                    stage, count = "representation", None
                    calls: list[dict[str, Any]] = []
                    first_attempt = len(ledger.attempts)
                    try:
                        if condition == "full_context":
                            representation = full
                        elif condition == "no_history":
                            recovery = item["task"]["recovery_context"]
                            representation = recovery if isinstance(recovery, str) else compact(recovery)
                        else:
                            source_condition = "cognitive_state" if condition in ABLATIONS else condition
                            key = (source_condition, budget)
                            if key not in shared:
                                extraction_calls: list[dict[str, Any]] = []
                                start = len(ledger.attempts)
                                extraction_error, source = None, None
                                try:
                                    source = StateExtractor(ledger, counter, budget).extract(history, source_condition, prompts[source_condition], extraction_calls)
                                except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
                                    extraction_error = {"stage": "representation", "type": type(exc).__name__, "message": str(exc)}
                                path = f"extractions/{ident}_r{repetition}_{source_condition}_b{budget}.json"
                                extraction = {"instance_id": ident, "repetition": repetition, "source_condition": source_condition,
                                              "budget": budget, "representation": source, "error": extraction_error,
                                              "calls": extraction_calls, "request_indices": list(range(start, len(ledger.attempts))),
                                              "token_usage": ledger_totals(ledger.attempts[start:]), "artifact": path,
                                              "representation_size": counter.count(source) if source is not None else None,
                                              "raw_response_sizes": [counter.count(c["response"]) for c in extraction_calls]}
                                shared[key] = extraction
                                extractions.append(extraction)
                                save_json(output / path, extraction)
                                flush()
                            extraction = shared[key]
                            if extraction["error"]:
                                error = deepcopy(extraction["error"])
                                if error["type"] == "RuntimeError":
                                    raise RuntimeError(error["message"])
                                raise ValueError("Shared extraction failed; see frozen extraction artifact")
                            representation = extraction["representation"]
                            if condition in ABLATIONS:
                                representation, rule = ablate(representation, condition, item["task"].get("ablation_progress_terms"))
                        count = counter.count(representation)
                        if budget is not None and count > budget:
                            raise ValueError("Representation exceeds UTF8 byte budget; no truncation performed")
                        stage = "executor"
                        executor.run(representation, env, calls)
                    except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
                        error = error or {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
                    metrics = env.evaluate()
                    if error:
                        metrics["task_success"] = False
                    exec_attempts = [a for a in ledger.attempts[first_attempt:] if a["purpose"] == "executor"]
                    exec_usage = ledger_totals(exec_attempts)
                    extraction_usage = extraction["token_usage"]["total_tokens"] if extraction else 0
                    deployment_usage = {"extraction_tokens": extraction_usage, "executor_tokens": exec_usage["total_tokens"],
                                        "total_tokens": add_usage(extraction_usage, exec_usage["total_tokens"]),
                                        "initial_executor_input_tokens": exec_attempts[0].get("metadata", {}).get("input_tokens") if exec_attempts else None,
                                        "scope": "Independent deployment equivalent, including entire shared extraction"}
                    artifact = f"instances/{ident}_r{repetition}_{condition}_b{budget if budget is not None else 'none'}.json"
                    row = {"instance_id": ident, "repetition": repetition, "condition": condition, "budget": budget,
                           "control": bool(item["entry"].get("control", False)), "pair_id": item["entry"].get("pair_id"),
                           "variant": item["entry"].get("variant"), "order_index": order_index,
                           "status": "error" if error else "completed", "error": error,
                           "termination": "error" if error else "finished" if env.finished else "step_limit", "metrics": metrics,
                           "representation_size": count, "full_history_size": counter.count(full), "representation_counter": "utf8_bytes",
                           "budget_compliant": count <= budget if count is not None and budget is not None else None,
                           "deployment_token_usage": deployment_usage,
                           "extraction_artifact": extraction["artifact"] if extraction else None,
                           "execution_started": bool(exec_attempts), "diagnostic_only": condition in ABLATIONS,
                           "ablation_removed_item_count": rule["removed_item_count"] if rule else None,
                           "ablation_changed": rule["changed"] if rule else None,
                           "diagnostics": behavior_diagnostics(env, bool(exec_attempts)), "artifacts": [artifact]}
                    save_json(output / artifact, {"result": row, "representation": representation, "ablation_rule": rule,
                                                 "calls": calls, "trace": env.trace, "final_settings": env.settings,
                                                 "request_indices": [a["request_index"] for a in exec_attempts],
                                                 "extraction_artifact": extraction["artifact"] if extraction else None})
                    results.append(row)
                    flush()
                    if progress:
                        progress({"saved_runs": len(results), "assigned_runs": planned, "instance_id": ident,
                                  "condition": condition, "budget": budget, "repetition": repetition,
                                  "status": row["status"], "success": metrics["task_success"], "error": error})
                    if error and error["type"] == "RuntimeError":
                        provenance["status"] = "aborted_api_error"
                        break
                if provenance["status"] == "aborted_api_error":
                    break
            if provenance["status"] == "aborted_api_error":
                break
        if provenance["status"] != "aborted_api_error":
            provenance["status"] = "completed_with_errors" if any(r["error"] for r in results) else "completed"
    except BaseException:
        provenance["status"] = "interrupted"
        raise
    finally:
        provenance["finished_at"] = datetime.now(timezone.utc).isoformat()
        flush()
        complete = provenance["status"] in {"completed", "completed_with_errors"} and len(results) == planned
        summary = summarize(results, complete, planned, ledger.attempts if ledger else [])
        summary["status"] = provenance["status"]
        save_json(output / "summary.json", summary)
    return summary
