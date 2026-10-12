"""P5 step 2: build the matched-replay harness from the FROZEN sensor-v2 simulate.py (RUN_01a124ff) via text substitution (same pattern as the G7 replays):
 * arms: A_DR (IMU+wheel only) | B_OLD | C_CONST | C_AFFINE | D_NEW | E_COND | BEST_PLUS_R | BEST_PLUS_R_IAT  (range-only; no s)
 * identical per (case, drift, seed): physical trajectory, sensor stream, x0/P0, F/G/Q, gate, timestamps. Only the range series (additive delta vs B) and, for the two BEST_PLUS_R arms, R change.
 * prior: pose SMALL (xy 3 cm, yaw 2 deg), calibration prior as in the config (engineering diagnostic; V02 LARGE FAIL is untouched)
 * extra per-run outputs: pose-error p95, endpoint error, range-innovation lag-1 autocorrelation, accepted-range fraction, full innovation NIS.
usage: p5_build_harness.py JOB_DIR ARM_RANGE_DIR (JOB_DIR = copy of the G7 job tree)"""
import json,sys,shutil
from pathlib import Path
J=Path(sys.argv[1]);AR=Path(sys.argv[2])
src=(J/'simulate_g7.py').read_text()
def rep(a,b,cnt=1):
    global src
    assert a in src,a[:60];src=src.replace(a,b,cnt)
rep("cfg=configure(case,level,arm!='A',arm in ['C','D','E'],known);x0=np.r_[truth[0],0.,0.,0.]",
"""cfg=configure(case,level,arm!='A',False,known)
 import dataclasses as _dc,math as _m
 arms_np=np.load(Path('"""+str(AR)+"""')/f'{case}.npz')
 _p0=list(cfg.p0_std);_p0[0]=_p0[1]=0.03;_p0[2]=_m.radians(2.);cfg=_dc.replace(cfg,p0_std=tuple(_p0))
 if arm in('BEST_PLUS_R','BEST_PLUS_R_IAT'):
  _var=float(arms_np['resid_var'])*(IAT_COND if arm=='BEST_PLUS_R_IAT' else 1.0);_base=cfg.range_sigma**2+cfg.range_extra_sigma**2+cfg.range_quant_var
  cfg=_dc.replace(cfg,range_extra_sigma=_m.sqrt(max(_var-cfg.range_sigma**2-cfg.range_quant_var,0.0)))
 x0=np.r_[truth[0],0.,0.,0.]""")
rep("if arm=='C':obs['s']=obslos['s'][ids];obs['power']=obslos['power'][ids]",
"""_dkey={'B_OLD':None,'C_CONST':'delta_C_CONST','C_AFFINE':'delta_C_AFFINE','D_NEW':'delta_D_NEW','E_COND':'delta_E_COND','BEST_PLUS_R':'delta_E_COND','BEST_PLUS_R_IAT':'delta_E_COND'}.get(arm)
 if _dkey:obs['range_m']=obs['range_m']+arms_np[_dkey][ids]""")
rep("ARMS_MARK","") if False else None
# extras before return
i=src.rindex(" return row")
extra=''' try:
  _e=arr['pose_error'][mask];_ep=np.hypot(_e[:,0],_e[:,1]);row['pos_err_p95']=float(np.percentile(_ep,95)) if len(_ep) else None;row['hdg_err_p95_deg']=float(np.degrees(np.percentile(np.abs(_e[:,2]),95))) if len(_e) else None
  _last=np.where(arr['completed'])[0][-1];row['endpoint_pos_err']=float(np.hypot(*arr['pose_error'][_last,:2]));row['endpoint_hdg_err_deg']=float(np.degrees(abs(arr['pose_error'][_last,2])))
  _v=mask&np.isfinite(arr['range_S'])&(arr['range_S']>0)&(arr['range_status']=='applied');_z=(arr['range_innovation'][_v]/np.sqrt(arr['range_S'][_v]))
  row['range_innov_acf1']=float(np.corrcoef(_z[:-1],_z[1:])[0,1]) if len(_z)>5 else None;row['range_nis_mean_applied']=float(np.mean(_z**2)) if len(_z) else None;row['n_range_applied']=int(_v.sum())
  row['nees_p95']=float(np.nanpercentile(arr['nees'][mask],95)) if mask.any() else None;row['nees_max']=float(np.nanmax(arr['nees'][mask])) if mask.any() else None
 except Exception as _ex:row['extra_error']=repr(_ex)
'''
src=src[:i]+extra+src[i:]
# tasks
t0="tasks=[(c,d,s,a,'stochastic','unknown',phase) for c in cases for d in range(3) for s in range(50) for a in ['A','B','C','D']]"
rep(t0,"import os as _os;_seeds=range(5000,5032) if _os.environ.get('P5_SEEDS')=='dev' else range(5100,5228);tasks=[(c,d,s,a,'stochastic','unknown',phase) for c in cases for d in range(3) for s in _seeds for a in ARMS_P5]")
rep("def runphase(phase):","ARMS_P5=['A','B_OLD','C_CONST','C_AFFINE','D_NEW','E_COND','BEST_PLUS_R','BEST_PLUS_R_IAT']\nIAT_COND=5.8\ndef runphase(phase):")
rep("pd.DataFrame(rows).drop(columns=['parity'])","pd.DataFrame(rows).drop(columns=['parity'],errors='ignore')") if "drop(columns=['parity'])" in src else None
(J/'simulate_p5.py').write_text(src);print('built')
