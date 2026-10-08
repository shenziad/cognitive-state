"""Offline replay, stage gate and all-assigned descriptive cycle5 summaries."""
from collections import Counter
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.exp004_mechanism.runtime import audit_run,RELEASE,validate_review
from evaluation.staged import ledger_totals
from utils.io import load_json,save_json,digest


def analyze(run,output):
    assert not output.exists()
    config=load_json(run/'config.json')
    rows=load_json(run/'results.json') if (run/'results.json').exists() else []
    ledger=load_json(run/'call_ledger.json')
    audit=audit_run(run) if (run/'results.json').exists() else {
        'stage':config['stage'],'complete':False,'evidence_type':load_json(run/'manifest.json')['evidence_type'],
        'usage':ledger_totals(ledger),'verification':'preparation interrupted; full execution replay unavailable'}
    groups={}
    for condition in config['conditions']:
        selected=[r for r in rows if r['condition']==condition]
        indices=set(i for r in selected for i in r['request_indices'])
        by_family={}
        for family in sorted({r['family'] for r in selected}):
            rs=[r for r in selected if r['family']==family]
            by_family[family]={'saved':len(rs),'successes':sum(r['success'] for r in rs) if audit['complete'] else None}
        groups[condition]={'assigned':len(config['task_ids']),'saved':len(selected),
            'successes':sum(r['success'] for r in selected) if audit['complete'] else None,
            'statuses':dict(Counter(r['status'] for r in selected)),
            'representation_valid':sum(r['representation_valid'] is True for r in selected),
            'deployment_usage':ledger_totals([ledger[i] for i in sorted(indices)]),
            'actual_condition_usage':ledger_totals([a for a in ledger if a.get('condition')==condition]),
            'credits_spent':sum(r['metrics']['workspace_credits_spent'] for r in selected),
            'by_family':by_family}
    pairs=[]
    for pair in sorted({r.get('pair_id') for r in rows if r.get('pair_id')}):
        for condition in config['conditions']:
            rs=[r for r in rows if r.get('pair_id')==pair and r['condition']==condition]
            pairs.append({'pair_id':pair,'condition':condition,'saved':len(rs),
                'joint_success':all(r['success'] for r in rs) if len(rs)==2 and audit['complete'] else None})
    source={}
    if (run/'source_review.json').exists():
        review=load_json(run/'source_review.json')
        validate_review(run,review)
        for condition in config['conditions']:
            entries=[e for e in review['entries'] if e['condition']==condition]
            if entries:
                source[condition]={scope:{'entries':len(es),'concrete_errors':sum('incorrect' in e['assessment'].values() for e in es),
                    'ambiguous':sum('ambiguous' in e['assessment'].values() for e in es)}
                    for scope in sorted({e['review_scope'] for e in entries})
                    for es in [[e for e in entries if e['review_scope']==scope]]}
    result={'stage':config['stage'],'complete':audit['complete'],'evidence_type':audit['evidence_type'],
        'source_run':str(run.resolve()),'model':config['model'],'temperature':config['temperature'],
        'thinking':config['extra_body']['enable_thinking'],'execution_release_sha256':digest(RELEASE),
        'actual_usage':audit['usage'],'conditions':groups,'paired_variants':pairs,'source_review':source,
        'actual_requests_not_associated_with_saved_rows':sorted(set(range(len(ledger)))-set(i for r in rows for i in r['request_indices'])),
        'failed_rows':[r for r in rows if not r['success']],
        'limits':['Known assistant-authored synthetic development workflows; paired members are correlated.',
                  'Assistant source annotations are not independent human gold or condition blinded.',
                  'CS-text compares this reversible field-path presentation only; it retains structure and all source information.',
                  'Strategy deployment costs include shared source extraction for each strategy; their sum is not actual suite cost.',
        'Token usage does not establish measured currency fees or behavioral equivalence.',
        'Incomplete deployment rows do not cover all incurred strategy costs; actual_condition_usage and unassociated requests preserve them.']}
    output.mkdir(parents=True,exist_ok=False)
    save_json(output/'audit.json',audit)
    save_json(output/'summary.json',result)
    if config['stage']=='diagnostic':
        save_json(output/'gate.json',{'status':'passed' if audit['complete'] and audit['evidence_type']=='api' and audit['usage']['unknown_usage_attempts']==0 else 'failed',
            'execution_release_sha256':digest(RELEASE),'source_run':str(run.resolve()),'audit':audit})
    lines=[f"# 第五轮 {config['stage']}",'',f"完整运行：{audit['complete']}；模型 `{config['model']}`，temperature={config['temperature']}，thinking=false。",'',
        '| 条件 | 成功/分配 | 策略归属 Tokens | credits |','|---|---:|---:|---:|']
    for c,g in groups.items():
        lines.append(f"| {c} | {g['successes'] if audit['complete'] else '未知'}/{g['assigned']} | {g['deployment_usage']['total_tokens']} | {g['credits_spent']} |")
    u=audit['usage']
    lines += ['',f"实际全账本：{u['request_attempts']} 次尝试，{u['known_reported_tokens']} 已知 Tokens，{u['unknown_usage_attempts']} 次未知用量。策略归属包含各自完整源提取；共享 CS 源只在实际账本计一次，不相加冒充实际收费。",'']
    if any(g['by_family'] for g in groups.values()):
        lines += ['| 条件 | 任务层 | 成功/保存 |','|---|---|---:|']
        for c,g in groups.items():
            for family,v in g['by_family'].items():
                lines.append(f"| {c} | {family} | {v['successes']}/{v['saved']} |")
    if pairs:
        lines += ['','| 基础配对 | 条件 | 双成员全成功 |','|---|---|---|']
        for p in pairs:
            lines.append(f"| {p['pair_id']} | {p['condition']} | {p['joint_success']} |")
    if source:
        lines += ['','| 条件 | 审阅范围 | 具体来源错误/审阅 | 歧义 |','|---|---|---:|---:|']
        for c,scopes in source.items():
            for scope,v in scopes.items():
                lines.append(f"| {c} | {scope} | {v['concrete_errors']}/{v['entries']} | {v['ambiguous']} |")
    lines += ['','实际评分、失败、状态来源与成本归属分别报告。解释与案例需对照公开来源和真实轨迹，不将编码有效或字段存在等同于状态充分。','',
        '## 局限','']+['- '+x for x in result['limits']]
    (output/'analysis.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print({'complete':audit['complete'],'actual_usage':audit['usage'],
           'successes':{c:g['successes'] for c,g in groups.items()}})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    analyze(a.run.resolve(),a.output.resolve())
