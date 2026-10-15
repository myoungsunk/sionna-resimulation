"""Independent result read-back, Cholesky-score validation, and historical-local-step diagnostics.
Input source and every completed stage receipt are checked before scored output is accepted.
"""
from __future__ import annotations
import io,json,math,zipfile
import numpy as np
import pandas as pd
from common import ROOT,INPUT,OUT,AUDIT,sha,write_json,require_gate,setup_original

def independent_score(x,P,truth,t,bias=None):
 keep=t>=30;er=x[keep,:3]-truth[keep]
 er[:,2]=np.arctan2(np.sin(er[:,2]),np.cos(er[:,2]))
 C=P[keep,:3,:3]
 L=np.linalg.cholesky(C);whitened=np.linalg.solve(L,er[...,None])[...,0]
 nees=np.sum(whitened*whitened,axis=1)
 hn=er[:,2]**2/C[:,2,2]
 result={'n':int(keep.sum()),'heading_RMSE_deg':float(np.sqrt(np.dot(er[:,2],er[:,2])/len(er))*180/np.pi),
 'position_RMSE_m':float(np.sqrt(np.sum(er[:,:2]*er[:,:2])/len(er))),
 'heading_NEES':float(hn.sum()/len(hn)),'pose_NEES':float(nees.sum()/len(nees)),
 'heading95':float(np.sum(abs(er[:,2])<=np.sqrt(3.841458820694124*C[:,2,2]))/len(er)),
 'pose95':float(np.sum(nees<=7.814727903251179)/len(er)),
 'heading_sigma_rms_deg':float(np.sqrt(C[:,2,2].sum()/len(er))*180/np.pi)}
 if bias is not None:
  e=x[keep,3]-bias*np.pi/180
  result.update({'bias_RMSE_dps':float(np.sqrt(np.dot(e,e)/len(e))*180/np.pi),
  'bias_final_dps':float(x[-1,3]*180/np.pi),
  'bias95':float(np.mean(abs(e)<=np.sqrt(3.841458820694124*P[keep,3,3])))})
 return result

def verify():
 require_gate('POST');setup_original()
 # Do not import the inference metric helper: calculate scores independently above.
 combined=pd.concat([pd.read_csv(OUT/f'C2_METRICS_{k}.csv') for k in range(4)],ignore_index=True)
 assert len(combined)==112 and not combined.duplicated(['case','channel','level','method']).any()
 combined.to_csv(OUT/'C2_METRICS.csv',index=False)
 par=sum([json.loads((OUT/f'C2_PARITY_{k}.json').read_text()) for k in range(4)],[])
 write_json(OUT/'C2_PARITY.json',par)
 c1=pd.read_csv(OUT/'C1_METRICS.csv');assert len(c1)==98
 predictions=pd.read_csv(OUT/'B_OOF_PREDICTIONS.csv.gz').set_index(['case','channel','pose_id','group'])
 assert len(predictions)==152304 and not predictions.index.duplicated().any()
 ar=zipfile.ZipFile(ROOT.parent/'ekf3_frozen_rf_original.zip')
 checks=[];cov_count=0;max_metric_error=0.
 for phase,table,folder in [('C1',c1,'C1_TRACES'),('C2',combined,'C2_TRACES')]:
  groupby=['case','channel']+(['level'] if phase=='C2' else [])
  for key,g in table.groupby(groupby):
   case,ch=key[:2];level=key[2] if len(key)==3 else None
   name=f'{case}_{ch}'+(f'_{level}' if level else '')+'.npz'
   with np.load(OUT/folder/name,allow_pickle=False) as r:
    xx=r['estimate'];pp=r['covariance'];t=r['t_s'];ids=r['pose_id'];rs=r['Rs'];methods=r['methods'].tolist()
    assert np.isfinite(xx).all() and np.isfinite(pp).all() and np.isfinite(rs).all()
    assert np.max(abs(pp-pp.swapaxes(-1,-2)))<1e-12
    mineig=float(np.linalg.eigvalsh(pp).min());assert mineig>0
    cov_count+=len(t)*len(methods)
    with np.load(io.BytesIO(ar.read(f'P2_OUT/{case}_{ch}_seed0_ONE_STEP.npz')),allow_pickle=False) as original:
     truth=original['truth_for_offline_scoring_only'].copy()
     np.testing.assert_array_equal(ids,original['pose_id']);np.testing.assert_array_equal(t,original['t_s'])
    for j,m in enumerate(methods):
     row=g[g.method==m].iloc[0]
     expected_rs=predictions.loc[[(case,ch,int(i),m) for i in ids],'R_eff'].to_numpy()
     np.testing.assert_array_equal(rs[:,j],expected_rs)
     score=independent_score(xx[:,j],pp[:,j],truth,t,float(row.true_bias_dps) if phase=='C2' else None)
     for k,v in score.items():
      error=abs(v-float(row[k]));max_metric_error=max(max_metric_error,error)
      assert error<=1e-9*max(1.,abs(v)),('INDEPENDENT_METRIC_DIFFERENCE',phase,key,m,k,error)
    checks.append({'phase':phase,'case':case,'channel':ch,'level':level,'frames':len(t),'methods':len(methods),'min_cov_eigenvalue':mineig})
 write_json(OUT/'POST_VALIDATION.json',{'status':'PASS_WITH_EXPLICIT_ARCHIVE_CAVEAT','metric_rows':210,
   'covariance_matrices_verified':cov_count,'max_independent_metric_abs_error':max_metric_error,
   'cases':checks,'historical_strict_parity_failed':sum(not r['archive_strict_1e9_pass'] for r in par),
   'new_same_environment_reference_state_max':max(r.get('same_env_original_max_state',0) for r in par),
   'original_inputs_unchanged':True,'scientific_PASS':False})
 print('POST_VALIDATION',cov_count,max_metric_error,flush=True)

def numerical_diagnostic():
 require_gate('POST');setup_original()
 from r2_bias_replay import build_positive_bias_controls,predict_one,filter_one,BIAS_LEVELS,INITIAL_POSE_STD,BIAS_PRIOR_STD
 from p3_rf_adapter4 import FrozenLut
 manifest=json.loads((INPUT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
 case=next(c for c in manifest['cases'] if c['id']=='R2_aA_m0');lut=FrozenLut(root=INPUT)
 zo=zipfile.ZipFile(ROOT.parent/'ekf3_frozen_rf_original.zip');zb=zipfile.ZipFile(ROOT.parent/'r2_bias_results.zip')
 with np.load(io.BytesIO(zo.read('P2_OUT/R2_aA_m0_full_seed0_ONE_STEP.npz')),allow_pickle=False) as f:
  t=f['t_s'];truth=f['truth_for_offline_scoring_only'];z=np.column_stack([f['z_r_m'],f['z_s']])
 result=[]
 for level,bias in BIAS_LEVELS.items():
  controls,x0=build_positive_bias_controls(t,truth,level,0)
  with np.load(io.BytesIO(zb.read(f'_temp/r2_bias_replay/R2_aA_m0_full_{level}_seed0_recursive.npz')),allow_pickle=False) as a:
   j=int(np.flatnonzero(a['names']=='J4')[0]);xs=a['estimate'][:,j];ps=a['covariance'][:,j]
   maxx=maxp=0.;flips=0
   for k in range(len(t)):
    if k:
     x,P=predict_one(xs[k-1],ps[k-1],float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
    else:
     x=np.r_[x0,0.];P=np.zeros((4,4));P[:3,:3]=np.diag(INITIAL_POSE_STD**2);P[3,3]=BIAS_PRIOR_STD**2
    x,P,status,nis=filter_one(x,P,z[k],'J4',case,lut)
    dx=x-xs[k];dx[2]=np.arctan2(np.sin(dx[2]),np.cos(dx[2]))
    maxx=max(maxx,float(np.max(abs(dx))));maxp=max(maxp,float(np.max(abs(P-ps[k]))));flips+=status!=a['status'][k,j]
   result.append({'level':level,'one_local_step_max_state_error':maxx,'one_local_step_max_cov_error':maxp,'gate_differences':int(flips)})
 write_json(OUT/'ARCHIVE_LOCAL_STEP_DIAGNOSTIC.json',{'original_tolerance_not_relaxed':True,'local_steps':result,
   'interpretation':'Local-step numeric reproduction and same-environment complete trajectory tests separate numerical reproducibility from feature intervention. Exact cause of cross-environment accumulated discrepancy not proven.'})
 print('LOCAL_STEP_DIAGNOSTIC',result,flush=True)
if __name__=='__main__':verify();numerical_diagnostic()
