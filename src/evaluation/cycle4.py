"""Cycle4 execution, public-input reconstruction and release checks."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import importlib.metadata
import importlib.util
import sys
import shutil

from agents.agent import AgentExecutor
from evaluation.lifecycle import LifecycleEnvironment
from evaluation.longitudinal import repeated_attempts
from evaluation.staged import LedgerClient, ledger_totals
from llm.client import OpenAISDKClient
from llm.environment import load_project_env
from state.v031 import ExtractorV031, compact, retained_event, state_delta, validate_state
from utils.io import digest, load_json, save_json, parse_json

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs/cycle4_plan_20261003.json"
PROTOCOL = ROOT / "docs/freezes/cycle4_protocol_v1.json"
RELEASE = ROOT / "docs/freezes/cycle4_execution_v2.json"


def dependencies():
    return {name: importlib.metadata.version(name) for name in ("openai", "python-dotenv", "tiktoken",
        "httpx", "httpcore", "pydantic", "anyio", "jiter", "sniffio", "distro", "typing_extensions")}


def release_paths():
    paths = list((ROOT / "src").rglob("*.py")) + list((ROOT / "datasets/cycle4_v1").glob("*.json")) + list((ROOT / "prompts/cycle4").glob("*.txt"))
    paths += [ROOT / f"configs/cycle4_{s}_v1.json" for s in ("preflight", "regression", "longitudinal")]
    paths += [ROOT / p for p in ("docs/freezes/cycle4_protocol_v1.json", "docs/cycle4_plan_20261003.json",
        "docs/schemas/cognitive_state_v0.3.1.schema.json", "scripts/check_cycle4_protocol.py", "scripts/build_cycle4.py",
        "scripts/run_cycle4.py", "scripts/audit_cycle4.py", "scripts/freeze_cycle4.py", "tests/test_cycle4.py",
        "requirements-cycle4.txt", "docs/freezes/cycle4_offline_validation_v2.json")]
    return sorted(set(paths))


def verify_release(path=RELEASE):
    if sys.flags.optimize:
        raise ValueError("Do not disable assertion-based offline integrity checks with Python -O")
    manifest = load_json(path)
    if manifest.get("status") != "execution_frozen" or manifest.get("protocol_sha256") != digest(PROTOCOL):
        raise ValueError("Execution release is missing or mismatched")
    if set(manifest["sha256"]) != {p.relative_to(ROOT).as_posix() for p in release_paths()}:
        raise ValueError("Execution release does not cover all required assets")
    for relative, sha in manifest["sha256"].items():
        if digest(ROOT / relative) != sha:
            raise ValueError("Execution file changed: " + relative)
    for relative, sha in load_json(PROTOCOL)["sha256"].items():
        if digest(ROOT / relative) != sha:
            raise ValueError("Protocol file changed: " + relative)
    if dependencies() != manifest["dependencies"] or sys.version_info < (3, 10):
        raise ValueError("Dependency environment differs from frozen execution release")
    if load_json(ROOT / "docs/freezes/cycle4_offline_validation_v2.json").get("passed") is not True:
        raise ValueError("Offline validation has not passed")
    return manifest


def validate_config(config):
    stage = config.get("stage")
    if stage not in {"preflight", "regression", "longitudinal"}:
        raise ValueError("Unknown stage")
    if config != load_json(ROOT / f"configs/cycle4_{stage}_v1.json"):
        raise ValueError("Config differs from execution version")
    return load_json(PLAN)


def available_input(history, fixture, ident, handoff):
    env = LifecycleEnvironment(fixture)
    interface = env.public_interface(f"{ident}:checkpoint_{handoff}")
    available = deepcopy(history) + [
        {"id": f"runtime_{handoff}", "role": "runtime", "content": compact({
            "remaining_credits": interface["remaining_credits"], "credit_scope": interface["credit_scope"]})},
        {"id": f"interface_{handoff}", "role": "tool", "source_type": "public_tool_contract", "content":
            "The current public_interface provides authoritative operation contracts and prices, not evidence of past execution."}]
    return env, available, interface


def next_memory(history, available, env, rep, condition, handoff):
    events = []
    for i, trace in enumerate(env.trace):
        events += [{"id": f"h{handoff}_a{i}", "role": "assistant", "content": compact(trace["action"])},
                   {"id": f"h{handoff}_o{i}", "role": "tool", "content": compact(trace["observation"])}]
    return (history if condition == "full_context" else [retained_event(rep, condition, available, handoff)]) + events


def executor_context(rep, condition, interface):
    return {"retained_context": rep if condition == "summary" else parse_json(rep), "public_interface": interface}


def execution_status(env):
    if env.finished:
        return "completed"
    # Preconditions and budget exhaustion are well-formed behavioral failures.
    # Only malformed/unknown tool calls make an exhausted chain a format error.
    malformed = any(t["observation"].get("error") == "Invalid tool or arguments" for t in env.trace)
    return "executor_error" if malformed else "step_limit"


class RecordingClient(LedgerClient):
    def __init__(self, client, maximum, real):
        super().__init__(client, maximum)
        self.real = real

    def complete(self, messages, *, purpose):
        try:
            completion = super().complete(messages, purpose=purpose)
        except Exception as exc:
            if self.attempts and self.attempts[-1]["status"] in {"pending", "api_error"}:
                self.attempts[-1].update({"status": "api_error", "error": {"type": type(exc).__name__},
                                          "metadata": {"input_tokens": None, "output_tokens": None}})
            # Avoid persisting arbitrary provider/transport exception bodies.
            raise RuntimeError("Client request failed; see sanitized ledger status") from None
        m = completion.metadata
        if any(type(m.get(k)) is not int or m[k] < 0 for k in ("input_tokens", "output_tokens")):
            raise RuntimeError("Unknown provider usage; stop current run")
        if self.real and (m.get("source") != "api" or m.get("transport") != "openai_sdk" or
                          m.get("model") != "deepseek-ai/DeepSeek-V4-Flash"):
            raise RuntimeError("Unexpected provider/model metadata")
        return completion


def run(config_path, output, client=None, gate_path=None, progress=None):
    config = load_json(config_path)
    plan = validate_config(config)
    real = client is None
    if real:
        verify_release()
        if config["stage"] != "preflight":
            if gate_path is None:
                raise ValueError("A cycle4 reviewed stage gate is required")
            from evaluation.cycle4_audit import verify_gate
            verify_gate(gate_path, config["stage"])
    data = load_json(ROOT / config["dataset"])
    schedule = load_json(ROOT / config["schedule"])
    prompts = {k: (ROOT / p).read_text(encoding="utf-8") for k, p in config["prompts"].items()}
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "config.json", config)
    save_json(output / "inputs.json", data)
    save_json(output / "schedule.json", schedule)
    save_json(output / "plan.json", plan)
    if gate_path is not None:
        shutil.copyfile(gate_path, output / "incoming_gate.json")
    release_sha = digest(RELEASE) if RELEASE.exists() else None
    if RELEASE.exists():
        shutil.copyfile(RELEASE, output / "execution_release.json")
        for relative in load_json(RELEASE)["sha256"]:
            target = output / "snapshot" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
    for name, text in prompts.items():
        target = output / "prompts" / (name + ".txt")
        target.parent.mkdir(exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    rows, attempts = [], []
    ledger = None
    manifest = {"execution_version": config["execution_version"], "stage": config["stage"],
                "evidence_type": "api" if real else "mock_protocol_validation", "status": "running",
                "assigned_cells": len(schedule), "execution_release_sha256": release_sha,
                "started_at": datetime.now(timezone.utc).isoformat(), "dependencies": dependencies(),
                "python": sys.version, "protocol_sha256": digest(PROTOCOL),
                "config_sha256": digest(output / "config.json"), "inputs_sha256": digest(output / "inputs.json"),
                "schedule_sha256": digest(output / "schedule.json")}
    cases = {c["instance_id"]: c for c in data.get("cases", [])}
    scenarios = {s["scenario_id"]: s for s in data.get("scenarios", [])}
    worlds, memory, stopped = {}, {}, set()

    def flush():
        actual = ledger.attempts if ledger else attempts
        complete = manifest["status"] == "completed" and len(rows) == len(schedule)
        groups = {}
        for cond in config["conditions"]:
            selected = [r for r in rows if r["condition"] == cond]
            groups[cond] = {"assigned": sum(s["condition"] == cond for s in schedule), "saved": len(selected),
                "successes": sum(r["success"] for r in selected) if complete else None,
                "final_valid": sum(r["representation_valid"] is True for r in selected),
                "first_valid": sum(bool(r["extraction_attempts"]) and r["extraction_attempts"][0]["valid"] for r in selected),
                "repair_calls": sum(max(0, len(r["extraction_attempts"]) - 1) for r in selected),
                "usage": ledger_totals([a for r in selected for a in actual[r["request_start"]:r["request_end"]]])}
        for filename, value in (("results.json", rows), ("call_ledger.json", actual), ("manifest.json", manifest),
            ("summary.json", {"complete": complete, "conditions": groups, "usage": ledger_totals(actual),
                              "evidence_type": manifest["evidence_type"], "scientific_conclusion": None})):
            save_json(output / filename, value)

    flush()
    try:
        if real:
            load_project_env(ROOT)
            client = OpenAISDKClient(config)
        ledger = RecordingClient(client, config["max_api_calls"], real)
        for slot in schedule:
            if real:
                verify_release()
            ident, cond, h = slot["instance_id"], slot["condition"], slot["handoff"]
            key = (ident, cond)
            if scenarios:
                scenario = scenarios[ident]; stage = scenario["handoffs"][h - 1]
                if key not in worlds:
                    worlds[key] = deepcopy(scenario["initial_state"])
                    memory[key] = [deepcopy(scenario["public_goal"])]
                worlds[key].update(deepcopy(stage["external_state_patch"]))
                fixture = deepcopy(stage["environment"]); fixture["initial_state"] = deepcopy(worlds[key])
                history = deepcopy(memory[key]) + deepcopy(stage["public_events"])
            else:
                fixture = deepcopy(cases[ident]["environment"])
                history = deepcopy(cases[ident]["history"])
            env, available, interface = available_input(history, fixture, ident, h)
            start = len(ledger.attempts)
            calls, diagnostics, error = [], [], None
            rep = None
            status = "skipped_chain_error" if key in stopped else "completed"
            if status != "skipped_chain_error":
                try:
                    if cond == "full_context":
                        rep = compact(available)
                    else:
                        rep, diagnostics = ExtractorV031(ledger, config["representation_budget"]).extract(available, interface, cond, prompts[cond], calls)
                    if rep is None:
                        status = "representation_error"
                    else:
                        AgentExecutor(ledger, prompts["executor"], config["max_steps"]).run(executor_context(rep, cond, interface), env, calls)
                        status = execution_status(env)
                except RuntimeError as exc:
                    error = {"kind": "api_error", "message": str(exc)}; status = "api_error"
                except (ValueError, TypeError, KeyError) as exc:
                    error = {"kind": "executor_error", "type": type(exc).__name__, "message": str(exc)[:400]}; status = "executor_error"
            executed = any(c["metadata"]["purpose"] == "executor" for c in calls)
            metrics = env.evaluate() if executed else None
            row = {**slot, "control": cases.get(ident, {}).get("control", False), "status": status, "error": error,
                "success": bool(executed and status == "completed" and metrics["task_success"]),
                "representation_valid": None if cond == "full_context" or key in stopped else rep is not None,
                "representation_bytes": len(rep.encode("utf-8")) if rep is not None else None,
                "extraction_attempts": diagnostics, "executed": executed, "metrics": metrics,
                "repeat_attempts": repeated_attempts(env) if executed else None,
                "premature_completed": env.finish_status == "completed" and not all(env.evaluate()["goal_checks"].values()),
                "request_start": start, "request_end": len(ledger.attempts),
                "artifact": f"instances/{ident}_{cond}_r{slot['repetition']}_h{h}.json"}
            old = next((parse_json(e["content"]) for e in history if e.get("retained_schema") == "cs_v031"), None)
            delta = state_delta(old, parse_json(rep)) if cond == "cs_v031" and rep else None
            save_json(output / row["artifact"], {"result": row, "history": available if key not in stopped else None,
                "public_interface": interface, "representation": rep, "calls": calls, "environment": fixture,
                "trace": env.trace, "final_settings": env.settings, "update_delta": delta})
            rows.append(row); flush()
            if progress:
                progress({"saved": len(rows), "assigned": len(schedule), **slot, "status": status, "success": row["success"]})
            if status == "api_error":
                manifest["status"] = "aborted_api_error"; return
            if scenarios:
                worlds[key] = deepcopy(env.settings)
                if status in {"representation_error", "executor_error", "skipped_chain_error"}:
                    stopped.add(key)
                else:
                    memory[key] = next_memory(history, available, env, rep, cond, h)
        manifest["status"] = "completed"
    except BaseException:
        manifest["status"] = "interrupted"; raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat(); flush()
