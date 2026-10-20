"""Read-only completion checks: locked cells, exact member bytes, remote S2, preserved S0/S1."""
from pathlib import Path
import base64,hashlib,json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];PREFIX='research/POWERJOINT_AUDIT_FOLLOWUP_20261020';HERE=ROOT/PREFIX/'S2_N2_GEOMETRY'
sys.path.insert(0,str(HERE.parent/'S0_CORRECTIONS'))
from github_io import session,api
S1='5b2f7c509863558e4de1f184d38f2404699d248e'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 s=session();head=api(s,'git/ref/heads/research/powerjoint-audit-followup-20261020')['object']['sha']
 def subtree(commit,path):
  cur=api(s,'git/commits/'+commit)['tree']['sha']
  for part in path.split('/'):cur=next(x['sha'] for x in api(s,'git/trees/'+cur)['tree'] if x['path']==part)
  d=api(s,'git/trees/'+cur,params={'recursive':1});assert not d.get('truncated')
  return {path+'/'+x['path']:x['sha'] for x in d['tree'] if x['type']=='blob'}
 remote=subtree(head,PREFIX+'/S2_N2_GEOMETRY');n=0
 for p in HERE.rglob('*'):
  if not p.is_file() or '__pycache__' in p.parts or p.suffix.lower() in ['.npz','.npy','.zip','.gz']:continue
  b=p.read_bytes();rel=p.relative_to(ROOT).as_posix();assert len(b)<=20_000_000 and remote.get(rel)==hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),rel;n+=1
 for path in [PREFIX+'/S0_CORRECTIONS',PREFIX+'/S1_N1_EVENTS','research/POWERJOINT_AUDIT_RERUN_20261020']:
  assert subtree(S1,path)==subtree(head,path),('PRESERVED_TREE_CHANGED',path)
 summary=PREFIX+'/00_SUMMARY_KO.md';old=base64.b64decode(api(s,'contents/'+summary,params={'ref':S1})['content']);assert (ROOT/summary).read_bytes().startswith(old),'S1_SUMMARY_PREFIX_CHANGED'
 lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text())
 for rel,want in lock['contract_hashes'].items():assert sha(HERE/rel)==want,rel
 if (HERE/'OUTPUT_INDEX.json').exists():
  index=json.loads((HERE/'OUTPUT_INDEX.json').read_text())
  for rel,record in index['outputs'].items():
   p=HERE/rel;assert p.stat().st_size==record['bytes'] and sha(p)==record['sha256'],('OUTPUT_INDEX',rel)
 df=pd.read_csv(HERE/'RESULTS.csv',float_precision='round_trip');matrix=pd.read_csv(HERE/'CASE_MATRIX.csv');keys=['case','channel','bias','seed','arm']
 assert len(df)==792 and not df.duplicated(keys).any() and set(map(tuple,df[keys].to_numpy()))==set(map(tuple,matrix[keys].to_numpy()))
 assert df.status.eq('TECHNICAL_PASS').all() and df.scorer_max_abs_difference.max()<=1e-9
 metrics=['heading_rmse_deg','signed_heading_deg','heading_sigma_rms_deg','heading95','heading_nees','pose_nees','conditional_xy_nees','xy_rmse_m','bias_rmse_dps','bias_mean_dps','bias_final_dps'];assert np.isfinite(df[metrics].to_numpy()).all()
 models=json.loads((HERE/'TRAIN_PARAMS.json').read_text());splits=json.loads((HERE/'TRAIN_SPLITS.json').read_text())['folds']
 for fold,record in models.items():
  assert record['training_key_sha256']==splits[fold]['training_key_sha256']
  a=record['models'];assert a['GEOM']['cuts']==a['GEOM_Q']['cuts']==a['DIST_ONLY']['cuts']
  assert len(a['GEOM']['scaler_mean'])==10 and len(a['GEOM_Q']['scaler_mean'])==11
  assert a['GEOM']['bin_feature']=='d_3D_m' and all(b['n_train']>=15 for arm in a.values() for b in arm['bin_stats'])
 receipt=json.loads((HERE/'MANIFEST.json').read_text())
 for record in receipt['original_artifacts']:
  assert record['archive_sha256']==record['release_readback_sha256'] and record['archive_bytes']==record['release_readback_bytes']
  folder=HERE/'execution'/record['name']
  for member in record['members']:
   if not member.get('summary_extracted'):continue
   p=folder/member['name'];assert p.stat().st_size==member['bytes'] and sha(p)==member['sha256'],str(p)
 # Recompute recorded inference features and learned predictions, separately
 # from the runtime adapter, using saved prior coordinates and fixed metadata.
 metadata=json.loads((HERE/'CASE_METADATA.json').read_text());cases={c['id']:c for c in metadata['legacy']+metadata['new']};feature_rows=0;feature_max=0.;prediction_max=0.
 for record in receipt['original_artifacts']:
  if record['actions_run_id'] not in [39374960558,39375649673]:continue
  folder=HERE/'execution'/record['name']
  for path in folder.rglob('ONLINE_FEATURES_*.csv'):
   cid=next(c for c in cases if path.name.startswith('ONLINE_FEATURES_'+c+'_'));case=cases[cid];fold=cid.split('_')[0] if cid.startswith('R') else 'ALL_OLD'
   f=pd.read_csv(path,float_precision='round_trip');anchor=np.asarray(case['anchor']);dx=anchor[0]-f.prior_x.to_numpy();dy=anchor[1]-f.prior_y.to_numpy();dd=np.sqrt(dx**2+dy**2+(anchor[2]-case['robot_z_m'])**2)
   angle=np.arctan2(dy,dx)-f.prior_yaw_rad.to_numpy()-np.radians(case['mount_deg']);logd=np.log10(np.maximum(dd,1e-6));g=np.column_stack([logd,logd**2,np.cos(angle),np.sin(angle),np.cos(2*angle),np.sin(2*angle),np.full(len(f),case['mount_deg']/45),*[np.full(len(f),v/10) for v in anchor]])
   feature_max=max(feature_max,float(abs(dd-f.distance_m.to_numpy()).max()))
   for arm,part in f.groupby('arm',sort=False):
    idx=part.index.to_numpy();rec=models[fold]['models'][arm];X=part[[f'f{i}' for i in range(len(rec['scaler_mean']))]].to_numpy();b=part.bin_scalar.to_numpy()
    expected=part.q.to_numpy()[:,None] if arm=='Q_POWER1' else dd[idx,None] if arm=='DIST_ONLY' else g[idx] if arm=='GEOM' else np.column_stack([g[idx],part.q.to_numpy()])
    feature_max=max(feature_max,float(abs(X-expected).max()),float(abs(b-(part.q.to_numpy() if arm=='Q_POWER1' else dd[idx])).max()))
    if arm in ['GEOM','DIST_ONLY']:assert part.q.isna().all(),'FORBIDDEN_Q_IN_GEOM_OR_DISTANCE_LOG'
    bins=np.searchsorted(rec['cuts'],b,side='right');mean=((X-np.asarray(rec['scaler_mean']))/np.asarray(rec['scaler_scale']))@np.asarray(rec['ridge_coef']).T+np.asarray(rec['ridge_intercept'])+np.asarray(rec['offsets'])[bins];C=np.asarray(rec['covs'])[bins]
    prediction_max=max(prediction_max,float(abs(mean-part[['mu_r','mu_s']].to_numpy()).max()),float(abs(C[:,0,0]-part.C00).max()),float(abs(C[:,0,1]-part.C01).max()),float(abs(C[:,1,1]-part.C11).max()))
   feature_rows+=len(f)
 assert feature_rows>0 and feature_max<=1e-12 and prediction_max<=1e-12,('INDEPENDENT_INFERENCE_FEATURE_PREDICTION',feature_max,prediction_max)
 d=json.loads((HERE/'DECISION.json').read_text());gain=pd.read_csv(HERE/'GAIN_COMPARISON.csv');new=gain[(gain.population=='new')&(gain.seed==0)];old=gain[(gain.population=='legacy')&(gain.channel=='full')&gain.case.str.endswith('_m0')]
 assert len(new)==36 and len(old)==12
 assert d['new_seed0']['pass_cells']==int((new.GEOM<=1.1*new.Q_POWER1).sum()) and d['legacy_M0']['pass_cells']==int((old.GEOM<=1.1*old.DIST_ONLY).sum())
 assert d['geom_q_additional']['improved_cells']==int((new.GEOM_Q<.95*new.GEOM).sum())
 print(json.dumps(dict(final_commit=head,remote_S2_files_byte_identical=n,preserved_S0_S1_and_original_audit=True,S1_root_summary_prefix_preserved=True,locked_rows=792,independent_11_max_abs=float(df.scorer_max_abs_difference.max()),original_archives_verified=len(receipt['original_artifacts']),inference_feature_rows=feature_rows,inference_feature_max_abs=feature_max,inference_prediction_max_abs=prediction_max,decision=d['scientific'],new_pass=d['new_seed0'],old_M0_pass=d['legacy_M0'],geom_q=d['geom_q_additional']),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
