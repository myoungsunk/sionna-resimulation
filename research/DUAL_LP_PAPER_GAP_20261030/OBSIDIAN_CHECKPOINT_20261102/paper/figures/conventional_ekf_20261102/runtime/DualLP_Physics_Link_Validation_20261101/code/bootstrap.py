"""Resolve immutable legacy source without modifying it; reconstruction utilities."""
from __future__ import annotations
import os,sys,json,hashlib,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REC=ROOT/'recovered'; INPUT=REC/'inputs'; LEGACY=REC/'legacy/research/DS_MASK_CAUSAL_X1_X2_20261026'
os.environ['REFLECT_ROOT']=str(INPUT)
sys.path.insert(0,str(LEGACY/'mbvar_premodel_diag_20261029/code'))
import numpy as np
import pandas as pd
import diag_mbvar as DG
PB=DG.PB;C=DG.C
from core import wrap
CONFIG=json.loads((ROOT/'contracts/CONFIG_LOCK.json').read_text())
CASES=CONFIG['cases'];BIASES=list(CONFIG['gyro_bias_deg_per_s'])
RESULTS=ROOT/'results';TABLES=RESULTS/'tables';TRACES=RESULTS/'traces'
for p in (RESULTS,TABLES,TRACES,RESULTS/'inputs_for_runs'):p.mkdir(parents=True,exist_ok=True)
def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write_json(p,obj):
 def cv(v):
  if isinstance(v,np.ndarray):return v.tolist()
  if isinstance(v,np.generic):return v.item()
  if isinstance(v,Path):return str(v)
  raise TypeError(type(v))
 Path(p).write_text(json.dumps(obj,indent=2,default=cv,allow_nan=False))
def load_data(case,bias,model):
 """Same inputs as diag_mbvar.load; BASE gate filled from its single replay."""
 spec=C.CASES[case]; ref=C.load_control(case,'B0');jb,jm=ref['jb'],ref['jm']
 t=ref['t_s'];gt=ref['truth_scoring_only'];z=ref['nu'][:,jb]+ref['h'][:,jb]+ref['mu'][:,jb]
 ds,gy,dt,x0=PB.build_controls(t,gt[:,:3],bias)
 hg,_=model.batch(np.c_[gt[:,:3],np.zeros(len(t))],spec)
 a=np.array(spec['anchor'][:2]); n=len(t)
 assert n==CONFIG['sample_counts']['full_RF_timeline_per_case'][case]
 assert np.isfinite(z).all() and np.isfinite(gt).all()
 assert np.unique(ref['pose_id']).size==n and np.all(np.diff(t)>0)
 return dict(case=case,bias=bias,t=t,gt=gt,z=z,R=ref['R'][:,jb],acc=np.zeros(n,bool),ds=ds,gy=gy,dt=dt,x0=np.r_[x0,0.],P0=ref['Pprior'][0,jb],spec=spec,anchor=a,hg=hg,mu=dict(BB=ref['mu'][:,jb],MB=ref['mu'][:,jm]),rho_true=np.hypot(gt[:,0]-a[0],gt[:,1]-a[1]),pose_id=ref['pose_id'])
def save_data(D):
 obj={k:v for k,v in D.items() if k not in ('spec','mu')}
 obj.update(mu_BB=D['mu']['BB'],mu_MB=D['mu']['MB'],spec_json=json.dumps(D['spec']))
 np.savez_compressed(RESULTS/'inputs_for_runs'/f"{D['case']}_{D['bias']}.npz",**obj)
def read_data(case,bias):
 with np.load(RESULTS/'inputs_for_runs'/f'{case}_{bias}.npz',allow_pickle=False) as z:D=dict(z)
 D['case']=str(D['case']);D['bias']=str(D['bias']);D['spec']=json.loads(str(D.pop('spec_json')));D['mu']={'BB':D.pop('mu_BB'),'MB':D.pop('mu_MB')};return D
class Recorder:
 """Passive wrapper records exactly the Jacobian returned to legacy run."""
 def __init__(self,model):self.model=model;self.js=[]
 def batch(self,*args,**kwargs):
  result=self.model.batch(*args,**kwargs);self.js.extend(result[1].copy());return result
def trace_path(case,bias,arm,gate):return TRACES/f'{case}__{bias}__{arm}__{gate}.npz'
def read_trace(case,bias,arm,gate):
 if arm=='BB_ORIG' and gate=='fixed':gate='self'
 with np.load(trace_path(case,bias,arm,gate),allow_pickle=False) as z:return dict(z)
def full_run(D,bg,mode,gate,model,tab=None):
 rec=Recorder(model);kw={'model':rec}
 if tab is not None:kw['tab']=tab
 X,P,L=DG.run(D,bg,mode,gate,**kw)
 J=np.full((len(X),2,4),np.nan);finite=np.isfinite(D['z']).all(1);J[finite]=np.asarray(rec.js)
 prev=np.vstack([D['x0'],X[:-1]])
 rho=np.array([math.hypot(x[0]-D['anchor'][0],x[1]-D['anchor'][1]) for x in prev])
 sg=np.array([DG.sigf(r,tab if tab is not None else DG.HAND) for r in rho])
 arm=bg+('_CONST' if tab is not None and mode=='var' else '_VAR' if mode=='var' else '_ORIG')
 tr=dict(X=X,PX=P,J=J,rho_lookup=rho,sigma_lookup=sg,**L)
 np.savez_compressed(trace_path(D['case'],D['bias'],arm,gate),**tr)
 scores=PB.scores(D,X,P);u=L['used'];s=D['t']>=30-1e-9;nis=L['nis'][finite]
 row=dict(case=D['case'],bias=D['bias'],arm=arm,gate=gate,n_all=len(X),n_finite=int(finite.sum()),n_used=int(u.sum()),n_used_score=int((u&s).sum()),accept_rate=float(u.sum()/finite.sum()),longest_gap_s=DG.longest_gap_s(D['t'],u,finite),nis_mean_all=float(np.mean(nis)),nis_mean_used=float(np.mean(L['nis'][u])),frac_all_over_gate=float(np.mean(nis>DG.GATE)),role_of_truth='CONTROL_GENERATION_AND_SCORING_ONLY',**scores)
 return tr,row
