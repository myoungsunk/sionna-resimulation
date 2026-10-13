"""M1 frozen-data evaluation, fixed RF, paired motion, no online oracle input."""
import sys,json,csv,gzip,time,math,argparse,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from d6_d9_common import check_inputs,original_lut,case_motion,initial_state,wrap,eval_covariance,file_sha
from ekf3 import archived_direct_s_model
from m1_bias_robust_ekf import RobustBiasEKF
from rf_error_model import load_models

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--inputs',type=Path,required=True);ap.add_argument('--structure',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--smoke',action='store_true');a=ap.parse_args()
 a.out.mkdir(exist_ok=False);start=time.time();contract=json.loads((HERE/'experiment_contract.json').read_text());im=json.loads((a.inputs/'MANIFEST.json').read_text())
 for n,h in im['sha256'].items():
  if file_sha(a.inputs/n)!=h:raise RuntimeError('Input cache drift '+n)
 assert json.loads((a.inputs/'M0_PARITY.json').read_text())['status']=='PASS'
 models,rfcontract=load_models(a.structure);(a.out/'RF_ERROR_MODEL_CONTRACT.json').write_text(json.dumps(rfcontract,indent=2))
 p0=check_inputs();lut=original_lut(p0);metrics=[];writer=None
 with gzip.open(a.out/'M1_TRACE.csv.gz','wt',newline='') as trace:
  for case in p0['cases']:
   if a.smoke and case['id']!='R2_aA_m0':continue
   model=archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),tag_height_m=case['robot_z_m'],mount_deg=case['mount_deg'])
   for ch in contract['channels']:
    q=np.load(a.inputs/(case['id']+'_'+ch+'.npz'));t=q['t'];truth=q['truth']
    for rm in contract['range_models']:
     if rm not in q:continue
     mu,cov=models[(case['route'],ch,rm)]
     for condition in (['noise_pair'] if a.smoke else contract['conditions']):
      for level in contract['levels']:
       for seed in ([0] if a.smoke else contract['seeds']):
        mt,mtruth,mpids,motion,oracle=case_motion(p0,case,seed,level,condition)
        assert np.array_equal(t,mt) and np.array_equal(truth,mtruth) and np.array_equal(q['pose_ids'],mpids)
        x0=initial_state(truth[0],seed)
        for arm in contract['arms']:
         f=RobustBiasEKF(x0,contract['bias_prior_std_dps'],contract['bias_rw_dps_sqrt_s']);values=[];times=[]
         for k in range(len(t)):
          tic=time.perf_counter()
          if k:f.predict(float(motion['ds_odom'][k]),float(motion['dtheta_gyro'][k]),float(motion['dt_s'][k]))
          st=f.update(arm,float(q['s'][k]),float(q[rm][k]),model,case['anchor'],case['robot_z_m'],mu,cov,contract['huber_delta'])
          times.append(time.perf_counter()-tic)
          if t[k]<30:continue
          e=f.pose-truth[k];e[2]=wrap(e[2]);nees,hn,cover=eval_covariance(e,f.Ppose)
          row=dict(case=case['id'],channel=ch,range_model=rm,condition=condition,level=level,seed=seed,arm=arm,model='M1',sample_index=k,t_s=t[k],error_x=e[0],error_y=e[1],heading_error_deg=math.degrees(e[2]),pose_NEES=nees,heading_NEES=hn,pose95=int(cover),heading95=int(hn<=3.841458820694124),bias_est_rad_s=f.x[3],bias_true_rad_s=oracle['true_bias_rad_s'][k],bias_std_rad_s=math.sqrt(f.P[3,3]),bias_heading_corr=f.P[2,3]/math.sqrt(f.P[2,2]*f.P[3,3]),NIS=st['NIS'],huber_weight=st.get('huber_weight'),iterations=st['iterations'])
          if writer is None:writer=csv.DictWriter(trace,fieldnames=row);writer.writeheader()
          writer.writerow(row);values.append(row)
         mean=lambda key:float(np.mean([x[key] for x in values]));rms=lambda key:float(np.sqrt(np.mean([x[key]**2 for x in values])))
         metrics.append(dict(case=case['id'],channel=ch,range_model=rm,condition=condition,level=level,seed=seed,arm=arm,model='M1',n=len(values),heading_rmse_deg=rms('heading_error_deg'),xy_rmse_m=float(np.sqrt(np.mean([x['error_x']**2+x['error_y']**2 for x in values]))),mean_pose_NEES=mean('pose_NEES'),mean_heading_NEES=mean('heading_NEES'),pose95=mean('pose95'),heading95=mean('heading95'),bias_rmse_dps=float(np.sqrt(np.mean([(x['bias_est_rad_s']-x['bias_true_rad_s'])**2 for x in values]))*180/np.pi),max_abs_bias_heading_corr=max(abs(x['bias_heading_corr']) for x in values),update_ms_p95=float(np.quantile(times,.95)*1000),update_ms_max=max(times)*1000))
        print(case['id'],ch,rm,condition,seed,len(metrics),flush=True)
 with (a.out/'M1_METRICS.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=metrics[0]);w.writeheader();w.writerows(metrics)
 expected=12 if a.smoke else 504
 if len(metrics)!=expected:raise RuntimeError('Incomplete cells')
 (a.out/'MANIFEST.json').write_text(json.dumps(dict(status='COMPLETED',scientific_PASS=False,elapsed_s=time.time()-start,command=sys.argv,contract=contract,input_manifest_sha256=file_sha(a.inputs/'MANIFEST.json'),rf_contract=rfcontract,rows=len(metrics),E1_scope='WHOLE_ROUTE_EXPLORATORY_NOT_SPATIALLY_INDEPENDENT; masking scores alone does not remove contaminated history',output_sha256={p.name:file_sha(p) for p in a.out.iterdir() if p.is_file()},script_sha256={p.name:file_sha(p) for p in HERE.glob('*.py')}),indent=2))
if __name__=='__main__':main()
