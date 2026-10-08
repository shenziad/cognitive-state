"""Offline checks for denominators, interrupted costs and unexecuted diagnostics."""

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from analyze_discriminative import analyze_discriminative, build_report, stage_tokens, DIAGNOSTICS
from utils.io import load_json, save_json, digest

DATA = ROOT / "datasets/exp001/discriminative_v0.1"
CONDITIONS = ["full_context", "summary", "cognitive_state", "reference_state"]


def call(purpose, inputs, outputs):
    return {"metadata": {"purpose": purpose, "input_tokens": inputs, "output_tokens": outputs}}


def finished(status="completed", state=None):
    return {"action": {"tool": "finish", "arguments": {"status": status}},
            "observation": {"finished": status}, "valid": True, "cost": 0,
            "policy_violations": [], "repeated_work": False, "state_after": state or {}}


def make_run(run):
    dataset = load_json(DATA / "manifest.json")
    save_json(run / "inputs/manifest.json", dataset)
    save_json(run / "config.json", {"benchmark": dataset["dataset_version"], "conditions": CONDITIONS,
        "repetitions": 1, "instance_ids": None, "provider": "openai_sdk", "model": "offline-test"})
    save_json(run / "manifest.json", {"status": "completed_with_errors", "assigned_runs": 72,
        "input_sha256": {"manifest.json": digest(run / "inputs/manifest.json")}})
    rows = []
    for entry in dataset["instances"]:
        fixture = load_json(DATA / entry["environment"])
        save_json(run / "inputs" / entry["environment"], fixture)
        ident = entry["instance_id"]
        for condition in CONDITIONS:
            extraction = [call(condition, 20, 3)] if condition in {"summary", "cognitive_state"} else []
            calls = extraction + [call("executor", 1000 if condition == "full_context" else 100, 10)]
            trace = [finished(state=fixture["initial_state"])]
            error = None
            task_success = not (ident == "disc_g01_a" and condition == "full_context" or
                                ident == "disc_g01_b" and condition == "summary")
            if ident == "disc_g02_a" and condition == "cognitive_state":
                error = {"stage": "representation", "type": "ValueError", "message": "invalid extraction"}
                calls, trace, task_success = extraction, [], False
            if ident == "disc_control02_a" and condition == "summary":
                state = fixture["initial_state"]
                trace = [{"action": {"tool": "execute", "arguments": {"operation": "run_A"}},
                    "observation": {"error": "Workspace credit budget exhausted"}, "valid": True,
                    "cost": 2, "policy_violations": ["budget_exceeded"], "repeated_work": False,
                    "state_after": state}, finished("blocked", state)]
                calls += [call("executor", 120, 10)]
                task_success = False
            if ident == "disc_control01_a" and condition == "cognitive_state":
                trace = [{"action": {"tool": "observe", "arguments": {"resource": "archive/absent"}},
                    "observation": {"error": "Resource unavailable in this continuation"}, "valid": True,
                    "cost": 0, "policy_violations": [], "repeated_work": False,
                    "state_after": fixture["initial_state"]}]
                task_success = False
            artifact = f"instances/{ident}_r0_{condition}.json"
            executor_calls = [c for c in calls if c["metadata"]["purpose"] == "executor"]
            total = sum(c["metadata"]["input_tokens"] + c["metadata"]["output_tokens"] for c in calls)
            row = {"instance_id": ident, "condition": condition, "repetition": 0,
                "status": "error" if error else "completed", "error": error,
                "termination": "error" if error else "step_limit" if ident == "disc_control01_a"
                    and condition == "cognitive_state" else "finished",
                "metrics": {"task_success": task_success, "final_goal_completion": 1.0,
                    "goal_checks": {"initial_goal_already_true": True},
                    "decision_checks": {"completion_status_correct": True},
                    "tool_usage_correctness": 1.0, "decision_consistency": 2 / 3,
                    "workspace_credit_budget": fixture["budget"]},
                "token_usage": {"total_tokens": total}, "artifacts": [artifact]}
            save_json(run / artifact, {"result": row, "calls": calls, "trace": trace})
            rows.append(row)
    save_json(run / "results.json", rows)
    return rows


class DiscriminativeAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run = self.root / "run"
        self.rows = make_run(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pair_scope_sides_controls_and_discordances(self):
        report, diagnostics = build_report(self.run)
        self.assertTrue(report["performance_evaluation_available"])
        self.assertEqual((report["scope"]["paired_instances"], report["scope"]["ab_groups"],
                          report["scope"]["controls"]), (16, 8, 2))
        self.assertEqual(report["scope"]["family_instances"], {"G": 4, "W": 6, "F": 6})
        self.assertEqual(report["success_by_family"]["G"]["cognitive_state"]["task_success_rate"], 3 / 4)
        pair = report["ab_pairs"]["g01"]["conditions"]["summary"]
        self.assertEqual((pair["a_success_rate"], pair["b_success_rate"], pair["joint_success_rate"]), (1, 0, 0))
        self.assertEqual(pair["a_success_delta_vs_full_context_macro_mean"], 1)
        self.assertEqual(pair["b_success_delta_vs_full_context_macro_mean"], -1)
        s = report["full_context_discordances"]["summary"]["paired_instances"]
        self.assertEqual((s["both_success"], s["only_full_success"], s["only_condition_success"], s["both_fail"]), (14, 1, 1, 0))
        self.assertEqual(len(diagnostics), 72)
        self.assertEqual(report["hypotheses_confirmed"], [])
        self.assertFalse(report["significance_inference_performed"])

    def test_extraction_failure_is_in_success_denominator_but_not_behavior(self):
        report, diagnostics = build_report(self.run)
        d = next(d for d in diagnostics if d["instance_id"] == "disc_g02_a" and d["condition"] == "cognitive_state")
        self.assertFalse(d["task_success"])
        self.assertFalse(d["execution_started"])
        self.assertTrue(all(d[k] is None for k in DIAGNOSTICS))
        self.assertIsNone(d["goal_checks"])
        self.assertIsNone(d["final_goal_completion"])
        self.assertEqual(d["tokens"]["api_total_tokens"], 23)
        self.assertEqual(d["tokens"]["executor"]["total_tokens"], 0)
        s = report["success_by_scope"]["all"]["cognitive_state"]
        self.assertEqual((s["assigned_runs"], s["successes"], s["representation_errors"]), (18, 16, 1))
        behavior = report["diagnostics_by_scope"]["all"]["cognitive_state"]
        self.assertEqual(behavior["executed_runs"], 17)
        self.assertEqual(behavior["diagnostics"]["steps"]["observed_runs"], 17)

    def test_failed_extraction_actual_spend_and_comparable_pair_costs(self):
        report, _ = build_report(self.run)
        costs = report["tokens_by_scope"]["all"]["cognitive_state"]
        self.assertEqual(costs["api_total_tokens"]["total"], 17 * 133 + 23)
        self.assertEqual(costs["api_total_tokens"]["macro_mean"], (17 * 133 + 23) / 18)
        self.assertEqual(costs["initial_executor_input_tokens"]["observed_runs"], 17)
        self.assertIsNone(costs["initial_executor_input_tokens"]["total"])
        reduced = costs["end_to_end_reduction_vs_full_context"]
        self.assertEqual((reduced["observed_pairs"], reduced["error_excluded_pairs"]), (17, 1))
        self.assertEqual(reduced["comparable_condition_token_total"], 17 * 133)
        self.assertEqual(reduced["comparable_full_context_token_total"], 17 * 1010)
        # The non-error step-limit failure remains in the comparable population.
        self.assertEqual(costs["initial_input_reduction_vs_full_context"]["observed_pairs"], 17)
        reference = report["tokens_by_scope"]["all"]["reference_state"]
        self.assertEqual(reference["api_total_tokens"]["total"], 18 * 110)
        self.assertIsNone(reference["end_to_end_tokens"]["total"])
        self.assertIsNone(reference["end_to_end_reduction_vs_full_context"]["macro_mean"])

    def test_finish_blocked_step_limit_and_posthoc_budget_blocked_repeat(self):
        _, diagnostics = build_report(self.run)
        d = next(d for d in diagnostics if d["instance_id"] == "disc_control02_a" and d["condition"] == "summary")
        self.assertEqual(d["termination_category"], "finish_blocked")
        self.assertEqual((d["steps"], d["workspace_credits_spent"], d["policy_violation_count"]), (2, 2, 1))
        self.assertEqual((d["repeated_work_count"], d["repeated_work_attempts_posthoc"],
                          d["budget_exhausted_observation_count"]), (0, 1, 1))
        limit = next(d for d in diagnostics if d["instance_id"] == "disc_control01_a" and d["condition"] == "cognitive_state")
        self.assertEqual(limit["termination_category"], "step_limit")
        self.assertEqual(limit["unavailable_observation_count"], 1)

    def test_provider_interruption_publishes_no_performance_or_reduction(self):
        row = deepcopy(self.rows[0])
        row.update(status="error", termination="error", error={"stage": "executor", "type": "RuntimeError", "message": "HTTP=402"})
        row["token_usage"]["total_tokens"] = None
        artifact = load_json(self.run / row["artifacts"][0])
        artifact["result"] = row
        save_json(self.run / row["artifacts"][0], artifact)
        save_json(self.run / "results.json", [row])
        manifest = load_json(self.run / "manifest.json")
        manifest["status"] = "aborted_api_error"
        save_json(self.run / "manifest.json", manifest)
        report, diagnostics = build_report(self.run)
        self.assertFalse(report["performance_evaluation_available"])
        self.assertFalse(report["outcomes_available"])
        self.assertTrue(all(s["task_success_rate"] is None for s in report["success_by_scope"]["all"].values()))
        self.assertIsNone(report["ab_pairs"]["g01"]["conditions"]["full_context"]["joint_success_rate"])
        self.assertIsNone(report["full_context_discordances"]["summary"]["all"]["both_success"])
        self.assertIsNone(diagnostics[0]["task_success"])
        self.assertIsNone(diagnostics[0]["tokens"]["executor"]["total_tokens"])
        self.assertEqual(diagnostics[0]["tokens"]["executor"]["reported_total_tokens"], 1010)
        self.assertIsNone(report["tokens_by_scope"]["all"]["full_context"]["initial_input_reduction_vs_full_context"]["macro_mean"])

    def test_unknown_usage_is_not_zero_and_output_cannot_overwrite(self):
        missing = stage_tokens([call("executor", None, None)], False)
        self.assertIsNone(missing["total_tokens"])
        self.assertIsNone(missing["reported_total_tokens"])
        self.assertEqual(stage_tokens([], False)["total_tokens"], 0)
        row = self.rows[0]
        artifact = load_json(self.run / row["artifacts"][0])
        artifact["calls"][0]["metadata"]["output_tokens"] = None
        row["token_usage"]["total_tokens"] = None
        artifact["result"] = row
        save_json(self.run / row["artifacts"][0], artifact)
        save_json(self.run / "results.json", self.rows)
        before = digest(self.run / "results.json")
        output = self.root / "analysis"
        report = analyze_discriminative(self.run, output)
        self.assertEqual(digest(self.run / "results.json"), before)
        tokens = report["tokens_by_scope"]["all"]["full_context"]["executor"]["total_tokens"]
        self.assertEqual(tokens["observed_runs"], 17)
        self.assertIsNone(tokens["total"])
        self.assertTrue((output / "discrimination.json").exists())
        self.assertTrue((output / "task_diagnostics.json").exists())
        text = (output / "analysis.md").read_text(encoding="utf-8")
        self.assertIn("不能证明 H1–H3", text)
        self.assertIn("不是 gold", text)
        with self.assertRaises(FileExistsError):
            analyze_discriminative(self.run, output)

    def test_duplicate_grid_and_mutated_snapshot_are_rejected(self):
        save_json(self.run / "results.json", self.rows + [self.rows[0]])
        with self.assertRaisesRegex(ValueError, "duplicated"):
            build_report(self.run)
        save_json(self.run / "results.json", self.rows)
        dataset = load_json(self.run / "inputs/manifest.json")
        dataset["status"] = "changed"
        save_json(self.run / "inputs/manifest.json", dataset)
        with self.assertRaisesRegex(ValueError, "hash"):
            build_report(self.run)


if __name__ == "__main__":
    unittest.main()
