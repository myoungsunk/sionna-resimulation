"""Offline materialization of immutable sensor streams and disjoint scoring labels."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
s=Path(__file__).resolve().parent
a=s.parent/'A0_R3_REFIT'
sys.path.insert(0,str(a))
import check_base as base
cache=base.cache/'S1_INPUTS'
def digest(v):return hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest()
def main():
 cache.mkdir(exist_ok=True)
 feat=pd.read_csv(base.orig/'p2_artifacts/prepared/OBSERVATION_FEATURES_LABELS.csv.gz')
 trained=pd.read_csv(base.orig/'p2/research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz')
 lock=json.loads((a/'BASE_INPUTS.json').read_text());receipts={}
 for zone in ['algorithm_input','evaluator_truth']:
  (cache/zone).mkdir(exist_ok=True)
 for route in ('R4','R5'):
  case=route+'_aB_m0';native=pd.read_csv(a/(case+'_Native_LoS.csv')).set_index('pose_id',verify_integrity=True)
  dsfile=s.parent/'A0_R2_SEARCH'/(case+'_Native_LoS_features.npz')
  with np.load(dsfile) as f: nds=pd.Series(abs(f['features'][:,f['columns'].tolist().index('ds_+1')]),index=f['pose_id'])
  for bias in ('B0','L2'):
   ctl=np.load(next(base.cache.rglob(case+'_'+bias+'.npz')))
   ids=ctl['pose_id'];t=ctl['t_s'];gt=ctl['truth_scoring_only'];jb=list(ctl['names']).index('OFF_BB');jm=list(ctl['names']).index('OFF_MB');P0=ctl['Pprior'][0,jb]
   ef={ch:feat[(feat.case==case)&(feat.channel==ch)].set_index('pose_id',verify_integrity=True).loc[ids] for ch in ['full','los']}
   efpath=cache/'evaluator_truth'/(case+'_'+bias+'.npz')
   np.savez_compressed(efpath,pose_id=ids,t=t,truth=gt[:,:3],e_mp=ef['full'].s_fp.to_numpy()-ef['los'].s_fp.to_numpy(),bg=np.deg2rad(0.2 if bias=='L2' else 0.))
   for channel in ('Full','Native_LoS'):
    key=case+'_'+bias+'_'+channel
    if channel=='Full':
     bb=ctl['mu'][:,jb];mb=ctl['mu'][:,jm];R=ctl['R'][:,jb];z=ctl['nu'][:,jb]+ctl['h'][:,jb]+bb
     ds=trained[(trained.case==case)&(trained.channel=='full')&(trained.bias==bias)].set_index('pose_id',verify_integrity=True).loc[ids,'abs_ds1'].to_numpy()
    else:
     old=np.load(next((base.orig/'p2_artifacts').rglob(case+'_los_'+bias+'_TRACE.npz')));j=list(old['arms']).index('POWER_DIAG')
     z=ef['los'][['range_m','s_fp']].to_numpy();bb=old['mu'][:,j];R=old['R'][:,j];mb=bb.copy();mb[:,0]=native.loc[ids,'MU_R_EXDS_m'].to_numpy();ds=nds.loc[ids].to_numpy()
    vals=dict(z=z,muMB=mb,muBASE=bb,R=R,P0=P0)
    assert all(digest(v)==lock['inputs'][key]['arrays'][k] for k,v in vals.items()) and np.isfinite(ds).all()
    np.savez_compressed(cache/'algorithm_input'/(key+'.npz'),**vals,t=t,pose_id=ids,D=ds)
   for seed in range(30):
    ds,gy,dt,x0=base.pb.build_controls(t,gt[:,:3],bias,seed);key=f'{case}_{bias}_{seed}'
    vals=dict(ds=ds,gy=gy,dt=dt,x0=x0);assert {k:digest(v) for k,v in vals.items()}==lock['controls'][key]
    np.savez_compressed(cache/'algorithm_input'/(key+'.npz'),**vals)
 for p in sorted(cache.glob('*/*.npz')):receipts[p.relative_to(cache).as_posix()]=base.sha(p)
 (s/'MATERIALIZED_INPUTS.json').write_text(json.dumps(receipts,indent=2))
if __name__=='__main__':main()
