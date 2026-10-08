import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from llm.client import Completion
from utils.io import load_json, save_json
from state.v03 import compact

spec = importlib.util.spec_from_file_location("cycle3_runner", ROOT / "scripts/run_v03_cycle.py")
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


class Fake:
    def __init__(self, fail=False): self.fail, self.counter = fail, 0
    def complete(self, messages, *, purpose):
        self.counter += 1
        if self.fail: raise RuntimeError("Test transport failure; usage unknown")
        if purpose == "executor":
            content = compact({"tool": "finish", "arguments": {"status": "completed"}})
        else:
            payload = json.loads(messages[1]["content"])
            source = next(e["content"] for e in payload["history"] if e["id"] == "p3")
            content = compact({"goal": {"revision": "g1", "objective": "Finish the observed completed checkpoint", "requirements": [
                {"id": "r1", "text": "Apply the requested setting and validate", "source_refs": ["p2"]}], "constraints": [], "preferences": []},
                "world": {"claims": [{"id": "c1", "text": source, "basis": "observed", "source_refs": ["p3"]}], "operations": [], "resources": []},
                "frontier": {"obligations": [], "open_questions": []}})
        return Completion(content, {"purpose": purpose, "source": "mock", "finish_reason": "stop", "input_tokens": 1, "output_tokens": 1})


class Cycle3RunnerTests(unittest.TestCase):
    def execute(self, fail=False):
        with tempfile.TemporaryDirectory(prefix="cycle3_test_", dir=ROOT / "results/raw") as directory:
            p = Path(directory).resolve()
            self.assertTrue(p.is_relative_to((ROOT / "results/raw").resolve()))
            data = load_json(ROOT / "datasets/cycle3_v03/preflight.json")
            data["cases"] = [c for c in data["cases"] if c["family"] == "already_done"]
            save_json(p / "input.json", data)
            config = load_json(ROOT / "configs/cycle3_preflight_v03.json")
            config["dataset"] = (p / "input.json").relative_to(ROOT).as_posix()
            save_json(p / "config.json", config)
            client = Fake(fail)
            runner.run(ROOT, p / "config.json", p / "run", client=client)
            return load_json(p / "run/summary.json"), load_json(p / "run/manifest.json"), load_json(p / "run/call_ledger.json"), load_json(p / "run/results.json")

    def test_complete_artifact_grid_and_no_mock_gate(self):
        summary, manifest, ledger, rows = self.execute()
        self.assertEqual(manifest["evidence_type"], "mock_protocol_validation")
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(r["success"] for r in rows))
        self.assertFalse(summary["gate"]["automatic_pass"])
        self.assertEqual(len(ledger), 12)
        self.assertEqual(summary["actual_usage"]["total_tokens"], 24)

    def test_provider_error_stops_and_preserves_unknown_usage(self):
        summary, manifest, ledger, rows = self.execute(True)
        self.assertEqual(manifest["status"], "aborted_api_error")
        self.assertFalse(summary["complete"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(ledger), 1)
        self.assertIsNone(summary["actual_usage"]["total_tokens"])

    def test_missing_gate_refuses_comparison_before_output_or_env(self):
        with tempfile.TemporaryDirectory(prefix="cycle3_gate_", dir=ROOT / "results/raw") as directory:
            p = Path(directory).resolve()
            self.assertTrue(p.is_relative_to((ROOT / "results/raw").resolve()))
            with self.assertRaises(ValueError):
                runner.run(ROOT, ROOT / "configs/cycle3_regression_v03.json", p / "run", client=Fake())
            self.assertFalse((p / "run").exists())


if __name__ == "__main__": unittest.main()
