#!/usr/bin/env python3
"""P4 Full Native-C0+ actual RF completeness auditor / immutable route packager.

Verifies each new C Native PathSolver H/tau/count original SHA in all received
deterministic shards, joins immutable P3 original 39, confirms 3136/3136
original pose/time keys. Recomputes signed s/tap/raw r independently from 257
frequency 2-port H. Fail-closed on missing 1 pose, hash, timestamp, path count.
Produces per-route ZIP preserving every original raw new/old NPZ and a compact
full-route C-only H,z,tap/count bundle. Absolutely no new RF inferred.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,os,pathlib,platform,sys,time,traceback,zipfile
from collections import Counter
import numpy as np
ROOT=pathlib.Path.cwd()
CON=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P4_FULL_20261102"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
SHARDS=pathlib.Path(os.getenv("DLP_FULL_SHARDS","/tmp/p4full_shards"))
OUT=pathlib.Path(os.getenv("DLP_FULL_ROUTE_OUT","/tmp/p4full_aggregate"))
OUT.mkdir(parents=True,exist_ok=True)
C=299792458.;N=257;DF=1950000.;START=time.monotonic()
LOG=[];BAD=[];GATES={}
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def shab(b):return hashlib.sha256(b).hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_text("utf-8"))
def need(ok,msg):
 if not bool(ok):raise RuntimeError(msg)
def readcsv(p):
 with pathlib.Path(p).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def gate(name,passed,measure):
 GATES[name]={"status":"PASS" if passed else "FAIL","measured":measure}
 print("P4_FULL_RF_GATE",name,GATES[name]["status"],str(measure)[:300],flush=True)
 if not passed:BAD.append(dict(gate=name,measured=measure))
def observer(h):
 h=np.asarray(h)
 need(h.shape==(N,2,2) and np.isfinite(h).all(),"NATIVE_257x2x2_BAD")
 win=.5-.5*np.cos(2*np.pi*np.arange(N)/(N-1))
 cir=np.fft.ifft(h[:,:,0]*win[:,None],n=4*N,axis=0)*N
 amp=np.abs(cir)
 branch=int(np.argmax(amp.max(axis=0)))
 peak=float(amp[:,branch].max())
 need(peak>0,"NO_CIR")
 tap=int(np.argmax(amp[:,branch]>=.3*peak))
 p=np.abs(cir[tap])**2;den=float(np.sum(p))
 need(den>0 and np.isfinite(den),"CIR_DEN_INVALID")
 return float((p[0]-p[1])/den),float(tap*C/(1028*DF)),tap
def read_npz_bytes(raw,key,route,source_row):
 with np.load(io.BytesIO(raw),allow_pickle=False) as data:
  full=data["H_native_full"].copy();los=data["H_native_los"].copy()
  cf=data["full_path_counts"].copy();cl=data["los_path_counts"].copy()
  tf=data["full_tau_s"].copy();tl=data["los_tau_s"].copy()
  of=data["full_tau_offsets"].copy();ol=data["los_tau_offsets"].copy()
  freq=data["frequency_hz"].copy()
  pid=int(data["pose_id"])
  rt=data["route"].item()
  if "original_t_s" in data.files:
    time_s=float(data["original_t_s"]);yaw=float(data["robot_yaw_deg"])
  else:
    time_s=float(data["time_s"]);yaw=float(data["robot_yaw_deg"])
  xyz=data["robot_xyz"].copy();anchor=data["anchor_xyz"].copy()
 need(rt==route and pid==key,"NATIVE_SOURCE_ROUTE_OR_POSE_KEY_MISMATCH")
 need(full.shape==(N,2,2) and los.shape==(N,2,2) and
      np.isfinite(full).all() and np.isfinite(los).all(),"ORIGINAL_C_NATIVE_H_SHAPE_NONFINITE")
 need(np.array_equal(freq,6250400000.+DF*np.arange(N)),"ORIGINAL_NATIVE_FREQ_NOT_257")
 # The ORIGINAL CorridorSetup computes anchor z=height-standoff, i.e.
 # float64(2.7)-float64(0.05)=2.6500000000000004 (not the literal
 # float64(2.65)). Require EXACT original geometry, without tolerance edits.
 original_anchor=np.asarray([16.,.8,2.7-0.05],dtype=np.float64)
 need(np.array_equal(anchor,original_anchor),"C_ANCHOR_CHANGED")
 need(cf.shape==(N,) and cl.shape==(N,) and
      int(cf.min())>=1 and int(cl.min())>=1,"C_NATIVE_PATH_COUNTS_INVALID")
 need(np.array_equal(np.diff(of),cf) and np.array_equal(np.diff(ol),cl) and
      of[-1]==len(tf) and ol[-1]==len(tl) and
      np.isfinite(tf).all() and np.isfinite(tl).all(),"NATIVE_TAU_OFFSETS_CORRUPT")
 need(abs(time_s-source_row["t_s"])<=1e-9 and
      np.max(abs(xyz-np.array([source_row["x_m"],source_row["y_m"],.45])))<=1e-6 and
      abs(((yaw-source_row["yaw_deg"]+180)%360)-180)<=1e-6,
      "NATIVE_POSE_TIME_NOT_ORIGINAL_C0")
 # tau for each direct singleton
 dist=np.linalg.norm(xyz-anchor)
 max_tau=max(abs(tl[int(ol[i])]-dist/C) for i in range(N))
 need(max_tau<=1e-12,"NATIVE_C_DIRECT_LOS_DELAY_DRIFT")
 sl,rl,il=observer(los)
 sf,rf,ifull=observer(full)
 return dict(full=full,los=los,full_counts=cf,los_counts=cl,
             s=[sl,sf],r=[rl,rf],tap=[il,ifull],
             max_tau_s=max_tau,full_min=int(cf.min()),full_max=int(cf.max()))
def do_route(route):
 cfg=J(CON/"P4_FULL_CONFIG_LOCK.json")
 p1=J(P1/"P1_INPUT_LOCK.json")
 timeline_file=next(v["path"] for v in p1["base_assets"] if v["kind"]=="TIMELINE_TNONE" and
                    "timeline_"+route+"_" in v["path"])
 tr=readcsv(ROOT/timeline_file)
 expected=cfg["geometry"]["routes_n"][route]
 need(len(tr)==expected,"TIMELINE_SIZE_DRIFT")
 timeline={int(a["pose_id"]):dict(route=route,pose_id=int(a["pose_id"]),
       t_s=float(a["t_s"]),x_m=float(a["x"]),y_m=float(a["y"]),
       yaw_deg=float(a["yaw_body_deg"]),timeindex=i) for i,a in enumerate(tr)}
 need(len(timeline)==expected,"ORIGINAL_C0_DUPLICATE_TIME_POSE_KEY")
 oldpath=ROOT/cfg["inputs"]["old_39_zip"]
 need(sha(oldpath)==cfg["inputs"]["old_zip_sha256"],"39_ORIGINAL_NATIVE_H_SHA_CHANGED")
 original=readcsv(ROOT/cfg["inputs"]["old_39_csv"])
 old={int(v["pose_id"]):v for v in original if v["route"]==route}
 need(len(old)==13,"P3_ORIGINAL_ROUTE_39_COUNT_CHANGED")
 missing=sorted(set(timeline)-set(old))
 chunks=[missing[i:i+40] for i in range(0,len(missing),40)]
 files={}
 for chunkid,ids in enumerate(chunks):
  path=SHARDS/f"{route}_{chunkid}"/"P4_FULL_NATIVE_SHARD_RECEIPT.json"
  need(path.exists(),"MISSING_NATIVE_SHARD_RECEIPT:"+str(path))
  rec=J(path)
  need(rec["status"]=="PASS" and rec["route"]==route and
       rec["shard"]==chunkid and rec["n_expected"]==len(ids) and
       rec["n_completed"]==len(ids) and not rec["failed"],"NATIVE_SHARD_NOT_PASS:"+str(path))
  got=[int(r["pose_id"]) for r in rec["records"]]
  need(got==ids,"NATIVE_SHARD_KEY_NOT_SORTED_OR_MISSING:"+str(path))
  for record in rec["records"]:
   pid=int(record["pose_id"])
   f=path.parent/record["native_H_file"]
   need(f.is_file() and sha(f)==record["sha256"] and f.stat().st_size==record["bytes"],
        "C_NATIVE_NEW_NPZ_HASH_BAD:"+str(f))
   need(record["status"]=="PASS" and record["full_paths_min"]>=1
      and record["los_paths_min"]==1,"ORIGINAL_P4_RAW_PATHS_NOT_VALID")
   files[pid]=dict(raw=f.read_bytes(),original_sha=record["sha256"],kind="NEW_NATIVE")
 need(set(files)==set(missing),"NEW_C_NATIVE_COVERAGE_INCOMPLETE")
 with zipfile.ZipFile(oldpath) as z:
  need(z.testzip() is None,"P3_OLD_C_NATIVE_ZIP_CRC_CHANGED")
  for pid,record in old.items():
   raw=z.read(f"traces/P3_NATIVE_C_{route}_pose{pid}_full.npz")
   need(shab(raw)==record["file_sha256"],"P3_ORIGINAL_NATIVE_39_INNER_SHA_CHANGED")
   files[pid]=dict(raw=raw,original_sha=record["file_sha256"],kind="ORIGINAL_P3_NATIVE")
 need(set(files)==set(timeline),"FULL_NATIVE_C_MISSING_POSE_IDS")
 m=len(tr)
 arr=np.empty((m,2,N,2,2),np.complex128)
 cnt=np.empty((m,2,N),np.int16)
 measurements=np.empty((m,2,2),float)
 tap=np.empty((m,2),np.int16)
 rows=[];max_tau=0.;port_err=0.;n_old=0;n_new=0
 rawarchive=OUT/f"P4_FULL_C_{route}_NATIVE_H_TAU_ALL_POSES.zip"
 with zipfile.ZipFile(rawarchive,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as dest:
  for k,record in enumerate(tr):
   pid=int(record["pose_id"])
   item=files[pid]
   x=read_npz_bytes(item["raw"],pid,route,timeline[pid])
   arr[k,0]=x["los"];arr[k,1]=x["full"]
   cnt[k,0]=x["los_counts"];cnt[k,1]=x["full_counts"]
   measurements[k,0]=[x["r"][0],x["s"][0]]
   measurements[k,1]=[x["r"][1],x["s"][1]]
   tap[k]=x["tap"]
   n_old+=int(item["kind"]=="ORIGINAL_P3_NATIVE");n_new+=int(item["kind"]=="NEW_NATIVE")
   max_tau=max(max_tau,float(x["max_tau_s"]))
   rows.append(dict(route=route,pose_id=pid,timeline_index=k,
     t_s=timeline[pid]["t_s"],source_kind=item["kind"],sha256=item["original_sha"],
     native_los_count_min=int(x["los_counts"].min()),
     native_full_count_min=int(x["full_counts"].min()),native_full_count_max=int(x["full_counts"].max()),
     native_loS_signed_s=x["s"][0],native_Full_signed_s=x["s"][1],
     native_loS_raw_range_m=x["r"][0],native_Full_raw_range_m=x["r"][1],
     native_loS_first_tap=x["tap"][0],native_Full_first_tap=x["tap"][1],
     n_native_frequency_bins=N))
   dest.writestr(f"native_pose/{route}_{pid}.npz",item["raw"])
   if (k+1)%200==0:print("P4_C_NATIVE_ROUTE_VERIFY",route,k+1,"/",m,flush=True)
  # Aggregate arrays are derivable from the archived raw field data, but
  # saved for downstream all-epoch EKF and double bookkeeping validation.
  buffer=io.BytesIO()
  np.savez_compressed(buffer,original_time_s=np.array([float(r["t_s"]) for r in tr]),
     pose_id=np.array([int(r["pose_id"]) for r in tr]),
     original_x_m=np.array([float(r["x"]) for r in tr]),
     original_y_m=np.array([float(r["y"]) for r in tr]),
     original_yaw_deg=np.array([float(r["yaw_body_deg"]) for r in tr]),
     anchor_c_xyz=np.array([16,.8,2.65]),H_native_full=arr[:,1],
     H_native_los=arr[:,0],native_path_counts=cnt,
     raw_r_s=measurements,first_path_tap=tap,source_schema=np.array("P4_FULL_NATIVE_C_0FILL_0INTERPOLATE_V1"))
  compact=buffer.getvalue()
  dest.writestr(f"merged/{route}_C_NATIVE_ALL_EPOCHS.npz",compact)
  dest.writestr("provenance.txt","All per-pose actual Native Sionna RT H and real physical path delays stored; no interpolation; original 39 immutable.\n")
 gate("W04_RAW_COMPLETENESS",m==n_old+n_new and n_old==13 and n_new==m-13,
     {"route":route,"timeline":m,"original_p3":n_old,"new_native":n_new})
 gate("W05_H_TAU",max_tau<=1e-12 and cnt.min()>=1,
     {"route":route,"max_direct_delay_error_s":max_tau,"min_path_count":int(cnt.min()),
      "max_full_path_count":int(cnt[:,1].max())})
 csvname=OUT/f"P4_FULL_C_{route}_ALL_POSE_SHA_INDEX.csv"
 with csvname.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 summary=dict(schema="DLP_P4_FULL_C_NATIVE_ROUTE_PROVENANCE_V1",
     status="PASS" if all(x["status"]=="PASS" for x in GATES.values()) else "FAIL",
     route=route,original_timeline_epochs=m,original_old_p3_count=n_old,
     newly_generated_original_native_count=n_new,missing=0,
     original_39_native_zip_sha256=cfg["inputs"]["old_zip_sha256"],
     raw_archive_file=rawarchive.name,raw_archive_sha256=sha(rawarchive),
     raw_archive_bytes=rawarchive.stat().st_size,
     merged_native_C_npz_bytes=len(compact),merged_native_C_npz_sha256=shab(compact),
     merged_npz_member=f"merged/{route}_C_NATIVE_ALL_EPOCHS.npz",
     source_original_P3_one_scene=1,measured_hardware_sync=False,
     no_interpolation=True,no_source_only_substitution=True,
     checks=GATES,failures=BAD,all_original_pose_keys=sorted(timeline),
     SHA_index_file=csvname.name,SHA_index_sha256=sha(csvname),
     runner_sha256=sha(__file__),run_id=os.environ.get("GITHUB_RUN_ID"),
     verified_utc=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
 (OUT/f"P4_FULL_C_{route}_ROUTE_RECEIPT.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
 print("P4_FULL_ROUTE_AGG_FINAL",route,summary["status"],"native",n_old+n_new,
       "new",n_new,"old",n_old,"archive_sha",summary["raw_archive_sha256"],flush=True)
 return summary
def gate(name,passed,measure):
 GATES[name]={"status":"PASS" if passed else "FAIL","measured":measure}
 if not passed:BAD.append(dict(gate=name,measured=measure))
 print("P4_FULL_C_VERIFY",name,GATES[name]["status"],str(measure)[:450],flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--route",choices=("R2","R4","R5"),required=True)
 args=p.parse_args()
 try:
  result=do_route(args.route)
  sys.exit(0 if result["status"]=="PASS" else 1)
 except Exception as e:
  print("P4_FULL_C_AGG_FATAL",repr(e),traceback.format_exc(),flush=True)
  (OUT/f"P4_FULL_C_{args.route}_FATAL.json").write_text(json.dumps(dict(
    status="BLOCKED",route=args.route,error=repr(e),traceback=traceback.format_exc(),
    n_failed=len(BAD),source_code_sha256=sha(__file__)),indent=2)+"\n")
  sys.exit(1)
