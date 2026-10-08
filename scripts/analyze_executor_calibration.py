"""Offline paired executor calibration audit, separate from representation performance."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.continuation import ContinuationEnvironment
from utils.io import digest, load_json, save_json


def inspect(run):
    manifest, rows = load_json(run / "manifest.json"), load_json(run / "results.json")
    assert manifest["status"] == "completed" and len(rows) == manifest["assigned_runs"] == 16
    entries = {e["instance_id"]: e for e in load_json(run / "inputs/manifest.json")["instances"]}
    tokens = responses = invalid = premature = 0
    for row in rows:
        artifact = load_json(run / row["artifacts"][0])
        assert artifact["result"] == row
        env = ContinuationEnvironment(load_json(run / "inputs" / entries[row["instance_id"]]["environment"]))
        for saved in artifact["trace"]:
            env.apply(saved["action"])
            assert env.trace[-1] == saved
        assert env.settings == artifact["final_settings"]
        for k, v in env.evaluate().items():
            assert row["metrics"][k] == v
        invalid += sum(not t["valid"] for t in artifact["trace"])
        premature += int(env.finish_status == "completed" and not all(env.evaluate()["goal_checks"].values()))
        for c in artifact["calls"]:
            assert c["metadata"]["source"] == "api"
            responses += 1
            tokens += c["metadata"]["input_tokens"] + c["metadata"]["output_tokens"]
    return manifest, rows, {"successes": sum(r["metrics"]["task_success"] for r in rows), "assigned_runs": len(rows),
        "invalid_actions": invalid, "premature_finish": premature, "reported_api_responses": responses,
        "reported_api_tokens": tokens, "results_sha256": digest(run / "results.json"), "replayed_runs": len(rows)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Use a new analysis directory")
    m0, r0, s0 = inspect(a.baseline); m1, r1, s1 = inspect(a.candidate)
    assert m0["input_sha256"] == m1["input_sha256"]
    assert {(r["instance_id"], r["repetition"]) for r in r0} == {(r["instance_id"], r["repetition"]) for r in r1}
    finish_only = [r for r in r1 if r["instance_id"] == "cal_finish_only"]
    passed = s1["successes"] >= 15 and len(finish_only) == 2 and all(r["metrics"]["task_success"] for r in finish_only)
    result = {"evidence_type": "independent_synthetic_executor_calibration", "baseline_v02": s0,
        "candidate_v03": s1, "predeclared_gate_passed": passed, "candidate_advantage_demonstrated": s1["successes"] > s0["successes"],
        "hypotheses_confirmed": [], "limitation": "Calibration tests tool execution, not state sufficiency; equal success does not show a protocol improvement."}
    save_json(a.output / "calibration.json", result)
    text = f"""# 共同执行器校准

8 个独立案例，各 2 次，Full Context 输入；两种协议使用完全相同的任务和环境。全部 32 条轨迹独立重放一致。

| 提示 | 成功 | 无效动作 | 提前 completed | API 响应 | 实际 Token |
| --- | --- | --- | --- | --- | --- |
| v0.2 | {s0['successes']}/16 | {s0['invalid_actions']} | {s0['premature_finish']} | {s0['reported_api_responses']} | {s0['reported_api_tokens']} |
| v0.3 | {s1['successes']}/16 | {s1['invalid_actions']} | {s1['premature_finish']} | {s1['reported_api_responses']} | {s1['reported_api_tokens']} |

预先设定的 v0.3 门槛：至少 15/16 成功，且两个 finish-only 正确。通过：{passed}。

这是执行协议校准，不是 Cognitive State 实验结论。若两种提示同样成功，不能声称修正已提高可靠性，也不能保证后续更复杂任务无工具错误。新提示仅明确通用动作形状、目录和完成证据规则，不包含任何后续任务答案。未修改本轮失败记录，未按结果调校准提示。
"""
    (a.output / "analysis.md").write_text(text, encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
