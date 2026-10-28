"""Regression tests for the three reviewed v2 defects; synthetic inputs only."""
import json
from itertools import product
import numpy as np
import pandas as pd
import pytest
from dsreassess.stage12 import summary_residuals
from dsreassess.io import sha256, write_json
import run_selective as runner


def population(labels,accepted=None,raw=None):
    n=len(labels)
    g=pd.DataFrame(dict(case='R2',bias='B0',arm='EXDS',sample='all',
        distance_bin=labels,packet_index=np.arange(n),
        raw_sample_index=np.arange(n) if raw is None else raw,
        pose_id=100+np.arange(n)*4,t_s=np.arange(n)*.2,
        accepted_ab=np.ones(n,bool) if accepted is None else accepted,
        er_m=np.sin(np.arange(n)*.1),es=np.cos(np.arange(n)*.1),Rrr=.01,Rss=.01))
    a=g[g.accepted_ab].copy();a['sample']='accepted_A_B'
    native=pd.concat([g,a],ignore_index=True)
    whole=native.copy();whole['distance_bin']='whole'
    return g,pd.concat([native,whole],ignore_index=True)


def test_summary_preserves_native_distance_bins_and_actual_pairs():
    mask=np.ones(300,bool);mask[10]=False
    raw=np.arange(300);raw[50:]+=2
    g,df=population(['near']*100+['mid']*100+['far']*100,mask,raw)
    stats=summary_residuals(df,reps=30)
    for b,sample,lag in product(('whole','near','mid','far'),('all','accepted_A_B'),(1,5)):
        pairs=[(i,j) for i in range(len(g)) for j in range(i+1,len(g))
               if raw[j]-raw[i]==lag and
               (b=='whole' or g.distance_bin.iloc[i]==g.distance_bin.iloc[j]==b) and
               (sample=='all' or mask[i] and mask[j])]
        row=stats[(stats.distance_bin==b)&(stats['sample']==sample)].iloc[0]
        assert row[f'lag{lag}_n_pairs']==len(pairs)>0
        expected=np.corrcoef([g.er_m.iloc[i] for i,j in pairs],
                             [g.er_m.iloc[j] for i,j in pairs])[0,1]
        assert row[f'acf{lag}_er']==pytest.approx(expected)


@pytest.mark.parametrize('count',[0,1,7])
def test_sparse_and_empty_bins_are_explicit(count):
    g,df=population(['near']*count+['far']*150,accepted=np.zeros(count+150,bool))
    stats=summary_residuals(df,reps=30)
    assert len(stats)==8
    near=stats[(stats.distance_bin=='near')&(stats['sample']=='all')].iloc[0]
    assert near.n_packets==count
    assert near.sample_status==('NA_NO_SAMPLES' if count==0 else 'NA_INSUFFICIENT_PACKETS')
    assert np.isnan(near.cov_er_es) and np.isnan(near.acf1_er)
    assert near.boot_8_status.startswith('NA_')
    empty=stats[(stats.distance_bin=='mid')|(stats['sample']=='accepted_A_B')]
    assert empty.n_packets.eq(0).all()
    assert empty.sample_status.eq('NA_NO_SAMPLES').all()
    assert empty.boot_32_status.eq('NA_NO_SAMPLES').all()


def completed_output(root,step):
    path=root/runner.STAGE_FOLDERS[step];path.mkdir(exist_ok=True)
    write_json(path/'CHECKS.json',[{'status':'PASS','label':'synthetic'}])
    if step=='2':
        pd.DataFrame([dict(lag1_n_pairs=9,lag5_n_pairs=8,boot_8_status='PASS',
            boot_16_status='PASS',boot_32_status='PASS',bootstrap_stability='STABLE_POS',
            original_origin_s=0)]).to_csv(path/'RESIDUAL_STATS.csv',index=False)
    if step=='3':
        write_json(path/'LEGACY_ALL_PARITY.json',{'status':'PASS','max_abs_diff':0})
    if step=='5':
        pd.DataFrame([{'status':'PASS'}]).to_csv(path/'FISHER_INDEPENDENT_AUDIT.csv',index=False)
        pd.DataFrame([{'status':'STABLE_PASS'}]).to_csv(path/'H_PHI_FD_CHAIN_AUDIT.csv',index=False)
    write_json(path/'OUTPUT_SHA256.json',{p.name:sha256(p) for p in path.iterdir()})
    write_json(path/'RUN_STATUS.json',{'status':'CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION'})


def test_separate_stages_accumulate_and_only_all_create_final(tmp_path):
    contract={'code':'v21','inputs':'frozen','config':{'cov_shrink':.5}}
    for i,step in enumerate(('2','3','5'),1):
        completed_output(tmp_path,step)
        runner.record_stage_completion(tmp_path,step,contract)
        status=runner.finalize_available(tmp_path,contract)
        assert status['completed_steps']==['2','3','5'][:i]
        assert (tmp_path/'PATCH_V2_FINAL.json').exists()==(i==3)
    assert status['status']=='TECHNICAL_QA_PASS_NOT_SCIENTIFIC_ADOPTION'
    before=(tmp_path/'PATCH_V2_FINAL.json').read_bytes()
    runner.finalize_available(tmp_path,contract)
    assert (tmp_path/'PATCH_V2_FINAL.json').read_bytes()==before


def test_stage5_alone_is_partial(tmp_path):
    completed_output(tmp_path,'5')
    runner.record_stage_completion(tmp_path,'5',{'code':'v21'})
    r=runner.finalize_available(tmp_path,{'code':'v21'})
    assert r['completed_steps']==['5'] and r['missing_steps']==['2','3']
    assert r['status']=='PARTIAL_TECHNICAL_QA_PASS'
    assert not (tmp_path/'PATCH_V2_FINAL.json').exists()


@pytest.mark.parametrize('key',['code','inputs','config'])
def test_mixed_stage_contracts_cannot_finalize(tmp_path,key):
    original={'code':'v21','inputs':'frozen','config':{'cov_shrink':.5}}
    completed_output(tmp_path,'2');runner.record_stage_completion(tmp_path,'2',original)
    changed={**original,key:'different'}
    with pytest.raises(RuntimeError,match='STAGE_CONTRACT_MISMATCH'):
        runner.finalize_available(tmp_path,changed)
    assert not (tmp_path/'PATCH_V2_FINAL.json').exists()


@pytest.mark.parametrize('file',['CHECKS.json','RUN_STATUS.json','OUTPUT_SHA256.json'])
def test_prior_stage_tampering_prevents_final(tmp_path,file):
    for step in ('2','3','5'):
        completed_output(tmp_path,step);runner.record_stage_completion(tmp_path,step,{})
    target=tmp_path/'02_residuals'/file
    target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(RuntimeError,match='HASH_MISMATCH'):
        runner.finalize_available(tmp_path,{})
    assert not (tmp_path/'PATCH_V2_FINAL.json').exists()


def test_failed_stage_cannot_record_completion(tmp_path):
    completed_output(tmp_path,'5')
    p=tmp_path/'05_full_observability'
    write_json(p/'CHECKS.json',[{'status':'FAIL'}])
    m=json.loads((p/'OUTPUT_SHA256.json').read_text())
    m['CHECKS.json']=sha256(p/'CHECKS.json');write_json(p/'OUTPUT_SHA256.json',m)
    with pytest.raises(RuntimeError,match='NO_REAL_CHECKS_PASS'):
        runner.record_stage_completion(tmp_path,'5',{})
    assert not (tmp_path/'PATCH_STAGE_5.json').exists()


@pytest.mark.parametrize('mode',['all','separate'])
def test_main_dispatch_and_receipts_without_rf(tmp_path,monkeypatch,capsys,mode):
    from types import SimpleNamespace
    repo=tmp_path/'repo';repo.mkdir()
    old=repo/runner.RELATIVE/'results'/'03_RF_R_H';old.mkdir(parents=True)
    (old/'SCORES.csv').write_text('synthetic parity reference')
    output=tmp_path/'output';calls=[]
    args=SimpleNamespace(repo_root=repo,output_root=output,source_root=tmp_path/'source',
        artifacts_root=tmp_path/'artifacts',fd_stride=20,cov_shrink=.5,min_train_n=30,step='all')
    class SyntheticContext:
        def __init__(self,cfg):
            self.cfg=cfg;cfg.output_root.mkdir(exist_ok=True)
        def cases(self):return iter([None]*14)
        def evidence_metadata(self):
            return {'package_code_sha256':{'synthetic':'fixed'},
                    'input_sha256':{'synthetic_input':'fixed'},
                    'config':{k:str(v) if hasattr(v,'__fspath__') else v for k,v in vars(self.cfg).items()}}
    monkeypatch.setattr(runner,'make_args',lambda:args)
    monkeypatch.setattr(runner,'Context',SyntheticContext)
    monkeypatch.setattr(runner,'verify_patch_code_unchanged',lambda:None)
    monkeypatch.setattr(runner,'verify_cached_source',lambda old:{'cached':'fixed'})
    monkeypatch.setattr(runner.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=runner.BASE_SHA))
    actual_sha=runner.sha256
    monkeypatch.setattr(runner,'sha256',lambda p:'synthetic_manifest' if p.name=='PATCHED_PY_SHA256.json' else actual_sha(p))
    def stage(step,w):
        calls.append(step);completed_output(output,step)
    monkeypatch.setattr(runner,'stage2_from_verified_cache',lambda ctx,w,old:stage('2',w))
    monkeypatch.setattr(runner,'stage3',lambda ctx,w:stage('3',w))
    monkeypatch.setattr(runner,'stage5',lambda ctx,w:stage('5',w))
    for step in (['all'] if mode=='all' else ['2','3','5']):
        args.step=step
        assert runner.main()==0
        text=capsys.readouterr().out
        if step in ('2','3'):
            assert '[PARTIAL]' in text and '[DONE]' not in text
            assert not (output/'PATCH_V2_FINAL.json').exists()
    assert calls==['2','3','5']
    final=json.loads((output/'PATCH_V2_FINAL.json').read_text())
    assert final['completed_steps']==['2','3','5'] and not final['missing_steps']
