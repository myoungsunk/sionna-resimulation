"""User-authorized S2 only; frozen S1 decisions, no selection or EKF."""
import os
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import sys,json,gzip,pathlib,datetime,collections,traceback
import numpy as np
root=pathlib.Path(__file__).resolve().parents[2];os.chdir(root)
sys.path[:0]=[str(root/'src'),str(root/'scripts')]
import fp_sc_vab_shadow_stages as s
from qclean_uwb.fp_sc.followup.numerics import cir_from_spectrum,raw_detection
out=pathlib.Path(__file__).resolve().parent
for name in ('REVIEWS','MANIFESTS','APPROVALS'): (out/name).mkdir(exist_ok=True)
def rel(p):return p.relative_to(root).as_posix()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def gz(p):
    with gzip.open(p,'rt',encoding='utf-8') as f:return json.load(f)
check=root/'research/FP_SC_S1_RUN_20261106/CHECK_001.json'
assert read(check)['status']=='PASS_S1_SELF_CHECK' and read(check)['rows_checked']==25088
batch=dict(stage='S2_ONLY',start=now(),status='RUNNING',cases=[],independent_audit=False)
s.write_json(out/'BATCH_RECEIPT.json',batch)
changed=[]
try:
    for f in sorted((root/'research/FP_SC_S1_PREPARATION_20261106/FINAL_002').glob('*_S1_MANIFEST.json')):
        stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
        if stop and pathlib.Path(stop).exists():raise RuntimeError('STOP_REQUESTED')
        m,p=s.inspect_manifest(f);cid=m['case_id']
        source=root/'research/FP_SC_S1_RUN_20261106/RESULTS'/cid
        receipt=source/'RUN_RECEIPT.json';result=source/'ROWS.json.gz'
        assert read(receipt)['result_sha256']==s.sha256(result)
        review=out/'REVIEWS'/f'{cid}.json'
        s.write_json(review,dict(stage=s.STAGES[0],decision='ACCEPT_TO_NEXT_STAGE',
            receipt_sha256=s.sha256(receipt),reviewer='IMPLEMENTER_SELF_REVIEW_WITH_EXPLICIT_USER_S2_AUTHORIZATION',
            reviewed_at=now(),independent_audit=False,evidence=rel(check),evidence_sha256=s.sha256(check),
            scope='Technical S1 completeness accepted for posthoc S2 evaluation only; no efficacy acceptance'))
        m['stage']=s.STAGES[1]
        link={}
        for kind,path in [('result',result),('receipt',receipt),('review',review)]:
            link[kind+'_path']=rel(path);link[kind+'_sha256']=s.sha256(path)
            m['input_files'][rel(path)]=s.sha256(path)
        m['input_files'][rel(check)]=s.sha256(check)
        m['previous']={s.STAGES[0]:link}
        manifest=out/'MANIFESTS'/f'{cid}.json';s.write_json(manifest,m)
        approval=out/'APPROVALS'/f'{cid}.json'
        s.write_json(approval,dict(execute_shadow_science=True,stage=s.STAGES[1],case_id=cid,
            manifest_sha256=s.sha256(manifest),code_lock_sha256=s.digest(m['code_files']),
            actor='USER_EXPLICIT_CHAT_REQUEST',issued_utc=now(),authorization_text='S2 실행 시작한다',
            scope='Continue six-case frozen S1 to S2 only. No S3/E1-02/E2.'))
        print('START',cid,flush=True)
        r=s.run(manifest,approval,out/'RESULTS'/cid)
        rows=gz(out/'RESULTS'/cid/'ROWS.json.gz');previous=gz(result)
        n=m['case']['expected_rows'];assert len(rows)==4*n
        assert {(x['k'],x['mode']) for x in rows}=={(k,mode) for k in range(n) for mode in ('C','P','M','PM')}
        with np.load(root/m['case']['evaluator_npz'],allow_pickle=False) as a:refs=a['clean_H']
        refobs=[];reftaps=[]
        for h in refs:
            tap,_,obs=raw_detection(cir_from_spectrum(h));reftaps.append(tap);refobs.append(obs)
        before={(x['k'],x['mode']):x for x in previous}
        groups={}
        for x in rows:
            k=x['k'];mode=x['mode'];b=before[(k,mode)]
            assert x['raw_tap']==b['raw_tap'] and x['proposed_tap']==b['hypothetical_selected_tap']
            assert x['reference_tap']==reftaps[k]
            assert x['raw_correct']==(x['raw_tap']==reftaps[k]) and x['proposed_correct']==(x['proposed_tap']==reftaps[k])
            for arm in ('F00','F01','F11'):
                v=b['observations'][arm];expected=None if v is None or refobs[k] is None else np.asarray(v)-refobs[k]
                if expected is None:assert x['errors'][arm] is None
                else:np.testing.assert_array_equal(x['errors'][arm],expected)
            g=groups.setdefault(mode,dict(n=0,reference_invalid=0,changed=0,transitions=collections.Counter(),errors={a:[] for a in ('F00','F01','F11')}))
            g['n']+=1;g['changed']+=int(x['changed']);g['reference_invalid']+=int(not x['reference_valid'])
            if x['reference_valid']:g['transitions'][('correct' if x['raw_correct'] else 'wrong')+'_to_'+('correct' if x['proposed_correct'] else 'wrong')]+=1
            for arm in g['errors']:
                if x['errors'][arm] is not None:g['errors'][arm].append(x['errors'][arm])
            if x['changed']:changed.append(x)
        for g in groups.values():
            for arm,values in g['errors'].items():
                a=np.asarray(values);g['errors'][arm]=dict(n=len(a),mae=np.abs(a).mean(axis=0).tolist(),rmse=np.sqrt((a*a).mean(axis=0)).tolist(),mean=a.mean(axis=0).tolist())
        assert r['result_sha256']==s.sha256(out/'RESULTS'/cid/'ROWS.json.gz')
        batch['cases'].append(dict(case=cid,rows=len(rows),verification='PASS_EXACT_REFERENCE_AND_ERRORS',modes=groups,receipt=r))
        s.write_json(out/'BATCH_RECEIPT.json',batch);print('CHECKED',cid,len(rows),flush=True)
    assert sum(x['rows'] for x in batch['cases'])==25088
    batch['status']='PASS_S2_EXECUTION_AND_SELF_CHECK';s.write_json(out/'CHANGED_CASES.json',changed)
except Exception:
    batch['status']='FAILED_PRESERVED';batch['error']=traceback.format_exc();raise
finally:
    batch['end']=now();s.write_json(out/'BATCH_RECEIPT.json',batch)
