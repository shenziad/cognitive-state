"""Research-critical checks: boundaries, rubric behavior, failed runs and artifacts."""

import io
import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluation.controlled import ControlledEnvironment
from evaluation.analysis import analyze_run
from evaluation.runner import run_experiment, load_dataset, validate_config, attach_reductions
from llm.client import ChatCompletionsClient, OpenAISDKClient, Completion
from llm.environment import load_project_env
from llm.mock import MockClient
from state.representation import CognitiveState
from utils.io import load_json, parse_json, save_json

DATA = ROOT / "datasets/exp001/v0.1"
CONFIG = ROOT / "experiments/exp001_context_equivalence/config.json"


def action(env, tool, **arguments):
    return env.apply({"tool": tool, "arguments": arguments})


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_json(DATA / "environments/pilot02_api_endpoint.json")
        self.env = ControlledEnvironment(self.fixture)

    def solve(self, reverse=False):
        action(self.env, "read_file", path="docs/runbook.json")
        changes = list(self.fixture["rubric"]["target_settings"].items())
        for key, value in reversed(changes) if reverse else changes:
            action(self.env, "set_config", key=key, value=value)
        action(self.env, "run_check")
        action(self.env, "finish", status="completed")

    def test_alternative_valid_action_order_is_accepted(self):
        self.solve(reverse=True)
        self.assertTrue(self.env.evaluate()["task_success"])

    def test_preserved_constraint_violation_cannot_be_erased_by_restore(self):
        action(self.env, "set_config", key="region", value="us")
        action(self.env, "set_config", key="region", value="eu")
        self.solve()
        score = self.env.evaluate()
        self.assertEqual(score["final_goal_completion"], 1.0)
        self.assertFalse(score["task_success"])
        self.assertLess(score["tool_usage_correctness"], 1.0)

    def test_completion_without_verification_fails(self):
        for key, value in self.fixture["rubric"]["target_settings"].items():
            action(self.env, "set_config", key=key, value=value)
        action(self.env, "finish", status="completed")
        self.assertFalse(self.env.evaluate()["task_success"])

    def test_edit_invalidates_previous_check(self):
        action(self.env, "read_file", path="docs/runbook.json")
        for key, value in self.fixture["rubric"]["target_settings"].items():
            action(self.env, "set_config", key=key, value=value)
        action(self.env, "run_check")
        action(self.env, "set_config", key="api_version", value="v1")
        action(self.env, "set_config", key="api_version", value="v2")
        action(self.env, "finish", status="completed")
        self.assertFalse(self.env.evaluate()["task_success"])

    def test_bad_arguments_get_observations_without_mutation(self):
        initial = deepcopy(self.env.settings)
        for bad in ([], {"tool": "set_config", "arguments": []},
                    {"tool": "read_file", "arguments": {"path": ["private"]}},
                    {"tool": "migrate_database", "arguments": {}},
                    {"tool": "set_config", "arguments": {"key": "nonexistent", "value": 1}}):
            self.assertIn("error", self.env.apply(bad))
        self.assertEqual(initial, self.env.settings)

    def test_fresh_environment_is_isolated(self):
        self.solve()
        fresh = ControlledEnvironment(self.fixture)
        self.assertEqual(fresh.settings, self.fixture["files"]["config/service.json"])
        self.assertFalse(fresh.finished)


class BoundaryTests(unittest.TestCase):
    def test_references_have_only_pre_cutoff_source_ids(self):
        _, tasks, _ = load_dataset(ROOT, load_json(CONFIG))
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            CognitiveState.from_dict(task["reference"]["state"])
            self.assertEqual(task["reference"]["review"]["status"], "pending")

    def test_invalid_state_types_and_nonfinite_json_are_rejected(self):
        state = load_json(DATA / "references/pilot01_jwt_units.json")["state"]
        state["world"]["beliefs"][0]["confidence"] = True
        with self.assertRaises(ValueError):
            CognitiveState.from_dict(state)
        for text in ('{"x":NaN}', '{"x":1,"x":2}'):
            with self.assertRaises(ValueError):
                parse_json(text)

    def test_api_config_requires_deliberate_model_and_counter_selection(self):
        with self.assertRaises(ValueError):
            validate_config(load_json(ROOT / "configs/exp001_api.example.json"))


class PipelineTests(unittest.TestCase):
    def test_provider_failure_stops_run_and_publishes_no_performance_score(self):
        class FailedClient:
            def complete(self, messages, *, purpose):
                raise RuntimeError("SDK APIStatusError; HTTP=402; category=insufficient_balance")

        with tempfile.TemporaryDirectory() as tmp:
            config = load_json(ROOT / "configs/exp001_siliconflow_smoke.json")
            path = Path(tmp) / "config.json"
            save_json(path, config)
            with patch("evaluation.runner.OpenAISDKClient", return_value=FailedClient()), patch("evaluation.runner.load_project_env", return_value=False):
                summary = run_experiment(ROOT, path, Path(tmp) / "run")
            self.assertTrue(summary["incomplete_run"])
            self.assertEqual(summary["saved_runs"], 1)
            self.assertFalse(summary["performance_evaluation_available"])
            self.assertIsNone(next(iter(summary["conditions"].values()))["task_success_rate"])
            self.assertEqual(load_json(Path(tmp) / "run/manifest.json")["status"], "aborted_api_error")

    def test_cost_reductions_include_extraction_and_exclude_reference_authoring(self):
        rows = []
        for condition, first, total in (("full_context", 100, 200), ("summary", 50, 240), ("reference_state", 40, 80)):
            rows.append({"instance_id": "test", "repetition": 0, "condition": condition, "status": "completed",
                         "metrics": {}, "token_usage": {"initial_executor_input_tokens": first, "total_tokens": total}})
        attach_reductions(rows)
        self.assertEqual(rows[1]["metrics"]["token_reduction"], 0.5)
        self.assertAlmostEqual(rows[1]["metrics"]["end_to_end_token_reduction"], -0.2)
        self.assertIsNone(rows[2]["metrics"]["end_to_end_token_reduction"])

    def test_over_budget_representations_fail_without_full_context_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_json(CONFIG)
            config.update(instance_ids=["pilot01_jwt_units"], representation_budget=10)
            path = Path(tmp) / "config.json"
            save_json(path, config)
            run_experiment(ROOT, path, Path(tmp) / "run")
            for row in load_json(Path(tmp) / "run/results.json"):
                if row["condition"] == "full_context":
                    self.assertTrue(row["metrics"]["task_success"])
                else:
                    self.assertEqual(row["status"], "error")
                    self.assertFalse(row["metrics"]["task_success"])
                    self.assertEqual(row["error"]["stage"], "representation")

    def test_full_pilot_outputs_and_input_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            summary = run_experiment(ROOT, CONFIG, output)
            results = load_json(output / "results.json")
            self.assertEqual(len(results), 48)
            self.assertTrue(all(row["metrics"]["task_success"] for row in results))
            self.assertEqual(summary["evidence_type"], "mock_protocol_validation")
            self.assertTrue(all(row["metrics"]["token_reduction"] is None for row in results))
            for row in results:
                artifact = load_json(output / row["artifacts"][0])
                for call in artifact["calls"]:
                    if call["metadata"]["purpose"] != "executor":
                        payload = json.loads(call["messages"][1]["content"])
                        self.assertEqual(set(payload), {"history", "representation_budget", "budget_counter"})
                        self.assertNotIn("target_settings", call["messages"][1]["content"])
                        self.assertNotIn("recommended_settings", call["messages"][1]["content"])
                    else:
                        first = json.loads(call["messages"][1]["content"])
                        self.assertEqual(set(first), {"instruction", "context", "tools"})
                self.assertEqual(artifact["result"], row)
            self.assertEqual(load_json(output / "config.json"), load_json(CONFIG))
            self.assertEqual(load_json(output / "manifest.json")["status"], "completed")
            with self.assertRaises(FileExistsError):
                run_experiment(ROOT, CONFIG, output)

    def test_invalid_extraction_is_saved_and_counted_as_failure(self):
        class BadExtractor(MockClient):
            def complete(self, messages, *, purpose):
                if purpose == "cognitive_state":
                    return Completion('{"invalid":true}', {
                        "purpose": purpose, "finish_reason": "stop", "input_tokens": 100, "output_tokens": 10})
                return super().complete(messages, purpose=purpose)

        with tempfile.TemporaryDirectory() as tmp:
            config = load_json(CONFIG)
            config["instance_ids"] = ["pilot01_jwt_units"]
            config_path = Path(tmp) / "config.json"
            save_json(config_path, config)
            with patch("evaluation.runner.MockClient", return_value=BadExtractor()):
                summary = run_experiment(ROOT, config_path, Path(tmp) / "run")
            row = next(row for row in load_json(Path(tmp) / "run/results.json") if row["condition"] == "cognitive_state")
            self.assertFalse(row["metrics"]["task_success"])
            self.assertEqual(row["token_usage"]["extraction_tokens"], 110)
            self.assertEqual(summary["conditions"]["cognitive_state"]["assigned_runs"], 1)
            self.assertEqual(summary["conditions"]["cognitive_state"]["errors"], 1)


class AdapterTests(unittest.TestCase):
    def test_dotenv_loads_without_overwriting_existing_environment(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"CS_TEST_ENV": "existing"}):
            root = Path(tmp)
            (root / ".env").write_text('CS_TEST_ENV="candidate"\nCS_NEW_TEST_ENV="placeholder"\n', encoding="utf-8")
            self.assertTrue(load_project_env(root))
            self.assertEqual(os.environ["CS_TEST_ENV"], "existing")
            self.assertEqual(os.environ["CS_NEW_TEST_ENV"], "placeholder")

    def test_sdk_uses_configured_base_url_model_and_thinking_controls(self):
        config = load_json(ROOT / "configs/exp001_siliconflow.json")
        response = SimpleNamespace(id="test", model=config["model"], system_fingerprint=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")],
            usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens": 11, "completion_tokens": 3}))
        with patch.dict(os.environ, {config["api_key_env"]: "test-placeholder"}), patch("openai.OpenAI") as sdk:
            sdk.return_value.chat.completions.create.return_value = response
            client = OpenAISDKClient(config)
            result = client.complete([{"role": "user", "content": "test"}], purpose="executor")
            self.assertEqual(sdk.call_args.kwargs["base_url"], "https://api.siliconflow.cn/v1")
            self.assertEqual(sdk.call_args.kwargs["max_retries"], 0)
            sent = sdk.return_value.chat.completions.create.call_args.kwargs
            self.assertEqual(sent["model"], "deepseek-ai/DeepSeek-V4-Flash")
            self.assertEqual(sent["extra_body"], {"enable_thinking": False})
            self.assertEqual(sent["max_tokens"], 2048)
            self.assertEqual(result.metadata["input_tokens"], 11)
            self.assertNotIn("test-placeholder", json.dumps(result.metadata))

    def test_sdk_error_body_is_not_persisted(self):
        import httpx
        from openai import AuthenticationError

        config = load_json(ROOT / "configs/exp001_siliconflow.json")
        failure = AuthenticationError("SECRET-ECHO", response=httpx.Response(
            401, request=httpx.Request("POST", config["endpoint"])), body={"echo": "SECRET-ECHO"})
        with patch.dict(os.environ, {config["api_key_env"]: "test-placeholder"}), patch("openai.OpenAI") as sdk:
            sdk.return_value.chat.completions.create.side_effect = failure
            with self.assertRaises(RuntimeError) as raised:
                OpenAISDKClient(config).complete([], purpose="executor")
            self.assertNotIn("SECRET", str(raised.exception))
            self.assertIn("401", str(raised.exception))

    def test_http_adapter_and_call_limit_without_network(self):
        config = load_json(CONFIG)
        config.update(endpoint="https://example.invalid/v1/chat/completions", max_api_calls=1)
        response = {"id": "test", "model": "test", "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 2}}
        with patch.dict(os.environ, {"LLM_API_KEY": "test-placeholder"}):
            client = ChatCompletionsClient(config)
            with patch("llm.client.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as http:
                result = client.complete([{"role": "user", "content": "test"}], purpose="executor")
                payload = json.loads(http.call_args.args[0].data)
                self.assertEqual(payload["max_completion_tokens"], 2048)
                self.assertEqual(result.metadata["input_tokens"], 7)
                self.assertNotIn("test-placeholder", json.dumps(result.metadata))
            with self.assertRaises(RuntimeError):
                client.complete([], purpose="executor")


class AnalysisTests(unittest.TestCase):
    def test_incomplete_run_does_not_convert_provider_errors_to_performance(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            config = load_json(ROOT / "configs/exp001_siliconflow_smoke.json")
            save_json(run / "config.json", config)
            save_json(run / "manifest.json", {"status": "aborted_api_error", "assigned_runs": 8})
            save_json(run / "results.json", [{"condition": "full_context", "instance_id": "test", "error": {
                "stage": "executor", "type": "RuntimeError", "message": "HTTP=402"},
                "representation_size": 100, "artifacts": ["instances/test.json"],
                "metrics": {"task_success": False, "final_goal_completion": 0.66}}])
            save_json(run / "instances/test.json", {"calls": []})
            report = analyze_run(run, Path(tmp) / "analysis")
            self.assertFalse(report["performance_evaluation_available"])
            self.assertEqual(report["reported_api_responses"], 0)
            self.assertTrue(all(stats["task_success_rate"] is None for stats in report["conditions"].values()))
            self.assertEqual(report["hypotheses_confirmed"], [])

    def test_mock_analysis_stays_labeled_as_protocol_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_json(CONFIG)
            config["instance_ids"] = ["pilot01_jwt_units"]
            path = Path(tmp) / "config.json"
            save_json(path, config)
            run_experiment(ROOT, path, Path(tmp) / "run")
            report = analyze_run(Path(tmp) / "run", Path(tmp) / "analysis")
            self.assertFalse(report["performance_evaluation_available"])
            self.assertEqual(report["evidence_type"], "mock_protocol_validation")


if __name__ == "__main__":
    unittest.main()
