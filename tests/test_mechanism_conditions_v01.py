"""Offline controls: lossless encoding, input boundaries, and declared calls only."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location("mechanism_conditions_v01", ROOT / "experiments/exp004_mechanism/conditions.py")
c = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = c
SPEC.loader.exec_module(c)
from llm.client import Completion


def state():
    return {"goal": {"revision": "g1", "objective": "Complete current work", "requirements": [
        {"id": "r1", "text": "Complete work", "source_refs": ["u1"]}], "constraints": [], "preferences": []},
        "world": {"claims": [{"id": "cl1", "text": "Observed result", "basis": "observed", "source_refs": ["t1"]}],
                  "operations": [], "resources": []},
        "frontier": {"obligations": [], "open_questions": []}}


def interface():
    return {"version": "lifecycle-interface-v1", "catalog": {"operations": [], "resources": [], "catalog_cost": 0},
            "remaining_credits": 4, "credit_scope": "test:h1", "receipt_contract": "Public definition, not history."}


HISTORY = [{"id": "u1", "role": "user", "content": "Complete current work", "family": "hidden-family",
            "source_id": "hidden-reference", "expected_actions": ["hidden answer"]},
           {"id": "t1", "role": "tool", "content": "A current observation"}]


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, messages, *, purpose, max_output_tokens):
        self.requests.append({"messages": deepcopy(messages), "purpose": purpose, "max_output_tokens": max_output_tokens})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, tuple):
            text, finish = response
        else:
            text, finish = response, "stop"
        return Completion(text, {"source": "mock", "purpose": purpose, "finish_reason": finish,
                                 "input_tokens": 2, "output_tokens": 3})


class MechanismPreparationTests(unittest.TestCase):
    def test_lossless_order_empty_and_all_scalar_types(self):
        value = {"unicode\u2028key": {"source_refs": ["u1", "t1", "t1"], "empty": {}, "another": []},
                 "scalars": [None, False, True, 0, -5, 0.0, -0.0, 1.5, "\t\n\r\u2028\" | text"],
                 "path/": [{"[0]": "Chinese 中文"}]}
        text = c.render_state_text(value)
        restored = c.restore_state_text(text)
        self.assertEqual(c.compact(restored), c.compact(value))
        self.assertEqual(list(restored), list(value))
        self.assertIs(type(restored["scalars"][1]), bool)
        self.assertIs(type(restored["scalars"][3]), int)
        self.assertIs(type(restored["scalars"][5]), float)

    def test_lossless_rejects_omitted_reordered_or_wrong_typed_records(self):
        lines = c.render_state_text({"a": 1, "b": False}).split("\n")
        for altered in (lines[:-1], [lines[0], lines[1], lines[3], lines[2]],
                        lines + [lines[-1]], [*lines[:-1], lines[-1].replace("boolean", "integer", 1)]):
            with self.assertRaises(ValueError):
                c.restore_state_text("\n".join(altered))

    def test_public_projection_removes_metadata_and_is_idempotent(self):
        public, i = c.project_inputs(HISTORY, interface())
        self.assertFalse({"family", "source_id", "expected_actions"} & public[0].keys())
        self.assertNotIn("hidden answer", c.compact(public))
        self.assertEqual(c.project_inputs(public, i), (public, i))
        self.assertEqual(c.source_authorities(public)["mechanism:interface_contract"], "contract")
        with self.assertRaises(ValueError):
            c.project_inputs(HISTORY, {**interface(), "fixture": {"hidden": True}})
        with self.assertRaises(ValueError):
            c.project_inputs(HISTORY + [HISTORY[0]], interface())

    def test_full_is_free_and_full_planner_retains_entire_history(self):
        free = FakeClient([])
        result = c.prepare("full_context", HISTORY, interface(), {}, free)
        self.assertTrue(result.valid)
        self.assertEqual(free.requests, [])
        self.assertEqual(json.loads(result.representation)[0]["content"], HISTORY[0]["content"])
        client = FakeClient(["A planning aid"])
        planner = c.prepare("full_planner", HISTORY, interface(), {}, client)
        self.assertEqual(client.requests[0]["max_output_tokens"], 1024)
        self.assertEqual(json.loads(planner.representation)["history"], c.project_inputs(HISTORY, interface())[0])
        self.assertEqual(planner.intermediate, "A planning aid")

    def test_strong_summary_two_stage_keeps_original_input_and_limits(self):
        client = FakeClient(["An untrusted draft", "A full final summary"])
        result = c.prepare("summary_s2", HISTORY, interface(), {}, client)
        self.assertTrue(result.valid)
        self.assertEqual([r["max_output_tokens"] for r in client.requests], [1024, 4096])
        first, second = [json.loads(r["messages"][1]["content"]) for r in client.requests]
        self.assertEqual(first["history"], second["history"])
        self.assertEqual(second["untrusted_information_organizer"], "An untrusted draft")
        self.assertNotIn("untrusted_information_organizer", second["source_authority"])

    def test_intermediate_failure_is_not_retried_or_passed_to_final(self):
        client = FakeClient([("unfinished draft", "length")])
        result = c.prepare("summary_s2", HISTORY, interface(), {}, client)
        self.assertFalse(result.valid)
        self.assertEqual(len(client.requests), 1)

    def test_schema_repair_only_one_then_shared_failure(self):
        client = FakeClient(["{}", "{}"])
        source = c.prepare("cs1", HISTORY, interface(), {}, client)
        self.assertFalse(source.valid)
        self.assertEqual(len(client.requests), 2)
        self.assertEqual([r["purpose"] for r in client.requests], ["cs1:extract", "cs1:repair"])
        paired = c.prepare("cs_text", HISTORY, interface(), {}, FakeClient([]), shared_state=source.to_dict())
        self.assertFalse(paired.valid)
        self.assertIsNone(paired.representation)
        self.assertEqual(paired.calls, [])
        self.assertEqual(paired.deployment_calls(), source.calls)

    def test_semantic_error_remains_valid_not_repaired(self):
        wrong = state()
        wrong["world"]["claims"][0]["text"] = "An unsupported factual assertion"
        client = FakeClient([c.compact(wrong)])
        result = c.prepare("cs1", HISTORY, interface(), {}, client)
        self.assertTrue(result.valid)
        self.assertEqual(len(client.requests), 1)
        self.assertIn("unsupported factual", result.representation)

    def test_missing_source_reference_triggers_encoding_repair(self):
        wrong = state()
        wrong["world"]["claims"][0]["source_refs"] = ["not_available"]
        client = FakeClient([c.compact(wrong), c.compact(state())])
        result = c.prepare("cs1", HISTORY, interface(), {}, client)
        self.assertTrue(result.valid)
        self.assertEqual([d["valid"] for d in result.diagnostics], [False, True])

    def test_shared_text_is_same_information_no_cap_and_restorable(self):
        source = c.prepare("cs1", HISTORY, interface(), {}, FakeClient([c.compact(state())]))
        target = c.prepare("cs_text", HISTORY, interface(), {}, FakeClient([]), shared_state=source.to_dict())
        self.assertTrue(target.valid)
        self.assertEqual(c.compact(c.restore_state_text(target.representation)), source.representation)
        self.assertEqual(target.calls, [])
        self.assertEqual(target.deployment_calls(), source.calls)
        self.assertEqual(c.Preparation.from_dict(target.to_dict()).to_dict(), target.to_dict())
        changed = deepcopy(HISTORY)
        changed[0]["content"] = "A different public goal"
        with self.assertRaises(ValueError):
            c.prepare("cs_text", changed, interface(), {}, FakeClient([]), shared_state=source)

    def test_output_length_does_not_truncate_and_has_one_repair(self):
        client = FakeClient(["汉" * 3, "汉" * 3])
        result = c.prepare("summary_s1", HISTORY, interface(), {"representation_budget": 8}, client)
        self.assertFalse(result.valid)
        self.assertEqual(len(client.requests), 2)
        self.assertIsNone(result.representation)

    def test_api_failure_propagates_without_retry(self):
        client = FakeClient([RuntimeError("sanitized fixture error")])
        with self.assertRaises(RuntimeError):
            c.prepare("summary_s1", HISTORY, interface(), {}, client)
        self.assertEqual(len(client.requests), 1)

    def test_common_semantics_exact_suffix_and_same_executor_string_wrapper(self):
        common = (c.PROMPTS / "semantic_common.txt").read_text(encoding="utf-8").strip()
        for name in c.PROMPT_NAMES:
            self.assertTrue(c.load_prompt(name).endswith("\n\n" + common))
        for rep in ("Full text", "Summary", c.compact(state()), c.render_state_text(state())):
            wrapper = c.executor_context(rep, interface())
            self.assertIsInstance(wrapper["retained_context"], str)
            self.assertEqual(set(wrapper), {"retained_context", "public_interface"})


if __name__ == "__main__":
    unittest.main()
