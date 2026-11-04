"""Additive historical R2 same-start event analysis, Full or independently supplied Native."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import numpy as np
import pandas as pd
from full_input import ROOT,Inputs,materialize_full,sha,p
N0B=ROOT/'POST_S3_PROPOSER_20261104/N0B'
sys.path.insert(0,str(N0B))
from branching import iter_event_pairs,covariance_recovery,checkpoint_filter
from endpoints_n0b import measure
from summary_n0b import aggregate
from rates import tabulate

def put(path,value):
 Path(path).write_text(json.dumps(value,indent=2,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else x.tolist()))

def policy_summary(stage,bias,channel,seed,arm,tr,packet,truth,bg):
 errors=tr['x'][:,:3]-truth;errors[:,2]=np.angle(np.exp(1j*errors[:,2]));head=np.degrees(errors[:,2]);xy=np.linalg.norm(errors[:,:2],axis=1)
 rows=[]
 for name,mask in [('all',np.ones(len(head),bool)),('primary',packet['t']>=30)]:
  rows.append(dict(stage=stage,route='R2',bias=bias,channel=channel,seed=seed,arm=arm,window=name,n=int(mask.sum()),heading_rmse_deg=float(np.sqrt(np.mean(head[mask]**2))),xy_rmse_m=float(np.sqrt(np.mean(xy[mask]**2))),heading_coverage95=float(np.mean(errors[mask,2]**2/tr['P'][mask,2,2]<=3.841458820694124))))
 return rows

def evaluate_pair(pair,bias,channel,seed,truth,bg):
 ids=pair.on['sample_index'];k=pair.index;before=pair.pretreatment_prior
 dh=float(abs(np.degrees(np.angle(np.exp(1j*(before[2]-truth[k,2]))))));dx=float(np.linalg.norm(before[:2]-truth[k,:2]));accurate=bool(dh<=1 and dx<=.1)
 aa,bb=[measure(tr['t'],tr['x'],tr['P'],truth[ids],np.asarray(bg)[ids] if np.ndim(bg) else bg,accurate) for tr in (pair.on,pair.off)]
 applied=pair.disposition in ('APPLIED','ACCEPT')
 row=dict(event=f'{pair.stage}.R2.{bias}.{channel}.{seed}.{pair.arm}.{k}',stage=pair.stage,route='R2',bias=bias,channel=channel,seed=seed,arm=pair.arm,index=k,pose_id=pair.pose_id,time=pair.time,accurate=accurate,applied=applied,disposition=pair.disposition,start_hash=pair.start_hash,start_heading_deg=dh,start_xy_m=dx)
 for name,value in aa.items():
  row['on_'+name]=value;row['off_'+name]=bb[name]
  if name not in ('available_s','full_10','full_20') and value is not None and bb[name] is not None:row['delta_'+name]=float(value)-float(bb[name])
 if not aa['full_20']:row['delta_exit_observed']=np.nan
 a=row.get('delta_head_int_20',np.nan);b=row.get('delta_xy_int_20',np.nan)
 row['effect']='censored' if not aa['full_20'] else 'tie' if abs(a)<=1e-7 and abs(b)<=1e-8 else 'benefit' if a < -1e-7 and b < -1e-8 else 'harm' if a>1e-7 and b>1e-8 else 'mixed'
 if not applied and (not np.allclose(pair.on['x'],pair.off['x'],atol=1e-10,rtol=1e-10) or not np.allclose(pair.on['P'],pair.off['P'],atol=1e-10,rtol=1e-10)):raise ValueError('rejected branch divergence')
 for endpoint,a_flag,b_flag,eligible in [('recovered',np.isfinite(aa['recovery_s']),np.isfinite(bb['recovery_s']),not accurate),('exited',aa['exit_observed'],bb['exit_observed'],accurate),('reentered',np.isfinite(aa['reentry_s']),np.isfinite(bb['reentry_s']),accurate and (aa['exit_observed'] or bb['exit_observed']))]:
  for label,flag in [('on_only',a_flag and not b_flag),('off_only',b_flag and not a_flag),('both',a_flag and b_flag),('neither',not a_flag and not b_flag)]:row[label+'_'+endpoint]=bool(flag) if eligible and aa['full_20'] else None
 return row

def execute(output,input_root,channel='Full',packet_root=None):
 output=Path(output);input_root=Path(input_root)
 if output.exists():raise ValueError('preserve previous run')
 output.mkdir(parents=True);(output/'natural').mkdir();(output/'pairs').mkdir()
 code={str(path.relative_to(ROOT)).replace('\\','/'):sha(path) for folder in ('S1','S2','S3','POST_S3_PROPOSER_20261104/N0B','POST_S3_PROPOSER_20261104/R2_EXTENSION') for path in (ROOT/folder).glob('*.py')}
 manifest=dict(status='RUNNING',scope='user-authorized additive comparable R2 Full/Native N0B',channel=channel,seeds=list(range(10,30)),biases=['B0','L2'],code_sha256=code,python=sys.version,platform=platform.platform(),threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS')},utc_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,calibration_overlap='R2 Full fixed tau_DS donor, descriptive training-route reuse; same RF sensor realizations; no new environment inference')
 put(output/'MANIFEST.json',manifest);put(output/'SELF_PARITY.json',{});(output/'FAILURES.jsonl').touch()
 results=[];natural_index=[];pair_index=[];parities=[];counts=[];summaries=[];all_events=[];selfchecks={}
 try:
  if not input_root.exists():
   if channel!='Full':raise ValueError('Full controls/truth must exist before Native run')
   materialize_full(input_root)
  store=Inputs(input_root,channel,packet_root);manifest['input_lock_sha256']=sha(input_root/'INPUT_LOCK.json');manifest['channel_input_lock_sha256']=sha(store.packet_root/'INPUT_LOCK.json');put(output/'MANIFEST.json',manifest)
  for bias in ('B0','L2'):
   packet=store.packet(bias);labels=store.truth(bias);truth=labels['truth'];bg=labels['bg'];ct0=store.controls(bias,0)
   if not np.array_equal(packet['pose_id'],labels['pose_id']) or not np.array_equal(packet['t'],labels['t']):raise ValueError('R2 truth alignment')
   # Historical Full baseline parity precedes any seed10-29 natural/event replay.
   if channel=='Full':
    reference=store.reference(bias)
    controls0=store.controls(bias,0)
    mask=p.b.pb.gated_mask(packet['z'],packet['muBASE'],packet['R'],controls0['ds'],controls0['gy'],controls0['dt'],np.r_[controls0['x0'],0.],packet['P0'],p.spec,p.b.model)
    data=dict(t=packet['t'],z=packet['z'],mu=dict(MB=packet['muMB']),R=packet['R'],R0=packet['R'],ds=controls0['ds'],gy=controls0['gy'],dt=controls0['dt'],x0=np.r_[controls0['x0'],0.],P0=packet['P0'],spec=p.spec,anchor=np.asarray(p.spec['anchor'][:2]),acc=mask,fin=np.isfinite(packet['z']).all(1))
    # Stored OFF_MB is MB_ORIG. Historical producer exp_pb.py explicitly tests it with mode=orig.
    original_x,original_P,_,_=p.b.pb.run(data,packet['muMB'],dict(mode='orig'),p.b.model)
    var_x,var_P,_,_=p.b.pb.run(data,packet['muMB'],dict(mode='var'),p.b.model)
    control_x,control_P,_=p.b.ctl.run(data,'MB',p.b.ctl.R_var)
    tr=p.online.replay(packet,controls0,'W0',p.b.core,p.b.model,p.spec)
    check=dict(reference_producer='7e2855314de867e0481f8eb5ed1a07c48710f364:research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py',stored_reference_mode='MB_ORIG',max_historical_orig_state_abs=float(np.max(abs(original_x-reference['x']))),max_historical_orig_P_abs=float(np.max(abs(original_P-reference['P']))),max_state_abs=float(np.max(abs(tr['x']-var_x))),max_P_abs=float(np.max(abs(tr['P']-var_P))),max_second_reference_state_abs=float(np.max(abs(control_x-var_x))),max_second_reference_P_abs=float(np.max(abs(control_P-var_P))),mask_differences=int(np.count_nonzero(tr['mask']!=reference['mask'])))
    check['passed']=bool(np.allclose(original_x,reference['x'],atol=1e-8,rtol=1e-8) and np.allclose(original_P,reference['P'],atol=1e-8,rtol=1e-8) and np.allclose(tr['x'],var_x,atol=1e-10,rtol=1e-10) and np.allclose(tr['P'],var_P,atol=1e-10,rtol=1e-10) and np.allclose(control_x,var_x,atol=1e-10,rtol=1e-10) and np.allclose(control_P,var_P,atol=1e-10,rtol=1e-10) and np.array_equal(tr['mask'],reference['mask']))
    selfchecks[bias]=check;put(output/'SELF_PARITY.json',selfchecks)
    if not check['passed']:raise ValueError('historical Full W0 seed0 parity '+bias)
   for seed in range(10,30):
    stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if stop and Path(stop).exists():raise InterruptedError('owner stopped')
    controls=store.controls(bias,seed)
    for arm,policy in [('A','W0'),('B','W-d0-DS')]:
     tr=p.online.replay(packet,controls,policy,p.b.core,p.b.model,p.spec);tr['pose_id']=packet['pose_id'];tr['sample_index']=np.arange(len(packet['t']))
     name=f'R2_{bias}_{channel}_{seed}_{arm}.npz';np.savez_compressed(output/'natural'/name,**tr,t=packet['t'])
     natural_index.append(dict(stage='S2_S3_SHARED',bias=bias,channel=channel,seed=seed,arm=arm,file='natural/'+name,sha256=sha(output/'natural'/name)))
     for stage in ('S2','S3'):summaries.extend(policy_summary(stage,bias,channel,seed,arm,tr,packet,truth,bg))
    for stage,arms in [('S2',('C_P','D_P')),('S3',('C_CP','D_CP'))]:
     config=sha(ROOT/'S3/RULES.json')
     for arm in arms:
      if stage=='S2':tr,events=covariance_recovery.replay(packet,controls,arm,p.b.core,p.b.model,p.spec,p.online)
      else:tr,events,*_=checkpoint_filter.replay(packet,controls,arm,p.b.core,p.b.model,p.spec,config)
      tr['pose_id']=packet['pose_id'];tr['sample_index']=np.arange(len(packet['t']))
      name=f'{stage}_R2_{bias}_{channel}_{seed}_{arm}.npz';np.savez_compressed(output/'natural'/name,**tr,t=packet['t'])
      natural_index.append(dict(stage=stage,bias=bias,channel=channel,seed=seed,arm=arm,file='natural/'+name,sha256=sha(output/'natural'/name)))
      summaries.extend(policy_summary(stage,bias,channel,seed,arm,tr,packet,truth,bg))
      all_events.extend(dict(stage=stage,route='R2',bias=bias,channel=channel,seed=seed,arm=arm,**event) for event in events)
      counts.append(dict(stage=stage,route='R2',bias=bias,channel=channel,seed=seed,arm=arm,attempts=len(events),applied=sum(event.get('disposition','APPLIED') in ('APPLIED','ACCEPT') for event in events)))
      pairs=iter_event_pairs(stage,packet,controls,arm,p.b.core,p.b.model,p.spec,p.online,tr,events,config)
      seen=0
      for pair in pairs:
       row=evaluate_pair(pair,bias,channel,seed,truth,bg);results.append(row);seen+=1
       f=output/'pairs'/(row['event']+'.npz');on,off=pair.on,pair.off
       np.savez_compressed(f,t=on['t'],pose_id=on['pose_id'],sample_index=on['sample_index'],prior=pair.pretreatment_prior,on_x=on['x'],on_P=on['P'],off_x=off['x'],off_P=off['P'],mask=on['mask'],on_weight=on['weight'],off_weight=off['weight'],on_Pprior=on['Pprior'],off_Pprior=off['Pprior'],on_applied=on['recovery_applied'],off_applied=off['recovery_applied'],on_suppressed=on['recovery_suppressed'],off_suppressed=off['recovery_suppressed'])
       pair_index.append(dict(event=row['event'],file='pairs/'+f.name,sha256=sha(f)));parities.append(dict(event=row['event'],parity=pair.parity,decision=pair.decision))
      if seen!=len(events):raise ValueError('R2 event denominator mismatch')
    pd.DataFrame(results).to_csv(output/'EVENT_RESULTS.csv',index=False);pd.DataFrame(summaries).to_csv(output/'NATURAL_SUMMARY.csv',index=False);put(output/'PROGRESS.json',dict(bias=bias,seed=seed,completed_policy_cells=len(counts),event_pairs=len(results)))
    print(channel,bias,seed,'cells',len(counts),'pairs',len(results),flush=True)
  if len(counts)!=160 or len(natural_index)!=240:raise ValueError('R2 policy cell coverage')
  if results:
   table=pd.DataFrame(results);aggregate(table,output);tabulate(table,output)
  manifest.update(status='COMPLETE',natural_traces=len(natural_index),policy_cells=len(counts),pairs=len(results),utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat())
 except BaseException as error:
  manifest.update(status='FAILED',error=repr(error));(output/'FAILURES.jsonl').write_text(json.dumps(dict(error=repr(error)))+'\n');raise
 finally:
  pd.DataFrame(results).to_csv(output/'EVENT_RESULTS.csv',index=False);pd.DataFrame(summaries).to_csv(output/'NATURAL_SUMMARY.csv',index=False);pd.DataFrame(counts).to_csv(output/'POLICY_COUNTS.csv',index=False)
  put(output/'NATURAL_INDEX.json',natural_index);put(output/'PAIR_INDEX.json',pair_index);put(output/'EVENTS.json',all_events);put(output/'PARITY.json',parities);put(output/'MANIFEST.json',manifest)
 if manifest['status']=='COMPLETE':put(output/'ARTIFACT_HASHES.json',{str(path.relative_to(output)).replace('\\','/'):sha(path) for path in sorted(output.rglob('*')) if path.is_file() and path.name!='ARTIFACT_HASHES.json'})

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('output');parser.add_argument('--input-root',default=str(Path(__file__).parent/'inputs'));parser.add_argument('--channel',choices=['Full','Native_LoS'],default='Full');parser.add_argument('--packet-root');args=parser.parse_args();execute(args.output,args.input_root,args.channel,args.packet_root)
