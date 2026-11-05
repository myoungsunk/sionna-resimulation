"""One approved stored-only G4 run. No RT imports or legacy evidence writes."""
import argparse,csv,datetime,importlib.util,json,os,sys,traceback
from pathlib import Path
from authority import HERE,read,sha,bindings,verify_inputs,verify_scope,runtime,check_go
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,o):p.write_bytes((json.dumps(o,indent=2,allow_nan=False)+'\n').encode())
def table(p,rows):
 with p.open('x',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def module(path):
 s=importlib.util.spec_from_file_location('g4_frozen_diagnostics',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--revision',required=True);args=ap.parse_args()
 plan=read(HERE/'PLAN.json');lock=read(HERE/'INPUT_LOCK.json');go=read(HERE/plan['go_file'])
 check_go(plan,go);verify_scope(plan,lock);verify_inputs(lock);rt=runtime(plan,lock)
 out=HERE/plan['output']
 if out.exists() or len(args.revision)!=40 or any(c not in '0123456789abcdef' for c in args.revision):raise ValueError('fresh output/immutable revision required')
 import numpy as np
 from threadpoolctl import threadpool_info
 pools=threadpool_info()
 if not pools or any(v['num_threads']!=1 for v in pools):raise ValueError('actual one-thread BLAS')
 from physics import analyze
 from model_adapter import load,evaluate
 D=module(lock['diagnostics']['path'])
 out.mkdir();(out/'FAILURES.jsonl').touch();m=dict(question_id=plan['question_id'],status='RUNNING',start_utc=stamp(),code_revision=args.revision,go_sha256=sha(HERE/plan['go_file']),bindings_sha256=bindings(plan),command=sys.argv,runtime=rt,threadpools=pools,completed_conditions=0,completed_pairs=0,source_model_initializations=0,new_RT_calls=0,new_training_runs=0,new_EKF_runs=0,G3_original_clean_execution_acceptance=False)
 put(out/'MANIFEST.json',m);current=None
 try:
  model,imports=load(lock);m['source_model_initializations']=1;m['model_imports']=imports;put(out/'MANIFEST.json',m)
  records=[];summaries=[]
  for row in lock['conditions']:
   current=row['id'];folder=out/current;folder.mkdir()
   with np.load(row['files']['RAW.npz']['path'],allow_pickle=False) as z:a=dict(z)
   physical,arrays,groups,surfaces=analyze(a,D,plan);pred=evaluate(model,row,plan)
   record=dict(condition_id=current,coordinate=row['coordinate'],xyz=row['xyz'],yaw_deg=row['yaw_deg'],yaw_index=row['yaw_index'],raw_sha256=row['files']['RAW.npz']['sha256'],physical=physical,model=pred)
   put(folder/'RESULT.json',record);np.savez_compressed(folder/'FIELDS_AND_WINDOWS.npz',**arrays);table(folder/'GROUP_REMOVAL.csv',groups);table(folder/'SURFACE_REMOVAL.csv',surfaces)
   det=physical['detector'];summary=dict(condition_id=current,coordinate=row['coordinate'],yaw_deg=row['yaw_deg'],sFull=det['full']['s'],sLoS=det['los']['s'],eMP=det['e_mp'],fixed=det['same_los_tap'],selector=det['detector_choice'],tapFull=det['full']['tap'],tapLoS=det['los']['tap'],rangeFull=det['full']['range_m'],rangeLoS=det['los']['range_m'],delta_range=det['delta_range_m'],Full_plus_power=det['full']['power'][0],Full_minus_power=det['full']['power'][1],LoS_plus_power=det['los']['power'][0],LoS_minus_power=det['los']['power'][1],h_s=pred['h_s'],Hpsi_s_per_rad=pred['Hpsi_s_per_rad'],Hpsi_s_per_deg=pred['Hpsi_s_per_deg'],derivative_status=pred['derivative_status'],model_minus_LoS=pred['h_s']-det['los']['s'])
   records.append(record);summaries.append(summary);m['completed_conditions']+=1;put(out/'MANIFEST.json',m);print('G4_CONDITION',current,pred['derivative_status'],flush=True)
  pairs=[]
  numeric=['sFull','sLoS','eMP','fixed','selector','tapFull','tapLoS','rangeFull','rangeLoS','delta_range','Full_plus_power','Full_minus_power','LoS_plus_power','LoS_minus_power','h_s','Hpsi_s_per_rad','Hpsi_s_per_deg']
  for coordinate in plan['coordinates']:
   subset=[r for r in summaries if r['coordinate']==coordinate['id']]
   if len(subset)!=4:raise ValueError('coordinate completeness')
   for spec in plan['pairwise_contrasts']:
    first,second=subset[spec['first']],subset[spec['second']];p=dict(coordinate=coordinate['id'],first_id=first['condition_id'],second_id=second['condition_id'],first_yaw_deg=first['yaw_deg'],second_yaw_deg=second['yaw_deg'],delta_convention='second-minus-first')
    p.update({'delta_'+k:second[k]-first[k] for k in numeric});p['decomposition_residual']=abs(p['delta_sFull']-p['delta_sLoS']-p['delta_fixed']-p['delta_selector'])
    if p['decomposition_residual']>plan['decomposition_abs_tol']:raise ValueError('pairwise identity')
    pairs.append(p)
  if len(records)!=24 or len(pairs)!=36:raise ValueError('output completeness')
  table(out/'CONDITIONS.csv',summaries);table(out/'YAW_PAIRS.csv',pairs);put(out/'CONDITIONS.json',records);put(out/'YAW_PAIRS.json',pairs)
  put(out/'READ_ONLY_CONTROLS.json',dict(scope='Original actual-yaw source bindings only; not among24 or36; no RT or earlier result rerun',controls=lock['actual_yaw_read_only']))
  m.update(status='G4_ANALYSIS_PASS_PENDING_INDEPENDENT_AUDIT',completed_pairs=len(pairs),smooth_conditions=sum(r['derivative_status']=='VERIFIED_SMOOTH' for r in summaries),undefined_branch_conditions=sum(r['derivative_status']=='UNDEFINED_BRANCH_CHANGE' for r in summaries))
 except BaseException as e:
  m.update(status='STOP_ERROR',failed_condition=current,error=repr(e))
  with (out/'FAILURES.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(dict(condition=current,error=repr(e),traceback=traceback.format_exc()))+'\n')
  raise
 finally:
  m['end_utc']=stamp();put(out/'MANIFEST.json',m)
  index={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='ARTIFACT_HASHES.json'};put(out/'ARTIFACT_HASHES.json',index)
 print('G4_RESULT',json.dumps(m,allow_nan=False),flush=True)
if __name__=='__main__':main()
