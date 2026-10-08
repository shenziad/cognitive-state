"""Offline descriptive analysis of one frozen exp001 discriminative run.

This entry point reads saved JSON only. It neither imports the experiment runner
nor loads credentials, and never changes the raw run or an existing output.
"""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.analysis import LABELS
from utils.io import digest, load_json, save_json

DIAGNOSTICS = ("steps", "executor_api_calls", "workspace_credits_spent",
               "workspace_credit_budget", "policy_violation_count",
               "repeated_work_count", "repeated_work_attempts_posthoc",
               "budget_exhausted_observation_count", "unavailable_observation_count",
               "invalid_action_count", "tool_usage_correctness", "decision_consistency")
OUTCOMES = ("both_success", "only_full_success", "only_condition_success", "both_fail")


def within(run: Path, relative: str) -> Path:
    path = (run / relative).resolve()
    if not path.is_relative_to(run.resolve()):
        raise ValueError(f"Artifact path leaves run directory: {relative}")
    return path


def integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def macro(values: list[Any], assigned: int) -> dict[str, Any]:
    """Average task-run values, with explicit coverage rather than missing=0."""
    observed = [v for v in values if type(v) in (int, float)]
    return {"assigned_runs": assigned, "observed_runs": len(observed),
            "missing_runs": assigned - len(observed),
            "macro_mean": mean(observed) if observed else None,
            "reported_total": sum(observed) if observed else None,
            "total": sum(observed) if len(observed) == assigned and assigned else None}


def success(row: dict[str, Any]) -> bool:
    return row["status"] != "error" and not row.get("error") and bool(row["metrics"]["task_success"])


def success_stats(rows: list[dict[str, Any]], assigned: int, available: bool) -> dict[str, Any]:
    count = sum(success(r) for r in rows) if available else None
    return {"assigned_runs": assigned, "recorded_runs": len(rows), "successes": count,
            "task_success_rate": count / assigned if available and assigned else None,
            "errors": sum(bool(r.get("error")) or r["status"] == "error" for r in rows),
            "representation_errors": sum(r.get("error", {}).get("stage") == "representation"
                                         for r in rows if r.get("error"))}


def stage_tokens(calls: list[dict[str, Any]], request_interrupted: bool) -> dict[str, Any]:
    out: dict[str, Any] = {"reported_calls": len(calls)}
    for field in ("input_tokens", "output_tokens"):
        values = [c["metadata"].get(field) for c in calls]
        known = [v for v in values if integer(v)]
        out[field] = sum(known) if len(known) == len(values) and not request_interrupted else None
        out["reported_" + field] = sum(known) if known or not calls else None
        out[field + "_observed_calls"] = len(known)
    out["total_tokens"] = (out["input_tokens"] + out["output_tokens"]
                           if integer(out["input_tokens"]) and integer(out["output_tokens"]) else None)
    known_parts = [out["reported_" + field] for field in ("input_tokens", "output_tokens")
                   if integer(out["reported_" + field])]
    out["reported_total_tokens"] = sum(known_parts) if known_parts else None
    out["request_interrupted"] = request_interrupted
    return out


def task_diagnostic(run: Path, row: dict[str, Any], entry: dict[str, Any],
                    artifact: dict[str, Any], available: bool) -> dict[str, Any]:
    calls, trace = artifact["calls"], artifact["trace"]
    executor = [c for c in calls if c["metadata"]["purpose"] == "executor"]
    extraction = [c for c in calls if c["metadata"]["purpose"] != "executor"]
    error = row.get("error")
    interrupted = bool(error and error["type"] == "RuntimeError")
    # An executor response can fail validation before an action is applied.
    executed = bool(executor or trace)
    finish_status = next((t["observation"]["finished"] for t in reversed(trace)
                          if t["observation"].get("finished") in {"completed", "blocked"}), None)
    termination = ("representation_error" if error and error["stage"] == "representation"
                   else "executor_error" if error else "finish_" + finish_status if finish_status
                   else "step_limit" if row["termination"] == "step_limit" else "finished_unknown")
    stages = {
        "extraction": stage_tokens(extraction, interrupted and error["stage"] == "representation"),
        "executor": stage_tokens(executor, interrupted and error["stage"] == "executor"),
    }
    first = executor[0]["metadata"].get("input_tokens") if executor else None
    total = row["token_usage"].get("total_tokens")
    if not integer(total) or interrupted:
        total = None
    metrics = row["metrics"]
    fixture = load_json(within(run / "inputs", entry["environment"]))
    before, repeated_attempts = fixture["initial_state"], 0
    for t in trace:
        action = t["action"]
        args = action.get("arguments") if isinstance(action, dict) else None
        if (isinstance(action, dict) and set(action) == {"tool", "arguments"}
                and action.get("tool") == "execute" and isinstance(args, dict)
                and set(args) == {"operation"} and isinstance(args["operation"], str)):
            operation = fixture["operations"].get(args["operation"], {})
            repeat_key = operation.get("repeat_key")
            repeated_attempts += bool(repeat_key and before.get(repeat_key) is True)
        before = t["state_after"]
    values = {
        "steps": len(trace), "executor_api_calls": len(executor),
        "workspace_credits_spent": sum(t["cost"] for t in trace),
        "workspace_credit_budget": metrics.get("workspace_credit_budget"),
        "policy_violation_count": sum(len(t["policy_violations"]) for t in trace),
        "repeated_work_count": sum(bool(t["repeated_work"]) for t in trace),
        "repeated_work_attempts_posthoc": repeated_attempts,
        "budget_exhausted_observation_count": sum(t["observation"].get("error") ==
                                                 "Workspace credit budget exhausted" for t in trace),
        "unavailable_observation_count": sum(t["observation"].get("error") ==
                                             "Resource unavailable in this continuation" for t in trace),
        "invalid_action_count": sum(not t["valid"] for t in trace),
        "tool_usage_correctness": metrics.get("tool_usage_correctness") if available else None,
        "decision_consistency": metrics.get("decision_consistency") if available else None,
    }
    values = values if executed else dict.fromkeys(DIAGNOSTICS)
    warnings = [f"saved metric differs from trace: {k}" for k, v in values.items()
                if executed and k in metrics and metrics[k] != v]
    relative = row["artifacts"][0]
    path = within(run, relative)
    return {
        "instance_id": row["instance_id"], "condition": row["condition"],
        "repetition": row["repetition"], "pair_id": entry["pair_id"], "variant": entry["variant"],
        "primary_component": entry["primary_component"], "control": entry["control"],
        "task_success": success(row) if available else None,
        "outcome_available": available, "status": row["status"], "error": error,
        "raw_termination": row["termination"], "termination_category": termination,
        "finish_status": finish_status, "execution_started": executed,
        "behavior_diagnostics_available": executed, **values,
        "policy_violations": [v for t in trace for v in t["policy_violations"]] if executed else None,
        "goal_checks": metrics.get("goal_checks") if executed and available else None,
        "decision_checks": metrics.get("decision_checks") if executed and available else None,
        "final_goal_completion": metrics.get("final_goal_completion") if executed and available else None,
        "diagnostic_consistency_warnings": warnings,
        "tokens": {"initial_executor_input_tokens": first if integer(first) else None,
                   "api_total_tokens": total,
                   "end_to_end_tokens": total if row["condition"] != "reference_state" else None,
                   "reference_construction_cost_measured": False if row["condition"] == "reference_state" else None,
                   **stages},
        "representation_size": row.get("representation_size"),
        "representation_counter": row.get("representation_counter"),
        "representation_budget_compliant": row.get("representation_budget_compliant"),
        "artifact_relative_path": relative, "artifact_path": str(path), "artifact_sha256": digest(path),
        "trajectory_path": str(path), "trajectory_json_pointer": "/trace",
    }


def discordances(rows: list[dict[str, Any]], baselines: dict[tuple[str, int], dict[str, Any]],
                 assigned: int, available: bool) -> dict[str, Any]:
    out: dict[str, Any] = {"assigned_pairs": assigned, "observed_pairs": 0,
                           **dict.fromkeys(OUTCOMES), "success_rate_delta": None,
                           "discordant_instances": []}
    if not available:
        return out
    counts = Counter({key: 0 for key in OUTCOMES})
    for row in rows:
        baseline = baselines[(row["instance_id"], row["repetition"])]
        a, b = success(baseline), success(row)
        key = "both_success" if a and b else "only_full_success" if a else "only_condition_success" if b else "both_fail"
        counts[key] += 1
        if a != b:
            out["discordant_instances"].append({"instance_id": row["instance_id"],
                "repetition": row["repetition"], "full_context_success": a, "condition_success": b,
                "success_delta": int(b) - int(a)})
    return {**out, **counts, "observed_pairs": len(rows),
            "success_rate_delta": (counts["only_condition_success"] - counts["only_full_success"]) / assigned
                                  if assigned else None}


def paired_reduction(rows: list[dict[str, Any]], lookup: dict[tuple[str, int, str], dict[str, Any]],
                     field: str, assigned: int, available: bool) -> dict[str, Any]:
    ratios, condition_values, baseline_values = [], [], []
    excluded_errors = 0
    if available:
        for d in rows:
            if field == "end_to_end_tokens" and d["condition"] == "reference_state":
                continue
            baseline = lookup.get((d["instance_id"], d["repetition"], "full_context"))
            if d["error"] or d["status"] == "error" or (baseline and (baseline["error"] or baseline["status"] == "error")):
                excluded_errors += 1
                continue
            base = baseline["tokens"][field] if baseline else None
            value = d["tokens"][field]
            if integer(base) and base > 0 and integer(value):
                ratios.append((base - value) / base)
                condition_values.append(value)
                baseline_values.append(base)
    return {"assigned_pairs": assigned, "observed_pairs": len(ratios),
            "missing_pairs": assigned - len(ratios), "macro_mean": mean(ratios) if ratios else None,
            "error_excluded_pairs": excluded_errors,
            "comparable_condition_token_total": sum(condition_values) if ratios else None,
            "comparable_full_context_token_total": sum(baseline_values) if ratios else None,
            "comparable_condition_token_macro_mean": mean(condition_values) if ratios else None,
            "comparable_full_context_token_macro_mean": mean(baseline_values) if ratios else None,
            "comparison_population": "same instance/repetition; both status non-error and tokens observed; task success not filtered",
            "available": available and bool(ratios),
            "reason": "reference_construction_cost_unmeasured" if rows and rows[0]["condition"] == "reference_state"
                      and field == "end_to_end_tokens" else None}


def cost_stats(rows: list[dict[str, Any]], lookup: dict[tuple[str, int, str], dict[str, Any]],
               assigned: int, available: bool) -> dict[str, Any]:
    stats: dict[str, Any] = {field: macro([d["tokens"][field] for d in rows], assigned)
                           for field in ("initial_executor_input_tokens", "api_total_tokens", "end_to_end_tokens")}
    for stage in ("extraction", "executor"):
        stats[stage] = {field: macro([d["tokens"][stage][field] for d in rows], assigned)
                        for field in ("input_tokens", "output_tokens", "total_tokens")}
        stats[stage]["reported_calls"] = sum(d["tokens"][stage]["reported_calls"] for d in rows)
        known = [d["tokens"][stage]["reported_total_tokens"] for d in rows
                 if integer(d["tokens"][stage]["reported_total_tokens"])]
        stats[stage]["reported_call_tokens"] = sum(known) if known else None
    stats["initial_input_reduction_vs_full_context"] = paired_reduction(
        rows, lookup, "initial_executor_input_tokens", assigned, available)
    stats["end_to_end_reduction_vs_full_context"] = paired_reduction(
        rows, lookup, "end_to_end_tokens", assigned, available)
    stats["macro_unit"] = "assigned instance × repetition; observable task-run token counts, not API-call averages"
    stats["cost_scope"] = "complete_assigned_run" if available else "saved_responses_only_incomplete_or_mock_run"
    return stats


def behavior_stats(rows: list[dict[str, Any]], assigned: int) -> dict[str, Any]:
    executed = [d for d in rows if d["execution_started"]]
    return {"assigned_runs": assigned, "recorded_runs": len(rows), "executed_runs": len(executed),
            "not_executed_recorded_runs": len(rows) - len(executed),
            "termination_counts": dict(Counter(d["termination_category"] for d in rows)),
            "diagnostics": {k: macro([d[k] for d in executed], len(executed)) for k in DIAGNOSTICS},
            "diagnostic_denominator": "executed_runs; representation failures are null, never zero behavior"}


def pair_stats(pair_id: str, entries: list[dict[str, Any]], conditions: list[str], repetitions: int,
               lookup: dict[tuple[str, int, str], dict[str, Any]], available: bool) -> dict[str, Any]:
    ids = {e["variant"]: e["instance_id"] for e in entries}
    out = {"pair_id": pair_id, "title": entries[0]["title"], "primary_component": entries[0]["primary_component"],
           "instances": ids, "complete_ab_assignment": set(ids) == {"a", "b"}, "conditions": {}}
    for condition in conditions:
        observations = []
        if set(ids) == {"a", "b"}:
            for repetition in range(repetitions):
                a = lookup.get((ids["a"], repetition, condition))
                b = lookup.get((ids["b"], repetition, condition))
                fa = lookup.get((ids["a"], repetition, "full_context"))
                fb = lookup.get((ids["b"], repetition, "full_context"))
                valid = available and all(d is not None for d in (a, b, fa, fb))
                observations.append({"repetition": repetition,
                    "a_success": a["task_success"] if valid else None,
                    "b_success": b["task_success"] if valid else None,
                    "joint_success": a["task_success"] and b["task_success"] if valid else None,
                    "b_minus_a_success": int(b["task_success"]) - int(a["task_success"]) if valid else None,
                    "a_success_delta_vs_full_context": int(a["task_success"]) - int(fa["task_success"]) if valid else None,
                    "b_success_delta_vs_full_context": int(b["task_success"]) - int(fb["task_success"]) if valid else None,
                    "joint_success_delta_vs_full_context": int(a["task_success"] and b["task_success"]) -
                        int(fa["task_success"] and fb["task_success"]) if valid else None})
        known = [o for o in observations if o["joint_success"] is not None]
        counts = Counter("both_success" if o["a_success"] and o["b_success"] else "only_a_success" if o["a_success"]
                         else "only_b_success" if o["b_success"] else "both_fail" for o in known)
        stats = {"assigned_ab_pairs": repetitions if set(ids) == {"a", "b"} else 0,
                 "observed_ab_pairs": len(known), "repetitions": observations,
                 **{key: counts[key] if known else None for key in
                    ("both_success", "only_a_success", "only_b_success", "both_fail")}}
        for side in ("a", "b", "joint"):
            stats[side + "_success_rate"] = mean(int(o[side + "_success"]) for o in known) if known else None
        for key in ("b_minus_a_success", "a_success_delta_vs_full_context", "b_success_delta_vs_full_context",
                    "joint_success_delta_vs_full_context"):
            stats[key + "_macro_mean"] = mean(o[key] for o in known) if known else None
        out["conditions"][condition] = stats
    return out


def build_report(run: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config, manifest = load_json(run / "config.json"), load_json(run / "manifest.json")
    dataset = load_json(run / "inputs/manifest.json")
    rows = load_json(run / "results.json")
    if not config["benchmark"].startswith("exp001-discriminative-") or dataset["dataset_version"] != config["benchmark"]:
        raise ValueError("Expected a frozen exp001 discriminative dataset matching config")
    snapshot_hash = manifest.get("input_sha256", {}).get("manifest.json")
    if snapshot_hash and snapshot_hash != digest(run / "inputs/manifest.json"):
        raise ValueError("Frozen input manifest hash differs from the recorded run")
    conditions, repetitions = config["conditions"], config["repetitions"]
    if not integer(repetitions) or repetitions == 0 or len(set(conditions)) != len(conditions) or "full_context" not in conditions:
        raise ValueError("Invalid repetitions or conditions")
    all_entries = {e["instance_id"]: e for e in dataset["instances"]}
    if len(all_entries) != len(dataset["instances"]):
        raise ValueError("Duplicate dataset instance IDs")
    requested = config["instance_ids"]
    if requested is not None and (set(requested) - set(all_entries) or len(set(requested)) != len(requested)):
        raise ValueError("Invalid selected instance IDs")
    entries = {k: e for k, e in all_entries.items() if requested is None or k in requested}
    expected = {(ident, repetition, condition) for ident in entries
                for repetition in range(repetitions) for condition in conditions}
    lookup = {}
    artifacts = {}
    for row in rows:
        key = (row["instance_id"], row["repetition"], row["condition"])
        if key not in expected or key in lookup:
            raise ValueError("Unexpected or duplicated instance/repetition/condition result")
        path = within(run, row["artifacts"][0])
        artifact = load_json(path)
        if artifact.get("result") != row:
            raise ValueError(f"Result and trajectory artifact differ: {row['artifacts'][0]}")
        lookup[key], artifacts[key] = row, artifact
    interruption = any(r.get("error") and r["error"]["type"] == "RuntimeError" for r in rows)
    complete = (manifest["status"] in {"completed", "completed_with_errors"} and set(lookup) == expected
                and manifest["assigned_runs"] == len(expected) and not interruption)
    # Mock runs can show protocol outcomes, but they remain unavailable as model evidence.
    performance = complete and config["provider"] != "mock"
    diagnostics = [task_diagnostic(run, row, entries[row["instance_id"]], artifacts[key], complete)
                   for key, row in lookup.items()]
    diagnostic_lookup = {(d["instance_id"], d["repetition"], d["condition"]): d for d in diagnostics}
    paired = {k for k, e in entries.items() if not e["control"]}
    controls = set(entries) - paired
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ident in paired:
        pairs[entries[ident]["pair_id"]].append(entries[ident])
    scopes = {"all": set(entries), "paired_instances": paired, "controls": controls}
    families = {family: {k for k in paired if entries[k]["primary_component"] == family} for family in ("G", "W", "F")}
    baselines = {(r["instance_id"], r["repetition"]): r for r in rows if r["condition"] == "full_context"}
    report: dict[str, Any] = {
        "schema_version": "1.0", "status": "completed_descriptive_run" if complete else "blocked_or_incomplete",
        "run_status": manifest["status"], "outcomes_available": complete,
        "performance_evaluation_available": performance,
        "evidence_type": "mock_protocol_validation" if config["provider"] == "mock" else "synthetic_single_run" if complete else "api_interruption_or_incomplete",
        "benchmark": config["benchmark"], "model": config["model"], "provider": config["provider"],
        "conditions": conditions, "repetitions": repetitions, "planned_runs": len(expected),
        "manifest_assigned_runs": manifest["assigned_runs"], "saved_runs": len(rows),
        "reported_api_responses": sum(len(a["calls"]) for a in artifacts.values()),
        "scope": {"selected_instances": len(entries), "paired_instances": len(paired), "ab_groups": len(pairs),
                  "controls": len(controls), "dataset_instances": len(all_entries),
                  "family_instances": {k: len(v) for k, v in families.items()},
                  "dataset_construction": dataset.get("construction"), "dataset_review_status": dataset.get("status")},
        "source": {"run_directory": str(run.resolve()),
                   **{name + "_sha256": digest(run / ("inputs/manifest.json" if name == "dataset_manifest" else name + ".json"))
                      for name in ("manifest", "config", "results", "dataset_manifest")}},
        "missing_assignments": [{"instance_id": k[0], "repetition": k[1], "condition": k[2]}
                                for k in sorted(expected - set(lookup))],
        "success_by_scope": {}, "success_by_family": {}, "controls": {},
        "full_context_discordances": {}, "tokens_by_scope": {}, "diagnostics_by_scope": {},
        "ab_pairs": {key: pair_stats(key, sorted(es, key=lambda e: e["variant"]), conditions,
                                      repetitions, diagnostic_lookup, complete) for key, es in sorted(pairs.items())},
        "reference_construction_cost_measured": False, "reference_end_to_end_advantage": None,
        "scientific_conclusion": None, "hypotheses_confirmed": [], "significance_inference_performed": False,
        "task_diagnostics_file": "task_diagnostics.json",
        "limits": [
            "本报告只描述这一次小型、助手构造的合成续做任务运行；不能推广到长期真实 Agent 任务。",
            "G/W/F 是任务设计中的主要信息差异标签，不是组件消融或因果归因。",
            "各条件的任务失败与提取/表示错误均保留成功率分母；provider/transport 中断使整轮性能与降幅不可发布。",
            "未启动 executor 的提取/表示失败，其 steps、credits、违规、重复工作与不可用观察等执行诊断为 null；均值按已执行样本计算。",
            "Token 宏平均按可观测的 instance × repetition 计算，列出覆盖数量；失败样本已报告成本仍计入，未知用量不补零。",
            "实际已报告 API 花费包含提取失败；降幅仅使用两条件都没有 error 且 Token 可观测的同实例配对，列出 n，不按任务成功筛选。低成本提取失败不能解释为效率优势。",
            "初次输入是第一条 executor 请求的输入 Token；端到端包括提取与全部 executor API 输入/输出 Token。",
            "候选参考状态尚待研究者审核，制作成本未测量；仅列已报告 API 成本，不计算参考状态端到端总成本或优势。",
            "候选参考状态不是 gold：disc_w02_a 的 repair_queue 具体动作名不在关键历史中，含目录知识或作者推断；自动提取阶段看不到目录，存在参考来源缺口。",
            "ToolUsageCorrectness 只衡量 JSON/工具调用是否合法，不衡量行动是否符合目标；DecisionConsistency 是最终要求、约束合规、finish 状态三项均值，提前合法 finish 可在任务失败时仍得 2/3。",
            "repeated_work_count 是环境已记录重复工作；超过预算的重复尝试可能不计入。另列 posthoc repeated_work_attempts 与预算耗尽观察次数，未预注册且不改成功判定。",
            "W02 与 F01 存在统一查询后适应的策略；关键历史可能主要影响成本，因此 A/B joint success 不能证明历史信息不可替代。",
            "相同表示字节上限不保证实际长度相同；UTF-8 字节不是提供方 Token。",
            "本轮不进行显著性推断，不能证明 H1–H3，不能证明 Cognitive State 优于 Summary。",
        ],
    }
    for scope, ids in scopes.items():
        assigned = len(ids) * repetitions
        report["success_by_scope"][scope] = {}
        report["tokens_by_scope"][scope] = {}
        report["diagnostics_by_scope"][scope] = {}
        for condition in conditions:
            selected = [r for r in rows if r["condition"] == condition and r["instance_id"] in ids]
            ds = [d for d in diagnostics if d["condition"] == condition and d["instance_id"] in ids]
            report["success_by_scope"][scope][condition] = success_stats(selected, assigned, complete)
            report["tokens_by_scope"][scope][condition] = cost_stats(ds, diagnostic_lookup, assigned, performance)
            report["diagnostics_by_scope"][scope][condition] = behavior_stats(ds, assigned)
    for family, ids in families.items():
        report["success_by_family"][family] = {condition: success_stats(
            [r for r in rows if r["condition"] == condition and r["instance_id"] in ids], len(ids) * repetitions, complete)
            for condition in conditions}
    for ident in sorted(controls):
        report["controls"][ident] = {"title": entries[ident]["title"], "conditions": {condition: success_stats(
            [r for r in rows if r["condition"] == condition and r["instance_id"] == ident], repetitions, complete)
            for condition in conditions}}
    for condition in conditions:
        if condition == "full_context":
            continue
        report["full_context_discordances"][condition] = {scope: discordances(
            [r for r in rows if r["condition"] == condition and r["instance_id"] in ids],
            baselines, len(ids) * repetitions, complete) for scope, ids in {**scopes, **families}.items()}
    return report, diagnostics


def number(value: Any) -> str:
    return "未提供" if value is None else f"{value:.2f}" if type(value) is float else str(value)


def rate(value: Any) -> str:
    return "不可评价" if value is None else f"{value:.1%}"


def token_cell(stats: dict[str, Any]) -> str:
    return f"{number(stats['macro_mean'])} / {number(stats['total'])}（{stats['observed_runs']}/{stats['assigned_runs']}）"


def markdown(report: dict[str, Any]) -> str:
    lines = ["# exp001 区分性合成续做任务：单轮描述分析", "",
             f"模型：`{report['model']}`；数据集：`{report['benchmark']}`；状态：`{report['run_status']}`。",
             f"本次选择 {report['scope']['paired_instances']} 个配对实例（{report['scope']['ab_groups']} 组 A/B）和 "
             f"{report['scope']['controls']} 个 controls；每组合重复 {report['repetitions']} 次；"
             f"保存 {report['saved_runs']}/{report['planned_runs']} 个组合。", ""]
    if not report["outcomes_available"]:
        lines += ["**运行中断或记录不完整：不发布本轮任务成功率、A/B joint success、配对差异或 Token 降幅。**",
                  "以下诊断和已报告 Token 仅描述已保存响应；未知请求成本与未完成组合不能补零。", ""]
    elif not report["performance_evaluation_available"]:
        lines += ["**本次使用 mock；下列结果仅验证协议和后处理，不能当作真实模型能力证据。**", ""]
    lines += ["## 成功率与分母", "", "| 条件 | 16 配对实例范围 | controls 范围 | 全部 | G | W | F |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for condition in report["conditions"]:
        cells = []
        for group in ("paired_instances", "controls", "all"):
            s = report["success_by_scope"][group][condition]
            cells.append(f"{rate(s['task_success_rate'])}（{number(s['successes'])}/{s['assigned_runs']}）")
        for family in ("G", "W", "F"):
            s = report["success_by_family"][family][condition]
            cells.append(f"{rate(s['task_success_rate'])}（{number(s['successes'])}/{s['assigned_runs']}）")
        lines.append(f"| {LABELS[condition]} | " + " | ".join(cells) + " |")
    lines += ["", "任务失败和提取/表示错误均保留分母。16 配对实例与 2 controls 是完整数据集的规模；上表按本次实际选择计算。", "",
              "## 每组 A/B 成功与变化", "", "| 组（家族） | 条件 | A 成功率 | B 成功率 | Joint success | B−A | A 相对 Full | B 相对 Full |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for pair_id, pair in report["ab_pairs"].items():
        for condition, s in pair["conditions"].items():
            lines.append(f"| {pair_id}（{pair['primary_component']}） | {LABELS[condition]} | {rate(s['a_success_rate'])} | "
                f"{rate(s['b_success_rate'])} | {rate(s['joint_success_rate'])}（{number(s['both_success'])}/{s['assigned_ab_pairs']}） | "
                f"{number(s['b_minus_a_success_macro_mean'])} | {number(s['a_success_delta_vs_full_context_macro_mean'])} | "
                f"{number(s['b_success_delta_vs_full_context_macro_mean'])} |")
    lines += ["", "Joint success 要求同一组、同一次重复的 A 和 B 都成功；变化是 0/1 成功值之差的宏平均。controls 不进入 A/B 分母。", "",
              "## 与 Full Context 的同实例配对 discordances", "",
              "| 条件 | 范围 | 都成功 | 仅 Full 成功 | 仅该条件成功 | 都失败 | 分母 |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for condition, scopes in report["full_context_discordances"].items():
        for scope in ("paired_instances", "controls"):
            s = scopes[scope]
            lines.append(f"| {LABELS[condition]} | {scope} | " + " | ".join(number(s[k]) for k in OUTCOMES) +
                         f" | {s['assigned_pairs']} |")
    lines += ["", "逐个不一致实例、家族分类与成功率变化保存在 discrimination.json；本轮不作显著性推断。", "",
              "## Token 成本", "",
              "每格为 **每任务宏平均 / 完整总量（可观测组合 / 分配组合）**。完整总量缺失时，JSON 另保留 reported_total；未提供用量不补零。已报告 API 花费包含提取失败。", "",
              "| 条件 | 初次 executor 输入 | Extraction 总 Token | Executor 总 Token | 已报告 API 总 Token | 端到端 Token | 初次输入降幅 | 端到端降幅 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for condition, s in report["tokens_by_scope"]["all"].items():
        end = "制作成本未测量" if condition == "reference_state" else token_cell(s["end_to_end_tokens"])
        initial = s["initial_input_reduction_vs_full_context"]
        reduction = s["end_to_end_reduction_vs_full_context"]
        lines.append(f"| {LABELS[condition]} | {token_cell(s['initial_executor_input_tokens'])} | "
            f"{token_cell(s['extraction']['total_tokens'])} | {token_cell(s['executor']['total_tokens'])} | "
            f"{token_cell(s['api_total_tokens'])} | {end} | {rate(initial['macro_mean'])}（{initial['observed_pairs']}/{initial['assigned_pairs']}） | "
            f"{rate(reduction['macro_mean'])}（{reduction['observed_pairs']}/{reduction['assigned_pairs']}） |")
    lines += ["", "提取与执行阶段的输入/输出 Token、配对实例和 controls 的分项成本在 JSON 中分别列出。降幅只用两条件都非 error 且用量可观测的同实例配对，并列 n；不按任务成功筛选。JSON 另列这些可比配对两侧总量和宏平均。低成本提取失败不能宣称效率优势。参考状态只列 API 成本，不计算其端到端优势。", "",
              "## 已执行样本诊断", "",
              "| 条件 | 已执行 / 分配 | Steps 均值 | Credits 均值 | 违规总数 | 已记录重复 / posthoc 重复尝试 | 预算耗尽观察 | 不可用观察总数 | 终止分类 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for condition, s in report["diagnostics_by_scope"]["all"].items():
        d = s["diagnostics"]
        termination = "; ".join(f"{k}={v}" for k, v in sorted(s["termination_counts"].items()))
        lines.append(f"| {LABELS[condition]} | {s['executed_runs']}/{s['assigned_runs']} | {number(d['steps']['macro_mean'])} | "
            f"{number(d['workspace_credits_spent']['macro_mean'])} | {number(d['policy_violation_count']['reported_total'])} | "
            f"{number(d['repeated_work_count']['reported_total'])} / {number(d['repeated_work_attempts_posthoc']['reported_total'])} | "
            f"{number(d['budget_exhausted_observation_count']['reported_total'])} | {number(d['unavailable_observation_count']['reported_total'])} | {termination} |")
    lines += ["", "执行诊断分母只包含已启动 executor 的样本；提取失败的诊断为 null。finish_blocked、step_limit、representation_error 与 executor_error 分开保存。重复尝试是依据冻结 initial_state、operation.repeat_key 与逐步 state_after 推导的 posthoc 诊断，包括被预算挡住的合法重复尝试；不修改原评分。", "",
              "逐任务错误、执行状态、诊断、Token 以及原始轨迹文件路径和 SHA-256 保存在 task_diagnostics.json；轨迹在原始实例 JSON 的 /trace。", "",
              "## 解释范围", ""]
    lines.extend("- " + limit for limit in report["limits"])
    return "\n".join(lines) + "\n"


def analyze_discriminative(run: Path, output: Path) -> dict[str, Any]:
    run, output = run.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite analysis directory: {output}")
    if output.is_relative_to(run) or run.is_relative_to(output):
        raise ValueError("Analysis output must be separate from the frozen raw run")
    report, diagnostics = build_report(run)
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "discrimination.json", report)
    save_json(output / "task_diagnostics.json", {"schema_version": "1.0", "run_directory": str(run),
        "outcomes_available": report["outcomes_available"], "tasks": diagnostics})
    (output / "analysis.md").write_text(markdown(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = analyze_discriminative(args.run, args.output)
    print(f"Saved {report['status']} analysis to {args.output.resolve()}")


if __name__ == "__main__":
    main()
