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
 d=json.loads((HERE/'DECISION.json').read_text());gain=pd.read_csv(HERE/'GAIN_COMPARISON.csv');new=gain[(gain.population=='new')&(gain.seed==0)];old=gain[(gain.population=='legacy')&(gain.channel=='full')&gain.case.str.endswith('_m0')]
 assert len(new)==36 and len(old)==12
 assert d['new_seed0']['pass_cells']==int((new.GEOM<=1.1*new.Q_POWER1).sum()) and d['legacy_M0']['pass_cells']==int((old.GEOM<=1.1*old.DIST_ONLY).sum())
 assert d['geom_q_additional']['improved_cells']==int((new.GEOM_Q<.95*new.GEOM).sum())
 print(json.dumps(dict(final_commit=head,remote_S2_files_byte_identical=n,preserved_S0_S1_and_original_audit=True,S1_root_summary_prefix_preserved=True,locked_rows=792,independent_11_max_abs=float(df.scorer_max_abs_difference.max()),original_archives_verified=len(receipt['original_artifacts']),decision=d['scientific'],new_pass=d['new_seed0'],old_M0_pass=d['legacy_M0'],geom_q=d['geom_q_additional']),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
