"""Read-only validation and per-budget analysis of a frozen staged run."""

import argparse
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.staged import ABLATIONS, summarize, validate_config  # noqa: E402
from utils.io import digest, load_json, save_json  # noqa: E402


def analyze(run: Path, output: Path) -> dict:
    run = run.resolve()
    manifest, config, results, attempts = [load_json(run / f"{name}.json") for name in ("manifest", "config", "results", "call_ledger")]
    budgets = validate_config(config)
    dataset = load_json(run / "inputs/manifest.json")
    selected = [entry for entry in dataset["instances"] if config["instance_ids"] is None or entry["instance_id"] in config["instance_ids"]]
    expected = {(entry["instance_id"], repetition, condition, budget) for entry in selected
                for repetition in range(config["repetitions"]) for condition, values in budgets.items() for budget in values}
    keys = [(r["instance_id"], r["repetition"], r["condition"], r["budget"]) for r in results]
    if len(set(keys)) != len(keys) or set(keys) - expected:
        raise ValueError("Duplicate or unexpected staged cells")
    checks = []
    for category, directory in (("input_sha256", "inputs"), ("code_sha256", "source")):
        for relative, wanted in manifest[category].items():
            if digest(run / directory / relative) != wanted:
                raise ValueError(f"Frozen {category} hash differs: {relative}")
        checks.append(category)
    for name, wanted in manifest["prompt_sha256"].items():
        if digest(run / "prompts" / f"{name}.txt") != wanted:
            raise ValueError(f"Frozen prompt hash differs: {name}")
    checks.append("prompt_sha256")
    if [a["request_index"] for a in attempts] != list(range(len(attempts))):
        raise ValueError("Attempt ledger indices are not unique and contiguous")
    extractions = load_json(run / "extraction_records.json")
    if len({e["artifact"] for e in extractions}) != len(extractions):
        raise ValueError("Duplicate shared extraction record")
    extraction_lookup = {e["artifact"]: e for e in extractions}
    used_indices = []
    for extraction in extractions:
        if load_json(run / extraction["artifact"]) != extraction:
            raise ValueError("Extraction artifact differs from ledger")
        used_indices.extend(extraction["request_indices"])
    diagnostics = []
    for row in results:
        artifact = load_json(run / row["artifacts"][0])
        if artifact["result"] != row:
            raise ValueError("Instance artifact result differs from result ledger")
        used_indices.extend(artifact["request_indices"])
        source = extraction_lookup.get(row["extraction_artifact"])
        if row["extraction_artifact"] and source is None:
            raise ValueError("Missing shared extraction")
        if source and (source["instance_id"], source["repetition"], source["budget"]) != (
                row["instance_id"], row["repetition"], row["budget"]):
            raise ValueError("Shared extraction belongs to a different task/repetition/budget")
        if row["condition"] == "no_history":
            task_entry = next(e for e in selected if e["instance_id"] == row["instance_id"])
            task = load_json(run / "inputs" / task_entry["task"])
            from evaluation.staged import compact
            recovery = task["recovery_context"]
            if artifact["representation"] != (recovery if isinstance(recovery, str) else compact(recovery)):
                raise ValueError("No-history representation differs from explicit recovery context")
        error = row["error"]
        if error:
            category = "representation_budget" if error["stage"] == "representation" and "exceeds" in error["message"].lower() else error["stage"] + "_error"
        elif row["metrics"]["task_success"]:
            category = "success"
        elif row["termination"] == "step_limit":
            category = "step_limit"
        elif not row["metrics"]["goal_checks"] or not all(row["metrics"]["goal_checks"].values()):
            category = "unfinished_requirements"
        elif row["metrics"]["policy_violation_count"]:
            category = "policy_violation"
        else:
            category = "wrong_finish_status"
        diagnostics.append({"instance_id": row["instance_id"], "condition": row["condition"], "budget": row["budget"],
                            "repetition": row["repetition"], "control": row["control"], "category": category,
                            "error": error, "metrics": row["metrics"], "diagnostics": row["diagnostics"],
                            "representation_size": row["representation_size"], "deployment_token_usage": row["deployment_token_usage"],
                            "artifact": row["artifacts"][0], "extraction_artifact": row["extraction_artifact"],
                            "actions": [t["action"] for t in artifact["trace"]], "ablation_rule": artifact["ablation_rule"]})
    if Counter(used_indices) != Counter(range(len(attempts))):
        raise ValueError("Actual requests are missing or duplicated across execution and extraction ledgers")
    complete = manifest["status"] in {"completed", "completed_with_errors"} and set(keys) == expected
    if any(a["status"] != "response" for a in attempts):
        complete = False
    summary = summarize(results, complete, len(expected), attempts)
    summary["status"] = manifest["status"]
    summary["verification"] = {"checks": checks + ["grid", "artifact_consistency", "unique_actual_request_accounting", "explicit_no_history"],
                               "complete_grid": set(keys) == expected, "missing_cells": len(expected - set(keys))}
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "analysis.json", summary)
    save_json(output / "task_diagnostics.json", diagnostics)
    lines = ["# 阶段实验分析", "", f"- 原始运行：`{run}`", f"- 状态：`{manifest['status']}`", f"- 保存组合：{len(results)}/{len(expected)}", "",
             "Full Context 和无历史条件每任务、每重复仅执行一次。每个预算复用相同 Full Context 配对基线，不增加独立样本数。",
             "共享 CS 每任务、每重复、每预算只抽取一次。单方案成本包含完整提取及本方案执行；全套实际账本只计提取一次。",
             "格式或预算错误计入成功率分母；已知失败调用用量计入实际及方案成本。降幅仅计算配对两侧均非error且用量可观测的组合，附观察数，不按task_success筛选。API 中断轮次不报告性能或降幅。", ""]
    if not complete:
        lines += ["**本轮不完整，下面的性能与降幅为空，不能用于比较。**", ""]
    for scope, title in (("main", "主任务"), ("controls", "控制任务")):
        lines += [f"## {title}", "", "| 条件 | 预算（UTF8字节） | 成功/组合 | 表示失败 | 执行错误 | 配对胜/负 | E2E Token 降幅 | 降幅观察数/错误排除数 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for stats in summary["conditions"].values():
            s = stats["scopes"][scope]
            if not s["runs"]:
                continue
            successes = s["successes"] if complete else "不可评价"
            delta = s["end_to_end_token_reduction"]
            reduction = "诊断消融，不报告" if stats["condition"] in ABLATIONS else f"{delta:.1%}" if delta is not None else "不可评价"
            pair = s["paired_vs_full"]
            lines.append(f"| {stats['condition']} | {stats['budget'] if stats['budget'] is not None else '—'} | {successes}/{s['runs']} | {s['representation_errors']} | {s['executor_errors']} | {pair['wins']}/{pair['losses']} | {reduction} | {s['token_reduction_observed_runs']}/{s['token_reduction_error_excluded_pairs']} |")
        lines.append("")
    usage = summary["actual_suite_usage"]
    lines += ["## 消融实际删除量", "", "| 条件 | 预算 | 应用组合 | 删除项总量 | 变化组合 | 无变化组合 |", "|---|---:|---:|---:|---:|---:|"]
    for stats in summary["conditions"].values():
        if stats["condition"] in ABLATIONS:
            s = stats["scopes"]["all"]
            lines.append(f"| {stats['condition']} | {stats['budget']} | {s['ablation_applied_runs']} | {s['ablation_removed_items']} | {s['ablation_changed_runs']} | {s['ablation_no_op_runs']} |")
    lines += ["", "删除0项的组合没有改变输入，不能作为对应字段不必要的证据。", ""]
    lines += ["## 实际调用账本", "", f"- 请求尝试：{usage['request_attempts']}；成功响应：{usage['successful_responses']}",
              f"- Provider 报告总 Token：{usage['total_tokens']}；已知部分：{usage['known_reported_tokens']}；未知用量请求：{usage['unknown_usage_attempts']}", "",
              "## 解释范围", "", "- 所有预算单独比较，不能将同一任务的多个预算当作新增独立任务。重复仅提供本协议的重复观测。",
              "- 消融保留完整 CS 提取成本，检验字段依赖；不是可部署方案的降本结论。",
              "- cs_no_progress_facts 只删除 world.facts 中匹配显式词组的事实，其他字段可能仍然保存进度。",
              "- repeat_attempts 仅覆盖环境配置 repeat_key，不能等同所有冗余行动。",
              "- 辅助工具合法性和完成状态不能替代主要任务成功；失败分类是后处理诊断，不是机制的因果证明。",
              "- 本分析使用冻结输入、提示及源文件校验，所有失败原输出保存在提取或执行 artifact 中。", ""]
    (output / "analysis.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        summary = analyze(args.run, args.output)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved analysis of {summary['saved_runs']} cells to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
