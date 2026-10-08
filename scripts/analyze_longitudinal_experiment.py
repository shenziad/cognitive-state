"""Read-only replay and descriptive analysis of the four-handoff pilot."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.continuation import ContinuationEnvironment  # noqa: E402
from evaluation.longitudinal import HandoffMemory, LongitudinalEnvironment, handoff_metrics, summarize  # noqa: E402
from evaluation.runner import usage_total  # noqa: E402
from utils.io import digest, load_json, save_json  # noqa: E402


def audit_run(run: Path) -> dict:
    manifest, config, rows = (load_json(run / name) for name in ("manifest.json", "config.json", "results.json"))
    complete = manifest["status"] in {"completed", "completed_with_errors"} and len(rows) == 32
    issues, identities = [], set()
    for relative, sha in manifest["input_sha256"].items():
        if digest(run / "inputs" / relative) != sha:
            issues.append(f"input hash mismatch: {relative}")
    for name, sha in manifest["prompt_sha256"].items():
        if digest(run / "prompts" / f"{name}.txt") != sha:
            issues.append(f"prompt hash mismatch: {name}")
    for relative, sha in manifest["code_sha256"].items():
        if digest(run / "source" / relative) != sha:
            issues.append(f"frozen code hash mismatch: {relative}")
    dataset_manifest = load_json(run / "inputs/manifest.json")
    scenarios = {entry["scenario_id"]: load_json(run / "inputs" / entry["path"])
                 for entry in dataset_manifest["scenarios"]}
    diagnostics, grouped = [], {}
    for row in rows:
        identity = (row["scenario_id"], row["condition"], row["handoff"])
        if identity in identities:
            issues.append(f"duplicate result: {identity}")
        identities.add(identity)
        grouped.setdefault(identity[:2], []).append(row)
    expected = {(scenario_id, condition, handoff) for scenario_id in scenarios
                for condition in config["conditions"] for handoff in range(1, 5)}
    if identities - expected or (complete and identities != expected):
        issues.append("result grid differs from assigned scenario/condition/handoff combinations")
    for (scenario_id, condition), chain in grouped.items():
        scenario = scenarios[scenario_id]
        memory, world = HandoffMemory(condition, scenario["public_goal"]), LongitudinalEnvironment(scenario["initial_state"])
        chain = sorted(chain, key=lambda row: row["handoff"])
        if [row["handoff"] for row in chain] != list(range(1, len(chain) + 1)):
            issues.append(f"nonsequential chain: {scenario_id}/{condition}")
        for row in chain:
            stage = scenario["handoffs"][row["handoff"] - 1]
            artifact = load_json(run / row["artifact"])
            if artifact["result"] != row:
                issues.append(f"artifact row mismatch: {row['artifact']}")
            env = world.open_handoff(stage)
            if env.fixture != artifact["environment_fixture"]:
                issues.append(f"world carry or fixture mismatch: {row['artifact']}")
            skipped = row["status"] == "skipped_chain_error"
            expected_input = None if skipped else memory.update_input(stage["public_events"])
            if artifact["public_update_input"] != expected_input:
                issues.append(f"history retention boundary mismatch: {row['artifact']}")
            calls = artifact["calls"]
            update_calls = [c for c in calls if c["metadata"]["purpose"] != "executor"]
            for call in update_calls:
                payload = json.loads(call["messages"][1]["content"])
                if payload["history"] != expected_input or call["metadata"]["purpose"] != condition:
                    issues.append(f"extractor input mismatch: {row['artifact']}")
            executor_calls = [c for c in calls if c["metadata"]["purpose"] == "executor"]
            if executor_calls:
                payload = json.loads(executor_calls[0]["messages"][1]["content"])
                if set(payload) != {"instruction", "context", "tools"} or payload["context"] != artifact["representation"]:
                    issues.append(f"executor context mismatch: {row['artifact']}")
            for trace in artifact["trace"]:
                observation = env.apply(trace["action"])
                if observation != trace["observation"] or env.trace[-1] != trace:
                    issues.append(f"trace replay mismatch: {row['artifact']}")
            if env.settings != artifact["final_settings"]:
                issues.append(f"final state mismatch: {row['artifact']}")
            if row["execution_started"] != bool(executor_calls):
                issues.append(f"execution-started flag mismatch: {row['artifact']}")
            measured = handoff_metrics(env, bool(executor_calls), row["error"], skipped)
            if measured != row["metrics"]:
                issues.append(f"score replay mismatch: {row['artifact']}")
            is_api_error = row["error"] and row["error"]["type"] in {"RuntimeError", "OSError"}
            if not is_api_error and usage_total(calls) != row["token_usage"]["total_tokens"]:
                issues.append(f"usage mismatch: {row['artifact']}")
            if usage_total(calls) != row["token_usage"]["reported_total_tokens"]:
                issues.append(f"reported-response usage mismatch: {row['artifact']}")
            world.close_handoff(env)
            if artifact["representation"] is not None and not skipped and not (
                    row["error"] and (row["error"]["stage"] == "representation" or is_api_error)):
                memory.retain(expected_input, artifact["representation"], env.trace, row["handoff"])
            if artifact["next_available_history"] is not None and artifact["next_available_history"] != memory.available:
                issues.append(f"next history mismatch: {row['artifact']}")
            diagnostics.append({
                "scenario_id": scenario_id, "condition": condition, "handoff": row["handoff"],
                "status": row["status"], "success": row["metrics"]["task_success"], "error": row["error"],
                "goal_checks": row["metrics"]["goal_checks"],
                "goal_drift_proxy": [key for key, correct in row["metrics"]["goal_checks"].items() if not correct]
                if row["metrics"]["goal_checks"] is not None else None,
                "drift_proxy_interpretation": "unsatisfied state checks only; does not prove information was missing in the representation",
                "repeated_work_attempts": row["metrics"]["repeated_work_attempts"],
                "recorded_repeated_work": row["metrics"]["repeated_work_count"],
                "policy_violations": [violation for t in env.trace for violation in t["policy_violations"]] if executor_calls else None,
                "credits_spent": env.spent if executor_calls else None, "credit_budget": env.budget,
                "format_error_count": row["metrics"]["format_error_count"],
                "unavailable_observations": row["metrics"]["unavailable_observation_count"],
                "action_count": len(env.trace) if executor_calls else None, "call_count": len(calls), "token_usage": row["token_usage"],
                "representation_size": row["representation_size"], "artifact": row["artifact"],
                "artifact_sha256": digest(run / row["artifact"]),
            })
    if issues:
        raise ValueError("Frozen-run audit failed: " + "; ".join(issues))
    summary = summarize(rows, complete)
    chains = []
    for (scenario_id, condition), chain in grouped.items():
        values = [row["token_usage"]["total_tokens"] for row in chain]
        chains.append({"scenario_id": scenario_id, "condition": condition, "saved_handoffs": len(chain),
                       "cost_comparable": len(chain) == 4 and all(row["status"] == "completed" for row in chain),
                       "chain_success": len(chain) == 4 and all(row["metrics"]["task_success"] for row in chain) if complete else None,
                       "total_tokens": sum(values) if len(chain) == 4 and all(type(v) is int for v in values) else None,
                       "update_tokens": sum(row["token_usage"]["update_tokens"] for row in chain)
                       if all(type(row["token_usage"]["update_tokens"]) is int for row in chain) else None,
                       "executor_tokens": sum(row["token_usage"]["executor_tokens"] for row in chain)
                       if all(type(row["token_usage"]["executor_tokens"]) is int for row in chain) else None})
    baseline = {row["scenario_id"]: row for row in chains if row["condition"] == "full_context"}
    for row in chains:
        base_row = baseline.get(row["scenario_id"], {})
        base = base_row.get("total_tokens")
        row["end_to_end_token_reduction_vs_full"] = (base - row["total_tokens"]) / base if complete and (
            row["cost_comparable"] and base_row.get("cost_comparable") and type(base) is int and base > 0
            and type(row["total_tokens"]) is int) else None
    return {"complete": complete, "source_run": str(run.resolve()), "source_manifest_sha256": digest(run / "manifest.json"),
            "verified": {"frozen_input_hashes": True, "prompt_hashes": True, "frozen_source_hashes": True, "world_carry": True,
                         "discarded_history_not_reintroduced": True, "trace_replay": True,
                         "score_replay": True, "reported_token_usage": True, "saved_handoffs": len(rows)},
            "summary": summary, "chains": chains, "diagnostics": diagnostics,
            "limitations": ["Two synthetic chains, four handoffs and one repetition; not evidence of natural long-horizon generalization.",
                            "No-history deliberately loses prior public goal revisions and tool evidence; its failures are not a W/F-specific ablation.",
                            "Unsatisfied goal checks and repeated actions are behavioral drift proxies, not semantic proof of state omission.",
                            "Full/Summary/CS share new events and tools. Summary and CS update only retained representations plus genuinely new observations.",
                            "Costs include every representation update and executor call. Local size is UTF-8 bytes, not model tokenization.",
                            "Cost reductions are suppressed for chains with representation/executor errors or skipped handoffs; low-cost behavioral failures remain visible alongside their success outcomes.",
                            "Workspace credit budgets differ by checkpoint; credit totals do not represent monetary API cost.",
                            "Candidate reference states are absent. Completion claims do not expose scoring results to the model."]}


def render_report(analysis: dict) -> str:
    lines = ["# 多次中断续做试验：描述性结果", "", f"原始运行：`{analysis['source_run']}`", "",
             "32 个交接组合 = 两个场景 × 四个交接位置 × 四条件；每条件两条独立 chain。", "",
             f"完整运行：{analysis['complete']}；历史边界、世界状态、轨迹、评分和实际 Token 统计复核通过。", "",
             "| 条件 | 成功交接 / 8 | 全部四段成功的 chain / 2 | API Tokens | 重复动作尝试 | 工作区 credits |",
             "|---|---:|---:|---:|---:|---:|"]
    for condition, stats in analysis["summary"]["conditions"].items():
        lines.append(f"| {condition} | {stats['successful_handoffs']} | {stats['successful_chains']} | {stats['total_tokens']} | {stats['repeated_work_attempts']} | {stats['workspace_credits_spent']} |")
    lines += ["", "## 逐链成本（含更新及执行）", "", "| 场景 | 条件 | chain 成功 | API Tokens | 对 Full 降幅 |",
              "|---|---|---:|---:|---:|"]
    for chain in analysis["chains"]:
        reduction = chain["end_to_end_token_reduction_vs_full"]
        display = f"{reduction:.1%}" if reduction is not None else "不可用"
        lines.append(f"| {chain['scenario_id']} | {chain['condition']} | {chain['chain_success']} | {chain['total_tokens']} | {display} |")
    lines += ["", "## 按交接位置成功数量（各位置两场景）", "", "| 条件 | h1 | h2 | h3 | h4 |", "|---|---:|---:|---:|---:|"]
    for condition, stats in analysis["summary"]["conditions"].items():
        positions = stats["successful_handoffs_by_position"]
        lines.append("| " + condition + " | " + " | ".join(str(positions[str(i)]) for i in range(1, 5)) + " |")
    lines += ["", "## 限制与解释边界", ""] + ["- " + limitation for limitation in analysis["limitations"]]
    lines += ["", "本报告不自动判断假设成立。`diagnostics.json` 提供各段失败状态检查、动作成本和原始证据路径，需结合轨迹人工判断原因。", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analysis = audit_run(args.run.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    save_json(args.output / "analysis.json", analysis)
    save_json(args.output / "diagnostics.json", analysis["diagnostics"])
    (args.output / "analysis.md").write_text(render_report(analysis), encoding="utf-8")
    print(f"Saved read-only analysis to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
