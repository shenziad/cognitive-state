"""Descriptive pilot analysis; provider interruptions never become model failures."""

from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from utils.io import digest, load_json, save_json

LABELS = {"full_context": "Full Context", "summary": "Summary", "cognitive_state": "Cognitive State",
          "reference_state": "候选参考状态（待审核）"}


def analyze_run(run: Path, output: Path, diagnostic: Path | None = None) -> dict[str, Any]:
    manifest = load_json(run / "manifest.json")
    config = load_json(run / "config.json")
    results = load_json(run / "results.json")
    assigned_instances = manifest["assigned_runs"] // (config["repetitions"] * len(config["conditions"]))
    task_scope = (f"{assigned_instances} 个合成续做场景（含配对任务/对照）；不能外推到长期真实 Agent 任务"
                  if config["benchmark"].startswith("exp001-discriminative-")
                  else f"{assigned_instances} 个合成配置修复场景；不能外推到长期真实 Agent 任务")
    evaluable = manifest["status"] in {"completed", "completed_with_errors"} and len(results) == manifest["assigned_runs"]
    artifacts = {r["artifacts"][0]: load_json(run / r["artifacts"][0]) for r in results}
    report: dict[str, Any] = {
        "status": "completed_pilot" if evaluable else "blocked_or_incomplete",
        "performance_evaluation_available": evaluable and config["provider"] != "mock",
        "evidence_type": "mock_protocol_validation" if config["provider"] == "mock" else "synthetic_pilot" if evaluable else "api_interruption",
        "run_status": manifest["status"], "planned_runs": manifest["assigned_runs"], "saved_runs": len(results),
        "model": config["model"], "provider": config["provider"], "benchmark": config["benchmark"],
        "representation_counter": config["representation_counter"], "representation_budget": config["representation_budget"],
        "reported_api_responses": sum(len(a["calls"]) for a in artifacts.values()),
        "source": {"run_directory": str(run.resolve()), "manifest_sha256": digest(run / "manifest.json"),
                   "results_sha256": digest(run / "results.json")},
        "conditions": {}, "paired_outcomes": {}, "errors": [],
        "limits": [task_scope,
                   "相同表示上限不保证实际长度相同，字节不等于 DeepSeek Token",
                   "候选参考状态尚未经过研究者审核，人工制作成本未测量",
                   "一次重复只能做描述性分析，不能证明行为等价或方法优越"],
        "hypotheses_confirmed": [],
    }
    if diagnostic is not None:
        report["connection_diagnostic"] = load_json(diagnostic)
    for row in results:
        if row["error"]:
            report["errors"].append({"instance_id": row["instance_id"], "condition": row["condition"], **row["error"]})
    for condition in config["conditions"]:
        rows = [r for r in results if r["condition"] == condition]
        calls = [call for row in rows for call in artifacts[row["artifacts"][0]]["calls"]]
        counts = [r["representation_size"] for r in rows if r["representation_size"] is not None]
        stats: dict[str, Any] = {
            "recorded_runs": len(rows), "task_success_rate": mean(r["metrics"]["task_success"] for r in rows) if evaluable and rows else None,
            "errors": sum(r["error"] is not None for r in rows), "reported_api_responses": len(calls),
            "mean_representation_size": mean(counts) if counts else None,
            "input_tokens": None, "output_tokens": None, "total_tokens": None,
        }
        for key in ("final_goal_completion", "tool_usage_correctness", "decision_consistency", "token_reduction", "end_to_end_token_reduction"):
            values = [r["metrics"].get(key) for r in rows if r["metrics"].get(key) is not None]
            stats[key] = mean(values) if evaluable and values else None
            stats[key + "_observed_runs"] = len(values) if evaluable else 0
        if evaluable and calls and all(type(c["metadata"].get(k)) is int for c in calls for k in ("input_tokens", "output_tokens")):
            stats["input_tokens"] = sum(c["metadata"]["input_tokens"] for c in calls)
            stats["output_tokens"] = sum(c["metadata"]["output_tokens"] for c in calls)
            stats["total_tokens"] = stats["input_tokens"] + stats["output_tokens"]
        report["conditions"][condition] = stats
    if evaluable:
        baselines = {(r["instance_id"], r["repetition"]): r for r in results if r["condition"] == "full_context"}
        for condition in config["conditions"]:
            if condition == "full_context":
                continue
            paired: Counter[str] = Counter()
            for row in (r for r in results if r["condition"] == condition):
                baseline = baselines[(row["instance_id"], row["repetition"])]
                a, b = baseline["metrics"]["task_success"], row["metrics"]["task_success"]
                paired["both_success" if a and b else "only_full_success" if a else "only_condition_success" if b else "both_fail"] += 1
            report["paired_outcomes"][condition] = dict(paired)
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "analysis.json", report)
    lines = ["# SiliconFlow exp001 首轮分析", "", f"模型：`{config['model']}`；数据集：`{config['benchmark']}`。", ""]
    if not evaluable:
        lines += ["**本轮未完成，不能评价模型任务能力或 Cognitive State 效果。**", "",
                  f"计划 {report['planned_runs']} 个组合，保存 {len(results)} 个错误/运行记录，收到 {report['reported_api_responses']} 个模型响应。", ""]
        if report.get("connection_diagnostic"):
            lines += ["脱敏连接诊断：`" + report["connection_diagnostic"].get("sanitized_error", "ok") + "`。", ""]
        lines += ["请求在模型执行前被服务拒绝，因此没有可比较的 Full Context、Summary、CS 结果，也没有可报告的 Token 降幅。原始记录中初始化环境的检查项不是模型完成的目标，不能据此推断表现。", "",
                  "下一步：处理账户余额/付费权限后，以新输出目录重新运行两任务检查，再运行完整 12 任务轮次。保留本次中断记录，不合并为任务失败样本。", ""]
    else:
        lines += ["| 条件 | 成功率 | 初次输入 Token 降幅 | 端到端 Token 降幅 | 已报告总 Token | 错误 |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for condition, stats in report["conditions"].items():
            def percent(value: Any) -> str:
                return "未提供" if value is None else f"{100 * value:.1f}%"
            lines.append(f"| {LABELS[condition]} | {percent(stats['task_success_rate'])} | {percent(stats['token_reduction'])} | {percent(stats['end_to_end_token_reduction'])} | {stats['total_tokens']} | {stats['errors']} |")
        lines += ["", "初次输入降幅与端到端降幅是可观察配对的均值，须结合 JSON 中的 observed_runs；提取失败仍留在成功率分母。候选状态制作成本未知，所以不计算其端到端降幅。", ""]
    lines += ["## 解释范围", ""] + ["- " + limit for limit in report["limits"]]
    if config["provider"] == "mock":
        lines += ["", "本运行使用脚本 mock，分数只能证明协议跑通，不能当作模型实验结论。"]
    (output / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
