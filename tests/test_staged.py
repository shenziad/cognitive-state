"""Offline gates for leakage, shared extraction, failures, and unique billing."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from evaluation.staged import ablate, run_staged_experiment, validate_config
from llm.client import Completion
from utils.io import load_json, save_json
from analyze_staged_experiment import analyze


STATE = {
    "goal": {"objective": "Perform do", "success_criteria": ["done"], "constraints": [], "preferences": []},
    "world": {"facts": ["The preliminary phase has completed", "The active workspace is test"],
              "beliefs": [{"claim": "Readiness may hold", "confidence": 0.7}], "assumptions": ["The schema is stable"]},
    "frontier": {"current_focus": "do", "information_needs": [], "next_action": "Execute do"},
}


def setup(root, conditions, *, count=1, budget=900, repetitions=1):
    config = {"experiment_id": "test-stage", "benchmark": "test-v1", "dataset": "data", "prompt_version": "v0.3",
              "conditions": conditions, "instance_ids": None, "repetitions": repetitions, "randomization_seed": 21,
              "max_steps": 3, "representation_counter": "utf8_bytes", "representation_budget": budget,
              "provider": "openai_sdk", "model": "not-real", "temperature": 0,
              "endpoint": "https://example.test/v1/chat/completions", "api_key_env": "NOT_USED",
              "output_limit_parameter": "max_tokens", "max_output_tokens": 1000, "timeout_seconds": 30,
              "max_api_calls": 100}
    entries = []
    for index in range(count):
        ident = f"task_{index}"
        task = {"instance_id": ident, "history": [{"id": "h1", "role": "user", "content": "HISTORY_ONLY_SECRET"}],
                "recovery_context": "PUBLIC_RECOVERY_ONLY: perform do", "ablation_progress_terms": ["preliminary phase"]}
        environment = {"instance_id": ident, "environment_type": "continuation", "initial_state": {"done": False},
                       "budget": 1, "operations": {"do": {"description": "perform work", "cost": 1, "effects": {"done": True}, "repeat_key": "done"}},
                       "observations": {}, "rubric": {"target_state": {"done": True}, "hidden_audit_marker": "RUBRIC_ONLY_SECRET"}}
        entry = {"instance_id": ident, "task": f"tasks/{ident}.json", "environment": f"environments/{ident}.json",
                 "pair_id": "test_pair" if count == 2 else None, "variant": "a" if index == 0 else "b", "control": False}
        entries.append(entry)
        save_json(root / "data" / entry["task"], task)
        save_json(root / "data" / entry["environment"], environment)
    save_json(root / "data/manifest.json", {"dataset_version": "test-v1", "instances": entries})
    prompt = root / "prompts/v0.3"
    prompt.mkdir(parents=True)
    for name in ("summary", "cognitive_state", "executor"):
        (prompt / f"{name}.txt").write_text(name, encoding="utf-8")
    (root / "src").mkdir()
    (root / "src/snapshot_marker.py").write_text("# frozen source", encoding="utf-8")
    save_json(root / "config.json", config)
    return config


class FakeClient:
    def __init__(self, state=None, missing_usage=False):
        self.state = deepcopy(state if state is not None else STATE)
        self.seen = []
        self.missing_usage = missing_usage

    def complete(self, messages, *, purpose):
        self.seen.append((deepcopy(messages), purpose))
        if purpose == "cognitive_state":
            text = json.dumps(self.state)
        elif purpose == "summary":
            text = "Perform do."
        else:
            text = ('{"tool":"execute","arguments":{"operation":"do"}}' if len(messages) == 2
                    else '{"tool":"finish","arguments":{"status":"completed"}}')
        metadata = {"purpose": purpose, "finish_reason": "stop", "input_tokens": None if self.missing_usage else 10,
                    "output_tokens": None if self.missing_usage else 5}
        return Completion(text, metadata)


class StagedTests(unittest.TestCase):
    def test_no_history_passes_only_explicit_public_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup(root, ["full_context", "no_history"])
            client = FakeClient()
            result = run_staged_experiment(root, root / "config.json", root / "run", client=client)
            rows = load_json(root / "run/results.json")
            no_history = next(r for r in rows if r["condition"] == "no_history")
            artifact = load_json(root / "run" / no_history["artifacts"][0])
            all_messages = json.dumps([c["messages"] for c in artifact["calls"]])
            self.assertIn("PUBLIC_RECOVERY_ONLY", all_messages)
            self.assertNotIn("HISTORY_ONLY_SECRET", all_messages)
            self.assertNotIn("RUBRIC_ONLY_SECRET", all_messages)
            self.assertTrue(result["performance_evaluation_available"])

    def test_shared_cs_extraction_and_cost_ledgers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup(root, ["full_context", "cognitive_state", "cs_no_frontier", "cs_no_uncertainty", "cs_no_progress_facts"])
            client = FakeClient()
            summary = run_staged_experiment(root, root / "config.json", root / "run", client=client)
            self.assertEqual(sum(p == "cognitive_state" for _, p in client.seen), 1)
            records = load_json(root / "run/extraction_records.json")
            self.assertEqual(len(records), 1)
            self.assertEqual(summary["actual_suite_usage"]["total_tokens"], 165)
            rows = load_json(root / "run/results.json")
            self.assertEqual(sum(r["deployment_token_usage"]["total_tokens"] for r in rows), 210)
            self.assertEqual(len({r["extraction_artifact"] for r in rows if r["extraction_artifact"]}), 1)
            for condition in ("cs_no_frontier@900", "cs_no_uncertainty@900", "cs_no_progress_facts@900"):
                self.assertIsNone(summary["conditions"][condition]["scopes"]["all"]["end_to_end_token_reduction"])
            self.assertEqual(load_json(root / "run" / records[0]["artifact"])["representation"], records[0]["representation"])
            report = analyze(root / "run", root / "analysis")
            self.assertTrue(report["verification"]["complete_grid"])

    def test_ablation_cannot_mutate_source_and_progress_scope_is_narrow(self):
        original = deepcopy(STATE)
        text = json.dumps(original)
        state, rule = ablate(text, "cs_no_progress_facts", ["preliminary phase"])
        new = json.loads(state)
        self.assertEqual(original, STATE)
        self.assertEqual(len(new["world"]["facts"]), 1)
        self.assertEqual(new["frontier"], original["frontier"])
        self.assertEqual(rule["removed"]["facts"], [original["world"]["facts"][0]])
        uncertain, _ = ablate(text, "cs_no_uncertainty")
        self.assertEqual(json.loads(uncertain)["world"]["facts"], original["world"]["facts"])
        frontier, _ = ablate(text, "cs_no_frontier")
        self.assertEqual(json.loads(frontier)["frontier"]["next_action"], "unknown")
        empty = deepcopy(original)
        empty["world"]["beliefs"] = []
        empty["world"]["assumptions"] = []
        unchanged, no_op = ablate(json.dumps(empty), "cs_no_uncertainty")
        self.assertEqual(json.loads(unchanged), empty)
        self.assertTrue(no_op["no_op"])
        self.assertEqual(no_op["removed_item_count"], 0)

    def test_extraction_format_failure_has_denominator_and_known_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup(root, ["full_context", "cognitive_state", "cs_no_frontier"])
            invalid = deepcopy(STATE)
            invalid["forbidden_extra"] = True
            client = FakeClient(invalid)
            summary = run_staged_experiment(root, root / "config.json", root / "run", client=client)
            self.assertEqual(sum(p == "cognitive_state" for _, p in client.seen), 1)
            rows = load_json(root / "run/results.json")
            errors = [r for r in rows if r["error"]]
            self.assertEqual(len(errors), 2)
            self.assertTrue(all(r["deployment_token_usage"]["total_tokens"] == 15 for r in errors))
            self.assertTrue(all(r["diagnostics"]["steps"] is None for r in errors))
            self.assertEqual(summary["actual_suite_usage"]["total_tokens"], 45)
            self.assertEqual(summary["conditions"]["cognitive_state@900"]["scopes"]["all"]["task_success_rate"], 0)
            stats = summary["conditions"]["cognitive_state@900"]["scopes"]["all"]
            self.assertIsNone(stats["end_to_end_token_reduction"])
            self.assertEqual(stats["token_reduction_observed_runs"], 0)
            self.assertEqual(stats["token_reduction_error_excluded_pairs"], 1)
            self.assertEqual(stats["deployment_reported_tokens"], 15)
            self.assertIn("forbidden_extra", load_json(root / "run/extraction_records.json")[0]["calls"][0]["response"])

    def test_failed_extraction_excluded_from_reduction_without_losing_other_task_cost(self):
        class OneBadExtractor(FakeClient):
            def complete(self, messages, *, purpose):
                if purpose == "cognitive_state":
                    self.state = deepcopy(STATE)
                    if not any(p == "cognitive_state" for _, p in self.seen):
                        self.state["extra_field"] = True
                return super().complete(messages, purpose=purpose)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup(root, ["full_context", "cognitive_state"], count=2)
            summary = run_staged_experiment(root, root / "config.json", root / "run", client=OneBadExtractor())
            stats = summary["conditions"]["cognitive_state@900"]["scopes"]["main"]
            self.assertEqual(stats["task_success_rate"], 0.5)
            self.assertEqual(stats["token_reduction_observed_runs"], 1)
            self.assertEqual(stats["token_reduction_error_excluded_pairs"], 1)
            self.assertEqual(stats["end_to_end_token_reduction"], -0.5)
            self.assertEqual(stats["deployment_reported_tokens"], 60)
            self.assertEqual(summary["actual_suite_usage"]["total_tokens"], 120)

    def test_api_error_stops_whole_run_no_performance(self):
        class BrokenClient:
            def complete(self, messages, *, purpose):
                raise RuntimeError("SDK error; usage unknown")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup(root, ["full_context"], count=2)
            summary = run_staged_experiment(root, root / "config.json", root / "run", client=BrokenClient())
            self.assertEqual(summary["status"], "aborted_api_error")
            self.assertEqual((summary["saved_runs"], summary["planned_runs"]), (1, 2))
            self.assertFalse(summary["performance_evaluation_available"])
            self.assertIsNone(summary["actual_suite_usage"]["total_tokens"])
            self.assertIsNone(summary["conditions"]["full_context"]["scopes"]["all"]["task_success_rate"])
            self.assertEqual(len(load_json(root / "run/call_ledger.json")), 1)
            report = analyze(root / "run", root / "analysis")
            self.assertFalse(report["performance_evaluation_available"])

    def test_budget_grid_does_not_duplicate_full_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = setup(root, ["full_context", "cognitive_state", "summary"], count=2, repetitions=2)
            config["condition_budgets"] = {"cognitive_state": [700, 900], "summary": [700, 900]}
            save_json(root / "config.json", config)
            client = FakeClient()
            summary = run_staged_experiment(root, root / "config.json", root / "run", client=client)
            self.assertEqual(summary["saved_runs"], 20)
            self.assertEqual(summary["conditions"]["full_context"]["assigned_runs"], 4)
            self.assertEqual(sum(p == "cognitive_state" for _, p in client.seen), 8)
            for key in ("cognitive_state@700", "cognitive_state@900", "summary@700", "summary@900"):
                self.assertEqual(summary["conditions"][key]["scopes"]["main"]["paired_vs_full"]["runs"], 4)
                self.assertEqual(summary["conditions"][key]["scopes"]["main"]["paired_variant_joint_success"]["pairs"], 2)

    def test_unknown_usage_is_never_zero_and_budget_is_never_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup(root, ["full_context", "cognitive_state"], budget=100)
            client = FakeClient(missing_usage=True)
            summary = run_staged_experiment(root, root / "config.json", root / "run", client=client)
            self.assertIsNone(summary["actual_suite_usage"]["total_tokens"])
            extraction = load_json(root / "run/extraction_records.json")[0]
            self.assertIn("exceeds", extraction["error"]["message"])
            self.assertGreater(extraction["raw_response_sizes"][0], 100)
            self.assertEqual(json.loads(extraction["calls"][0]["response"]), STATE)

    def test_strict_configuration_and_input_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = setup(root, ["full_context", "no_history"])
            wrong = deepcopy(config)
            wrong["implicit_retries"] = 2
            with self.assertRaises(ValueError):
                validate_config(wrong)
            wrong = deepcopy(config)
            wrong["condition_budgets"] = {"full_context": [100]}
            with self.assertRaises(ValueError):
                validate_config(wrong)
            task = load_json(root / "data/tasks/task_0.json")
            task["recovery_context"] = {"rubric": "forbidden"}
            save_json(root / "data/tasks/task_0.json", task)
            with self.assertRaises(ValueError):
                run_staged_experiment(root, root / "config.json", root / "run", client=FakeClient())
            self.assertFalse((root / "run").exists())


if __name__ == "__main__":
    unittest.main()
