import hashlib,json,platform,sys
from pathlib import Path
import numpy as np
import pandas as pd
out=Path(__file__).resolve().parent
cache=Path('D:/codex/MBVAR_PRR_001_20261103_inputs')
old=Path('D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(n,d):(out/n).write_text(json.dumps(d,indent=2,allow_nan=False))
records=[]
for path in sorted(cache.rglob('*.npz')):
 if 'CONTROL' not in path.parts:continue
 with np.load(path) as z:
  j=list(z['names']).index('OFF_MB'); b=list(z['names']).index('OFF_BB')
  R=z['R'][:,b]; m=z['mu'][:,j];eig=np.linalg.eigvalsh(R)
  assert np.isfinite(m).all() and np.isfinite(R).all() and eig.min()>0 and np.all(R[:,0,1]==0) and np.all(R[:,1,0]==0)
  records.append(dict(file=path.name,bytes_sha256=sha(path),mu_source='OFF_MB',R_source='OFF_BB',n=len(R),min_eigenvalue=float(eig.min()),max_abs_Rrs=0,mu_sha256=hashlib.sha256(m.tobytes()).hexdigest()))
assert len(records)==6
cols=['case','channel','pose_id','s_fp','fp_tap']
featpath=old/'p2_artifacts/prepared/OBSERVATION_FEATURES_LABELS.csv.gz'
features=pd.read_csv(featpath,usecols=cols)
f=features[(features.case=='R2_aB_m0')&(features.channel=='full')].set_index('pose_id',verify_integrity=True)
z=np.load(next(cache.rglob('R2_aB_m0_B0.npz'))); ids=np.unique(z['pose_id'])
raw=next(cache.rglob('H_R2_aB_m0.npy'));H=np.load(raw,mmap_mode='r')
samples=json.loads(next(cache.rglob('R2_aB_m0/SAMPLES.json')).read_text()); lookup={v['pose_id']:i for i,v in enumerate(samples)};assert len(lookup)==len(samples)
values=[];maxdiff=0
for group in np.array_split(ids,32):
 h=np.asarray(H[[lookup[int(i)] for i in group],:,:,0],dtype=np.complex128);nf=h.shape[1]
 amp=np.abs(np.fft.ifft(h*np.hanning(nf)[None,:,None],n=4*nf,axis=1)*nf)
 row=np.arange(len(group));strong=amp[row,:,amp.max(axis=1).argmax(axis=1)]
 fp=(strong>=.3*strong.max(axis=1)[:,None]).argmax(axis=1)
 assert np.array_equal(fp,f.loc[group,'fp_tap']) and np.all(fp+1<4*nf)
 def signed(offset):
  p=amp[row,fp+offset]**2;assert np.all(p.sum(1)>np.finfo(float).tiny);return (p[:,0]-p[:,1])/p.sum(1)
 s=signed(0);maxdiff=max(maxdiff,float(np.max(abs(s-f.loc[group,'s_fp']))));values.extend(abs(signed(1)-s))
assert maxdiff<1e-10
save('CALIBRATION_AND_ARRAYS.json',dict(records=records,calibration=dict(case='R2_aB_m0',channel='full',timeline='B0 unique original pose_id, equal weights, all phases',n=len(ids),feature_reference_sha256=sha(featpath),raw_sha256=sha(raw),max_sfp_error=maxdiff,tau_ds=float(np.quantile(values,.9,method='linear')),quantile_method='linear')))
save('ENVIRONMENT.json',dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,pandas=pd.__version__,cpu='Intel Core i5-13400',purpose='A0 evidence preparation'))
