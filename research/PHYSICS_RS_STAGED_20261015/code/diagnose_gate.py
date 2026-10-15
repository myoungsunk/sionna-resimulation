"""Bounded post-result diagnostics, NOT a replacement of preregistered C2 results.
Two L2 Full cases; exact original scalar implementation vs optimized G5 and
an OFFLINE fixed R0 acceptance schedule counterfactual (not deployable policy).
"""
import io,json,math,zipfile
import numpy as np
import pandas as pd
from common import ROOT,INPUT,OUT,AUDIT,setup_original,require_gate,write_json
from post_validate import independent_score

def decomposition(x,P,truth,t):
 mask=t>=30;e=x[mask,:3]-truth[mask];e[:,2]=np.arctan2(np.sin(e[:,2]),np.cos(e[:,2]))
 order=[2,0,1];C=P[mask,:3,:3][:,order][:,:,order];v=e[:,order]
 L=np.linalg.cholesky(C);w=np.linalg.solve(L,v[...,None])[...,0]
 heading=w[:,0]**2;xy=(w[:,1:]**2).sum(axis=1);n=heading+xy
 cond=L[:,1:,1:]@L[:,1:,1:].transpose(0,2,1)
 return {'pose_NEES_mean':float(n.mean()),'heading_term_mean':float(heading.mean()),
  'conditional_xy_term_mean':float(xy.mean()),'conditional_xy_NEES_share':float(xy.sum()/n.sum()),
  'conditional_xy_narrow_sigma_median_m':float(np.median(np.sqrt(np.linalg.eigvalsh(cond)[:,0]))),
  'top1pct_frames_NEES_share':float(np.sort(n)[-math.ceil(.01*len(n)):].sum()/n.sum())}

def run():
 require_gate('DIAG');setup_original()
 from r2_bias_replay import build_positive_bias_controls,predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD
 from p3_rf_adapter4 import R0,GATE_JOINT,FrozenLut
 from core import gaussian_update
 manifest=json.loads((INPUT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text());cases={c['id']:c for c in manifest['cases']};lut=FrozenLut(root=INPUT)
 ar=zipfile.ZipFile(ROOT.parent/'ekf3_frozen_rf_original.zip');rows=[];parts=[];comparisons=[]
 for name in ['R2_aA_m0','R2_aA_m45']:
  with np.load(io.BytesIO(ar.read(f'P2_OUT/{name}_full_seed0_ONE_STEP.npz')),allow_pickle=False) as a:
   t=a['t_s'];truth=a['truth_for_offline_scoring_only'];obs=np.column_stack([a['z_r_m'],a['z_s']])
  with np.load(OUT/'C2_TRACES'/f'{name}_full_L2.npz',allow_pickle=False) as source:
   j=source['methods'].tolist().index('G5');rs=source['Rs'][:,j].copy();mask0=source['accepted'][:,0].copy()
   reference_x=source['estimate'][:,j].copy();reference_P=source['covariance'][:,j].copy();reference_acc=source['accepted'][:,j].copy()
   for mm in ['R0','G5']:
    jj=source['methods'].tolist().index(mm)
    parts.append({'case':name,'method':mm,**decomposition(source['estimate'][:,jj],source['covariance'][:,jj],truth,t)})
  controls,x0=build_positive_bias_controls(t,truth,'L2',0)
  for method in ['G5_ORIGINAL_SCALAR','G5_FIXED_R0_GATE_DIAGNOSTIC']:
   x=np.r_[x0,0.];P=np.zeros((4,4));P[:3,:3]=np.diag(INITIAL_POSE_STD**2);P[3,3]=BIAS_PRIOR_STD**2
   xx=[];PP=[];accept=[]
   for k in range(len(t)):
    if k:x,P=predict_one(x,P,float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
    R=R0.copy();R[1,1]=rs[k]
    if method=='G5_FIXED_R0_GATE_DIAGNOSTIC':
     ap=bool(mask0[k])
     if ap:x,P,_=gaussian_update(x,P,obs[k],lambda q:lut.model(q,cases[name]),R)
    else:
     x,P,d=gaussian_update(x,P,obs[k],lambda q:lut.model(q,cases[name]),R,gate_threshold=GATE_JOINT);ap=d['accepted']
    xx.append(x.copy());PP.append(P.copy());accept.append(ap)
   xx=np.array(xx);PP=np.array(PP);accept=np.array(accept)
   if method=='G5_ORIGINAL_SCALAR':
    mx=float(np.max(abs(xx-reference_x)));mp=float(np.max(abs(PP-reference_P)))
    assert mx<=1e-12 and mp<=1e-12 and np.array_equal(accept,reference_acc),('OPTIMIZATION_PARITY_FAILURE',name,mx,mp)
    comparisons.append({'case':name,'full_original_scalar_state_max_difference':mx,'cov_max_difference':mp})
   else:
    np.savez_compressed(OUT/f'DIAG_{name}_G5_R0MASK.npz',t_s=t,x=xx,P=PP,accepted=accept,Rs=rs)
   rows.append({'case':name,'method':method,'accepted_eval':int(np.sum(accept&(t>=30))),**independent_score(xx,PP,truth,t,.2)})
   print('DIAG_CASE',name,method,flush=True)
 pd.DataFrame(rows).to_csv(OUT/'DIAG_GATE_METRICS.csv',index=False);pd.DataFrame(parts).to_csv(OUT/'DIAG_NEES_DECOMPOSITION.csv',index=False)
 write_json(OUT/'DIAG_ORIGINAL_SCALAR_PARITY.json',comparisons)
if __name__=='__main__':run()
