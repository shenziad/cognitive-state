"""Offline protocol tests; oracle clients here are NOT research baselines."""

from collections import deque
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from state.v031 import validate_state, retained_event, source_authorities, ExtractorV031, compact, SCHEMA, shape
from evaluation.lifecycle import LifecycleEnvironment
from evaluation.cycle4 import run, available_input, executor_context, execution_status, RecordingClient
from evaluation.cycle4_audit import audit, review_packet, make_gate, validate_review
from llm.client import Completion
from utils.io import load_json, save_json
import importlib.util


def state(history):
    source = next(e["id"] for e in history if e["role"] == "user")
    return {"goal": {"revision": "g1", "objective": "offline encoding fixture", "requirements": [
        {"id": "r1", "text": "offline fixture", "source_refs": [source]}], "constraints": [], "preferences": []},
        "world": {"claims": [], "operations": [], "resources": []}, "frontier": {"obligations": [], "open_questions": []}}


def solution(fixture):
    """Privileged BFS for offline fixture solvability ONLY; never sent to models."""
    actions = ([{"tool": "observe", "arguments": {"resource": k}} for k in fixture["observations"]] +
               [{"tool": "execute", "arguments": {"operation": k}} for k in fixture["operations"]])
    finish = {"tool": "finish", "arguments": {"status": "completed"}}
    queue = deque([[]]); seen = set()
    while queue:
        path = queue.popleft(); env = LifecycleEnvironment(fixture)
        for a in path:
            env.apply(a)
        if any(t["policy_violations"] or not t["valid"] for t in env.trace):
            continue
        key = compact([env.settings, env.spent])
        if key in seen:
            continue
        seen.add(key)
        if all(env.evaluate()["goal_checks"].values()):
            return path + [finish]
        if len(path) < 5:
            queue.extend(path + [a] for a in actions)
    raise AssertionError("Offline fixture has no budget-valid solution")


class OfflineOracle:
    """Tests input plumbing/world carry with privileged fixture actions, not ability."""
    def __init__(self, data):
        self.cases = {c["instance_id"]: c for c in data.get("cases", [])}
        self.scenarios = {s["scenario_id"]: s for s in data.get("scenarios", [])}
        self.worlds = {}; self.counter = 0

    def complete(self, messages, *, purpose):
        self.counter += 1
        payload = json.loads(messages[1]["content"])
        if purpose != "executor":
            history = payload["history"]
            if purpose.startswith("cs_v031"):
                text = compact(state(history))
            elif purpose.startswith("summary"):
                text = "Offline placeholder. No claim of successful compression."
            else:
                text = compact({"goal": {"objective": "offline fixture", "success_criteria": ["offline fixture"], "constraints": [], "preferences": []},
                    "world": {"facts": [], "beliefs": [], "assumptions": []},
                    "frontier": {"current_focus": "offline fixture", "information_needs": [], "next_action": "offline fixture"}})
        else:
            context = payload["context"]
            assert isinstance(context, dict) and not isinstance(context["public_interface"], str)
            scope = context["public_interface"]["credit_scope"]
            ident, h = scope.rsplit(":checkpoint_", 1); h = int(h)
            if len(messages) == 2:
                if self.scenarios:
                    s = self.scenarios[ident]; stage = s["handoffs"][h - 1]
                    if h == 1:
                        self.worlds[ident] = deepcopy(s["initial_state"])
                    self.worlds[ident].update(stage["external_state_patch"])
                    fixture = deepcopy(stage["environment"]); fixture["initial_state"] = deepcopy(self.worlds[ident])
                else:
                    fixture = self.cases[ident]["environment"]
                self.actions = solution(fixture); self.env = LifecycleEnvironment(fixture); self.index = 0
            action = self.actions[self.index]; self.index += 1
            self.env.apply(action)
            if self.scenarios:
                self.worlds[ident] = deepcopy(self.env.settings)
            text = compact(action)
        return Completion(text, {"purpose": purpose, "source": "mock", "finish_reason": "stop", "input_tokens": 0, "output_tokens": 0})


class Cycle4Tests(unittest.TestCase):
    def setUp(self):
        self.history = [{"id": "u1", "role": "user", "content": "Complete job-17"},
                        {"id": "e1", "role": "tool", "content": "job-17 accepted"}]

    def test_all_normative_examples_shape_and_references(self):
        for case in load_json(ROOT / "docs/examples/cognitive_state_v0.3.1/conformance_cases.json")["cases"]:
            history = [{"id": "u1", "role": "user", "content": case["user_goal"]}] + case["public_events"]
            s = state(history); s["world"]["operations"] = case["expected_operations"]
            validate_state(s, history)

    def test_job_cannot_use_submission_completed_enum(self):
        s = state(self.history)
        s["world"]["operations"] = [{"id": "j1", "kind": "job", "entity_id": "job-17", "operation": "submit_job", "phase": "completed", "source_refs": ["e1"]}]
        with self.assertRaises(ValueError): validate_state(s, self.history)

    def test_unsupported_but_well_encoded_success_not_repaired(self):
        s = state(self.history)
        s["world"]["operations"] = [{"id": "j1", "kind": "job", "entity_id": "job-17", "operation": "submit_job", "phase": "succeeded", "source_refs": ["e1"]}]
        self.assertEqual(validate_state(s, self.history), s)

    def test_bad_plan_and_source_class_are_diagnostics_not_encoding_errors(self):
        s = state(self.history); s["goal"]["requirements"][0]["source_refs"] = ["e1"]
        s["frontier"]["obligations"] = [{"id": "o1", "text": "x", "requirement_ref": "r1"}]
        s["frontier"]["candidate_action"] = {"tool": "execute", "arguments": {"operation": "nonexistent"}, "requires": [], "obligation_ref": "o1", "goal_revision": "stale", "known_cost": 999}
        validate_state(s, self.history)

    def test_inherited_contract_never_becomes_user_authority(self):
        h = self.history + [{"id": "c1", "role": "tool", "source_type": "public_tool_contract", "content": "contract"}]
        for condition in ["summary", "cs_v02", "cs_v031"]:
            retained = retained_event('Retained c1 and e1; no source contents.', condition, h, 1)
            self.assertEqual(source_authorities([retained])["c1"], "contract")
            self.assertEqual(source_authorities([retained])["e1"], "tool")
            self.assertNotIn("u1", retained["source_authority"])

    def test_dangling_active_ref_is_rejected(self):
        s = state(self.history); s["frontier"]["obligations"] = [{"id": "o1", "text": "x", "requirement_ref": "absent"}]
        with self.assertRaises(ValueError): validate_state(s, self.history)

    def test_repair_is_once_and_retains_original(self):
        class Bad:
            def complete(self, messages, *, purpose):
                return Completion('not json', {"purpose": purpose, "finish_reason": "stop"})
        calls = []; rep, attempts = ExtractorV031(Bad()).extract(self.history, {}, "cs_v031", "prompt", calls)
        self.assertIsNone(rep); self.assertEqual(len(attempts), 2)
        self.assertEqual(calls[1]["messages"][2]["content"], 'not json')

    def test_public_interface_does_not_expose_hidden_world_or_observation(self):
        f = deepcopy(load_json(ROOT / "datasets/cycle4_v1/preflight.json")["cases"][2]["environment"])
        before = LifecycleEnvironment(f).public_interface('x')
        f["initial_state"]["private_secret"] = "HIDDEN_STATE"
        f["rubric"]["target_state"]["private_secret"] = "HIDDEN_RUBRIC"
        f["observations"]["current/submission"]["observation"] = {"private": "UNREAD_VALUE"}
        self.assertEqual(before, LifecycleEnvironment(f).public_interface('x'))

    def test_all_preflight_offline_solutions(self):
        for c in load_json(ROOT / "datasets/cycle4_v1/preflight.json")["cases"]:
            env = LifecycleEnvironment(c["environment"])
            for a in c["offline_solution"]: env.apply(a)
            self.assertTrue(env.evaluate()["task_success"], c["instance_id"])

    def test_operational_precondition_failure_does_not_become_format_error(self):
        f=deepcopy(load_json(ROOT/'datasets/cycle4_v1/preflight.json')['cases'][0]['environment'])
        f['initial_state']['submitted']=False
        env=LifecycleEnvironment(f)
        env.apply({'tool':'execute','arguments':{'operation':'consume_job'}})
        self.assertEqual(env.trace[-1]['observation']['error'],'Operational precondition not met')
        self.assertEqual(execution_status(env),'step_limit')
        env.apply({'tool':'execute','operation':'consume_job'})
        self.assertEqual(execution_status(env),'executor_error')

    def test_builder_reproducibility_and_shared_semantic_prompt(self):
        spec = importlib.util.spec_from_file_location('build_cycle4',ROOT/'scripts/build_cycle4.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        parent=(ROOT/'results/raw').resolve();parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='cycle4_build_',dir=parent) as temp:
            base=Path(temp).resolve();self.assertTrue(base.is_relative_to(parent))
            module.build(base/'data')
            for p in (ROOT/'datasets/cycle4_v1').glob('*.json'):
                self.assertEqual(load_json(p),load_json(base/'data'/p.name))
        common=(ROOT/'prompts/cycle4/lifecycle_common.txt').read_text(encoding='utf-8')
        for name in ['executor','summary','cs_v02','cs_v031']:
            self.assertTrue((ROOT/f'prompts/cycle4/{name}.txt').read_text(encoding='utf-8').endswith(common))

    def test_comparison_adapter_preserves_old_world_budget_and_rubric(self):
        old=load_json(ROOT/'datasets/cycle3_v03r2/regression.json')
        new=load_json(ROOT/'datasets/cycle4_v1/regression.json')
        for a,b in zip(old['cases'],new['cases']):
            for k in ['initial_state','budget','rubric','observations']:
                self.assertEqual(a['environment'][k],b['environment'][k])
            for name,definition in a['environment']['operations'].items():
                for k,v in definition.items(): self.assertEqual(v,b['environment']['operations'][name][k])

    def test_20_frozen_gate_cases_and_behavior_not_a_veto(self):
        spec=importlib.util.spec_from_file_location('protocol_check',ROOT/'scripts/check_cycle4_protocol.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.verify()['gate_decision_cases_checked'],20)

    def test_representation_failure_skips_chain_without_restoring_history(self):
        class FailedState(OfflineOracle):
            def complete(self,messages,*,purpose):
                if purpose.startswith('cs_v031'):
                    return Completion('invalid',{'purpose':purpose,'source':'mock','finish_reason':'stop','input_tokens':0,'output_tokens':0})
                return super().complete(messages,purpose=purpose)
        parent=(ROOT/'results/raw').resolve()
        with tempfile.TemporaryDirectory(prefix='cycle4_failed_',dir=parent) as temp:
            base=Path(temp).resolve();self.assertTrue(base.is_relative_to(parent));path=base/'long'
            data=load_json(ROOT/'datasets/cycle4_v1/longitudinal.json')
            run(ROOT/'configs/cycle4_longitudinal_v1.json',path,client=FailedState(data))
            self.assertTrue(audit(path)['complete'])
            rows=[r for r in load_json(path/'results.json') if r['condition']=='cs_v031']
            self.assertEqual(sum(r['status']=='representation_error' for r in rows),2)
            self.assertEqual(sum(r['status']=='skipped_chain_error' for r in rows),6)
            self.assertTrue(all(not r['success'] for r in rows))

    def test_provider_interruption_has_no_complete_performance(self):
        class Failing:
            def complete(self,messages,*,purpose): raise RuntimeError('offline outage')
        parent=(ROOT/'results/raw').resolve()
        with tempfile.TemporaryDirectory(prefix='cycle4_outage_',dir=parent) as temp:
            base=Path(temp).resolve();self.assertTrue(base.is_relative_to(parent));path=base/'run'
            run(ROOT/'configs/cycle4_preflight_v1.json',path,client=Failing())
            report=audit(path)
            self.assertFalse(report['complete'])
            self.assertEqual(report['usage']['unknown_usage_attempts'],1)
            self.assertTrue(all(v['successes'] is None for v in load_json(path/'summary.json')['conditions'].values()))

    def test_recording_stops_unknown_usage_and_sanitizes_transport(self):
        class Unknown:
            def complete(self, messages, *, purpose):
                return Completion('x', {"purpose": purpose, "input_tokens": None, "output_tokens": None})
        client = RecordingClient(Unknown(), 2, False)
        with self.assertRaises(RuntimeError): client.complete([], purpose="x")
        self.assertEqual(len(client.attempts), 1)
        class Error:
            def complete(self, messages, *, purpose): raise RuntimeError('SENSITIVE_EXCEPTION_BODY')
        client = RecordingClient(Error(), 2, False)
        with self.assertRaises(RuntimeError): client.complete([], purpose="x")
        self.assertNotIn('SENSITIVE_EXCEPTION_BODY', compact(client.attempts))

    def test_all_stages_mock_replay_review_and_gate(self):
        # TemporaryDirectory deletes only its verified child below results/raw.
        parent = (ROOT / 'results/raw').resolve(); parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='cycle4_offline_', dir=parent) as temp:
            base = Path(temp).resolve(); self.assertTrue(base.is_relative_to(parent))
            for stage in ['preflight', 'regression', 'longitudinal']:
                path = base / stage; data = load_json(ROOT / f'datasets/cycle4_v1/{stage}.json')
                run(ROOT / f'configs/cycle4_{stage}_v1.json', path, client=OfflineOracle(data))
                result = audit(path)
                self.assertTrue(result['complete'])
                self.assertEqual(result['evidence_type'], 'mock_protocol_validation')
                rows = load_json(path/'results.json')
                self.assertTrue(all(r['success'] for r in rows), (stage, [(r['instance_id'],r['condition'],r['status'],r['error']) for r in rows if not r['success']]))
                packet = review_packet(path)
                self.assertNotIn('trace', compact(packet))
                with self.assertRaises(AssertionError): validate_review(path, packet)
                packet['reviewer'] = 'offline test annotator; not actual semantic review'
                for entry in packet['entries']:
                    entry['assessment'] = {k:'ambiguous' for k in entry['assessment']}
                    entry['evidence_notes'] = 'Offline test of completed review plumbing only.'
                save_json(path/'review.json',packet)
                gate = make_gate(path,path/'review.json')
                self.assertEqual(gate['status'],'failed', 'Mock evidence must not release real comparison')
                # Tampering with an actual public input is detected by replay.
                artifact = path/rows[0]['artifact']; a=load_json(artifact)
                a['history'][0]['content'] += ' TAMPERED'; save_json(artifact,a)
                with self.assertRaises(AssertionError): audit(path)


if __name__ == '__main__':
    unittest.main()
