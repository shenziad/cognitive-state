"""Freeze one bounded, whole A restart after the preserved API interruption."""
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.exp004_mechanism.runtime_v2 import verify_release
from experiments.exp004_mechanism.budget_bridge import engineering_gate
from evaluation.staged import ledger_totals
from utils.io import load_json, save_json, digest

if __name__ == '__main__':
    target = ROOT / 'docs/freezes/cycle5_execution_v3.json'
    assert not target.exists()
    parent = verify_release()
    old = load_json(ROOT / 'configs/cycle5_mechanism_v2.json')
    new = load_json(ROOT / 'configs/cycle5_mechanism_v3.json')
    assert set(old) == set(new)
    assert {k for k in old if old[k] != new[k]} == {'execution_version', 'experiment_id', 'config_path'}
    for old_path, new_path, before, after in [
        ('experiments/exp004_mechanism/runtime_v2.py', 'experiments/exp004_mechanism/runtime_v3.py', 'cycle5_execution_v2.json', 'cycle5_execution_v3.json'),
        ('scripts/run_cycle5_v2.py', 'scripts/run_cycle5_v3.py', 'runtime_v2', 'runtime_v3'),
        ('scripts/analyze_cycle5_v2.py', 'scripts/analyze_cycle5_v3.py', 'runtime_v2', 'runtime_v3')]:
        assert (ROOT / new_path).read_text(encoding='utf-8') == (ROOT / old_path).read_text(encoding='utf-8').replace(before, after)
    gate = engineering_gate()
    assert gate == load_json(ROOT / new['incoming_diagnostic_gate'])
    assert gate['scope_task_ids'] == new['task_ids']
    prior = ROOT / 'results/raw/cycle5/mechanism_v2_20261004'
    assert load_json(prior / 'manifest.json')['status'] == 'aborted_api_error'
    assert not (prior / 'results.json').exists()
    usage = ledger_totals(load_json(prior / 'call_ledger.json'))
    assert usage['request_attempts'] == 26 and usage['successful_responses'] == 25
    assert usage['known_reported_tokens'] == 78153 and usage['unknown_usage_attempts'] == 1
    assert len(load_json(prior / 'prepared.json')) == 31
    probe = ROOT / 'results/raw/cycle5/service_probe_20261004.json'
    assert load_json(probe)['status'] == 'response_received'
    output = ROOT / 'results/raw/cycle5/mechanism_v3_20261004'
    assert not output.exists(), 'Freeze must precede all A-v3 requests'
    paths = set(parent['sha256']) | {
        'docs/freezes/cycle5_execution_v2.json',
        'experiments/exp004_mechanism/runtime_v3.py',
        'scripts/run_cycle5_v3.py', 'scripts/analyze_cycle5_v3.py', 'scripts/freeze_cycle5_v3.py',
        new['config_path'], 'docs/cycle5_recovery_v3.md',
        'docs/cycle5_transport_recovery_audit_v3.md',
        probe.relative_to(ROOT).as_posix(),
    }
    paths.update((prior / name).relative_to(ROOT).as_posix() for name in
        ('manifest.json', 'call_ledger.json', 'prepared.json', 'config.json',
         'execution_release.json', 'task_order.json', 'executor_schedule.json'))
    save_json(target, {
        'execution_version': new['execution_version'], 'protocol_id': 'cycle5-bounded-whole-recovery-v3',
        'status': 'frozen_before_model_calls', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'dependencies': parent['dependencies'], 'sha256': {p: digest(ROOT / p) for p in sorted(paths)},
        'parent_execution_release_sha256': digest(ROOT / 'docs/freezes/cycle5_execution_v2.json'),
        'prior_A_status': 'aborted_api_error', 'prior_A_usage': usage,
        'no_prior_preparation_reuse': True, 'prompts_inputs_limits_and_schedule_unchanged': True,
        'original_D_complete': False, 'original_D_gate_status': 'failed',
        'assignment': {'mechanism_cells': 72, 'paired_members': 12, 'basic_workflows': 6, 'source_reviews_before_execution': 60},
        'next_failure_policy': 'stop_preserve_no_further_automatic_recovery',
    })
    print({'frozen_assets': len(paths), 'A_v3_model_calls_before_freeze': 0, 'prior_A_unknown_usage_attempts': 1})
