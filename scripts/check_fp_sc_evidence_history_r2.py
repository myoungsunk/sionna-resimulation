"""Full dynamic history-input interventions; existing guards, not a VALID provider."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import argparse,csv,gzip,json,sys,time
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import psutil
p=psutil.Process();p.cpu_affinity(p.cpu_affinity()[:3])
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.followup.contracts import Policy,STEP_M,sha256,write_json
from qclean_uwb.fp_sc.followup.detection import RawDetectionHistory
from qclean_uwb.fp_sc.followup.integrity import PriorIntegrity
B=R/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001'
PKG=B/'PRIOR_EVIDENCE_R2_20261106'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    a.output.mkdir(exist_ok=False);t0=time.time(); source=a.source
    receipt=json.loads((source/'RUN_RECEIPT.json').read_text()); assert receipt['status'].startswith('COMPLETE_')
    for name,h in receipt['files'].items():assert sha256(source/name)==h
    write_json(a.output/'START.json',dict(utc=datetime.now(timezone.utc).isoformat(),script_sha256=sha256(Path(__file__)),
        source_receipt_sha256=sha256(source/'RUN_RECEIPT.json'),contract_sha256=sha256(PKG/'CONTRACT_KO.md'),
        role='IMPLEMENTER_SELF_CHECK',cpu_affinity=p.cpu_affinity(),command=sys.argv))
    with gzip.open(source/'C_ONLY_ONLINE.jsonl.gz','rt') as f:raw={(r['case_id'],r['k']):r for r in map(json.loads,f) if r['corpus']=='dynamic'}
    assert len(raw)==6272
    counts=[];policy=Policy();total=0
    kinds=[('nominal',0.),('missing',1.),('missing',2.),('missing',5.),('delay',1.),('delay',2.),('delay',5.),
           ('reinitialize',0.),('wrong_past_fp',-2.),('wrong_past_fp',2.),('wrong_prior_zero_innovation',0.)]
    fields=['case_id','k','kind','value','history_count','past_nis_mean','past_rejected_count','prior_state',
            'motion_support_absent','trusted_cleared','raw_fp_available','wrong_prior_fixture','recovery_performance']
    with gzip.open(a.output/'HISTORY_CHECKS.csv.gz','wt',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader()
        for path in sorted(source.glob('*_DIAGNOSTICS.npz')):
            cid=path.name.removesuffix('_DIAGNOSTICS.npz')
            with np.load(path) as z:t=z['t'];nis=z['main_nis'];mask=z['shadow_mask']
            mid=len(t)//2;start=t[mid];case_n=0
            for kind,value in kinds:
                for k,now in enumerate(t):
                    idx=np.arange(k); idx=idx[t[:k]>=now-5.]
                    if kind=='delay':idx=idx[t[idx]+value<=now]
                    if kind=='missing':idx=idx[(t[idx]<start)|(t[idx]>=start+value)]
                    if kind=='reinitialize' and k>=mid:idx=idx[idx>=mid]
                    assert np.all(idx<k)
                    v=nis[idx] if kind!='wrong_prior_zero_innovation' else np.zeros(len(idx))
                    state=PriorIntegrity(); previous=raw.get((cid,k-1)); tap=None if previous is None else previous['raw_tap']
                    seeded=None if tap is None else (tap+(value if kind=='wrong_past_fp' else 0))*STEP_M
                    history=RawDetectionHistory(t=None if k==0 else float(t[k-1]),detector_m=seeded,streak=10)
                    support=history.support(float(now),0.,policy,integrity=state)
                    cleared=history.t is None and history.detector_m is None and history.streak==0
                    assert support is None and cleared
                    w.writerow(dict(case_id=cid,k=k,kind=kind,value=value,history_count=len(idx),
                        past_nis_mean=None if not len(idx) else float(np.mean(v)),past_rejected_count=int((~mask[idx]).sum()),
                        prior_state=state.state,motion_support_absent=True,trusted_cleared=cleared,
                        raw_fp_available=tap is not None,wrong_prior_fixture=kind=='wrong_prior_zero_innovation',
                        recovery_performance='NOT_ESTABLISHED_NO_VALID_PROVIDER'))
                    case_n+=1
            total+=case_n;counts.append(dict(case_id=cid,original_rows=len(t),checks=case_n))
            print(cid,case_n,flush=True)
    assert total==6272*len(kinds)
    write_json(a.output/'CHECK.json',dict(status='PASS_EXISTING_GUARD_HISTORY_INTERVENTIONS_ONLY',cases=counts,
        original_rows=6272,checks=total,kinds=kinds,static=0,VALID_count=0,dangerous_VALID_rate=None,
        activation_rate=0.,usefulness='NOT_PASSED',recovery_latency='NOT_ESTABLISHED_NO_PROVIDER',
        zero_innovation_scope='SYNTHETIC_HISTORY_ONLY_NOT_RF_REPLAY',elapsed_s=time.time()-t0,
        csv_sha256=sha256(a.output/'HISTORY_CHECKS.csv.gz'),independent_audit=False,E1_02_started=False,E2_started=False))

if __name__=='__main__':main()
