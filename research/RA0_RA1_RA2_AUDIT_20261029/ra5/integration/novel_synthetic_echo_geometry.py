#!/usr/bin/env python3
"""RA5-I4: NEW preregistered SourceFFD geometry and synthetic delayed echo (NO RT).
Mechanism/portability stress only. Echo is a 2-port coherent delay toy, not an
independently ray-traced specular path, a new physical scene, or blind test data.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,pathlib,sys
import numpy as np
from raw_tap_covariance import make_cir,extract,noise_trials

# New geometry: not a previously frozen Corridor/Office RF trajectory or S1 train window.
POSES=np.array([[2.75,4.20,-.10],[3.75,4.55,.12],[4.75,4.90,.34],
  [5.75,5.25,.56],[6.75,5.60,.78],[7.75,5.95,1.00]],dtype=float)
ANCHORS=("A","C")
DELAYS_NS=(0.,.35,1.5,3.)
GAIN=np.array([.35*np.exp(.3j),.18*np.exp(-.5j)])
def req(v,msg):
    if not v:raise RuntimeError(msg)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def dump(p,rows):
    keys=sorted(set().union(*(r.keys() for r in rows)))
    with p.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def echo(h,freq,delay_ns):
    if delay_ns==0:return np.asarray(h).copy()
    # Frequency-offset phase; carrier phase placed in the complex per-port gains.
    rot=np.exp(-2j*np.pi*(freq-freq[0])*delay_ns*1e-9)
    return h*(1+rot[:,None]*GAIN[None,:])
def main(args):
    out=pathlib.Path(args.out);out.mkdir(exist_ok=True,parents=True)
    sys.path.insert(0,str(pathlib.Path(args.mbvar_code).resolve()))
    import world
    m=world.model();freq=np.asarray(m.freqs);df=float(freq[1]-freq[0])
    states=np.c_[POSES,np.zeros(len(POSES))]
    rows=[]
    for anchor in ANCHORS:
        H,_,*_=m.spectrum(states,world.spec(anchor),True)
        req(H.shape==(len(POSES),257,2),"ERR_H_NEW_GEOMETRY")
        # No source labels, no trained correction and no output-based pose selection.
        source_s=world.h_H(states,anchor)[0][:,1]
        for pi in range(len(POSES)):
            base,base_tap,_,bvalid=extract(make_cir(H[pi]),df)
            req(bool(bvalid[0]),"ERR_INVALID_BASE_NOVEL_POSE")
            req(abs(base[0,1]-source_s[pi])<1e-10,"ERR_FFD_SOURCE_S_PARITY")
            for delay in DELAYS_NS:
                h=echo(H[pi],freq,delay)
                z,tap,port,good=extract(make_cir(h),df)
                req(bool(good[0]),"ERR_INVALID_ECHO")
                seed=int(hashlib.sha256(f"RA5-I4|{anchor}|{pi}|{delay}|20261030".encode()).hexdigest()[:15],16)
                noise=noise_trials(h,freq,5.,100.,.3,args.draw,seed)
                rows.append(dict(anchor=anchor,pose_i=pi,x=float(POSES[pi,0]),y=float(POSES[pi,1]),
                  yaw_rad=float(POSES[pi,2]),echo_delay_ns=delay,
                  echo_amp_plus=float(abs(GAIN[0])) if delay else 0.,
                  echo_amp_minus=float(abs(GAIN[1])) if delay else 0.,
                  first_tap=int(tap[0]),tap_changed_from_direct=bool(tap[0]!=base_tap[0]),
                  dr_native_vs_direct_m=float(z[0,0]-base[0,0]),
                  ds0_vs_direct=float(z[0,1]-base[0,1]),
                  ds1_vs_direct=float(z[0,2]-base[0,2]),
                  var_s0_noise=noise["var_s0"],var_ds1_noise=noise["var_ds1"],
                  cov_s0_ds1_noise=noise["cov_s0_ds1"],
                  noise_tap_switch_rate=noise["tap_flip_rate"],
                  covariance_fullrank=noise["covariance_fullrank"],
                  new_physical_scene=False,ray_traced_reflection=False,
                  source="SYNTHETIC_ECHO_SUPERPOSITION_FFD_LOS"))
        print("RA5_I4_ANCHOR "+json.dumps(dict(anchor=anchor,n=len(rows))),flush=True)
    req(len(rows)==48,"ERR_SCOPE_48")
    dump(out/"RA5_NEW_GEOMETRY_SYNTHETIC_ECHO.csv",rows)
    qa=dict(status="PASS_NEW_GEOMETRY_SYNTHETIC_STRESS_ONLY",
       n_anchors=len(ANCHORS),n_new_poses=len(POSES),n_echo_conditions=len(DELAYS_NS),
       n_configurations=len(rows),draws_per_config=args.draw,
       n_original_RT_calls=0,n_source_FFD_s_parity_fail=0,
       n_echo_detector_tap_changes=sum(r["tap_changed_from_direct"] for r in rows),
       n_noise_mixture_cells=sum(r["noise_tap_switch_rate"]>0 for r in rows),
       n_singular_joint_R=sum(not r["covariance_fullrank"] for r in rows),
       qualification="new synthetic geometry/echo stress only; NO new physical RT scene",
       source_world_sha256=sha(pathlib.Path(args.mbvar_code)/"world.py"),
       independent_auditor=False,science_release=False,
       completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_NEW_GEOMETRY_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_I4_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--mbvar-code",required=True);ap.add_argument("--out",required=True)
    ap.add_argument("--draw",type=int,default=256)
    a=ap.parse_args();req(a.draw>=128,"ERR_DRAWS");main(a)
