"""Assemble frozen observations, train-only fit outputs, exact Sensor-v2 controls."""
from pathlib import Path
import json,sys,hashlib
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;SOURCE=HERE.parents[2];DATA=SOURCE.parent
sys.path.insert(0,str(SOURCE/'research/CHAIN_HYPOTHESIS_20261019'))
import run as original
def main():
 out=DATA/'old_bundle';out.mkdir(exist_ok=True)
 raw=original.frozen_inputs()
 cases=json.loads((SOURCE/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())['cases']
 params=pd.read_csv(DATA/'reference_ae/OOF_PARAMETERS.csv.gz')
 memory=json.loads((DATA/'reference_ae/MEMORY_TRAIN_PARAMS.json').read_text())
 recs=[]
 for case in cases:
  cid=case['id'];a=raw[cid,'full'];t=a['t_s'];truth=a['truth_for_offline_scoring_only'][:,:3];ids=a['pose_id'].astype(int)
  frame=params[(params.case==cid)&(params.channel=='full')].set_index('pose_id').loc[ids]
  z=np.c_[a['z_r_m'],a['z_s']]
  if np.max(abs(z-frame[['range_m','s_fp']].to_numpy()))>1e-10:raise RuntimeError('OBSERVER_PARITY')
  mp=next(x for x in memory if x['held_route']==cid.split('_')[0]);C=np.zeros((len(t),2,2))
  C[:,0,0]=frame.C00;C[:,1,1]=frame.C11;C[:,0,1]=C[:,1,0]=frame.C01
  for bias,bias_dps in original.BIAS_LEVELS.items():
   controls,initial=original.build_positive_bias_controls(t,truth,bias,0)
   name=f'{cid}_{bias}.npz'
   np.savez_compressed(out/name,t=t,truth=truth,initial_pose=initial,z=z,mu=frame[['mu_r','mu_s']].to_numpy(),C=C,risk=frame.risk.to_numpy(),controls_dt=controls['dt_s'],controls_ds=controls['ds_odom'],controls_dyaw=controls['dtheta_gyro'])
   recs.append(dict(case=case,bias=bias,bias_dps=bias_dps,npz=name,training_scope='route-heldout:'+cid.split('_')[0],tau_s=mp['tau_s'],fraction=mp['fraction'],historical_power1_trace='../reference_ae/traces/'+name))
 (out/'BUNDLE.json').write_text(json.dumps({'cases':recs},indent=2))
 print('BUNDLE_READY',len(recs),flush=True)
if __name__=='__main__':main()
