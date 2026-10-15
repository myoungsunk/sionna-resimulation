"""Exploratory EKF R_s ablation using ONLY previously frozen out-of-route predictions.
Same-prior common-gate one-step and paired recursive R2; no bias clamping.
"""
from __future__ import annotations
import argparse,hashlib,io,json,math,zipfile
import numpy as np
import pandas as pd
from common import ROOT,INPUT,OUT,AUDIT,sha,write_json,require_gate,setup_original
from features import GROUPS
METHODS=['R0']+list(GROUPS)

def metric(x,P,true,t,truebias=None):
 mask=t>=30;e=x[mask,:3]-true[mask,:3];e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
 C=P[mask,:3,:3]
 assert np.isfinite(x).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
 nh=e[:,2]**2/C[:,2,2];ne=np.einsum('bi,bi->b',e,np.linalg.solve(C,e[...,None])[...,0])
 row={'n':int(mask.sum()),'heading_RMSE_deg':float(np.rad2deg(np.sqrt(np.mean(e[:,2]**2)))),
 'position_RMSE_m':float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
 'heading_NEES':float(np.mean(nh)),'pose_NEES':float(np.mean(ne)),
 'heading95':float(np.mean(nh<=3.841458820694124)),'pose95':float(np.mean(ne<=7.814727903251179)),
 'heading_sigma_rms_deg':float(np.rad2deg(np.sqrt(np.mean(C[:,2,2]))))}
 if truebias is not None:
  be=x[mask,3]-math.radians(truebias);pb=P[mask,3,3]
  row.update({'bias_RMSE_dps':float(np.rad2deg(np.sqrt(np.mean(be**2)))),
    'bias_final_dps':float(np.rad2deg(x[-1,3])),
    'bias95':float(np.mean(be**2<=3.841458820694124*pb))})
 return row

def table_sources():
 bf=json.loads((OUT/'B_FINAL.json').read_text());assert bf['status']=='HELDOUT_EVALUATION_COMPLETE'
 assert sha(OUT/'B_OOF_PREDICTIONS.csv.gz')==bf['predictions_sha256']
 tab=pd.read_csv(OUT/'B_OOF_PREDICTIONS.csv.gz')
 assert not tab.duplicated(['case','channel','pose_id','group']).any()
 return tab.set_index(['case','channel','pose_id','group'])

def r_sequences(tab,case,ch,ids):
 cols=[]
 for m in METHODS:
  keys=pd.MultiIndex.from_tuples([(case,ch,int(i),m) for i in ids],names=tab.index.names)
  rr=tab.loc[keys,'R_eff'].to_numpy(float)
  assert len(rr)==len(ids) and np.isfinite(rr).all() and np.all(rr>=.0081) and np.all(rr<=.81)
  cols.append(rr)
 return np.column_stack(cols)

def load_original():
 setup_original()
 from p3_rf_adapter4 import FrozenLut,R0,GATE_JOINT
 from core import gaussian_update
 from r2_bias_replay import predict_one,build_positive_bias_controls,INITIAL_POSE_STD,BIAS_PRIOR_STD,filter_one
 manifest=json.loads((INPUT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
 cases={x['id']:x for x in manifest['cases']}
 lut=FrozenLut(root=INPUT)
 return cases,lut,R0,GATE_JOINT,gaussian_update

def archive_iter():
 ar=ROOT.parent/'ekf3_frozen_rf_original.zip'
 assert sha(ar)=='88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63'
 with zipfile.ZipFile(ar) as z:
  summary=json.loads(z.read('P2_OUT/P2_ONE_STEP_SUMMARY.json'))
  for d in summary['per_case']:
   b=z.read('P2_OUT/'+d['trace_file']);assert hashlib.sha256(b).hexdigest()==d['trace_sha256']
   with np.load(io.BytesIO(b),allow_pickle=False) as f: yield d['case'],d['channel'],{k:f[k].copy() for k in f.files}

def frozen_batch_update(mu,P,z,h,H,R,accepted):
 """Vectorized Joseph update; compared against scalar original on all saved partial outputs."""
 S=H@P@H.transpose(0,2,1)+R
 K=np.linalg.solve(S,H@P).transpose(0,2,1)
 y=mu+(K@(z-h)[...,None])[...,0]
 y[:,2]=(y[:,2]+np.pi)%(2*np.pi)-np.pi
 A=np.eye(4)[None,:,:]-K@H
 C=A@P@A.transpose(0,2,1)+K@R@K.transpose(0,2,1)
 C=(C+C.transpose(0,2,1))/2
 y[~accepted]=mu[~accepted];C[~accepted]=P[~accepted]
 assert np.isfinite(y).all() and np.isfinite(C).all() and np.linalg.eigvalsh(C).min()>0
 return y,C

def one_step():
 require_gate('C');tab=table_sources();cases,lut,R0,gate,gu=load_original()
 rows=[];parities=[];(OUT/'C1_TRACES').mkdir(exist_ok=True)
 for case,ch,d in archive_iter():
  n=len(d['t_s']);Rs=r_sequences(tab,case,ch,d['pose_id']);xx=np.zeros((n,len(METHODS),4));PP=np.zeros((n,len(METHODS),4,4));acc=d['status'][:,2]=='applied'
  mu=np.column_stack([d['xminus'],np.zeros(n)])
  P=np.zeros((n,4,4));P[:,:3,:3]=d['Pminus'];P[:,3,3]=math.radians(.1)**2
  z=np.column_stack([d['z_r_m'],d['z_s']])
  mh=[lut.model(x,cases[case]) for x in mu];h=np.array([v[0] for v in mh]);H=np.array([v[1] for v in mh])
  for j,m in enumerate(METHODS):
   R=np.tile(R0,(n,1,1));R[:,1,1]=Rs[:,j]
   xx[:,j],PP[:,j]=frozen_batch_update(mu,P,z,h,H,R,acc)
  slow=AUDIT/'C1_PARTIAL_ORIGINAL_SCALAR'/f'{case}_{ch}.npz'
  if slow.exists():
   with np.load(slow,allow_pickle=False) as old:
    assert np.max(abs(xx-old['estimate']))<=1e-9 and np.max(abs(PP-old['covariance']))<=1e-9,('BATCH_SCALAR_DIVERGENCE',case,ch)
  dx=xx[:,0,:3]-d['xplus'][:,2,:];dx[:,2]=(dx[:,2]+np.pi)%(2*np.pi)-np.pi
  dp=float(np.max(abs(PP[:,0,:3,:3]-d['Pplus'][:,2])))
  mx=float(np.max(abs(dx)));assert mx<=1e-9 and dp<=1e-9,('C1_ARCHIVED_BASELINE_PARITY',case,ch,mx,dp)
  parities.append({'case':case,'channel':ch,'max_state':mx,'max_cov':dp})
  for j,m in enumerate(METHODS):
   rr=Rs[d['t_s']>=30,j]
   rows.append({'case':case,'channel':ch,'method':m,'common_accepted_eval':int(np.sum(acc&(d['t_s']>=30))),
    'R_median':float(np.median(rr)),'R_p95':float(np.quantile(rr,.95)),**metric(xx[:,j],PP[:,j],d['truth_for_offline_scoring_only'],d['t_s'])})
  np.savez_compressed(OUT/'C1_TRACES'/f'{case}_{ch}.npz',t_s=d['t_s'],pose_id=d['pose_id'],methods=METHODS,estimate=xx,covariance=PP,Rs=Rs,accepted=acc)
  print('C1_CASE',case,ch,flush=True)
 pd.DataFrame(rows).to_csv(OUT/'C1_METRICS.csv',index=False)
 write_json(OUT/'C1_PARITY.json',parities)
 write_json(OUT/'C1_FINAL.json',{'status':'ONE_STEP_EXPLORATORY_COMPLETE','metric_rows':len(rows),'methods':METHODS,
 'common_gate':True,'max_archived_state_discrepancy':max(x['max_state'] for x in parities),'scientific_PASS':False})


def fast_predict(x,P,ds,gyro,dt):
 """Exact original transition/Q/Joseph algebra; retain finite/PD guard at every step."""
 from core import transition
 y,F,G=transition(x,ds,gyro,dt)
 Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
 P=(P+P.T)/2;C=F@P@F.T+G@Q@G.T;C=(C+C.T)/2
 if not np.isfinite(y).all() or not np.isfinite(C).all() or np.linalg.eigvalsh(C).min()<=0:raise RuntimeError('INVALID_PREDICTION')
 return y,C

def fast_update(x,P,z,model,R,gate):
 h,H=model(x.copy());P=(P+P.T)/2;R=(R+R.T)/2
 if not np.isfinite(np.r_[x,z,h,H.ravel(),P.ravel(),R.ravel()]).all():raise RuntimeError('NONFINITE_INPUT')
 nu=z-h;S=H@P@H.T+R;S=(S+S.T)/2
 nis=float(nu@np.linalg.solve(S,nu));K=np.linalg.solve(S,H@P).T
 y=x.copy();C=P.copy();accepted=nis<=gate
 if accepted:
  y+=K@nu;y[2]=(y[2]+np.pi)%(2*np.pi)-np.pi
  A=np.eye(4)-K@H;C=A@P@A.T+K@R@K.T;C=(C+C.T)/2
 if np.linalg.eigvalsh(C).min()<=0 or not np.isfinite(C).all():raise RuntimeError('INVALID_JOSEPH')
 return y,C,nis,accepted

def recursive_filter(t,controls,obs,case,lut,x0,rs):
 """No truth/labels/features evaluated here; frozen measured-packet Rs only."""
 from core import gaussian_update
 from p3_rf_adapter4 import R0,GATE_JOINT
 from r2_bias_replay import predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD,filter_one
 n=len(t);p0=np.zeros((4,4));p0[:3,:3]=np.diag(INITIAL_POSE_STD**2);p0[3,3]=BIAS_PRIOR_STD**2
 xx=np.zeros((n,len(METHODS),4));PP=np.zeros((n,len(METHODS),4,4));nis=np.zeros((n,len(METHODS)));accepted=np.zeros((n,len(METHODS)),bool)
 for j,m in enumerate(METHODS):
  x=np.r_[x0,0.];P=p0.copy()
  for k in range(n):
   if k:
    predict_fn=predict_one if m=='R0' else fast_predict
    x,P=predict_fn(x,P,float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
   if m=='R0':
    x,P,status,NIS=filter_one(x,P,obs[k],'J4',case,lut);ap=status=='APPLIED'
   else:
    R=R0.copy();R[1,1]=float(rs[k,j])
    x,P,NIS,ap=fast_update(x,P,obs[k],lambda q:lut.model(q,case),R,GATE_JOINT)
   xx[k,j]=x;PP[k,j]=P;nis[k,j]=NIS;accepted[k,j]=ap
 return xx,PP,nis,accepted

def recursive(part=None):
 require_gate('C');tab=table_sources();cases,lut,R0,gate,gu=load_original()
 from r2_bias_replay import build_positive_bias_controls,BIAS_LEVELS,run_filters
 traces={(c,ch):d for c,ch,d in archive_iter() if c in ('R2_aA_m0','R2_aA_m45')}
 rows=[];par=[];(OUT/'C2_TRACES').mkdir(exist_ok=True)
 baseline=ROOT.parent/'r2_bias_results.zip'
 assert sha(baseline)=='ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399'
 with zipfile.ZipFile(baseline) as zb:
  for ilevel,(level,bias) in enumerate(BIAS_LEVELS.items()):
   if part is not None and ilevel!=part:continue
   for (case,ch),d in traces.items():
    t=d['t_s'];rs=r_sequences(tab,case,ch,d['pose_id']);truth=d['truth_for_offline_scoring_only']
    controls,x0=build_positive_bias_controls(t,truth,level,0)
    obs=np.column_stack([d['z_r_m'],d['z_s']])
    xx,PP,nis,acc=recursive_filter(t,controls,obs,cases[case],lut,x0,rs)
    with np.load(io.BytesIO(zb.read(f'_temp/r2_bias_replay/{case}_{ch}_{level}_seed0_recursive.npz')),allow_pickle=False) as ar:
     j=int(np.flatnonzero(ar['names']=='J4')[0]);dx=xx[:,0]-ar['estimate'][:,j];dx[:,2]=(dx[:,2]+np.pi)%(2*np.pi)-np.pi
     row={'case':case,'channel':ch,'level':level,'archive_max_state':float(np.max(abs(dx))),
        'archive_max_cov':float(np.max(abs(PP[:,0]-ar['covariance'][:,j]))),
        'archive_gate_differences':int(np.sum(acc[:,0]!=(ar['status'][:,j]=='APPLIED')))}
    row['archive_strict_1e9_pass']=row['archive_max_state']<=1e-9 and row['archive_max_cov']<=1e-9 and row['archive_gate_differences']==0
    # Each level uses one same-environment complete original multi-arm comparator.
    # No historical tolerance is relaxed. Both parities are kept independently.
    if case=='R2_aA_m0' and ch=='full':
     ref=run_filters(t,controls,obs,cases[case],lut,x0)['recursive'];jj=5
     samex=float(np.max(abs(xx[:,0]-ref['estimate'][:,jj])));samep=float(np.max(abs(PP[:,0]-ref['covariance'][:,jj])))
     assert samex<=1e-12 and samep<=1e-12,('SAME_ENV_REFERENCE_PARITY',samex,samep)
     assert np.array_equal(acc[:,0],ref['status'][:,jj]=='APPLIED')
     row['same_env_original_max_state']=samex;row['same_env_original_max_cov']=samep
    par.append(row)
    for j,m in enumerate(METHODS):
     rr=rs[t>=30,j]
     rows.append({'case':case,'channel':ch,'level':level,'true_bias_dps':bias,'method':m,
      'accepted_eval':int(np.sum(acc[:,j]&(t>=30))),'rejected_eval':int(np.sum(~acc[:,j]&(t>=30))),
      'R_median':float(np.median(rr)),'R_p95':float(np.quantile(rr,.95)),
      **metric(xx[:,j],PP[:,j],truth,t,bias)})
    np.savez_compressed(OUT/'C2_TRACES'/f'{case}_{ch}_{level}.npz',t_s=t,pose_id=d['pose_id'],methods=METHODS,estimate=xx,covariance=PP,Rs=rs,nis=nis,accepted=acc)
    print('C2_CASE',case,ch,level,flush=True)
 suffix='' if part is None else f'_{part}'
 pd.DataFrame(rows).to_csv(OUT/f'C2_METRICS{suffix}.csv',index=False)
 write_json(OUT/f'C2_PARITY{suffix}.json',par)
 write_json(OUT/f'C2_FINAL{suffix}.json',{'status':'RECURSIVE_EXPLORATORY_COMPLETE','rows':len(rows),'scientific_PASS':False})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['one','recursive']);p.add_argument('--part',type=int);a=p.parse_args()
 if a.phase=='one':one_step()
 else:recursive(a.part)
