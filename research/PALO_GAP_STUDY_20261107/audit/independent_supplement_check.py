import csv,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
J=lambda f:json.loads(f.read_bytes())
H=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
p=Path('D:/codex/PALO_GAP_STUDY_20261107_01')
a=p/'audit'
receipt=J(a/'REACCEPTANCE_SUPPLEMENT_RECEIPT.json')
assert H(a/'REACCEPTANCE_ALL_ARMS.csv')==receipt['sha256']
assert H(a/'reacceptance_supplement.py')==receipt['source_sha256']
def csvrows(path):return list(csv.DictReader(path.open(newline='',encoding='utf-8')))
new=csvrows(a/'REACCEPTANCE_ALL_ARMS.csv')
old=csvrows(p/'analysis/REACCEPTANCE_EVENTS.csv')
lookup={(r['path'],int(r['k'])):r for r in new}
assert len(new)==len(lookup)==14239
counts=Counter()
groups=Counter()
dmax=0.
fields=('heading_error_deg','heading_abs_deg','Ppsi','heading_nees','xy_error_m','x_error_m','y_error_m','Pxx','Pxy','Pyy','Pxy_trace','xy_nees')
def evidence(x,P,true):
 e=x[:3]-true
 h=np.arctan2(np.sin(e[2]),np.cos(e[2]))
 ep=e[:2]; C=P[:2,:2]
 return np.array([np.degrees(h),np.degrees(abs(h)),P[2,2],h*h/P[2,2],np.linalg.norm(ep),*ep,C[0,0],C[0,1],C[1,1],C.trace(),ep@np.linalg.solve(C,ep)])
for arm in J(p/'results/SUMMARY.json')['rows']:
 with np.load(p/'results/trajectories'/arm['path'],allow_pickle=False) as z:
  t,truth,X,P,xm,pm,yes=(z[k] for k in ('t','truth','X','P','prior_X','prior_P','accepted'))
  picks=np.flatnonzero(yes); gaps=np.diff(np.r_[-1,picks])-1
  for k,gap in zip(picks,gaps):
   if gap<5 or t[k]<(140 if arm['group']=='development' else 40):continue
   r=lookup.pop((arm['path'],int(k)))
   assert all(r[f]==arm[f] for f in ('group','level','name','path')) and float(r['t'])==t[k] and int(r['preceding_rejects'])==gap
   b=evidence(xm[k],pm[k],truth[k]);c=evidence(X[k],P[k],truth[k])
   for suff,vals in [('before',b),('after',c)]:
    err=np.max(np.abs(vals-[float(r[f+'_'+suff]) for f in fields]))
    assert err<1e-8,(arm['path'],k,err)
    dmax=max(dmax,err)
   flags=(b[3]<=3.841458820694124<c[3],b[-1]<=5.991464547107979<c[-1],c[2]<b[2] and c[1]>b[1],c[-2]<b[-2] and c[4]>b[4])
   for f,flag in zip(('heading_95_crossing','xy_95_crossing','heading_variance_shrinks_error_grows','xy_trace_shrinks_error_grows'),flags):
    assert r[f]==str(flag),(arm['path'],k,f)
    counts[f]+=int(flag)
   groups[arm['group']]+=1
assert not lookup and dict(groups)==receipt['counts']
lookup={(r['group'],r['level'],r['name'],r['k']):r for r in new if r['group'] in ('baseline','rf','development')}
assert len(old)==len(lookup)==608
pairs=(('prior_heading_abs_deg','heading_abs_deg_before'),('posterior_heading_abs_deg','heading_abs_deg_after'),('Ppsi_before','Ppsi_before'),('Ppsi_after','Ppsi_after'),('heading_nees_before','heading_nees_before'),('heading_nees_after','heading_nees_after'),('xy_nees_after','xy_nees_after'))
for r in old:
 n=lookup.pop(tuple(r[f] for f in ('group','level','name','k')))
 assert all(abs(float(r[f])-float(n[g]))<1e-9 for f,g in pairs)
assert not lookup
print(json.dumps(dict(supplement_rows=len(new),original_rows=len(old),counts=groups,flags=counts,max_numeric_difference=dmax,supplement_sha256=receipt['sha256'],supplement_source_sha256=receipt['source_sha256'])))
