#!/usr/bin/env python3
"""P3 Native RT post-run second-formula verification/aggregation.

Reads real GitHub Actions artifacts, never runs PathSolver or changes RF.
Fails closed if smoke not PASS or any one of 39 preselected source keys is
missing/duplicated or raw H/tau/path metadata is corrupted. Separately
recalculates r/s, verifies original 3 smoke matches expanded full results,
and produces one durable non-LFS ZIP plus a fully hashed JSON/CSV receipt.
"""
from __future__ import annotations
import csv,hashlib,json,math,os,pathlib,platform,sys,time,traceback,zipfile
from collections import Counter,defaultdict
import numpy as np

ROOT=pathlib.Path.cwd()
OUT=pathlib.Path(os.getenv("DLP_P3_AGG_OUT","/tmp/p3_native_aggregate"));OUT.mkdir(parents=True,exist_ok=True)
IN=pathlib.Path(os.getenv("DLP_P3_ARTIFACTS","/tmp/p3_native_downloads"))
PILOT=pathlib.Path(os.getenv("DLP_FIXED_PILOT","/tmp/p3_native_fixed_pilot"))
C0=299792458.;DF=1950000.;N=257;START=time.monotonic()
ERR=[];GATES={};RESULTS=[];STRATA=[]
SOURCE_PLAN_SHA="efb9c7b1d91b865f143f8fa26fd3defb97eed02e385ee4137062ce336e9a0b61"
P3_NATIVE_AMENDMENT="P3_NATIVE_RT_APPEND_ONLY_AMENDMENT_V1.json"
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for v in iter(lambda:f.read(1<<20),b""):h.update(v)
    return h.hexdigest()
def J(path):return json.loads(pathlib.Path(path).read_text("utf-8"))
def ck(name,success,values=None):
    GATES[name]={"status":"PASS" if success else "FAIL","values":values}
    if not success:ERR.append({"gate":name,"details":values})
    print("P3_NATIVE_AGG_CHECK",name,GATES[name]["status"],str(values)[:350],flush=True)
def independent_obs(H):
    w=.5-.5*np.cos(2*np.pi*np.arange(N)/(N-1))
    cir=np.fft.ifft(H[:,:,0]*w[:,None],n=4*N,axis=0)*N
    env=np.abs(cir)
    strongest=int(env.max(axis=0).argmax())
    tap=int(np.argmax(env[:,strongest]>=.3*env[:,strongest].max()))
    pp=np.abs(cir[tap])**2;v=float(pp.sum())
    if v<=0 or not np.isfinite(v):raise ValueError("invalid power")
    return {"s":float((pp[0]-pp[1])/v),"r_m":float(tap*C0/(4*N*DF)),"tap":tap}
def csv_rows(p):
    with p.open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def write_rows(path,items):
    if not items:
       path.write_text("empty\n");return
    cols=list(items[0])
    with path.open("w",newline="",encoding="utf-8") as f:
      w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore");w.writeheader();w.writerows(items)
def run():
    plan=J(PILOT/"P3_FROZEN_PILOT_SELECTION_PLAN.json")
    ck("A00_LOCKED_PILOT_PLAN",sha(PILOT/"P3_FROZEN_PILOT_SELECTION_PLAN.json")==SOURCE_PLAN_SHA and plan["n_pilot_pose"]==39,
       {"n":plan["n_pilot_pose"],"sha":sha(PILOT/"P3_FROZEN_PILOT_SELECTION_PLAN.json")})
    smoke=IN/"smoke";sr=smoke/"P3_NATIVE_EXECUTION_QA.json"
    if not sr.is_file():
       ck("A01_3POSE_SMOKE_SUCCESS",False,{"reason":"missing smoke artifact"});return
    sq=J(sr)
    ck("A01_3POSE_SMOKE_SUCCESS",sq["status"]=="PASS" and len(sq["results"])==3 and not sq["failures"],
       {"status":sq["status"],"n":len(sq["results"]),"failed":sq["failures"][:3]})
    if sq["status"]!="PASS":return
    smoke_map={(v["route"],v["pose_id"]):v for v in sq["results"]}
    expected={(route,int(p["pose_id"])) for route,data in plan["routes"].items() for p in data}
    seen={};counts=Counter();sample_rows=[];rt_all_full=[];max_s_err=0.;max_r_err=0.;source_max=0.
    for route in ("R2","R4","R5"):
        d=IN/route
        rec=d/"P3_NATIVE_EXECUTION_QA.json"
        if not rec.exists():ck("A02_ALL_ROUTE_RECEIPTS",False,{"route":route,"missing":True});return
        q=J(rec)
        ck("A02_ROUTE_"+route,q["status"]=="PASS" and len(q["results"])==13 and not q["failures"],
           {"route":route,"status":q["status"],"n":len(q["results"]),"failures":q["failures"][:2]})
        if q["status"]!="PASS":return
        for data in q["results"]:
            key=(data["route"],int(data["pose_id"]))
            if key in seen:ERR.append({"type":"DUPLICATE_ROUTE_POSE", "key":key});continue
            seen[key]=data
            f=d/data["file"]
            if not f.is_file() or sha(f)!=data["file_sha256"] or f.stat().st_size!=data["bytes"]:
               ERR.append({"type":"FILE_SHA_OR_SIZE_INVALID","key":key});continue
            with np.load(f,allow_pickle=False) as z:
                hl=z["H_native_los"];hf=z["H_native_full"]
                lc=z["los_path_counts"];fc=z["full_path_counts"]
                lt=z["los_tau_s"];ft=z["full_tau_s"]
                lo=z["los_tau_offsets"];fo=z["full_tau_offsets"]
                fh=z["frequency_hz"]
                if (hl.shape!=(N,2,2) or hf.shape!=(N,2,2) or not np.isfinite(hl).all() or not np.isfinite(hf).all()
                   or not np.array_equal(fh,6250400000.+DF*np.arange(N))):
                    ERR.append({"type":"INVALID_NATIVE_RF_ARRAY","key":key});continue
                if (len(lc)!=N or len(fc)!=N or np.any(lc<1) or np.any(fc<1) or
                     lo[-1]!=len(lt) or fo[-1]!=len(ft) or
                     not np.array_equal(np.diff(lo),lc) or not np.array_equal(np.diff(fo),fc) or
                     not np.isfinite(lt).all() or not np.isfinite(ft).all()):
                    ERR.append({"type":"NATIVE_PATH_DELAY_OR_OFFSETS_INVALID","key":key});continue
                ol=independent_obs(hl);of=independent_obs(hf)
                v=data["measured"]
                s_err=max(abs(ol["s"]-v["native_los_signed_s"]),
                          abs(of["s"]-v["native_full_signed_s"]))
                r_err=max(abs(ol["r_m"]-v["native_los_first_path_r_m"]),
                          abs(of["r_m"]-v["native_full_first_path_r_m"]))
                max_s_err=max(max_s_err,s_err);max_r_err=max(max_r_err,r_err)
                if (s_err>1e-10 or r_err>1e-10 or ol["tap"]!=v["native_los_first_tap"] or
                    of["tap"]!=v["native_full_first_tap"]):
                   ERR.append({"type":"NATIVE_OBSERVER_RECALC_DIFF","key":key,"s_err":s_err,"r_err":r_err})
                counts[(route,"full",int(fc.min()),int(fc.max()))]+=1
                rt_all_full.extend(fc.tolist())
                source_max=max(source_max,float(v["source_complex_rel"]))
                sample_rows.append(dict(route=key[0],pose_id=key[1],
                   original_t_s=data["time_s"],x_m=data["pos_xy_m"][0],y_m=data["pos_xy_m"][1],
                   yaw_deg=data["yaw_deg"],source_vs_native_los_H_rel=v["source_complex_rel"],
                   source_vs_native_los_s_abs=v["source_signed_s_abs"],
                   native_LoS_signed_s=v["native_los_signed_s"],
                   native_Full_signed_s=v["native_full_signed_s"],
                   full_minus_los_s=v["full_minus_los_signed_s"],
                   native_LoS_first_tap=v["native_los_first_tap"],
                   native_Full_first_tap=v["native_full_first_tap"],
                   LoS_path_count_min=v["path_counts_los_min"],
                   LoS_path_count_max=v["path_counts_los_max"],
                   Full_path_count_min=v["path_counts_full_min"],
                   Full_path_count_max=v["path_counts_full_max"],
                   full_multipath_bin_fraction=v["path_count_full_multi_fraction"],
                   Native_RT_not_hardware_measurement=True,
                   file_sha256=data["file_sha256"]))
                if key in smoke_map:
                   prior=smoke_map[key];pr=smoke/prior["file"]
                   if not pr.is_file() or sha(pr)!=prior["file_sha256"]:
                     ERR.append({"type":"SMOKE_NPZ_MISSING_OR_SHA","key":key})
                   else:
                     with np.load(pr,allow_pickle=False) as old:
                       old_h=old["H_native_los"];old_f=old["H_native_full"]
                       e0=float(np.linalg.norm(old_h-hl)/max(np.linalg.norm(hl),1e-300))
                       e1=float(np.linalg.norm(old_f-hf)/max(np.linalg.norm(hf),1e-300))
                       if max(e0,e1)>1e-5:
                          ERR.append({"type":"SMOKE_FULL_REPRODUCIBILITY","key":key,"lo":e0,"full":e1})
    ck("A03_PREDECLARED_39_KEYS",set(seen)==expected and len(seen)==39,
       {"seen":len(seen),"expected":len(expected),"missing":sorted(expected-set(seen))[:10]})
    ck("A04_NATIVE_SIONNA_H_TAU_OBSERVER",not ERR and len(sample_rows)==39,
       {"n":len(sample_rows),"first_path_s_recalc_max":max_s_err,
        "first_path_r_recalc_max_m":max_r_err,"errors":ERR[:8]})
    ck("A05_ORIGINAL_3_SMOKE_REPLAYED",len(smoke_map)==3 and all(k in seen for k in smoke_map) and
       not any(e["type"]=="SMOKE_FULL_REPRODUCIBILITY" for e in ERR if "type" in e),
       {"smoke":len(smoke_map),"full":len(seen)})
    ck("A06_NO_MISSING_NATIVE_FULL_OR_LOS",bool(rt_all_full) and min(rt_all_full)>=1,
       {"full_path_count_total_bins":len(rt_all_full),"full_path_min":min(rt_all_full) if rt_all_full else None,
        "full_path_max":max(rt_all_full) if rt_all_full else None})
    ck("A07_NO_NEW_SCENE_EKF",True,{"RT_stage":"one known C0 scene new C native physical raytracing",
         "P4":"NOT_RUN","measurement":"simulation only","synchronization":"trajectory labels only"})
    RESULTS.extend(sample_rows)
    write_rows(OUT/"P3_NATIVE_C_39_CASE_RESULTS.csv",sample_rows)
    # Archive actual per-pose native H/paths/tau, avoiding the repository's
    # *.npz Git-LFS write restriction; all original NPZ SHA verified above.
    archive=OUT/"P3_NATIVE_C_39_RAW_H_TAU_PATHS.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
       for route,pose_id in sorted(expected):
          if (route,pose_id) not in seen:continue
          r=seen[(route,pose_id)]
          f=IN/route/r["file"]
          if f.is_file():z.write(f,arcname=f"traces/{f.name}")
       z.writestr("original_preselected_plan_sha256.txt",SOURCE_PLAN_SHA+"\n")
    ck("A08_NATIVE_ARCHIVE_AND_FULL_INDEX",archive.is_file() and zipfile.ZipFile(archive).testzip() is None and len(sample_rows)==39,
       {"archive_bytes":archive.stat().st_size,"archive_sha256":sha(archive),"n_zip_entries":len(zipfile.ZipFile(archive).namelist())})
    sections=[]
    for route in ("R2","R4","R5"):
       rr=[z for z in sample_rows if z["route"]==route]
       sections.append(dict(route=route,n=len(rr),
          max_source_los_H_rel=max((r["source_vs_native_los_H_rel"] for r in rr),default=None),
          max_source_los_s_abs=max((r["source_vs_native_los_s_abs"] for r in rr),default=None),
          mean_full_minus_los_s=float(np.mean([r["full_minus_los_s"] for r in rr])) if rr else None,
          rmse_full_minus_los_s=float(np.sqrt(np.mean([r["full_minus_los_s"]**2 for r in rr]))) if rr else None,
          n_with_multipath=sum(r["Full_path_count_max"]>1 for r in rr)))
    STRATA.extend(sections)
    (OUT/"P3_NATIVE_ROUTE_SUMMARY.json").write_text(json.dumps(sections,indent=2)+"\n")
    print("P3_RT_39_NATIVE_AGGREGATED",json.dumps(sections),flush=True)

if __name__=="__main__":
   try:run()
   except Exception as e:
     ERR.append(dict(gate="AGG_CRASH",cause=repr(e),traceback=traceback.format_exc()))
     print("P3_NATIVE_AGG_FATAL",repr(e),traceback.format_exc(),flush=True)
   status="PASS_39_NATIVE_C_SIONNA_RT_CANARY" if not ERR and all(v["status"]=="PASS" for v in GATES.values()) and len(GATES)>=8 else "BLOCKED_OR_FAIL"
   receipt=dict(schema="DLP_P3_NATIVE_39_RT_AGGREGATED_V1",
       status=status,original_contract_id="DLP-EKF-GAPS-001/P3-V1",
       amended_contract=P3_NATIVE_AMENDMENT,
       original_workflow_run=os.getenv("GITHUB_RUN_ID"),
       pose_n=len(RESULTS),extra_smoke_n=3,distinct_route_n=3,
       total_native_path_solver_calls=21588 if status.startswith("PASS") else None,
       original_single_scene_n=1,
       new_C_native_full_H="COMPUTED" if status.startswith("PASS") else "INCOMPLETE",
       full_P4_EKF="NOT_RUN",
       measured_RF_hardware=False,
       retrospective_source_comparison=True,
       no_39_pose_case_selection_posthoc=True,
       gates=GATES,failures=ERR,route_stats=STRATA,
       original_preselected_plan_sha256=SOURCE_PLAN_SHA,
       computation_code_sha256=sha(__file__),
       raw_zip_sha256=sha(OUT/"P3_NATIVE_C_39_RAW_H_TAU_PATHS.zip") if (OUT/"P3_NATIVE_C_39_RAW_H_TAU_PATHS.zip").is_file() else None,
       code_and_runner_identity="same ChatGPT implementation author; separate Actions aggregation runner, not independent human auditor",
       elapsed_s=time.monotonic()-START,
       caveats=["Sionna computed physical ray tracing in same simulation corridor, not real-world measurements",
               "39 sparse pilot poses only, not all 3136 route timeline samples",
               "No cross-anchor packet timing/noise independence calibration",
               "No P4 multi-anchor EKF or generalized conclusion"])
   (OUT/"P3_NATIVE_39_AGGREGATE_QA.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
   print("P3_NATIVE_AGGREGATE_FINAL",status,"n",len(RESULTS),"errors",len(ERR),flush=True)
   sys.exit(0 if status.startswith("PASS") else 1)
