import r45 as a
import numpy as np,json,datetime
from pathlib import Path
a.OUT=a.ROOT/'R4_RUN_002';a.OUT.mkdir(exist_ok=False)
a.write('CONTRACT.json',dict(scope='R4 only fixed archived P center offsets, redetect all samples',radius_m=.075,offsets_cm=[-15,-7.5,-5,-2.5,0,2.5,5,7.5,15],script_sha256=a.sha(Path(__file__)),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
rows=[]
for route in ['R2','R4','R5']:
 case=route+'_B0_Full_10';on=a.data(case,'online.npz');B,S,pools,center0=a.prepare(case,on);ev=a.data(case,'evaluator.npz');ref=a.obs.first_path_batch(a.obs.cir_batch(ev['clean_H']),1950000);wrong=B!=ref['index']
 for off in [-.15,-.075,-.05,-.025,0,.025,.05,.075,.15]:
  c=center0+off;alarm=abs(B*a.STEP-c)>.075+1e-12
  for policy in ['K0','K1','K2','K3']:
   sel=np.array([a.choose(int(B[k]),c[k],pools[k],policy)[0] if alarm[k] else B[k] for k in range(len(B))])
   rows.append(dict(case=case,offset_cm=off*100,policy=policy,n=len(B),alarms=int(alarm.sum()),TP=int((alarm&wrong).sum()),FP=int((alarm&~wrong).sum()),FN=int((~alarm&wrong).sum()),exact_recovery=int((wrong&(sel==ref['index'])).sum()),normal_harm=int((~wrong&(sel!=ref['index'])).sum()),retained=int((alarm&(sel==B)).sum()),range_MAE_cm=float(np.mean(abs(sel-ref['index']))*a.STEP*100),S_MAE=float(np.mean(abs(S[np.arange(len(B)),sel]-ref['s'])))))
a.table('SENSITIVITY.csv',rows)
frozen=json.loads((a.ROOT/'R2_RUN_001/SUMMARY.json').read_text())
for p in frozen:
 rr=[r for r in rows if r['offset_cm']==0 and r['policy']==p]
 assert sum(r['exact_recovery'] for r in rr)==frozen[p]['TP_exact']
 assert sum(r['normal_harm'] for r in rr)==frozen[p]['FP_harmed']
a.write('CHECKS.json',dict(status='PASS',zero_offset_reproduces_R2=True,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
print('R4_COMPLETE',len(rows))
