#!/usr/bin/env python3
"""Read-only C0-A: physical Full-vs-LoS first-path and fixed-tap decomposition.
No Sionna run, no new RF, no EKF replay, no oracle used by an online filter.
Run on verified Git objects. Outputs contain *noise-free* composite-channel diagnostics.
"""
import argparse,csv,hashlib,importlib.util,json,math,sys
from collections import Counter
from pathlib import Path
import numpy as np

BASE="results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
ROUTES={"R2":979,"R4":742,"R5":1415}
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def check(x,why):
    if not x:raise AssertionError(why)
def ratio(port):
    p=np.abs(port)**2
    den=p.sum(-1)
    return np.where(den>0,(p[...,0]-p[...,1])/np.maximum(den,1e-300),np.nan)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[3])
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    root=args.repo.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    lock=json.loads((root/"research/MBVAR_PRR_001_20261103/A0_R1/VERIFIED_INPUT_SUBSET.json").read_text())
    expected=lock["files"]
    obs_path=root/"src/qclean_uwb/drivesim/observation.py"
    spec=importlib.util.spec_from_file_location("source_observation_readonly",obs_path)
    O=importlib.util.module_from_spec(spec);spec.loader.exec_module(O)
    ff=root/BASE/"freqs_hz.npy"
    freq=np.load(ff,allow_pickle=False)
    check(freq.shape==(257,) and np.allclose(np.diff(freq),np.diff(freq)[0],rtol=0,atol=1e-6),"frequency grid")
    df=float(freq[1]-freq[0])
    records=[];stats={};files={}
    for route,n in ROUTES.items():
        cas=f"{route}_aB_m0"
        paths=dict(
            full=f"{BASE}/FULL_RF/H_{cas}.npy",
            los=f"{BASE}/H_LoS_{cas}.npy",
            samples=f"{BASE}/{cas}/SAMPLES.json",
            timeline=f"{BASE}/INPUTS/timeline_{route}_Tnone.csv"
        )
        for kind,rel in paths.items():
            path=root/rel
            check(path.exists(),"missing file "+rel)
            digest=sha(path)
            check(expected.get(rel)==digest,"source SHA mismatch "+rel)
            files[rel]=dict(sha256=digest,size=path.stat().st_size)
        sample=json.loads((root/paths["samples"]).read_text())
        with (root/paths["timeline"]).open(newline="",encoding="utf-8") as f:
            timeline=list(csv.DictReader(f))
        check(len(timeline)==n,"timeline population "+route)
        ids=np.array([int(r["pose_id"]) for r in timeline],dtype=int)
        check(len(np.unique(ids))==n and ids.min()>=0 and ids.max()<len(sample),"pose id and timeline")
        for r in timeline:
            s=sample[int(r["pose_id"])]
            check(all(abs(float(r[k])-float(s[k]))<7e-6 for k in ("x","y","yaw_body_deg")), "misaligned pose "+str(r["pose_id"]))
        full=np.load(root/paths["full"],mmap_mode="r",allow_pickle=False)
        los=np.load(root/paths["los"],mmap_mode="r",allow_pickle=False)
        check(full.shape==los.shape==(len(sample),257,2,2),"H shape "+route)
        check(np.issubdtype(full.dtype,np.complexfloating) and full.dtype==los.dtype,"H dtype "+route)
        route_rows=[]
        for offset in range(0,n,128):
            rows=timeline[offset:offset+128];idx=ids[offset:offset+128]
            FH=np.asarray(full[idx,:,:,:1][...,0]);LH=np.asarray(los[idx,:,:,:1][...,0])
            CF=O.cir_batch(FH);CL=O.cir_batch(LH)
            of=O.first_path_batch(CF,df);ol=O.first_path_batch(CL,df)
            batch=np.arange(len(idx))
            fixed=ratio(CF[batch,ol["index"],:])
            sF=of["s"];sL=ol["s"]
            same=fixed-sL
            detector=sF-fixed
            err=sF-sL
            check(np.isfinite(err).all() and np.isfinite(same).all() and np.isfinite(detector).all(),"nonfinite ratio")
            check(np.max(np.abs(err-same-detector))<=1e-12,"decomposition")
            for j,row in enumerate(rows):
                v=dict(case=cas,route=route,pose_id=int(row["pose_id"]),t_s=float(row["t_s"]),
                     phase=row["phase"],x=float(row["x"]),y=float(row["y"]),yaw_body_deg=float(row["yaw_body_deg"]),
                     fp_full=int(of["index"][j]),fp_los=int(ol["index"][j]),
                     delta_tap=int(of["index"][j]-ol["index"][j]),
                     s_full=float(sF[j]),s_los=float(sL[j]),
                     physical_e_mp=float(err[j]),same_los_tap_component=float(same[j]),
                     tap_selection_component=float(detector[j]),
                     range_full_m=float(of["range_m"][j]),range_los_m=float(ol["range_m"][j]),
                     delta_range_m=float(of["range_m"][j]-ol["range_m"][j]))
                route_rows.append(v)
        ep=np.array([q["physical_e_mp"] for q in route_rows]);drift=np.array([q["delta_tap"] for q in route_rows])
        extreme=np.abs(ep)>.30;shift=drift!=0
        stats[cas]=dict(n=n,source_n=len(sample),Full_mean_bias=float(ep.mean()),
                        Full_minus_LoS_rms=float(np.sqrt(np.mean(ep**2))),
                        extreme_count=int(extreme.sum()),
                        extreme_with_tap_shift=int((extreme&shift).sum()),
                        all_tap_shift_count=int(shift.sum()),
                        biggest_abs_e_mp_pose=int(route_rows[int(np.argmax(np.abs(ep)))]["pose_id"]),
                        max_fixed_tap_identity_error=float(np.max([abs(q["physical_e_mp"]-q["same_los_tap_component"]-q["tap_selection_component"]) for q in route_rows])))
        for pid in ([168,172,173,194,234,500,525] if route=="R4" else [401,465,982] if route=="R5" else []):
            hit=[q for q in route_rows if q["pose_id"]==pid]
            if hit:stats[cas].setdefault("hotspots",[]).append(hit[0])
        records.extend(route_rows)
    with (out/"C0A_AGGREGATE_TAP_DECOMPOSITION.csv").open("w",newline="",encoding="utf-8") as f:
        wr=csv.DictWriter(f,fieldnames=list(records[0]));wr.writeheader();wr.writerows(records)
    report=dict(status="C0A_COMPOSITE_ONLY",sha_ref="pinned_verified_input_subset",noise_free=True,
                lfs_banks_used=False,per_ray_paths_inferred=False,
                n_all=len(records),observation_source_sha256=sha(obs_path),frequency_sha256=sha(ff),
                files=files,metrics=stats)
    (out/"C0A_MANIFEST.json").write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("files",)},ensure_ascii=False,allow_nan=False))
if __name__=="__main__":main()
