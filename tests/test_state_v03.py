import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.evidence_interface import EvidenceEnvironment
from llm.client import Completion
from state.v03 import validate_state, ExtractorV03, compact, state_delta
from utils.io import load_json


class Replies:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.messages = []

    def complete(self, messages, *, purpose):
        self.messages.append(copy.deepcopy(messages))
        return Completion(next(self.replies), {"purpose": purpose, "finish_reason": "stop", "input_tokens": 1, "output_tokens": 1})


class StateV03Tests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "docs/examples/cognitive_state_v0.3"
        self.state = load_json(path / "state_before.json")
        self.history = load_json(path / "public_history.json")
        # This is the design example's own public interface, not hidden fixture state.
        self.interface = {"remaining_credits": 3, "credit_scope": "current-checkpoint", "catalog": {
            "operations": [{"name": "consume_Z", "cost": 2}], "resources": [{"name": "current/reservation_ledger", "cost": 2}]}}
        # tool_contract carries explicit public source content, not an observation.

    def test_initial_example_and_observed_completion_update(self):
        validate_state(self.state, self.history, self.interface)
        p = ROOT / "docs/examples/cognitive_state_v0.3"
        after = load_json(p / "state_after.json")
        event = load_json(p / "completion_event.json")
        validate_state(after, self.history + [event], {**self.interface, "remaining_credits": 1})
        delta = state_delta(self.state, after)
        self.assertIn("c1", delta["removed_ids"])
        self.assertIn("op2", delta["added_ids"])
        self.assertTrue(delta["candidate_changed"])

    def test_plan_cannot_certify_completed_operation(self):
        self.history.append({"id": "plan", "role": "assistant", "content": "Plan to consume notice"})
        self.state["world"]["operations"][0].update(phase="completed", source_refs=["plan"])
        with self.assertRaises(ValueError):
            validate_state(self.state, self.history, self.interface)

    def test_missing_source_and_tool_cannot_create_user_requirement(self):
        for refs in (["unseen_future"], ["h03"]):
            s = copy.deepcopy(self.state); s["goal"]["requirements"][0]["source_refs"] = refs
            with self.assertRaises(ValueError): validate_state(s, self.history, self.interface)

    def test_stale_goal_overspend_and_inactive_evidence_rejected(self):
        for change in ("revision", "cost", "inactive"):
            s = copy.deepcopy(self.state)
            if change == "revision": s["frontier"]["candidate_action"]["goal_revision"] = "old"
            elif change == "cost": s["frontier"]["candidate_action"]["known_cost"] = 0
            else: s["world"]["claims"][0]["standing"] = "refuted"
            with self.assertRaises(ValueError): validate_state(s, self.history, self.interface)
        s = copy.deepcopy(self.state); s["world"]["resources"] = []
        s["frontier"]["candidate_action"]["requires"].remove("budget1")
        with self.assertRaises(ValueError): validate_state(s, self.history, {**self.interface, "remaining_credits": 1})

    def test_empty_frontier_and_no_candidate_allowed(self):
        self.state["frontier"] = {"obligations": [], "open_questions": []}
        validate_state(self.state, self.history, self.interface)

    def test_dependency_cycles_and_dangling_links_rejected(self):
        for deps in (["missing"], ["ob1"]):
            s = copy.deepcopy(self.state); s["world"]["claims"][0]["depends_on"] = deps
            with self.assertRaises(ValueError): validate_state(s, self.history, self.interface)

    def test_retained_only_provenance_without_raw_history_recovery(self):
        retained = [{"id": "retained_h1", "role": "assistant", "content": compact(self.state), "retained_schema": "v0.3"}]
        validate_state(self.state, retained, self.interface)
        broken = copy.deepcopy(self.state); broken["world"]["claims"][0]["source_refs"] = ["unretained_h99"]
        with self.assertRaises(ValueError): validate_state(broken, retained, self.interface)

    def test_one_repair_preserves_original_and_uses_no_extra_history(self):
        client = Replies(["{broken", compact(self.state)])
        calls = []
        rep, diagnostics = ExtractorV03(client).extract(self.history, self.interface, "cs_v03", "protocol", calls)
        self.assertIsNotNone(rep)
        self.assertEqual([d["valid"] for d in diagnostics], [False, True])
        self.assertEqual(len(calls), 2)
        self.assertEqual(client.messages[1][:2], client.messages[0])
        self.assertEqual(calls[0]["response"], "{broken")

    def test_double_failure_never_falls_back_or_truncates(self):
        client = Replies([compact(self.state), compact(self.state)])
        rep, checks = ExtractorV03(client, budget=100).extract(self.history, self.interface, "cs_v03", "protocol", [])
        self.assertIsNone(rep); self.assertEqual(len(checks), 2)

    def test_summary_has_same_repair_cap_and_keeps_plain_prose(self):
        client = Replies(["too long", "ok"])
        rep, checks = ExtractorV03(client, budget=3).extract(self.history, self.interface, "summary", "summary prompt", [])
        self.assertEqual(rep, "ok"); self.assertEqual(len(checks), 2)

    def test_every_preflight_solution_and_unperformed_plan_negative(self):
        dataset = load_json(ROOT / "datasets/cycle3_v03/preflight.json")
        for case in dataset["cases"]:
            env = EvidenceEnvironment(case["environment"])
            for action in case["offline_solution"]: env.apply(action)
            self.assertTrue(env.evaluate()["task_success"], case["instance_id"])
            if case["family"] == "plan_only":
                empty = EvidenceEnvironment(case["environment"])
                empty.apply({"tool": "finish", "arguments": {"status": "completed"}})
                self.assertFalse(empty.evaluate()["task_success"])

    def test_public_contract_does_not_reveal_unread_data_or_rubric(self):
        fixture = load_json(ROOT / "datasets/exp001/continuation_v0.2/environments/cont2_inflight_a.json")
        env = EvidenceEnvironment(fixture); interface = env.public_interface("checkpoint")
        self.assertNotIn("accepted_broker", compact(interface))
        self.assertNotIn("target_state", compact(interface))
        self.assertNotIn("initial_state", compact(interface))
        receipt = env.apply({"tool": "execute", "arguments": {"operation": "consume_Z"}})
        self.assertEqual(receipt["confirmed_effects"], {"fulfilled": True})
        self.assertEqual(receipt["remaining_credits"], 1)
        self.assertEqual(env.trace[-1]["observation"], receipt)


if __name__ == "__main__": unittest.main()
