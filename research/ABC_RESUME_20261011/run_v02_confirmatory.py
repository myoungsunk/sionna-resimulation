from pathlib import Path
import sys,json,time,hashlib,argparse
import numpy as np,pandas as pd
from scipy.stats import chi2,binom
ap=argparse.ArgumentParser();ap.add_argument('--repo-root',required=True,type=Path);ap.add_argument('--out',required=True,type=Path);args=ap.parse_args()
sys.path[:0]=[str(args.repo_root/'src'),str(args.repo_root/'research/P0_FINISH_20261011'),str(Path(__file__).resolve().parent)]
import V02_stress_repair_check as task
from ckf_candidate import JointCubatureFilter
original=task.F.SensorV2Filter
seeds=np.arange(640,768);models=['ORIGINAL_FIXED_SENSOR_V2','JOINT_STATE_INPUT_CUBATURE_GH9_CANDIDATE'];o=args.out;o.mkdir(parents=True,exist_ok=True)
summary=[];store={};failed=[];start=time.time()
for estimator in models:
 task.F.SensorV2Filter=original if estimator==models[0] else JointCubatureFilter
 for mode in task.MODES:
  vals=[]
  for seed in seeds:
   try: vals.append(task.trial(mode,int(seed)))
   except Exception as e:
    failed.append({'estimator':estimator,'mode':mode,'seed':int(seed),'error':str(e)});raise
  E=np.stack([v[0] for v in vals]);P=np.stack([v[1] for v in vals]);key=estimator+'___'+mode
  store[key+'__error']=E;store[key+'__P6']=P
  store[key+'__prior_error']=np.stack([v[2] for v in vals]);store[key+'__prior_P6']=np.stack([v[3] for v in vals])
  for j,k in enumerate(task.CHECK):
   e=E[:,j,:3];C=P[:,j,:3,:3];nees=np.einsum('ni,ni->n',e,np.linalg.solve(C,e[...,None])[...,0]);n=len(e)
   low,high=chi2.ppf([.025/112,1-.025/112],3*n)/n;cl,ch=binom.ppf([.025/112,1-.025/112],n,.95)/n
   lo56,hi56=chi2.ppf([.025/56,1-.025/56],3*n)/n;cl56,ch56=binom.ppf([.025/56,1-.025/56],n,.95)/n
   cov=(nees<=chi2.ppf(.95,3)).mean();bias=e.mean(0);emp=np.cov(e,rowvar=False);mse=e.T@e/n;pred=C.mean(0)
   summary.append(dict(estimator=estimator,mode=mode,k=k,time_s=k*.2,n_seeds=n,
    mean_pose_NEES=float(nees.mean()),pose95coverage=float(cov),NEES_family112_PASS=bool(low<=nees.mean()<=high),coverage_family112_PASS=bool(cl<=cov<=ch),
    NEES_family56_PASS=bool(lo56<=nees.mean()<=hi56),coverage_family56_PASS=bool(cl56<=cov<=ch56),
    nees_low=float(low),nees_high=float(high),coverage_low=float(cl),coverage_high=float(ch),
    heading_bias_deg=float(np.degrees(bias[2])),position_bias_m=float(np.linalg.norm(bias[:2])),
    heading_RMSE_deg=float(np.degrees(np.sqrt(mse[2,2]))),position_RMSE_m=float(np.sqrt(np.trace(mse[:2,:2]))),
    centered_covariance_trace=float(np.trace(emp)),MSE_trace=float(np.trace(mse)),pred_P_trace=float(np.trace(pred)),
    min_P6_eigenvalue=float(np.min(np.linalg.eigvalsh(P[:,j]))),mean_odom_rejections=float(np.mean([v[4] for v in vals]))))
  pd.DataFrame(summary).to_csv(o/'V02_CONFIRMATORY_CHECKPOINTS.csv',index=False)
  print(estimator,mode,'NEES48',summary[-1]['mean_pose_NEES'],'COV48',summary[-1]['pose95coverage'],'elapsed',round(time.time()-start,2),flush=True)
np.savez_compressed(o/'V02_CONFIRMATORY_TENSORS.npz',**store,seeds=seeds,checkpoints=np.array(task.CHECK))
df=pd.DataFrame(summary)
state=dict(execution='COMPLETE',source_fixed_commit='3bfcae6715bac5a933cc3b8336b6e6fad846c58a',n_filter_runs=2*14*128,n_modes=14,n_estimators=2,seeds=[640,767],checkpoints_s=[0,12,24,48],n_checkpoints=len(df),
 failed_gate_checkpoints=df[~(df.NEES_family112_PASS&df.coverage_family112_PASS)].to_dict('records'),
 original_source_failures_preserved=True,automatic_estimator_adoption=False,stage_A_PASS=False,stage_B_allowed=False,stage_C_allowed=False,
 elapsed_s=time.time()-start,source_sha256={str(p.name):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('ckf_candidate.py'),Path(task.__file__)]})
(o/'STATUS.json').write_text(json.dumps(state,indent=2));print('V02_CONFIRMATORY_COMPLETE',json.dumps({k:v for k,v in state.items() if k!='failed_gate_checkpoints'}),flush=True)
