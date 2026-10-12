"""P5 step 1: per-pose range corrections (delta = r_arm - r_B, in metres) for every case, using LEAVE-ONE-ROUTE-OUT fold parameters from the P3 file (the arm for a case of route X uses
coefficients fitted on the other two routes; nothing is evaluated on its own training route). Also the training-fold residual variance of the E1 arm (for the separate BEST_PLUS_R arm).
usage: p5_arm_ranges.py OUT_DIR FROZEN.json --h-full-dirs .. --freqs F"""
import argparse,json,sys
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import p3_common as P
ap=argparse.ArgumentParser();ap.add_argument('out');ap.add_argument('frozen');ap.add_argument('--h-full-dirs',nargs='+',required=True);ap.add_argument('--freqs',required=True);a=ap.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=False);fz=json.load(open(a.frozen));freq=np.load(a.freqs);tm=P.tap_m(freq)
G7=P.ROOT/'research/V01B_CLOSURE_20261012/G7/out';l=pd.read_csv(G7/'02_LABELS_EVAL_ONLY_12.csv',usecols=['case','route','pose_id','true_distance_m']);find=lambda n:next(p for dd in a.h_full_dirs for p in [Path(dd)/n] if p.exists())
# training-fold residual variance of the E1 arm (training rows, labels allowed in training)
cache={}
def det_for(case):
    if case not in cache:
        H=np.load(find(f'H_{case}.npy'),mmap_mode='r');st,_=P.cir_mag(np.asarray(H));cache[case]=P.detect(st,tm)
    return cache[case]
resid={}
for held in ('R2','R4','R5'):
    fp=fz['loro_fold_params'][held];e=[]
    for case in sorted(l.case.unique()):
        if case[:2]==held:continue
        det=det_for(case);m=int(case.split('_m')[1]);q=l[l.case==case].sort_values('pose_id');ids=q.pose_id.to_numpy()
        X=P.e1_features({k:v[ids] for k,v in det.items()},np.full(len(ids),m),tm);rb=det['r_b'][ids]-P.B_OLD;e.append(rb-P.ridge_pred(fp['E1'],X)-q.true_distance_m.to_numpy())
    resid[held]=float(np.var(np.concatenate(e)))
summary={'train_fold_E1_residual_var_m2':resid,'cases':{}}
for case in sorted(l.case.unique()):
    held=case[:2];fp=fz['loro_fold_params'][held];det=det_for(case);m=int(case.split('_m')[1]);n=len(det['r_b']);rb=det['r_b']-P.B_OLD
    X=P.e1_features(det,np.full(n,m),tm);detD=dict(det);detD['r_b']=det['r_d1']-fp['D1_offset']
    arms=dict(B_OLD=rb,C_CONST=det['r_b']-fp['C_const'],C_AFFINE=(det['r_b']-fp['C2'][0])/fp['C2'][1],D_NEW=det['r_d1']-fp['D1_offset'],E_COND=rb-P.ridge_pred(fp['E1'],X))
    np.savez(out/f'{case}.npz',**{f'delta_{k}':(v-rb) for k,v in arms.items()},resid_var=resid[held])
    summary['cases'][case]={k:dict(mean_delta=float((v-rb).mean()),sd_delta=float((v-rb).std())) for k,v in arms.items()}
(out/'P5_ARM_RANGE_SUMMARY.json').write_text(json.dumps(summary,indent=1));print(json.dumps(summary['train_fold_E1_residual_var_m2']))
