"""Substantive synthetic provider-cost coverage; no API, credentials or real run."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.exp004_mechanism import reporting as r


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mock_run(path):
    """12 versions, 6 conditions, encoding failures, repairs, and shared sources."""
    tasks = [f"hd{pair:02}_{variant}" for pair in range(1, 7) for variant in ("a", "b")]
    config = {"stage": "mechanism", "conditions": list(r.CONDITIONS), "task_ids": tasks,
              "max_api_calls": 400, "token_stop_threshold": 1000000,
              "intermediate_max_output_tokens": 1024, "max_output_tokens": 4096, "max_steps": 4}
    manifest = {"status": "completed", "assigned_cells": 72, "evidence_type": "mock_protocol_validation"}
    ledger, prepared, rows, entries = [], [], [], []

    def request(task, condition, phase, suffix, input_tokens, output_tokens):
        index = len(ledger)
        purpose = condition + ":" + suffix if phase == "prepare" else "executor"
        ledger.append({"request_index": index, "task_id": task, "condition": condition, "phase": phase,
            "purpose": purpose, "status": "response", "request_settings": {"max_output_tokens": 1024 if suffix in {"planner", "organizer"} else 4096},
            "metadata": {"response_id": f"mock_response_{index}", "input_tokens": input_tokens,
                         "output_tokens": output_tokens, "finish_reason": "stop", "purpose": purpose}})
        return index

    for task_number, task in enumerate(tasks):
        source = []
        for condition in r.CONDITIONS:
            own = []
            if condition == "full_planner":
                own.append(request(task, condition, "prepare", "planner", 200 + task_number * 10, 20))
            elif condition == "summary_s1":
                own.append(request(task, condition, "prepare", "extract", 80 + task_number * 10, 20))
                if task == "hd01_b":
                    own.append(request(task, condition, "prepare", "repair", 40, 8))
            elif condition == "summary_s2":
                own.append(request(task, condition, "prepare", "organizer", 90 + task_number * 10, 12))
                own.append(request(task, condition, "prepare", "extract", 120 + task_number * 10, 20))
            elif condition == "cs1":
                own.append(request(task, condition, "prepare", "extract", 110 + task_number * 10, 30))
                if task in {"hd02_a", "hd03_b"}:
                    own.append(request(task, condition, "prepare", "repair", 15, 5))
                source = own
            invalid = (condition == "summary_s1" and task == "hd01_b") or (condition in {"cs1", "cs_text"} and task == "hd03_b")
            rep = None if invalid else "汉字" * (task_number + 1) + (" expanded path/value" if condition == "cs_text" else "")
            prepared.append({"task_id": task, "condition": condition, "actual_prepare_request_indices": own,
                "source_request_indices": source if condition == "cs_text" else own,
                "preparation": {"representation": rep, "valid": not invalid}})
    by_prepared = {(p["task_id"], p["condition"]): p for p in prepared}
    for task_number, task in enumerate(tasks):
        for condition in r.CONDITIONS:
            p = by_prepared[(task, condition)]
            ex = []
            if p["preparation"]["valid"]:
                amount = {"full_context": (100, 10), "full_planner": (90, 10), "summary_s1": (40, 5),
                          "summary_s2": (35, 6), "cs1": (30, 4), "cs_text": (60, 7)}[condition]
                ex.append(request(task, condition, "execute", "executor", amount[0] + task_number * 10, amount[1]))
            indices = p["source_request_indices"] + ex
            success = p["preparation"]["valid"] and not (condition == "cs_text" and task == "hd01_a")
            rows.append({"task_id": task, "condition": condition, "pair_id": task.split("_")[0],
                "variant": task[-1], "success": success, "status": "completed" if p["preparation"]["valid"] else "representation_error",
                "representation_valid": p["preparation"]["valid"], "source_request_indices": p["source_request_indices"],
                "executor_request_indices": ex, "request_indices": indices,
                "deployment_usage": {"total_tokens": sum(ledger[i]["metadata"]["input_tokens"] + ledger[i]["metadata"]["output_tokens"] for i in indices)}})
            if condition not in {"full_context", "cs_text"}:
                scopes = ("planner",) if condition == "full_planner" else ("organizer", "final") if condition == "summary_s2" else ("final",)
                for scope in scopes:
                    status = "not_observed" if not p["preparation"]["valid"] and scope == "final" else "correct"
                    assessment = {dimension: status for dimension in r.DIMENSIONS}
                    if condition == "cs1" and task == "hd01_a":
                        assessment["invented_requirement"] = "incorrect"
                    if condition == "summary_s2" and task == "hd02_b" and scope == "organizer":
                        assessment["missing_decision_dependency"] = "ambiguous"
                    entries.append({"task_id": task, "condition": condition, "review_scope": scope,
                                    "assessment": assessment, "evidence_notes": "Mock source evidence."})
    values = {"manifest.json": manifest, "config.json": config, "results.json": rows,
              "call_ledger.json": ledger, "prepared.json": prepared, "source_review.json": {"entries": entries}}
    for name, value in values.items():
        write(path / name, value)
    return values


def audit_stub(path):
    ledger = json.loads((path / "call_ledger.json").read_text(encoding="utf-8"))
    return {"complete": True, "usage": {"unknown_usage_attempts": 0, "request_attempts": len(ledger),
        "total_tokens": sum(a["metadata"]["input_tokens"] + a["metadata"]["output_tokens"] for a in ledger)}}


class Cycle5ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run = Path(self.temporary.name)
        self.data = mock_run(self.run)
        self.patch = patch.object(r, "_execution_audit", side_effect=audit_stub)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temporary.cleanup()

    def save(self, name):
        write(self.run / name, self.data[name])

    def test_full_shared_cost_identity_and_preparation_subcategories(self):
        report = r.describe_complete_run(self.run)
        budget = report["full_ledger_validation"]
        actual = sum(a["metadata"]["input_tokens"] + a["metadata"]["output_tokens"] for a in self.data["call_ledger.json"])
        shared = 12 * 140 + 10 * sum(range(12)) + 2 * 20
        self.assertEqual(budget["actual_usage"]["total_tokens"], actual)
        self.assertEqual(budget["shared_cs_preparation_usage"]["total_tokens"], shared)
        self.assertEqual(budget["deployment_attribution_sum"]["total_tokens"], actual + shared)
        self.assertEqual(report["conditions"]["cs_text"]["deployment_preparation_usage"], report["conditions"]["cs1"]["deployment_preparation_usage"])
        text_actual = report["conditions"]["cs_text"]["actual_condition_usage"]
        self.assertEqual(text_actual, report["conditions"]["cs_text"]["executor_usage"])
        self.assertEqual(report["conditions"]["full_planner"]["preparation_by_purpose"]["planner"]["request_attempts"], 12)
        self.assertEqual(report["conditions"]["summary_s2"]["preparation_by_purpose"]["organizer"]["request_attempts"], 12)
        self.assertEqual(report["conditions"]["summary_s1"]["preparation_by_purpose"]["repair"]["total_tokens"], 48)
        self.assertEqual(report["conditions"]["cs1"]["preparation_by_purpose"]["repair"]["total_tokens"], 40)

    def test_executor_input_and_whole_strategy_reductions_are_different(self):
        report = r.describe_complete_run(self.run)
        summary = report["conditions"]["summary_s1"]
        full_executor_input = 12 * 100 + 10 * sum(range(12))
        summary_executor_input = 12 * 40 + 10 * sum(range(12)) - 50
        self.assertAlmostEqual(summary["executor_input_reduction_vs_full_aggregate"], 1 - summary_executor_input / full_executor_input)
        self.assertLess(summary["deployment_total_token_reduction_vs_full"], 0)
        failed = next(t for t in summary["per_task"] if t["task_id"] == "hd01_b")
        self.assertEqual(failed["executor_input_reduction_vs_full"], 1)
        self.assertTrue(failed["executor_input_reduction_is_not_efficiency_evidence"])
        self.assertEqual(failed["deployment_total_usage"]["total_tokens"], 158)
        self.assertEqual(summary["executor_input_reduction_observed_tasks"], 12)

    def test_pairs_include_all_failures_and_two_members(self):
        report = r.describe_complete_run(self.run)
        summary = report["conditions"]["summary_s1"]["paired_joint_success"]
        self.assertEqual(len(summary), 6)
        self.assertFalse(summary[0]["both_success"])
        self.assertEqual(len(summary[0]["member_success"]), 2)
        self.assertEqual(report["conditions"]["cs1"]["successes"], 11)
        self.assertEqual(report["conditions"]["cs_text"]["successes"], 10)

    def test_same_source_error_can_succeed_in_cs_and_fail_in_text(self):
        cross = r.describe_complete_run(self.run)["source_semantics_behavior_cross"]
        cs = cross["cs1"]["final"]["concrete_error_success_cross"]
        text = cross["cs_text"]["final"]["concrete_error_success_cross"]
        self.assertEqual(cs["error_and_success"], 1)
        self.assertEqual(text["error_and_failure"], 1)
        self.assertEqual(cross["cs_text"]["final"]["annotation_origin"], "paired_cs1_shared_source")
        self.assertEqual(cross["cs1"]["final"]["exclusive_classes"]["not_observed"]["failures"], 1)
        self.assertEqual(cross["summary_s2"]["organizer"]["exclusive_classes"]["ambiguous_without_concrete_error"]["successes"], 1)

    def test_utf8_bytes_are_measured_with_missing_representations(self):
        conditions = r.describe_complete_run(self.run)["conditions"]
        base = conditions["full_context"]["per_task"][0]
        self.assertEqual(base["representation_utf8_bytes"], 6)
        self.assertEqual(conditions["cs1"]["representation_bytes"]["missing"], 1)
        self.assertGreater(conditions["cs_text"]["representation_bytes"]["sum"], conditions["cs1"]["representation_bytes"]["sum"])

    def test_incomplete_or_missing_assignment_never_gets_full_comparison(self):
        self.data["manifest.json"]["status"] = "aborted_token_threshold"
        self.save("manifest.json")
        with self.assertRaisesRegex(ValueError, "completed run"):
            r.describe_complete_run(self.run)
        self.data["manifest.json"]["status"] = "completed"
        self.save("manifest.json")
        self.data["results.json"].pop()
        self.save("results.json")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            r.describe_complete_run(self.run)

    def test_extra_request_or_missing_shared_attribution_is_rejected(self):
        extra = deepcopy(self.data["call_ledger.json"][-1])
        extra["request_index"] += 1
        extra["metadata"]["response_id"] = "extra_response"
        self.data["call_ledger.json"].append(extra)
        self.save("call_ledger.json")
        with self.assertRaisesRegex(ValueError, "Unattributed"):
            r.describe_complete_run(self.run)
        self.data["call_ledger.json"].pop()
        self.save("call_ledger.json")
        text = next(row for row in self.data["results.json"] if row["condition"] == "cs_text")
        text["source_request_indices"] = []
        text["request_indices"] = text["executor_request_indices"]
        self.save("results.json")
        with self.assertRaisesRegex(ValueError, "source attribution"):
            r.describe_complete_run(self.run)

    def test_budget_last_response_overshoot_is_allowed_but_extra_send_is_not(self):
        ledger = self.data["call_ledger.json"]
        total = sum(a["metadata"]["input_tokens"] + a["metadata"]["output_tokens"] for a in ledger)
        last = ledger[-1]["metadata"]["input_tokens"] + ledger[-1]["metadata"]["output_tokens"]
        self.data["config.json"]["token_stop_threshold"] = total - last + 1
        self.save("config.json")
        report = r.describe_complete_run(self.run)
        self.assertEqual(report["full_ledger_validation"]["final_known_tokens_exceed_threshold"], last - 1)
        self.data["config.json"]["token_stop_threshold"] = total - last
        self.save("config.json")
        with self.assertRaisesRegex(ValueError, "stopping threshold"):
            r.describe_complete_run(self.run)
        self.data["config.json"]["token_stop_threshold"] = 1000000
        self.data["config.json"]["max_api_calls"] = len(ledger) - 1
        self.save("config.json")
        with self.assertRaisesRegex(ValueError, "request cap"):
            r.describe_complete_run(self.run)

    def test_unknown_provider_usage_is_not_zero(self):
        self.data["call_ledger.json"][0]["metadata"]["input_tokens"] = None
        self.save("call_ledger.json")
        # The independent local usage check fails before calling the audit stub.
        with patch.object(r, "_execution_audit", return_value={"complete": True, "usage": {}}):
            with self.assertRaisesRegex(ValueError, "Unknown provider usage"):
                r.describe_complete_run(self.run)


if __name__ == "__main__":
    unittest.main()
