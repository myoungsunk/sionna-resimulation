"""S3 adapter around the byte-frozen canonical engine. No engine modifications."""
from pathlib import Path
import base64,contextlib,hashlib,io,json,os,pickle,sys
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;SOURCE=HERE.parents[2];AUDIT=SOURCE/'research/POWERJOINT_AUDIT_RERUN_20261020'
sys.path.insert(0,str(AUDIT/'T1_MEMORY'))
from unit_tests import load_engine
load_engine(SOURCE)
sys.path.insert(0,str(AUDIT));sys.path.insert(0,str(SOURCE/'research/CHAIN_HYPOTHESIS_20261019'))
import canonical_engine as engine
import run as original
from source_model import SourceFFD
from scalar_power import ScalarPower
from replay import score
sys.path.insert(0,str(HERE.parent/'S1_N1_EVENTS'))
from independent_score import score_window
from prepare_contract import MEASURED,FEATURES,sha,digest,dump
ACTIONS=['POWER','R0','INFLATE4','SKIP'];NONPOWER=ACTIONS[1:]
def load(p):
 with np.load(p,allow_pickle=False) as f:return {k:f[k] for k in f.files}
def runtime(out):
 lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text());assert sha(AUDIT/'canonical_engine.py')==lock['engine_sha256'];assert sha(AUDIT/'T2_NEW_ROUTE_BASELINE/PROTOCOL_LOCK.json')==lock['sensor_lock_sha256']
 for file,value in lock['contract_hashes'].items():assert sha(HERE/file)==value,('CONTRACT_HASH',file)
 for item in lock['label_shards']:assert sha(HERE/item['file'])==item['sha256']
 assert sha(SOURCE.parent/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz')==lock['labels_sha256']
 assert sha(SOURCE.parent/'reference_ae/OOF_PARAMETERS.csv.gz')==lock['cached_oof_sha256']
 import p0_initial
 p0_initial.OUT=out/'bank_audit';p0_initial.OUT.mkdir(exist_ok=True)
 return lock,SourceFFD()
def internal_features(measured,P,h,H,mu,C,z):
 nu=z-h-mu;S=H@P@H.T+C
 a=np.r_[measured,nu@np.linalg.solve(S,nu),np.sqrt(P[2,2]),P[2,3],H[1,2]]
 assert a.shape==(21,) and np.isfinite(a).all(),'INVALID_CAUSAL_FEATURES'
 return a
def data_old(raw,frame,case,bias,seed,mu=None,C=None,channel='full'):
 packet=raw[case['id'],channel];ids=packet['pose_id'];ordered=frame.set_index('pose_id').loc[ids];t=packet['t_s'];truth=packet['truth_for_offline_scoring_only'][:,:3];z=np.c_[packet['z_r_m'],packet['z_s']]
 assert np.max(abs(z-ordered[['range_m','s_fp']].to_numpy()))<=1e-10,'FEATURE_OBSERVATION_PARITY'
 controls,initial=original.build_positive_bias_controls(t,truth,bias,seed)
 if mu is None:
  mu=ordered[['mu_r','mu_s']].to_numpy();C=np.zeros((len(t),2,2));C[:,0,0]=ordered.C00;C[:,1,1]=ordered.C11;C[:,0,1]=C[:,1,0]=ordered.C01
 return dict(t=t,truth=truth,z=z,mu=mu,C=C,controls=controls,initial=initial,radio=np.ones(len(t),bool),measured=ordered[MEASURED].to_numpy(),ids=ids)
def recurse(model,d,case,specs,callback=None,**kw):
 # The engine's per-call progress print would otherwise emit a line for every label.
 with contextlib.redirect_stdout(io.StringIO()):return engine.run(d['t'],d['controls'],d['initial'],d['z'],d['mu'],d['C'],np.zeros(len(d['t'])),case,model,specs,radio_mask=d['radio'],decision_provider=callback,**kw)
def finite_spd(r):
 for k in ('state','prior','cov','prior_cov'):assert np.isfinite(r[k]).all(),('NONFINITE',k)
 eig=min(float(np.linalg.eigvalsh(r[k]).min()) for k in ('cov','prior_cov'));assert eig>0,('NONSPD',eig)
 return eig
def metrics(r,j,truth,bias,mask):
 x=r['state'][mask,j,:4];P=r['cov'][mask,j,:4,:4];gt=truth[mask];a=score(x,P,gt,bias,np.ones(len(x),bool));b=score_window(x,P,gt,bias);delta=max(abs(a[k]-b[k]) for k in a)
 assert len(a)==11 and np.isfinite(list(a.values())).all() and delta<=1e-9,('INDEPENDENT_SCORE',delta)
 return dict(n=int(mask.sum()),scorer_max_abs_difference=delta,**a)
def parity(r,j,ref,k):
 assert np.array_equal(r['t'],ref['t']),'CLOCK_PARITY'
 s=float(abs(r['state'][:,j,:4]-ref['state'][:,k,:4]).max());p=float(abs(r['cov'][:,j,:4,:4]-ref['cov'][:,k,:4,:4]).max());g=int(np.count_nonzero(r['accepted'][:,j]!=ref['accepted'][:,k]));return s,p,g
def save_trace(path,r,d):
 np.savez_compressed(path,**r,truth_for_offline_scoring_only=d['truth'],observations=d['z'],mu_input=d['mu'],C_input=d['C'],radio_mask=d['radio'],controls_dt=d['controls']['dt_s'],controls_ds=d['controls']['ds_odom'],controls_dyaw=d['controls']['dtheta_gyro'],initial_pose=d['initial'],**({'los_exists_at_radio':d['los_exists']} if 'los_exists' in d else {}))
def controls_hash(d):return digest({k:v.tolist() for k,v in d['controls'].items()})
def serialize(obj):
 b=pickle.dumps(obj,protocol=5);return dict(base64=base64.b64encode(b).decode(),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def deserialize(rec):
 b=base64.b64decode(rec['base64']);assert hashlib.sha256(b).hexdigest()==rec['sha256'];return pickle.loads(b)
def manifest(out,stage,errors,**kwargs):
 dump(out/'ERRORS.json',errors);dump(out/'MANIFEST.json',dict(task='S3_Q1_POLICY',stage=stage,technical='TECHNICAL_PASS' if not errors else 'ERROR_OR_INCOMPLETE',protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),actions_run_id=os.getenv('GITHUB_RUN_ID'),source_commit=os.getenv('GITHUB_SHA'),outputs={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file() and p.name!='MANIFEST.json'},**kwargs))
 for p in out.rglob('*'):
  if p.is_file() and p.suffix in ('.csv','.json'):assert p.stat().st_size<=20_000_000,('FILE_LIMIT',p)
