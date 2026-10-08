"""Read-only aggregation of original interruption, recovery stages and probe costs."""

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utils.io import load_json, save_json, digest
from evaluation.staged import ledger_totals
from report_cycle4 import summarize


def campaign(output):
    if output.exists():
        raise ValueError("Refuse to overwrite a campaign report")
    plan = load_json(ROOT / "docs/cycle4_recovery_v1.json")
    freeze = load_json(ROOT / "docs/freezes/cycle4_recovery_v1.json")
    for relative, sha in freeze["sha256"].items():
        if digest(ROOT / relative) != sha:
            raise ValueError("Recovery plan evidence changed: " + relative)
    prior = ROOT / plan["prior_run"]
    probe = load_json(ROOT / plan["service_probe"])
    ledgers = load_json(prior / "call_ledger.json")
    stages = []
    for item in plan["stages"]:
        run = ROOT / item["output"]
        analysis = ROOT / f"results/analysis/cycle4_{item['stage']}_recovery_v1"
        if not (run / "manifest.json").exists():
            stages.append({"stage": item["stage"], "status": "not_started", "complete": False})
            continue
        review = analysis / "review.json"
        audit = analysis / "audit.json"
        result = summarize(run, review if review.exists() else None, audit if audit.exists() else None)
        result["status"] = load_json(run / "manifest.json")["status"]
        if review.exists():
            entries = load_json(review)["entries"]
            result["source_review"] = {"entries": len(entries),
                "observed_representations": sum(e["representation"] is not None for e in entries),
                "with_concrete_error": sum("incorrect" in e["assessment"].values() for e in entries),
                "with_ambiguity": sum("ambiguous" in e["assessment"].values() for e in entries),
                "by_condition": {c: {"entries": sum(e["condition"] == c for e in entries),
                    "observed_representations": sum(e["condition"] == c and e["representation"] is not None for e in entries),
                    "with_concrete_error": sum(e["condition"] == c and "incorrect" in e["assessment"].values() for e in entries)}
                    for c in result["conditions"] if c != "full_context"}}
        if (analysis / "gate.json").exists():
            result["gate_status"] = load_json(analysis / "gate.json")["status"]
        if audit.exists():
            result["paired_costs"] = load_json(audit).get("paired_costs", [])
        stages.append(result)
        ledgers += load_json(run / "call_ledger.json")
    actual = ledger_totals(ledgers)
    known = actual["known_reported_tokens"] + (probe["total_tokens"] or 0)
    unknown = actual["unknown_usage_attempts"] + probe["unknown_usage_attempts"]
    attempts = actual["request_attempts"] + probe["request_attempts"]
    assert attempts <= plan["request_limit_all_runs_and_probe"]
    record = {"experiment_id": plan["experiment_id"], "execution_version": plan["execution_version"],
        "recovery_plan_sha256": digest(ROOT / "docs/freezes/cycle4_recovery_v1.json"),
        "stages": stages, "prior_interrupted_usage": ledger_totals(load_json(prior / "call_ledger.json")),
        "service_probe": probe, "entire_campaign_usage": {"request_attempts": attempts,
            "successful_responses": actual["successful_responses"] + (probe["status"] == "response_received"),
            "known_reported_tokens": known, "total_tokens": known if unknown == 0 else None,
            "unknown_usage_attempts": unknown},
        "limits": ["Recovery is a separate full run; partial rows are never merged into its denominator.",
            "Task success and encoding validity do not establish source-grounded state correctness.",
            "All tasks are known synthetic development data; repetitions are correlated.",
            "Assistant review is not independent human gold or condition-blinded.",
            "Unknown usage remains unknown; token totals are not currency amounts."]}
    lines = ["# 第四轮恢复实验与研究进展", "",
        "原预检因 API 错误中断，保留原轮并按单独恢复计划从头运行；不拼接部分样本。", "",
        "| 阶段 | 完成 | Full | Summary | CS v0.2 | CS v0.3.1 | 已知 Tokens |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for s in stages:
        values = []
        for c in ("full_context", "summary", "cs_v02", "cs_v031"):
            v = s.get("conditions", {}).get(c)
            values.append(f"{v['successes']}/{v['assigned']}" if v and s["complete"] else "未完成")
        lines.append(f"| {s['stage']} | {s['complete']} | " + " | ".join(values) +
                     f" | {s.get('actual_usage', {}).get('known_reported_tokens', '未运行')} |")
    if all(s["complete"] for s in stages):
        lines += ["", "## 本轮主要发现", "",
            "三个阶段共完成 184 个分配组合（96 预检、56 回归、32 连续交接）；压缩条件的 138 份表示全部首次编码有效，无编码修复。来源审阅与行为成绩分开记录，不能把这些编码结果解释为语义完全正确。", "",
            "**具体正面线索：保留已完成工作的决策身份。** archive 链的 Summary 在第三段丢失此前确认并修复的 right 分支，第四段缺少选择依据而实际 `finish blocked`；Full、CS v0.2、CS v0.3.1 都保留该依据并执行 `seal_right`。错误来源先于当前行为揭示完成审阅。两版 CS 都成功，不能把本案例归因于 v0.3.1 新增字段、G/W/F 名称或 JSON 编码。", "",
            "**负面结果：总成本目标仍未达到。** v0.3.1 三阶段总 Tokens 均高于 Full 和 Summary；v0.2 各阶段均高于 Summary，回归虽少于 Full，却只有 12/14 成功。连续交接仅有两个已知工作流，每条件一次；CS 整链 2/2、Summary 1/2 是开发案例结果，不能确认普遍优势或行为等价。", "",
            "**状态正确性和行为成功不一致。** 预检 35/72 份压缩表示有具体来源错误，其中 32 份仍行为成功。回归 v0.2 的两次失败在实际校准完成后添加预算外 ledger 查询；连续实验 v0.3.1 又保留与当前成功阶段并存的旧 claim，按歧义记录。这些问题需要独立的状态更新诊断。"]
    lines += ["", "## 连续交接", "",
        "| 工作流 | 条件 | 整链全成功 | 成功段数 |", "|---|---|---|---:|"]
    for s in stages:
        for chain in s.get("chains", []):
            lines.append(f"| {chain['scenario']} | {chain['condition']} | {chain['success']} | {chain['handoff_successes']}/4 |")
    lines += ["", "## 成本与审阅", "",
        f"整个流程（含中断原轮和独立探测）：{attempts} 次尝试，{known:,} 已知 Tokens，{unknown} 次未知用量；完整总 Tokens {'未知' if unknown else str(known)}。", "",
        "下表计入提取、维护、执行及失败调用；相对 Full 的正数表示更多 Tokens。它不按任务成功筛选，也不代表人民币费用。", "",
        "| 阶段 | 条件 | 全部策略 Tokens | 相对 Full |", "|---|---|---:|---:|"]
    for s in stages:
        full = s.get("conditions", {}).get("full_context", {}).get("usage", {}).get("total_tokens")
        for c, v in s.get("conditions", {}).items():
            total = v["usage"]["total_tokens"]
            relative = f"{(total / full - 1):+.1%}" if full and total is not None else "未知"
            lines.append(f"| {s['stage']} | {c} | {total if total is not None else '未知'} | {relative} |")
    lines += ["",
        "| 阶段 | 条件 | 最终表示有效 | 首次有效 | 来源审阅有具体错误的表示 | 全部策略 Tokens |",
        "|---|---|---:|---:|---:|---:|"]
    for s in stages:
        for c, v in s.get("conditions", {}).items():
            if c == "full_context":
                continue
            review = s.get("source_review", {}).get("by_condition", {}).get(c)
            annotation = f"{review['with_concrete_error']}/{review['entries']}" if review else "未审阅"
            total = v["usage"]["total_tokens"]
            lines.append(f"| {s['stage']} | {c} | {v['final_valid']}/{v['assigned']} | {v['first_valid']}/{v['assigned']} | {annotation} | {total if total is not None else '未知'} |")
    lines += ["", "编码失败/提取未完成的表示按 not_observed 记录；上述来源错误计数不能与编码有效率或任务成功率互换。全部维护、修复、执行和失败成本保留。", "",
        "详细证据：[恢复预检](../cycle4_preflight_recovery_v1/semantic_behavior_notes.md)、[回归](../cycle4_regression_recovery_v1/semantic_behavior_notes.md)、[连续交接](../cycle4_longitudinal_recovery_v1/semantic_behavior_notes.md)。原中断轮单独见 [关联分析](../cycle4_preflight_v2_interrupted/semantic_behavior_notes.md)。", "",
        "## 新任务与下一步", "",
        "已生成并离线审查 12 条业务工作流、48 个 checkpoint；先写用户要求、工具契约和事件，不以 G/W/F 标签作为任务答案。修复了公开接口泄露、隐含执行要求和失败后仍假定成功等构造问题。它们仍是已知开发候选任务，离线可解性不是模型验证，也没有证明每段都需要历史。见 [设计](../../../docs/independent_workflow_design_v01.md)、[审计](../../../docs/independent_workflow_review_v01.md)和[数据](../../../datasets/independent_workflows_v01/README.md)。", "",
        "下一步优先核查这些候选任务的历史必要性：用 No History 与改变早期事实、保持当前请求相同的配对版本，检查工具能否免费恢复答案及当前提示是否已暴露选择。随后冻结阶段 A 的最小机制矩阵，比较强摘要、额外规划、两步摘要、CS 和同信息文本编码；先区分保留的信息、额外推理和表示形式。v0.3.1 的旧 claim 撤销问题应在单独的新更新版本处理，再在新任务检验。", "",
        "[机制与成本方案](../../../docs/mechanism_and_cost_plan_v01.md)目前仅为草案：运行器、干预规则和新实验协议尚未冻结，A/B/C 均未调用模型。长期成本曲线留待前述检查完成；没有继续扩大本轮样本或选择性重跑。", "",
        "## 解释范围", ""] + ["- " + x for x in record["limits"]]
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "summary.json", record)
    (output / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(record["entire_campaign_usage"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    campaign(p.parse_args().output)
