#!/usr/bin/env python3
"""Stage A V03 ONLY: six preregistered fresh Native LOS points, fixed pole-safe model.
No full-multipath run, no Stage B, no threshold fitting from these points.
"""
from __future__ import annotations
import argparse,csv,json,math,sys,traceback
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'research/P1_CAUSAL_20261011')]
from common import models,receipt
from qclean_uwb.drivesim.body_pose_channel import NativeSionnaAtPose,NativeSolverSettings,RFPoseRequest
from qclean_uwb.drivesim import observation as O,hs_lut as HL
POINTS=[(4.,0.,.031,.017,45.),(4.,45.,.031,.017,45.),(10.,0.,-.045,.026,180.),(10.,45.,-.045,.026,180.),(4.,0.,.077,-.015,0.),(10.,45.,.118,.014,90.)]

def dump_csv(p,rows):
 if not rows:return
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--coeff',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 lut,safe,_=models(a.coeff);receipt(a.out,dict(stage='A',gate='V03_FRESH_NATIVE',threshold_abs_s=.01,stage_B_allowed=False))
 rows=[];errors=[];engines={}
 for i,(ax,mount,dx,dy,yaw) in enumerate(POINTS):
  try:
   key=(ax,mount)
   if key not in engines:
    engine=NativeSionnaAtPose(output_scene_dir=a.out/f'scene_{ax}_{mount}',bank_dir=ROOT,bank_manifest=ROOT/'configs/body_probe/FFD_BANK_MANIFEST.json',anchor_x_m=ax,mount_deg=mount,settings=NativeSolverSettings(max_depth=0,compute_los=False))
    engine.full_cfg=dict(engine.los_cfg) # Explicitly LOS only; H_full container slot is labeled LOS below.
    engine.provenance['source_id']='NATIVE_SIONNA_FRESH_LOS_ONLY_P0_V03';engine.provenance['full_solver']=dict(engine.full_cfg)
    engines[key]=engine
   engine=engines[key];x=ax+dx;y=dy;psi=math.radians(yaw);anchor=(ax,0.,2.65)
   req=RFPoseRequest(f'V03_fresh_{i}',0.,(x,y,psi),mount,0,i);ch=engine.generate(req)
   ob=O.observe(ch.H_full[None],ch.freqs_hz,None,None,tx=0);native=float(ob['s'][0])
   old=float(HL.s_model(lut,anchor,.45,x,y,psi,mount));new,J=safe(anchor,.45,x,y,psi,mount,True)
   fd=[]
   for d in range(3):
    minus=np.array([x,y,psi]);plus=minus.copy();minus[d]-=1e-5;plus[d]+=1e-5
    fd.append((float(safe(anchor,.45,*plus,mount))-float(safe(anchor,.45,*minus,mount)))/2e-5)
   derivative_error=float(np.max(abs(np.asarray(J)-fd)))
   rows.append(dict(index=i,anchor_x=ax,mount_deg=mount,x=x,y=y,yaw_deg=yaw,rho_m=math.hypot(dx,dy),native_los_s=native,original_lut_s=old,corrected_s=float(new),original_error=native-old,corrected_error=native-float(new),J_x=float(J[0]),J_y=float(J[1]),J_psi=float(J[2]),model_analytic_vs_fd_maxerror=derivative_error,value_PASS=bool(abs(native-float(new))<=.01),derivative_PASS=bool(derivative_error<=1e-5)))
   np.savez_compressed(a.out/f'FRESH_NATIVE_LOS_{i}.npz',H_los=ch.H_full,freqs_hz=ch.freqs_hz,physical_pose=np.array([x,y,psi]),mount=mount,anchor=np.array(anchor))
   dump_csv(a.out/'FRESH_NATIVE_POLE_VALUES_AND_JACOBIANS.csv',rows)
   print('FRESH_NATIVE_V03',rows[-1],flush=True)
  except Exception as ex:
   errors.append(dict(index=i,error=str(ex),traceback=traceback.format_exc()));print('V03_FRESH_FAILURE',errors[-1],flush=True)
 state=dict(execution='COMPLETE' if not errors else 'COMPLETED_WITH_ERRORS',n_planned=6,n_completed=len(rows),fresh_native_value_PASS=bool(len(rows)==6 and all(r['value_PASS'] for r in rows)),model_derivative_PASS=bool(len(rows)==6 and all(r['derivative_PASS'] for r in rows)),new_native_max_abs_s_error=max([abs(r['corrected_error']) for r in rows],default=None),errors=errors,derivative_reference='Finite difference of repaired MODEL; physical native s independently checked at centers only',scope='Six preregistered new near-pole native LOS points; earlier original9519/directFFD1120/global boundary tests retained',stage_B_allowed=False,scientific_PASS=False)
 (a.out/'STATUS.json').write_text(json.dumps(state,indent=2));(a.out/'EXECUTED_SOURCE.py').write_bytes(Path(__file__).read_bytes());print('V03_FRESH_NATIVE_RESULT',json.dumps(state),flush=True)
if __name__=='__main__':main()
