"""Run only a separately authorized S1 phase. Preserve completed traces on interruption."""
import datetime,hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
s=Path(__file__).resolve().parent
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def write_json(f,value):f.write_text(json.dumps(value,indent=2,allow_nan=False))
def execute(phase,output):
 from grant import authorize, verify_external
 grant=authorize(phase)
 verify_external()
 from score import score
 from summary import paired_summary
 import parity as p
 token=grant['token'];code=grant['code_commit']
 assert not output.exists(),output
 output.mkdir(parents=True);meta=dict(phase=phase,token=token,code_commit=code,contract_sha256=sha(s.parent/'A0_R3_REFIT/CONTRACT_LOCK.json'),input_sha256=sha(s/'MATERIALIZED_INPUTS.json'),audit_sha256=grant["audit_sha256"],approval_commit=grant["source_commit"],utc_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,arms=['W0','H-d0','W-d0','W-d0-DS'] if phase=='dev' else ['W0','W-d0-DS'])
 write_json(output/'RUN_MANIFEST.json',meta);(output/'FAILURES.jsonl').touch()
 scores=[];records=[]
 try:
  for route in ('R4','R5'):
   for bias in ('B0','L2'):
    for channel in ('Full','Native_LoS'):
     key=f'{route}_aB_m0_{bias}_{channel}';pk=p.read(key)
     for seed in (range(10) if phase=='dev' else range(10,30)):
      ct=p.read(f'{route}_aB_m0_{bias}_{seed}')
      fixed=p.b.pb.gated_mask(pk['z'],pk['muBASE'],pk['R'],ct['ds'],ct['gy'],ct['dt'],np.r_[ct['x0'],0.],pk['P0'],p.spec,p.b.model)
      for arm in meta['arms']:
       stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
       if stop and Path(stop).exists():raise InterruptedError('owner stopped')
       tr=p.online.replay(pk,ct,arm,p.b.core,p.b.model,p.spec)
       assert np.array_equal(tr['mask'],fixed)
       if not all(np.isfinite(v).all() for v in tr.values()):raise ValueError('nonfinite')
       scales=np.array([.1,.1,np.deg2rad(1),np.deg2rad(.05)]);C=tr['P']/scales[None,:,None]/scales[None,None,:]
       ev=np.linalg.eigvalsh(C);tol=1e-12*np.maximum(1,np.linalg.norm(C,ord=2,axis=(1,2)))
       assert np.all(ev[:,0]>=-tol) and np.all(np.linalg.norm(C-C.transpose(0,2,1),ord=2,axis=(1,2))<=tol)
       rec=dict(route=route,bias=bias,channel=channel,seed=seed,arm=arm);name=f'{key}_{seed}_{arm}.npz';f=output/name
       np.savez_compressed(f,**tr,pose_id=pk['pose_id'],r_used=fixed,s_used=fixed&(tr['weight']>0),t=pk['t'],z=pk['z'],D=pk['D'],Rbase=pk['R'])
       truth_file=p.cache.parent/'evaluator_truth'/f'{route}_aB_m0_{bias}.npz'
       assert p.b.sha(truth_file)==p.lock['evaluator_truth/'+truth_file.name]
       with np.load(truth_file) as truth:
        assert np.array_equal(pk['pose_id'],truth['pose_id'])
        epath=p.cache.parent/'evaluator_epsilon_r1'/(key+'.npz')
        assert p.b.sha(epath)==json.loads((s/'EPSILON_INPUTS.json').read_bytes())[epath.name]
        with np.load(epath) as ef:
         assert np.array_equal(ef['pose_id'],pk['pose_id'])
         scores.extend([{**rec,**d} for d in score(pk,tr,truth,channel,ef['epsilon_s'])])
        if phase=='dev' and seed==0 and arm=='W0':
         from same_prior import contrasts
         contrasts(pk,tr,truth,channel).to_csv(output/(key+'_same_prior.csv'),index=False)
       records.append(dict(**rec,file=name,sha256=sha(f),n=len(fixed)))
      print(key,seed,flush=True)
 except Exception as error:
  (output/'FAILURES.jsonl').write_text(json.dumps(dict(error=str(error),context=locals().get('key'),seed=locals().get('seed'),arm=locals().get('arm')))+'\n');raise
 finally:
  pd.DataFrame(scores).to_csv(output/'SCORES_PER_SEED.csv',index=False);write_json(output/'TRACE_INDEX.json',records)
 assert len(records)==320
 paired_summary(pd.DataFrame(scores)).to_csv(output/'PAIRED_SUMMARY.csv',index=False)
 meta.update(utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),n=len(records),status='COMPLETE');write_json(output/'RUN_MANIFEST.json',meta)
if __name__=='__main__':execute(sys.argv[1],Path(sys.argv[2]))
