"""Frozen single-checkpoint history diagnostics and source-first mechanism runs.

This module is outside src so the previous cycle4 asset set remains unchanged.
"""

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import random
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from agents.agent import AgentExecutor
from evaluation.lifecycle import LifecycleEnvironment
from evaluation.staged import ledger_totals
from llm.client import OpenAISDKClient
from llm.environment import load_project_env
from state.v031 import compact
from utils.io import digest, load_json, parse_json, save_json

RELEASE = ROOT / "docs/freezes/cycle5_execution_v1.json"
CONDITIONS = ["full_context", "full_planner", "summary_s1", "summary_s2", "cs1", "cs_text"]
DIMENSIONS = ["entity_phase_confusion", "unsupported_completion", "invented_requirement",
              "missing_pending_job", "unsupported_reopened_question", "missing_decision_dependency"]


class StopRun(RuntimeError):
    pass


class RecordingClient:
    def __init__(self, client, config, persist=None, real=True):
        self.client, self.config, self.persist, self.real = client, config, persist, real
        self.attempts, self.owner = [], {}

    def complete(self, messages, *, purpose, max_output_tokens=None):
        limit = max_output_tokens or self.config["max_output_tokens"]
        if len(self.attempts) >= self.config["max_api_calls"]:
            raise StopRun("request_cap")
        if ledger_totals(self.attempts)["known_reported_tokens"] >= self.config["token_stop_threshold"]:
            raise StopRun("token_threshold")
        attempt = {"request_index": len(self.attempts), **deepcopy(self.owner), "purpose": purpose,
                   "messages": deepcopy(messages), "status": "pending",
                   "request_settings": {"model": self.config["model"], "temperature": self.config["temperature"],
                       "max_output_tokens": limit, "extra_body": deepcopy(self.config["extra_body"])}}
        self.attempts.append(attempt)
        if self.persist:
            self.persist()
        try:
            # The SDK reads this recorded output limit at the moment of the call.
            previous = self.client.config["max_output_tokens"] if hasattr(self.client, "config") else None
            if previous is not None:
                self.client.config["max_output_tokens"] = limit
            try:
                completion = self.client.complete(messages, purpose=purpose)
            finally:
                if previous is not None:
                    self.client.config["max_output_tokens"] = previous
        except Exception as exc:
            # Never persist provider bodies or arbitrary exception strings.
            message = str(exc) if isinstance(exc, RuntimeError) else ""
            category = next((c for c in ("insufficient_balance", "quota_exhausted", "payment_required")
                             if "category=" + c in message), "provider_request_failed")
            match = re.search(r"HTTP=(\d{3})", message)
            attempt.update(status="api_error", error={"type": type(exc).__name__, "category": category,
                "http_status": int(match.group(1)) if match else None},
                metadata={"input_tokens": None, "output_tokens": None})
            if self.persist:
                self.persist()
            raise StopRun("api_error") from None
        attempt.update(status="response", response=completion.text, metadata=completion.metadata)
        if self.persist:
            self.persist()
        if any(type(completion.metadata.get(k)) is not int or completion.metadata[k] < 0
               for k in ("input_tokens", "output_tokens")):
            raise StopRun("unknown_usage")
        if self.real and (completion.metadata.get("source") != "api" or
                completion.metadata.get("transport") != "openai_sdk" or
                completion.metadata.get("model") != self.config["model"] or
                not isinstance(completion.metadata.get("response_id"),str) or not completion.metadata["response_id"]):
            raise StopRun("provider_metadata_mismatch")
        return completion


def verify_release():
    from evaluation.cycle4 import dependencies, verify_release as verify_cycle4
    verify_cycle4()
    release = load_json(RELEASE)
    assert release["status"] == "frozen_before_model_calls"
    assert release["dependencies"] == dependencies()
    assert not sys.flags.optimize
    for path, sha in release["sha256"].items():
        assert digest(ROOT / path) == sha, path
    return release


def projection(task, include_history=True):
    from experiments.exp004_mechanism.conditions import project_inputs
    allowed = {"id", "role", "content", "source_type", "source_authority", "retained_schema"}
    events = (task["historical_context"] if include_history else []) + task["current_public_events"]
    assert events and all(set(e) <= allowed for e in events)
    assert len({e["id"] for e in events}) == len(events)
    return project_inputs(deepcopy(events), deepcopy(task["public_interface"]))


def public_context(representation, interface):
    # Identical string transport for JSON, prose and lossless path text.
    return compact({"retained_context": representation, "public_interface": interface})


def selected_tasks(config):
    public = load_json(ROOT / config["dataset_public"])
    private = load_json(ROOT / config["dataset_private"])
    tasks = {t["task_id"]: t for t in public["tasks"]}
    fixtures = {t["task_id"]: t for t in private["tasks"]}
    ids = config["task_ids"]
    assert len(ids) == len(set(ids)) and set(ids) <= set(tasks) and set(ids) <= set(fixtures)
    return tasks, fixtures


def initial_run(config, output, real):
    release = verify_release()
    assert config == load_json(ROOT / config["config_path"])
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "config.json", config)
    save_json(output / "execution_release.json", release)
    for relative in release["sha256"]:
        target = output / "snapshot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    manifest = {"experiment_id": config["experiment_id"], "stage": config["stage"],
        "evidence_type": "api" if real else "mock_protocol_validation", "status": "created",
        "started_at": datetime.now(timezone.utc).isoformat(), "assigned_cells": len(config["task_ids"]) * len(config["conditions"]),
        "execution_release_sha256": digest(RELEASE), "config_sha256": digest(output / "config.json")}
    save_json(output / "manifest.json", manifest)
    return manifest


def executor_run(rep, interface, fixture, client, prompt, config):
    env = LifecycleEnvironment(deepcopy(fixture))
    assert env.public_interface(interface["credit_scope"]) == interface
    calls = []
    error = None
    try:
        AgentExecutor(client, prompt, config["max_steps"]).run(public_context(rep, interface), env, calls)
    except StopRun as exc:
        exc.partial = {"representation": rep, "public_interface": interface, "calls": calls,
                       "trace": env.trace, "final_world": env.settings, "metrics": env.evaluate()}
        raise
    except ValueError:
        error = "executor_format_error"
    return env, calls, error


def diagnostic(config_path, output, client=None):
    from experiments.exp004_mechanism.conditions import load_prompt
    config = load_json(config_path)
    real = client is None
    manifest = initial_run(config, output, real)
    tasks, fixtures = selected_tasks(config)
    prompt = load_prompt("executor")
    rows, ledger = [], None
    schedule = [{"task_id": t, "condition": c} for t in config["task_ids"] for c in config["conditions"]]
    random.Random(config["seed"]).shuffle(schedule)
    save_json(output / "schedule.json", schedule)

    def flush():
        save_json(output / "manifest.json", manifest)
        save_json(output / "results.json", rows)
        save_json(output / "call_ledger.json", ledger.attempts if ledger else [])

    manifest["status"] = "running"
    flush()
    if real:
        load_project_env(ROOT)
        client = OpenAISDKClient(deepcopy(config))
    ledger = RecordingClient(client, config, flush, real)
    try:
        for slot in schedule:
            verify_release()
            task = tasks[slot["task_id"]]
            history, interface = projection(task, slot["condition"] == "full_context")
            rep, start = compact(history), len(ledger.attempts)
            ledger.owner = deepcopy(slot)
            env, calls, error = executor_run(rep, interface, fixtures[task["task_id"]]["environment"], ledger, prompt, config)
            artifact = f"instances/{task['task_id']}_{slot['condition']}.json"
            row = {**slot, "family": task["family"], "pair_id": task.get("pair_id"), "variant": task.get("variant"),
                "request_indices": list(range(start, len(ledger.attempts))), "artifact": artifact,
                "success": env.evaluate()["task_success"], "metrics": env.evaluate(),
                "status": error or ("completed" if env.finished else "step_limit"), "representation_valid": None}
            save_json(output / artifact, {"row": row, "history": history, "public_interface": interface,
                "representation": rep, "calls": calls, "trace": env.trace, "final_world": env.settings})
            rows.append(row)
            flush()
        manifest["status"] = "completed"
    except StopRun as exc:
        manifest["status"] = "aborted_" + str(exc)
        if hasattr(exc, "partial"):
            save_json(output / "interrupted_cell.json", {**slot, "partial": exc.partial})
    except (Exception, KeyboardInterrupt) as exc:
        manifest["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "aborted_integrity_error"
        manifest["failure_type"] = type(exc).__name__
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        flush()


def prepare_run(config_path, output, client=None):
    from experiments.exp004_mechanism.conditions import prepare
    config = load_json(config_path)
    real = client is None
    if real:
        gate = load_json(ROOT / config["incoming_diagnostic_gate"])
        assert gate["status"] == "passed" and gate["execution_release_sha256"] == digest(RELEASE)
        fresh = audit_run(Path(gate["source_run"]))
        assert fresh == gate["audit"] and fresh["complete"] and fresh["evidence_type"] == "api"
        assert fresh["usage"]["unknown_usage_attempts"] == 0
    manifest = initial_run(config, output, real)
    tasks, _ = selected_tasks(config)
    prepared, ledger = [], None
    task_order = list(config["task_ids"])
    random.Random(config["seed"]).shuffle(task_order)
    save_json(output / "task_order.json", task_order)
    schedule = [{"task_id": t, "condition": c} for t in task_order for c in CONDITIONS]
    random.Random(config["seed"] + 1).shuffle(schedule)
    save_json(output / "executor_schedule.json", schedule)

    def flush():
        save_json(output / "manifest.json", manifest)
        save_json(output / "prepared.json", prepared)
        save_json(output / "call_ledger.json", ledger.attempts if ledger else [])

    manifest["status"] = "preparing"
    flush()
    if real:
        load_project_env(ROOT)
        client = OpenAISDKClient(deepcopy(config))
    ledger = RecordingClient(client, config, flush, real)
    try:
        for ident in task_order:
            history, interface = projection(tasks[ident])
            shared, shared_indices = None, []
            for condition in CONDITIONS:
                verify_release()
                ledger.owner = {"task_id": ident, "condition": condition, "phase": "prepare"}
                start = len(ledger.attempts)
                result = prepare(condition, history, interface, config, ledger, shared_state=shared)
                own = list(range(start, len(ledger.attempts)))
                if condition == "cs1":
                    shared, shared_indices = result, own
                item = {"task_id": ident, "condition": condition, "preparation": asdict(result),
                    "source_request_indices": shared_indices if condition == "cs_text" else own,
                    "actual_prepare_request_indices": own,
                    "history": history, "public_interface": interface}
                prepared.append(item)
                flush()
        manifest["status"] = "prepared"
        manifest["prepared_sha256"] = digest(output / "prepared.json")
    except StopRun as exc:
        manifest["status"] = "aborted_" + str(exc)
    except (Exception, KeyboardInterrupt) as exc:
        manifest["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "aborted_integrity_error"
        manifest["failure_type"] = type(exc).__name__
        raise
    finally:
        flush()


def source_packet(output):
    prepared = load_json(output / "prepared.json")
    entries = []
    for p in prepared:
        if p["condition"] not in {"full_planner", "summary_s1", "summary_s2", "cs1"}:
            continue
        scopes = ["planner"] if p["condition"] == "full_planner" else ["final"]
        if p["condition"] == "summary_s2":
            scopes.insert(0, "organizer")
        for scope in scopes:
            rep = p["preparation"]["representation"] if scope == "final" else p["preparation"]["intermediate"]
            entries.append({"task_id":p["task_id"],"condition":p["condition"],"review_scope":scope,
                "history":p["history"],"public_interface":p["public_interface"],"representation":rep,
                "valid":p["preparation"]["valid"] if scope == "final" else bool(rep),
                "assessment":{d:None for d in DIMENSIONS},"evidence_notes":""})
    return {"source_run": str(output.resolve()), "prepared_sha256": digest(output / "prepared.json"),
        "review_method": "public_sources_before_current_behavior;assistant_not_independent_gold;condition_not_blinded",
        "reviewer": "", "entries": entries}


def validate_review(output, review):
    expected = source_packet(output)
    assert review["source_run"] == expected["source_run"]
    assert review["prepared_sha256"] == expected["prepared_sha256"]
    assert review["review_method"] == expected["review_method"] and review["reviewer"].strip()
    assert len(review["entries"]) == len(expected["entries"])
    for entry, original in zip(review["entries"], expected["entries"]):
        for key in original.keys() - {"assessment", "evidence_notes"}:
            assert entry[key] == original[key]
        assert set(entry["assessment"]) == set(DIMENSIONS)
        assert all(v in {"correct", "incorrect", "ambiguous", "not_observed"} for v in entry["assessment"].values())
        assert entry["evidence_notes"].strip()
        if not entry["valid"]:
            assert set(entry["assessment"].values()) == {"not_observed"}
    return True


def execute_run(output, review_path, client=None):
    from experiments.exp004_mechanism.conditions import load_prompt
    config, manifest = load_json(output / "config.json"), load_json(output / "manifest.json")
    assert manifest["status"] == "prepared", "Only one transition from prepared to executed is allowed"
    verify_release()
    assert config == load_json(ROOT / config["config_path"])
    assert manifest["prepared_sha256"] == digest(output / "prepared.json")
    validate_review(output, load_json(review_path))
    manifest["source_review_sha256"] = digest(review_path)
    shutil.copyfile(review_path, output / "source_review.json")
    tasks, fixtures = selected_tasks(config)
    prepared = {(p["task_id"], p["condition"]): p for p in load_json(output / "prepared.json")}
    rows, ledger = [], None
    real = client is None
    assert manifest["evidence_type"] == ("api" if real else "mock_protocol_validation")
    prompt = load_prompt("executor")
    prior = load_json(output / "call_ledger.json")

    def flush():
        save_json(output / "manifest.json", manifest)
        save_json(output / "results.json", rows)
        save_json(output / "call_ledger.json", ledger.attempts if ledger else prior)

    manifest["status"] = "executing"
    flush()
    if real:
        load_project_env(ROOT)
        client = OpenAISDKClient(deepcopy(config))
    ledger = RecordingClient(client, config, flush, real)
    ledger.attempts = prior
    try:
        for slot in load_json(output / "executor_schedule.json"):
            verify_release()
            p = prepared[(slot["task_id"], slot["condition"])]
            start = len(ledger.attempts)
            ledger.owner = {**slot, "phase": "execute"}
            calls, error = [], None
            env = LifecycleEnvironment(deepcopy(fixtures[slot["task_id"]]["environment"]))
            if p["preparation"]["valid"]:
                env, calls, error = executor_run(p["preparation"]["representation"], p["public_interface"],
                    fixtures[slot["task_id"]]["environment"], ledger, prompt, config)
            else:
                error = "representation_error"
            indices = p["source_request_indices"] + list(range(start, len(ledger.attempts)))
            assert len(indices) == len(set(indices))
            artifact = f"instances/{slot['task_id']}_{slot['condition']}.json"
            row = {**slot, "family": tasks[slot["task_id"]]["family"], "pair_id": tasks[slot["task_id"]].get("pair_id"),
                "variant": tasks[slot["task_id"]].get("variant"), "artifact": artifact,
                "status": error or ("completed" if env.finished else "step_limit"),
                "success": env.evaluate()["task_success"] and error is None, "metrics": env.evaluate(),
                "representation_valid": p["preparation"]["valid"], "diagnostics": p["preparation"]["diagnostics"],
                "source_request_indices": p["source_request_indices"],
                "executor_request_indices": list(range(start, len(ledger.attempts))), "request_indices": indices,
                "deployment_usage": ledger_totals([ledger.attempts[i] for i in indices])}
            save_json(output / artifact, {"row": row, "representation": p["preparation"]["representation"],
                "public_interface": p["public_interface"], "calls": calls, "trace": env.trace, "final_world": env.settings})
            rows.append(row)
            flush()
        manifest["status"] = "completed"
    except StopRun as exc:
        manifest["status"] = "aborted_" + str(exc)
        if hasattr(exc, "partial"):
            save_json(output / "interrupted_cell.json", {**slot, "partial": exc.partial})
    except (Exception, KeyboardInterrupt) as exc:
        manifest["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "aborted_integrity_error"
        manifest["failure_type"] = type(exc).__name__
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        flush()


def audit_run(output):
    from experiments.exp004_mechanism.conditions import load_prompt,prepare
    from llm.client import Completion
    config, manifest = load_json(output / "config.json"), load_json(output / "manifest.json")
    tasks, fixtures = selected_tasks(config)
    ledger, rows = load_json(output / "call_ledger.json"), load_json(output / "results.json")
    assert config == load_json(ROOT / config["config_path"])
    assert digest(output / "config.json") == manifest["config_sha256"]
    release=load_json(RELEASE)
    assert load_json(output / "execution_release.json")==release
    for path,sha in release["sha256"].items():
        assert digest(output / "snapshot" / path)==sha
    complete = manifest["status"] == "completed" and len(rows) == manifest["assigned_cells"]
    assert manifest["execution_release_sha256"] == digest(RELEASE)
    schedule = load_json(output / ("executor_schedule.json" if config["stage"] == "mechanism" else "schedule.json"))
    assert len(schedule) == manifest["assigned_cells"]
    assert {(s["task_id"],s["condition"]) for s in schedule} == {(t,c) for t in config["task_ids"] for c in config["conditions"]}
    assert len({(s["task_id"],s["condition"]) for s in schedule}) == len(schedule)
    assert [{k:r[k] for k in ("task_id","condition")} for r in rows] == schedule[:len(rows)]
    for i, attempt in enumerate(ledger):
        assert attempt["request_index"] == i
        settings=attempt["request_settings"]
        assert settings["model"]==config["model"] and settings["temperature"]==config["temperature"]
        assert settings["extra_body"]==config["extra_body"]
        assert settings["max_output_tokens"]==(config["intermediate_max_output_tokens"]
            if attempt["purpose"].endswith((":planner",":organizer")) else config["max_output_tokens"])
    requests = [a["metadata"].get("response_id") for a in ledger if a["status"] == "response"]
    assert all(isinstance(r,str) and r for r in requests)
    assert len(requests) == len(set(requests))
    prepared_list=load_json(output / "prepared.json") if (output / "prepared.json").exists() else None
    prepared = {(p["task_id"], p["condition"]): p for p in prepared_list} if prepared_list else None
    if prepared:
        assert len(prepared_list)==len(prepared)==len(config["task_ids"])*len(CONDITIONS)
    covered = set()

    def match_calls(calls, indices, owner, phase=None):
        assert len(calls) == len(indices) and len(indices) == len(set(indices))
        for call,i in zip(calls,indices):
            request=ledger[i]
            assert request["status"] == "response"
            assert all(request[k]==v for k,v in owner.items())
            assert request.get("phase")==phase
            assert request["purpose"]==call["metadata"]["purpose"]
            for key in ("messages","response","metadata"):
                assert call[key] == request[key]
            if "max_output_tokens" in call:
                assert call["max_output_tokens"] == request["request_settings"]["max_output_tokens"]
            covered.add(i)

    if prepared:
        validate_review(output, load_json(output / "source_review.json"))
        assert digest(output / "source_review.json") == manifest["source_review_sha256"]
        assert manifest["prepared_sha256"] == digest(output / "prepared.json")
        assert len(prepared) == len(config["task_ids"])*len(CONDITIONS)

        class Replay:
            def __init__(self,calls): self.calls,self.index=calls,0
            def complete(self,messages,*,purpose,max_output_tokens):
                call=self.calls[self.index];self.index+=1
                assert messages==call["messages"] and purpose==call["metadata"]["purpose"]
                assert max_output_tokens==call["max_output_tokens"]
                return Completion(call["response"],deepcopy(call["metadata"]))

        for ident in config["task_ids"]:
            shared,shared_indices=None,[]
            history,interface=projection(tasks[ident])
            for condition in CONDITIONS:
                p=prepared[(ident,condition)]
                assert p["history"]==history and p["public_interface"]==interface
                replay=Replay(p["preparation"]["calls"])
                reconstructed=prepare(condition,history,interface,config,replay,shared_state=shared)
                assert asdict(reconstructed)==p["preparation"] and replay.index==len(replay.calls)
                match_calls(replay.calls,p["actual_prepare_request_indices"],{"task_id":ident,"condition":condition},"prepare")
                if condition=="cs1":
                    shared,shared_indices=reconstructed,p["actual_prepare_request_indices"]
                assert p["source_request_indices"]==(shared_indices if condition=="cs_text" else p["actual_prepare_request_indices"])
    for row in rows:
        artifact = load_json(output / row["artifact"])
        assert artifact["row"] == row
        env = LifecycleEnvironment(deepcopy(fixtures[row["task_id"]]["environment"]))
        for trace in artifact["trace"]:
            env.apply(trace["action"])
            assert env.trace[-1] == trace
        assert env.settings == artifact["final_world"] and env.evaluate() == row["metrics"]
        assert row["success"] == (env.evaluate()["task_success"] and row["status"] not in {"representation_error","executor_format_error"})
        if prepared:
            p = prepared[(row["task_id"], row["condition"])]
            assert artifact["representation"] == p["preparation"]["representation"]
            assert row["request_indices"] == p["source_request_indices"] + row["executor_request_indices"]
            assert row["deployment_usage"] == ledger_totals([ledger[i] for i in row["request_indices"]])
            match_calls(artifact["calls"],row["executor_request_indices"],{"task_id":row["task_id"],"condition":row["condition"]},"execute")
        else:
            history, interface = projection(tasks[row["task_id"]], row["condition"] == "full_context")
            assert artifact["representation"] == compact(history) and artifact["history"] == history
            match_calls(artifact["calls"],row["request_indices"],{"task_id":row["task_id"],"condition":row["condition"]})
        assert artifact["public_interface"] == tasks[row["task_id"]]["public_interface"]
        # Reconstruct every full executor message, including paid failed outcomes.
        expected = [{"role": "system", "content": load_prompt("executor")},
            {"role": "user", "content": json.dumps({"instruction": "Resume the interrupted task using the supplied context.",
             "context": public_context(artifact["representation"],artifact["public_interface"]),
             "tools": env.tool_spec},ensure_ascii=False)}]
        for call, trace in zip(artifact["calls"], artifact["trace"]):
            assert call["messages"] == expected
            assert call["metadata"]["finish_reason"] == "stop"
            try:
                parsed = parse_json(call["response"])
            except (ValueError, TypeError):
                parsed = {"invalid_output": call["response"]}
            assert parsed == trace["action"]
            expected += [{"role":"assistant","content":call["response"]},
                {"role":"user","content":json.dumps({"action":trace["action"],"observation":trace["observation"]},ensure_ascii=False)}]
        if len(artifact["calls"]) != len(artifact["trace"]):
            assert row["status"] == "executor_format_error"
            assert len(artifact["calls"]) == len(artifact["trace"]) + 1
            assert artifact["calls"][-1]["metadata"]["finish_reason"] != "stop"
    if complete:
        assert covered==set(range(len(ledger)))
        assert ledger_totals(ledger)["unknown_usage_attempts"]==0
    return {"complete":complete,"evidence_type":manifest["evidence_type"],"stage":config["stage"],
        "results_sha256":digest(output/"results.json"),"ledger_sha256":digest(output/"call_ledger.json"),
        "usage":ledger_totals(ledger),"verification":"public input, exact executor messages, world/trace/score and cost indices replayed"}
