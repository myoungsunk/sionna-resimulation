"""Frozen historical R2 Full input materialization and reusable channel reader."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'S1'))
import parity as p

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def put(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False))

def materialize_full(destination):
 destination=Path(destination)
 if destination.exists():raise ValueError('preserve original materialized inputs')
 destination.mkdir(parents=True)
 original=p.b.orig
 feature_path=original/'p2_artifacts/prepared/OBSERVATION_FEATURES_LABELS.csv.gz'
 mr_path=original/'p2/research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz'
 means=pd.read_csv(mr_path)
 sources={str(feature_path):sha(feature_path),str(mr_path):sha(mr_path)};outputs={};references={}
 controls_root=p.b.cache/'research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/CONTROL'
 for bias in ('B0','L2'):
  path=controls_root/f'R2_aB_m0_{bias}.npz';sources[str(path)]=sha(path)
  with np.load(path) as z:
   old=dict(z);jb=old['names'].tolist().index('OFF_BB');jm=old['names'].tolist().index('OFF_MB')
  ids=old['pose_id'];t=old['t_s'];truth=old['truth_scoring_only'][:,:3]
  mean=means[(means.case=='R2_aB_m0')&(means.channel=='full')&(means.bias==bias)].set_index('pose_id',verify_integrity=True).loc[ids]
  packet=dict(t=t,pose_id=ids,z=old['nu'][:,jb]+old['h'][:,jb]+old['mu'][:,jb],muBASE=old['mu'][:,jb],muMB=old['mu'][:,jm],R=old['R'][:,jb],P0=old['Pprior'][0,jb],D=mean.abs_ds1.to_numpy())
  if not all(np.isfinite(v).all() for v in packet.values()):raise ValueError('nonfinite R2 Full packet')
  f=destination/f'R2_aB_m0_{bias}_Full.npz';np.savez_compressed(f,**packet);outputs[f.name]=sha(f)
  f=destination/f'R2_aB_m0_{bias}_TRUTH.npz';np.savez_compressed(f,t=t,pose_id=ids,truth=truth,bg=np.deg2rad(.2 if bias=='L2' else 0.));outputs[f.name]=sha(f)
  f=destination/f'R2_aB_m0_{bias}_REFERENCE.npz';np.savez_compressed(f,x=old['x'][:,jm],P=old['P'][:,jm],prior=old['prior'][:,jm],Pprior=old['Pprior'][:,jm],mask=old['acc'][:,jb],mu=old['mu'][:,jm],pose_id=ids);outputs[f.name]=sha(f);references[bias]=f.name
  for seed in [0,*range(10,30)]:
   ds,gy,dt,x0=p.b.pb.build_controls(t,truth,bias,seed)
   f=destination/f'R2_aB_m0_{bias}_{seed}.npz';np.savez_compressed(f,ds=ds,gy=gy,dt=dt,x0=x0);outputs[f.name]=sha(f)
 manifest=dict(route='R2',channel='Full',sources=sources,files=outputs,references=references,recipe='S1/materialize.py Full recipe, historical immutable mu/R, abs_ds1, and original build_controls; no fitting',calibration_overlap='R2 Full previously used to freeze tau_DS; R2 is descriptive in-sample reuse, not holdout confirmation')
 put(destination/'INPUT_LOCK.json',manifest);return manifest

class Inputs:
 def __init__(self,directory,channel='Full',packet_directory=None):
  self.root=Path(directory);self.lock=json.loads((self.root/'INPUT_LOCK.json').read_bytes());self.channel=channel
  self.packet_root=self.root if packet_directory is None else Path(packet_directory)
  self.packet_lock=self.lock if packet_directory is None else json.loads((self.packet_root/'INPUT_LOCK.json').read_bytes())
  if self.packet_lock['channel']!=channel:raise ValueError('channel input registry mismatch')
 def read(self,name):
  path=self.root/(name+'.npz')
  if sha(path)!=self.lock['files'][path.name]:raise ValueError('R2 input checksum '+name)
  with np.load(path) as z:return dict(z)
 def packet(self,bias):
  name=f'R2_aB_m0_{bias}_{self.channel}.npz';path=self.packet_root/name
  if sha(path)!=self.packet_lock['files'][name]:raise ValueError('R2 channel packet checksum')
  with np.load(path) as z:return dict(z)
 def controls(self,bias,seed):return self.read(f'R2_aB_m0_{bias}_{seed}')
 def truth(self,bias):return self.read(f'R2_aB_m0_{bias}_TRUTH')
 def reference(self,bias):return self.read(self.lock['references'][bias][:-4])
