#!/usr/bin/env python3
"""DLP-R1B PREC-V2: emulate EXACT Sionna RT v2.0.1 LoS path-length operations.
This is a Source-geometry-only numerical adapter, NOT empirical RF calibration.
Sionna field_calculator.py v2.0.1 uses:
  ki_world = mi.Vector3f(vertex - prev_vertex)
  path_length = dr.norm(ki_world)
  tau = path_length*dr.rcp(speed_of_light)
For a direct path, vertex=target, prev_vertex=source.
Original SourceFFD h,H and old HOLD receipts remain immutable.
"""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import mitsuba as mi
mi.set_variant("llvm_ad_mono_polarized")
import drjit as dr
from scipy.constants import speed_of_light

N=257
IDS=(0,150,221,440,458,476,696,916)
LIMITS=dict(complex_max=5e-4,complex_rms=1e-4,s_max=2e-5,s_rms=2e-6)
def sha(p):
    d=hashlib.sha256()
    with Path(p).open("rb") as file:
        for b in iter(lambda:file.read(1<<20),b""):d.update(b)
    return d.hexdigest()
def source_only_native_float_delay(xyz,anchor):
    # Strict source-only path: no original Native tau, coefficients or residual.
    src=mi.Point3f(*[float(x) for x in anchor])
    tgt=mi.Point3f(*[float(x) for x in xyz])
    ki_world=mi.Vector3f(tgt-src)
    path_length=dr.norm(ki_world)
    tau=path_length*dr.rcp(speed_of_light)
    return float(np.asarray(tau).reshape(-1)[0])
def render(h,f,xyz,anchor):
    original_delay=np.linalg.norm(np.asarray(xyz,float)-np.asarray(anchor,float))/speed_of_light
    solver_delay=source_only_native_float_delay(xyz,anchor)
    return h*np.exp(-2j*np.pi*f[:,None]*(solver_delay-original_delay))
def observe(h):
    w=.5-.5*np.cos(2*np.pi*np.arange(N)/(N-1))
    cir=np.fft.ifft(h*w[:,None],n=4*N,axis=0)*N
    m=np.abs(cir)
    p=int(np.argmax(m.max(axis=0)))
    ix=int(np.flatnonzero(m[:,p]>=.3*m[:,p].max())[0])
    powers=np.abs(cir[ix])**2
    return (ix,p,float((powers[0]-powers[1])/powers.sum()))
def audit(raw_dir,poses):
    records=[]
    for k in poses:
        f=raw_dir/("pose_%04d.npz"%k)
        meta=json.loads((raw_dir/("pose_%04d.json"%k)).read_text())
        assert sha(f)==meta["raw_sha256"] and meta["pose_id"]==k
        with np.load(f,allow_pickle=False) as d:
            freq=d["freq_hz"];native=d["H_los"][:,:,0];h=d["source_physical_h"]
            assert h.shape==native.shape==(N,2)
            assert np.array_equal(freq,6250400000.+1950000.*np.arange(N))
            xyz=d["xyz_m"];anchor=d["anchor_xyz_m"]
            tau_source=source_only_native_float_delay(xyz,anchor)
            matched=render(h,freq,xyz,anchor)
            den=np.linalg.norm(native)
            z=observe(native);r=observe(matched)
            t=d["los_tau_s"]
            records.append(dict(pose_id=k,raw_sha256=meta["raw_sha256"],
                original_complex=float(np.linalg.norm(native-h)/den),
                fixed_complex=float(np.linalg.norm(native-matched)/den),
                s_abs=abs(z[2]-r[2]),tap_mismatch=int(z[0]!=r[0]),
                port_mismatch=int(z[1]!=r[1]),
                native_tau_equals_source_drjit_tau_on_all_bins_DIAGNOSTIC=bool(np.all(t==tau_source)),
                native_tau_minus_predicted_max_fs_DIAGNOSTIC=float(np.max(np.abs(t-tau_source))*1e15)))
    o=np.array([r["original_complex"] for r in records])
    a=np.array([r["fixed_complex"] for r in records])
    s=np.array([r["s_abs"] for r in records])
    results=dict(original_rms=float(np.sqrt(np.mean(o**2))),
       bridge_rms=float(np.sqrt(np.mean(a**2))),bridge_max=float(a.max()),
       s_max=float(s.max()),s_rms=float(np.sqrt(np.mean(s**2))),
       tap_mismatches=sum(r["tap_mismatch"] for r in records),
       port_mismatches=sum(r["port_mismatch"] for r in records),
       exact_native_tau_matches=sum(r["native_tau_equals_source_drjit_tau_on_all_bins_DIAGNOSTIC"] for r in records))
    checks=dict(complex_max=results["bridge_max"]<=LIMITS["complex_max"],
      complex_rms=results["bridge_rms"]<=LIMITS["complex_rms"],
      s_max=results["s_max"]<=LIMITS["s_max"],
      s_rms=results["s_rms"]<=LIMITS["s_rms"],
      tap=results["tap_mismatches"]==0,
      port=results["port_mismatches"]==0)
    return dict(schema="DLP_R1B_PREC_V2_SOURCE_CODE_MATCHED_DELAY_QA",
      verdict="NUMERIC_PARITY_PASS" if all(checks.values()) else "HOLD_NUMERIC_PARITY",
      original_science_status="HOLD_RF_PARITY",
      science_signoff=False,no_sionna_PathSolver_calls=True,
      ffd_source_h_H_unchanged=True,fitted_phase_gain_or_delay=0,
      precision_operation_source="NVlabs/sionna-rt/v2.0.1/src/sionna/rt/path_solvers/field_calculator.py",
      thresholds_unchanged=LIMITS,pose_ids=list(poses),
      counts=results,checks=checks,records=records)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--raw-dir",type=Path,required=True)
    p.add_argument("--poses",type=int,nargs="+",default=IDS)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    assert len(set(args.poses))==len(args.poses)
    if args.out.exists():raise FileExistsError(args.out)
    out=audit(args.raw_dir,args.poses)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    print(json.dumps(dict(verdict=out["verdict"],counts=out["counts"],checks=out["checks"])),flush=True)
    raise SystemExit(0 if out["verdict"]=="NUMERIC_PARITY_PASS" else 2)
