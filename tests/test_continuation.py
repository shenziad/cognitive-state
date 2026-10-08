"""Meaningful gates for history-dependent continuation and irreversible violations."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from agents.agent import AgentExecutor
from evaluation.continuation import ContinuationEnvironment
from llm.client import Completion
from utils.io import load_json
from validate_discriminative_dataset import audit, replay

DATA = ROOT / "datasets/exp001/discriminative_v0.1"


def fixture(ident):
    return load_json(DATA / "environments" / f"{ident}.json")


def examples(ident):
    return load_json(DATA / "review_cases" / f"{ident}.json")["accepted_example"]


class ContinuationTests(unittest.TestCase):
    def test_all_18_solutions_pair_swaps_boundaries_and_provenance(self):
        report = audit(DATA)
        self.assertEqual((report["tasks"], report["pairs"], report["controls"]), (18, 8, 2))

    def test_preferences_and_constraints_lead_to_distinct_valid_choices(self):
        hard, soft = fixture("disc_g02_a"), fixture("disc_g02_b")
        cloud = examples("disc_g02_b")
        self.assertFalse(replay(hard, cloud)["task_success"])
        self.assertTrue(replay(soft, cloud)["task_success"])

    def test_evidence_after_a_repair_does_not_erase_premature_action(self):
        seq = examples("disc_w02_b")
        seq = [seq[1], seq[0], seq[2]]
        result = replay(fixture("disc_w02_b"), seq)
        self.assertEqual(result["final_goal_completion"], 1.0)
        self.assertFalse(result["task_success"])
        self.assertEqual(result["policy_violation_count"], 1)

    def test_validated_stages_allow_both_remaining_orders(self):
        seq = examples("disc_f02_a")
        self.assertTrue(replay(fixture("disc_f02_a"), [seq[1], seq[0], seq[2]])["task_success"])

    def test_repeated_completed_work_consumes_budget_and_blocks_completion(self):
        seq = [{"tool": "execute", "arguments": {"operation": "run_A"}}] + examples("disc_f02_a")
        r = replay(fixture("disc_f02_a"), seq)
        self.assertFalse(r["task_success"])
        self.assertEqual(r["repeated_work_count"], 1)
        self.assertGreater(r["workspace_credits_spent"], r["workspace_credit_budget"])

    def test_untrusted_shapes_do_not_crash_or_change_state(self):
        env = ContinuationEnvironment(fixture("disc_f01_a"))
        before = deepcopy(env.settings)
        for a in ([], {"tool": "finish", "arguments": {"status": []}},
                  {"tool": "execute", "arguments": {"operation": {}}},
                  {"tool": "observe", "arguments": {"resource": []}}):
            self.assertIn("error", env.apply(a))
        self.assertEqual(env.settings, before)

    def test_executor_uses_new_tools_and_does_not_restate_goal_or_rubric(self):
        class EndClient:
            def complete(self, messages, *, purpose):
                import json
                payload = json.loads(messages[1]["content"])
                self_test.assertEqual(set(payload), {"instruction", "context", "tools"})
                self_test.assertEqual({t["tool"] for t in payload["tools"]}, {"observe", "execute", "finish"})
                return Completion('{"tool":"finish","arguments":{"status":"completed"}}',
                                  {"purpose": purpose, "finish_reason": "stop"})
        self_test = self
        env = ContinuationEnvironment(fixture("disc_control02_a"))
        AgentExecutor(EndClient(), "shared executor", 3).run("already verified", env, [])
        self.assertTrue(env.evaluate()["task_success"])


if __name__ == "__main__":
    unittest.main()
