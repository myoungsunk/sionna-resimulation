"""Synthetic finite-horizon sensitivity using the ORIGINAL FP LUT.

Persistent RF offsets are an identifiability diagnostic, NOT an admitted AR
model. No real RF fusion or causal claim is made. Gaussian posterior metrics
belong to the explicitly linearized, iid synthetic problem only.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

DIAG=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(DIAG))
from d6_d9_common import (RS,RR,arc,range_h,sinc_with_derivative,
                          atomic_json,write_csv,file_sha)
from run_d0_d4 import read_p0,original_lut
from ekf3 import archived_direct_s_model

RANK_RTOL=1e-8
DT=.2
STEPS=100
# Unit normalization/illustrative Gaussian prior, not filter hyperparameters.
SCALES=dict(x=.1,y=.1,psi=math.radians(5),bg=math.radians(.1),
            cs=math.sqrt(RS),cr=math.sqrt(RR))


def controls(pattern):
    ds=np.full(STEPS,.04)
    yaw=np.zeros(STEPS)
    if pattern=='turn': yaw[:]=.02
    elif pattern=='return':
        ds[40:60]=0.;yaw[40:60]=math.pi/20
    elif pattern!='straight': raise ValueError(pattern)
    return ds,yaw


def transition_jacobian(pose,ds,yaw,dt,n):
    sc,der=sinc_with_derivative(yaw/2)
    a=pose[2]+yaw/2
    v=np.array([math.cos(a),math.sin(a)])
    vp=np.array([-v[1],v[0]])
    F=np.eye(n)
    F[:2,2]=ds*sc*vp
    F[:2,3]=-dt*ds/2*(der*v+sc*vp)
    F[2,3]=-dt
    return F


def sensitivity(pattern,arm,latent,model,anchor,z):
    names=['x','y','psi','bg']
    if latent and arm in ('A','C'):names.append('cs')
    if latent and arm in ('B','C'):names.append('cr')
    n=len(names);Phi=np.eye(n);rows=[]
    pose=np.array([0.,-1.,0.]);ds,yaw=controls(pattern)
    for k in range(STEPS+1):
        if k:
            Phi=transition_jacobian(pose,ds[k-1],yaw[k-1],DT,n)@Phi
            pose=arc(pose,ds[k-1],yaw[k-1])
        if arm in ('A','C'):
            _,js=model(pose);h=np.zeros(n);h[:3]=js
            if 'cs' in names:h[names.index('cs')]=1
            rows.append(h@Phi/math.sqrt(RS))
        if arm in ('B','C'):
            _,jr=range_h(pose,anchor,z);h=np.zeros(n);h[:3]=jr
            if 'cr' in names:h[names.index('cr')]=1
            rows.append(h@Phi/math.sqrt(RR))
    O=np.asarray(rows,float).reshape(-1,n)
    return O,names


def summarize(O,names,fixed_initial_pose):
    ids=np.arange(3,len(names)) if fixed_initial_pose else np.arange(len(names))
    active=[names[i] for i in ids]
    scales=np.array([SCALES[name] for name in active])
    A=O[:,ids]*scales
    values=np.linalg.svd(A,compute_uv=False) if A.size else np.zeros(0)
    singular=np.zeros(len(ids));singular[:len(values)]=values
    top=float(singular[0]) if len(singular) else 0.
    rank=int(np.count_nonzero(singular>top*RANK_RTOL)) if top>0 else 0
    # Unit diagonal PRIOR is added only here, after measurement-only rank.
    information=np.eye(len(ids))+A.T@A
    posterior=np.linalg.inv(information)
    sd=np.sqrt(np.diag(posterior))
    cor=posterior/np.outer(sd,sd)
    result=dict(initial_pose='fixed_exactly' if fixed_initial_pose else 'free_with_declared_prior',
                active_states=','.join(active),n_states=len(ids),measurement_rows=len(O),
                measurement_only_rank=rank,measurement_only_smallest_singular=float(singular[-1]),
                measurement_only_largest_singular=top,
                measurement_only_condition_ratio=float(singular[-1]/top) if top else 0.,
                normalized_singular_values=singular.tolist(),
                prior_augmented_rank=int(np.linalg.matrix_rank(information)),
                posterior_covariance_normalized=posterior.tolist(),
                gaussian_posterior_prior_only=bool(not len(O)))
    for rf in ('cs','cr'):
        result['posterior_corr_bg_'+rf]=(float(cor[active.index('bg'),active.index(rf)])
                                        if rf in active else None)
    return result


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    p0=read_p0();case=next(c for c in p0['cases'] if c['id']=='R2_aA_m0')
    lut=original_lut(p0)
    model=archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),
                                 tag_height_m=case['robot_z_m'],mount_deg=case['mount_deg'])
    rows=[];details=[]
    for pattern in ('straight','turn','return'):
        for arm in ('D0','A','B','C'):
            for latent in (False,True):
                O,names=sensitivity(pattern,arm,latent,model,case['anchor'],case['robot_z_m'])
                for fixed in (False,True):
                    result=summarize(O,names,fixed)
                    base=dict(pattern=pattern,arm=arm,
                              rf_offset_diagnostic=latent,representative_case=case['id'])
                    details.append(base|result)
                    rows.append(base|{k:v for k,v in result.items()
                                      if k not in ('normalized_singular_values','posterior_covariance_normalized')})
    write_csv(out/'OBSERVABILITY.csv',rows)
    atomic_json(out/'LINEAR_GAUSSIAN_DETAILS.json',details)
    atomic_json(out/'OBSERVABILITY_RECEIPT.json',dict(status='EXECUTED_SYNTHETIC_DIAGNOSTIC',
        scientific_PASS=False,real_rf_bias_identifiability='NOT_ESTABLISHED',
        observation_model='original frozen FP s LUT; original 3D range',
        latent_dynamics='constant persistent offsets, structural diagnostic ONLY, no AR1 approval',
        linearization='noise-free SE2 synthetic paths, fixed nominal initial pose [0,-1,0]',
        controls=dict(dt_s=DT,steps=STEPS,ds_m=.04,turn_yaw_rad=.02),
        covariance_semantics='exact linear-Gaussian posterior for frozen sensitivity matrix and declared diagonal prior; no process noise; not covariance of nonlinear robust estimator',
        measurement_covariance=dict(RS=RS,RR=RR,independent_temporally=True),
        normalization_scales=SCALES,rank_relative_tolerance=RANK_RTOL,
        n_cells=len(rows),code_sha256=file_sha(Path(__file__)),
        p0_manifest_sha256=file_sha(DIAG.parent/'P0_INPUT_MANIFEST.json'),
        output_sha256={p.name:file_sha(p) for p in out.iterdir() if p.is_file()}))
    print('OBSERVABILITY_SYNTHETIC_DONE',len(rows))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    run(ap.parse_args().out)
