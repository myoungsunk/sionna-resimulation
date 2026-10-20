"""Seven-condition range-equation retraining; original 9519-point request stays unmet."""
from pathlib import Path
import json,os,sys,traceback,argparse
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;SOURCE=HERE.parents[2];DATA=SOURCE.parent
sys.path.insert(0,str(HERE.parent/'T1_MEMORY'));sys.path.insert(0,str(SOURCE/'research/CHAIN_HYPOTHESIS_20261019'))
from unit_tests import load_engine
engine,_=load_engine(SOURCE)
from replay import score
import run as original
from source_model import SourceFFD
from src_range_model import SourceTapRange,RefitOffsetRange
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 (a.out/'traces').mkdir(exist_ok=True);rows=[];checks=[];fitted=[]
 try:
  model=SourceFFD();src=SourceTapRange(model);raw=original.frozen_inputs();cases=json.loads((SOURCE/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())['cases']
  df=pd.read_csv(DATA/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz');oldparams=pd.read_csv(DATA/'reference_ae/OOF_PARAMETERS.csv.gz')
  adjusted=df.copy();native=[]
  for case in cases:
   r=raw[case['id'],'los'];truth=r['truth_for_offline_scoring_only'][:,:3];state=np.c_[truth,np.zeros(len(truth))];hp=[];ho=[]
   for i in range(0,len(truth),48):
    hp.append(src.batch(state[i:i+48],case,gradient=False)[0][:,0]);ho.append(model.batch(state[i:i+48],case,gradient=False)[0][:,0])
   hp=np.concatenate(hp);ho=np.concatenate(ho)
   for channel in ['full','los']:
    ix=(adjusted.case==case['id'])&(adjusted.channel==channel)
    frame=adjusted.loc[ix];states=np.c_[frame.x_eval,frame.y_eval,frame.yaw_rad,np.zeros(len(frame))]
    changes=[]
    for j in range(0,len(states),48):
     hs=src.batch(states[j:j+48],case,gradient=False)[0][:,0];hb=model.batch(states[j:j+48],case,gradient=False)[0][:,0];changes.extend(hb-hs)
    adjusted.loc[ix,'e_r']=frame.e_r.to_numpy()+np.asarray(changes)
   native.extend(dict(case=case['id'],route=case['id'].split('_')[0],pose_id=int(pid),offset=float(obs-(dist+.5315983906250129))) for pid,obs,dist in zip(r['pose_id'],r['z_r_m'],ho))
  if not np.isfinite(adjusted[['e_r','e_s']].to_numpy()).all():raise RuntimeError('NONFINITE_TRAINING_LABELS_AFTER_ROW_POSE_ADJUSTMENT')
  native=pd.DataFrame(native);full=adjusted[adjusted.channel=='full'].copy().reset_index(drop=True)
  plans={};fitinfo=[]
  for held,tr,te in original.feature_splits(np,full):
   train=full.loc[tr];target=adjusted[adjusted.route==held].copy();mu,C,info=original.fit_model(np,train,target,original.site_weights(np,pd,train),'POWER_BIN_JOINT',original.GROUPS)
   target['mu_r']=mu[:,0];target['mu_s']=mu[:,1];target['C00']=C[:,0,0];target['C11']=C[:,1,1];target['C01']=C[:,0,1];fitted.append(target);plans[held]=target
   offset=float(native[native.route!=held].offset.mean());fitinfo.append(dict(held_route=held,src_power=info,refit_offset_m=offset));plans[held+'_offset']=offset
  pd.concat(fitted).to_csv(a.out/'OOF_PARAMETERS_SRC_TAP.csv.gz',index=False,compression='gzip')
  (a.out/'PARAMETER_MANIFEST.json').write_text(json.dumps(dict(range_model='SRC_TAP',training='held-route; identical-site exclusion preserved',source='SourceFFD exact tap, no interpolation',native_points_available=len(native),native_points_requested=9519),indent=2))
  (a.out/'TRAIN_PARAMS.json').write_text(json.dumps(fitinfo,indent=2))
  for case in cases:
   cid=case['id'];held=cid.split('_')[0];offset=plans[held+'_offset']
   for channel in ['full','los']:
    r=raw[cid,channel];t=r['t_s'];truth=r['truth_for_offline_scoring_only'][:,:3];ids=r['pose_id'];z=np.c_[r['z_r_m'],r['z_s']]
    old=oldparams[(oldparams.case==cid)&(oldparams.channel==channel)].set_index('pose_id').loc[ids];new=plans[held];new=new[(new.case==cid)&(new.channel==channel)].set_index('pose_id').loc[ids]
    for label,bias in original.BIAS_LEVELS.items():
     controls,initial=original.build_positive_bias_controls(t,truth,label,0)
     for variant,observation,frame in [('B_OLD',model,old),('SRC_TAP',src,new),('B_REFIT_ONLY',RefitOffsetRange(model,offset),old)]:
      mu=frame[['mu_r','mu_s']].to_numpy().copy();C=np.zeros((len(t),2,2));C[:,0,0]=frame.C00;C[:,1,1]=frame.C11;C[:,0,1]=C[:,1,0]=frame.C01
      if variant=='B_REFIT_ONLY':mu[:,0]-=offset+.5315983906250129
      result=engine.run(t,controls,initial,z,mu,C,np.zeros(len(t)),case,observation,[dict(name='JOINT4',base='r0'),dict(name='POWER1',base='power')])
      err=0.
      for j,name in enumerate(result['names']):
       values=score(result['state'][:,j],result['cov'][:,j],truth,bias,t>=30);ind=score(result['state'][:,j],result['cov'][:,j],truth,bias,t>=30,scalar=True);err=max(err,max(abs(values[k]-ind[k]) for k in values));rows.append(dict(case=cid,channel=channel,bias=label,range_model=variant,arm=str(name),n=int((t>=30).sum()),**values))
      check=dict(case=cid,channel=channel,bias=label,range_model=variant,independent_scorer_max=err)
      if err>1e-9:raise RuntimeError('RANGE_INDEPENDENT_SCORE')
      if channel=='full' and variant=='B_OLD':
       with np.load(DATA/'reference_ae/traces'/f'{cid}_{label}.npz') as ref:
        j=list(ref['names']).index('POWER1');check['old_gate_mismatch']=int(np.count_nonzero(ref['accepted'][:,j]!=result['accepted'][:,1]));check['old_state_max']=float(abs(ref['state'][:,j,:4]-result['state'][:,1,:4]).max())
       if check['old_gate_mismatch'] or check['old_state_max']>1e-10:raise RuntimeError('RANGE_OLD_PARITY')
      checks.append(check)
      result.update(truth_for_offline_scoring_only=truth,observations=z,mu_input=mu,C_input=C,initial_pose=initial,controls_dt=controls['dt_s'],controls_ds=controls['ds_odom'],controls_dyaw=controls['dtheta_gyro'])
      np.savez_compressed(a.out/'traces'/f'{cid}_{channel}_{label}_{variant}.npz',**result)
      pd.DataFrame(rows).to_csv(a.out/'RANGE_REPLAY.csv',index=False);pd.DataFrame(checks).to_csv(a.out/'REPLAY_CHECKS.csv',index=False)
      print('T6_REPLAY',cid,channel,label,variant,flush=True)
  (a.out/'MANIFEST.json').write_text(json.dumps(dict(technical='TECHNICAL_PASS_SEVEN_CONDITIONS',scientific='NOT_ESTABLISHED',native_9519='BLOCKED_INPUT_2268_POINTS_MISSING',actions_run_id=os.getenv('GITHUB_RUN_ID'),artifact_id=None),indent=2))
 except Exception as e:
  (a.out/'ERRORS.json').write_text(json.dumps([dict(error=str(e),traceback=traceback.format_exc(),retry='requires review')],indent=2));raise
if __name__=='__main__':main()
