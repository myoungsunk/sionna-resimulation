"""Additive audit correction: all 636 arms, prior/post Heading AND XY evidence."""
import json,csv,hashlib
from pathlib import Path
import numpy as np
B=Path(__file__).resolve().parents[1];D=B/'audit'
H95=3.841458820694124;XY95=5.991464547107979
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def evidence(x,P,truth):
 e=x[:3]-truth;e[2]=wrap(e[2]);ex,ey=e[:2];a,b,d=P[0,0],P[0,1],P[1,1]
 return dict(heading_error_deg=float(np.rad2deg(e[2])),heading_abs_deg=float(np.rad2deg(abs(e[2]))),Ppsi=float(P[2,2]),heading_nees=float(e[2]**2/P[2,2]),xy_error_m=float(np.hypot(ex,ey)),x_error_m=float(ex),y_error_m=float(ey),Pxx=float(a),Pxy=float(b),Pyy=float(d),Pxy_trace=float(a+d),xy_nees=float((d*ex*ex-2*b*ex*ey+a*ey*ey)/(a*d-b*b)))
def main():
 out=D/'REACCEPTANCE_ALL_ARMS.csv';receipt=D/'REACCEPTANCE_SUPPLEMENT_RECEIPT.json'
 assert not out.exists() and not receipt.exists(),'CREATE_ONLY'
 summary=json.loads((B/'results/SUMMARY.json').read_bytes());rows=[];counts={};arms=summary['rows'];assert len(arms)==636
 for r in arms:
  with np.load(B/'results/trajectories'/r['path'],allow_pickle=False) as a:
   streak=0;start=140 if r['group']=='development' else 40
   for k,yes in enumerate(a['accepted']):
    if not yes:streak+=1;continue
    if streak>=5 and a['t'][k]>=start:
     before=evidence(a['prior_X'][k],a['prior_P'][k],a['truth'][k]);after=evidence(a['X'][k],a['P'][k],a['truth'][k])
     row=dict(group=r['group'],level=r['level'],name=r['name'],path=r['path'],k=k,t=float(a['t'][k]),preceding_rejects=streak)
     row.update({f'{key}_before':val for key,val in before.items()});row.update({f'{key}_after':val for key,val in after.items()})
     row.update(heading_95_crossing=before['heading_nees']<=H95<after['heading_nees'],xy_95_crossing=before['xy_nees']<=XY95<after['xy_nees'],heading_variance_shrinks_error_grows=after['Ppsi']<before['Ppsi'] and after['heading_abs_deg']>before['heading_abs_deg'],xy_trace_shrinks_error_grows=after['Pxy_trace']<before['Pxy_trace'] and after['xy_error_m']>before['xy_error_m'])
     rows.append(row);counts[r['group']]=counts.get(r['group'],0)+1
    streak=0
 with out.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 with (B/'analysis/REACCEPTANCE_EVENTS.csv').open(encoding='utf-8') as f:old=list(csv.DictReader(f))
 lookup={(r['group'],r['level'],r['name'],r['k']):r for r in rows}
 assert len(lookup)==len(rows)
 for r in old:
  n=lookup[r['group'],r['level'],r['name'],int(r['k'])]
  for before,after in [('prior_heading_abs_deg','heading_abs_deg_before'),('posterior_heading_abs_deg','heading_abs_deg_after'),('Ppsi_before','Ppsi_before'),('Ppsi_after','Ppsi_after'),('heading_nees_before','heading_nees_before'),('heading_nees_after','heading_nees_after'),('xy_nees_after','xy_nees_after')]:
   assert abs(float(r[before])-n[after])<1e-9
 assert len(old)==608 and sum(counts[g] for g in ('baseline','rf','development'))==608
 result=dict(status='ADDITIVE_EVIDENCE_COMPLETE_SELF_CHECK_PASS',arms=636,events=len(rows),counts=counts,original_subset_events=608,prior_results_unchanged=True,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
