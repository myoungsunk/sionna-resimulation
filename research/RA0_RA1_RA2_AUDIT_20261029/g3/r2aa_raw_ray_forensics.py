#!/usr/bin/env python3
"""Read-only original R2_aA 925 trace reconstruction; never silently extrapolate to other cases.
Source: exact post-A23 STORED_PATH_TRACES_R2_aA from original Snowball routes.
Output: individual strict-failing rays with independently calculated unmerged and classed delays.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,itertools,json,math,os,platform,sys
from pathlib import Path
import numpy as np
from qclean_uwb.drivesim.paths import path_residuals
from qclean_uwb.drivesim.rf_store import tag_of
from qclean_uwb.features.reflection_attribution import image_delays
C=299792458.0
STRICT=5e-14
RELAX=2e-13
TIE=1e-13
G3_MAX=5.1090357159952736e-14
PLANES={"floor":(2,0.),"ceiling":(2,2.7),"wall_y_neg":(1,-1.2),"wall_y_pos":(1,1.2),"end_x_min":(0,0.),"end_x_max":(0,20.)}
def independent_delays(tx,rx):
    tbl={(): float(np.linalg.norm(np.asarray(tx)-np.asarray(rx)))/C}
    for depth in (1,2,3):
        for seq in itertools.product(PLANES,repeat=depth):
            if any(a==b for a,b in zip(seq,seq[1:])):continue
            img=np.array(rx,float)
            for name in reversed(seq):
                axis,value=PLANES[name];img[axis]=2*value-img[axis]
            tbl[seq]=float(np.linalg.norm(np.asarray(tx)-img))/C
    return tbl
def independent_classes(tbl):
    order=sorted(tbl.items(),key=lambda e:e[1])
    out=[]
    for name,d in order:
        if out and d-out[-1][1]<=TIE:
            # retain original representative delay (minimum), not current value
            continue
        out.append((name,d))
    return out
def filehash(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--traces",type=Path,required=True)
    p.add_argument("--timeline",type=Path,required=True)
    p.add_argument("--samples",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    timeline=list(csv.DictReader(args.timeline.open()))
    rows=[]
    seen=set()
    for item in timeline:
        if item["phase"]!="drive":continue
        xy=(round(float(item["x"]),6),round(float(item["y"]),6))
        if xy in seen:continue
        seen.add(xy)
        rows.append(dict(xy=xy,tag=tag_of(*xy),timeline=item))
    if len(rows)!=925 or len({x["tag"] for x in rows})!=925:
        raise ValueError(f"BAD_TIMELINE_EXPECTED_925 {len(rows)}")
    samples=json.loads(args.samples.read_text())
    if len(samples)!=1303:raise ValueError("BAD_SAMPLES_EXPECTED_1303")
    smap={}
    for pose in samples:
        smap.setdefault(tag_of(float(pose["x"]),float(pose["y"])),[]).append(int(pose["pose_id"]))
    original_summary=[];bad_rows=[];max_merged=0.;max_raw=0.;n_unmatched=0;n_bad_receipt=0;input_pairs=[]
    tx=np.array([4.,0.,2.65])
    for station,entry in enumerate(rows):
        tag=entry["tag"]; fp=args.traces/(tag+"_trace.npz"); receipt=args.traces/(tag+"_trace_receipt.json")
        if not fp.is_file() or not receipt.is_file():raise FileNotFoundError(f"ERR_TRACE_MISSING {tag}")
        meta=json.loads(receipt.read_text())
        if meta["tag"]!=tag or meta["status"]!="OK":raise ValueError(f"ERR_RECEIPT {tag}")
        with np.load(fp,allow_pickle=False) as z:
            tau=np.asarray(z["tau"],dtype=np.float64)
            rx=np.array([float(z["x"]),float(z["y"]),0.45])
            dtype=str(z["tau"].dtype)
            status=str(z["status"])
            if status!="OK" or tau.ndim!=1 or not len(tau):raise ValueError(f"ERR_TAU {tag}")
            if not (np.isfinite(tau).all() and len(tau)==int(meta["n_paths"])):raise ValueError(f"ERR_PATH_COUNT {tag}")
            theta=np.asarray(z["ang"])
            nodes=np.asarray(z["node_bins"])
        if abs(meta["x"]-rx[0])>5e-9 or abs(meta["y"]-rx[1])>5e-9:
            raise ValueError("ERR_RECEIPT_COORDINATES")
        if max(abs(rx[0]-entry["xy"][0]),abs(rx[1]-entry["xy"][1]))>5.1e-7:
            raise ValueError(f"ERR_TIMELINE_TRACE_POSITION {tag}")
        original_res,_,_,_=path_residuals(tau,tx,rx,20.,1.2,2.7)
        independent=independent_delays(tx,rx)
        project=image_delays(tx,rx,20.,1.2,2.7)
        if set(independent)!=set(project) or max(abs(independent[k]-project[k]) for k in project)>1e-22:
            raise ValueError(f"ERR_INDEPENDENT_IMAGE_MISMATCH {tag}")
        unmerged=list(independent.items())
        merged=independent_classes(independent)
        dclasses=np.array([d for _,d in merged])
        if np.max(np.abs(original_res-np.min(np.abs(tau[:,None]-dclasses[None,:]),axis=1)))>1e-21:
            raise ValueError(f"ERR_INDEPENDENT_CLASS_MISMATCH {tag}")
        m=np.asarray([min(abs(t-d) for _,d in unmerged) for t in tau])
        strict=int(np.sum(original_res>STRICT))
        if strict!=int(meta.get("unmatched_paths",-1)):n_bad_receipt+=1
        n_unmatched+=strict;max_merged=max(max_merged,float(original_res.max()));max_raw=max(max_raw,float(m.max()))
        for ray in np.flatnonzero(original_res>STRICT):
            value=float(tau[ray])
            origseq,origdelay=min(unmerged,key=lambda q:abs(value-q[1]))
            clsseq,clsdelay=min(merged,key=lambda q:abs(value-q[1]))
            fp=float(np.float32(value))
            ulp=float(np.spacing(np.float32(value)))
            delta_m=float(original_res[ray]); delta_u=float(m[ray])
            category="TIE_CLASS_ARTIFACT" if delta_u<=STRICT else "UNMERGED_STRICT_FAIL"
            rx32=np.asarray(rx,dtype=np.float32).astype(np.float64)
            t32table=independent_delays(tx,rx32)
            d32=min(abs(value-v) for v in t32table.values())
            bad_rows.append(dict(
                case="R2_aA",station=station,tag=tag,ray_index=int(ray),n_rays=len(tau),
                pose_ids=";".join(map(str,smap.get(tag,[]))),x_trace=float(rx[0]),y_trace=float(rx[1]),
                x_timeline=float(entry["timeline"]["x"]),y_timeline=float(entry["timeline"]["y"]),
                tau_s=value,tau_source_dtype=dtype,tau_float32_roundtrip_s=fp,
                tau_float32_ulp_s=ulp,tau_vs_float32_s=abs(value-fp),
                raw_best_sequence=">".join(origseq) if origseq else "LOS",
                class_best_sequence=">".join(clsseq) if clsseq else "LOS",
                image_raw_s=float(origdelay),image_class_s=float(clsdelay),
                residual_unmerged_s=delta_u,residual_merged_s=delta_m,
                residual_float32_pose_model_s=d32,
                raw_strict_pass=delta_u<=STRICT,merged_strict_pass=False,
                norm_phase_delta_at_6_5GHz=2*math.pi*6.5e9*delta_u,
                numerical_beyond_half_tau_float32_ulp=delta_u>abs(ulp)*.5,
                category=category,
                trace_git_blob_sha256=filehash(fp),receipt_git_blob_sha256=filehash(receipt)
            ))
        original_summary.append(dict(station=station,tag=tag,n_rays=len(tau),strict_unmatched=strict,raw_strict_unmatched=int(np.sum(m>STRICT)),max_merged=float(original_res.max()),max_raw=float(m.max())))
    if len(smap)!=len(set(smap)):
        raise ValueError("INTERNAL_DUPLICATE_SMAP")
    totalbad=len(bad_rows)
    # We *must* reproduce historic G3 before treating this as historical root-cause evidence.
    gate=dict(n_stations=len(rows),strict_unmatched=n_unmatched,strict_expected=1,
              max_merged_residual_s=max_merged,max_expected_s=G3_MAX,
              trace_receipt_disagreement=n_bad_receipt,
              matched_trace_archive=bool(n_unmatched==1 and abs(max_merged-G3_MAX)<1e-19 and n_bad_receipt==0))
    status="ROOT_CAUSE_PARTIALLY_RESOLVED" if gate["matched_trace_archive"] else "BLOCKED_SOURCE_PARITY"
    if not gate["matched_trace_archive"]:
        (args.out/"BLOCKED_PROVENANCE.json").write_text(json.dumps({"gate":gate,"status":status},indent=2))
        raise SystemExit("BLOCKED_SOURCE_PARITY: original G3 cannot be reproduced on archived ray data")
    assert totalbad==1
    with (args.out/"R2_A_RAY_LEDGERS.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(bad_rows[0]));w.writeheader();w.writerows(bad_rows)
    with (args.out/"R2_A_STATION_AUDIT.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(original_summary[0]));w.writeheader();w.writerows(original_summary)
    qa=dict(status=status,source_commit=os.getenv("GITHUB_SHA","LOCAL"),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            sample_sha256=filehash(args.samples),timeline_sha256=filehash(args.timeline),gate=gate,bad_rays=bad_rows,
            classification_counts={x:sum(b["category"]==x for b in bad_rows) for x in set(b["category"] for b in bad_rows)},
            affected_pose_ids=sorted(set(i for b in bad_rows for i in map(int,b["pose_ids"].split(";")))),
            downstream_cases=["R2_aA_m0","R2_aA_m45"],independent_audit="SELF_REVIEW_ONLY",
            boundary="Does not establish any R2_aB/R4/R5 original tau physical root cause; do not infer H correction from G3 strict fail.")
    (args.out/"R2_A_RAY_AUDIT.json").write_text(json.dumps(qa,indent=2))
    print(json.dumps({"status":status,"strict_count":totalbad,"category":bad_rows[0]["category"],
                      "max_merged":max_merged,"raw_residual":bad_rows[0]["residual_unmerged_s"],
                      "bad_tag":bad_rows[0]["tag"],"poses":qa["affected_pose_ids"]},ensure_ascii=False))
if __name__=="__main__":main()
