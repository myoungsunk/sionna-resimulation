#!/usr/bin/env python3
"""Stage A V03 only. Independent raw-FFD derivative, not the model's own FD.
Frozen candidate coefficient SHA, original two LP bank SHA and six predeclared
fresh Native centers. No new calibration, no Q/R changes, no Stage B/C.
Derivative errors are scored against a preregistered 0.01 per-coordinate bound;
actual-distance derivatives are recorded separately from fixed-10m LUT definition.
"""
from pathlib import Path
import argparse,hashlib,json,math,sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'research/P1_CAUSAL_20261011')]
from common import models,COEFF_SHA
from qclean_uwb.drivesim import hs_lut as HL,observation as O,pattern_apply as PA
BANKS={'LP_plus45_bank.npz':'b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b','LP_minus45_bank.npz':'39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9'}
POINTS=[(4.,0.,.031,.017,45.),(4.,45.,.031,.017,45.),(10.,0.,-.045,.026,180.),(10.,45.,-.045,.026,180.),(4.,0.,.077,-.015,0.),(10.,45.,.118,.014,90.)]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--coeff',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 _,model,_=models(a.coeff);banks=[]
 for name,digest in BANKS.items():
  p=ROOT/name;assert sha(p)==digest,('BANK_SHA',name)
  banks.append(PA.Bank(np.load(p,allow_pickle=False)))
 def reference(anc,p,mount,actual_distance):
  d=np.array([p[0]-anc[0],p[1]-anc[1],.45-anc[2]],float);distance=np.linalg.norm(d)
  h=HL.los_h(banks,d/distance,np.degrees(p[2])+mount,float(distance) if actual_distance else 10.)
  v=O.observe(h[None],banks[0].freqs_hz,None,None,tx=0)
  return float(v['s'][0]),int(v['index'][0])
 rows=[]
 for i,(ax,mount,dx,dy,yaw) in enumerate(POINTS):
  anchor=(ax,0.,2.65);p=np.array([ax+dx,dy,np.radians(yaw)])
  value,J=model(anchor,.45,*p,mount,True)
  for actual in (False,True):
   center,tap=reference(anchor,p,mount,actual)
   for step in (1e-5,5e-6):
    fd=[];taps=[]
    for k in range(3):
     pos=p.copy();neg=p.copy();pos[k]+=step;neg[k]-=step
     plus,tp=reference(anchor,pos,mount,actual);minus,tm=reference(anchor,neg,mount,actual)
     fd.append((plus-minus)/(2*step));taps.extend([tp,tm])
    row=dict(index=i,anchor_x=ax,mount_deg=mount,x=float(p[0]),y=float(p[1]),yaw_deg=yaw,reference='ACTUAL_LINK_DISTANCE' if actual else 'FIXED10M_SAME_LUT_DEFINITION',step=step,model_s=float(value),reference_s=center,value_error=float(value-center),model_Jx=float(J[0]),model_Jy=float(J[1]),model_Jpsi=float(J[2]),directFFD_Jx=fd[0],directFFD_Jy=fd[1],directFFD_Jpsi=fd[2],max_J_abs_error=float(np.max(abs(np.array(fd)-J))),center_tap=tap,all_perturbed_taps_identical=all(t==tap for t in taps))
    row['derivative_threshold_PASS']=bool(row['max_J_abs_error']<=.01 and row['all_perturbed_taps_identical'])
    rows.append(row)
 pd.DataFrame(rows).to_csv(a.out/'DIRECT_FFD_MODEL_JACOBIAN.csv',index=False)
 same=[r for r in rows if r['reference']=='FIXED10M_SAME_LUT_DEFINITION']
 state=dict(execution='COMPLETE',n_centers=6,n_tests=len(rows),original_bank_SHA256=BANKS,coefficient_SHA256=COEFF_SHA,derivative_abs_threshold=.01,same_definition_J_PASS=all(r['derivative_threshold_PASS'] for r in same),same_definition_max_J_error=max(r['max_J_abs_error'] for r in same),reference_definition='Direct original complex FFD field contraction plus same leading-edge observer; derivative is independently differenced, not model self-FD',actual_link_reference='separately scored and not interchangeable with fixed10m model',stage_B_allowed=False,stage_C_allowed=False,scientific_PASS=False)
 (a.out/'STATUS.json').write_text(json.dumps(state,indent=2));print('DIRECT_FFD_GRADIENT_RESULT',json.dumps(state))
 (a.out/'EXECUTED_SOURCE.py').write_bytes(Path(__file__).read_bytes())
if __name__=='__main__':main()
