"""Paired pilot execution, frozen inputs and explicit result artifacts."""

import json
import random
import re
import shutil
import subprocess
import platform
from importlib.metadata import PackageNotFoundError, version
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from agents.agent import AgentExecutor
from llm.client import ChatCompletionsClient, OpenAISDKClient
from llm.environment import load_project_env
from llm.mock import MockClient
from llm.tokens import RepresentationCounter
from state.extractor import StateExtractor
from state.representation import CognitiveState
from utils.io import digest, load_json, save_json
from .controlled import ControlledEnvironment
from .continuation import ContinuationEnvironment
from .metrics import token_reduction

CONDITIONS = {"full_context", "summary", "cognitive_state", "reference_state"}
CONFIG_KEYS = {
    "experiment_id", "benchmark", "dataset", "prompt_version", "conditions", "instance_ids",
    "repetitions", "randomization_seed", "max_steps", "representation_counter", "representation_budget",
    "provider", "model", "temperature", "endpoint", "api_key_env", "output_limit_parameter",
    "max_output_tokens", "timeout_seconds", "max_api_calls",
}
OPTIONAL_CONFIG_KEYS = {"extra_body"}


class AbortAPI(RuntimeError):
    """Stop an incomplete run after a transport/provider error, without discarding results."""


def dependency_versions() -> dict[str, str | None]:
    found = {}
    for name in ("openai", "python-dotenv", "httpx", "tiktoken"):
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            found[name] = None
    return found


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise ValueError("Config must be a JSON object")
    if CONFIG_KEYS - set(config) or set(config) - CONFIG_KEYS - OPTIONAL_CONFIG_KEYS:
        raise ValueError(f"Config keys differ: missing={CONFIG_KEYS - set(config)}, extra={set(config) - CONFIG_KEYS}")
    for key in ("experiment_id", "benchmark", "dataset", "prompt_version", "representation_counter", "model", "api_key_env"):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"{key} must be a nonempty string")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", config["prompt_version"]):
        raise ValueError("prompt_version must be v<major>.<minor>")
    for key in ("repetitions", "max_steps", "representation_budget", "max_output_tokens", "timeout_seconds", "max_api_calls"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if type(config["randomization_seed"]) is not int:
        raise ValueError("randomization_seed must be an integer")
    conditions = config["conditions"]
    if (not isinstance(conditions, list) or not conditions or any(c not in CONDITIONS for c in conditions)
            or len(set(conditions)) != len(conditions) or "full_context" not in conditions):
        raise ValueError("Choose unique supported conditions including full_context")
    ids = config["instance_ids"]
    if ids is not None and (not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids)
                            or len(set(ids)) != len(ids)):
        raise ValueError("instance_ids must be null or a nonempty list of unique IDs")
    temp = config["temperature"]
    if temp is not None and (type(temp) not in (int, float) or not 0 <= temp <= 2):
        raise ValueError("temperature must be null or a number in [0, 2]")
    if config["output_limit_parameter"] not in {"max_completion_tokens", "max_tokens"}:
        raise ValueError("Select max_completion_tokens or max_tokens explicitly")
    if config["provider"] not in {"mock", "chat_completions", "openai_sdk"}:
        raise ValueError("Unknown provider")
    if config.get("extra_body") is not None:
        body = config["extra_body"]
        if (not isinstance(body, dict) or set(body) - {"enable_thinking", "thinking_budget", "reasoning_effort"}):
            raise ValueError("extra_body accepts only explicit thinking controls")
        if "enable_thinking" in body and type(body["enable_thinking"]) is not bool:
            raise ValueError("enable_thinking must be boolean")
        if "thinking_budget" in body and (type(body["thinking_budget"]) is not int or not 128 <= body["thinking_budget"] <= 32768):
            raise ValueError("thinking_budget must be an integer in [128, 32768]")
        if "reasoning_effort" in body and body["reasoning_effort"] not in {"high", "max"}:
            raise ValueError("reasoning_effort must be high or max")
    if config["provider"] in {"chat_completions", "openai_sdk"}:
        if not (config["representation_counter"].startswith("tiktoken:") or config["representation_counter"] == "utf8_bytes"):
            raise ValueError("Select an explicit tokenizer or a clearly labeled byte budget")
        endpoint = urlparse(config["endpoint"] or "")
        if (endpoint.scheme != "https" or not endpoint.netloc or endpoint.username or endpoint.password
                or endpoint.query or endpoint.fragment):
            raise ValueError("Endpoint must be an HTTPS URL without credentials or query parameters")
    elif config["representation_counter"] != "utf8_bytes":
        raise ValueError("The mock counter must be utf8_bytes, not provider tokens")


def within(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Input path must remain within its declared directory")
    return path


def load_dataset(root: Path, config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
    dataset = within(root, config["dataset"])
    manifest = load_json(dataset / "manifest.json")
    if manifest["dataset_version"] != config["benchmark"]:
        raise ValueError("Benchmark and dataset version differ")
    entries = manifest["instances"]
    all_ids = [entry["instance_id"] for entry in entries]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("Duplicate dataset IDs")
    requested = config["instance_ids"]
    if requested is not None and set(requested) - set(all_ids):
        raise ValueError("Unknown instance ID in config")
    selected = [entry for entry in entries if requested is None or entry["instance_id"] in requested]
    loaded = []
    for entry in selected:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", entry["instance_id"]):
            raise ValueError("Unsafe instance ID")
        item = {"entry": entry}
        for kind in ("task", "environment", "reference"):
            item[kind] = load_json(within(dataset, entry[kind]))
            if item[kind]["instance_id"] != entry["instance_id"]:
                raise ValueError("Fixture ID mismatch")
        CognitiveState.from_dict(item["reference"]["state"])
        history_ids = {message["id"] for message in item["task"]["history"]}
        for ids in item["reference"]["source_message_ids"].values():
            if set(ids) - history_ids:
                raise ValueError("Reference provenance points beyond public history")
        loaded.append(item)
    if not loaded:
        raise ValueError("No instances selected")
    return manifest, loaded, dataset


def usage_total(calls: list[dict[str, Any]], purpose: str | None = None) -> int | None:
    selected = [call for call in calls if purpose is None or call["metadata"]["purpose"] == purpose]
    values = [call["metadata"].get(key) for call in selected for key in ("input_tokens", "output_tokens")]
    return sum(values) if all(type(value) is int for value in values) else None


def attach_reductions(results: list[dict[str, Any]]) -> None:
    baselines = {(r["instance_id"], r["repetition"]): r for r in results if r["condition"] == "full_context"}
    for row in results:
        baseline = baselines.get((row["instance_id"], row["repetition"]))
        row["metrics"]["token_reduction"] = None
        row["metrics"]["end_to_end_token_reduction"] = None
        if baseline is None or row["status"] == "error" or baseline["status"] == "error":
            continue
        for source, metric in (("initial_executor_input_tokens", "token_reduction"),
                               ("total_tokens", "end_to_end_token_reduction")):
            if metric == "end_to_end_token_reduction" and row["condition"] == "reference_state":
                continue  # Candidate authoring cost is unmeasured.
            base, value = baseline["token_usage"][source], row["token_usage"][source]
            if type(base) is int and base > 0 and type(value) is int:
                row["metrics"][metric] = token_reduction(base, value)


def aggregate(results: list[dict[str, Any]], mock: bool) -> dict[str, Any]:
    out: dict[str, Any] = {"evidence_type": "mock_protocol_validation" if mock else "unreviewed_synthetic_pilot",
                           "scientific_conclusion": None, "conditions": {}}
    for condition in sorted({r["condition"] for r in results}):
        rows = [r for r in results if r["condition"] == condition]
        stats = {"assigned_runs": len(rows), "errors": sum(r["status"] == "error" for r in rows),
                 "task_success_rate": sum(r["metrics"]["task_success"] for r in rows) / len(rows)}
        for metric in ("final_goal_completion", "tool_usage_correctness", "decision_consistency",
                       "token_reduction", "end_to_end_token_reduction"):
            values = [r["metrics"][metric] for r in rows if r["metrics"].get(metric) is not None]
            stats[metric] = sum(values) / len(values) if values else None
            stats[metric + "_observed_runs"] = len(values)
        out["conditions"][condition] = stats
    return out


def run_experiment(root: Path, config_path: Path, output: Path,
                   progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    root = root.resolve()
    config = load_json(config_path)
    validate_config(config)
    manifest, instances, dataset = load_dataset(root, config)
    types = {item["environment"].get("environment_type", "configuration_repair") for item in instances}
    if types - {"configuration_repair", "continuation"}:
        raise ValueError("Unknown environment type")
    if "continuation" in types and config["provider"] == "mock":
        raise ValueError("The configuration-repair mock cannot solve continuation tasks; use the offline dataset validator")
    counter = RepresentationCounter(config["representation_counter"])
    dotenv_loaded = load_project_env(root) if config["provider"] != "mock" else False
    clients = {"mock": MockClient, "chat_completions": ChatCompletionsClient, "openai_sdk": OpenAISDKClient}
    client = clients[config["provider"]]() if config["provider"] == "mock" else clients[config["provider"]](config)
    prompts_dir = root / "prompts" / config["prompt_version"]
    prompts = {name: (prompts_dir / f"{name}.txt").read_text(encoding="utf-8")
               for name in ("summary", "cognitive_state", "executor")}
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "config.json", config)
    snapshot_files = {"manifest.json": dataset / "manifest.json"}
    for item in instances:
        for kind in ("task", "environment", "reference"):
            relative = item["entry"][kind]
            snapshot_files[relative] = within(dataset, relative)
    for relative, path in snapshot_files.items():
        target = output / "inputs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copytree(prompts_dir, output / "prompts")
    try:
        git = ["git", "-c", f"safe.directory={root.as_posix()}"]
        commit = subprocess.check_output(git + ["rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(git + ["status", "--porcelain"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip())
    except (subprocess.SubprocessError, OSError):
        commit, dirty = None, None
    provenance = {
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
        "git_commit": commit, "git_dirty": dirty, "dataset_version": manifest["dataset_version"],
        "python_version": platform.python_version(), "platform": platform.platform(),
        "dotenv_loaded": dotenv_loaded,
        "dependencies": dependency_versions(),
        "input_sha256": {name: digest(path) for name, path in snapshot_files.items()},
        "prompt_sha256": {name: digest(prompts_dir / f"{name}.txt") for name in prompts},
        "code_sha256": {path.relative_to(root).as_posix(): digest(path)
                        for directory in (root / "src", root / "scripts") for path in directory.rglob("*.py")},
        "reference_review_status": {item["entry"]["instance_id"]: item["reference"]["review"] for item in instances},
        "reference_construction_cost_included": False,
        "counter": counter.name, "seed_scope": "condition order only; model sampling is not seeded",
        "assigned_runs": len(instances) * config["repetitions"] * len(config["conditions"]),
    }
    save_json(output / "manifest.json", provenance)
    results: list[dict[str, Any]] = []
    rng = random.Random(config["randomization_seed"])
    extractor = StateExtractor(client, counter, config["representation_budget"])
    executor = AgentExecutor(client, prompts["executor"], config["max_steps"])
    try:
        for item in instances:
            history = item["task"]["history"]
            full_context = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
            for repetition in range(config["repetitions"]):
                order = list(config["conditions"])
                rng.shuffle(order)
                for order_index, condition in enumerate(order):
                    instance_id = item["entry"]["instance_id"]
                    calls: list[dict[str, Any]] = []
                    env_class = ContinuationEnvironment if item["environment"].get("environment_type") == "continuation" else ControlledEnvironment
                    env = env_class(item["environment"])
                    representation, error, stage = None, None, "representation"
                    count = None
                    try:
                        if condition == "full_context":
                            representation = full_context
                        elif condition == "reference_state":
                            representation = json.dumps(item["reference"]["state"], ensure_ascii=False, separators=(",", ":"))
                        else:
                            representation = extractor.extract(history, condition, prompts[condition], calls)
                        count = counter.count(representation)
                        if condition != "full_context" and count > config["representation_budget"]:
                            raise ValueError("Reference state exceeds the configured representation budget")
                        stage = "executor"
                        executor.run(representation, env, calls)
                    except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
                        error = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
                    metrics = env.evaluate()
                    if error:
                        metrics["task_success"] = False
                    exec_calls = [c for c in calls if c["metadata"]["purpose"] == "executor"]
                    total = usage_total(calls)
                    # A failed request can consume unreported usage; do not publish a partial cost as total.
                    if error and error["type"] == "RuntimeError":
                        total = None
                    row = {
                        "experiment_id": config["experiment_id"], "instance_id": instance_id,
                        "repetition": repetition, "condition": condition, "order_index": order_index,
                        "status": "error" if error else "completed", "error": error,
                        "termination": "error" if error else "finished" if env.finished else "step_limit",
                        "evidence_type": "mock_protocol_validation" if config["provider"] == "mock" else "unreviewed_synthetic_pilot",
                        "metrics": metrics, "representation_size": count, "representation_counter": counter.name,
                        "full_history_size": counter.count(full_context),
                        "representation_budget_compliant": None if condition == "full_context" else count is not None and count <= config["representation_budget"],
                        "token_usage": {"extraction_tokens": usage_total([c for c in calls if c["metadata"]["purpose"] != "executor"]),
                                        "executor_tokens": usage_total(exec_calls), "total_tokens": total,
                                        "initial_executor_input_tokens": exec_calls[0]["metadata"].get("input_tokens") if exec_calls else None},
                        "call_count": len(calls), "config": config,
                    }
                    artifact = f"instances/{instance_id}_r{repetition}_{condition}.json"
                    row["artifacts"] = [artifact]
                    save_json(output / artifact, {"result": row, "representation": representation,
                                                "calls": calls, "trace": env.trace, "final_settings": env.settings})
                    results.append(row)
                    save_json(output / "results.json", results)
                    if progress:
                        progress({"saved_runs": len(results), "assigned_runs": provenance["assigned_runs"],
                                  "instance_id": instance_id, "condition": condition,
                                  "status": row["status"], "success": metrics["task_success"], "error": error})
                    if config["provider"] != "mock" and error and error["type"] == "RuntimeError":
                        raise AbortAPI("Run stopped after provider/transport error")
        attach_reductions(results)
        save_json(output / "results.json", results)
        # Keep per-instance result records consistent with final paired metrics.
        for row in results:
            path = output / row["artifacts"][0]
            artifact_data = load_json(path)
            artifact_data["result"] = row
            save_json(path, artifact_data)
        summary = aggregate(results, config["provider"] == "mock")
        save_json(output / "summary.json", summary)
        provenance["status"] = "completed_with_errors" if any(r["error"] for r in results) else "completed"
    except AbortAPI:
        attach_reductions(results)
        save_json(output / "results.json", results)
        for row in results:
            path = output / row["artifacts"][0]
            data = load_json(path)
            data["result"] = row
            save_json(path, data)
        summary = aggregate(results, False)
        summary["incomplete_run"] = True
        summary["evidence_type"] = "api_interruption"
        summary["performance_evaluation_available"] = False
        summary["planned_runs"] = provenance["assigned_runs"]
        summary["saved_runs"] = len(results)
        for stats in summary["conditions"].values():
            for metric in ("task_success_rate", "final_goal_completion", "tool_usage_correctness", "decision_consistency",
                           "token_reduction", "end_to_end_token_reduction"):
                stats[metric] = None
        save_json(output / "summary.json", summary)
        provenance["status"] = "aborted_api_error"
    except BaseException:
        provenance["status"] = "interrupted"
        raise
    finally:
        provenance["finished_at"] = datetime.now(timezone.utc).isoformat()
        provenance["saved_runs"] = len(results)
        save_json(output / "manifest.json", provenance)
    return summary
