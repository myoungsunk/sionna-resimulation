from pathlib import Path
import csv,json,hashlib,math,sys
from collections import defaultdict
import numpy as np
B=Path(__file__).resolve().parent
R=B.parent/'checkout'
sys.path[:0]=[str(R/'research/EKF3_INDEPENDENT_20261013/diagnostics')]
import run_d5_regimes as d5

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def main():
 receipt=json.loads((B/'D5_EXECUTION_RECEIPT.json').read_text())
 metricpath=B/'D5_MULTI_SEED_FULL_ROUTE_METRICS.csv';assert digest(metricpath)==receipt['csv_sha256']
 metrics=rows(metricpath);assert len(metrics)==4536
 keycols=['case','channel','range_model','condition','level','seed','arm']
 indexed={tuple(r[c] for c in keycols):r for r in metrics};assert len(indexed)==4536
 independent_fields=['heading_rmse_deg','xy_rmse_m','mean_pose_NEES','mean_heading_NEES','pose95','accepted_updates','rejected_updates']
 paired=0
 for key,r in indexed.items():
  case,ch,model,cond,lev,seed,arm=key
  if ch=='full' and model=='E1_FULL_LORO' and arm in ('D0','A'):
   baseline=indexed[(case,ch,'B_OLD',cond,lev,seed,arm)]
   assert all(r[c]==baseline[c] for c in independent_fields);paired+=1
 p0=d5.read_p0();timelines=d5.timelines(p0);cases={c['id']:c for c in p0['cases']}
 checked=0;tracecount=0;motioncount=0;motion_signatures={};maxerr=0.;bytes_verified=0
 for manifestpath in sorted((B/'D5_PARTS').glob('*/*/EVIDENCE_MANIFEST.json')):
  manifest=json.loads(manifestpath.read_text());assert manifest['exit_code']==0
  ev=manifestpath.parent/'evidence'
  for key,rec in manifest['inputs'].items():
   file=ev/rec['file'];assert digest(file)==rec['sha256'];motioncount+=1;bytes_verified+=file.stat().st_size
   if key in motion_signatures:assert motion_signatures[key]==rec['array_signature']
   motion_signatures[key]=rec['array_signature']
  for run in manifest['runs']:
   f=ev/run['trace_file'];assert digest(f)==run['sha256'];tracecount+=1;bytes_verified+=f.stat().st_size
   if not run['key'].endswith('_L2_seed2'):continue
   key=run['key'];case=manifestpath.parent.name
   rest=key[len(case)+1:];ch,rest=rest.split('_',1)
   model='E1_FULL_LORO' if rest.startswith('E1_FULL_LORO_') else 'B_OLD'
   cond=rest[len(model)+1:-len('_L2_seed2')]
   t,truth,pids=timelines[cases[case]['route']]
   with np.load(f,allow_pickle=False) as z:
    assert np.array_equal(z['pose_id'],pids) and np.array_equal(z['t_s'],t)
    assert np.isfinite(z['NIS'][:,1:,1]).all()
    mask=t>=30
    for a,arm in enumerate(['D0','A','B','C']):
     event=0 if arm=='D0' else 1
     x=z['post_x'][mask,a,event];P=z['post_P'][mask,a,event];e=x-truth[mask];e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
     nees=np.einsum('ni,ni->n',e,np.linalg.solve((P+P.transpose(0,2,1))/2,e[...,None])[...,0])
     actual={'heading_rmse_deg':float(np.sqrt(np.mean(np.degrees(e[:,2])**2))),'xy_rmse_m':float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),'mean_pose_NEES':float(np.mean(nees)),'mean_heading_NEES':float(np.mean(e[:,2]**2/P[:,2,2]))}
     row=indexed[(case,ch,model,cond,'2','2',arm)];assert int(row['n'])==int(mask.sum())
     for col,val in actual.items():
      err=abs(float(row[col])-val);maxerr=max(maxerr,err);assert np.isclose(float(row[col]),val,rtol=1e-10,atol=1e-9),(key,arm,col,err)
     checked+=1
 assert tracecount==1134 and checked==504 and paired==756
 groups=defaultdict(list)
 for r in metrics:
  groups[tuple(r[k] for k in ['channel','range_model','condition','level','arm'])].append(r)
 pooled=[]
 for keys,rs in sorted(groups.items()):
  rec=dict(zip(['channel','range_model','condition','level','arm'],keys));n=sum(int(r['n']) for r in rs);rec.update(n=n,n_case_seed=len(rs))
  for col in ['heading_rmse_deg','xy_rmse_m']:rec[col]=math.sqrt(sum(int(r['n'])*float(r[col])**2 for r in rs)/n)
  for col in ['mean_pose_NEES','mean_heading_NEES','pose95']:rec[col]=sum(int(r['n'])*float(r[col]) for r in rs)/n
  pooled.append(rec)
 with (B/'D5_POOLED_METRICS.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(pooled[0]));w.writeheader();w.writerows(pooled)
 out=dict(status='PASS_EXECUTION_EVIDENCE_CHECKS',trajectory_trace_count=tracecount,motion_file_count=motioncount,distinct_paired_motion_streams=len(motion_signatures),D0_A_range_correction_invariance_pairs=paired,metric_rows_recomputed_from_trace=checked,recompute_selection='all 7 cases x 6 conditions x 3 channel/model combinations, level2 seed2, four arms',max_absolute_metric_difference=maxerr,bytes_hash_verified=bytes_verified,scientific_PASS=False)
 (B/'FINAL_VERIFICATION.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
 print(json.dumps([r for r in pooled if r['condition'] in ['noise_pair','all'] and r['level']=='1'],indent=2))
if __name__=='__main__':main()
