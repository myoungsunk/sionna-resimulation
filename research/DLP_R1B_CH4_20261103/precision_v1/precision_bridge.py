#!/usr/bin/env python3
"""DLP-R1B-CH4-001/PREC-V1: numeric-representation bridge, NOT RF calibration.
Existing V2 canary failures are immutable. No Native data (including tau) is
used to calculate the source prediction; Native H is read only for scoring.
Preserves continuous SourceFFD h/H for EKF, and its original QA outcome.
"""
import argparse, hashlib, json, datetime
from pathlib import Path
import numpy as np

POSES=(0,150,221,440,458,476,696,916)
C=299792458.0
N=257
F0=6250400000.
DF=1950000.
THRESHOLDS=dict(complex_max=5e-4,complex_rms=1e-4,s_max=2e-5,s_rms=2e-6,
                tap_mismatch=0,port_mismatch=0)

def sha256(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as stream:
        for block in iter(lambda:stream.read(1<<20),b""):
            h.update(block)
    return h.hexdigest()

def solver_precision_tau(xyz,anchor):
    # Pure geometry: quantized endpoint STORAGE followed by double norm,
    # float32 delay STORAGE. This is an emulation, NOT an assertion about the
    # internal order of every DrJit kernel floating operation.
    a=np.asarray(anchor,dtype=np.float32).astype(np.float64)
    x=np.asarray(xyz,dtype=np.float32).astype(np.float64)
    return float(np.float32(np.linalg.norm(x-a)/C))

def source_render_for_rt(source_h,freq,xyz,anchor):
    tau_geo=np.linalg.norm(np.asarray(xyz,dtype=np.float64)
                           -np.asarray(anchor,dtype=np.float64))/C
    tau_native_rep=solver_precision_tau(xyz,anchor)
    # Analytic representation difference, NO fitted phase, gain, or tau.
    return source_h*np.exp(-2j*np.pi*freq[:,None]*(tau_native_rep-tau_geo))

def observe(h):
    window=.5-.5*np.cos(2*np.pi*np.arange(N)/(N-1))
    cir=np.fft.ifft(h*window[:,None],n=4*N,axis=0)*N
    mag=np.abs(cir)
    port=int(np.argmax(mag.max(axis=0)))
    ix=int(np.flatnonzero(mag[:,port]>=0.3*mag[:,port].max())[0])
    p=np.abs(cir[ix])**2
    return dict(tap=ix,port=port,s=float((p[0]-p[1])/p.sum()))

def audit(run):
    q=json.loads((run/"03_RF_CANARY_QA.json").read_text())
    assert tuple(q["canary_pose_ids"])==POSES and q["status"]=="HOLD_RF_PARITY"
    assert not q["checks"]["complex_rms"]
    records=[]
    for pose in POSES:
        f=run/("pose_%04d.npz"%pose)
        m=json.loads((run/("pose_%04d.json"%pose)).read_text())
        assert m["pose_id"]==pose and sha256(f)==m["raw_sha256"]
        with np.load(f,allow_pickle=False) as z:
            source=z["source_physical_h"]
            native=z["H_los"][:,:,0]
            xyz=z["xyz_m"]
            anchor=z["anchor_xyz_m"]
            freq=z["freq_hz"]
            assert source.shape==native.shape==(N,2)
            assert np.array_equal(freq,F0+DF*np.arange(N))
            assert np.isfinite(native).all() and np.isfinite(source).all()
            predicted=source_render_for_rt(source,freq,xyz,anchor)
            normalizer=np.linalg.norm(native)
            before=float(np.linalg.norm(native-source)/normalizer)
            after=float(np.linalg.norm(native-predicted)/normalizer)
            o=observe(native); t=observe(predicted)
            # Only AFTER predicting H, inspect Native tau as diagnostic data.
            native_tau=z["los_tau_s"]
            assert native_tau.shape==(N,)
            records.append(dict(pose_id=pose,raw_sha256=m["raw_sha256"],
                complex_original=before,complex_precision_bridge=after,
                s_abs=abs(o["s"]-t["s"]),
                tap_mismatch=int(o["tap"]!=t["tap"]),
                port_mismatch=int(o["port"]!=t["port"]),
                native_tau_minus_bridge_max_fs_DIAG=float(np.max(
                    abs(native_tau-solver_precision_tau(xyz,anchor)))*1e15),
                native_tau_float32_roundtrip_DIAG=bool(np.array_equal(
                    native_tau,native_tau.astype("f4").astype("f8")))))
    original=np.array([r["complex_original"] for r in records])
    fixed=np.array([r["complex_precision_bridge"] for r in records])
    s=np.array([r["s_abs"] for r in records])
    metrics=dict(original_complex_rms=float(np.sqrt(np.mean(original**2))),
        bridge_complex_rms=float(np.sqrt(np.mean(fixed**2))),
        bridge_complex_max=float(np.max(fixed)),
        bridge_s_max=float(np.max(s)),bridge_s_rms=float(np.sqrt(np.mean(s**2))),
        tap_mismatches=sum(r["tap_mismatch"] for r in records),
        port_mismatches=sum(r["port_mismatch"] for r in records))
    assert abs(metrics["original_complex_rms"]-q["metrics"]["complex_rms"])<1e-12
    checks=dict(original_holds=metrics["original_complex_rms"]>THRESHOLDS["complex_rms"],
       bridge_complex_max=metrics["bridge_complex_max"]<=THRESHOLDS["complex_max"],
       bridge_complex_rms=metrics["bridge_complex_rms"]<=THRESHOLDS["complex_rms"],
       bridge_s_max=metrics["bridge_s_max"]<=THRESHOLDS["s_max"],
       bridge_s_rms=metrics["bridge_s_rms"]<=THRESHOLDS["s_rms"],
       tap=metrics["tap_mismatches"]==0,port=metrics["port_mismatches"]==0)
    return dict(schema="DLP_R1B_PRECISION_BRIDGE_V1_OFFLINE_RECHECK",
      created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      status="NUMERIC_BRIDGE_REPLAY_PASS" if all(checks.values()) else "NUMERIC_BRIDGE_REPLAY_FAIL",
      original_V2_science_status="HOLD_RF_PARITY",
      independent_native_holdout_status="NOT_RUN",
      source_ekf_h_H_untouched=True,source_physically_measured_tau_used_in_prediction=False,
      future_production_RF_authorized=False,new_native_rt_calls=0,fitted_parameters=0,
      frozen_tolerances_unchanged=True,thresholds=THRESHOLDS,
      interpretive_limit="Reuse of the original 8 canary poses is NOT a prospective held-out RT validation; require fresh solver result and independent auditor sign-off to replace science HOLD.",
      precision_rule="float32 input endpoints; float64 Euclidean norm; float32 delay for phase; no input from native tau",
      metrics=metrics,checks=checks,records=records)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(str(a.out))
    result=audit(a.run)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(dict(status=result["status"],metrics=result["metrics"],checks=result["checks"])))
    raise SystemExit(0 if result["status"]=="NUMERIC_BRIDGE_REPLAY_PASS" else 2)
