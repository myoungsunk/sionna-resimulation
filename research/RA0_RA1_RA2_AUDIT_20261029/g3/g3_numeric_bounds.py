#!/usr/bin/env python3
"""Original receipt constrained numeric/geometry audit on G3 23 stations (25 rays).
Can exclude simple rounding/casting; MUST NOT classify missing per-ray tau by guess.
"""
from __future__ import annotations
import csv, hashlib, io, json, pathlib, re, sys, tarfile, urllib.request
import numpy as np
from qclean_uwb.features.reflection_attribution import image_delays
from qclean_uwb.drivesim.paths import _classes, TIE_S
from qclean_uwb.drivesim.rf_store import tag_of
HERE=pathlib.Path(__file__).resolve().parent
LOCK=HERE/"G3_23_ORIGINAL_SOURCE_LOCK.json"
SOURCE="9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13"
REPO="https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/"
ARCHIVE="results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z/final_20261007T140446Z.tar.gz"
ARCHIVE_SHA="2d2321599ae08e7b98a8652133e22173eaed7731d11e5cb89863b5c91b4bde06"
REC_RE=re.compile(r"(?:^|/)traces_(R[245]_a[AB])/([^/]+)_trace_receipt.json$")
THR=5e-14
C0=299792458.

def sha(b):return hashlib.sha256(b).hexdigest()
def download(url,p):
 if not p.is_file():
  with urllib.request.urlopen(url,timeout=150) as f,p.open("wb") as o:
   while True:
    b=f.read(1<<20)
    if not b:break
    o.write(b)
 return p
def main(outdir):
 out=pathlib.Path(outdir);out.mkdir(parents=True,exist_ok=True)
 contract=json.loads(LOCK.read_text())
 items=contract["items"];assert len(items)==23 and sum(int(i["expected_n_strict_paths"]) for i in items)==25
 arc=download(REPO+SOURCE+"/"+ARCHIVE,out/"cached_original_receipts.tar.gz")
 if sha(arc.read_bytes())!=ARCHIVE_SHA:raise SystemExit("ERR_ARCHIVE_DIGEST")
 req={(o["case"],o["tag"]):o for o in items}
 receipts={}
 with tarfile.open(arc,"r:gz") as tf:
  for item in tf:
   if not item.isfile():continue
   m=REC_RE.search(item.name)
   if m and (m.group(1),m.group(2)) in req:
    key=(m.group(1),m.group(2))
    if key in receipts:raise SystemExit("ERR_DUPLICATE_RECEIPT")
    bytes_=tf.extractfile(item).read()
    if sha(bytes_)!=req[key]["expected_original_receipt_sha256"]:
     raise SystemExit("ERR_RECEIPT_SHA "+str(key))
    receipts[key]=json.loads(bytes_)
 if set(receipts)!=set(req):raise SystemExit("ERR_MISSING_RECEIPTS "+str(set(req)-set(receipts)))
 timelines={}
 for route in ("R2","R4","R5"):
  raw=download(REPO+SOURCE+f"/results/DRIVE_SIM_20261007/S1/routes/timeline_{route}_Tnone.csv",out/f"timeline_{route}.csv")
  rows=list(csv.DictReader(raw.open()))
  timelines[route]={tag_of(float(r["x"]),float(r["y"])):r for r in rows if r["phase"]=="drive"}
 rows=[]
 for (case,tag),entry in sorted(req.items()):
  receipt=receipts[(case,tag)]
  x,y=float(receipt["x"]),float(receipt["y"])
  if receipt["tag"]!=tag or int(receipt["unmatched_paths"])!=int(entry["expected_n_strict_paths"]):raise SystemExit("ERR_RECORD_PARITY "+case+" "+tag)
  t=timelines[case[:2]][tag]
  delta_pose=float(np.hypot(x-float(t["x"]),y-float(t["y"])))
  tx=np.array([4. if case.endswith("aA") else 10.,0.,2.65])
  rx=np.array([x,y,.45])
  tab=image_delays(tx,rx,20.,1.2,2.7,3)
  arr=np.array(list(tab.values()),dtype=np.float64)
  class_delays,_=_classes(tab)
  raw_float32=arr.astype(np.float32).astype(np.float64)
  rawerr=np.abs(raw_float32-arr)
  # Classify SOURCE-CANDIDATE mechanisms, NOT the historic 25 paths.
  idx=np.abs(raw_float32[:,None]-class_delays[None,:]).argmin(axis=1)
  mergederr=np.abs(raw_float32-class_delays[idx])
  classerr=np.abs(arr-class_delays[np.abs(arr[:,None]-class_delays[None,:]).argmin(axis=1)])
  possible_class=int(np.sum((rawerr<=THR) & (mergederr>THR)))
  possible_unmerged=int(np.sum(rawerr>THR))
  max_half_ulp=float(np.max(np.spacing(arr.astype(np.float32)).astype(np.float64)/2))
  if float(np.max(rawerr))>max_half_ulp+1e-20:raise SystemExit("ERR_FLOAT32_BOUND")
  if delta_pose/C0>THR:raise SystemExit("ERR_POSE_DELTA")
  rows.append(dict(case=case,tag=tag,pose_id=t["pose_id"],n_actual_failed_paths=entry["expected_n_strict_paths"],
    raw_tau_missing=True,verified_receipt_sha=entry["expected_original_receipt_sha256"],
    n_image_candidates=len(arr),n_classes=len(class_delays),
    max_float32_rounding_s=float(np.max(rawerr)),max_half_float32_ulp_s=max_half_ulp,
    max_class_merging_s=float(np.max(classerr)),n_image_candidates_fail_after_cast_and_merge=int((mergederr>THR).sum()),
    n_class_only_potential=possible_class,n_float32_cast_only_potential=possible_unmerged,
    actual_ray_mechanism="NOT_IDENTIFIABLE_WITHOUT_RAW_TAU",
    coord_delta_m=delta_pose,coord_delay_upper_s=delta_pose/C0,
    no_local_H_repair_authorized=True))
 assert len(rows)==23
 result=dict(status="25_ORIGINAL_RAW_TAU_MISSING__NUMERIC_HYPOTHESES_BOUND_ONLY",
   original_receipts_sha_verified=23,requested_original_rays=25,
   max_final_float32_cast_only_error_s=max(r["max_float32_rounding_s"] for r in rows),
   max_timeline_pose_delay_s=max(r["coord_delay_upper_s"] for r in rows),
   n_stations_with_potential_merged_class_excess=sum(r["n_class_only_potential"]>0 for r in rows),
   total_image_candidate_class_excess=sum(r["n_class_only_potential"] for r in rows),
   n_stations_where_simple_float32_cast_exceeds_strict=sum(r["n_float32_cast_only_potential"]>0 for r in rows),
   strict_s=THR,tie_s=TIE_S,
   conclusion="Final float32 casting and source timeline coordinate rounding alone cannot cause strict excess at these stations; class merging has counterexamples but actual 25 ray indices/tau absent, so no causal attribution.",
   source_status="BLOCKED_25_ORIGINAL_TAU",local_H_patch="NOT_JUSTIFIED_FROM_G3_ALONE",self_review_only=True)
 with (out/"G3_NUMERIC_BOUNDS.json").open("w") as f:json.dump(result,f,indent=2)
 with (out/"G3_23_STATION_HYPOTHESIS_BOUNDS.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(json.dumps(result),flush=True)
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "g3_precision_out")
