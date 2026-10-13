"""Frozen M0 parity and common inputs; no baseline edits."""
import sys,json,csv,hashlib,time,subprocess
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parents[1];sys.path.insert(0,str(D))
from d6_d9_common import check_inputs,spectrum,original_lut,rf_case,corrected_ranges,P3_MODEL,case_motion,file_sha
from run_d5_regimes import run_one,timelines
CONTRACT=json.loads((Path(__file__).parent/'experiment_contract.json').read_text())
def dump(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False))
def main():
 out=Path(sys.argv[1]);out.mkdir(exist_ok=False);start=time.time()
 p0=check_inputs();freq=spectrum(p0);lut=original_lut(p0);frozen=json.loads(P3_MODEL.read_text());tl=timelines(p0)
 archive=D/'results/AUDITED_RUN_20261013_701b8d2/D5_MULTI_SEED_FULL_ROUTE_METRICS.csv'
 old=list(csv.DictReader(archive.open()));keys=['case','channel','condition','level','seed','range_model','arm'];by={tuple(x[k] for k in keys):x for x in old};rows=[];maximum=0.;count=0
 for case in p0['cases']:
  t,truth,pids=tl[case['route']]
  for ch in CONTRACT['channels']:
   det=rf_case(p0,case,ch,freq,pids);ranges=corrected_ranges(det,frozen['loro_fold_params'][case['route']],allow_e1_on_los=False,channel=ch)
   cache=dict(t=t,truth=truth,pose_ids=pids,s=det['s'],range_raw=det['range_raw_m'])
   for route,params in frozen['loro_fold_params'].items():
    if ch=='full':cache['E1_outer_'+route]=corrected_ranges(det,params,allow_e1_on_los=False,channel=ch)['E1_FULL_LORO']
   for rm in CONTRACT['range_models']:
    if rm not in ranges:continue
    cache[rm]=ranges[rm]
    for condition in CONTRACT['conditions']:
     for level in CONTRACT['levels']:
      for seed in CONTRACT['seeds']:
       _,current=run_one(case,ch,level,condition,seed,t,truth,pids,det,rm,ranges[rm],lut)
       for row in current:
        key=tuple(str(row[k]) for k in keys);ref=by[key]
        for m in ['heading_rmse_deg','xy_rmse_m','mean_pose_NEES','mean_heading_NEES','pose95']:
         delta=abs(float(row[m])-float(ref[m]));maximum=max(maximum,delta)
         if delta>CONTRACT['parity_abs_tolerance']:raise RuntimeError(('M0_PARITY',key,m,delta))
        for m in ['n','accepted_updates','rejected_updates']:
         if int(row[m])!=int(ref[m]):raise RuntimeError(('M0_COUNTS',key,m))
        count+=1
       rows+=current
   np.savez_compressed(out/(case['id']+'_'+ch+'.npz'),**cache)
   print(case['id'],ch,'matched',count,flush=True)
 with (out/'M0_METRICS.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
 dump(out/'CASES.json',p0['cases'])
 dump(out/'M0_PARITY.json',dict(status='PASS',compared=count,expected=504,max_abs_difference=maximum,tolerance=1e-8,reference_sha256=file_sha(archive)))
 assert count==504,count
 dump(out/'MANIFEST.json',dict(status='PASS',contract=CONTRACT,command=sys.argv,elapsed_s=time.time()-start,sha256={p.name:file_sha(p) for p in out.iterdir() if p.is_file()},scientific_PASS=False))
if __name__=='__main__':main()
