#!/usr/bin/env python3
"""Reconstruct G3 strict-failure locations from archived 2026-10-07 trace receipts.
Read-only, source SHA locked. Distinguish raw ray tau absent from receipt.
"""
import csv, hashlib, io, json, math, pathlib, re, sys, tarfile, urllib.request
from collections import Counter
import numpy as np
from qclean_uwb.features.reflection_attribution import image_delays
from qclean_uwb.drivesim.paths import _classes, TIE_S
from qclean_uwb.drivesim.rf_store import tag_of

REPO="myoungsunk/sionna-resimulation"
SRC="9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13"
ARCHIVE_SHA="2d2321599ae08e7b98a8652133e22173eaed7731d11e5cb89863b5c91b4bde06"
BUNDLE="results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z/final_20261007T140446Z.tar.gz"
RUN="results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/S2/G3_continuity_"
CASES=["R2_aA","R2_aB","R4_aA","R4_aB","R5_aA","R5_aB"]
EXPECTED={"R2":925,"R4":547,"R5":1343}
C0=299792458.
REGEX=re.compile(r"(?:^|/)(traces_(R[245]_a[AB]))/([^/]+)_trace_receipt\.json$")
def get(url):
 with urllib.request.urlopen(url,timeout=120) as f:return f.read()
def raw(ref,path):return get(f"https://raw.githubusercontent.com/{REPO}/{ref}/{path}")
def dumpcsv(p,rows,cols):
 with p.open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,cols,extrasaction="ignore");w.writeheader();w.writerows(rows)
def image_checks(r,anchor_x):
 tx=np.array([anchor_x,0,2.65])
 rx=np.array([float(r["x"]),float(r["y"]),.45])
 tab=image_delays(tx,rx,20.,1.2,2.7,3)
 rawtaus=np.array(list(tab.values()),float)
 cd,names=_classes(tab)
 # Class matcher uses the earliest (lowest delay) representative.
 near=np.min(abs(rawtaus[:,None]-cd[None,:]),axis=1)
 return tab,rawtaus,cd,dict(n_image=len(tab),n_image_classes=len(cd),
  max_class_shift_s=float(max(near)),n_image_shift_gt_strict=int((near>5e-14).sum()),
  min_image_gap_s=float(np.diff(np.sort(rawtaus)).min()),
  n_image_strict_potential=int((near>5e-14).sum()))
def main(outdir):
 out=pathlib.Path(outdir);out.mkdir(parents=True,exist_ok=True)
 tar_path=out/"cached_archival_trace_receipts.tar.gz"
 if not tar_path.exists():tar_path.write_bytes(raw("f100a983cc389fcdef073592a254add61e7115da",BUNDLE))
 got=hashlib.sha256(tar_path.read_bytes()).hexdigest()
 if got!=ARCHIVE_SHA:raise SystemExit(f"ERR_ARCHIVE_HASH {got}")
 receipts={}
 seenpaths=[]
 with tarfile.open(tar_path,"r:gz") as tf:
  for m in tf.getmembers():
   k=REGEX.search(m.name)
   if k and m.isfile():
    case,tag=k.group(2),k.group(3)
    if (case,tag) in receipts:raise RuntimeError("ERR_DUPLICATE_RECEIPT")
    receipts[(case,tag)]=json.load(tf.extractfile(m))
    seenpaths.append(m.name)
 if len(receipts)!=5630:raise SystemExit(f"ERR_RECEIPT_COUNT {len(receipts)} !=5630; names={seenpaths[:5]}")
 rows=[];block_receipts=[];totals=[]
 for case in CASES:
  route=case[:2]
  expected=EXPECTED[route]
  rr={k[1]:v for k,v in receipts.items() if k[0]==case}
  if len(rr)!=expected:raise RuntimeError(f"ERR_GROUP_RECEIPT_COUNT {case} {len(rr)}")
  timeline=list(csv.DictReader(io.StringIO(raw(SRC,f"results/DRIVE_SIM_20261007/S1/routes/timeline_{route}_Tnone.csv").decode())))
  source_by_tag={}
  for pose in timeline:
   if pose["phase"]!="drive":continue
   tag=tag_of(round(float(pose["x"]),6),round(float(pose["y"]),6))
   if tag in source_by_tag:raise RuntimeError(f"ERR_TAG_COLLISION {case} {tag}")
   source_by_tag[tag]=pose
  if set(rr)!=set(source_by_tag):raise RuntimeError(f"ERR_TAG_JOIN {case} receipts={len(rr)} timeline={len(source_by_tag)}")
  bad=0;drop_count=0;drop_matching=[]
  for tag,r in rr.items():
   p=source_by_tag[tag]
   rx=float(r["x"]);ry=float(r["y"])
   dx=rx-float(p["x"]);dy=ry-float(p["y"]);dp=math.hypot(dx,dy)
   if dp>1e-6:raise RuntimeError(f"ERR_POSE_COORDINATE_DIFFERENCE {case} {tag} ({dx},{dy})")
   n=int(r["unmatched_paths"])
   if n>0:
    bad+=n
    tab,rtau,cd,geom=image_checks(r,4. if case.endswith("aA") else 10.)
    # source receipt carries some tau values, only for freq-dropped paths; never pretend these cover all.
    dropped=[]
    for d in r.get("dropped_audit",[]):
     if not isinstance(d,dict) or "tau_s" not in d:continue
     tau=float(d["tau_s"])
     rawdiff=float(np.min(abs(rtau-tau)))
     mdiff=float(np.min(abs(cd-tau)))
     dropped.append({"path_id":d.get("path"),"tau":tau,"d_raw":rawdiff,"d_merged":mdiff,"is_strict_fail":mdiff>5e-14,
                     "caused_by_merge":rawdiff<=5e-14 and mdiff>5e-14})
    nstr=sum(x["is_strict_fail"] for x in dropped)
    row=dict(case=case,tag=tag,pose_id=p["pose_id"],x=rx,y=ry,t_s=p["t_s"],
      coordinate_delta_m=dp,coordinate_max_delay_s=dp/C0,strict_mismatch_paths=n,n_paths=int(r["n_paths"]),
      n_archived_tau=len(dropped),n_strict_mismatch_with_archived_tau=nstr,
      n_confirmed_merge_causes=sum(x["caused_by_merge"] for x in dropped),
      **geom)
    rows.append(row)
    block_receipts.append(dict(**row, archived_dropped_tau_checks=dropped,receipted_versions=r.get("versions"),
                               n_nodes=r.get("n_nodes"),checksum_status="FROM_SHA256_VERIFIED_ARCHIVE"))
  g3=json.loads(raw("f100a983cc389fcdef073592a254add61e7115da",RUN+case+".json"))
  reference=int(g3["unmatched_paths_total"]["tol_5e-14"])
  totals.append({"case":case,"receipt_strict_paths":bad,"g3_strict_paths":reference,"stations":len(rr),"affected_tags":sum(r["case"]==case for r in rows)})
  if bad!=reference:raise SystemExit(f"ERR_G3_COUNT_PARITY {case} receipts {bad} vs g3 {reference}")
 if sum(x["receipt_strict_paths"] for x in totals)!=26:raise SystemExit("ERR_TOTAL_26")
 col=["case","tag","pose_id","x","y","t_s","coordinate_delta_m","coordinate_max_delay_s","strict_mismatch_paths","n_paths",
      "n_archived_tau","n_strict_mismatch_with_archived_tau","n_confirmed_merge_causes",
      "n_image","n_image_classes","max_class_shift_s","n_image_shift_gt_strict","min_image_gap_s"]
 dumpcsv(out/"G3_26_OFFENDING_STATIONS.csv",rows,col)
 (out/"G3_26_EVIDENCE.json").write_text(json.dumps({"status":"LOCATIONS_RECOVERED_TAU_PARTIAL","frozen_archive_sha256":ARCHIVE_SHA,
      "raw_tau_npz_in_original_bundle":False,"total_receipts":len(receipts),"total_strict_paths":26,
      "n_offending_stations":len(rows),"max_coordinate_delta_m":max(x["coordinate_delta_m"] for x in rows),"max_delay_explainable_by_timeline_rounding_s":max(x["coordinate_max_delay_s"] for x in rows),"groups":totals,"records":block_receipts,
      "raw_tau_status":"DROPPED_PATH_ONLY; missing non-dropped per-ray tau must be retrieved from preserved source or regenerated",
      "audit_limit":"Cannot classify all 26 path IDs and change H without original per-ray tau and Jones responses."},indent=2))
 print(json.dumps({"status":"LOCATIONS_RECOVERED_TAU_PARTIAL","records":len(receipts),
  "offending_stations":len(rows),"failed_paths":26,"archived_dropped_tau":sum(r["n_archived_tau"] for r in rows),
  "confirmed_merge":sum(r["n_confirmed_merge_causes"] for r in rows),"groups":totals}))
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "g3_out")
