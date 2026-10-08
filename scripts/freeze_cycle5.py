"""Freeze reviewed input, allocation, prompts, runtime and reports before calls."""
from datetime import datetime,timezone
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from evaluation.cycle4 import verify_release,dependencies
from utils.io import load_json,save_json,digest


def freeze():
    target=ROOT/'docs/freezes/cycle5_execution_v1.json'
    assert not target.exists(),'Refuse to replace an existing execution freeze'
    old=verify_release()
    audit=load_json(ROOT/'docs/cycle5_input_audit_v1.json')
    assert audit['status']=='passed_pre_call_engineering_review'
    for path,sha in audit['audited_sha256'].items():
        assert digest(ROOT/path)==sha,path
    public=load_json(ROOT/'datasets/history_diagnostics_v01/tasks_public.json')['tasks']
    for stage in ['diagnostic','mechanism']:
        c=load_json(ROOT/f'configs/cycle5_{stage}_v1.json')
        ids=[t['task_id'] for t in public if stage=='diagnostic' or t['family']=='historical_counterfactual']
        assert c['task_ids']==ids and c['max_steps']==4 and c['representation_budget']==6000
        assert c['model']=='deepseek-ai/DeepSeek-V4-Flash' and c['temperature']==0
        assert c['max_api_calls']==(192 if stage=='diagnostic' else 400)
        assert c['token_stop_threshold']==(500000 if stage=='diagnostic' else 750000)
    checks=[]
    for pattern in ['test_mechanism_conditions_v01.py','test_cycle5_runtime_v1.py']:
        p=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',pattern,'-v'],cwd=ROOT,
                         capture_output=True,text=True,encoding='utf-8')
        assert p.returncode==0,p.stdout+p.stderr
        checks.append({'pattern':pattern,'passed':True,'output':p.stdout+p.stderr})
    validation=ROOT/'docs/freezes/cycle5_offline_validation_v1.json'
    save_json(validation,{'evidence_type':'offline_protocol_validation_not_model_performance',
        'model_calls':0,'tests_passed':20,'checks':checks,'cycle4_unchanged':True,'input_audit_sha256':digest(ROOT/'docs/cycle5_input_audit_v1.json')})
    relative=set(old['sha256'])|{'docs/freezes/cycle4_execution_v2.json'}
    relative.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'prompts/cycle5').glob('*.txt'))
    relative.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'datasets/history_diagnostics_v01').glob('*') if p.is_file())
    relative.update(['experiments/exp004_mechanism/runtime.py','experiments/exp004_mechanism/conditions.py',
        'scripts/run_cycle5.py','scripts/analyze_cycle5.py','scripts/freeze_cycle5.py','scripts/build_history_diagnostics_v01.py',
        'tests/test_cycle5_runtime_v1.py','tests/test_mechanism_conditions_v01.py',
        'configs/cycle5_diagnostic_v1.json','configs/cycle5_mechanism_v1.json',
        'docs/cycle5_protocol_v01.md','docs/cycle5_input_audit_v1.json','docs/cycle5_input_audit_v1.md',
        'docs/freezes/cycle5_offline_validation_v1.json'])
    release={'execution_version':'cycle5-execution-v1','protocol_id':'cycle5-history-mechanism-v1',
        'status':'frozen_before_model_calls','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'dependencies':dependencies(),'cycle4_release_sha256':digest(ROOT/'docs/freezes/cycle4_execution_v2.json'),
        'sha256':{path:digest(ROOT/path) for path in sorted(relative)},
        'assignment':{'diagnostic_cells':48,'mechanism_cells':72,'mechanism_basic_workflows':6,
            'repetitions':1,'selection_uses_current_model_results':False,'source_first_preparations_reviewed':60},
        'stops':{'diagnostic_requests':192,'mechanism_requests':400,'diagnostic_tokens':500000,'mechanism_tokens':750000,
            'automatic_retries':0,'automatic_recovery':False}}
    save_json(target,release)
    print({'frozen_assets':len(relative),'offline_tests':20,'model_calls':0})


if __name__=='__main__':freeze()
