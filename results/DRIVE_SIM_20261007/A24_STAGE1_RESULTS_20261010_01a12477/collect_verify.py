from pathlib import Path
import json,hashlib,csv,shutil,tarfile,sys
import numpy as np,pandas as pd
J=Path('/job');SRC=J/'source';R=Path('/routes/source/results/DRIVE_SIM_20261007');S6=R/'SNOWBALL_ROUTES_01a11669/S6_routes/results_R2_aA_m0.csv'
labels=['F2','F1','F3','F2acf','F1acf'];gate=json.loads((J/'OUTPUT_GATE/A0_CHECK.json').read_text());assert gate['inference_valid'] and gate['filter_variant']=='F0aug' and gate['n_matched']==150
baseline=pd.read_csv(S6);req=pd.DataFrame(gate['requested'],columns=['route','anchor','lateral','mount_deg','drift','snr_db','seed']);selected=baseline.merge(req,how='inner',on=list(req.columns),validate='many_to_one');selected=selected[(selected['filter']=='ekf') & selected.baseline.isin(['odom_imu','range','range_s_P0'])];counts=selected.groupby('baseline').size().to_dict();assert counts=={'odom_imu':150,'range':150,'range_s_P0':150},counts
inputs=J/'INPUTS';inputs.mkdir(exist_ok=False);shutil.copyfile(S6,inputs/S6.name);shutil.copyfile(S6.with_name('manifest_R2_aA_m0.json'),inputs/'manifest_R2_aA_m0.json');selected.to_csv(inputs/'S6_REQUESTED_BASELINES.csv',index=False)
manifest0=json.loads((J/'OUTPUT_GATE/RUN_MANIFEST_check-a0.json').read_text());sourceout=J/'FROZEN_SOURCE';sourceout.mkdir()
for rel,h in manifest0['source_sha256'].items():
 p=SRC/rel;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;dst=sourceout/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst)
for rel in ['results/DRIVE_SIM_20261007/A24/A24_FIT_PARAMS.json','results/DRIVE_SIM_20261007/REQUESTS/A24_STAGE1_RUN.md','results/DRIVE_SIM_20261007/S0/PREREG_AMENDMENTS.md']:
 dst=sourceout/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SRC/rel,dst)
expectedarms=['A0_real_real','M0_Rmatched_Rmatched','W0_white_white','S1_bias','S2_ar0','S3_ar1','S4_iid','S5_iid0','S6_realdem','S7_block','S8_real','R1_bias','R2_ar0','R3_ar1','R4_iid','R5_realdem','R6_distbin','R7_tapbin','R8_real','J1_ar_indep','J2_ar_corr','J3_joint_block'];reports=[]
for label in labels:
 out=J/('OUTPUT_'+label);rows=pd.read_csv(out/f'ARMS_{label}.csv');units=pd.read_csv(out/f'ARM_UNIT_STATS_{label}.csv');man=json.loads((out/f'RUN_MANIFEST_{label}.json').read_text());variant='F2' if label=='F2acf' else 'F1' if label=='F1acf' else label
 keys=[(r.arm,int(r.drift),int(r.seed)) for r in rows.itertuples()];wanted={(a,d,s) for a in expectedarms for d in range(3) for s in range(50)}
 assert len(rows)==3300 and set(keys)==wanted and len(keys)==len(set(keys)),(label,len(rows));assert man['a0_gate']=='passed' and man['fingerprint']==gate['fingerprint'];assert set(rows.variant)=={variant};assert len(units)==3300
 ukeys={(r.arm,int(r.drift),int(r.seed)) for r in units.itertuples()};assert ukeys==wanted
 tracefiles=list((out/'TRACES').glob('*.npz'));expectednames={f'R2A_m0_{a}_s{s}_d{d}.npz' for a in expectedarms for d in range(3) for s in range(5)};assert len(tracefiles)==330 and {p.name for p in tracefiles}==expectednames
 failed=int(rows.error.fillna('').ne('').sum());trace_failures=0;shapes={};missing=[]
 for p in tracefiles:
  with np.load(p,allow_pickle=False) as z:
   if bool(z['failed']):trace_failures+=1;continue
   needed={'beta_hat','beta_var','beta_cross','est','cov6','keep','s_log','r_log','truth','t'}
   assert needed<=set(z.files),(label,p.name,needed-set(z.files));assert set(z['keep'].tolist())<=set([True,False]);assert np.isfinite(z['beta_hat']).all() and np.isfinite(z['beta_var']).all()
   shapes[p.name]={'beta_hat':list(z['beta_hat'].shape),'beta_var':list(z['beta_var'].shape),'beta_cross':list(z['beta_cross'].shape),'cov6':list(z['cov6'].shape)}
 reports.append({'label':label,'variant':variant,'rows':len(rows),'unit_rows':len(units),'missing':0,'duplicates':0,'failed_runs':failed,'trace_files':330,'failed_traces':trace_failures,'a0_gate':man['a0_gate'],'fingerprint':man['fingerprint'],'fit_params':man['fit_params'],'error_counts':rows.loc[rows.error.fillna('').ne(''),'error'].value_counts().to_dict(),'trace_shapes':shapes})
result={'state':'completed','gate_valid':True,'gate_n_matched':150,'labels':reports,'total_main_rows':16500,'total_traces':1650,'S6_baseline_counts':counts,'no_scientific_adoption_assessment':True};(J/'VERIFICATION.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='labels'}));print(json.dumps([{k:v for k,v in r.items() if k not in ['fit_params','trace_shapes']} for r in reports]))
