"""Read-only replay, input-boundary verification and accounting for cycle3."""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.evidence_interface import EvidenceEnvironment
from evaluation.longitudinal import repeated_attempts
from evaluation.staged import ledger_totals
from state.v03 import compact, validate_state, state_delta
from utils.io import digest, load_json, save_json, parse_json


def audit(run):
    manifest, config, dataset, rows, ledger = [load_json(run / name) for name in
        ("manifest.json", "config.json", "inputs.json", "results.json", "call_ledger.json")]
    checked_state = validate_state
    if config["state_schema"] == "v0.3-minimal-2":
        from state.v03r2 import validate_state as checked_state
    for filename, key in (("config.json", "config_sha256"), ("inputs.json", "input_sha256"), ("plan.json", "plan_sha256")):
        assert digest(run / filename) == manifest[key]
    for relative, sha in manifest["source_code_sha256"].items():
        assert digest(run / "source" / relative) == sha
        assert digest(ROOT / relative) == sha, "Replay implementation differs from frozen code"
    for relative, sha in manifest["cycle_protocol_sha256"].items():
        assert digest(run / "protocol" / relative) == sha
    for name, sha in manifest["prompt_sha256"].items():
        assert digest(run / "prompts" / f"{name}.txt") == sha
    complete = manifest["status"] in {"completed", "completed_with_errors"} and len(rows) == manifest["assigned_cells"]
    scenarios = {s["scenario_id"]: s for s in dataset.get("scenarios", [])}
    cases = {c["instance_id"]: c for c in dataset.get("cases", [])}
    if scenarios:
        expected = {(s, cond, 0, h) for s in scenarios for cond in config["conditions"] for h in range(1, 5)}
    else:
        expected = {(s, cond, r, 1) for s in cases for cond in config["conditions"] for r in range(config["repetitions"])}
    identities = {(r["instance_id"], r["condition"], r["repetition"], r["handoff"]) for r in rows}
    assert len(identities) == len(rows) and identities <= expected
    if complete:
        assert identities == expected
    retained, worlds, stopped = {}, {}, set()
    request_indices, diagnostics, per_row_usage = [], [], {}
    for row in rows:
        a = load_json(run / row["artifact"])
        assert a["result"] == row
        ident, cond, h = row["instance_id"], row["condition"], row["handoff"]
        key = (ident, cond)
        if scenarios:
            s = scenarios[ident]; stage = s["handoffs"][h - 1]
            if key not in worlds:
                assert h == 1
                worlds[key] = deepcopy(s["initial_state"])
                retained[key] = [deepcopy(s["public_goal"])]
            worlds[key].update(deepcopy(stage["external_state_patch"]))
            fixture = deepcopy(stage["environment"]); fixture["initial_state"] = deepcopy(worlds[key])
            history = deepcopy(retained[key]) + deepcopy(stage["public_events"])
            assert (row["status"] == "skipped_chain_error") == (key in stopped)
        else:
            fixture = deepcopy(cases[ident]["environment"])
            history = deepcopy(cases[ident]["history"])
        assert a["environment"] == fixture
        env = EvidenceEnvironment(fixture)
        interface = env.public_interface(f"{ident}:checkpoint_{h}")
        assert interface == a["public_interface"]
        available = history + [{"id": f"runtime_{h}", "role": "runtime", "content": compact({
            "remaining_credits": interface["remaining_credits"], "credit_scope": interface["credit_scope"]})},
            {"id": f"interface_{h}", "role": "tool", "content": "The current public_interface supplies the authoritative catalog, operation contracts and receipt semantics for this checkpoint; its preconditions are definitions, not evidence that any action occurred."}]
        if config["state_schema"] == "v0.3-minimal-2":
            # Match the frozen runner's insertion order for exact JSON bytes.
            event = available[-1]
            available[-1] = {"id": event["id"], "role": event["role"],
                             "source_type": "public_tool_contract", "content": event["content"]}
        assert a["history"] == (None if row["status"] == "skipped_chain_error" else available)
        selected = ledger[row["request_start"]:row["request_end"]]
        request_indices.extend(range(row["request_start"], row["request_end"]))
        responses = [r for r in selected if r["status"] == "response"]
        assert len(responses) == len(a["calls"])
        for call, attempt in zip(a["calls"], responses):
            assert all(call[k] == attempt[k] for k in ("messages", "response", "metadata"))
        extractor_calls = [c for c in a["calls"] if c["metadata"]["purpose"] != "executor"]
        executor_calls = [c for c in a["calls"] if c["metadata"]["purpose"] == "executor"]
        for i, call in enumerate(extractor_calls):
            assert call["messages"][0]["content"] == (run / "prompts" / f"{cond}.txt").read_text(encoding="utf-8")
            payload = parse_json(call["messages"][1]["content"])
            assert payload == {"history": available, "public_interface": interface, "representation_budget": config["representation_budget"], "budget_counter": "utf8_bytes"}
            assert len(call["messages"]) == 2 + 2 * i
            if i:
                assert call["messages"][2]["content"] == extractor_calls[0]["response"]
                assert call["messages"][3]["role"] == "user"
        assert len(extractor_calls) <= 2
        if cond == "full_context" and a["representation"] is not None:
            assert a["representation"] == compact(available)
        if cond == "cs_v03" and a["representation"] is not None:
            current = checked_state(parse_json(a["representation"]), available, interface)
            previous = next((parse_json(e["content"]) for e in history if e.get("retained_schema") == "v0.3"), None)
            assert a["update_delta"] == state_delta(previous, current)
        if executor_calls:
            first = executor_calls[0]["messages"]
            assert first[0]["content"] == (run / "prompts/executor.txt").read_text(encoding="utf-8")
            payload = parse_json(first[1]["content"])
            assert set(payload) == {"instruction", "context", "tools"}
            assert parse_json(payload["context"]) == {"retained_context": a["representation"], "public_interface": interface}
            assert payload["tools"] == env.tool_spec
        for trace in a["trace"]:
            env.apply(trace["action"])
            assert env.trace[-1] == trace
        assert env.settings == a["final_settings"]
        executed = bool(executor_calls)
        assert executed == row["executed"]
        assert row["metrics"] == (env.evaluate() if executed else None)
        assert row["success"] == (row["status"] == "completed" and env.evaluate()["task_success"])
        assert row["repeat_attempts"] == (repeated_attempts(env) if executed else None)
        if scenarios:
            worlds[key] = deepcopy(env.settings)
            if row["status"] in {"representation_error", "executor_error", "skipped_chain_error"}:
                stopped.add(key)
            elif row["status"] != "api_error":
                events = []
                for i, t in enumerate(env.trace):
                    events += [{"id": f"h{h}_a{i}", "role": "assistant", "content": compact(t["action"])},
                               {"id": f"h{h}_o{i}", "role": "tool", "content": compact(t["observation"])}]
                retained[key] = history + events if cond == "full_context" else [{
                    "id": f"retained_h{h}", "role": "assistant", "content": a["representation"],
                    "retained_schema": "v0.3" if cond == "cs_v03" else cond}] + events
        usage = ledger_totals(selected)
        metas = [r["metadata"] for r in responses]
        usage["input_tokens"] = sum(m["input_tokens"] for m in metas)
        usage["output_tokens"] = sum(m["output_tokens"] for m in metas)
        cached_values = [m.get("usage_details", {}).get("prompt_tokens_details", {}).get("cached_tokens") for m in metas]
        usage["cached_input_tokens"] = sum(cached_values) if all(type(v) is int for v in cached_values) else None
        usage["latency_seconds"] = sum(m["latency_seconds"] for m in metas)
        per_row_usage[row["artifact"]] = usage
        diagnostics.append({**row, "usage": usage, "actions": [t["action"] for t in env.trace],
            "artifact_sha256": digest(run / row["artifact"])})
    assert sorted(request_indices) == list(range(len(ledger)))
    ids = []
    for attempt in ledger:
        if attempt["status"] != "response": continue
        m = attempt["metadata"]
        assert m["source"] == "api" and m["transport"] == "openai_sdk" and m["model"] == config["model"]
        assert m["input_tokens"] + m["output_tokens"] == m["usage_details"]["total_tokens"]
        ids.append(m["response_id"])
    assert all(ids) and len(ids) == len(set(ids))
    groups = {}
    for condition in config["conditions"]:
        selected = [d for d in diagnostics if d["condition"] == condition]
        groups[condition] = {}
        for scope in ("all", "main", "controls"):
            ds = [d for d in selected if scope == "all" or d["control"] == (scope == "controls")]
            observed = [d for d in ds if d["executed"]]
            groups[condition][scope] = {"assigned": len(ds), "successes": sum(d["success"] for d in ds) if complete else None,
                "executed": len(observed), "representation_errors": sum(d["status"] == "representation_error" for d in ds),
                "skipped": sum(d["status"] == "skipped_chain_error" for d in ds),
                "first_valid": sum(bool(d["extraction_attempts"]) and d["extraction_attempts"][0]["valid"] for d in ds),
                "repair_calls": sum(max(0, len(d["extraction_attempts"]) - 1) for d in ds),
                "tokens": sum(d["usage"]["known_reported_tokens"] for d in ds),
                "tokens_scope": "reported known tokens, not complete cost if a request usage is unknown",
                "input_tokens": sum(d["usage"]["input_tokens"] for d in ds), "output_tokens": sum(d["usage"]["output_tokens"] for d in ds),
                "cached_input_tokens": sum(d["usage"]["cached_input_tokens"] for d in ds) if all(d["usage"]["cached_input_tokens"] is not None for d in ds) else None,
                "latency_seconds": sum(d["usage"]["latency_seconds"] for d in ds),
                "repeated_attempts": sum(d["repeat_attempts"] for d in observed)}
    chains = []
    if scenarios:
        for ident in scenarios:
            for condition in config["conditions"]:
                ds = [d for d in diagnostics if d["instance_id"] == ident and d["condition"] == condition]
                chains.append({"scenario": ident, "condition": condition, "success": all(d["success"] for d in ds) if complete and len(ds) == 4 else None,
                               "comparable": len(ds) == 4 and all(d["status"] == "completed" for d in ds),
                               "tokens": sum(d["usage"]["known_reported_tokens"] for d in ds)})
        full = {c["scenario"]: c for c in chains if c["condition"] == "full_context"}
        for c in chains:
            b = full[c["scenario"]]
            c["token_reduction"] = 1 - c["tokens"] / b["tokens"] if complete and c["comparable"] and b["comparable"] and b["tokens"] else None
    return {"stage": config["stage"], "complete": complete, "source_run": str(run.resolve()),
            "source_manifest_sha256": digest(run / "manifest.json"), "results_sha256": digest(run / "results.json"),
            "verification": {"snapshot_hashes": True, "actual_public_inputs": True, "retained_history_boundary": True,
                "actual_world_carry": True, "trace_and_score_replay": True, "every_request_accounted_once": True,
                "unique_response_ids": len(ids), "model_calls_by_audit": 0},
            "actual_usage": ledger_totals(ledger), "conditions": groups, "chains": chains, "diagnostics": diagnostics,
            "limitations": ["Small synthetic exploratory study; regression tasks were previously inspected.",
                            "V0.3 is a bundle of schema, instructions, validation and repair; not an individual mechanism ablation.",
                            "Common public contracts changed for every condition; old scores are not a matched baseline.",
                            "Bytes are not model tokens; costs include all calls and do not imply currency savings."]}


def report(a):
    lines = [f"# 第三轮：{a['stage']} 结果", "", f"完整运行：{a['complete']}。冻结输入、源文件、模型输入、轨迹、评分及实际调用账本复核通过。", "",
        "| 条件 | 范围 | 成功/分配 | 实际执行 | 表示失败 | 修复调用 | 总 Tokens（已报告） |", "|---|---|---:|---:|---:|---:|---:|"]
    for condition, scopes in a["conditions"].items():
        for scope in ("main", "controls"):
            s = scopes[scope]
            if not s["assigned"]: continue
            lines.append(f"| {condition} | {scope} | {s['successes']}/{s['assigned']} | {s['executed']} | {s['representation_errors']} | {s['repair_calls']} | {s['tokens']:,} |")
    if a["chains"]:
        lines += ["", "| 场景 | 条件 | 完整链成功 | 总 Tokens | 对 Full 降幅 |", "|---|---|---|---:|---:|"]
        for c in a["chains"]:
            reduction = f"{c['token_reduction']:.1%}" if c["token_reduction"] is not None else "不适用"
            lines.append(f"| {c['scenario']} | {c['condition']} | {c['success']} | {c['tokens']} | {reduction} |")
    u = a["actual_usage"]
    lines += ["", f"实际响应 {u['successful_responses']} 次，总 Tokens {u['total_tokens']}，未知用量请求 {u['unknown_usage_attempts']}。", "",
              "首次有效率、缓存输入、输出和延迟见 analysis.json；错误/跳过保留在分母中，低成本失败不代表效率优势。", ""]
    lines += ["- " + item for item in a["limitations"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    analysis = audit(args.run.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    save_json(args.output / "analysis.json", analysis)
    (args.output / "analysis.md").write_text(report(analysis), encoding="utf-8")
    print(compact({"verified": analysis["verification"], "usage": analysis["actual_usage"]}))
