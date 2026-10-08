"""Prospective A-v2 engineering gate after D's measured token stop.

Never changes D's incomplete result or its failed original gate. Uses the entire
predeclared counterfactual stratum, with no behavior-performance criterion.
"""
from copy import deepcopy
from pathlib import Path
import json

from experiments.exp004_mechanism import runtime as v1
from experiments.exp004_mechanism.conditions import load_prompt
from evaluation.lifecycle import LifecycleEnvironment
from utils.io import digest,load_json,parse_json

ROOT=Path(__file__).resolve().parents[2]
PRIOR=ROOT/'results/raw/cycle5/diagnostic_v1_20261004'


def engineering_gate(run=PRIOR):
    run=Path(run).resolve()
    old=v1.audit_run(run)
    old_gate_path=ROOT/'results/analysis/cycle5_diagnostic_v1_20261004/gate.json'
    old_gate=load_json(old_gate_path)
    assert old_gate['status']=='failed' and old_gate['audit']==old
    manifest=load_json(run/'manifest.json')
    assert not old['complete'] and manifest['status']=='aborted_token_threshold'
    assert old['evidence_type']=='api' and old['usage']['unknown_usage_attempts']==0
    config=load_json(run/'config.json')
    assert old['usage']['known_reported_tokens']>=config['token_stop_threshold']
    rows=load_json(run/'results.json');ledger=load_json(run/'call_ledger.json')
    tasks,private=v1.selected_tasks(config)
    chosen=[t['task_id'] for t in tasks.values() if t['family']=='historical_counterfactual']
    scoped=[r for r in rows if r['task_id'] in chosen]
    assert len(chosen)==12 and len(scoped)==24
    assert {(r['task_id'],r['condition']) for r in scoped}=={(t,c) for t in chosen for c in ['full_context','no_history']}
    covered=set(i for r in rows for i in r['request_indices'])
    partial=load_json(run/'interrupted_cell.json')
    assert partial['task_id'] not in chosen and partial['condition']=='no_history'
    artifact=partial['partial'];history,interface=v1.projection(tasks[partial['task_id']],False)
    assert artifact['representation']==v1.compact(history) and artifact['public_interface']==interface
    env=LifecycleEnvironment(deepcopy(private[partial['task_id']]['environment']))
    messages=[{'role':'system','content':load_prompt('executor')},{'role':'user','content':json.dumps({
        'instruction':'Resume the interrupted task using the supplied context.',
        'context':v1.public_context(artifact['representation'],interface),'tools':env.tool_spec},ensure_ascii=False)}]
    remaining=[i for i in range(len(ledger)) if i not in covered]
    assert len(remaining)==len(artifact['calls'])==len(artifact['trace'])
    for call,trace,index in zip(artifact['calls'],artifact['trace'],remaining):
        request=ledger[index]
        assert request['task_id']==partial['task_id'] and request['condition']==partial['condition']
        assert request['purpose']=='executor' and request['status']=='response'
        assert call['messages']==messages
        assert all(request[k]==call[k] for k in ['messages','response','metadata'])
        assert parse_json(call['response'])==trace['action'] and call['metadata']['finish_reason']=='stop'
        env.apply(trace['action']);assert env.trace[-1]==trace
        messages += [{'role':'assistant','content':call['response']},
            {'role':'user','content':json.dumps({'action':trace['action'],'observation':trace['observation']},ensure_ascii=False)}]
        covered.add(index)
    assert env.settings==artifact['final_world'] and env.evaluate()==artifact['metrics']
    assert covered==set(range(len(ledger)))
    assert all(a['metadata']['source']=='api' and a['metadata']['transport']=='openai_sdk' and
               a['metadata']['model']==config['model'] for a in ledger)
    # Verify the actual first No-History request is identical within every pair.
    for pair in sorted({tasks[t]['pair_id'] for t in chosen}):
        rs=[r for r in scoped if tasks[r['task_id']]['pair_id']==pair and r['condition']=='no_history']
        assert len(rs)==2
        assert ledger[rs[0]['request_indices'][0]]['messages']==ledger[rs[1]['request_indices'][0]]['messages']
    return {'status':'passed','gate_type':'prospective_A_v2_complete_predeclared_paired_stratum',
        'source_run':str(run),'original_D_complete':False,'original_D_gate_status':'failed',
        'complete_scope':True,'complete_scope_cells':24,'scope_task_ids':chosen,'scope_workflows':6,
        'behavior_threshold':None,'missing_original_candidate_cells':3,
        'all_incurred_requests_verified':len(ledger),'usage':old['usage'],
        'prior_execution_release_sha256':digest(v1.RELEASE),
        'original_gate_sha256':digest(old_gate_path),
        'protected_sha256':{n:digest(run/n) for n in ['config.json','manifest.json','results.json','call_ledger.json','interrupted_cell.json']},
        'limits':['This gate was amended after D stopped on its measured token budget.',
                  'D remains incomplete; no three-cell fill, concatenation or complete original-stratum claim.',
                  'A task/condition/prompt selection predates D; scope is not selected by success.']}
