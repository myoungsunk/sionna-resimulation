"""Assemble and check the BASE gate using the R3 frozen means only in MB."""
import hashlib,json,sys,types,subprocess
from pathlib import Path
import numpy as np
import pandas as pd
out=Path(__file__).resolve().parent
repo=out.parents[2]
orig=Path('D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849')
base=orig/'p2'
cache=Path('D:/codex/MBVAR_PRR_001_20261103_inputs')
rev='7e2855314de867e0481f8eb5ed1a07c48710f364'
source='research/DS_MASK_CAUSAL_X1_X2_20261026/'
sys.dont_write_bytecode=True
def module(name,path):
 m=types.ModuleType(name);m.__file__=str(repo/path);sys.modules[name]=m
 raw=subprocess.check_output(['git','-C',str(repo),'show',rev+':'+path]);exec(compile(raw,m.__file__,'exec'),m.__dict__);return m
sys.path[:0]=[str(base/'research/FFD_P0P3_20261016'),str(base/'research/EKF4_RANGE_S_STAGED_20261014'),str(base/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src')]
core=module('core','research/EKF4_RANGE_S_STAGED_20261014/core.py')
import source_model
from qclean_uwb.drivesim import pattern_apply as PA
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
banks=[]
for n in ('plus','minus'):
 with np.load(orig/f'LP_{n}45_bank.npz') as z:banks.append(PA.Bank(dict(z)))
model=source_model.SourceFFD(banks=banks)
common=types.ModuleType('common');common.REPO=base;common.base_model=lambda:model;sys.modules['common']=common
pb=module('exp_pb',source+'pol_bias_model/exp_pb.py')
ctl=module('ctl_core',source+'mbvar_control_correction_20261029/ctl_core.py')
def make_inputs():
 feat=pd.read_csv(orig/'p2_artifacts/prepared/OBSERVATION_FEATURES_LABELS.csv.gz')
 inputs={};checks={};controls={};baseline={}; trace_dir=cache/"F64_R3_REFERENCE";trace_dir.mkdir(exist_ok=True)
 for route in ('R4','R5'):
  case=route+'_aB_m0';nativemean=pd.read_csv(out/(case+'_Native_LoS.csv')).set_index('pose_id',verify_integrity=True)
  for bias in ('B0','L2'):
   refpath=next(cache.rglob(case+'_'+bias+'.npz'));ref=np.load(refpath)
   jb=ref['names'].tolist().index('OFF_BB');jm=ref['names'].tolist().index('OFF_MB')
   ids=ref['pose_id'];t=ref['t_s'];truth=ref['truth_scoring_only'];P0=ref['Pprior'][0,jb]
   for seed in range(30):
    ds,gy,dt,x0=pb.build_controls(t,truth[:,:3],bias,seed)
    controls[f'{case}_{bias}_{seed}']={k:hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest() for k,v in dict(ds=ds,gy=gy,dt=dt,x0=x0).items()}
   ds,gy,dt,x0=pb.build_controls(t,truth[:,:3],bias,0)
   for channel in ('Full','Native_LoS'):
    key=case+'_'+bias+'_'+channel;spec=dict(anchor=(10.,0.,2.65),robot_z_m=.45,mount_deg=0.)
    if channel=='Full':
     z=ref['nu'][:,jb]+ref['h'][:,jb]+ref['mu'][:,jb];mb=ref['mu'][:,jm];bb=ref['mu'][:,jb];R=ref['R'][:,jb];hist=ref['acc'][:,jb];trace=refpath
    else:
     trace=next((orig/'p2_artifacts').rglob(case+'_los_'+bias+'_TRACE.npz'));los=np.load(trace);j=los['arms'].tolist().index('POWER_DIAG')
     assert np.array_equal(ids,los['pose_id']) and np.array_equal(t,los['t_s'])
     z=feat[(feat.case==case)&(feat.channel=='los')].set_index('pose_id',verify_integrity=True).loc[ids,['range_m','s_fp']].to_numpy()
     bb=los['mu'][:,j];R=los['R'][:,j];hist=los['accepted'][:,j];mb=bb.copy();mb[:,0]=nativemean.loc[ids,'MU_R_EXDS_m'].to_numpy()
    assert np.isfinite(z).all() and np.isfinite(mb).all() and np.all(R[:,0,1]==0) and np.all(R[:,1,0]==0)
    acc=pb.gated_mask(z,bb,R,ds,gy,dt,np.r_[x0,0.],P0,spec,model)
    bad=np.flatnonzero(acc!=hist)
    dataset=dict(t=t,z=z,mu=dict(MB=mb),R=R,R0=R,ds=ds,gy=gy,dt=dt,x0=np.r_[x0,0.],P0=P0,anchor=np.array([10.,0.]),spec=spec,acc=acc,fin=np.isfinite(z).all(1))
    X,P,_,_=pb.run(dataset,mb,dict(mode="var"),model)
    Y,C,L=ctl.run(dataset,"MB",ctl.R_var)
    assert np.allclose(X,Y,rtol=1e-10,atol=1e-10) and np.allclose(P,C,rtol=1e-10,atol=1e-10) and not len(bad)
    trace_file=trace_dir/(key+".npz")
    np.savez_compressed(trace_file,pose_id=ids,mask=acc,x=X,P=P,h=L["hx"],H=L["H"],mu=L["mu_used"],R=L["Ru"],prior=L["xp"],Pprior=L["Pp"])
    baseline[key]=dict(n=len(ids),max_state=float(np.max(abs(X-Y))),max_P=float(np.max(abs(P-C))),trace_sha256=sha(trace_file))
    inputs[key]=dict(trace_sha256=sha(trace),pose_ids=hashlib.sha256(ids.tobytes()).hexdigest(),arrays={k:hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest() for k,v in dict(z=z,muMB=mb,muBASE=bb,R=R,P0=P0).items()})
    checks[key]=dict(n=len(ids),mask_mismatches=len(bad),first_mismatch_pose=int(ids[bad[0]]) if len(bad) else None)
 (out/'F64_REFERENCE.json').write_text(json.dumps(baseline,indent=2))
 (out/'BASE_INPUTS.json').write_text(json.dumps(dict(inputs=inputs,controls=controls),indent=2))
 (out/'BASE_GATE_CHECK.json').write_text(json.dumps(checks,indent=2));print(checks)
if __name__=='__main__':make_inputs()
