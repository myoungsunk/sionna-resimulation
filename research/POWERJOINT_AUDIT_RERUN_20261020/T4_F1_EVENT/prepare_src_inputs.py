"""Prepare SRC_TAP event inputs from existing certified T6/T2 outputs only.

No sensor or RF generation. New-route P1 fitting uses old Full labels exclusively.
Run only after PROTOCOL_LOCK_SRC.json is committed.
"""
from pathlib import Path
import argparse,importlib.util,json,os,sys,traceback
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from run_events import load_npz,normalize,sha

def main():
 p=argparse.ArgumentParser();p.add_argument('--t6-root',type=Path,required=True);p.add_argument('--new-config',type=Path)
 p.add_argument('--source-root',type=Path,required=True);p.add_argument('--mode',choices=['old','new'],required=True)
 p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 items=[];inputs={str(HERE/'PROTOCOL_LOCK_SRC.json'):sha(HERE/'PROTOCOL_LOCK_SRC.json'),str(Path(__file__)):sha(Path(__file__))};records=[]
 try:
  receipt=a.t6_root/'ARTIFACT_RECEIPT.json'
  recovered=json.loads(receipt.read_text(encoding='utf-8'))
  if recovered.get('id')!=12236414588 or recovered.get('verified_sha256')!='89dae721d000c3f8897b39b4cefdf75bbe635bb1ceffbe830a8b56d2ef826011':raise ValueError('FROZEN_T6_ARTIFACT_ID_OR_SHA_MISMATCH')
  inputs[str(receipt)]=sha(receipt)
  def unique(pattern):
   matches=list(a.t6_root.rglob(pattern))
   if len(matches)!=1:raise ValueError('EXPECTED_UNIQUE_T6_INPUT:'+pattern)
   inputs[str(matches[0])]=sha(matches[0]);return matches[0]
  manifest=unique('PARAMETER_MANIFEST.json');meta=json.loads(manifest.read_text())
  if meta.get('range_model')!='SRC_TAP':raise ValueError('T6_RANGE_MODEL_MISMATCH')
  train_path=unique('OOF_PARAMETERS_SRC_TAP.csv.gz')
  if a.mode=='old':
   cases=json.loads((a.source_root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())['cases']
   for case in cases:
    cid=case['id']
    if cid not in {'R5_aA_m0','R2_aA_m45'}:continue
    src=unique(cid+'_full_B0_SRC_TAP.npz');old=unique(cid+'_full_B0_B_OLD.npz')
    data=normalize(load_npz(src));old_data=normalize(load_npz(old))
    if not np.array_equal(data['t'],old_data['t']) or not np.array_equal(data['z'],old_data['z']):raise ValueError('T6_SOURCE_OLD_INPUT_MISMATCH')
    items.append(dict(case=case,bias='B0',trace=os.path.relpath(src,a.out),bold_reference=os.path.relpath(old,a.out),source_reference=os.path.relpath(src,a.out)))
  else:
   if a.new_config is None:raise ValueError('NEW_CONFIG_REQUIRED')
   sys.path.insert(0,str(HERE.parent/'T1_MEMORY'));from unit_tests import load_engine
   load_engine(a.source_root)
   sys.path.insert(0,str(a.source_root/'research/CHAIN_HYPOTHESIS_20261019'))
   spec=importlib.util.spec_from_file_location('src_event_original_run',a.source_root/'research/CHAIN_HYPOTHESIS_20261019/run.py')
   original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
   frame=pd.read_csv(train_path);train=frame[frame.channel=='full'].copy()
   if set(train.route)!= {'R2','R4','R5'}:raise ValueError('EXPECTED_OLD_ONLY_SOURCE_TRAIN_ROUTES')
   config=json.loads(a.new_config.read_text());inputs[str(a.new_config)]=sha(a.new_config)
   if config.get('range_model')!='B_OLD':raise ValueError('EXPECTED_T2_B_OLD_ASSEMBLY')
   event_cases={e['case'] for e in json.loads((HERE/'PROTOCOL_LOCK_SRC.json').read_text())['events']}
   for item in config['cases']:
    if item.get('bias')!='B0' or item['case']['id'] not in event_cases:continue
    cid=item['case']['id'];trace=a.new_config.parent/item.get('npz',item.get('trace',''));feature_path=a.new_config.parent/item['features']
    inputs[str(trace)]=sha(trace);inputs[str(feature_path)]=sha(feature_path)
    data=normalize(load_npz(trace));feature=pd.read_csv(feature_path).set_index('pose_id').loc[data['radio_pose_ids']].reset_index()
    if not np.isfinite(feature[original.FEATURES].to_numpy()).all():raise ValueError('NONFINITE_FULL_ONLY_FEATURE')
    mu,C,fit=original.fit_model(np,train,feature,original.site_weights(np,pd,train),'POWER_BIN_JOINT',original.GROUPS)
    if len(mu)!=int(data['radio_mask'].sum()):raise ValueError('RF_PARAMETER_COUNT_MISMATCH')
    data['mu']=np.zeros_like(data['mu']);data['C']=np.tile(np.eye(2),(len(data['t']),1,1))
    data['mu'][data['radio_mask']]=mu;data['C'][data['radio_mask']]=C
    # Aliases are updated too so no consumer can silently pick stale B_OLD parameters.
    data['mu_input']=data['mu'];data['C_input']=data['C'];data['risk']=np.zeros(len(data['t']))
    path=a.out/(cid+'_B0_SRC_TAP.npz');np.savez_compressed(path,**data)
    items.append(dict(case=item['case'],bias='B0',trace=path.name,bold_reference=os.path.relpath(trace,a.out)))
    records.append(dict(case=cid,range_model='SRC_TAP',training_routes=['R2','R4','R5'],training_new_rows=0,fit=fit))
  if len(items)!=(2 if a.mode=='old' else 5):raise ValueError('EXPECTED_EVENT_CASE_COUNT:'+str(len(items)))
  (a.out/'CASES.json').write_text(json.dumps(dict(range_model='SRC_TAP',cases=items),indent=2),encoding='utf-8')
  (a.out/'TRAIN_PARAMS.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
  (a.out/'MANIFEST.json').write_text(json.dumps(dict(technical='TECHNICAL_PASS_PREPARATION',inputs=inputs,case_ids=[x['case']['id'] for x in items],actions_run_id=os.getenv('GITHUB_RUN_ID'),artifact_id=None),indent=2),encoding='utf-8')
 except Exception as exc:
  (a.out/'ERRORS.json').write_text(json.dumps([dict(error=str(exc),traceback=traceback.format_exc(),retry=False)],indent=2),encoding='utf-8');raise
if __name__=='__main__':main()
