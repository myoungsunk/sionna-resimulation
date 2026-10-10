"""Independent saved-array algebra; no generator/filter calls or covariance repair."""
from pathlib import Path
import json,time,hashlib
import numpy as np,pandas as pd
J=Path('/job');start=time.time(); maxima={};counts={};violations=[]
def check(key,actual,expected,tol=1e-9):
 d=float(np.max(np.abs(np.asarray(actual)-expected)));maxima[key]=max(maxima.get(key,0),d);counts[key]=counts.get(key,0)+1
 if not np.isfinite(d) or d>tol:violations.append({'check':key,'difference':d,'tolerance':tol})
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def update(x,P,H,y,R,C):
 S=H@P@H+R+2*H@C;K=(P@H+C)/S;M=np.eye(6)-np.outer(K,H);out=x+K*y;out[2]=wrap(out[2]);cov=M@P@M.T+R*np.outer(K,K)-np.outer(M@C,K)-np.outer(K,M@C)
 return out,(cov+cov.T)/2,S
files=list((J/'BODY_CONTROLS_C_CORRECTED').glob('*/*/STATE_TRACE_C.npz'));allstages=0;negative=0;max_asymmetry=0.;sensor_equal=0
for ap in files:
 with np.load(J/'BODY_CONTROLS'/ap.parent.relative_to(J/'BODY_CONTROLS_C_CORRECTED')/'STATE_TRACE_A.npz') as a:
  sensor={k:a[k].copy() for k in a.files if k.startswith('sensor_')};clock=a['t_s'].copy();x0=a['initial_state'].copy();P0=a['initial_prior'].copy()
 oracle=np.load(ap.parent/'ORACLE_EVAL_ONLY.npz');truth=oracle['true_xypsi'];check('fixed_true_xy',truth[:,:2],np.broadcast_to(truth[0,:2],truth[:,:2].shape),0)
 for fp in ap.parent.glob('STATE_TRACE_*.npz'):
  arm=fp.stem.removeprefix('STATE_TRACE_');z=np.load(fp);manifest=json.loads((ap.parent/f'MANIFEST_{arm}.json').read_text());cfg=manifest['filter_cfg'];b=cfg['wheel_base'];n=len(z['t_s'])
  for key,value in sensor.items():check('paired_sensor_'+key,z[key],value,0)
  check('paired_clock',z['t_s'],clock,0);check('paired_x0',z['initial_state'],x0,0);check('paired_P0',z['initial_prior'],P0,0);sensor_equal+=1
  check('beforeRF_afterRange_x',z['x_before_RF'],z['x_after_range'],0);check('beforeRF_afterRange_P',z['P_before_RF'],z['P_after_range'],0)
  check('measured_delta',z['delta_probe_measured_rad'],np.cumsum(z['sensor_dtheta_gyro'])[z['packet_indices']],0)
  last=int(z['last_valid_sample'])
  for j in range(last+1):
   for stage in ['pred_before_odom','after_odom','after_range','before_RF','after_RF']:
    P=z['P_'+stage][j];ev=np.linalg.eigvalsh(P);tol=512*np.finfo(float).eps*max(np.linalg.norm(P0,2),np.max(abs(ev)));allstages+=1;max_asymmetry=max(max_asymmetry,float(np.max(abs(P-P.T))))
    if ev.min()<-tol or not np.isfinite(P).all():negative+=1;violations.append({'check':'stage_covariance','file':str(fp),'j':j,'stage':stage,'mineigen':float(ev.min())})
   if j:
    xp=z['x_after_RF'][j-1];pp=z['P_after_RF'][j-1];d=z['sensor_ds_odom'][j];g=z['sensor_dtheta_gyro'][j];dt=z['sensor_dt_s'][j];angle=(g-xp[3]*dt)/(1+xp[4]);distance=d-xp[5]*b*angle/4;pr=xp.copy();pr[:2]+=distance*np.sinc(angle/(2*np.pi))*np.array([np.cos(xp[2]+angle/2),np.sin(xp[2]+angle/2)]);pr[2]=wrap(pr[2]+angle)
    check('independent_SE2_prediction',z['x_pred_before_odom'][j],pr);P=z['P_pred_before_odom'][j];H=z['H_odom'][j];Q=z['Q_input'][j];G=z['G'][j];B=np.array([-xp[5]/b,-(1-xp[5]**2/4)/(1+xp[4]),1.]);C=-G@Q@B;R=B@Q@B
    check('odom_C',z['C_odom'][j],C);check('odom_R',z['odom_R'][j],R);check('prediction_P',P,z['F'][j]@pp@z['F'][j].T+G@Q@G.T)
    joint=np.block([[P,C[:,None]],[C[None,:],np.array([[R]])]]);ev=np.linalg.eigvalsh(joint)
    if ev.min()<-1e-10:violations.append({'check':'joint_cov','eigen':float(ev.min())})
    S=H@P@H+R+2*H@C;check('odom_S',z['odom_S'][j],S)
    out,cov,_=update(pr,P,H,z['odom_innovation'][j],R,C) if z['odom_status'][j]=='applied' else (pr,P,S)
    cov[3,3]+=cfg['bias_rw_std']**2*dt;check('odom_posterior_x',z['x_after_odom'][j],out);check('odom_posterior_P',z['P_after_odom'][j],cov)
   for m,pre,post in [('range','after_odom','after_range'),('s','before_RF','after_RF')]:
    st=z[m+'_status'][j];xp=z['x_'+pre][j];P=z['P_'+pre][j]
    if st in ['applied','rejected','zero_variance']:
     H=z['H_'+m][j];R=z[m+'_R'][j];S=H@P@H+R;check(m+'_S',z[m+'_S'][j],S)
     if S>0:check(m+'_NIS',z[m+'_NIS'][j],z[m+'_innovation'][j]**2/S)
     out,cov,_=update(xp,P,H,z[m+'_innovation'][j],R,np.zeros(6)) if st=='applied' else (xp,P,S)
    else:out,cov=xp,P
    check(m+'_posterior_x',z['x_'+post][j],out);check(m+'_posterior_P',z['P_'+post][j],cov)
  if manifest['status']=='COMPLETED':
   e=truth[last]-z['x_after_RF'][last,:3];e[2]=wrap(e[2]);P=z['P_after_RF'][last,:3,:3];ne=e@np.linalg.solve(P,e);check('endpoint_NEES',manifest['nees_pose_df3'],ne)
result={'passed':not violations,'checks':counts,'max_abs_difference':maxima,'violations':violations[:100],'total_violation_count':len(violations),'station_noise_tasks':len(files),'arm_traces':sensor_equal,'covariance_stage_samples':allstages,'invalid_covariance_count':negative,'max_covariance_asymmetry':max_asymmetry,'seconds':time.time()-start,'scope':'independent saved-array transition/update algebra, paired inputs and PSD guard; not physical motion validation; no tuning'}
(J/'CONTROL_INDEPENDENT_CHECK_C_CORRECTED.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ['checks','max_abs_difference','violations']}),flush=True)
assert result['passed'],result
