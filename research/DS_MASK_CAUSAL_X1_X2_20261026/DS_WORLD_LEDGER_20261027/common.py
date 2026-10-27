from pathlib import Path
import os,sys,json,hashlib,importlib.util
ROOT=Path(__file__).resolve().parent
E1=ROOT.parent/'DS_NONLINEAR_E1_E4_20261027_01a1775b'
PREVIOUS=ROOT.parent/'DS_GEOMETRY_PHYSICAL_20261027'
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('frozen_e',E1/'run_experiments.py');E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)
S=E.S;S.ROOT=ROOT;E.ROOT=ROOT;os.environ['PJ_OUT']=str(ROOT/'runtime')
sys.path.insert(0,str(S.PKG));import v_replay as V
S.V=V;E.V=V
import numpy as np
import pandas as pd
from geometry_model import GeometryFFD
def load(f):
 with np.load(f) as z:return {k:z[k] for k in z.files}
def write(n,d):S.write(n,d)
def wrap(x):return 180-(180-x)%360
def geometry(x,case):
 a=np.asarray(case['anchor']);v=a[:2]-x[...,:2];rho=np.linalg.norm(v,axis=-1);height=a[2]-case['robot_z_m']
 beta=np.arctan2(v[...,1],v[...,0]);el=np.arctan2(height,rho);r=np.sqrt(rho**2+height**2)
 return beta,el,r
def unitvec(b,e):return np.stack([np.cos(e)*np.cos(b),np.cos(e)*np.sin(b),np.sin(e)],axis=-1)
def check(n,a,b,tol=1e-10):S.check(n,np.asarray(a),np.asarray(b),tol,0)
def freeze():
 original=json.loads((E1/'INPUT_LOCK.json').read_text())['files']
 for r in original:assert S.sha(r['path'])==r['sha256'],r['path']
 expected={r['path']:r['sha256'] for r in json.loads((E1/'OUTPUT_SHA256.json').read_text())['files']}
 used=list((E1/'E1').glob('*.npz'))+[E1/'SCORES.csv',E1/'run_experiments.py']
 for p in used:assert S.sha(p)==expected[p.relative_to(E1).as_posix()]
 prior_manifest={r['path']:r['sha256'] for r in json.loads((PREVIOUS/'OUTPUT_SHA256.json').read_text())['files']}
 prior_used=[PREVIOUS/'C_SCORES.csv',PREVIOUS/'C_GAP_REDUCTIONS.csv',PREVIOUS/'geometry_model.py']+list((PREVIOUS/'C').glob('*.npz'))
 for p in prior_used:assert S.sha(p)==prior_manifest[p.relative_to(PREVIOUS).as_posix()],str(p)
 assert S.sha(ROOT/'geometry_model.py')==S.sha(PREVIOUS/'geometry_model.py')
 files=original+[dict(path=str(p),sha256=S.sha(p)) for p in used+prior_used]+[dict(path=str(p),sha256=S.sha(p)) for p in ROOT.glob('*.py')]+[dict(path=str(ROOT/'PROTOCOL.md'),sha256=S.sha(ROOT/'PROTOCOL.md'))]
 write('INPUT_LOCK.json',dict(files=files,source_commit='0686b23ceeefb696bc158b32b39f8077c564ef5d',runtime=sys.version,command=sys.argv))
def preserve():
 for r in json.loads((ROOT/'INPUT_LOCK.json').read_text())['files']:assert S.sha(r['path'])==r['sha256'],r['path']
def models():
 original=V.SourceFFD();new=GeometryFFD(banks=original.banks);return original,new
def eval_batches(model,x,case,gradient=True,batch=48):
 hh=[];jj=[]
 for k in range(0,len(x),batch):
  S.stopcheck();h,j=model.batch(x[k:k+batch],case,gradient=gradient);hh.append(h)
  if gradient:jj.append(j)
 return np.concatenate(hh),np.concatenate(jj) if gradient else None
