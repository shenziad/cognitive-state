"""Freeze the prospective mechanism-only budget amendment, preserving v1."""
from datetime import datetime,timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src'))
from experiments.exp004_mechanism.budget_bridge import engineering_gate
from experiments.exp004_mechanism.runtime import verify_release
from utils.io import load_json,save_json,digest

if __name__=='__main__':
    target=ROOT/'docs/freezes/cycle5_execution_v2.json'
    assert not target.exists()
    original=verify_release()
    old=load_json(ROOT/'configs/cycle5_mechanism_v1.json')
    new=load_json(ROOT/'configs/cycle5_mechanism_v2.json')
    changed={k for k in old if old[k]!=new[k]}
    assert changed=={'execution_version','experiment_id','config_path','incoming_diagnostic_gate'}
    gate=engineering_gate()
    assert gate==load_json(ROOT/new['incoming_diagnostic_gate'])
    assert gate['scope_task_ids']==new['task_ids']
    paths=set(original['sha256'])|{'docs/freezes/cycle5_execution_v1.json',
        'experiments/exp004_mechanism/runtime_v2.py','experiments/exp004_mechanism/budget_bridge.py',
        'scripts/run_cycle5_v2.py','scripts/analyze_cycle5_v2.py','scripts/freeze_cycle5_v2.py',
        'configs/cycle5_mechanism_v2.json','docs/cycle5_budget_amendment_v2.md','docs/cycle5_budget_amendment_v2.json',
        new['incoming_diagnostic_gate'],'results/analysis/cycle5_diagnostic_v1_20261004/gate.json'}
    prior=Path(gate['source_run'])
    paths.update((prior/n).relative_to(ROOT).as_posix() for n in gate['protected_sha256'])
    save_json(target,{'execution_version':'cycle5-execution-v2','protocol_id':'cycle5-mechanism-budget-amendment-v2',
        'status':'frozen_before_model_calls','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'dependencies':original['dependencies'],'sha256':{p:digest(ROOT/p) for p in sorted(paths)},
        'parent_execution_release_sha256':digest(ROOT/'docs/freezes/cycle5_execution_v1.json'),
        'gate_change_after_D':True,'original_D_complete':False,'original_D_gate_status':'failed',
        'mechanism_selection_unchanged':True,'prompts_and_inputs_unchanged':True,
        'offline_validation':'20 original mechanism tests plus complete 113-request partial-D replay and independent bridge review',
        'assignment':{'mechanism_cells':72,'paired_members':12,'basic_workflows':6,'source_reviews_before_execution':60},
        'no_automatic_recovery_or_D_concatenation':True})
    print({'frozen_assets':len(paths),'A_model_calls_before_freeze':0,'original_D_complete':False})
