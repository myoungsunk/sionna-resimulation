import hashlib,io,json,subprocess
from pathlib import Path
import pandas as pd
import numpy as np
a=Path(__file__).resolve().parent
q=Path('D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849')
ref='7e2855314de867e0481f8eb5ed1a07c48710f364'
raw='9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13'
pkg='research/DS_MASK_CAUSAL_X1_X2_20261026/'
def git(*args):return subprocess.check_output(['git',*args])
def sha(data):return hashlib.sha256(data).hexdigest()
def save(n,d):(a/n).write_text(json.dumps(d,indent=2))
records=json.loads((a/'SOURCE_INPUTS.json').read_text())['files']
lock={f['path']:f['sha256'] for f in records}
for rt in (2,4,5):
 path=f'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/INPUTS/timeline_R{rt}_Tnone.csv'
 data=git('show',raw+':'+path);lock[path]=sha(data)
 table=pd.read_csv(io.BytesIO(data))
 for b in ('B0','L2'):
  f=next(Path('D:/codex/MBVAR_PRR_001_20261103_inputs').rglob(f'R{rt}_aB_m0_{b}.npz'))
  with np.load(f) as z:assert np.array_equal(table.pose_id,z['pose_id']) and np.allclose(table.t_s,z['t_s'],rtol=0,atol=1e-12)
for p in ['p2_artifacts/prepared/OBSERVATION_FEATURES_LABELS.csv.gz','p2_artifacts/prepared/OOF_PARAMETERS.csv.gz','p2/research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz','p2/research/PJ_DS_GATED_20261021/mu_recursive.py']:
 lock[p]=sha((q/p).read_bytes())
for p in ['pol_bias_model/exp_pb.py','mbvar_control_correction_20261029/ctl_core.py','reflect_model/common.py','reflect_model/fetch_inputs.sh']:
 lock[pkg+p]=sha(git('show',ref+':'+pkg+p))
save('VERIFIED_INPUT_SUBSET.json',dict(files=lock,complete=False,missing='Channel-specific frozen Native-LoS MB range correction or original fitted inference object. MR_SERIES is Full-only; mu_recursive.py fits held-route HGB and exports series only for full. No refit or Full-to-LoS substitution.'))
paths=git('ls-tree','-r','--name-only',ref,pkg+'mbvar_control_correction_20261029/results',pkg+'mbvar_e2_e5_revalidation_20261029/results').decode().splitlines()
lineage=[]
for p in paths:
 if p.endswith('.csv') and any(s in p.split('/')[-1] for s in ['SEED_GRID_CONTROL','SEED_FACTORIAL','ALL_SEEDS','E1_SEEDS','SEED_SPREAD']):
  data=git('show',ref+':'+p);df=pd.read_csv(io.BytesIO(data));seeds=sorted(set(map(int,df.seed.dropna()))) if 'seed' in df else None
  lineage.append(dict(path=p,sha256=sha(data),seeds=seeds))
save('SEED_LINEAGE.json',dict(commit=ref,checked=lineage,development=list(range(10)),stability=list(range(10,30)),claim='Additional sensor realizations on same known RF only. Prior use outside inspected registries unknown. No claim of unseen seeds.'))
