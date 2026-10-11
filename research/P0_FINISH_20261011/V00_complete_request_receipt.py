#!/usr/bin/env python3
"""Complete V00 identity fields without changing replay results.
Every parent receipt is rechecked against original SAMPLES plus original CASES.
Corrected full-history MC tensors are independently reduced, not rerelabeled.
"""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research/P0_RESTORE_20261011'))
from rf_pose_index import PoseIndex,sha256,regression_tests
B=ROOT/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--parent',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 df=pd.read_csv(a.parent/'ROW_POSE_PARITY.csv.gz');meta=json.loads((B/'CASES.json').read_text());caseby={c['case']:c for c in meta};hashes=json.loads((a.parent/'HASH_MANIFEST.json').read_text())
 rows=[];source=[]
 for case,g in df.groupby('case',sort=False):
  c=caseby[case];p=B/case/'SAMPLES.json';samples=json.loads(p.read_text());index=PoseIndex(samples,len(samples))
  assert c['input_H_sha256']==hashes['H_sha256'][case]
  for policy,h in g.groupby('policy',sort=False):
   tab=pd.DataFrame(dict(t_s=h.time_s.to_numpy(),pose_id=h.requested_pose_id.to_numpy(),x=h.x_requested_m.to_numpy(),y=h.y_requested_m.to_numpy(),yaw_body_deg=h.yaw_requested_deg.to_numpy(),phase=h.phase.to_numpy()))
   Hrows,new=index.timeline(tab,case,hashes['H_sha256'][case],hashes['frequency_sha256']);assert np.array_equal(Hrows,h.H_row.to_numpy())
   assert np.array_equal(new.H_pose_id.to_numpy(),h.H_pose_id.to_numpy())
   new['policy']=policy;new['request_id']=[f'{case}|{policy}|k={int(k)}|pose={int(pid)}' for k,pid in zip(new.timeline_k,new.requested_pose_id)]
   new['mount_deg']=float(c['mount_deg']);new['anchor_id']=case.split('_')[1]
   new['anchor_x_m'],new['anchor_y_m'],new['anchor_z_m']=map(float,c['anchor_xyz'])
   new['robot_antenna_z_m']=float(c['robot_z']);new['antenna_yaw_requested_deg']=(new.yaw_requested_deg+float(c['mount_deg'])+180)%360-180
   new['tx_rotation']='diag(1,-1,-1)';new['rx_boresight']='world+z';new['tx_port']='LP+45';new['rx_ports']='LP+45,LP-45'
   new['samples_sha256']=sha256(p);new['case_manifest_sha256']=sha256(B/'CASES.json');rows.append(new)
  source.append(dict(case=case,SAMPLES_sha256=sha256(p),H_sha256=hashes['H_sha256'][case],anchor_xyz=c['anchor_xyz'],mount_deg=c['mount_deg'],robot_z=c['robot_z']))
 out=pd.concat(rows,ignore_index=True);assert len(out)==19038 and out.request_id.nunique()==19038
 out.to_csv(a.out/'V00_COMPLETE_RF_REQUEST_IDENTITY.csv.gz',index=False)
 q=np.load(a.parent/'POSE_ID_FIXED_128SEED_TENSORS.npz',allow_pickle=False);e=q['errors'];P=q['P6'];metrics=[]
 expected=pd.read_csv(a.parent/'CORRECTED_VS_QUARANTINED_MC.csv');expected=expected[expected['mode']=='POSE_ID_FIXED'].sort_values('snapshot')
 maxdiff=0.
 for i,t in enumerate(q['times']):
  ee=e[:,i,:3];cov=P[:,i,:3,:3];nees=np.einsum('ni,ni->n',ee,np.linalg.solve(cov,ee[...,None])[...,0]);row=dict(snapshot=i,time_s=float(t),n_seeds=len(ee),mean_pose_nees=float(nees.mean()),pose95_coverage=float(np.mean(nees<=7.814727903251179)),heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(ee[:,2]**2)))),position_rmse_m=float(np.sqrt(np.mean(np.sum(ee[:,:2]**2,axis=1)))))
  metrics.append(row)
  for key in ['mean_pose_nees','pose95_coverage','heading_rmse_deg','position_rmse_m']:maxdiff=max(maxdiff,abs(row[key]-float(expected.iloc[i][key])))
 assert maxdiff<1e-11
 pd.DataFrame(metrics).to_csv(a.out/'CORRECTED_128SEED_INDEPENDENT_RECALC.csv',index=False)
 result=dict(execution='COMPLETE',V00_request_identity_PASS=True,n_requests=19038,n_cases=7,n_mapping_regression_tests=len(regression_tests()),all_required_identity_fields_present=True,unique_request_scope='case+policy+timeline_k+pose_id',parent_corrected_full_history_run=38120812381,full_history_MC_receipt='Parent corrected128 used pose_id mapping from first sample, not only last three points',corrected128_recalc_maxdiff=maxdiff,original_faulty_run_status='QUARANTINED_REFERENCE_ONLY',sources=source,stage_B_allowed=False)
 (a.out/'STATUS.json').write_text(json.dumps(result,indent=2));(a.out/'EXECUTED_SOURCE.py').write_bytes(Path(__file__).read_bytes());print('V00_COMPLETE_IDENTITY_RESULT',json.dumps(result),flush=True)
if __name__=='__main__':main()
