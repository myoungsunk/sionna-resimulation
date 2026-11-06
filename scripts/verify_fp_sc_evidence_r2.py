"""Stored-output checks; same-operator verification, not independent audit."""
import csv,gzip,json,sys
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.followup.contracts import sha256,write_json
B=R/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/PRIOR_EVIDENCE_R2_20261106'
run=B/'RUN_001'; receipt=json.loads((run/'RUN_RECEIPT.json').read_text())
assert receipt['status']=='COMPLETE_DIAGNOSTICS_AND_C_ONLY_PROVIDER_HOLD'
for name,h in receipt['files'].items():assert sha256(run/name)==h
for name,h in receipt['code_hashes'].items():assert sha256(R/name)==h
for name,h in receipt['input_hashes'].items():assert sha256(R/name)==h
for name,h in receipt['contract_hashes'].items():assert sha256(B/name)==h
summary=json.loads((run/'C_ONLY_SUMMARY.json').read_text())
with gzip.open(run/'C_ONLY_LABELLED.jsonl.gz','rt') as f:rows=list(map(json.loads,f))
assert len(rows)==6320 and len({(r['case_id'],r['k']) for r in rows})==6320
assert all(r['raw_tap']==r['selected_tap'] for r in rows)
assert all(r['flag']==(r['wrong_score']>=2.) for r in rows)
assert sum(r['corpus']=='dynamic' for r in rows)==6272
assert sum(r['corpus']=='static' for r in rows)==48
assert all(r['raw_valid'] and r['reference_valid'] for r in rows)
conf={'tp':0,'fp':0,'tn':0,'fn':0}
for row in rows:
    wrong=row['raw_tap']!=row['reference_tap'];flag=row['flag']
    conf['tp' if wrong and flag else 'fn' if wrong else 'fp' if flag else 'tn']+=1
assert all(summary['all'][k]==v for k,v in conf.items())
with gzip.open(run/'C_ONLY_ONLINE.jsonl.gz','rt') as f:online=list(map(json.loads,f))
assert all(all(final[k]==v for k,v in orig.items()) for orig,final in zip(online,rows))
lookup={(r['case_id'],r['scenario']):r for r in json.loads((run/'EVIDENCE_SUMMARY.json').read_text())}
grid=receipt['scenario_grid']; expanded=0;source_rows=0;shared_max=0.
for path in run.glob('*_DIAGNOSTICS.npz'):
    cid=path.name.removesuffix('_DIAGNOSTICS.npz')
    with np.load(path,allow_pickle=False) as z:
        a=z['values'];ids=z['scenario_ids'];cols=z['columns'];n=len(z['t'])
        assert a.shape==(277,n,6) and len(set(z['pose_id']))==n and np.isfinite(a).all()
        assert list(ids)==[s['id'] for s in grid]
        assert np.isnan(z['past_features'][0,0]) and z['past_features'][0,1]==0
        for j,s in enumerate(grid):
            for k,col in enumerate(cols):
                m=lookup[(cid,s['id'])]['metrics'][col]
                assert m['n']==n and m['available']==n and m['missing']==0
                assert abs(m['median']-float(np.median(a[j,:,k])))<1e-12
                assert abs(m['p95']-float(np.quantile(a[j,:,k],.95)))<1e-12
            if s['shared']:
                err=float(np.max(abs(a[j,:,:2]-a[0,:,:2])));shared_max=max(shared_max,err);assert err<1e-10
        expanded+=a.shape[0]*n;source_rows+=n
assert expanded==1737344 and source_rows==6272
history=B/'HISTORY_001'; hc=json.loads((history/'CHECK.json').read_text())
assert sha256(history/'HISTORY_CHECKS.csv.gz')==hc['csv_sha256']
with gzip.open(history/'HISTORY_CHECKS.csv.gz','rt') as f:
    keys=set()
    for row in csv.DictReader(f):
        key=(row['case_id'],row['k'],row['kind'],row['value']);assert key not in keys;keys.add(key)
        assert row['motion_support_absent']=='True' and row['trusted_cleared']=='True' and row['prior_state']=='UNKNOWN'
assert len(keys)==68992==hc['checks']
write_json(B/'CHECK_001.json',dict(status='PASS_STORED_OUTPUT_SELF_CHECK_NOT_SCIENCE_ACCEPTANCE',
    source_rows=source_rows,intervention_rows=expanded,history_checks=len(keys),C_only_rows=len(rows),
    C_confusion=conf,shared_difference_max=shared_max,old_exclusions=11095,
    code_and_input_hashes_unchanged=True,independent_audit=False,provider_gate='UNDETERMINED',
    E1_02_started=False,E2_started=False,checker_sha256=sha256(Path(__file__))))
print('PASS stored arrays, C-only confusion, history rows, hashes; provider HOLD')
