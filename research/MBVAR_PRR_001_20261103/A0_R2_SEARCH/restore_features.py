"""Restore inference inputs from the producing run. Never fits or evaluates a model."""
import ast, hashlib, json, subprocess
from pathlib import Path
import numpy as np
import pandas as pd

out=Path(__file__).resolve().parent
cache=Path('D:/codex/MBVAR_PRR_001_20261103_inputs')
source=Path('D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2_artifacts/prepared/OBSERVATION_FEATURES_LABELS.csv.gz')
rev='902ddcaf0f8e59734bb8026d3bcdc36eab506a27'
def read(name):
 return subprocess.check_output(['git','show',rev+':research/PJ_DS_GATED_20261021/'+name])
def sha(b):return hashlib.sha256(b).hexdigest()
def definition(tree,name):
 return next(n for n in tree.body if (isinstance(n,ast.Assign) and n.targets[0].id==name) or (isinstance(n,ast.FunctionDef) and n.name==name))
series=read('series_dump.py'); mr=read('mu_recursive.py')
tree=ast.parse(series); offsets=ast.literal_eval(definition(tree,'OFFS').value)
space=dict(np=np,OFFS=offsets)
exec(compile(ast.Module([definition(tree,'taps')],type_ignores=[]),'pinned_taps','exec'),space)
existing=ast.literal_eval(definition(ast.parse(mr),'EXIST').value)
columns=existing+['ds_%+d'%i for i in offsets]
expected='6a69a36ad0f521e33a130a1bc1fbde5a4b7aae17ba62ec347ccc611fdd5c6fe4'
assert sha(source.read_bytes())==expected
features=pd.read_csv(source,usecols=['case','channel','pose_id','s_fp']+existing)
meta=dict(commit=rev,mu_recursive_sha256=sha(mr),series_dump_sha256=sha(series),feature_csv_sha256=expected,columns=columns,target='e_r',training_selection='full and route != held route',estimator='HistGradientBoostingRegressor(max_iter=200,learning_rate=0.05,max_leaf_nodes=15,l2_regularization=1.0,random_state=0)',record_type='inference inputs only',cases={})
for route in (4,5):
 case=f'R{route}_aB_m0'; rf=next(cache.rglob('H_LoS_'+case+'.npy')); h=np.load(rf,mmap_mode='r')
 samples=next(cache.rglob(case+'/SAMPLES.json')); pose=[r['pose_id'] for r in json.loads(samples.read_bytes())]
 assert len(set(pose))==len(h)==len(pose)
 chunks=[space['taps'](h[k:k+128,:,:,0]) for k in range(0,len(h),128)]
 taps=pd.DataFrame({key:np.concatenate([c[key] for c in chunks]) for key in chunks[0]},index=pose)
 table=features[(features.case==case)&(features.channel=='los')].set_index('pose_id',verify_integrity=True).loc[pose]
 error=float(abs(taps.s_fp_chk-table.s_fp).max());assert error<1e-9
 df=table[existing].join(taps[columns[len(existing):]],validate='one_to_one')
 timeline='results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/INPUTS/timeline_R%d_Tnone.csv'%route
 raw=subprocess.check_output(['git','show','9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13:'+timeline])
 import io
 ids=pd.read_csv(io.BytesIO(raw)).pose_id.to_numpy();assert len(set(ids))==len(ids)
 df=df.loc[ids];dest=out/(case+'_Native_LoS_features.npz');np.savez_compressed(dest,pose_id=ids,columns=np.array(columns),features=df.to_numpy(dtype=np.float64))
 meta['cases'][case]=dict(poses=len(ids),columns=len(columns),timeline_sha256=sha(raw),rf_sha256=sha(rf.read_bytes()),samples_sha256=sha(samples.read_bytes()),max_s_fp_difference=error,nonfinite_feature_cells=int((~np.isfinite(df.to_numpy())).sum()),feature_file_sha256=sha(dest.read_bytes()))
(out/'FEATURE_LINEAGE.json').write_text(json.dumps(meta,indent=2))
print(meta['cases'])
