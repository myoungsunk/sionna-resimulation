import sys,csv,json,time,hashlib,datetime
from pathlib import Path
import numpy as np
import argparse
ap=argparse.ArgumentParser(description='Pre-FP power-window diagnostic; no parameter search')
ap.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[3])
ap.add_argument('--out',type=Path,required=True)
args=ap.parse_args();R=args.out.resolve();R.mkdir(parents=True,exist_ok=False);repo=args.repo.resolve();d=repo/'research/EKF3_INDEPENDENT_20261013/diagnostics';sys.path.insert(0,str(d))
from d6_d9_common import OBS,check_inputs,checked_path,spectrum
from run_d5_regimes import timelines
from d10_d14_core import extract_cir_methods,signed_power_ratio,write_rows
# No weight/threshold fitting: primary is CO_PRE4, sum powers, inclusive FP.
config=dict(primary='CO_PRE4',anchors=['original_FP','reference_port_FP'],pre_offsets={'PRE3':[-2,-1,0],'PRE4':[-3,-2,-1,0]},post_offsets={'POST3':[0,1,2],'POST4':[0,1,2,3]},power_integration='uniform',eval_t_min=30,scientific_PASS=False)
(R/'CONFIG.json').write_text(json.dumps(config,indent=2));start=time.time();p0=check_inputs();freq=spectrum(p0);routes=timelines(p0);records={};online=[];maxparity=0
for case in p0['cases']:
 t,truth,pids=routes[case['route']];samples=json.loads(checked_path(p0,case['samples_path']).read_text('utf8'));pos={int(x['pose_id']):i for i,x in enumerate(samples)}
 for channel in ('los','full'):
  H=np.load(checked_path(p0,case[channel+'_path']),mmap_mode='r',allow_pickle=False);idx=np.flatnonzero(t>=30)
  for begin in range(0,len(idx),64):
   ids=idx[begin:begin+64];h=np.asarray(H[[pos[int(pids[i])] for i in ids]],complex);cir=OBS.cir_batch(h[...,0]);fp=OBS.first_path_batch(cir,float(freq[1]-freq[0]))
   for j,i in enumerate(ids):
    base,extra=extract_cir_methods(cir[j],fp_index=int(fp['index'][j]));p=abs(cir[j])**2;values={}
    for anchor,k in [('FP',int(fp['index'][j])),('CO',int(extra['window_begin']))]:
     if k<3 or k+3>=len(p):raise RuntimeError('Boundary window; no silent clipping')
     values[anchor+'_SINGLE']=signed_power_ratio(p[k])
     for size in (3,4):
      values[anchor+'_PRE'+str(size)]=signed_power_ratio(p[k-size+1:k+1].sum(axis=0))
      values[anchor+'_POST'+str(size)]=signed_power_ratio(p[k:k+size].sum(axis=0))
     # Fraction of pre-window energy carried by final FP tap.
     online.append(dict(case=case['id'],channel=channel,sample_index=int(i),anchor=anchor,fp_index=k,pre4_fp_energy_fraction=float(p[k].sum()/p[k-3:k+1].sum()),**{m[len(anchor)+1:]:v for m,v in values.items() if m.startswith(anchor+'_')}))
    err=max(abs(values['FP_SINGLE']-float(fp['s'][j])),abs(values['CO_POST3']-base['W1_EARLY3']),abs(values['CO_SINGLE']-base['W0_CO_FP']));maxparity=max(maxparity,err);assert err<=1e-12
    records[case['id'],int(i),channel]=dict(route=case['route'],values=values)
 print(case['id'],'done',flush=True)
paired=[]
for (case,i,ch),a in records.items():
 if ch!='full':continue
 b=records[case,i,'los'];paired.append(dict(case=case,route=a['route'],sample_index=i,**{m:a['values'][m]-b['values'][m] for m in a['values']}))
write_rows(R/'ONLINE_FEATURES.csv',online);write_rows(R/'PAIRED_DIFFERENCES.csv',paired)
summary=[]
for group in ['ALL','R2','R4','R5']+list(dict.fromkeys(x['case'] for x in paired)):
 rows=[x for x in paired if group=='ALL' or x['route']==group or x['case']==group];row=dict(group=group,n=len(rows))
 for m in paired[0]:
  if m not in ('case','route','sample_index'):row[m+'_rms']=float(np.sqrt(np.mean([x[m]**2 for x in rows])))
 summary.append(row)
write_rows(R/'SUMMARY.csv',summary)
(R/'RECEIPT.json').write_text(json.dumps(dict(start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_s=time.time()-start,baseline_max_abs=maxparity,n_pairs=len(paired),config=config,scientific_PASS=False,sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in R.iterdir() if p.is_file()}),indent=2));print(json.dumps(summary[:4]),flush=True)
