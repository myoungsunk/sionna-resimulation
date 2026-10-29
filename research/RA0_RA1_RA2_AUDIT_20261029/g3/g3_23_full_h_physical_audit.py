#!/usr/bin/env python3
"""G3 original 23 traces: exact 25-ray delay attribution, original H reconstruction,
and clearly hypothetical tau-only corrections (never writes source H/NPZ).
All evidence is read-only; a matching H does not establish physical truth.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, math, pathlib, sys, zipfile
import numpy as np
from qclean_uwb.drivesim import pattern_apply as P
from qclean_uwb.drivesim.paths import path_residuals, TIE_S
from qclean_uwb.drivesim.rf_store import h_for_antenna_yaws, tag_of
from qclean_uwb.features.reflection_attribution import image_delays
C=299792458.0; STRICT=5e-14; RELAX=2e-13
SHA_ZIP="4f625c84172fecd7539273eb8d19c841fd2eb204b61d9062a3b901cca6dc4a62"
BANKS={"LP_plus45_bank.npz":"b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b","LP_minus45_bank.npz":"39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9"}
H_SHA={"R2_aB":"b3b4c61e23286b86c78b6e87f5b9b5358121cbde7717bae73e5650cc900b546c",
       "R4_aA":"73cfc35ded71b0114d3b15d2a50dba4a804b377d7b3b2b37aafe11c628c83956",
       "R4_aB":"30743ca017615bbfede78a8350739262a756d47ac2213c60b08eb109cebfe1b0",
       "R5_aA":"026a2c5ebb17916633f74d767ec8675f9358c93f8a4ee0df465733838ec89f80",
       "R5_aB":"a4858372414f81156b25fde2e14d57fc0e1a3f987782a5b268dbdf14bcf174b3"}
GROUPS={"R2_aB":1,"R4_aA":3,"R4_aB":3,"R5_aA":9,"R5_aB":9}

def sha(data):
 if isinstance(data,pathlib.Path):
  h=hashlib.sha256()
  with data.open("rb") as f:
   for b in iter(lambda:f.read(1<<20),b""):h.update(b)
  return h.hexdigest()
 return hashlib.sha256(data).hexdigest()

def obs(H, freq):
 z=np.asarray(H)[:,:,0];n=len(freq)
 w=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1))
 p=np.zeros((4*n,2),complex);p[:n,:]=z*w[:,None]
 cir=np.fft.ifft(p,axis=0)*n
 amp=np.abs(cir);branch=int(amp.max(axis=0).argmax())
 ix=int(np.flatnonzero(amp[:,branch]>=.3*amp[:,branch].max())[0])
 pow=np.abs(cir[ix,:])**2;s=float((pow[0]-pow[1])/pow.sum()) if pow.sum() else float("nan")
 return dict(tap=ix,rx_peak_port=branch,r_m=float(ix*C/(4*n*(freq[1]-freq[0]))),s=s)

def independent_image(tx,rx):
 # Independent geometry from source image_delays: enumerate 6 axis-aligned planes
 import itertools
 planes={"floor":(2,0.),"ceiling":(2,2.7),"wall_y_neg":(1,-1.2),
         "wall_y_pos":(1,1.2),"end_x_min":(0,0.),"end_x_max":(0,20.)}
 out={():float(np.linalg.norm(tx-rx)/C)}
 for n in (1,2,3):
  for seq in itertools.product(planes,repeat=n):
   if any(a==b for a,b in zip(seq,seq[1:])):continue
   img=rx.copy()
   for name in reversed(seq):
    ax,val=planes[name];img[ax]=2*val-img[ax]
   out[seq]=float(np.linalg.norm(tx-img)/C)
 return out

def csv_out(path,records):
 if not records:raise RuntimeError("ERR_EMPTY_OUTPUT")
 with path.open("w",newline="",encoding="utf8") as f:
  w=csv.DictWriter(f,list(records[0]));w.writeheader();w.writerows(records)

def main():
 ap=argparse.ArgumentParser()
 for k in ("zip","manifest","lock","bank_dir","h_dir","poses_dir","out"):
  ap.add_argument("--"+k,required=True,type=pathlib.Path)
 a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 if sha(a.zip)!=SHA_ZIP:raise SystemExit("ERR_ZIP_SHA "+sha(a.zip))
 manifest=json.loads(a.manifest.read_text());lock=json.loads(a.lock.read_text())
 assert manifest["n_raw"]==23 and manifest["n_receipts"]==23 and manifest["n_ray_historic_strict"]==25
 entries={item["path"]:item for item in manifest["items"]}
 target={(item["case"],item["tag"]):item for item in lock["items"]}
 if len(target)!=23 or sum(v["expected_n_strict_paths"] for v in target.values())!=25:raise SystemExit("ERR_CONTRACT")
 banks=[]
 for n,digest in BANKS.items():
  p=a.bank_dir/n
  if sha(p)!=digest:raise SystemExit("ERR_BANK_SHA "+n)
  with np.load(p,allow_pickle=False) as z:banks.append(P.Bank(dict(z)))
 freq=banks[0].freqs_hz
 if not np.array_equal(freq,banks[1].freqs_hz) or len(freq)!=257:raise SystemExit("ERR_FREQ_BANK")
 poses={}
 for r in ("R2","R4","R5"):
  po=json.loads((a.poses_dir/f"rf_poses_{r}.json").read_text())
  tags=collections.defaultdict(list)
  for p in po:tags[tag_of(float(p["x"]),float(p["y"]))].append(p)
  poses[r]=tags
 H={}
 for c,expect in H_SHA.items():
  p=a.h_dir/f"H_{c}_m0.npy"
  if sha(p)!=expect:raise SystemExit("ERR_ORIGINAL_H_SHA "+c)
  H[c]=np.load(p,mmap_mode="r",allow_pickle=False)
 rays=[];hrows=[];files=[]
 with zipfile.ZipFile(a.zip) as z:
  names=[n for n in z.namelist() if n!="G3_REQUESTED_SOURCE_MANIFEST.json"]
  if set(names)!=set(entries) or len(names)!=46 or len(names)!=len(set(names)):raise SystemExit("ERR_MEMBERSHIP")
  for name in names:
   if ".." in pathlib.PurePosixPath(name).parts:raise SystemExit("ERR_TRAVERSAL")
   contents=z.read(name)
   if sha(contents)!=entries[name]["sha256"] or len(contents)!=entries[name]["size"]:
    raise SystemExit("ERR_FILE_SHA "+name)
  for (case,tag),item in sorted(target.items()):
   base=item["original_relpath"]
   rname=base.replace("_trace.npz","_trace_receipt.json")
   meta=json.loads(z.read(rname))
   if sha(z.read(rname))!=item["expected_original_receipt_sha256"]:raise SystemExit("ERR_RECEIPT_SHA "+case+"/"+tag)
   if meta["tag"]!=tag or meta["status"]!="OK" or int(meta["unmatched_paths"])!=int(item["expected_n_strict_paths"]):
    raise SystemExit("ERR_META_ORIGINAL "+case+"/"+tag)
   with np.load(io.BytesIO(z.read(base)),allow_pickle=False) as dat:tr={k:dat[k] for k in dat.files}
   tr["status"]=str(tr["status"])
   tau=np.asarray(tr["tau"],np.float64)
   if not (tr["status"]=="OK" and len(tau)==int(meta["n_paths"]) and
           tr["jones"].shape[1]==len(tau) and np.isfinite(tau).all() and np.isfinite(tr["jones"]).all()):
    raise SystemExit("ERR_TRACE_ARRAYS "+case+"/"+tag)
   rx=np.array([float(tr["x"]),float(tr["y"]),.45])
   tx=np.array([4. if case.endswith("_aA") else 10.,0.,2.65])
   if abs(rx[0]-float(meta["x"]))>1e-7 or abs(rx[1]-float(meta["y"]))>1e-7:raise SystemExit("ERR_TRACE_XY")
   source=image_delays(tx,rx,20.,1.2,2.7)
   alt=independent_image(tx,rx)
   if set(source)!=set(alt) or max(abs(source[k]-alt[k]) for k in source)>1e-20:raise SystemExit("ERR_INDEPENDENT_IMAGE")
   rep,pick,cd,class_names=path_residuals(tau,tx,rx,20.,1.2,2.7)
   bad=np.flatnonzero(rep>STRICT)
   if len(bad)!=int(item["expected_n_strict_paths"]) or (rep>RELAX).any():raise SystemExit("ERR_G3_COUNT "+case+"/"+tag)
   change_tau=np.asarray(tau).copy();deltas=[]
   for ray in bad:
    t=float(tau[ray]);seq,dt=min(source.items(),key=lambda pair:abs(t-pair[1]))
    unmerged=float(abs(t-dt));merged=float(rep[ray])
    seq_name="LOS" if not seq else ">".join(seq)
    f32=float(np.float32(t));f32ulp=float(abs(np.spacing(np.float32(t))))
    class_artifact=bool(unmerged<=STRICT and merged>STRICT)
    categories="TIE_CLASS_ARTIFACT" if class_artifact else "UNMERGED_STRICT_EXCESS"
    nearest_f32_image=float(np.float32(dt))
    rayrec=dict(case=case,tag=tag,ray_index=int(ray),tau_source_s=t,tau_dtype=str(tr["tau"].dtype),
      best_image_sequence=seq_name,best_image_tau_s=float(dt),
      residual_unmerged_s=unmerged,residual_merged_s=merged,
      category=categories,original_tau_exact_f32=bool(t==f32),f32_ulp_s=f32ulp,
      image_final_cast_residual_s=float(abs(t-nearest_f32_image)),
      beyond_final_f32_rounding=bool(unmerged>.5*f32ulp+1e-18),
      path_jones_norm=float(np.linalg.norm(tr["jones"][:,ray])),n_source_paths=int(len(tau)),
      trace_sha256=sha(z.read(base)),source_receipt_sha256=sha(z.read(rname)),H_corrected_source="HYPOTHETICAL_IMAGE_DELAY_ONLY_NOT_PHYSICAL_VALIDATION")
    rays.append(rayrec)
    change_tau[ray]=dt
   psel=poses[case[:2]].get(tag,[])
   if not psel:raise SystemExit("ERR_POSE_MAPPING "+case+"/"+tag)
   tr_alt=dict(tr);tr_alt["tau"]=change_tau
   all_yaws=[float(p["yaw_body_deg"]) for p in psel]
   re=h_for_antenna_yaws(tr,banks,all_yaws)
   hypothetical=h_for_antenna_yaws(tr_alt,banks,all_yaws)
   max_rel_source=0.;max_obs_diff_s=0.;max_obs_diff_r=0.;max_change_h=0.;max_relative_h=0.;tapswitch=0
   for i,pose in enumerate(psel):
    pid=int(pose["pose_id"])
    stored=H[case][pid]
    assert stored.shape==(257,2,2)
    err=float(np.max(np.abs(re[i]-stored)));reference=float(np.max(np.abs(stored)))
    rel=err/max(reference,1e-30)
    if rel>5e-9:raise SystemExit(f"ERR_H_RECONSTRUCT {case}/{tag}/{pid} {rel}")
    delta=hypothetical[i]-re[i]
    before=obs(stored,freq);after=obs(stored+delta,freq)
    ds=abs(before["s"]-after["s"]);dr=abs(before["r_m"]-after["r_m"])
    row=dict(case=case,tag=tag,pose_id=pid,mount_deg=0,n_failed_rays=len(bad),
      original_H_sha256=H_SHA[case],H_replay_abs=err,H_replay_rel=rel,
      hypothetical_delta_tau_max_s=max(abs(change_tau-tau)),
      hypothetical_dH_abs=float(np.max(np.abs(delta))),
      hypothetical_dH_l2_rel=float(np.linalg.norm(delta)/np.linalg.norm(stored)),
      hypothetical_delta_s=float(ds),hypothetical_delta_r_m=float(dr),
      tap_before=before["tap"],tap_after=after["tap"],tap_switched=before["tap"]!=after["tap"],
      hypothetical_s_tolerance_ok=bool(ds<=1e-12),hypothetical_r_tolerance_ok=bool(dr<=1e-9))
    hrows.append(row);max_rel_source=max(max_rel_source,rel)
    max_obs_diff_s=max(max_obs_diff_s,ds)
    max_obs_diff_r=max(max_obs_diff_r,dr)
    max_change_h=max(max_change_h,row["hypothetical_dH_abs"])
    max_relative_h=max(max_relative_h,row["hypothetical_dH_l2_rel"])
    tapswitch+=int(row["tap_switched"])
   files.append(dict(case=case,tag=tag,strict_paths=int(len(bad)),reconstructed_pose_rows=len(psel),
     max_replay_rel=max_rel_source,max_hypothetical_s=max_obs_diff_s,
     max_hypothetical_r_m=max_obs_diff_r,max_hypothetical_H_abs=max_change_h,
     max_hypothetical_H_rel=max_relative_h,n_tap_switch=tapswitch))
 if len(rays)!=25 or len(files)!=23:raise SystemExit("ERR_EXPECTED_25_RAYS")
 for case,n in GROUPS.items():
  if sum(r["case"]==case for r in rays)!=n:raise SystemExit("ERR_CASE_COUNT "+case)
 csv_out(a.out/"G3_25_ORIGINAL_RAY_CLASSIFICATION.csv",rays)
 csv_out(a.out/"G3_23_ORIGINAL_H_PARITY_AND_HYPOTHETICAL.csv",hrows)
 csv_out(a.out/"G3_23_STATION_SUMMARY.csv",files)
 count=collections.Counter(r["category"] for r in rays)
 result=dict(status="ORIGINAL_25_RAY_AND_H_REPLAY_COMPLETED",
   source_delivery_sha256=SHA_ZIP,original_receipts_verified=23,n_original_trace=23,n_strict_paths=25,
   n_affected_stations=23,n_original_H_rows_reconstructed=len(hrows),
   original_H_sha256=H_SHA,bank_sha256=BANKS,category_count=dict(count),
   max_H_replay_rel=max(x["H_replay_rel"] for x in hrows),
   max_hypothetical_dH_l2_rel=max(x["hypothetical_dH_l2_rel"] for x in hrows),
   max_hypothetical_ds=max(x["hypothetical_delta_s"] for x in hrows),
   max_hypothetical_dr_m=max(x["hypothetical_delta_r_m"] for x in hrows),
   hypothetical_n_tap_switch=sum(x["tap_switched"] for x in hrows),
   hypothetical_n_s_tol_exceeded=sum(not x["hypothetical_s_tolerance_ok"] for x in hrows),
   hypothetical_n_r_tol_exceeded=sum(not x["hypothetical_r_tolerance_ok"] for x in hrows),
   source_H_unchanged=True,
   physical_causality_claim="NOT_PROVEN_BY_DELAY_MATCH_ALONE",
   minimal_repair_decision="DO_NOT_MODIFY_H_WITHOUT_IDENTIFIED_PHYSICAL_MODEL_OR_SOLVER_ERROR",
   self_review_only=True,
   note="Image-delay hypothetical normalization is a numerical sensitivity experiment, not a validated physical ray correction; H/source arrays are unchanged.")
 (a.out/"G3_25_H_REVALIDATION_QA.json").write_text(json.dumps(result,indent=2))
 print(json.dumps(result),flush=True)
if __name__=="__main__":main()
