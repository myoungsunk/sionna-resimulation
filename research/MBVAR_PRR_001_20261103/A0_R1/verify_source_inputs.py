import concurrent.futures as cf, hashlib, json, pathlib, subprocess, urllib.request, platform
import numpy as np
root=pathlib.Path(__file__).resolve().parent
cache=pathlib.Path('D:/codex/MBVAR_PRR_001_20261103_inputs');cache.mkdir(exist_ok=True)
rev='9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13'
def git(*args):return subprocess.check_output(['git',*args])
block='results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/'
paths=['LP_plus45_bank.npz','LP_minus45_bank.npz']
for rt in (2,4,5):
 c=f'R{rt}_aB_m0'
 paths.extend([block+'FULL_RF/H_'+c+'.npy',block+'H_LoS_'+c+'.npy',block+c+'/SAMPLES.json'])
 paths.extend(['research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/CONTROL/'+c+'_'+b+'.npz' for b in ('B0','L2')])
def fetch(p):
 blob=git('rev-parse',rev+':'+p).decode().strip()
 dest=cache/p;dest.parent.mkdir(parents=True,exist_ok=True)
 data=git('cat-file','blob',blob)
 if data.startswith(b'version https://git-lfs'):
  oid=data.splitlines()[1].decode().split(':')[1]
  data=dest.read_bytes() if dest.exists() else urllib.request.urlopen('https://media.githubusercontent.com/media/myoungsunk/sionna-resimulation/'+rev+'/'+p,timeout=90).read()
  assert hashlib.sha256(data).hexdigest()==oid
 assert data
 dest.write_bytes(data)
 row=dict(path=p,blob=blob,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
 if '/CONTROL/' in p:
  with np.load(dest,allow_pickle=False) as z:
   row['fields']={k:[str(z[k].dtype),list(z[k].shape)] for k in z.files if not z[k].dtype.hasobject}
 return row
with cf.ThreadPoolExecutor(3) as pool: rows=list(pool.map(fetch,paths))
(root/'SOURCE_INPUTS.json').write_text(json.dumps(dict(commit=rev,files=rows),indent=2))
print(len(rows),list(rows[-1]['fields']))
