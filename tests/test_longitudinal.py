"""Offline gates for state carry, discarded history, accounting and termination."""

from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from evaluation.longitudinal import HandoffMemory, LongitudinalEnvironment, malformed_action, repeated_attempts, run_longitudinal
from llm.client import Completion
from utils.io import load_json, save_json
from analyze_longitudinal_experiment import audit_run

DATA = ROOT / "datasets/exp003/longitudinal_v0.1"
PATHS = {
    "release_workflow": [
        ["repair_cache"], ["repair_queue", "validate_A", "validate_B"],
        ["pack_private", "choose_offline"], ["deliver_private_offline"]],
    "archive_workflow": [
        ["observe:current/diagnosis", "correct_right"], ["submit_archive"],
        ["poll_archive", "validate_A", "validate_B"], ["seal_right"]],
}


def action(name):
    return {"tool": "observe" if name.startswith("observe:") else "execute",
            "arguments": {"resource": name.split(":", 1)[1]} if name.startswith("observe:") else {"operation": name}}


class ScriptedClient:
    """Protocol validation only; no experimental performance claim."""

    def __init__(self, fail_at=None, malformed_at=None):
        self.calls, self.fail_at, self.malformed_at = 0, fail_at, malformed_at

    def complete(self, messages, *, purpose):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError("Injected provider failure; usage unknown")
        payload = json.loads(messages[1]["content"])
        material = json.dumps(payload["history"]) if purpose != "executor" else payload["context"]
        handoff = int(re.findall(r"Checkpoint ([1-4])", material)[-1])
        scenario = "archive_workflow" if "archive" in material.lower() else "release_workflow"
        if purpose == "executor":
            index = sum(message["role"] == "assistant" for message in messages)
            choices = [action(name) for name in PATHS[scenario][handoff - 1]] + [
                {"tool": "finish", "arguments": {"status": "completed"}}]
            text = json.dumps(choices[index])
        elif purpose == "summary":
            text = f"{scenario} Checkpoint {handoff}; retained update for protocol validation."
        else:
            text = json.dumps({"goal": {"objective": "Protocol test", "success_criteria": ["Complete current checkpoint"],
                                        "constraints": [], "preferences": []},
                               "world": {"facts": [f"{scenario} Checkpoint {handoff}"], "beliefs": [], "assumptions": []},
                               "frontier": {"current_focus": "Current checkpoint", "information_needs": [], "next_action": "Use allowed operations"}})
        if self.calls == self.malformed_at:
            text = "{invalid JSON"
        return Completion(text, {"purpose": purpose, "finish_reason": "stop", "input_tokens": 11,
                                 "output_tokens": 7, "source": "offline_protocol_test"})


class LongitudinalTests(unittest.TestCase):
    def test_all_eight_checkpoint_paths_preserve_the_actual_world(self):
        for scenario_id, paths in PATHS.items():
            scenario = load_json(DATA / f"{scenario_id}.json")
            world = LongitudinalEnvironment(scenario["initial_state"])
            for stage, names in zip(scenario["handoffs"], paths):
                before = deepcopy(world.settings)
                env = world.open_handoff(stage)
                for key, value in before.items():
                    self.assertEqual(env.settings[key], stage["external_state_patch"].get(key, value))
                for name in names:
                    env.apply(action(name))
                env.apply({"tool": "finish", "arguments": {"status": "completed"}})
                self.assertTrue(env.evaluate()["task_success"], (scenario_id, env.evaluate()))
                world.close_handoff(env)

    def test_failed_checkpoint_is_not_replaced_with_a_success_fixture(self):
        scenario = load_json(DATA / "release_workflow.json")
        world = LongitudinalEnvironment(scenario["initial_state"])
        first = world.open_handoff(scenario["handoffs"][0])
        first.apply({"tool": "finish", "arguments": {"status": "completed"}})
        world.close_handoff(first)
        next_env = world.open_handoff(scenario["handoffs"][1])
        self.assertFalse(next_env.settings["cache_repaired"])
        self.assertFalse(next_env.evaluate()["goal_checks"]["cache_repaired"])

    def test_compressed_handoff_cannot_read_discarded_raw_history(self):
        for condition in ("summary", "cognitive_state"):
            memory = HandoffMemory(condition, {"id": "goal", "role": "user", "content": "RAW_SENTINEL"})
            history = memory.update_input([{"id": "event", "role": "tool", "content": "OLD_EVIDENCE_SENTINEL"}])
            memory.retain(history, "compact retained status", [
                {"action": action("repair_cache"), "observation": {"accepted": True}}], 1)
            next_history = memory.update_input([{"id": "new", "role": "user", "content": "next checkpoint"}])
            serialized = json.dumps(next_history)
            self.assertNotIn("RAW_SENTINEL", serialized)
            self.assertNotIn("OLD_EVIDENCE_SENTINEL", serialized)
            self.assertIn("compact retained status", serialized)
            self.assertIn("accepted", serialized)
            self.assertFalse(hasattr(memory, "archive"))
            self.assertIsNone(memory.public_goal)

    def test_tool_format_errors_do_not_include_valid_operational_preconditions(self):
        self.assertTrue(malformed_action({"tool": "execute", "arguments": {"resource": "x"}}))
        self.assertTrue(malformed_action({"tool": "finish", "arguments": {"status": "done"}}))
        self.assertFalse(malformed_action(action("submit_archive")))

    def test_no_history_does_not_reconstruct_old_goal_revisions(self):
        goal = {"id": "original", "role": "user", "content": "original shared objective"}
        memory = HandoffMemory("no_history", goal)
        history = memory.update_input([{"id": "revision", "role": "user", "content": "private only"}])
        memory.retain(history, "private only", [], 1)
        self.assertEqual(memory.update_input([]), [goal])

    def test_duplicate_attempts_are_counted_even_when_budget_blocks_them(self):
        scenario = load_json(DATA / "release_workflow.json")
        world = LongitudinalEnvironment({**scenario["initial_state"], "cache_repaired": True,
                                         "queue_repaired": True, "test_A": True, "test_B": True,
                                         "bundle_ready": True, "audience": "private", "route": "offline"})
        env = world.open_handoff(scenario["handoffs"][3])
        env.apply(action("deliver_private_offline"))
        env.apply(action("validate_A"))
        env.apply({"tool": "finish", "arguments": {"status": "completed"}})
        self.assertEqual(env.spent, 2)
        self.assertEqual(repeated_attempts(env), 1)
        self.assertEqual(env.evaluate()["repeated_work_count"], 0)
        self.assertFalse(env.evaluate()["task_success"])

    def temp_project(self, directory):
        root = Path(directory)
        shutil.copytree(DATA, root / "datasets/exp003/longitudinal_v0.1")
        shutil.copytree(ROOT / "prompts/v0.2", root / "prompts/v0.3")
        config = load_json(ROOT / "configs/exp003_longitudinal_pilot.json")
        save_json(root / "config.json", config)
        return root

    def test_frozen_protocol_costs_and_retention_replay_without_env_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.temp_project(directory)
            client = ScriptedClient()
            summary = run_longitudinal(root, root / "config.json", root / "output", client=client)
            self.assertTrue(summary["performance_evaluation_available"])
            report = audit_run(root / "output")
            self.assertTrue(report["complete"])
            self.assertEqual(len(report["diagnostics"]), 32)
            rows = load_json(root / "output/results.json")
            self.assertTrue(all(row["metrics"]["task_success"] for row in rows))
            self.assertEqual(sum(row["token_usage"]["total_tokens"] for row in rows), client.calls * 18)
            self.assertEqual(sum(row["token_usage"]["update_tokens"] for row in rows), 16 * 18)
            self.assertFalse(load_json(root / "output/manifest.json")["dotenv_loaded"])
            with self.assertRaises(FileExistsError):
                run_longitudinal(root, root / "config.json", root / "output", client=client)

    def test_provider_error_stops_and_saves_unknown_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.temp_project(directory)
            client = ScriptedClient(fail_at=3)
            summary = run_longitudinal(root, root / "config.json", root / "output", client=client)
            manifest = load_json(root / "output/manifest.json")
            self.assertEqual(manifest["status"], "aborted_api_error")
            self.assertFalse(summary["performance_evaluation_available"])
            self.assertEqual(client.calls, 3)
            rows = load_json(root / "output/results.json")
            self.assertIsNone(rows[-1]["token_usage"]["total_tokens"])
            self.assertTrue(audit_run(root / "output")["verified"]["score_replay"])

    def test_extractor_format_failure_stops_only_that_chain_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.temp_project(directory)
            # Force a compressed condition first so the malformed first output is extraction.
            config = load_json(root / "config.json")
            import random
            for seed in range(100):
                order = list(config["conditions"])
                random.Random(seed).shuffle(order)
                if order[0] == "cognitive_state":
                    config["randomization_seed"] = seed
                    break
            save_json(root / "config.json", config)
            summary = run_longitudinal(root, root / "config.json", root / "output", client=ScriptedClient(malformed_at=1))
            self.assertTrue(summary["performance_evaluation_available"])
            rows = load_json(root / "output/results.json")
            failed_chain = [r for r in rows if r["scenario_id"] == "release_workflow" and r["condition"] == "cognitive_state"]
            self.assertEqual([r["status"] for r in failed_chain], ["error"] + ["skipped_chain_error"] * 3)
            self.assertFalse(any(r["metrics"]["task_success"] for r in failed_chain))
            self.assertFalse(any(r["execution_started"] for r in failed_chain))
            self.assertTrue(all(r["metrics"]["repeated_work_attempts"] is None for r in failed_chain))
            self.assertTrue(audit_run(root / "output")["verified"]["discarded_history_not_reintroduced"])

    def test_call_guard_also_caps_injected_clients_before_sending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.temp_project(directory)
            config = load_json(root / "config.json")
            config["max_api_calls"] = 1
            save_json(root / "config.json", config)
            client = ScriptedClient()
            summary = run_longitudinal(root, root / "config.json", root / "output", client=client)
            self.assertEqual(client.calls, 1)
            self.assertFalse(summary["performance_evaluation_available"])
            manifest = load_json(root / "output/manifest.json")
            self.assertEqual(manifest["status"], "aborted_call_limit")
            self.assertEqual(manifest["request_attempts"], 1)
            rows = load_json(root / "output/results.json")
            self.assertIsNotNone(rows[-1]["token_usage"]["total_tokens"])
            self.assertTrue(audit_run(root / "output")["verified"]["score_replay"])


if __name__ == "__main__":
    unittest.main()
