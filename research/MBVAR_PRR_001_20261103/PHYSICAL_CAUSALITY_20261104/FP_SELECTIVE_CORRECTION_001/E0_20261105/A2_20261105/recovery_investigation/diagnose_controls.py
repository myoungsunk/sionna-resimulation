"""Control materialization diagnostic only: no observation/model/filter execution."""
from pathlib import Path
import hashlib, json, math, sys
import numpy as np

ROOT=Path('/workspace/scratch/dd87dad66e0c/repo')
sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim.sensor_v2 import SensorV2Config, generate, motion_increments, rng, wheel_transform, wrap
STUDY=ROOT/'research/MBVAR_PRR_001_20261103'
TRUTH=STUDY/'PHYSICAL_CAUSALITY_20261104/C1/C1A_001/FROZEN_PACKETS/evaluator_truth'
LOCK=json.loads((STUDY/'A0_R3_REFIT/BASE_INPUTS.json').read_text())['controls']
def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def controls(ds,da,t, mode):
    cfg=SensorV2Config(level=1, condition='noise_pair',common_scale=0.,bias_rw_rad_s_sqrt_s=0.)
    if mode=='original':return generate(t,ds,da,cfg,10)[0]['ds_odom']
    b=cfg.wheelbase_nominal_m
    wt=np.column_stack([ds-b*da/2,ds+b*da/2])
    qd=cfg.k_distance_m*np.abs(ds);qt=cfg.k_yaw_rad*np.abs(da)+cfg.k_yaw_distance_rad2_m*np.abs(ds)
    nd=rng(10,'wheel').standard_normal((len(t),2))*np.sqrt(np.column_stack([qd,qt]))
    inv=np.linalg.inv(wheel_transform(b))
    if mode=='unfused':offset=np.column_stack([nd[:,0]*inv[0,0]+nd[:,1]*inv[0,1],nd[:,0]*inv[1,0]+nd[:,1]*inv[1,1]])
    elif mode=='einsum':offset=np.einsum('ij,kj->ik',nd,inv,optimize=False)
    elif mode=='rowdot':offset=np.vstack([row@inv.T for row in nd])
    else:raise ValueError(mode)
    measured=wt+offset
    result=(measured[:,0]+measured[:,1])*.5
    result[0]=0.
    return result
rows=[]
for route in ('R4','R5'):
    with np.load(TRUTH/f'{route}_B0_TRUTH.npz') as z:t=z['t'];pose=z['truth']
    ds0,da=motion_increments(t,pose,convention='legacy-euler')
    mid=pose[:-1,2];dp=np.diff(pose[:,:2],axis=0)
    trig={
        'numpy_vector':(np.cos(mid),np.sin(mid)),
        'numpy_scalar':(np.array([np.cos(v) for v in mid]),np.array([np.sin(v) for v in mid])),
        'math_scalar':(np.array([math.cos(v) for v in mid]),np.array([math.sin(v) for v in mid])),
    }
    expected=LOCK[f'{route}_aB_m0_B0_10']['ds']
    standard=controls(ds0,da,t,'original')
    for tm,(co,si) in trig.items():
        ds=np.r_[0.,dp[:,0]*co+dp[:,1]*si]
        for mode in ('original','unfused','einsum','rowdot'):
            actual=controls(ds,da,t,mode)
            row=dict(route=route,trig=tm,wheel=mode,sha256=digest(actual),matches_expected=digest(actual)==expected,
                     differing_rows_vs_default=int(np.count_nonzero(actual!=standard)),maximum_abs_delta_vs_default=float(np.max(np.abs(actual-standard))))
            rows.append(row)
            if row['matches_expected']:
                out=Path('/workspace/scratch/dd87dad66e0c')/f'EXACT_{route}_ds.npy'
                np.save(out,actual)
    # Diagnose independent transition increments from both archived W0 priors.
    for bias in ('B0','L2'):
        for channel in ('Full','Native_LoS'):
            path=STUDY/'S1/runs/EVAL_001'/f'{route}_aB_m0_{bias}_{channel}_10_W0.npz'
            with np.load(path) as z: x=z['x'];prior=z['prior']
            cfg=SensorV2Config(level=1,condition='noise_pair') if bias=='B0' else SensorV2Config(level=2,condition='all',slip_mode='off')
            pars=None if bias=='B0' else dict(gyro_bias=math.radians(.2),gyro_sf=0.,wheel_asymmetry=0.,wheelbase=0.,common_scale=0.)
            gy=generate(t,ds0,da,cfg,10,parameters=pars)[0]['dtheta_gyro']
            aa=gy[1:]-x[:-1,3]*np.diff(t)
            c=np.sinc(aa/(2*np.pi));phi=x[:-1,2]+aa/2
            direction=np.column_stack([np.cos(phi),np.sin(phi)])
            recovered=np.sum((prior[1:,:2]-x[:-1,:2])*direction,axis=1)/c
            delta=recovered-standard[1:]
            rows.append(dict(route=route,bias=bias,channel=channel,kind='ARCHIVED_PRIOR_INVERSE_DIAGNOSTIC',maximum_abs_delta_vs_default=float(np.max(np.abs(delta))),q50=float(np.quantile(np.abs(delta),.5)),q99=float(np.quantile(np.abs(delta),.99))))
report=dict(python=sys.version,numpy=np.__version__,rows=rows)
out=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/workspace/scratch/dd87dad66e0c/controls_runtime_diagnostic.json')
out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
