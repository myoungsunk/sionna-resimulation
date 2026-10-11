#!/usr/bin/env python3
"""Native PathSolver residual P0 gates. Failed science parity never fabricated as PASS."""
from __future__ import annotations
import argparse,gc,json,math,time
from pathlib import Path
import numpy as np,pandas as pd
from common import ROOT,B,RUN,models,receipt,sha256
from qclean_uwb.drivesim.body_pose_channel import NativeSionnaAtPose,NativeSolverSettings,RFPoseRequest
from qclean_uwb.drivesim import observation as O,hs_lut as HL,pattern_apply as PA

def obs(H,f):
    q=O.observe(np.asarray(H)[None],f,None,None,tx=0)
    return dict(s=float(q['s'][0]),tap=int(q['index'][0]),range_m=float(q['range_m'][0]))

def compare(H1,H0,f):
    o1,o0=obs(H1,f),obs(H0,f)
    rel=float(np.linalg.norm(H1-H0)/max(np.linalg.norm(H0),1e-30))
    mag=float(np.linalg.norm(abs(H1)-abs(H0))/max(np.linalg.norm(H0),1e-30))
    return dict(complex_relative_error=rel,magnitude_relative_error=mag,s_delta=o1['s']-o0['s'],tap_delta=o1['tap']-o0['tap'],range_delta_m=o1['range_m']-o0['range_m'],exact_equivalence=bool(rel<=1e-3 and abs(o1['s']-o0['s'])<=.01 and o1['tap']==o0['tap']))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--coeff',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    lut,safe,meta=models(a.coeff);receipt(a.out,dict(experiment='P0_NATIVE_NEW_POINTS_AND_FAMILY'))
    banks=[PA.Bank(np.load(ROOT/n,allow_pickle=False)) for n in ['LP_plus45_bank.npz','LP_minus45_bank.npz']]
    mpath=ROOT/'configs/body_probe/FFD_BANK_MANIFEST.json'
    cases={c['case']:c for c in json.loads((B/'CASES.json').read_text())}
    rawdir=a.out/'new_native_H';rawdir.mkdir(exist_ok=True)
    family=[];near=[]
    # Full/LoS original pose checks, same solver settings as native baseline.
    for case in ['R2_aA_m0','R2_aA_m45','R2_aB_m0']:
        c=cases[case];engine=NativeSionnaAtPose(output_scene_dir=a.out/('scene_'+case),bank_dir=ROOT,bank_manifest=mpath,anchor_x_m=c['anchor_xyz'][0],mount_deg=c['mount_deg'])
        samples=json.loads((B/case/'SAMPLES.json').read_text());lookup={int(p['pose_id']):i for i,p in enumerate(samples)}
        hp=B/'FULL_RF'/('H_'+case+'.npy');lp=B/('H_LoS_'+case+'.npy')
        assert sha256(hp)==c['input_H_sha256'] and sha256(lp)==c['H_sha256']
        h=np.load(hp,mmap_mode='r');l=np.load(lp,mmap_mode='r')
        for pid in [0,50]:
            p=samples[lookup[pid]];req=RFPoseRequest(f'family_{case}_{pid}',0.,(p['x'],p['y'],math.radians(p['yaw_body_deg'])),float(c['mount_deg']),0,0)
            channel=engine.generate(req);channel.validate()
            np.savez_compressed(rawdir/(req.packet_id+'.npz'),freq=channel.freqs_hz,H_full=channel.H_full,H_los=channel.H_los,true_pose=np.asarray(req.true_pose_xyyaw))
            for mode,hh,prior in [('FULL',channel.H_full,h[lookup[pid]]),('LOS',channel.H_los,l[lookup[pid]])]:
                family.append(dict(case=case,pose_id=pid,mode=mode,**compare(hh,prior,channel.freqs_hz)))
            pd.DataFrame(family).to_csv(a.out/'FAMILY_PARITY.csv',index=False)
            print('FAMILY_POINT',case,pid,family[-2:],flush=True)
        del engine;gc.collect()
    # Fresh positions not among old 9 near-axis samples; LOS is max_depth0.
    tests=[(4.,0.,.031,.017,45.),(4.,45.,.031,.017,45.),(10.,0.,-.045,.026,180.),(10.,45.,-.045,.026,180.),(4.,0.,.077,-.015,0.),(10.,45.,.118,.014,90.)]
    for j,(ax,mount,ux,uy,yaw) in enumerate(tests):
        engine=NativeSionnaAtPose(output_scene_dir=a.out/('near_scene_'+str(j)),bank_dir=ROOT,bank_manifest=mpath,anchor_x_m=ax,mount_deg=mount,settings=NativeSolverSettings(max_depth=0,compute_los=True))
        req=RFPoseRequest(f'near_new_{j}',0.,(ax+ux,uy,math.radians(yaw)),mount,0,j)
        ch=engine.generate(req);base=obs(ch.H_los,ch.freqs_hz)
        anchor=[ax,0.,2.65];xy=np.array([ax+ux,uy,.45]);d=xy-np.array(anchor);d/=np.linalg.norm(d)
        directH=HL.los_h(banks,d,yaw+mount,float(np.linalg.norm(xy-np.array(anchor))))
        direct=obs(directH,ch.freqs_hz)
        old=float(HL.s_model(lut,anchor,.45,ax+ux,uy,math.radians(yaw),mount))
        new,J=safe(anchor,.45,ax+ux,uy,math.radians(yaw),mount,True)
        row=dict(index=j,anchor_x=ax,mount_deg=mount,x=ax+ux,y=uy,yaw_deg=yaw,rho_m=math.hypot(ux,uy),native_s=base['s'],direct_s=direct['s'],original_s=old,corrected_s=float(new),old_error=base['s']-old,new_error=base['s']-float(new),native_direct_s_error=base['s']-direct['s'],Jxy_norm=float(np.linalg.norm(J[:2])),pass_sample=bool(abs(base['s']-float(new))<=.01 and np.isfinite(J).all()))
        near.append(row);np.savez_compressed(rawdir/(req.packet_id+'.npz'),freq=ch.freqs_hz,H_full=ch.H_full,H_los=ch.H_los,true_pose=np.asarray(req.true_pose_xyyaw))
        pd.DataFrame(near).to_csv(a.out/'NEW_NATIVE_POLE_PARITY.csv',index=False)
        print('NATIVE_POLE_POINT',row,flush=True)
        del engine;gc.collect()
    ff=pd.DataFrame(family);nn=pd.DataFrame(near)
    result=dict(execution='COMPLETE',n_matched_legacy_native_poses=6,n_new_near_pole_native_poses=6,full_equivalence_pass=bool(ff[ff['mode']=='FULL'].exact_equivalence.all()),los_equivalence_pass=bool(ff[ff['mode']=='LOS'].exact_equivalence.all()),new_near_pole_pass=bool(nn.pass_sample.all()),max_near_s_error=float(abs(nn.new_error).max()),source_scope='Finite pose checks only; no all-12case equivalence certification',science_pass=False)
    (a.out/'STATUS.json').write_text(json.dumps(result,indent=2))
    print('P0_CLOSURE_NATIVE_RESULT',json.dumps(result),flush=True)
if __name__=='__main__':main()
