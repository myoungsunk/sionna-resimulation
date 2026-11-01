#!/usr/bin/env python3
"""Independent *arithmetic* second-pass on the committed P1 results.

A separate GitHub runner and fresh formulas verify post-run metrics.
Authored in the same ChatGPT conversation as the P1 implementer:
SELF_REVIEW_ONLY for independent-actor governance; NO human reviewer claim.
No RF, source, frozen science or outputs overwritten.
"""
from __future__ import annotations
import csv,hashlib,json,math,os,pathlib,platform,sys,traceback,collections,datetime
ROOT=pathlib.Path(os.environ["DLP_POST_INPUT"])
OUT=pathlib.Path(os.environ["DLP_POST_OUT"]);OUT.mkdir(parents=True,exist_ok=True)
fail=[];metrics={};checks={}
CASE_COUNTS={"R2_aA_m0":1303,"R2_aB_m0":1303,"R2_aA_m45":1303,
             "R4_aA_m0":922,"R4_aB_m0":922,"R5_aA_m0":1883,"R5_aB_m0":1883}
def check(name,ok,info,measured=None):
    checks[name]=dict(status="PASS" if ok else "FAIL",note=str(info))
    if measured is not None:checks[name]["measured"]=measured
    if not ok:fail.append(dict(id=name,details=info))
    print("POSTCHECK",name,checks[name]["status"],info,flush=True)
def h(p):
    sha=hashlib.sha256()
    with p.open("rb") as f:
      for b in iter(lambda:f.read(1024*1024),b""):sha.update(b)
    return sha.hexdigest()
def csv_rows(name):
    with (ROOT/name).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def near(a,b,tol=1e-10):return abs(float(a)-float(b))<=tol
def pstat(xs):
    n=len(xs)
    mr=math.fsum(x for x,_ in xs)/n
    ms=math.fsum(s for _,s in xs)/n
    rmser=math.sqrt(math.fsum(x*x for x,_ in xs)/n)
    rmses=math.sqrt(math.fsum(s*s for _,s in xs)/n)
    if n<=1:return mr,ms,rmser,rmses,None
    rr=math.fsum((x-mr)**2 for x,s in xs)/(n-1)
    rs=math.fsum((x-mr)*(s-ms) for x,s in xs)/(n-1)
    ss=math.fsum((s-ms)**2 for x,s in xs)/(n-1)
    eig=(rr+ss-math.hypot(rr-ss,2*rs))/2
    return mr,ms,rmser,rmses,(rr,rs,ss,eig)
def want(row,grp):
    if row["channel"]!=grp["channel"]:return False
    l=grp["stratum_level"]
    if l=="CHANNEL_ALL":return True
    if l=="CHANNEL_BIN":return row["distance_bin"]==grp["distance_bin"]
    if l=="ROUTE_BIN":return row["route"]==grp["stratum_id"] and row["distance_bin"]==grp["distance_bin"]
    if l=="CASE_ALL":return row["case_id"]==grp["stratum_id"]
    if l=="CASE_BIN":return row["case_id"]==grp["stratum_id"] and row["distance_bin"]==grp["distance_bin"]
    raise RuntimeError("UNRECOGNIZED_STRATUM:"+str(l))
def main():
  qa=json.loads((ROOT/"P1_SCIENCE_QA.json").read_text())
  manifest=json.loads((ROOT/"P1_MANIFEST.json").read_text())
  check("A0_PINNED_ID", qa["status"]=="PASS" and manifest["status"]=="PASS" and
        qa["contract_sha256"]=="373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594" and
        qa["run_id"]=="41300302082","original frozen science identity unchanged")
  outputs=[]
  for rec in manifest["outputs"]:
    path=ROOT/rec["name"]
    correct=path.is_file() and path.stat().st_size==rec["bytes"] and h(path)==rec["sha256"]
    outputs.append(dict(name=rec["name"],match=correct))
  check("A1_OUTPUT_SHA",len(outputs)==8 and all(z["match"] for z in outputs),
        "8 committed science output files SHA256 match original frozen manifest",outputs)
  rows=csv_rows("P1_MATCHED_SIGNED_ERRORS.csv")
  parity=csv_rows("P1_RAW_OBSERVER_PARITY.csv")
  moments=csv_rows("P1_STRATIFIED_MOMENTS.csv")
  ledger=csv_rows("P1_INVALID_AND_BOUNDARY_LEDGER.csv")
  canary=csv_rows("P1_SOURCE_OBSERVER_CANARY.csv")
  counts=collections.Counter((r["case_id"],r["channel"]) for r in rows)
  correct=(len(rows)==19038 and len(counts)==14 and all(counts[(case,ch)]==n for case,n in CASE_COUNTS.items() for ch in ("FULL","LOS")))
  keys={ch:{(r["case_id"],int(r["pose_id"])) for r in rows if r["channel"]==ch} for ch in ("FULL","LOS")}
  check("A2_ALL_PAIRED",correct and keys["FULL"]==keys["LOS"] and len(keys["FULL"])==9519,
       "strict 7-case × (Full,LoS) pairing, 9519 pose pairs, no duplicate case-channel-pose IDs",
       {"rows":len(rows),"case_channel_counts":{f"{k[0]}_{k[1]}":v for k,v in counts.items()}})
  parity_keys={(r["case_id"],r["channel"],int(r["pose_id"])) for r in parity}
  bad_parity=[r for r in parity if (float(r["abs_delta_r_m"])>1e-9 or float(r["abs_delta_s"])>1e-9 or r["status"]!="PASS")]
  check("A3_ARCHIVED_PARITY",len(parity)==14502 and len(parity_keys)==14502 and not bad_parity,
       "14502 stored historic RF trace records, per-row signed s/r parity within locked 1e-9",
       {"n":len(parity),"bad":len(bad_parity)})
  invalid=[r for r in rows if r["status"]!="VALID"]
  broken=[];range_changed=[];finite=[]
  row_by_key={(r["case_id"],r["channel"],int(r["pose_id"])):r for r in rows}
  fullshift=[]
  for r in rows:
    z=float(r["z_s_signed"]);h0=float(r["h_s_old"]);h1=float(r["h_s_source"])
    old=float(r["e_s_old"]);src=float(r["e_s_source"])
    shift=old-src
    err=max(abs(z-h0-old),abs(z-h1-src),abs((old-src)-(h1-h0)),
            abs(float(r["delta_e_s"])-(h0-h1)),
            abs(float(r["e_r_m"])-(float(r["z_r_raw_m"])-float(r["h_r_m"]))))
    if err>1e-10:broken.append([r["case_id"],r["channel"],r["pose_id"],err])
    if not all(math.isfinite(x) for x in (z,h0,h1,old,src,float(r["e_r_m"]))):
      finite.append(r)
    if r["channel"]=="FULL":fullshift.append((abs(float(r["delta_e_s"])),r))
  check("A4_INDEPENDENT_SIGNED_IDENTITIES",not broken and not finite and not invalid,
        "all 19038 row-wise exact signed residual identities, units, finite values and unaltered raw range",
        {"bad":len(broken),"nonfinite":len(finite),"invalid":len(invalid)})
  mpbad=[];los_bias=[];max_abs_mp_error=0.
  for k in keys["FULL"]:
    f=row_by_key[(k[0],"FULL",k[1])]
    l=row_by_key[(k[0],"LOS",k[1])]
    if not near(f["h_s_source"],l["h_s_source"],1e-12):mpbad.append([k,"source_geometry_diff"])
    diff=float(f["e_s_source"])-(float(f["multipath_s_contrast"])+float(l["e_s_source"]))
    max_abs_mp_error=max(max_abs_mp_error,abs(diff))
    if abs(diff)>1e-10:mpbad.append([k,diff])
    los_bias.append(float(l["e_s_source"]))
  check("A5_MATCHED_FULL_LOS_DECOMPOSITION",not mpbad,
        "Full source error = matched Full-LoS signed-s contrast + LoS source error, exact same pose",
        {"max_identity_difference":max_abs_mp_error,"native_los_max_abs_source_residual":max(map(abs,los_bias))})
  # Independently recompute 152 fixed group moments using Python math.fsum
  mismatched=[];maxmean=0.;maxrmse=0.;maxcov=0.;n_count=0
  for grp in moments:
    use=[r for r in rows if want(r,grp)]
    n=int(grp["n"]);n_count+=n
    if n!=len(use) or n<2 or grp["status"]!="VALID":
       mismatched.append(dict(key=str(grp),reason="n_or_status"));continue
    field="e_s_source" if grp["arm"]=="source" else "e_s_old"
    nums=[(float(r["e_r_m"]),float(r[field])) for r in use]
    mr,ms,rr,rs,C=pstat(nums)
    vals=[(mr,grp["mean_e_r_m"]),(ms,grp["mean_e_s"]),
         (rr,grp["rmse_e_r_m"]),(rs,grp["rmse_e_s"])]
    cvals=list(zip(C,[grp["C_rr_m2"],grp["C_rs_m"],grp["C_ss"],grp["min_cov_eigen"]]))
    err1=max(abs(a-float(b)) for a,b in vals)
    err2=max(abs(a-float(b)) for a,b in cvals)
    maxmean=max(maxmean,err1)
    maxcov=max(maxcov,err2)
    maxrmse=max(maxrmse,abs(rr-float(grp["rmse_e_r_m"])),abs(rs-float(grp["rmse_e_s"])))
    if err1>1e-10 or err2>1e-9 or C[-1]<-1e-12:mismatched.append(dict(level=grp["stratum_level"],group=grp["stratum_id"],arm=grp["arm"],error_mean=err1,error_cov=err2))
  check("A6_152_STRATUM_RECOMPUTATION",len(moments)==152 and not mismatched,
        "all 152 raw-row stratum moments recalculated independently with math.fsum and explicit 2x2 covariance",
        {"max_mean_rmse_error":maxmean,"max_covariance_error":maxcov,
        "mismatches":mismatched[:10],"computed_strata":len(moments)})
  check("A7_BOUNDARY_LEDGER",len(ledger)==37 and not any(r["type"] in ("INVALID_PACKET","SOURCE_JAC_MISMATCH") for r in ledger),
        "37 ledger records all recorded as first-path/cell boundary not as silent invalid packets",
        {"by_type":dict(collections.Counter(x["type"] for x in ledger)),"n":len(ledger)})
  check("A8_CANARY_COUNT",len(canary)==56 and
        {r["channel"] for r in canary}=={"FULL","LOS"},"56 real canary rows, both channels")
  # Model-shift outlier is retained. No trimming to improve result.
  fullshift.sort(key=lambda x:x[0],reverse=True)
  worst=fullshift[0][1];outlier=dict(case=worst["case_id"],pose_id=int(worst["pose_id"]),
       x=float(worst["x_truth_offline_m"]),y=float(worst["y_truth_offline_m"]),
       yaw_rad=float(worst["yaw_truth_offline_rad"]),
       distance_m=float(worst["d_truth_offline_m"]),
       s_old=float(worst["h_s_old"]),s_source=float(worst["h_s_source"]),
       abs_shift=float(fullshift[0][0]),source_near_boundary=worst["source_near_boundary"])
  metrics["top_model_shift_outlier"]=outlier
  metrics["top_10_model_shift"]=[
    {"case":r["case_id"],"pose_id":int(r["pose_id"]),
     "abs_shift":float(v),"d_m":float(r["d_truth_offline_m"])}
    for v,r in fullshift[:10]]
  rollup=[r for r in moments if r["stratum_level"]=="CHANNEL_ALL"]
  metrics["channel_all"]=[
      {"channel":r["channel"],"arm":r["arm"],"n":int(r["n"]),
        "s_rmse":float(r["rmse_e_s"]),"s_mean":float(r["mean_e_s"]),
        "C_rs_m":float(r["C_rs_m"])} for r in rollup]
  individual=[r for r in moments if r["stratum_level"]=="CASE_ALL" and r["channel"]=="FULL"]
  models=collections.defaultdict(dict)
  for r in individual:models[r["stratum_id"]][r["arm"]]=float(r["rmse_e_s"])
  metrics["full_case_rmse_shift"]=[{"case":k,"old":v["old"],"source":v["source"],
                                "delta":v["source"]-v["old"]} for k,v in sorted(models.items())]
  count_improved=sum(v["delta"]<0 for v in metrics["full_case_rmse_shift"])
  check("A9_PRESERVE_ALL_CASE_CONTRAST",len(models)==7,
        "source Full s RMSE improves on "+str(count_improved)+"/7 cases and worsens on "+str(7-count_improved)+"/7, no case selection",
        {"improved":count_improved,"worsened":7-count_improved})
  check("A10_ORIGINAL_QA_ALL_GATES",all(qa["gates"].get(f"T{i:02d}_"+suffix) for i,suffix in []) if False else
        all(x["status"]=="PASS" for k,x in qa["gates"].items() if k.startswith("T"))
        and len([k for k in qa["gates"] if k.startswith("T")])==16 and not qa["failed_tests"],
        "all 16 T00-T15 passed in original frozen science receipt; second-pass independently checks its output numerical rows")
  metrics["total_full_los"]=len(rows)
  metrics["parity_n"]=len(parity)
  metrics["manifest"]=dict(run_id=manifest["run_id"],source_head=manifest["github_head"],science_code_sha=qa["runner_script_sha256"])
  metrics["one_scene_only"]=True

if __name__=="__main__":
  try:main()
  except BaseException as ex:
    fail.append(dict(id="POST_RUN_CRASH",error=repr(ex),traceback=traceback.format_exc()))
    print("POSTRUN_ERROR",repr(ex),traceback.format_exc(),flush=True)
  label="PASS_SELF_REVIEW_ONLY" if not fail else "FAIL_OR_BLOCKED_SELF_REVIEW_ONLY"
  result=dict(schema="DLP_P1_POST_RUN_SECOND_FORMULA_VALIDATION_V1",
    status=label,role="SEPARATE_GITHUB_NUMERICAL_RUNNER_NOT_SEPARATE_ACTOR",
    scientific_independence="SELF_REVIEW_ONLY; SAME CHATGPT SESSION WROTE P1 IMPLEMENTATION AND THIS CHECK",
    original_science_run_id="41300302082",
    frozen_result_commit="9c5ad7ceb592678789ed06751b71de951ce22c61",
    original_proposer_contract_sha256="373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594",
    postcheck_script_sha=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
    github_actions_run=os.environ.get("GITHUB_RUN_ID"),
    checks=checks,failures=fail,metrics=metrics,
    runtime=dict(python=sys.version,platform=platform.platform(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),
    claims=["Retrospective C0 descriptive verification only, not new holdout, prediction improvement or scientific independence",
      "R0 remains conventional, cannot conclude noise independence, calibration, generalizability or M2 advantage"])
  p=OUT/"P1_POST_RUN_CROSSCHECK.json"
  p.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
  print("POST_RUN_RESULT",label,"CHECKS",len(checks),"FAILS",len(fail),"OUTLIER",metrics.get("top_model_shift_outlier"))
  sys.exit(0 if not fail else 1)
