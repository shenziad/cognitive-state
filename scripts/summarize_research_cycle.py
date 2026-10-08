"""Collate the frozen second research cycle; no model calls or credential access."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def sha(relative):
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def actual_calls():
    calls = []
    for relative in (
        "results/raw/exp001/fair_v02_20261002",
        "results/raw/exp001/ablation_budget_v02_20261002",
        "results/raw/exp001/frontier_case_v02_20261002",
    ):
        attempts = read(f"{relative}/call_ledger.json")
        assert all(a["status"] == "response" for a in attempts)
        calls.extend(attempts)
    for relative in (
        "results/raw/exp001/executor_calibration_v02_20261002",
        "results/raw/exp001/executor_calibration_v03_20261002",
        "results/raw/exp003/longitudinal_v01_20261002",
    ):
        for row in read(f"{relative}/results.json"):
            artifact = row.get("artifact") or row["artifacts"][0]
            calls.extend(read(f"{relative}/{artifact}")["calls"])
    ids = [c["metadata"]["response_id"] for c in calls]
    assert all(ids) and len(set(ids)) == len(ids)
    for c in calls:
        m = c["metadata"]
        assert m["model"] == "deepseek-ai/DeepSeek-V4-Flash"
        assert m["source"] == "api" and m["transport"] == "openai_sdk"
        assert m["input_tokens"] + m["output_tokens"] == m["usage_details"]["total_tokens"]
    return {"unique_actual_responses": len(calls),
            "provider_tokens": sum(c["metadata"]["usage_details"]["total_tokens"] for c in calls),
            "response_ids_unique_across_entire_cycle": True}


def summarize(output):
    output.mkdir(parents=True, exist_ok=False)
    calibration = read("results/analysis/executor_calibration_20261002/calibration.json")
    fair = read("results/analysis/fair_v02_20261002/analysis.json")
    budget = read("results/analysis/ablation_budget_v02_20261002/analysis.json")
    case = read("results/raw/exp001/frontier_case_v02_20261002/summary.json")
    longitudinal = read("results/analysis/longitudinal_v01_20261002/analysis.json")
    long_rows = read("results/raw/exp003/longitudinal_v01_20261002/results.json")
    sources = [
        "docs/next_experiment_plan_20261002.json",
        "configs/exp001_frontier_case.json",
        "results/analysis/executor_calibration_20261002/calibration.json",
        "results/analysis/fair_v02_20261002/analysis.json",
        "results/analysis/fair_v02_20261002/verification.json",
        "results/analysis/fair_v02_20261002/interpretation.json",
        "results/analysis/ablation_budget_v02_20261002/analysis.json",
        "results/analysis/ablation_budget_v02_20261002/verification.json",
        "results/analysis/ablation_budget_v02_20261002/interpretation.json",
        "results/analysis/cs_encoding_feasibility_20261002.json",
        "results/analysis/frontier_case_v02_20261002/analysis.json",
        "results/analysis/longitudinal_v01_20261002/analysis.json",
        "results/analysis/longitudinal_v01_20261002/interpretation.json",
    ]
    assert fair["saved_runs"] == fair["planned_runs"] == 56
    assert budget["saved_runs"] == budget["planned_runs"] == 140
    assert case["complete"] and case["saved_runs"] == 5
    assert longitudinal["complete"] and len(long_rows) == 32
    assert all(read(f"results/analysis/{name}/verification.json")["status"] == "passed"
               for name in ("fair_v02_20261002", "ablation_budget_v02_20261002"))

    stages = []
    for key, label in (("baseline_v02", "calibration_v0.2"), ("candidate_v03", "calibration_v0.3")):
        c = calibration[key]
        stages.append({"stage": label, "assigned_cells": c["assigned_runs"],
                       "api_responses": c["reported_api_responses"], "provider_tokens": c["reported_api_tokens"]})
    for label, data in (("fair_comparison", fair), ("ablation_budget", budget)):
        usage = data["actual_suite_usage"]
        assert usage["unknown_usage_attempts"] == 0
        stages.append({"stage": label, "assigned_cells": data["saved_runs"],
                       "api_responses": usage["successful_responses"], "provider_tokens": usage["total_tokens"]})
    stages.append({"stage": "posthoc_frontier_case", "assigned_cells": 5,
                   "api_responses": case["actual_api_usage"]["successful_responses"],
                   "provider_tokens": case["actual_api_usage"]["total_tokens"]})
    assert all(r["token_usage"]["total_tokens"] is not None for r in long_rows)
    stages.append({"stage": "four_handoff_pilot", "assigned_cells": 32,
                   "api_responses": sum(r["call_count"] for r in long_rows),
                   "provider_tokens": sum(r["token_usage"]["total_tokens"] for r in long_rows)})
    verified_calls = actual_calls()
    assert verified_calls["unique_actual_responses"] == sum(s["api_responses"] for s in stages)
    assert verified_calls["provider_tokens"] == sum(s["provider_tokens"] for s in stages)

    result = {
        "evidence_type": "small_synthetic_exploratory_research_cycle",
        "model": "deepseek-ai/DeepSeek-V4-Flash", "temperature": 0,
        "completed_planned_stages": 4, "additional_posthoc_diagnostics": 1,
        "hypotheses_confirmed": [], "researcher_dataset_review": "pending",
        "costs": {"stages": stages, "actual_api_responses": sum(s["api_responses"] for s in stages),
                  "actual_provider_tokens": sum(s["provider_tokens"] for s in stages),
                  "assigned_heterogeneous_cells": sum(s["assigned_cells"] for s in stages),
                  "scope": "Actual suite ledgers; shared CS extraction counted once, not a pooled success rate or currency cost."},
        "calibration": calibration,
        "fair_comparison": {k: s["scopes"] for k, s in fair["conditions"].items()},
        "budget_and_ablation": {k: s["scopes"] for k, s in budget["conditions"].items()},
        "frontier_case": {"evidence_type": case["evidence_type"], "successes": sum(r["metrics"]["task_success"] for r in case["results"]),
                          "runs": 5, "limitations": case["limitations"]},
        "longitudinal": {"conditions": longitudinal["summary"]["conditions"], "chains": longitudinal["chains"]},
        "findings": [
            "Automatic CS can preserve confirmed facts while inventing a need to reconfirm them, generating a budget-infeasible plan.",
            "At 1400 bytes only 3/12 main CS sources were executable; ablations left corresponding semantics in other fields.",
            "Five matched edits in one selected failed CS all failed; changing Next Action alone did not isolate the cause.",
            "Both longitudinal CS chains failed at first extraction; no CS executor ran, so long-term semantic drift was not measured.",
            "Summary completed the archive chain with 23.8% fewer total end-to-end tokens than Full, but more uncached input tokens and longer cumulative API latency; monetary savings were not measured.",
        ],
        "next_steps": [
            "First clarify public tool effects and completion receipts for every condition; freeze a new fixture version and preserve old scores.",
            "Then compare extraction reliability under a common measured request budget; log any constrained generation or repair, without silent history fallback.",
            "Add source-linked evidence and explicit unresolved/resolved status, and audit unsupported goals, assumptions and information needs.",
            "Use semantic deletions across all overlapping fields once valid representations are available; distinguish deletion from action-plan repair.",
            "Repeat the four-handoff comparison after reliability gates pass, and expand independently reviewed tasks, lengths and repetitions.",
        ],
        "source_sha256": {p: sha(p) for p in sources},
        "cross_stage_call_verification": verified_calls,
        "summarizer_sha256": sha("scripts/summarize_research_cycle.py"),
    }
    (output / "cycle_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 第二轮科研实验总报告（2026-10-02）", "",
        "四个预先安排的阶段全部执行完成，另有一项失败后选取的单案例诊断。模型为 SiliconFlow 的 `deepseek-ai/DeepSeek-V4-Flash`，temperature 0。所有错误保留；未训练模型、未隐式回退完整历史、未用候选参考状态替代自动提取。", "",
        "## 主要结果", "",
        "**当前自动 Cognitive State 没有显示优于任务导向普通摘要。最突出的缺陷是表示协议可靠性，以及重新打开已经解决的信息需求。**", "",
        "| 阶段 | Full Context | Summary | Cognitive State | No History |", "|---|---:|---:|---:|---:|",
    ]
    fc = fair["conditions"]
    lines.append("| 公平续做主任务（各 12） | " + " | ".join(str(fc[k]["scopes"]["main"]["successes"]) + "/12" for k in ("full_context", "summary@2200", "cognitive_state@2200", "no_history")) + " |")
    lc = longitudinal["summary"]["conditions"]
    lines.append("| 连续交接（各 8） | " + " | ".join(str(lc[k]["successful_handoffs"]) + "/8" for k in ("full_context", "summary", "cognitive_state", "no_history")) + " |")
    lines += ["", "CS 的连续交接 0/8 包括两次首次提取错误和六个 skipped 段；执行器没有启动。这是端到端协议失败，不能解释为认知状态经过多轮后漂移。Summary、Full 均完成 1/2 条四段 chain，No History 与 CS 均为 0/2。", "",
              "### 1. 共同执行器校准", "",
              "v0.2 与 v0.3 均 16/16 成功；v0.3 通过预声明进入门槛，但非法动作由 2 增至 4，总 Tokens 由 25,662 增至 35,150。没有证明新版改善可靠性。后续条件统一使用 v0.3。详见 [校准报告](../executor_calibration_20261002/analysis.md)。", "",
              "### 2. 公平续做", "",
              "12 个主任务来自 6 组 A/B 配对，另外 2 个 controls 分开统计。Summary 与 CS 的主任务端到端 Token 配对平均降幅分别为 28.5%（12 对）和 19.6%（11 对；1 个表示错误排除）。失败仍在成功分母及实际成本中。", "",
              "CS 在一个在途案例里保存了 pearl 已接受的事实，却新增了必须查询 ledger 的假设和信息缺口；额外查询后剩余预算不足。Full 的两例在执行后追加查询也失败；公开 consume 语义/回执不足构成接口混杂，不能据此宣布压缩状态优于完整历史。详见 [公平续做报告](../fair_v02_20261002/analysis.md)。", "",
              "### 3. 字节预算及信息消融", "", "| 表示 | 800 字节 | 1400 字节 | 2200 字节 |", "|---|---:|---:|---:|"]
    for condition in ("summary", "cognitive_state"):
        cells = [budget["conditions"][f"{condition}@{b}"]["scopes"]["main"] for b in (800, 1400, 2200)]
        lines.append("| " + condition + " | " + " | ".join(f"{c['successes']}/12（表示错误 {c['representation_errors']}）" for c in cells) + " |")
    lines += ["", "800/1400 下 CS 大量失败来自超限或格式，不能解释为理论上无法容纳充分信息。一个离线作者编写的合法 CS 仅 433 字节，并通过脚本续做；它不属于模型成绩，也不是人审 gold。", "",
              "1400 下仅 3 个主任务、1 个 control 有有效源 CS。三个消融都改变了输入，但删除字段后其他字段仍保存相同语义；不能证明 Frontier、不确定性或进度不必要。2200 下 CS 两个校准案例在正确完成剩余工作后又读 ledger 超预算。详见 [预算及消融报告](../ablation_budget_v02_20261002/analysis.md) 与 [离线编码可行性](../cs_encoding_feasibility_20261002.json)。", "",
              "### 附加：局部 Frontier 诊断", "",
              "固定一个坏 CS，仅删除必要性假设、屏蔽 Next Action、同时修改两者或写入有公开来源的正确 Next Action；连同原状态共 5 次，全部失败。正确 Next Action 也未阻止先查询 ledger。其他信念及信息缺口仍有冲突，无法把失败定位到单个字段；案例为观察失败后选择，不能合并为主基准成绩。详见 [单案例报告](../frontier_case_v02_20261002/analysis.md)。", "",
              "### 4. 连续四次交接", "",
              "真实世界继承、旧历史删除边界、模型输入、评分与成本复核通过。CS 两条链首次提取即失败。Summary 的 release 链前三段成功，第四次摘要超 2200 字节；archive 链完整成功，计入每次更新及执行后较 Full 少 23.8% 总 Tokens。该链 Summary 未缓存输入为 14,655、Full 为 12,835；输出为 1,382 vs 217；累计 API 耗时 45.39 vs 20.71 秒。缓存结构不同，总 Token 下降不能直接换算金额或时间节省。Full 的 release 第二段漏执行明确要求的 A/B 测试，过早完成，后续失败具有继承关系。详见 [连续交接报告](../longitudinal_v01_20261002/analysis.md)。", "",
              "## 实际模型用量", "", "| 运行 | 分配组合 | API 响应 | Provider Tokens |", "|---|---:|---:|---:|"]
    for s in stages:
        lines.append(f"| {s['stage']} | {s['assigned_cells']} | {s['api_responses']} | {s['provider_tokens']:,} |")
    lines += ["", f"共 {result['costs']['actual_api_responses']} 次实际成功响应、{result['costs']['actual_provider_tokens']:,} provider Tokens；没有未知用量请求。{result['costs']['assigned_heterogeneous_cells']} 个组合来自不同任务/预算/交接协议，不能汇总成总体成功率。共享提取按实际账本只计一次；Token 总量不等于人民币费用。", "",
              "## 下一步顺序", "",
              "1. 修正所有条件共享的公开工具语义及完成回执，冻结新数据版本；保留本轮原始成绩。", "2. 先做提取可靠性门槛：结构约束、字节控制和有记录的修复分别比较，全部调用计成本。禁止静默恢复完整历史。", "3. 给任务事实、未决问题和动作阶段增加可审计来源；检查状态是否虚构目标、前提或确认需求。", "4. 在有效表示足够时跨字段删除同一语义，分开检验信息必要性与行动计划修复。", "5. 通过门槛后重做多次交接，再扩展独立审阅任务、独立变化的历史长度及重复次数。", "",
              "## 结论边界", "",
              "本轮未确认 H1–H3。任务为助手构造的小型合成集，研究者审核仍 pending，除校准外只有一次重复。temperature 0 不能保证不同调用完全复现；预算版本是同一任务的不同条件。低成本失败不构成能力保持的效率优势。本报告及 `cycle_summary.json` 引用冻结结果与 SHA256；原始调用在被 Git 忽略的 `results/raw/`，Ubuntu clone 后需另外转移该目录才能复核原始证据。", ""]
    (output / "analysis.md").write_text("\n".join(lines), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.output)
    print(json.dumps(result["costs"], ensure_ascii=False))
