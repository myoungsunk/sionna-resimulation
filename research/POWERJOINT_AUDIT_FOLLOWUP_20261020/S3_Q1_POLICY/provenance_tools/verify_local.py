"""Independent lock/OOF/decision readback; cryptographic remote text verification."""
from pathlib import Path
import base64,hashlib,json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];PREFIX='research/POWERJOINT_AUDIT_FOLLOWUP_20261020';HERE=ROOT/PREFIX/'S3_Q1_POLICY';S2='8821d2e4d80ed749b5c4c5e3901e42957d29b2eb'
sys.path.insert(0,str(HERE.parent/'S0_CORRECTIONS'))
from github_io import session,api
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 s=session();head=api(s,'git/ref/heads/research/powerjoint-audit-followup-20261020')['object']['sha']
 def subtree(commit,path):
  cur=api(s,'git/commits/'+commit)['tree']['sha']
  for part in path.split('/'):cur=next(x['sha'] for x in api(s,'git/trees/'+cur)['tree'] if x['path']==part)
  d=api(s,'git/trees/'+cur,params={'recursive':1});assert not d.get('truncated');return {path+'/'+x['path']:x['sha'] for x in d['tree'] if x['type']=='blob'}
 remote=subtree(head,PREFIX+'/S3_Q1_POLICY');n=0
 for p in HERE.rglob('*'):
  if not p.is_file() or '__pycache__' in p.parts or p.suffix.lower() in ['.npz','.npy','.zip','.gz','.pkl']:continue
  b=p.read_bytes();rel=p.relative_to(ROOT).as_posix();assert len(b)<=20_000_000 and remote.get(rel)==hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),rel;n+=1
 for path in [PREFIX+'/S0_CORRECTIONS',PREFIX+'/S1_N1_EVENTS',PREFIX+'/S2_N2_GEOMETRY','research/POWERJOINT_AUDIT_RERUN_20261020']:assert subtree(S2,path)==subtree(head,path),('PRESERVED_TREE_CHANGED',path)
 summary=PREFIX+'/00_SUMMARY_KO.md';old=base64.b64decode(api(s,'contents/'+summary,params={'ref':S2})['content']);assert (ROOT/summary).read_bytes().startswith(old),'S2_SUMMARY_PREFIX_CHANGED'
 lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text());assert lock['oof_scope'].startswith('HGB_STAGE_')
 for rel,want in lock['contract_hashes'].items():assert sha(HERE/rel)==want,rel
 for item in lock['label_shards']:assert sha(HERE/item['file'])==item['sha256']
 if (HERE/'OUTPUT_INDEX.json').exists():
  for rel,r in json.loads((HERE/'OUTPUT_INDEX.json').read_text())['outputs'].items():assert (HERE/rel).stat().st_size==r['bytes'] and sha(HERE/rel)==r['sha256'],rel
 df=pd.read_csv(HERE/'POLICY_RESULTS.csv',float_precision='round_trip');matrix=pd.read_csv(HERE/'EVALUATION_MATRIX.csv');keys=['case','channel','bias','seed','arm','scope'];assert len(df)==288 and not df.duplicated(keys).any() and set(map(tuple,df[keys].values))==set(map(tuple,matrix[keys].values))
 assert df.status.eq('TECHNICAL_PASS').all() and df.scorer_max_abs_difference.max()<=1e-9
 names=['heading_rmse_deg','signed_heading_deg','heading_sigma_rms_deg','heading95','heading_nees','pose_nees','conditional_xy_nees','xy_rmse_m','bias_rmse_dps','bias_mean_dps','bias_final_dps'];assert np.isfinite(df[names].to_numpy()).all()
 comparison=[]
 for key,g in df.groupby(['case','channel','bias']):
  g=g.set_index('arm');ref='POWER1' if key[1]=='full' else 'R0';comparison.append((key[1],g.loc['POLICY_V3','heading_rmse_deg']<=1.1*g.loc[ref,'heading_rmse_deg']))
 full=sum(int(p) for c,p in comparison if c=='full');los=sum(int(p) for c,p in comparison if c=='los');d=json.loads((HERE/'DECISION.json').read_text());assert full==d['full_pass'] and los==d['los_pass']
 assert d['scientific']==('SUPPORTED_BUT_LIMITED' if full==64 and los==8 else 'NOT_ESTABLISHED')
 margins=json.loads((HERE/'MARGINS.json').read_text())['margins'];oof_count=0;max_margin_error=0.
 for outer in ['R2','R4','R5','ALL_OLD']:
  paths=list((HERE/'execution').rglob(f'OOF_PREDICTIONS_{outer}_*.csv'));assert paths
  f=pd.concat([pd.read_csv(p,float_precision='round_trip') for p in paths],ignore_index=True);assert not f.duplicated(['outer','case','bias','seed','frame']).any();pred=f[['predicted_'+x for x in ['R0','INFLATE4','SKIP']]].to_numpy();select=np.argmax(pred,axis=1);assert np.array_equal(np.array(['R0','INFLATE4','SKIP'])[select],f.selected_unadjusted_action.to_numpy())
  for j,action in enumerate(['R0','INFLATE4','SKIP']):
   take=select==j;r=margins[outer][action];assert int(take.sum())==r['n_selected']
   if take.any():
    err=np.maximum(0,pred[take,j]-f.loc[take,'actual_'+action].to_numpy());delta=float(np.quantile(err,.8,method='linear'));difference=abs(delta-r['delta']);max_margin_error=max(max_margin_error,difference);assert difference<=1e-9 and r['enabled_v3']
   else:assert r['delta'] is None and not r['enabled_v3'] and r['status']=='UNCALIBRATED_NO_OOF_SELECTION'
  oof_count+=len(f)
 assert oof_count==sum(x['included'] for x in lock['label_shards'])==351060
 manifest=json.loads((HERE/'MANIFEST.json').read_text())
 for r in manifest['original_artifacts']:
  assert r['archive_sha256']==r['release_readback_sha256'] and r['archive_bytes']==r['release_readback_bytes']
  folder=HERE/'execution'/r['name']
  for member in r['members']:
   if member.get('summary_extracted'):
    p=folder/member['name'];assert p.stat().st_size==member['bytes'] and sha(p)==member['sha256'],p
 print(json.dumps(dict(final_commit=head,remote_S3_files_byte_identical=n,preserved_S0_S1_S2_and_original_audit=True,S2_root_prefix_preserved=True,locked_evaluation_rows=288,locked_label_rows=oof_count,independent_11_max_abs=float(df.scorer_max_abs_difference.max()),margin_recalculation_max_abs=max_margin_error,original_archives_verified=len(manifest['original_artifacts']),full_pass=full,los_pass=los,scientific=d['scientific'])),flush=True)
if __name__=='__main__':main()
