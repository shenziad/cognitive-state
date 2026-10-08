"""A small, serial handoff experiment with genuine loss of discarded history."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import shutil
from typing import Any, Callable

from agents.agent import AgentExecutor
from llm.client import OpenAISDKClient
from llm.environment import load_project_env
from llm.tokens import RepresentationCounter
from state.extractor import StateExtractor
from utils.io import digest, load_json, save_json
from .continuation import ContinuationEnvironment
from .runner import dependency_versions, usage_total, within


CONDITIONS = {"full_context", "summary", "cognitive_state", "no_history"}


class RequestLimitReached(RuntimeError):
    """The local guard stopped before sending another request."""


class BoundedClient:
    def __init__(self, client: Any, maximum: int):
        self.client, self.maximum, self.request_attempts = client, maximum, 0

    def complete(self, messages, *, purpose):
        if self.request_attempts >= self.maximum:
            raise RequestLimitReached("Configured API call limit reached; no request sent")
        self.request_attempts += 1
        return self.client.complete(messages, purpose=purpose)


class HandoffMemory:
    """Only full_context owns an archive. Compressed updates cannot access one."""

    def __init__(self, condition: str, public_goal: dict[str, Any]):
        if condition not in CONDITIONS:
            raise ValueError("Unknown longitudinal condition")
        self.condition = condition
        self.public_goal = deepcopy(public_goal) if condition == "no_history" else None
        self.available = [deepcopy(public_goal)]

    def update_input(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.condition == "no_history":
            return [deepcopy(self.public_goal)] + deepcopy(events)
        return deepcopy(self.available) + deepcopy(events)

    def retain(self, history: list[dict[str, Any]], representation: str,
               trace: list[dict[str, Any]], handoff: int) -> None:
        executed = []
        for index, item in enumerate(trace):
            executed.extend([
                {"id": f"h{handoff}_a{index}", "role": "assistant",
                 "content": json.dumps(item["action"], ensure_ascii=False)},
                {"id": f"h{handoff}_o{index}", "role": "tool",
                 "content": json.dumps(item["observation"], ensure_ascii=False)},
            ])
        if self.condition == "full_context":
            self.available = deepcopy(history) + executed
        elif self.condition in {"summary", "cognitive_state"}:
            # This replaces rather than appends the history supplied to the extractor.
            self.available = [{"id": f"retained_h{handoff}", "role": "assistant",
                               "content": representation}] + executed
        else:
            self.available = [deepcopy(self.public_goal)]


class LongitudinalEnvironment:
    """Reopen the same virtual world; only the advertised external events patch it."""

    def __init__(self, initial_state: dict[str, Any]):
        self.settings = deepcopy(initial_state)

    def open_handoff(self, stage: dict[str, Any]) -> ContinuationEnvironment:
        self.settings.update(deepcopy(stage.get("external_state_patch", {})))
        fixture = deepcopy(stage["environment"])
        fixture["initial_state"] = deepcopy(self.settings)
        return ContinuationEnvironment(fixture)

    def close_handoff(self, environment: ContinuationEnvironment) -> None:
        self.settings = deepcopy(environment.settings)


def repeated_attempts(env: ContinuationEnvironment) -> int:
    """Include attempts rejected on budget, which the base repeat counter omits."""
    before, count = deepcopy(env.fixture["initial_state"]), 0
    for row in env.trace:
        action = row["action"]
        if isinstance(action, dict) and action.get("tool") == "execute":
            args = action.get("arguments", {})
            operation = args.get("operation") if isinstance(args, dict) else None
            definition = env.fixture["operations"].get(operation) if isinstance(operation, str) else None
            if definition and definition.get("repeat_key") and before.get(definition["repeat_key"]) is True:
                count += 1
        before = row["state_after"]
    return count


def malformed_action(action: Any) -> bool:
    """Protocol shape errors are distinct from a legal operation's precondition failure."""
    if not isinstance(action, dict) or set(action) != {"tool", "arguments"}:
        return True
    tool, arguments = action["tool"], action["arguments"]
    fields = {"observe": "resource", "execute": "operation", "finish": "status"}
    if not isinstance(tool, str) or tool not in fields or not isinstance(arguments, dict):
        return True
    field = fields[tool]
    return set(arguments) != {field} or not isinstance(arguments[field], str) or (
        tool == "finish" and arguments[field] not in {"completed", "blocked"})


def handoff_metrics(env: ContinuationEnvironment, execution_started: bool,
                    error: dict[str, Any] | None, skipped: bool) -> dict[str, Any]:
    metrics = env.evaluate()
    metrics["repeated_work_attempts"] = repeated_attempts(env)
    metrics["format_error_count"] = sum(malformed_action(row["action"]) for row in env.trace)
    metrics["task_success"] = bool(metrics["task_success"] and not error and not skipped and not metrics["format_error_count"])
    if not execution_started:
        for key in ("final_goal_completion", "tool_usage_correctness", "decision_consistency", "goal_checks",
                    "decision_checks", "policy_violation_count", "repeated_work_count", "repeated_work_attempts",
                    "format_error_count", "unavailable_observation_count", "workspace_credits_spent"):
            metrics[key] = None
    return metrics


def load_inputs(root: Path, config: dict[str, Any]) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    required = {"experiment_id", "benchmark", "dataset", "prompt_version", "conditions", "repetitions",
                "randomization_seed", "max_steps", "representation_counter", "representation_budget",
                "provider", "model", "temperature", "endpoint", "api_key_env", "output_limit_parameter",
                "max_output_tokens", "timeout_seconds", "max_api_calls", "extra_body"}
    if set(config) != required or config["provider"] != "openai_sdk":
        raise ValueError("Use the explicit SDK longitudinal config schema")
    if set(config["conditions"]) != CONDITIONS or len(config["conditions"]) != 4:
        raise ValueError("Choose each of Full, Summary, CS, and no_history once")
    for key in ("repetitions", "max_steps", "representation_budget", "max_output_tokens", "timeout_seconds", "max_api_calls"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if config["repetitions"] != 1 or not 4 <= config["max_steps"] <= 6 or config["max_api_calls"] > 320:
        raise ValueError("This pilot is limited to one repetition, 4-6 steps and <=320 requests")
    if config["representation_counter"] != "utf8_bytes" or config["temperature"] != 0:
        raise ValueError("This pilot freezes a UTF-8 byte budget and temperature zero")
    dataset = within(root, config["dataset"])
    manifest = load_json(dataset / "manifest.json")
    if manifest["dataset_version"] != config["benchmark"] or len(manifest["scenarios"]) != 2:
        raise ValueError("Expected this two-scenario dataset version")
    scenarios = [load_json(within(dataset, entry["path"])) for entry in manifest["scenarios"]]
    ids = [scenario["scenario_id"] for scenario in scenarios]
    if len(set(ids)) != 2 or any(not ident.replace("_", "").isalnum() for ident in ids):
        raise ValueError("Scenario IDs must be unique safe identifiers")
    for scenario in scenarios:
        if len(scenario["handoffs"]) != 4:
            raise ValueError("Every scenario must have four handoffs")
        for stage in scenario["handoffs"]:
            if stage["environment"].get("initial_state"):
                raise ValueError("Stage fixtures cannot reset the retained world")
            if not stage["public_events"] or set(stage["environment"]["rubric"]) - {
                    "target_state", "finish_status", "forbidden_actions", "before_action"}:
                raise ValueError("Invalid stage fixture")
    # Reuse the normal transport config checks without imposing exp001 conditions.
    from .runner import validate_config
    transport_config = {**config, "conditions": ["full_context", "summary", "cognitive_state"], "instance_ids": None}
    validate_config(transport_config)
    return dataset, manifest, scenarios


def summarize(rows: list[dict[str, Any]], completed: bool) -> dict[str, Any]:
    chains = {}
    for row in rows:
        key = (row["scenario_id"], row["condition"])
        chains.setdefault(key, []).append(row)
    stats = {}
    for condition in sorted(CONDITIONS):
        selected = [row for row in rows if row["condition"] == condition]
        chain_rows = [items for key, items in chains.items() if key[1] == condition]
        totals = [row["token_usage"]["total_tokens"] for row in selected]
        stats[condition] = {
            "assigned_handoffs": 8, "saved_handoffs": len(selected),
            "attempted_handoffs": sum(row["status"] != "skipped_chain_error" for row in selected),
            "executed_handoffs": sum(row["execution_started"] for row in selected),
            "successful_handoffs": sum(row["metrics"]["task_success"] for row in selected) if completed else None,
            "assigned_chains": 2,
            "successful_chains": sum(len(items) == 4 and all(row["metrics"]["task_success"] for row in items)
                                     for items in chain_rows) if completed else None,
            "reported_total_tokens": sum(row["token_usage"]["reported_total_tokens"] for row in selected
                                         if type(row["token_usage"]["reported_total_tokens"]) is int),
            "total_tokens": sum(totals) if len(selected) == 8 and all(type(v) is int for v in totals) else None,
            "successful_handoffs_by_position": {
                str(index): sum(row["handoff"] == index and row["metrics"]["task_success"] for row in selected)
                if completed else None for index in range(1, 5)},
            "repeated_work_attempts": sum(row["metrics"].get("repeated_work_attempts") or 0 for row in selected),
            "repeated_work_observed_handoffs": sum(row["metrics"].get("repeated_work_attempts") is not None for row in selected),
            "workspace_credits_spent": sum(row["metrics"].get("workspace_credits_spent") or 0 for row in selected),
            "workspace_credits_observed_handoffs": sum(row["metrics"].get("workspace_credits_spent") is not None for row in selected),
            "call_count": sum(row["call_count"] for row in selected),
        }
    return {"evidence_type": "unreviewed_synthetic_multi_handoff_pilot" if completed else "api_interruption",
            "performance_evaluation_available": completed, "conditions": stats,
            "scientific_conclusion": None}


def run_longitudinal(root: Path, config_path: Path, output: Path,
                     progress: Callable[[dict[str, Any]], None] | None = None,
                     client: Any = None) -> dict[str, Any]:
    root = root.resolve()
    config = load_json(config_path)
    dataset, manifest, scenarios = load_inputs(root, config)
    prompt_dir = within(root, "prompts/" + config["prompt_version"])
    prompts = {name: (prompt_dir / f"{name}.txt").read_text(encoding="utf-8")
               for name in ("summary", "cognitive_state", "executor")}
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "config.json", config)
    shutil.copytree(dataset, output / "inputs")
    shutil.copytree(prompt_dir, output / "prompts")
    code_files = [path for directory in (root / "src", root / "scripts") for path in directory.rglob("*.py")]
    for path in code_files:
        frozen = output / "source" / path.relative_to(root)
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, frozen)
    counter = RepresentationCounter(config["representation_counter"])
    provenance = {
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
        "assigned_chains": 8, "assigned_handoffs": 32, "dataset_version": manifest["dataset_version"],
        "input_sha256": {path.relative_to(dataset).as_posix(): digest(path) for path in dataset.rglob("*.json")},
        "prompt_sha256": {name: digest(prompt_dir / f"{name}.txt") for name in prompts},
        "code_sha256": {path.relative_to(root).as_posix(): digest(output / "source" / path.relative_to(root))
                        for path in code_files},
        "dependencies": dependency_versions(), "dotenv_loaded": False,
        "seed_scope": "condition order only; model sampling is not seeded",
        "history_policy": "compressed update reads retained representation + last executed actions/observations + new events only",
        "no_history_policy": "original shared public user objective plus this checkpoint's public events; no past tool observations",
        "fixture_scoring_rules_visible_to_models": False,
    }
    save_json(output / "manifest.json", provenance)
    rows: list[dict[str, Any]] = []
    interrupted, bounded, limit_reached = False, None, False
    save_json(output / "results.json", rows)
    try:
        if client is None:
            provenance["dotenv_loaded"] = load_project_env(root)
            client = OpenAISDKClient(config)
        bounded = BoundedClient(client, config["max_api_calls"])
        extractor = StateExtractor(bounded, counter, config["representation_budget"])
        executor = AgentExecutor(bounded, prompts["executor"], config["max_steps"])
        rng = random.Random(config["randomization_seed"])
        for scenario in scenarios:
            order = list(config["conditions"])
            rng.shuffle(order)
            for order_index, condition in enumerate(order):
                memory = HandoffMemory(condition, scenario["public_goal"])
                world = LongitudinalEnvironment(scenario["initial_state"])
                chain_error = False
                for handoff, stage in enumerate(scenario["handoffs"], start=1):
                    if interrupted:
                        break
                    env = world.open_handoff(stage)
                    calls: list[dict[str, Any]] = []
                    representation, error = None, None
                    input_history = None if chain_error else memory.update_input(stage["public_events"])
                    count, extraction_stage, unreported_request = None, True, False
                    if not chain_error:
                        try:
                            if condition in {"full_context", "no_history"}:
                                representation = json.dumps(input_history, ensure_ascii=False, separators=(",", ":"))
                            else:
                                representation = extractor.extract(input_history, condition, prompts[condition], calls)
                            count = counter.count(representation)
                            extraction_stage = False
                            executor.run(representation, env, calls)
                        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
                            error = {"stage": "representation" if extraction_stage else "executor",
                                     "type": type(exc).__name__, "message": str(exc)}
                            interrupted = isinstance(exc, (RuntimeError, OSError))
                            limit_reached = isinstance(exc, RequestLimitReached)
                            unreported_request = interrupted and not limit_reached
                            chain_error = extraction_stage or interrupted
                    world.close_handoff(env)
                    exec_calls = [call for call in calls if call["metadata"]["purpose"] == "executor"]
                    execution_started = bool(exec_calls)
                    metrics = handoff_metrics(env, execution_started, error, chain_error)
                    if representation is not None and not chain_error:
                        memory.retain(input_history, representation, env.trace, handoff)
                    reported_total = usage_total(calls)
                    row = {
                        "scenario_id": scenario["scenario_id"], "condition": condition, "handoff": handoff,
                        "order_index": order_index, "status": "error" if error else "skipped_chain_error" if chain_error else "completed",
                        "error": error, "termination": "error" if error else "skipped" if chain_error else "finished" if env.finished else "step_limit",
                        "execution_started": execution_started,
                        "metrics": metrics, "call_count": len(calls), "representation_size": count,
                        "representation_counter": counter.name,
                        "token_usage": {"update_tokens": None if unreported_request and extraction_stage else
                                        usage_total(calls, condition) if condition in {"summary", "cognitive_state"} else 0,
                                        "executor_tokens": None if unreported_request and not extraction_stage else usage_total(exec_calls),
                                        "reported_total_tokens": reported_total,
                                        "total_tokens": None if unreported_request else reported_total,
                                        "first_executor_input_tokens": exec_calls[0]["metadata"].get("input_tokens") if exec_calls else None},
                        "artifact": f"chains/{scenario['scenario_id']}_{condition}/handoff_{handoff}.json",
                    }
                    save_json(output / row["artifact"], {
                        "result": row, "public_update_input": input_history, "representation": representation,
                        "environment_fixture": env.fixture, "public_new_events": stage["public_events"],
                        "calls": calls, "trace": env.trace, "final_settings": env.settings,
                        "next_available_history": memory.available if not chain_error else None,
                    })
                    rows.append(row)
                    save_json(output / "results.json", rows)
                    provenance["saved_handoffs"] = len(rows)
                    provenance["reported_responses"] = sum(r["call_count"] for r in rows)
                    save_json(output / "manifest.json", provenance)
                    if progress:
                        progress({"saved_handoffs": len(rows), "assigned_handoffs": 32,
                                  "scenario_id": scenario["scenario_id"], "condition": condition,
                                  "handoff": handoff, "success": metrics["task_success"], "error": error})
                if interrupted:
                    break
            if interrupted:
                break
        provenance["status"] = "aborted_call_limit" if limit_reached else "aborted_api_error" if interrupted else "completed_with_errors" if any(r["error"] for r in rows) else "completed"
    except BaseException:
        provenance["status"] = "interrupted"
        raise
    finally:
        summary = summarize(rows, provenance["status"] in {"completed", "completed_with_errors"})
        save_json(output / "summary.json", summary)
        provenance.update({"finished_at": datetime.now(timezone.utc).isoformat(), "saved_handoffs": len(rows),
                           "request_attempts": bounded.request_attempts if bounded else 0,
                           "reported_responses": sum(r["call_count"] for r in rows)})
        save_json(output / "manifest.json", provenance)
    return summary
