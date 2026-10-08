"""Report every incurred cycle5 attempt, including interruptions and service probe."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.staged import ledger_totals
from utils.io import load_json, save_json, digest


def campaign():
    stages = []
    for label, relative in (
        ('D-v1', 'results/raw/cycle5/diagnostic_v1_20261004'),
        ('A-v2 interrupted', 'results/raw/cycle5/mechanism_v2_20261004'),
        ('A-v3 bounded recovery', 'results/raw/cycle5/mechanism_v3_20261004'),
    ):
        run = ROOT / relative
        if not run.exists():
            continue
        manifest = load_json(run / 'manifest.json')
        ledger = load_json(run / 'call_ledger.json')
        rows = load_json(run / 'results.json') if (run / 'results.json').exists() else []
        prepared = load_json(run / 'prepared.json') if (run / 'prepared.json').exists() else []
        stages.append({'stage': label, 'source_run': str(run),
            'status': manifest['status'], 'assigned_cells': manifest['assigned_cells'],
            'saved_behavior_cells': len(rows), 'saved_preparations': len(prepared),
            'usage': ledger_totals(ledger), 'source_sha256': {
                'manifest.json': digest(run / 'manifest.json'),
                'call_ledger.json': digest(run / 'call_ledger.json')}})
    probe_path = ROOT / 'results/raw/cycle5/service_probe_20261004.json'
    probe = load_json(probe_path) if probe_path.exists() else None
    probe_usage = {'request_attempts': 0, 'successful_responses': 0,
                   'known_reported_tokens': 0, 'unknown_usage_attempts': 0}
    if probe:
        known = type(probe.get('total_tokens')) is int
        probe_usage = {'request_attempts': probe['request_attempts'],
            'successful_responses': int(probe['status'].startswith('response')),
            'known_reported_tokens': probe['total_tokens'] if known else 0,
            'unknown_usage_attempts': probe['unknown_usage_attempts']}
    usages = [s['usage'] for s in stages] + [probe_usage]
    totals = {k: sum(u[k] for u in usages) for k in probe_usage}
    totals['total_tokens'] = None if totals['unknown_usage_attempts'] else totals['known_reported_tokens']
    return {'stages': stages, 'service_probe': {
        'source': str(probe_path), 'sha256': digest(probe_path), 'usage': probe_usage,
        'is_experimental_cell': False} if probe else None,
        'campaign_usage': totals,
        'cost_scope': 'all incurred actual attempts; shared CS extraction counted once per run',
        'unknown_usage_policy': 'total unknown; known_reported_tokens is a lower bound, never fill unknown with zero',
        'sample_policy': 'Do not concatenate D, interrupted A-v2, or recovery A-v3 behavior/preparations.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    assert not args.output.exists()
    result = campaign()
    save_json(args.output, result)
    print(result['campaign_usage'])
