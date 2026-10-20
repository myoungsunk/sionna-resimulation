"""Enumerate frozen input keys only. No utility labels, fitting or recursion."""
from pathlib import Path
import hashlib,io,json,zipfile,argparse
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
HERE=Path(__file__).resolve().parent
MEASURED=['range_m','log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
FEATURES=MEASURED+['power_nis','sigma_psi_rad','P_psi_bg','H_spsi']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
 p=argparse.ArgumentParser();p.add_argument('--rf',type=Path,required=True);p.add_argument('--labels',type=Path,required=True);a=p.parse_args()
 s2=json.loads((HERE.parent/'S2_N2_GEOMETRY/PROTOCOL_LOCK.json').read_text());assert sha(a.labels)==s2['labels_sha256']
 meta=json.loads((HERE.parent/'S2_N2_GEOMETRY/CASE_METADATA.json').read_text());dump(HERE/'CASE_METADATA.json',meta)
 df=pd.read_csv(a.labels);full=df[df.channel=='full'].reset_index(drop=True);routes=['R2','R4','R5'];folds={};index=[];deps=[]
 with zipfile.ZipFile(a.rf) as z:
  summary=json.loads(z.read('P2_OUT/P2_ONE_STEP_SUMMARY.json'))
  raw={r['case']:dict(np.load(io.BytesIO(z.read('P2_OUT/'+r['trace_file'])),allow_pickle=False)) for r in summary['per_case'] if r['channel']=='full'}
 for outer in routes+['ALL_OLD']:
  fits={}
  for inner in routes:
   if inner==outer:continue
   target=full[full.route==inner];allowed=full[(full.route!=inner)&(full.route!=outer)].copy();distance=cKDTree(target[['x_eval','y_eval']]).query(allowed[['x_eval','y_eval']])[0];train=allowed.loc[distance>1e-4].copy();keys=train[['case','pose_id']].values.tolist()
   fits[inner]=dict(training_routes=sorted(set(train.route)),rows_before=len(allowed),rows_after=len(train),sites_before=len(allowed[['x_eval','y_eval']].round(5).drop_duplicates()),sites_after=len(train[['x_eval','y_eval']].round(5).drop_duplicates()),heldout_min_distance_m=float(distance[distance>1e-4].min()),site_overlap=0,training_key_sha256=digest(keys),training_keys=keys)
   for cid in sorted(target.case.unique()):
    r=raw[cid];rows=[];t=r['t_s']
    for bias in ['B0','L0','L1','L2']:
     for seed in range(5):
      for i,tt in enumerate(t):
       status='INCLUDED' if tt>=30 and tt+10<=t[-1] else ('BEFORE_T30' if tt<30 else 'INCOMPLETE_HORIZON')
       end=int(np.searchsorted(t,tt+10,side='right'))
       rows.append(dict(outer=outer,inner_route=inner,case=cid,bias=bias,seed=seed,pose_id=int(r['pose_id'][i]),frame=i,t_s=float(tt),end_frame_exclusive=end,horizon_samples=end-i-1,status=status))
    path=HERE/f'LABEL_PACKET_INDEX_{outer}_{cid}.csv';pd.DataFrame(rows).to_csv(path,index=False)
    # Independent information is never multiplied by bias/seed/fold.
    eligible=np.flatnonzero((t>=30)&(t+10<=t[-1]));nonoverlap=0;next_t=-np.inf
    for i in eligible:
     if t[i]>=next_t:nonoverlap+=1;next_t=t[i]+10
    index.append(dict(outer=outer,case=cid,file=path.name,sha256=sha(path),rows=len(rows),included=sum(x['status']=='INCLUDED' for x in rows),incomplete_horizon=sum(x['status']=='INCOMPLETE_HORIZON' for x in rows),unique_rf_packets=len(eligible),nonoverlapping_10s_windows=nonoverlap))
  folds[outer]=fits
  for validation in fits:
   for label_route,fit in fits.items():
    deps.append(dict(outer=outer,hgb_oof_validation_route=validation,label_route=label_route,hgb_role='VALIDATION' if label_route==validation else 'TRAIN',p1_training_routes='|'.join(fit['training_routes']),p1_uses_hgb_validation_route=validation in fit['training_routes']))
 dump(HERE/'TRAIN_FOLDS.json',dict(site_rule='nearest xy >1e-4 m, v2 unchanged',site_weights='pinned inverse rounded5 xy multiplicity normalized mean1',folds=folds))
 dump(HERE/'LABEL_PACKET_INDEX.json',index);pd.DataFrame(deps).to_csv(HERE/'ROUTE_DEPENDENCIES.csv',index=False)
 matrix=[]
 for case in meta['legacy']+meta['new']:
  cid=case['id']
  for channel in ['full']+(['los'] if cid in ['R2_aA_m0','R2_aA_m45'] else []):
   for bias in ['B0','L0','L1','L2']:
    for arm in ['POWER1','R0','POLICY_V3','POLICY_NO_MARGIN']:matrix.append(dict(case=cid,route=cid.split('_')[0],channel=channel,bias=bias,seed=0,arm=arm,scope='motion',evaluation_start_s=30))
 pd.DataFrame(matrix).to_csv(HERE/'EVALUATION_MATRIX.csv',index=False);assert len(matrix)==288
 lock=dict(task='S3_Q1_POLICY',version=1,status='PREREGISTERED_BEFORE_LABELS_TRAIN_RECURSION',S2_commit='8821d2e4d80ed749b5c4c5e3901e42957d29b2eb',S2_audit='ACCEPT_FOR_S3; scientific NOT_ESTABLISHED preserved',engine_commit=s2['engine_commit'],engine_sha256=s2['engine_sha256'],sensor_lock_sha256=s2['new_sensor_lock_sha256'],B_OLD=s2['B_OLD'],rf_sha256=sha(a.rf),labels_sha256=sha(a.labels),cached_oof_sha256=s2['cached_oof_sha256'],features=FEATURES,actions=['POWER','R0','INFLATE4','SKIP'],bias_dps=dict(B0=0,L0=.01,L1=.05,L2=.2),seeds=list(range(5)),label_rule='every actual old7 Full RF t>=30 and t+10<=last; no subsampling; all other rows retained with exclusion status',label_loss='Heading deg^2 MSE on (t,t+10]; current action applied; subsequent POWER; u=MSE_POWER-MSE_action',p1='v2 nested outer+inner exclusion and >1e-4m site rule unchanged; novel labels never used',oof_scope='HGB_STAGE_ROUTE_HELDOUT_CONDITIONAL_ON_FIXED_V2_PRIOR_LABELS; NOT whole-pipeline OOF; no calibration coverage guarantee',oof_group='inner route, all bias/seed/overlapping windows kept together',learner=dict(max_iter=120,max_leaf_nodes=15,min_samples_leaf=20,learning_rate=.05,l2_regularization=1.,max_bins=255,early_stopping=False,random_state=20261020),margin=dict(selection='unadjusted nonPOWER argmax even if all negative',tie_order=['R0','INFLATE4','SKIP'],error='max(0,predicted-actual) only rows selecting that action',quantile=.8,quantile_method='numpy linear',no_selection='delta null; UNCALIBRATED_NO_OOF_SELECTION; action disabled in V3',decision='argmax(predicted-delta) enabled actions; strictly >0 else POWER',no_margin='same final models; delta=0, all three actions enabled; strictly >0 else POWER; uncalibrated disabling is specific to V3'),evaluation=dict(total=288,full_cells=64,los_cells=8,arms=['POWER1','R0','POLICY_V3','POLICY_NO_MARGIN'],scope='whole motion clock t>=30; radio scope auxiliary'),decision='support only Full64/64 V3<=1.10POWER1 AND NativeLoS8/8 V3<=1.10R0; any valid violation NOT_ESTABLISHED/NO_GO; missing or failed technical incomplete forbids support',checks=dict(power_heading_tol_deg=1e-6,power_gate_mismatch=0,restart_state_cov_tol=1e-10,independent_11_tol=1e-9,spd='all prior/posterior finite and eigenvalue>0; no repair',nonradio_updates=0),label_shards=index,contract_hashes={p.name:sha(p) for p in [HERE/'TRAIN_FOLDS.json',HERE/'LABEL_PACKET_INDEX.json',HERE/'ROUTE_DEPENDENCIES.csv',HERE/'EVALUATION_MATRIX.csv',HERE/'CASE_METADATA.json',HERE/'MODEL_AND_OOF_DESIGN.md']})
 dump(HERE/'PROTOCOL_LOCK.json',lock)
 print(json.dumps(dict(expected_results=len(matrix),included_labels=sum(x['included'] for x in index),index_rows=sum(x['rows'] for x in index),unique_packets_without_fold_bias_seed=sum(x['unique_rf_packets'] for x in index if x['outer']=='ALL_OLD'),nonoverlap_without_duplicates=sum(x['nonoverlapping_10s_windows'] for x in index if x['outer']=='ALL_OLD'))))
if __name__=='__main__':main()
