"""Meaningful input isolation, budget stop and artifact-tampering checks."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'src'))
from experiments.exp004_mechanism import runtime as r
from experiments.exp004_mechanism.conditions import load_prompt
from llm.client import Completion
from utils.io import load_json,save_json


class Fake:
    def __init__(self,actions=None):
        self.config={'max_output_tokens':4096};self.calls=0;self.actions=actions or []
    def complete(self,messages,*,purpose):
        action=self.actions[self.calls%len(self.actions)] if self.actions else {'tool':'finish','arguments':{'status':'completed'}}
        self.calls+=1
        return Completion(json.dumps(action),{'purpose':purpose,'response_id':f'mock-{self.calls}',
            'source':'mock','finish_reason':'stop','input_tokens':10,'output_tokens':10})


class RuntimeTests(unittest.TestCase):
    def config(self): return deepcopy(load_json(ROOT/'configs/cycle5_diagnostic_v1.json'))

    def test_actual_no_history_messages_identical_for_all_six_pairs(self):
        tasks=load_json(ROOT/'datasets/history_diagnostics_v01/tasks_public.json')['tasks']
        for pair in sorted({t['pair_id'] for t in tasks if t['pair_id']}):
            two=[t for t in tasks if t['pair_id']==pair]
            messages=[]
            for t in two:
                h,i=r.projection(t,False)
                messages.append({'system':load_prompt('executor'),'context':r.public_context(r.compact(h),i)})
                self.assertNotIn(t['task_id'],json.dumps(messages[-1]))
            self.assertEqual(messages[0],messages[1])

    def test_request_cap_stops_before_sending(self):
        config=self.config();config['max_api_calls']=1
        fake=Fake();client=r.RecordingClient(fake,config,real=False)
        client.complete([],purpose='executor')
        with self.assertRaisesRegex(r.StopRun,'request_cap'): client.complete([],purpose='executor')
        self.assertEqual(fake.calls,1)
        self.assertEqual(len(client.attempts),1)

    def test_token_threshold_stops_before_second_send(self):
        config=self.config();config['token_stop_threshold']=20
        fake=Fake();client=r.RecordingClient(fake,config,real=False)
        client.complete([],purpose='executor')
        with self.assertRaisesRegex(r.StopRun,'token_threshold'): client.complete([],purpose='executor')
        self.assertEqual(fake.calls,1)

    def test_unknown_usage_is_preserved_and_stops(self):
        class Unknown(Fake):
            def complete(self,messages,*,purpose):
                response=super().complete(messages,purpose=purpose)
                response.metadata['input_tokens']=None
                return response
        client=r.RecordingClient(Unknown(),self.config(),real=False)
        with self.assertRaisesRegex(r.StopRun,'unknown_usage'): client.complete([],purpose='executor')
        self.assertIsNone(r.ledger_totals(client.attempts)['total_tokens'])
        self.assertEqual(r.ledger_totals(client.attempts)['unknown_usage_attempts'],1)

    def test_exception_text_is_not_persisted(self):
        class Error(Fake):
            def complete(self,messages,*,purpose): raise RuntimeError('sensitive arbitrary server body')
        client=r.RecordingClient(Error(),self.config(),real=False)
        with self.assertRaises(r.StopRun):client.complete([],purpose='executor')
        self.assertNotIn('sensitive',json.dumps(client.attempts))

    def test_mock_run_replays_and_rejects_success_tampering(self):
        tempbase=ROOT/'results/raw/cycle5_offline';tempbase.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tempbase) as name:
            root=Path(name).resolve()
            self.assertTrue(root.is_relative_to(tempbase.resolve()))
            task=load_json(ROOT/'datasets/history_diagnostics_v01/tasks_public.json')['tasks'][12]
            private=load_json(ROOT/'datasets/history_diagnostics_v01/fixtures_private.json')['tasks'][12]
            save_json(root/'public.json',{'tasks':[task]});save_json(root/'private.json',{'tasks':[private]})
            config=self.config();config.update(config_path='config.json',dataset_public='public.json',dataset_private='private.json',task_ids=[task['task_id']])
            save_json(root/'config.json',config);release={'sha256':{}};save_json(root/'release.json',release)
            actions=[{'tool':'execute','arguments':{'operation':'publish_internal'}},{'tool':'finish','arguments':{'status':'completed'}}]
            with patch.object(r,'ROOT',root),patch.object(r,'RELEASE',root/'release.json'),patch.object(r,'verify_release',return_value=release):
                r.diagnostic(root/'config.json',root/'run',Fake(actions))
                audit=r.audit_run(root/'run');self.assertTrue(audit['complete'])
                self.assertEqual(audit['evidence_type'],'mock_protocol_validation')
                rows=load_json(root/'run/results.json');rows[0]['success']=False
                save_json(root/'run/results.json',rows)
                artifact=load_json(root/'run'/rows[0]['artifact']);artifact['row']=rows[0]
                save_json(root/'run'/rows[0]['artifact'],artifact)
                with self.assertRaises(AssertionError):r.audit_run(root/'run')

    def test_source_first_mechanism_replays_shared_cost_and_text(self):
        class MechanismFake(Fake):
            def complete(self,messages,*,purpose):
                if purpose=='executor':
                    value={'tool':'execute','arguments':{'operation':'publish_internal'}} if len(messages)==2 else {'tool':'finish','arguments':{'status':'completed'}}
                    text=json.dumps(value)
                elif purpose.startswith('cs1:'):
                    text=json.dumps({'goal':{'revision':'g1','objective':'Publish internal','requirements':[
                        {'id':'r1','text':'Publish once','source_refs':['hd01:current:u']}],'constraints':[],'preferences':[]},
                        'world':{'claims':[{'id':'cl1','text':'Evidence prepared','basis':'observed','source_refs':['hd01:preparation:receipt0']}],
                            'operations':[],'resources':[]},'frontier':{'obligations':[],'open_questions':[]}})
                else: text='Approved audience internal; commit once and then finish.'
                self.calls+=1
                return Completion(text,{'purpose':purpose,'response_id':f'mock-{self.calls}','source':'mock',
                    'finish_reason':'stop','input_tokens':10,'output_tokens':10})
        tempbase=ROOT/'results/raw/cycle5_offline';tempbase.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tempbase) as name:
            root=Path(name).resolve();self.assertTrue(root.is_relative_to(tempbase.resolve()))
            task=load_json(ROOT/'datasets/history_diagnostics_v01/tasks_public.json')['tasks'][12]
            private=load_json(ROOT/'datasets/history_diagnostics_v01/fixtures_private.json')['tasks'][12]
            save_json(root/'public.json',{'tasks':[task]});save_json(root/'private.json',{'tasks':[private]})
            config=deepcopy(load_json(ROOT/'configs/cycle5_mechanism_v1.json'))
            config.update(config_path='config.json',dataset_public='public.json',dataset_private='private.json',task_ids=[task['task_id']])
            save_json(root/'config.json',config);release={'sha256':{}};save_json(root/'release.json',release)
            client=MechanismFake()
            with patch.object(r,'ROOT',root),patch.object(r,'RELEASE',root/'release.json'),patch.object(r,'verify_release',return_value=release):
                r.prepare_run(root/'config.json',root/'run',client)
                self.assertEqual(load_json(root/'run/manifest.json')['status'],'prepared')
                self.assertFalse((root/'run/results.json').exists())
                packet=r.source_packet(root/'run');self.assertEqual(len(packet['entries']),5)
                packet['reviewer']='offline_protocol_test_not_semantic_gold'
                for entry in packet['entries']:
                    entry['assessment']={d:'correct' for d in r.DIMENSIONS};entry['evidence_notes']='Offline shape test only.'
                save_json(root/'review.json',packet)
                r.execute_run(root/'run',root/'review.json',client)
                self.assertTrue(r.audit_run(root/'run')['complete'])
                rows=load_json(root/'run/results.json')
                cs=next(x for x in rows if x['condition']=='cs1');text=next(x for x in rows if x['condition']=='cs_text')
                self.assertEqual(cs['source_request_indices'],text['source_request_indices'])
                ledger=load_json(root/'run/call_ledger.json')
                self.assertEqual(len(ledger),17)
                self.assertEqual(sum(x['deployment_usage']['total_tokens'] for x in rows),360)
                self.assertEqual(r.ledger_totals(ledger)['total_tokens'],340)


if __name__=='__main__': unittest.main()
