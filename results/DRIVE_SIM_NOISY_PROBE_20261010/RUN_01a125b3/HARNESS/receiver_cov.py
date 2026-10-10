from pathlib import Path
import sys,json,time,hashlib
import numpy as np,pandas as pd
import body_controls as C
from qclean_uwb.drivesim import observation as O
J=C.J;OUT=J/'RECEIVER_COV';OUT.mkdir(exist_ok=False);rows=[];records=[];start=time.time();freq=C.freq;df=freq[1]-freq[0];dt=1/(4*257*df)
for route in ['R2','R4','R5']:
 for anchor in ['aA','aB']:
  for mount in [0,45]:
   case=f'{route}_{anchor}_m{mount}';poses,full,los,groups=C.casepack(case)
   for gi,g in enumerate(groups):
    ids=np.array([g[i]['pose_id'] for i in [0,2,4]]);hf=np.asarray(full[ids]);hl=np.asarray(los[ids]);of=O.observe(hf,freq,None,None);ol=O.observe(hl,freq,None,None);res=np.r_[of['s']-ol['s'],of['range_m']-ol['range_m']];records.append(dict(case=case,route=route,anchor=anchor,mount=mount,station=gi,x=g[0]['x'],y=g[0]['y'],ids=ids,residual=res))
    # Capture all windows, no selection based on held-out heading outcome.
    for mode,H,obs in [('full',hf,of),('los',hl,ol)]:
     cir=O.cir_batch(H[:,:,:,0]);power=abs(cir)**2;mag=abs(cir);branch=mag.max(1).argmax(1)
     for p in range(3):
      tap=int(obs['index'][p]);peak=int(mag[p,:,branch[p]].argmax());row=dict(case=case,station=gi,pose_id=int(ids[p]),mode=mode,P1_FP=float(obs['power'][p,0]),P2_FP=float(obs['power'][p,1]),s_FP=float(obs['s'][p]),tap=tap,strongest_port=int(branch[p]),peak=peak,receiver_gain='unmeasured; unity model only',CIR_HARDWARE_SUPPORTED='UNKNOWN',cluster_status='RESEARCH_ONLY_MAGNITUDE_SURROGATE')
      for ns in [2,4,8]:
       width=int(round(ns*1e-9/dt));end=min(len(cir[p]),tap+width+1);E=power[p,tap:end].sum(0);row[f'window_{ns}_tap_start']=tap;row[f'window_{ns}_tap_end_exclusive']=end;row[f's_W_{ns}']=(E[0]-E[1])/E.sum();row[f'energy_capture_{ns}']=float(E.sum()/power[p].sum())
      rows.append(row)
    for snr in [30,10]:
     var=O.noise_var_from_snr(snr);rng=np.random.default_rng([20261011,int(route[1]),int(anchor=='aB'),mount,int(ids[0]),snr]);repeats=32;HH=np.repeat(hf[None],repeats,0).reshape(repeats*3,257,2,2);ob=O.observe(HH,freq,var,rng);v=np.concatenate([ob['s'].reshape(repeats,3)-of['s'],ob['range_m'].reshape(repeats,3)-of['range_m']],1);valid=np.isfinite(v).all(1);vv=v[valid];mean=vv.mean(0) if len(vv) else np.full(6,np.nan);cov=np.cov(vv,rowvar=False) if len(vv)>=2 else np.full((6,6),np.nan);eigen=np.linalg.eigvalsh(cov) if np.isfinite(cov).all() else np.full(6,np.nan)
     np.savez_compressed(OUT/f'{case}_g{gi}_snr{snr}_THERMAL.npz',cov_sr=cov,mean_sr=mean,centered_samples=vv-mean,finite_repeats=np.array(valid.sum()),total_repeats=np.array(repeats),order=np.array(['s0','s1','s2','range0','range1','range2']),eigenvalues=eigen,realized_snr_db=O.realised_snr_db(hf,var),noise_var=var,multipath_independent_samples=np.array(1),estimator_applied=np.array(False))
pd.DataFrame(rows).to_csv(J/'FP_CLUSTER_RATIO.csv',index=False)
cal=[]
for r in records:
 # Same geometry repeats and anchors/mounts are not separate physical calibration sites.
 train=[q for q in records if q['route']!=r['route'] and q['anchor']==r['anchor'] and q['mount']==r['mount'] and (q['x'],q['y'])!=(r['x'],r['y'])];unique={}
 for q in train:unique.setdefault((q['x'],q['y']),[]).append(q['residual'])
 vectors=np.array([np.mean(v,axis=0) for v in unique.values()]);n=len(vectors);valid=n>=8 and np.isfinite(vectors).all();mean=vectors.mean(0) if n else np.full(6,np.nan);cov=np.cov(vectors,rowvar=False) if valid else np.full((6,6),np.nan)
 np.savez_compressed(OUT/f"{r['case']}_g{r['station']}_MP_CAL.npz",mean_sr=mean,cov_sr=cov,calibration_site_xy=np.array(list(unique)),calibration_vectors=vectors,held_out_route=np.array(r['route']),independent_site_count=np.array(n),validated=np.array(valid),estimator_applied=np.array(False),model_status=np.array('EMPIRICAL_SPATIAL_CALIBRATION_ONLY; no cross-time pose/noise covariance'))
 cal.append(dict(case=r['case'],station=r['station'],training_sites=n,held_out_route=r['route'],status='SPATIAL_COV_ESTIMATED' if valid else 'COV_NOT_VALIDATED',mean_s0=float(mean[0]),mean_range0=float(mean[3]),s0_variance=float(cov[0,0]),range0_variance=float(cov[3,3]),s0_range0_cov=float(cov[0,3])))
pd.DataFrame(cal).to_csv(J/'COVARIANCE_CALIBRATION_INDEX.csv',index=False)
(J/'RECEIVER_COV_STATUS.json').write_text(json.dumps({'state':'COMPLETED_SPATIAL_DIAGNOSTIC','station_case_groups':len(records),'thermal_repeats':32,'nominal_snr':[30,10],'calibrated_groups':sum(x['status']=='SPATIAL_COV_ESTIMATED' for x in cal),'insufficient_groups':sum(x['status']=='COV_NOT_VALIDATED' for x in cal),'seconds':time.time()-start,'covariance_order':['s0','s1','s2','range0','range1','range2'],'centered_not_RMS':True,'same_H_repeats_not_MP_samples':True,'estimator_applied':False,'joint_inference_cross_time_covariance':'NOT_VALIDATED','gain_calibration':'UNKNOWN; no dB gain drift arm','cluster_primary_window':'NOT_SELECTED; no new cluster LUT; diagnostic only','F01':'OPEN','F02':'OPEN','scientific_PASS':False},indent=2));print('receiver covariance complete',len(records),flush=True)
