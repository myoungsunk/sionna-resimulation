#!/usr/bin/env python3
"""Independent arithmetical reconstruction, not an independent scientific signoff.
Do not import the implementer's precision_bridge or Native solver.
"""
import argparse, hashlib, json, pathlib, numpy as np
C=299792458.0
N=257
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as fd:
        for x in iter(lambda:fd.read(1048576),b""):h.update(x)
    return h.hexdigest()
def first_path(h):
    w=.5*(1-np.cos(2*np.pi*np.arange(N)/(N-1)))
    cir=np.fft.ifft(h*w[:,None],n=4*N,axis=0)*N
    p=np.abs(cir)
    branch=int(np.argmax(p.max(axis=0)))
    tap=int(np.flatnonzero(p[:,branch]>=.3*p[:,branch].max())[0])
    e=np.abs(cir[tap])**2
    return tap,branch,float((e[0]-e[1])/e.sum())
def raw_synthesis(z,kind):
    f=z["freq_hz"];h=z["H_"+kind];a=z[kind+"_a"]
    off=z[kind+"_path_offsets"];tau=z[kind+"_tau_s"];delta=0.
    for i in range(N):
        l,r=off[i:i+2]
        calculated=np.sum(a[:,:,l:r]*np.exp(-2j*np.pi*f[i]*tau[l:r])[None,None,:],axis=2)
        delta=max(delta,float(np.max(np.abs(calculated-h[i]))))
    return delta
def evaluate(d):
    rec=[]
    for p in sorted(d.glob("pose_*.npz")):
        j=int(p.stem.split("_")[-1])
        meta=json.loads((d/("pose_%04d.json"%j)).read_text())
        assert meta["pose_id"]==j and sha(p)==meta["raw_sha256"]
        with np.load(p,allow_pickle=False) as z:
            f=z["freq_hz"]
            assert np.array_equal(f,6250400000.+1950000.*np.arange(N))
            orig=z["source_physical_h"];actual=z["H_los"][:,:,0]
            assert orig.shape==(N,2)==actual.shape
            # Independent implementation of endpoint-precision representation.
            x=np.float64(np.float32(z["xyz_m"]))
            a=np.float64(np.float32(z["anchor_xyz_m"]))
            q=np.float32(np.sqrt(np.sum((x-a)**2))/C)
            xx=np.float64(z["xyz_m"])-np.float64(z["anchor_xyz_m"])
            physical=np.sqrt(np.sum(xx**2))/C
            rendered=orig*np.exp(-2j*np.pi*f[:,None]*(float(q)-physical))
            basis=first_path(actual);check=first_path(rendered)
            rel=np.linalg.norm(actual)
            rec.append(dict(pose_id=j,
                original_relative=float(np.linalg.norm(actual-orig)/rel),
                bridge_relative=float(np.linalg.norm(actual-rendered)/rel),
                s_abs=abs(basis[2]-check[2]),tap_mismatch=int(basis[0]!=check[0]),
                port_mismatch=int(basis[1]!=check[1]),
                H_from_raw_los_absmax=raw_synthesis(z,"los"),
                H_from_raw_full_absmax=raw_synthesis(z,"full"),
                source_model_unchanged=True,
                raw_sha256=sha(p)))
    e=np.array([r["bridge_relative"] for r in rec]);s=np.array([r["s_abs"] for r in rec])
    metrics=dict(n=len(rec),bridge_complex_rms=float(np.sqrt(np.mean(e**2))),
         bridge_complex_max=float(e.max()),bridge_s_rms=float(np.sqrt(np.mean(s**2))),
         bridge_s_max=float(s.max()),
         path_synthesis_absmax=max(max(r["H_from_raw_full_absmax"],r["H_from_raw_los_absmax"]) for r in rec),
         tap_mismatches=sum(r["tap_mismatch"] for r in rec),
         port_mismatches=sum(r["port_mismatch"] for r in rec))
    return dict(status="INDEPENDENT_ARITHMETIC_PASS" if (
         metrics["bridge_complex_rms"]<=1e-4 and metrics["bridge_complex_max"]<=5e-4
         and metrics["bridge_s_rms"]<=2e-6 and metrics["bridge_s_max"]<=2e-5
         and metrics["tap_mismatches"]==metrics["port_mismatches"]==0
         and metrics["path_synthesis_absmax"]<1e-10) else "HOLD_INDEPENDENT_ARITHMETIC",
         original_V2_science_status="HOLD_RF_PARITY",
         scientific_signoff=False,new_native_solver_calls=0,metrics=metrics,records=rec)
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw-dir",type=pathlib.Path,required=True)
    ap.add_argument("--out",type=pathlib.Path,required=True)
    args=ap.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    result=evaluate(args.raw_dir)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(dict(status=result["status"],metrics=result["metrics"])))
    raise SystemExit(0 if result["status"]=="INDEPENDENT_ARITHMETIC_PASS" else 2)
