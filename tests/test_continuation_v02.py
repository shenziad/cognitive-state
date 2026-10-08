"""Content gates for the frozen v0.2 counterfactual continuation dataset."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_continuation_v02 import FINISH, audit_cases, build_cases, execute, observe, replay
from evaluation.continuation import ContinuationEnvironment
from utils.io import load_json

DATA = ROOT / "datasets/exp001/continuation_v0.2"


class ContinuationV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = build_cases()
        cls.by_id = {case["instance_id"]: case for case in cls.cases}

    def test_14_accepted_paths_12_swaps_and_claimed_recovery_costs(self):
        audit = audit_cases(self.cases)
        self.assertEqual((audit["tasks"], audit["pairs"], audit["controls"]), (14, 6, 2))
        self.assertTrue(all(row["accepted_success"] for row in audit["instances"]))
        self.assertTrue(all(not row["swapped_success"] for row in audit["swaps"]))

    def test_frozen_files_match_reproducible_builder_and_manifest(self):
        manifest = load_json(DATA / "manifest.json")
        self.assertEqual({row["instance_id"] for row in manifest["instances"]}, set(self.by_id))
        for row in manifest["instances"]:
            case = self.by_id[row["instance_id"]]
            for kind in ("task", "environment", "reference", "review"):
                self.assertEqual(load_json(DATA / row[kind]), case[kind])

    def test_pairs_share_tool_definitions_recovery_context_and_noncheckpoint_history(self):
        for pair in ("goal", "belief", "assumption", "completed", "inflight", "information"):
            first = self.by_id[f"cont2_{pair}_a"]
            second = self.by_id[f"cont2_{pair}_b"]
            self.assertEqual(first["task"]["recovery_context"], second["task"]["recovery_context"])
            for case in (first, second):
                self.assertNotIn(next(m["content"] for m in case["task"]["history"] if m["id"] == "h04"),
                                 case["task"]["recovery_context"])
            strip_checkpoint = lambda case: [m for m in case["task"]["history"] if m["id"] != "h04"]
            self.assertEqual(strip_checkpoint(first), strip_checkpoint(second))
            catalogs = [ContinuationEnvironment(case["environment"]).catalog() for case in (first, second)]
            self.assertEqual(catalogs[0], catalogs[1])

    def test_evidence_position_and_length_variation_is_real(self):
        positions = set()
        lengths = set()
        for case in self.cases:
            if case["control"]:
                continue
            history = case["task"]["history"]
            checkpoint = next(i for i, m in enumerate(history) if m["id"] == "h04")
            noise = [i for i, m in enumerate(history) if m["id"].startswith("d")]
            if checkpoint < min(noise):
                position = "early"
            elif checkpoint > max(noise):
                position = "late"
            else:
                position = "middle"
            self.assertEqual(position, case["critical_evidence_position"])
            positions.add(position)
            lengths.add(len(noise))
        self.assertEqual(positions, {"early", "middle", "late"})
        self.assertEqual(len(lengths), 6)

    def test_reference_names_have_public_sources_and_unread_values_are_excluded(self):
        for case in self.cases:
            history = {m["id"]: m["content"] for m in case["task"]["history"]}
            for ids in case["reference"]["source_message_ids"].values():
                self.assertTrue(set(ids) <= history.keys())
            self.assertEqual(case["reference"]["review"]["status"], "pending")
        first = json.dumps(self.by_id["cont2_information_a"]["reference"]["state"])
        second = json.dumps(self.by_id["cont2_information_b"]["reference"]["state"])
        self.assertIn("R29", first)
        self.assertNotIn("P63", first)
        self.assertIn("P63", second)
        self.assertNotIn("R29", second)

    def test_progress_ablation_terms_only_match_real_current_progress_facts(self):
        for case in self.cases:
            facts = case["reference"]["state"]["world"]["facts"]
            for term in case["task"]["ablation_progress_terms"]:
                self.assertTrue(any(term.casefold() in fact.casefold() for fact in facts),
                                (case["instance_id"], term))
        self.assertEqual(self.by_id["cont2_completed_a"]["task"]["ablation_progress_terms"],
                         ["calibration completed", "calibration has not run"])

    def test_wrong_inflight_probe_is_not_a_free_history_recovery(self):
        case = self.by_id["cont2_inflight_a"]
        env = ContinuationEnvironment(case["environment"])
        error = env.apply(execute("consume_U"))
        self.assertEqual(error["error"], "Operational precondition not met")
        self.assertEqual(env.spent, 2)
        env.apply(execute("consume_Z"))
        env.apply(deepcopy(FINISH))
        self.assertFalse(env.evaluate()["task_success"])
        self.assertEqual(env.spent, 4)

    def test_no_history_control_has_no_cutoff_evidence_and_recoverable_control_works(self):
        complete = self.by_id["cont2_control_completed_a"]
        self.assertNotIn("both validated", complete["task"]["recovery_context"].lower())
        self.assertNotIn("only finish remains", complete["task"]["recovery_context"].lower())
        recoverable = self.by_id["cont2_control_recoverable_a"]
        self.assertNotIn("open_lane", recoverable["task"]["recovery_context"])
        self.assertTrue(replay(recoverable["environment"],
                               recoverable["review"]["no_history_recovery_example"])["task_success"])


if __name__ == "__main__":
    unittest.main()
