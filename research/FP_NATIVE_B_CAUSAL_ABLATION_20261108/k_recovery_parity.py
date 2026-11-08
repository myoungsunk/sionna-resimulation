#!/usr/bin/env python3
"""Replay baseline B and K1/K2 recoveries against frozen R5 traces on identical inputs."""
from __future__ import annotations
import argparse,sys,pathlib,json,hashlib,datetime as dt
import numpy as np

def h(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--routes',nargs='+',choices=['R2','R4','R5'],default=['R2','R4','R5']);a=p.parse_args()
 repo=a.repo.resolve();out=a.out.resolve();assert not out.exists();out.mkdir(parents=True)
 root=repo/'research/FP_SC_RECOVERY_R0_R5_20261107';sys.path.insert(0,str(root));import r45
 core,online,model,sourcehash=r45.load_original_model(r45.SRC)
 arms=r45.ARMS;rows=[];checks=[]
 for route in a.routes:
  case=route+'_B0_Full_10';on=r45.data(case,'online.npz')
  B,S,pools,oldcenter=r45.prepare(case,on)
  tr=r45.replay_six(core,online,model,on,B,S,pools,case)
  archived=root/'R45_RUN_001'/(route+'_TRACE.npz')
  assert archived.exists(),('MISSING_REFERENCE_TRACE',archived)
  parity={}
  with np.load(archived,allow_pickle=False) as old:
   for field in ['x','P','prior','Pprior','shadow_x','shadow_P','H','h','R','K','z','center','nis','gate_nis','selected','alarm','accepted']:
    left=np.asarray(tr[field]);right=old[field]
    assert left.shape==right.shape,(case,field,'SHAPE')
    if field in ('selected','alarm','accepted'):
     assert np.array_equal(left,right),(case,field,'MASK_OR_SELECTION_MISMATCH')
     parity[field]=0.
    else:
     err=float(np.max(np.abs(left-right)/np.maximum(1.,np.abs(right))))
     assert err<=1e-10,(case,field,err)
     parity[field]=err
  ev=r45.data(case,'evaluator.npz')
  metrics,_,_=r45.evaluate(case,on,ev,B,S,pools,oldcenter,tr)
  rows+=metrics;checks.append({'case':case,'parity':parity,'status':'PASS_REPLAY_SELF_CHECK'})
  print('K_REPLAY_COMPLETE',case,flush=True)
 names=['B','DROP','K1_R','K2_R','K1_RS','K2_RS'];pooled={}
 N=sum(len(r45.data(route+'_B0_Full_10','online.npz')['t']) for route in a.routes)
 for name in names:
  data=[m for m in rows if m['arm']==name]
  assert len(data)==len(a.routes)
  pooled[name]={
   'n':sum(v['n'] for v in data),
   'heading_RMSE_deg':float(np.sqrt(sum(v['n']*v['heading_RMSE_deg']**2 for v in data)/N)),
   'XY_RMSE_cm':float(100*np.sqrt(sum(v['n']*v['XY_RMSE_m']**2 for v in data)/N)),
   'normal_harm':int(sum(v['selected_normal_harm'] for v in data)),
   'exact_recovery':int(sum(v['selected_exact_recovery'] for v in data)),
   'accepted_normal_harm':int(sum(v['accepted_normal_harm'] for v in data)),
   'NEES3_mean':float(sum(v['n']*v['NEES3_mean'] for v in data)/N)}
 assert all(x['n']==N for x in pooled.values())
 result={'status':'PASS_IMPLEMENTER_REPLAY_SELF_CHECK','independent_audit':False,'source_commit':'c141839093d1a2e4a76f91eea632cb6467163e28','checks':checks,'per_case':rows,'pooled':pooled,'effect_of_K_vs_B':{name:{'heading_RMSE_delta_deg':pooled[name]['heading_RMSE_deg']-pooled['B']['heading_RMSE_deg'],'XY_RMSE_delta_cm':pooled[name]['XY_RMSE_cm']-pooled['B']['XY_RMSE_cm']} for name in names if name!='B'}}
 (out/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
 (out/'OUTPUT_HASHES.json').write_text(json.dumps({'RESULTS.json':h(out/'RESULTS.json')},indent=2)+'\n')
 print(json.dumps({'status':result['status'],'pooled':pooled},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
