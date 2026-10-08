"""Offline replay of saved partial preparations; no API or source-quality labels.

The original run, snapshot and freeze files are read-only inputs. Failed API
attempts are checked at their recorded request boundary, never given a reply.
"""

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.exp004_mechanism.conditions import (
    CONDITIONS, Preparation, compact, prepare, restore_state_text, render_state_text,
)
from experiments.exp004_mechanism.runtime_v2 import projection
from evaluation.staged import ledger_totals
from llm.client import Completion
from utils.io import digest, load_json, parse_json, save_json


def audit(run, output):
    assert not (output / "preparation_audit.json").exists() and not (output / "preparation_audit.md").exists(), "Refuse overwriting an audit release"
    config = load_json(run / "config.json")
    manifest = load_json(run / "manifest.json")
    release = load_json(run / "execution_release.json")
    ledger = load_json(run / "call_ledger.json")
    prepared = load_json(run / "prepared.json")
    task_order = load_json(run / "task_order.json")
    schedule = load_json(run / "executor_schedule.json")
    assert config["experiment_id"] == "cycle5-mechanism-v2"
    assert manifest["status"] == "aborted_api_error" and manifest["evidence_type"] == "api"
    assert release["execution_version"] == "cycle5-execution-v2"
    assert digest(run / "execution_release.json") == manifest["execution_release_sha256"]
    assert digest(run / "config.json") == manifest["config_sha256"]
    assert config == load_json(run / "snapshot" / config["config_path"])
    assert not (run / "results.json").exists()
    assert not (run / "source_review.json").exists()
    protected_paths = ["config.json", "manifest.json", "execution_release.json", "call_ledger.json",
                       "prepared.json", "task_order.json", "executor_schedule.json"]
    protected = {name: digest(run / name) for name in protected_paths}
    snapshot_checked = []
    for relative, expected_sha in release["sha256"].items():
        assert digest(run / "snapshot" / relative) == expected_sha, relative
        snapshot_checked.append(relative)
    # Imported functions load prompts and schemas from the current checkout.
    # Assert all their implementation/input assets remain byte-identical to the
    # saved execution snapshot before reusing existing prepare/projection.
    replay_assets = [path for path in release["sha256"] if path.startswith((
        "src/", "prompts/cycle5/", "experiments/exp004_mechanism/conditions.py",
        "experiments/exp004_mechanism/runtime_v2.py", "docs/schemas/"))]
    for relative in replay_assets:
        assert digest(ROOT / relative) == release["sha256"][relative], relative
    tasks = {task["task_id"]: task for task in load_json(
        run / "snapshot" / config["dataset_public"])["tasks"]}
    assert len(task_order) == len(set(task_order)) == len(config["task_ids"]) == 12
    assert set(task_order) == set(config["task_ids"])
    expected_preparation_order = [(ident, condition) for ident in task_order for condition in CONDITIONS]
    assert [(item["task_id"], item["condition"]) for item in prepared] == expected_preparation_order[:len(prepared)]
    assert len(prepared) == 31 and len(ledger) == 26
    assert len(schedule) == manifest["assigned_cells"] == 72
    assert {(slot["task_id"], slot["condition"]) for slot in schedule} == set(expected_preparation_order)
    for index, attempt in enumerate(ledger):
        assert attempt["request_index"] == index and attempt["phase"] == "prepare"
        assert attempt["task_id"] in config["task_ids"] and attempt["condition"] in CONDITIONS
        settings = attempt["request_settings"]
        assert settings["model"] == config["model"] and settings["temperature"] == config["temperature"]
        assert settings["extra_body"] == config["extra_body"]
        expected_limit = config["intermediate_max_output_tokens"] if attempt["purpose"].endswith((":planner", ":organizer")) else config["max_output_tokens"]
        assert settings["max_output_tokens"] == expected_limit
    responses = [attempt for attempt in ledger if attempt["status"] == "response"]
    ids = [attempt["metadata"]["response_id"] for attempt in responses]
    assert len(ids) == len(set(ids)) == 25 and all(isinstance(ident, str) and ident for ident in ids)
    assert all(attempt["metadata"]["source"] == "api" and attempt["metadata"]["transport"] == "openai_sdk"
               and attempt["metadata"]["model"] == config["model"] for attempt in responses)

    class Replay:
        def __init__(self, calls):
            self.calls, self.index = calls, 0

        def complete(self, messages, *, purpose, max_output_tokens):
            assert self.index < len(self.calls), "Unexpected unrecorded preparation request"
            call = self.calls[self.index]
            self.index += 1
            assert messages == call["messages"]
            assert purpose == call["metadata"]["purpose"]
            assert max_output_tokens == call["max_output_tokens"]
            return Completion(call["response"], deepcopy(call["metadata"]))

    shared, shared_indices, prior_ident = None, [], None
    covered, records, roundtrips = set(), [], []
    for item in prepared:
        ident, condition = item["task_id"], item["condition"]
        if ident != prior_ident:
            shared, shared_indices = None, []
        prior_ident = ident
        history, interface = projection(tasks[ident])
        assert history == item["history"] and interface == item["public_interface"]
        saved = Preparation.from_dict(item["preparation"])
        replay = Replay(saved.calls)
        reconstructed = prepare(condition, history, interface, config, replay, shared_state=shared)
        assert asdict(reconstructed) == item["preparation"] and replay.index == len(saved.calls)
        indices = item["actual_prepare_request_indices"]
        assert len(indices) == len(saved.calls) and len(indices) == len(set(indices))
        for call, index in zip(saved.calls, indices):
            assert index not in covered
            attempt = ledger[index]
            assert attempt["status"] == "response" and attempt["task_id"] == ident and attempt["condition"] == condition
            assert attempt["purpose"] == call["metadata"]["purpose"] and attempt["phase"] == "prepare"
            assert all(call[key] == attempt[key] for key in ("messages", "response", "metadata"))
            assert call["max_output_tokens"] == attempt["request_settings"]["max_output_tokens"]
            covered.add(index)
        if condition == "cs1":
            shared, shared_indices = reconstructed, indices
        expected_source_indices = shared_indices if condition == "cs_text" else indices
        assert item["source_request_indices"] == expected_source_indices
        assert reconstructed.deployment_calls() == [
            {"messages": deepcopy(ledger[index]["messages"]), "response": ledger[index]["response"],
             "metadata": deepcopy(ledger[index]["metadata"]),
             "max_output_tokens": ledger[index]["request_settings"]["max_output_tokens"]}
            for index in expected_source_indices]
        if condition == "cs_text":
            assert shared is not None and saved.calls == [] and indices == []
            if saved.valid:
                restored = restore_state_text(saved.representation)
                assert compact(restored) == compact(parse_json(shared.representation))
                assert render_state_text(restored) == saved.representation
                roundtrips.append({"task_id": ident, "lossless_roundtrip": True,
                    "source_request_indices": shared_indices,
                    "source_json_sha256": digest_text(shared.representation),
                    "rendered_text_sha256": digest_text(saved.representation),
                    "source_bytes": len(shared.representation.encode("utf-8")),
                    "rendered_bytes": len(saved.representation.encode("utf-8"))})
        records.append({"task_id": ident, "condition": condition,
                        "projected_source_exact": True, "prepare_replay_exact": True,
                        "all_recorded_calls_consumed": True,
                        "encoding_valid": saved.valid,
                        "actual_prepare_request_indices": indices,
                        "source_request_indices": item["source_request_indices"]})

    assert covered == set(range(25))
    failed = ledger[25]
    expected_ident, expected_condition = expected_preparation_order[len(prepared)]
    assert (failed["task_id"], failed["condition"]) == (expected_ident, expected_condition)
    assert failed["status"] == "api_error" and "response" not in failed
    assert failed["metadata"]["input_tokens"] is None and failed["metadata"]["output_tokens"] is None

    class FailedBoundary(Exception):
        pass

    class CheckUnknownRequest:
        def __init__(self):
            self.requests = 0

        def complete(self, messages, *, purpose, max_output_tokens):
            self.requests += 1
            assert self.requests == 1
            assert messages == failed["messages"] and purpose == failed["purpose"]
            assert max_output_tokens == failed["request_settings"]["max_output_tokens"]
            raise FailedBoundary()  # No fabricated Completion or usage.

    checker = CheckUnknownRequest()
    failed_history, failed_interface = projection(tasks[expected_ident])
    try:
        prepare(expected_condition, failed_history, failed_interface, config, checker)
        raise AssertionError("Unknown-usage failed request must not create a preparation")
    except FailedBoundary:
        assert checker.requests == 1
    usage = ledger_totals(ledger)
    assert usage["unknown_usage_attempts"] == 1 and usage["total_tokens"] is None
    assert protected == {name: digest(run / name) for name in protected_paths}
    report = {"audit_type": "partial_saved_preparation_projection_ledger_and_generation_replay_only",
        "source_run": str(run.resolve()), "experiment_id": config["experiment_id"],
        "original_status": manifest["status"], "comparison_complete": False,
        "executor_calls": 0, "source_quality_annotations_performed": False,
        "frozen_snapshot_asset_hashes_checked": len(snapshot_checked),
        "reused_implementation_asset_hashes_checked": len(replay_assets),
        "protected_raw_sha256": protected,
        "prepared_saved": len(prepared), "prepared_assigned": manifest["assigned_cells"],
        "prepared_missing": manifest["assigned_cells"] - len(prepared),
        "prepared_condition_counts": dict(Counter(item["condition"] for item in prepared)),
        "all_saved_preparations_replayed_exactly": True,
        "successful_request_indices_covered_once": sorted(covered),
        "uncovered_request_indices": [25],
        "failed_request": {"request_index": 25, "task_id": failed["task_id"], "condition": failed["condition"],
                           "phase": failed["phase"], "purpose": failed["purpose"], "status": failed["status"],
                           "error": failed["error"], "public_request_boundary_replayed_exactly": True,
                           "response_available": False, "usage_known": False, "fabricated_completion": False},
        "actual_usage": usage, "cs_text_lossless_roundtrips": roundtrips,
        "preparations": records,
        "limits": ["This audit checks exact source projection and preparation generation, not factual quality or future task behavior.",
                   "No source-quality assessments were created and no actor ran.",
                   "The partial preparations do not constitute a completed six-condition comparison.",
                   "Request 25 has no saved response and unknown usage; total Tokens cannot be inferred from the known subtotal.",
                   "CS-text shared source requests are covered once in the actual ledger; each strategy deployment separately includes its source cost."]}
    output.mkdir(parents=True, exist_ok=True)
    save_json(output / "preparation_audit.json", report)
    counts = report["prepared_condition_counts"]
    lines = ["# 第五轮 A-v2 中断准备阶段：离线审计", "",
        "原运行保持 `aborted_api_error`。本次只检查已保存准备产物的公开来源投影、生成可重放性及账本覆盖；没有调用模型，也没有开展来源质量标注。", "",
        f"- 已保存 {len(prepared)}/72 个准备产物，全部与冻结 `prepare`/`projection` 及记录响应逐字段重放一致。",
        "- 25 次成功请求（index 0–24）各由一个真实准备产物覆盖；Full 和 CS-text 不产生准备请求。",
        f"- {len(roundtrips)} 份 CS-text 与对应真实 CS1 做无损逆变换；JSON 值、容器顺序、类型与字段路径完整保留。",
        "- index 25 是下一准备单元 `hd01_b/full_planner` 的 API 失败：请求体边界可重放，但没有响应或可知用量，没有编造产物。",
        "- Executor 调用为 0，缺少 41 个准备产物；本运行不能用作完成的行为或成本比较。", "",
        "| 条件 | 保存准备产物 |", "|---|---:|"]
    lines += [f"| {condition} | {counts.get(condition, 0)} |" for condition in CONDITIONS]
    lines += ["", f"全账本 {usage['request_attempts']} 次尝试，已知小计 {usage['known_reported_tokens']} Tokens，{usage['unknown_usage_attempts']} 次未知用量。**总 Tokens 未知**。共享 CS 源在实际账本只计一次；CS-text 的独立部署归属仍包含该源提取。", "",
              f"冻结快照检查 {len(snapshot_checked)} 个资产 hash；重用实现及提示检查 {len(replay_assets)} 个资产。旧 raw、冻结文件和提示没有修改。", "",
              "编码及回放正确不等于内容充分；没有来源质量标签、任务成功率或任何表示优越性结论。失败 run 的已保存数据只作为可追溯的中断证据。", ""]
    (output / "preparation_audit.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps({"prepared_replayed": len(prepared), "successful_requests_covered": len(covered),
                      "unknown_request_index": 25, "executor_calls": 0,
                      "known_tokens": usage["known_reported_tokens"], "total_tokens": None,
                      "cs_text_roundtrips": len(roundtrips)}, ensure_ascii=False))


def digest_text(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.run.resolve(), args.output.resolve())
