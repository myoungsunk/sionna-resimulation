#!/usr/bin/env python3
"""RA5-I1 physical FFD no-RT Jacobian of [range,s_first,s_next].
Source: immutable MBVAR-INFO world.h_H_tap (tap-conditioned), NOT a new estimator.
Independent finite difference at the SAME detector tap; nonsmooth detector transitions flagged.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,os,pathlib,sys
import numpy as np

T=np.array([[1.,0.,0.],[0.,1.,0.],[0.,-1.,1.]])
def req(x,msg):
    if not x:raise RuntimeError(msg)
def sha(file):
    h=hashlib.sha256()
    with pathlib.Path(file).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def adapter(world,states,anchor,taps):
    s=np.atleast_2d(np.asarray(states,float))
    taps=np.asarray(taps,int)
    req(s.ndim==2 and s.shape[1]==4 and taps.shape==(len(s),),"ERR_ADAPTER_INPUT")
    m0,j0=world.h_H_tap(s,anchor,taps)
    m1,j1=world.h_H_tap(s,anchor,taps+1)
    req(m0.shape==(len(s),2) and j0.shape==(len(s),2,4),"ERR_JAC_LAYOUT")
    req(np.max(abs(m0[:,0]-m1[:,0]))<1e-10,"ERR_SAME_RANGE_DIFFERENT_TAP")
    value=np.column_stack([m0[:,0],m0[:,1],m1[:,1]])
    jac=np.stack([j0[:,0],j0[:,1],j1[:,1]],axis=1)
    req(jac.shape==(len(s),3,4) and np.isfinite(jac).all(),"ERR_NONFINITE_J3")
    return value,jac
def fd_jac(world,states,anchor,taps,steps):
    jac=np.zeros((len(states),3,4))
    for k in range(4):
        delta=np.zeros_like(states);delta[:,k]=steps[k]
        vplus,_=adapter(world,states+delta,anchor,taps)
        vminus,_=adapter(world,states-delta,anchor,taps)
        jac[:,:,k]=(vplus-vminus)/(2*steps[k])
    return jac
def main(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(pathlib.Path(args.mbvar_code).resolve()))
    import world
    # Chosen as source-domain validation geometries, never selected based on RMSE.
    poses=np.array([[3.0,7.,0.],[3.5,7.,0.],[5.0,7.,0.],
                    [6.0,7.5,0.],[7.0,7.5,0.],[8.0,7.5,0.]],float)
    states=np.c_[poses,np.zeros(len(poses))]
    taps=world.taps_of(states,"A")
    pure,srcjac=world.h_H(states,"A")
    obs,J=adapter(world,states,"A",taps)
    orig_diff=float(np.max(abs(obs[:,:2]-pure)))
    req(orig_diff<1e-8,"ERR_REPLAY_FFD_ORIGINAL "+str(orig_diff))
    req(np.max(abs(J[:,:2]-srcjac))<1e-6,"ERR_J0_REPLAY")
    z=obs@T.T;Jd=np.einsum("ij,njk->nik",T,J)
    directz=np.column_stack([obs[:,0],obs[:,1],obs[:,2]-obs[:,1]])
    req(np.max(abs(z-directz))<1e-14,"ERR_DS_J_TRANSFORM")
    steps=np.array([1e-4,1e-4,1e-5,1e-6])
    fd=fd_jac(world,states,"A",taps,steps)
    orig_taps=taps
    # Reselecting the detector on perturbed poses is a distinct nonsmooth model.
    smooth_mask=np.ones(len(states),bool)
    for k in range(3):
        d=np.zeros_like(states);d[:,k]=steps[k]
        smooth_mask&=(world.taps_of(states+d,"A")==orig_taps)&(world.taps_of(states-d,"A")==orig_taps)
    errs=np.max(abs(J-fd),axis=(1,2))
    rows=[]
    for i in range(len(states)):
        rows.append(dict(pose_i=i,pose_x=states[i,0],pose_y=states[i,1],yaw_rad=states[i,2],
          tap0=int(taps[i]),tap1=int(taps[i]+1),source_s0=float(obs[i,1]),
          next_s1=float(obs[i,2]),delta_s=float(obs[i,2]-obs[i,1]),
          tap_stable_fd=bool(smooth_mask[i]),jac_max_abs_fd=float(errs[i]),
          source_j0_replay=float(np.max(abs(J[i,:2]-srcjac[i]))),
          derivative_units="m,m,rad,rad/s"))
    with (out/"RA5_TAP_JACOBIAN_FD.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    good=(errs<5e-3)&smooth_mask
    qa=dict(status="PASS_TAP_JACOBIAN_SELECTED_POSES" if good.sum()>=2 else "BLOCKED_NO_STABLE_JACOBIAN_EVIDENCE",
      n_poses=len(states),n_tap_stable=int(smooth_mask.sum()),
      n_analytic_fd_matched=int(good.sum()),max_fd_err_on_stable=float(np.max(errs[smooth_mask])) if smooth_mask.any() else None,
      original_source_m0_parity=orig_diff,
      deriv_jacobian_formula="J_ds=J_s1-J_s0; tap held fixed in derivative",
      actual_observer_detector_argmax="NOT_DIFFERENTIABLE_AT_TAP_CHANGE",
      source_world_sha256=sha(pathlib.Path(args.mbvar_code)/"world.py"),
      observed_full_multipath_feature_jacobian="NOT_IMPLEMENTED",
      source_physics="FFD_LOS_ONLY",
      independent_auditor=False,science_release=False,
      timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_TAP_JACOBIAN_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_TAP_JACOBIAN_FINAL "+json.dumps(qa),flush=True)
    if qa["status"].startswith("BLOCKED"):raise RuntimeError("ERR_NO_FD_JACOBIAN_PASSES")
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--mbvar-code",required=True);ap.add_argument("--out",required=True)
    main(ap.parse_args())
