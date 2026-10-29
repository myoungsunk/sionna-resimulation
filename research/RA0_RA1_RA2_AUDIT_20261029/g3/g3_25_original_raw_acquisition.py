#!/usr/bin/env python3
"""Offline read-only G3 25-ray original-source audit.
Required input: original Snowball S2, not reconstructed raytracing.
Fail-closed on missing source, 23 receipt digest mismatches, 25 ray count mismatches.
No physical model verdict or H validity is ever inferred from this script alone.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math
from pathlib import Path
import numpy as np
from qclean_uwb.drivesim.paths import path_residuals
from qclean_uwb.features.reflection_attribution import image_delays
THRESHOLD=5e-14
C0=299792458.0
def sha(f):
    h=hashlib.sha256()
    with f.open("rb") as inp:
        for b in iter(lambda:inp.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def atomic_json(p,d):
    p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--s2-parent",required=True,type=Path,help="Original Snowball job root containing results/S2/traces_R2_aB/...")
    p.add_argument("--lock",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    a.out.mkdir(exist_ok=True,parents=True)
    contract=json.loads(a.lock.read_text())
    frozen=contract["items"]
    assert len(frozen)==23 and sum(int(x["expected_n_strict_paths"]) for x in frozen)==25
    acquisition=[];unmatched=[]
    for item in frozen:
        rp=Path(item["original_relpath"])
        # relpath includes results/S2/traces_CASE/x_TAG_trace.npz
        # Accept only these deterministic layouts; report the actual path used.
        # --s2-parent may be the archive job root or the literal S2 directory.
        candidates=[a.s2_parent/rp,
                    a.s2_parent/rp.relative_to("results/S2"),
                    a.s2_parent/"S2"/rp.relative_to("results/S2")]
        raw=next((f for f in candidates if f.is_file()), candidates[0])
        receipt=raw.with_name(raw.name.replace("_trace.npz","_trace_receipt.json"))
        v=dict(case=item["case"],tag=item["tag"],raw_path=str(raw),receipt_path=str(receipt),source_root=str(a.s2_parent))
        v["raw_found"]=raw.is_file()
        v["receipt_found"]=receipt.is_file()
        v["raw_sha256"]=sha(raw) if raw.is_file() else None
        v["receipt_sha256"]=sha(receipt) if receipt.is_file() else None
        v["receipt_sha_matches_original"]=bool(v["receipt_sha256"]==item["expected_original_receipt_sha256"])
        acquisition.append(v)
        if not v["raw_found"] or not v["receipt_sha_matches_original"]:
            unmatched.append(item["case"]+"/"+item["tag"])
    # Missing bytes cannot be replaced with synthetic original-like data.
    receipt_status=("BLOCKED_ORIGINAL_SOURCE_NOT_MATERIALIZED" if unmatched else "ARCHIVE_RECEIPT_SHA_MATCH")
    atomic_json(a.out/"SOURCE_ACQUISITION_QA.json",dict(
        status=receipt_status,original_source_sha=contract["base_git_sha"],
        n_requested=len(frozen),n_raw_found=sum(x["raw_found"] for x in acquisition),
        n_receipts_matching=sum(x["receipt_sha_matches_original"] for x in acquisition),
        unavailable_or_unverified=unmatched,entries=acquisition,
        caution="Historic source per-trace raw sha was not included in the frozen original release. Matched receipts are necessary but insufficient for proof of identical original raw ray bytes."
    ))
    if unmatched:
        print(json.dumps({"status":receipt_status,"n_missing_or_unverified":len(unmatched),"locations":unmatched}))
        raise SystemExit(2)
    rays=[];total=0
    for item,chk in zip(frozen,acquisition):
        meta=json.loads(Path(chk["receipt_path"]).read_text())
        if meta.get("tag")!=item["tag"] or meta.get("status")!="OK":
            raise RuntimeError("ERR_RECEIPT_IDENTITY "+item["tag"])
        with np.load(chk["raw_path"],allow_pickle=False) as z:
            tau=np.asarray(z["tau"],np.float64)
            dtype=str(z["tau"].dtype)
            x,y=float(z["x"]),float(z["y"])
            status=str(z["status"])
            npresent=int(np.asarray(z["jones"]).shape[1])
        if status!="OK" or len(tau)!=int(meta["n_paths"]) or not np.isfinite(tau).all():
            raise RuntimeError("ERR_TRACE_PARITY "+item["tag"])
        tx=np.array([4. if item["case"].endswith("aA") else 10.,0.,2.65])
        rx=np.array([x,y,.45])
        res,_,_,_=path_residuals(tau,tx,rx,20.,1.2,2.7)
        tab=image_delays(tx,rx,20.,1.2,2.7)
        seq=list(tab.items())
        strict=np.flatnonzero(res>THRESHOLD)
        if len(strict)!=int(item["expected_n_strict_paths"]):
            raise RuntimeError(f"ERR_HISTORIC_STRICT_COUNT {item['case']}/{item['tag']} expected {item['expected_n_strict_paths']} actual {len(strict)}")
        for j in strict:
            tj=float(tau[j])
            name,val=min(seq,key=lambda kv:abs(kv[1]-tj))
            rawdiff=float(abs(tj-val))
            u=float(np.spacing(np.float32(tj)))
            actual=float(res[j])
            cls="TIE_CLASS_ARTIFACT" if rawdiff<=THRESHOLD else "UNMERGED_STRICT_EXCESS_SOURCE_UNKNOWN"
            rays.append(dict(case=item["case"],tag=item["tag"],path_index=int(j),tau_s=tj,tau_dtype=dtype,
                n_trace_paths=len(tau),n_jones_paths=npresent,
                image_sequence=">".join(name) if name else "LOS",image_tau_s=float(val),
                merged_residual_s=actual,unmerged_residual_s=rawdiff,
                float32_ulp_s=u,half_ulp_s=u/2,float32_roundtrip_diff_s=abs(tj-float(np.float32(tj))),
                x_trace=x,y_trace=y,x_receipt=float(meta["x"]),y_receipt=float(meta["y"]),
                sha_of_raw_npz=chk["raw_sha256"],sha_of_original_receipt=chk["receipt_sha256"],
                category=cls,source_note="Historical original raw SHA not archived; verify H synthesis to original SHA before physical impact decision"))
            total+=1
    if len(rays)!=25:raise RuntimeError("ERR_TOTAL_EXPECTED_25")
    cols=list(rays[0])
    with (a.out/"G3_25_RAY_CLASSIFICATION.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rays)
    atomic_json(a.out/"G3_25_RAY_QA.json",dict(
        status="RAW_SOURCE_TECHNICAL_CLASSIFICATION_NOT_PHYSICAL_ACCEPTANCE",
        count=25,merged_strict_excess=25,
        tie_merge_artifacts=sum(x["category"]=="TIE_CLASS_ARTIFACT" for x in rays),
        unmerged_strict_excess=sum(x["category"]=="UNMERGED_STRICT_EXCESS_SOURCE_UNKNOWN" for x in rays),
        original_per_ray_H_parity="NOT_RUN",scientific_approval=False,
        self_review_only=True,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        original_receipts_verified=True,raw_files_immutable=True,
        unresolved="Could be internal path length numeric error, solver geometry, or physical mismatch. Need source H parity and numeric/geometry stress tests before declaring cause."))
    print(json.dumps({"status":"RAW_SOURCE_TECHNICAL_CLASSIFICATION_NOT_PHYSICAL_ACCEPTANCE","n":total,
       "class_tie":sum(x["category"]=="TIE_CLASS_ARTIFACT" for x in rays)}))
if __name__=="__main__":main()
