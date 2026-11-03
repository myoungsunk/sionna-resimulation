"""Prelock canonical rows, then refit two held-route estimators under the approved amendment."""
import argparse, ast, gzip, hashlib, importlib.metadata as md, json, os, platform, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
import joblib

out=Path(__file__).resolve().parent
repo=out.parents[2]
old=Path('/mnt/d/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849')
cache=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs')
rev='902ddcaf0f8e59734bb8026d3bcdc36eab506a27'
def git(*args):return subprocess.check_output(['git','-c','safe.directory=*','-C',str(repo),*args])
def sha(b):return hashlib.sha256(b).hexdigest()
def save(name,d):(out/name).write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def load(name):return json.loads((out/name).read_text())
def source(name):return git('show',rev+':research/PJ_DS_GATED_20261021/'+name)
def original(raw,names,ns):
 nodes=[]
 for node in ast.parse(raw).body:
  name=node.name if isinstance(node,ast.FunctionDef) else node.targets[0].id if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) else None
  if name in names:nodes.append(node)
 assert len(nodes)==len(names)
 exec(compile(ast.Module(nodes,type_ignores=[]),'original_run_source','exec'),ns)
def main(mode):
 versions={n:md.version(n) for n in ['numpy','scipy','pandas','scikit-learn','cloudpickle','joblib','python-dateutil','pytz','six','tabulate','threadpoolctl','tzdata']}
 assert list(versions.values())==['2.3.3','1.16.2','2.3.2','1.7.2','3.1.2','1.6.0','2.9.0.post0','2026.5','1.17.0','0.9.0','3.7.0','2026.5'],versions
 assert platform.python_version()=='3.11.17'
 assert all(os.environ[k]=='1' for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'])
 src=old/'p2'; manifest_path='research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
 manifest=json.loads((src/manifest_path).read_bytes());featpath=old/'p2_artifacts/prepared/OBSERVATION_FEATURES_LABELS.csv.gz'
 assert sha(featpath.read_bytes())=='6a69a36ad0f521e33a130a1bc1fbde5a4b7aae17ba62ec347ccc611fdd5c6fe4'
 source_hash={}
 for rel in [manifest_path]+[c[k] for c in manifest['cases'] for k in ('full_path','los_path','samples_path')]:
  raw=(src/rel).read_bytes();oid=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest();assert oid==git('rev-parse',rev+':'+rel).decode().strip(),rel
  source_hash[rel]=sha(raw)
 ns=dict(json=json,np=np,pd=pd,V=SimpleNamespace(ROOT=src,MANIFEST=manifest,one=lambda filename:featpath if filename==featpath.name else None),HistGradientBoostingRegressor=HistGradientBoostingRegressor)
 original(source('series_dump.py'),['OFFS','taps'],ns)
 original(source('mu_recursive.py'),['DS','EXIST','feature_table','hgb'],ns)
 ft=ns['feature_table']();cols=ns['EXIST']+ns['DS'];lock=dict(source=rev,python=platform.python_version(),packages=versions,source_hash=source_hash,features_sha256=sha(featpath.read_bytes()),columns=cols,fit={})
 for route in ['R4','R5']:
  tr=ft[(ft.channel=='full')&(ft.route!=route)]
  lock['fit'][route]=dict(n=len(tr),ordered_keys=sha(tr[['case','channel','pose_id']].to_csv(index=False).encode()),ordered_X_f64=sha(tr[cols].to_numpy(dtype='<f8').tobytes()),ordered_y_f64=sha(tr.e_r.to_numpy(dtype='<f8').tobytes()))
 if mode=='lock':save('TRAINING_LOCK.json',lock);return
 assert load('TRAINING_LOCK.json')==lock
 reference=load('REFERENCE.json'); gates={};models={};details=[]
 for route in ['R4','R5']:
  case=route+'_aB_m0';tr=ft[(ft.channel=='full')&(ft.route!=route)];model=ns['hgb'](tr,cols,'e_r');models[case]=model
  refpath=cache/'refit_reference'/(case+'_MR_SERIES.csv.gz');assert sha(refpath.read_bytes())==reference[refpath.name]['sha256']
  tab=pd.read_csv(refpath);assert set(tab.case)=={case} and set(tab.channel)=={'full'} and set(tab.bias)=={'B0','L2'}
  inp=ft[(ft.case==case)&(ft.channel=='full')].set_index('pose_id',verify_integrity=True)
  for bias in ['B0','L2']:
   z=tab[tab.bias==bias];ids=z.pose_id.to_numpy();timeline=next(cache.rglob(case+'_'+bias+'.npz'))
   with np.load(timeline) as cf:assert np.array_equal(ids,cf['pose_id'])
   assert len(np.unique(ids))==len(ids)
   f=inp.loc[ids];y=f.e_r.to_numpy()-z.MU_R_EXDS__meas_r_cm.to_numpy()/100;pred=model.predict(f[cols]);err=abs(pred-y);ok=np.isclose(pred,y,atol=1e-10,rtol=1e-10)&np.isfinite(pred)&np.isfinite(y)
   gates[case+'_'+bias]=dict(n=len(ids),failed=int((~ok).sum()),max_abs_m=float(err.max()),worst_pose=int(ids[err.argmax()]))
   details.append(pd.DataFrame(dict(case=case,bias=bias,pose_id=ids,reference_m=y,prediction_m=pred,abs_error_m=err,passed=ok)))
 pd.concat(details).to_csv(out/'FULL_PARITY.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 passed=all(g['failed']==0 for g in gates.values());save('FULL_GATE.json',dict(passed=passed,conditions=gates))
 if not passed:return 2
 for case,model in models.items():
  ids=details[0 if case.startswith('R4') else 2].pose_id.to_numpy()
  f=ft[(ft.case==case)&(ft.channel=='los')].set_index('pose_id',verify_integrity=True).loc[ids]
  pred=model.predict(f[cols]);assert np.isfinite(pred).all()
  pd.DataFrame(dict(case=case,channel='Native_LoS',pose_id=ids,MU_R_EXDS_m=pred)).to_csv(out/(case+'_Native_LoS.csv'),index=False,float_format='%.17g')
  joblib.dump(model,out/(case+'_refit.joblib'),compress=3)
 save('NATIVE_LOCK.json',{p.name:sha(p.read_bytes()) for p in sorted(out.iterdir()) if p.name.endswith(('_Native_LoS.csv','_refit.joblib'))})
if __name__=='__main__':sys.exit(main(sys.argv[1]))
