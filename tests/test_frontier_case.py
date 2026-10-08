"""Offline gates for the failure-selected matched intervention case study."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from evaluation.continuation import ContinuationEnvironment
from llm.client import Completion
from run_frontier_case import LOCKED_HASHES, NECESSITY, SOURCE_FILES, SUPPORTED_ACTION, VARIANTS
from run_frontier_case import diagnostics, load_case, run_case, string_digest
from state.representation import CognitiveState
from utils.io import load_json, save_json

CONFIG = ROOT / "configs/exp001_frontier_case.json"


class ProtocolClient:
    """A scripted tool user for protocol checks, never a model-performance estimate."""

    def __init__(self, *, failure_at=None, never_finish=False):
        self.calls, self.messages = 0, []
        self.failure_at, self.never_finish = failure_at, never_finish

    def complete(self, messages, *, purpose):
        self.calls += 1
        self.messages.append(deepcopy(messages))
        if self.calls == self.failure_at:
            raise RuntimeError("Injected provider failure; usage unknown")
        prior_actions = sum(message["role"] == "assistant" for message in messages)
        if self.never_finish:
            action = {"tool": "observe", "arguments": {"resource": "workspace/catalog.json"}}
        elif prior_actions == 0:
            action = {"tool": "execute", "arguments": {"operation": "consume_Z"}}
        else:
            action = {"tool": "finish", "arguments": {"status": "completed"}}
        return Completion(json.dumps(action), {"purpose": purpose, "finish_reason": "stop", "input_tokens": 11,
                                               "output_tokens": 7, "source": "offline_protocol_test"})


class FrontierCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_json(CONFIG)
        cls.source, cls.fixture, cls.prompt, cls.variants, cls.evidence = load_case(ROOT, cls.config)
        cls.original = json.loads(cls.variants[0]["representation"])

    def test_exact_source_locks_and_historical_action_support(self):
        self.assertEqual(string_digest(self.variants[0]["representation"]), LOCKED_HASHES["representation"])
        self.assertEqual(self.evidence["source_ids"], ["h02", "h04"])
        source_messages = {message["id"]: message["content"] for message in self.evidence["messages"]}
        self.assertIn("execute consume_Z: Consume the pearl broker notice", source_messages["h02"])
        self.assertIn("exactly one reservation was accepted by pearl", source_messages["h04"])
        self.assertNotIn("fulfilled=true", json.dumps(source_messages))
        self.assertEqual(self.config["selection"], "posthoc_observed_failure_exploratory")

    def test_only_predeclared_fields_and_strings_change(self):
        expected = {"original": set(), "remove_ledger_necessity_assumption": {"world.assumptions"},
                    "neutral_next_action": {"frontier.next_action"}, "both": {"world.assumptions", "frontier.next_action"},
                    "source_supported_next_action": {"frontier.next_action"}}
        for variant in self.variants:
            CognitiveState.from_dict(variant["state"])
            self.assertEqual({change["path"] for change in variant["diff"]}, expected[variant["variant"]])
            self.assertEqual(variant["state"]["goal"], self.original["goal"])
            for field in ("facts", "beliefs"):
                self.assertEqual(variant["state"]["world"][field], self.original["world"][field])
            for field in ("current_focus", "information_needs"):
                self.assertEqual(variant["state"]["frontier"][field], self.original["frontier"][field])
            if variant["variant"] in {"remove_ledger_necessity_assumption", "both"}:
                self.assertEqual(variant["state"]["world"]["assumptions"],
                                 [value for value in self.original["world"]["assumptions"] if value != NECESSITY])
            if variant["variant"] in {"neutral_next_action", "both"}:
                self.assertEqual(variant["state"]["frontier"]["next_action"], "unknown")
        self.assertEqual(self.variants[-1]["state"]["frontier"]["next_action"], SUPPORTED_ACTION)

    def test_changed_source_fixture_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / self.config["source_run"]
            for relative in SOURCE_FILES.values():
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.source / relative, target)
            changed = load_json(source / SOURCE_FILES["environment"])
            changed["budget"] = 99
            save_json(source / SOURCE_FILES["environment"], changed)
            with self.assertRaisesRegex(ValueError, "SHA mismatch: environment"):
                load_case(root, self.config)
        changed_config = deepcopy(self.config)
        changed_config["source_sha256"]["representation"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "immutable source locks"):
            load_case(ROOT, changed_config)

    def test_budget_and_post_goal_query_replay_are_distinct(self):
        consume = {"tool": "execute", "arguments": {"operation": "consume_Z"}}
        ledger = {"tool": "observe", "arguments": {"resource": "current/reservation_ledger"}}
        finish = {"tool": "finish", "arguments": {"status": "completed"}}
        outcomes = []
        for actions in ([ledger, consume, finish], [consume, finish], [consume, ledger, finish]):
            env = ContinuationEnvironment(self.fixture)
            for action in actions:
                env.apply(action)
            outcomes.append((env.evaluate(), diagnostics(env)))
        self.assertEqual([result[0]["task_success"] for result in outcomes], [False, True, False])
        self.assertEqual([result[0]["workspace_credits_spent"] for result in outcomes], [4, 2, 4])
        self.assertFalse(outcomes[0][0]["goal_checks"]["fulfilled"])
        self.assertTrue(outcomes[2][0]["goal_checks"]["fulfilled"])
        self.assertEqual(outcomes[2][1]["query_count_after_goal_attained"], 1)
        self.assertEqual(outcomes[1][1]["query_count_after_goal_attained"], 0)

    def test_saved_inputs_billing_and_no_fixture_leak_without_env_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            client = ProtocolClient()
            summary = run_case(ROOT, CONFIG, output, client=client)
            self.assertTrue(summary["complete"])
            self.assertEqual(summary["actual_api_usage"]["request_attempts"], 10)
            self.assertEqual(summary["actual_api_usage"]["total_tokens"], 180)
            self.assertFalse(load_json(output / "manifest.json")["dotenv_loaded"])
            self.assertIsNone(summary["scientific_conclusion"])
            self.assertEqual([row["variant"] for row in summary["results"]], VARIANTS)
            contexts = []
            for messages in client.messages:
                self.assertEqual(messages[0]["content"], self.prompt)
                payload = json.loads(messages[1]["content"])
                self.assertEqual(set(payload), {"instruction", "context", "tools"})
                self.assertNotIn("target_state", payload)
                self.assertNotIn("initial_state", payload)
                if len(messages) == 2:
                    contexts.append(payload["context"])
            self.assertEqual(contexts, [variant["representation"] for variant in self.variants])
            with self.assertRaises(FileExistsError):
                run_case(ROOT, CONFIG, output, client=client)
            self.assertEqual(client.calls, 10)

    def test_provider_error_stops_and_preserves_failed_attempt_unknown_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            client = ProtocolClient(failure_at=3)
            summary = run_case(ROOT, CONFIG, output, client=client)
            self.assertFalse(summary["complete"])
            self.assertEqual(summary["status"], "aborted_api_error")
            self.assertEqual(summary["saved_runs"], 2)
            self.assertEqual(client.calls, 3)
            self.assertIsNone(summary["actual_api_usage"]["total_tokens"])
            self.assertEqual(summary["actual_api_usage"]["known_reported_tokens"], 36)
            ledger = load_json(output / "call_ledger.json")
            self.assertEqual(ledger[-1]["status"], "api_error")
            failed = load_json(output / summary["results"][-1]["artifact"])
            self.assertEqual(len(failed["attempts"]), 1)
            self.assertEqual(failed["calls"], [])
            self.assertFalse(failed["result"]["metrics"]["task_success"])

    def test_never_finishing_executor_cannot_exceed_30_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            client = ProtocolClient(never_finish=True)
            summary = run_case(ROOT, CONFIG, Path(directory) / "run", client=client)
            self.assertTrue(summary["complete"])
            self.assertEqual(client.calls, 30)
            self.assertEqual(summary["actual_api_usage"]["request_attempts"], 30)
            self.assertTrue(all(row["termination"] == "step_limit" for row in summary["results"]))
            self.assertFalse(any(row["metrics"]["task_success"] for row in summary["results"]))


if __name__ == "__main__":
    unittest.main()
