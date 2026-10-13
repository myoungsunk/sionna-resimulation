from pathlib import Path
import sys,json,concurrent.futures,time
import numpy as np,pandas as pd
J=Path('/job');sys.path.insert(0,str(J/'source/src'))
from qclean_uwb.drivesim import observation as O
from qclean_uwb.drivesim.hs_lut import HsLut,s_model
B=Path('/input/BLOCK_C');L=Path('/lut');meta=json.loads((L/'hs_lut_meta.json').read_text())['meta'];lut=HsLut(dict(theta_deg=meta['theta_deg'],phi_deg=np.arange(meta['phi_deg'][0],meta['phi_deg'][1]+.01,meta['phi_deg'][2]),s=np.load(L/'hs_lut_2deg.npy')))
def calc(c):
 name=c['case'];H=np.load(B/'FULL_RF'/f'H_{name}.npy',mmap_mode='r');freq=np.load(B/'freqs_hz.npy');z=O.cir_batch(H[...,0]);mag=abs(z);p=mag**2;n=len(z);fp=np.load(J/'OBS'/f'{name}_full.npz');los=np.load(J/'OBS'/f'{name}_los.npz');samples=json.loads((B/name/'SAMPLES.json').read_text());dt_ns=1e9/(z.shape[1]*(freq[1]-freq[0]));rows=[];labels=[]
 for k,r in enumerate(samples):
  tap=int(fp['index'][k]);f={'case':name,'route':name[:2],'pose_id':r['pose_id'],'station_group':name[:2]+f"_{r['x']:.6f}_{r['y']:.6f}",'s':float(fp['s'][k]),'range_m':float(fp['range_m'][k]),'tap':tap,'branch':int(fp['branch'][k]),'peak':float(fp['peak'][k]),'power1':float(fp['power'][k,0]),'power2':float(fp['power'][k,1]),'detected':bool(fp['detected'][k]),'noise_floor':0.,'snr_requested':'noise_free','window_available':bool(tap+81<=len(p[k]))}
  early=[];ds=[];shapes=[]
  for rx in range(2):
   window=p[k,tap:tap+81,rx];tt=np.arange(len(window))*dt_ns;weights=window/window.sum() if window.sum()>0 else np.full(len(window),np.nan);mean=np.sum(weights*tt);ds.append(np.sqrt(np.sum(weights*(tt-mean)**2)));win80=p[k,tap:tap+80,rx];fraction=p[k,tap:tap+8,rx].sum()/win80.sum() if win80.sum()>0 else np.nan;early.append(fraction);peakidx=int(np.argmax(p[k,:,rx]));a=mag[k,:,rx];peak=a.max();i10=np.flatnonzero(a>=.1*peak);i90=np.flatnonzero(a>=.9*peak);shape=p[k,tap:tap+16,rx]+1e-12;shape=shape/shape.sum();shapes.append(shape)
   f.update({f'D1_rx{rx+1}_ns':float(ds[-1]),f'D2_rx{rx+1}':float(fraction),f'D3_rx{rx+1}':float(p[k,peakidx,rx]/max(p[k,tap,rx],1e-12)),f'D4_rx{rx+1}_ns':float((i90[0]-i10[0])*dt_ns) if len(i10) and len(i90) else np.nan})
  q1,q2=shapes;m=(q1+q2)/2;f['D1_mean_ns']=float(np.mean(ds));f['D1_diff_ns']=float(ds[0]-ds[1]);f['P1_jsd']=float(.5*np.sum(q1*np.log(q1/m))+.5*np.sum(q2*np.log(q2/m)));f['P2_peak_difference_ns']=float((np.argmax(p[k,tap:tap+16,0])-np.argmax(p[k,tap:tap+16,1]))*dt_ns);f['P3_early_asymmetry']=abs(early[0]-early[1]);f['P4_shape_L1']=float(abs(q1-q2).sum());f['P5_s']=float(fp['s'][k]);f['P5_log_power']=float(np.log10(max(fp['power'][k].sum(),1e-300)));rows.append(f)
  h=s_model(lut,c['anchor_xyz'],c['robot_z'],r['x'],r['y'],np.radians(r['yaw_body_deg']),c['mount_deg']);d=np.linalg.norm(np.array([r['x'],r['y'],c['robot_z']])-c['anchor_xyz']);labels.append({'case':name,'route':name[:2],'pose_id':r['pose_id'],'true_x':r['x'],'true_y':r['y'],'true_yaw_deg':r['yaw_body_deg'],'true_distance_m':d,'s_lut_truth':float(h),'s_los':float(los['s'][k]),'e_s':float(fp['s'][k]-h),'e_MP':float(fp['s'][k]-los['s'][k]),'e_range':float(fp['range_m'][k]-d),'range_los':float(los['range_m'][k]),'tap_los':int(los['index'][k])})
 np.savez_compressed(J/'OUTPUT'/f'CIR_AMPLITUDE_{name}.npz',amplitude=mag.astype(np.float64),dt_ns=dt_ns,pose_id=np.array([r['pose_id'] for r in samples]),source='noise-free H TX0; phase excluded from inference')
 return pd.DataFrame(rows),pd.DataFrame(labels)
if __name__=='__main__':
 start=time.time();cases=json.loads((B/'CASES.json').read_text())
 with concurrent.futures.ProcessPoolExecutor(max_workers=7) as ex:data=list(ex.map(calc,cases))
 features=pd.concat([r[0] for r in data],ignore_index=True);labels=pd.concat([r[1] for r in data],ignore_index=True);assert not features.duplicated(['case','pose_id']).any();features.to_csv(J/'OUTPUT/01_FEATURES.csv',index=False);labels.to_csv(J/'OUTPUT/02_LABELS_EVAL_ONLY.csv',index=False)
 joined=features.merge(labels,on=['case','route','pose_id'],validate='one_to_one');joined['distance_bin']=pd.cut(joined.true_distance_m,[0,5,10,np.inf],right=False).astype(str);summary=[]
 for key,g in joined.groupby(['case','distance_bin'],observed=True):
  r={'case':key[0],'distance_bin':key[1],'n':len(g),'descriptive_only':len(g)<20}
  for col in ['e_s','e_MP','e_range']:v=g[col].to_numpy();r.update({col+'_mean':float(np.mean(v)),col+'_variance_ddof0':float(np.var(v)),col+'_rms':float(np.sqrt(np.mean(v*v)))})
  summary.append(r)
 pd.DataFrame(summary).to_csv(J/'OUTPUT/03_DISTANCE_BIAS_VAR.csv',index=False)
 (J/'OUTPUT/FEATURE_STATUS.json').write_text(json.dumps({'state':'completed','rows':len(features),'seconds':time.time()-start,'noise':'noise-free primary','hardware_CIR_access':'UNKNOWN','heading_label':'not yet computed','oracle_columns_separate':True,'unresolved_path_labels':'not available from these H arrays alone'},indent=2));print('feature rows',len(features),'seconds',time.time()-start,flush=True)
