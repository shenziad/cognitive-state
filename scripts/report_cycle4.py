"""Summarize reviewed cycle4 stages; never sends model requests."""

from collections import Counter, defaultdict
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utils.io import load_json, save_json, digest
from evaluation.staged import ledger_totals


def summarize(run, review_path=None, audit_path=None):
    rows, ledger, manifest, config = [load_json(run / n) for n in
                                     ("results.json", "call_ledger.json", "manifest.json", "config.json")]
    complete = manifest["status"] == "completed" and len(rows) == manifest["assigned_cells"]
    groups = {}
    for condition in config["conditions"]:
        selected = [r for r in rows if r["condition"] == condition]
        calls = [a for r in selected for a in ledger[r["request_start"]:r["request_end"]]]
        purposes = defaultdict(list)
        for call in calls:
            purposes["executor" if call["purpose"] == "executor" else "repair" if call["purpose"].endswith(":repair") else "extraction"].append(call)
        groups[condition] = {"assigned": manifest["assigned_cells"] // len(config["conditions"]),
            "saved": len(selected), "successes": sum(r["success"] for r in selected) if complete else None,
            "executed": sum(r["executed"] for r in selected), "statuses": dict(Counter(r["status"] for r in selected)),
            "final_valid": sum(r["representation_valid"] is True for r in selected) if condition != "full_context" else None,
            "first_valid": sum(bool(r["extraction_attempts"]) and r["extraction_attempts"][0]["valid"] for r in selected) if condition != "full_context" else None,
            "premature_completed": sum(r["premature_completed"] for r in selected),
            "policy_violations": sum(r["metrics"]["policy_violation_count"] for r in selected if r["metrics"]),
            "repeat_attempts": sum(r["repeat_attempts"] for r in selected if r["repeat_attempts"] is not None),
            "usage": ledger_totals(calls), "phase_usage": {p: ledger_totals(c) for p, c in purposes.items()}}
        metas = [c.get("metadata", {}) for c in calls]
        for key in ("input_tokens", "output_tokens", "latency_seconds"):
            values = [m.get(key) for m in metas]
            groups[condition][key] = sum(values) if all(type(v) in (int, float) for v in values) else None
        cached = [(m.get("usage_details", {}).get("prompt_tokens_details") or {}).get("cached_tokens") for m in metas]
        groups[condition]["cached_input_tokens"] = sum(cached) if all(type(v) is int for v in cached) else None
    review_counts = {}
    if review_path:
        review = load_json(review_path)
        for c in config["conditions"]:
            entries = [e for e in review["entries"] if e["condition"] == c]
            if entries:
                review_counts[c] = {d: dict(Counter(e["assessment"][d] for e in entries)) for d in entries[0]["assessment"]}
    chains = []
    if config["stage"] == "longitudinal":
        for ident in sorted({r["instance_id"] for r in rows}):
            for c in config["conditions"]:
                rs = [r for r in rows if r["instance_id"] == ident and r["condition"] == c]
                chains.append({"scenario": ident, "condition": c, "success": all(r["success"] for r in rs) if complete and len(rs) == 4 else None,
                               "handoff_successes": sum(r["success"] for r in rs), "saved": len(rs)})
    failures = [{k: r[k] for k in ("instance_id", "condition", "repetition", "handoff", "status", "error", "metrics", "artifact")}
                for r in rows if not r["success"]]
    return {"stage": config["stage"], "complete": complete, "source_run": str(run), "evidence_type": manifest["evidence_type"],
            "execution_version": manifest["execution_version"], "results_sha256": digest(run / "results.json"),
            "ledger_sha256": digest(run / "call_ledger.json"), "actual_usage": ledger_totals(ledger), "conditions": groups,
            "review_counts": review_counts, "review_sha256": digest(review_path) if review_path else None,
            "audit_sha256": digest(audit_path) if audit_path else None, "chains": chains, "failures": failures,
            "limits": ["Small known synthetic development tasks; no unseen generalization claim.",
                       "Assistant content annotations; not independent human gold and not condition blinded.",
                       "Maintenance, repair and failed calls counted; tokens do not establish currency savings.",
                       "V0.3.1 changes schema, instructions and validation as a bundle; not a single-field causal test."]}


def report(a):
    def measured(value):
        return "未完成/未知" if value is None else str(value)

    lines = [f"# 第四轮：{a['stage']}", "", f"完整运行：{a['complete']}；执行版本 `{a['execution_version']}`。", "",
             "| 条件 | 成功/分配 | 最终编码有效 | 首次有效 | 过早完成 | 总 Tokens | 提取+修复 Tokens |", "|---|---:|---:|---:|---:|---:|---:|"]
    for c, s in a["conditions"].items():
        phases = s["phase_usage"]
        extraction = sum(phases[p]["known_reported_tokens"] for p in ("extraction", "repair") if p in phases)
        final_valid = "不适用" if c == "full_context" else measured(s["final_valid"])
        first_valid = "不适用" if c == "full_context" else measured(s["first_valid"])
        lines.append(f"| {c} | {measured(s['successes'])}/{s['assigned']} | {final_valid} | {first_valid} | {s['premature_completed']} | {measured(s['usage']['total_tokens'])} | {extraction} |")
    u = a["actual_usage"]
    lines += ["", f"实际响应 {u['successful_responses']} 次；已知 Tokens {u['known_reported_tokens']}；总 Tokens {measured(u['total_tokens'])}；未知用量请求 {u['unknown_usage_attempts']}。", "",
              "行为失败、编码错误与跳过均保留分配分母。语义维度、调用阶段成本、缓存输入和延迟见 summary.json。"]
    if not a["complete"]:
        lines += ["", "本阶段中断，表中编码和动作计数只覆盖已保存记录。未运行组合不是行为失败；不得从不平衡的部分样本计算条件成功率、编码率或成本优势。"]
    if a["chains"]:
        lines += ["", "| 场景 | 条件 | 整链全成功 | 成功段数 |", "|---|---|---|---:|"]
        for c in a["chains"]:
            lines.append(f"| {c['scenario']} | {c['condition']} | {c['success']} | {c['handoff_successes']}/4 |")
    lines += ["", "局限："] + ["- " + v for v in a["limits"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p.add_argument("--review", type=Path); p.add_argument("--audit", type=Path)
    args = p.parse_args()
    a = summarize(args.run.resolve(), args.review, args.audit)
    args.output.mkdir(parents=True, exist_ok=False)
    save_json(args.output / "summary.json", a)
    (args.output / "analysis.md").write_text(report(a), encoding="utf-8", newline="\n")
    print(json.dumps({"complete": a["complete"], "usage": a["actual_usage"]}))
