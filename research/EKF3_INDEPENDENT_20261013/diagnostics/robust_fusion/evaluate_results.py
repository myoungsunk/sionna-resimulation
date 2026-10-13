"""Descriptive paired summaries; no time-sample independence claim."""
import argparse,csv,json,math,gzip
import numpy as np
from pathlib import Path
from collections import defaultdict

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--m0',type=Path,required=True);ap.add_argument('--m1',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(exist_ok=False)
 rows=[]
 for model,path in [('M0',a.m0/'M0_METRICS.csv'),('M1',a.m1/'M1_METRICS.csv')]:
  for r in csv.DictReader(path.open()):r['model']=model;rows.append(r)
 keys=['case','channel','range_model','condition','level','seed','arm'];baseline={tuple(r[k] for k in keys):r for r in rows if r['model']=='M0'};paired=[]
 names=['heading_rmse_deg','xy_rmse_m','mean_pose_NEES','mean_heading_NEES','pose95']
 for r in rows:
  if r['model']!='M1':continue
  b=baseline[tuple(r[k] for k in keys)];assert r['n']==b['n'];q={k:r[k] for k in keys}
  for m in names:q['M0_'+m]=float(b[m]);q['M1_'+m]=float(r[m]);q['delta_'+m]=float(r[m])-float(b[m])
  paired.append(q)
 assert len(paired)==len(baseline)==504
 groups=defaultdict(list)
 for r in rows:groups[tuple(r[k] for k in ['model','channel','range_model','condition','arm'])].append(r)
 pooled=[]
 for key,values in sorted(groups.items()):
  row=dict(zip(['model','channel','range_model','condition','arm'],key));n=sum(int(x['n']) for x in values);row.update(n=n,cells=len(values))
  for m in names:
   power=2 if 'rmse' in m else 1;row[m]=(sum(int(x['n'])*float(x[m])**power for x in values)/n)**(1/power)
  pooled.append(row)
 for name,table in [('PAIRED_CELLS.csv',paired),('POOLED_METRICS.csv',pooled)]:
  with (a.out/name).open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=table[0]);w.writeheader();w.writerows(table)
 trace_groups=defaultdict(lambda:defaultdict(list))
 with gzip.open(a.m1/'M1_TRACE.csv.gz','rt') as f:
  for r in csv.DictReader(f):
   q=trace_groups[tuple(r[k] for k in keys)]
   q['position'].append(math.hypot(float(r['error_x']),float(r['error_y'])))
   q['heading'].append(abs(float(r['heading_error_deg'])))
   if r['NIS']:q['nis'].append(float(r['NIS']))
   if r['huber_weight']:q['weight'].append(float(r['huber_weight']))
 diagnostics=[]
 for key,q in trace_groups.items():
  nis=np.asarray(q['nis']);w=np.asarray(q['weight'])
  diagnostics.append(dict(zip(keys,key))|dict(position_error_p95_m=float(np.quantile(q['position'],.95)),heading_error_p95_deg=float(np.quantile(q['heading'],.95)),nis_pre_gate_lag1=float(np.corrcoef(nis[:-1],nis[1:])[0,1]) if len(nis)>2 and np.std(nis)>1e-12 else None,mean_huber_weight=float(np.mean(w)) if len(w) else None,downweighted_fraction=float(np.mean(w<1)) if len(w) else None))
 with (a.out/'M1_EXTRA_DIAGNOSTICS.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=diagnostics[0]);w.writeheader();w.writerows(diagnostics)
 (a.out/'INTERPRETATION.json').write_text(json.dumps({'paired_cells':len(paired),'aggregation':'sample-count weighted descriptive RMSE, arithmetic weighted NEES/coverage; sensor seeds not newRF realizations','M2_T0':'NOT_READY_PREFLIGHT','M2_T1':'HELD_RF_STRUCTURE_INCONCLUSIVE','E1':'whole-route exploratory; excluded-site scoring alone cannot remove prior state history contamination','scientific_PASS':False},indent=2))
 for r in pooled:
  if r['channel']=='full' and r['arm']=='C':print(r)
if __name__=='__main__':main()
