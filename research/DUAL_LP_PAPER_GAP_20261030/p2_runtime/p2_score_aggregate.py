#!/usr/bin/env python3
"""DLP P2 post-inference scorer and independent arithmetic QA.

Consumes only immutable saved range-only/joint recursive estimates and the
original archived truth. The inference function receives no truth. Every
case/arm/packet is validated and failures are preserved instead of omitted.
"""
from __future__ import annotations
import csv,datetime,hashlib,io,json,math,os,pathlib,platform,sys,traceback,zipfile
from collections import Counter,defaultdict
import numpy as np
ROOT=pathlib.Path.cwd()
ROUTES=pathlib.Path(os.environ.get("DLP_P2_ROUTES","/tmp/p2_route_bundle"))
OUTPUT=pathlib.Path(os.environ.get("DLP_P2_FINAL","/tmp/p2_aggregate_final"))
ARCH=pathlib.Path(os.environ.get("DLP_RF_ZIP","/tmp/dlp_p2_rf_original.zip"))
CORE_PATH=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
CONTRACT="568ef6b794457f682ae9fd96e30d8a6f072d0283fcfd17aed4dcc2adfb76a48b"
CONFIG="99c4f6303ece8d19b2a30f1217f62c852df3074583dff6c388245a54c555cc43"
TOL="ab385d88538b0f2485fdcf1cceef31262a08a7a5c214751c4dfc6949e6101ae3"
ARCHIVE_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
CHI_POSE95=7.814727903251179
CHI_HEAD95=3.841458820694124
RR=.0068578637;RS=.0081
GATE_R=6.6348966010212145;GATE_J=9.210340371976184
ARM_NAMES=("DR4","R4","J4_SRC")
routes={"R2":(979,829,3),"R4":(742,592,2),"R5":(1415,1265,2)}
BIAS={"B0":0.,"L2":.20}
errors=[];gates={};metrics=[];contrasts=[];summary=[];file_ledger=[];saved_keys=set()
def sha(path):
  h=hashlib.sha256()
  with pathlib.Path(path).open("rb") as f:
    for b in iter(lambda:f.read(1<<20),b""):h.update(b)
  return h.hexdigest()
def h_bytes(blob):return hashlib.sha256(blob).hexdigest()
def js(path):return json.loads(pathlib.Path(path).read_text())
def check(name,ok,note,data=None):
  gates[name]={"status":"PASS" if ok else "FAIL","note":str(note)}
  if data is not None:gates[name]["measured"]=data
  print("P2_AGG_CHECK",name,gates[name]["status"],str(data)[:380],flush=True)
  if not ok:errors.append(dict(test=name,reason=str(note),measured=data))
def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def wr(path,rows,head):
  with pathlib.Path(path).open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=head,extrasaction="ignore");w.writeheader();w.writerows(rows)
def means(x):return math.fsum(float(a) for a in x)/len(x)
def score(trace,ground_truth,t,label):
  X=trace["xpost"];P=trace["Ppost"];sts=trace["status"]
  mask=t>=30.
  valid=mask&np.isfinite(X).all(axis=1)&np.isfinite(P).all(axis=(1,2))
  n=int(np.count_nonzero(valid));required=int(mask.sum())
  if n<1:return dict(status="NO_VALID_FRAMES",n_valid=0,n_expected=required)
  e=X[valid,:3]-ground_truth[valid,:3]
  e[:,2]=wrap(e[:,2])
  cov=P[valid,:3,:3]
  min_eig=float(np.linalg.eigvalsh(cov).min())
  if min_eig<=0:raise RuntimeError("EVALUATION_POSE_COV_NONPD")
  pose_nees=np.einsum("ij,ij->i",e,np.linalg.solve(cov,e[:,:,None])[:,:,0])
  hnees=e[:,2]**2/P[valid,2,2]
  true_b=math.radians(BIAS[label])
  bias_error=X[valid,3]-true_b
  accepted=np.count_nonzero(sts=="APPLIED")
  rejected=np.count_nonzero(sts=="REJECT")
  missing=np.count_nonzero(sts=="MISSING")
  invalid=np.count_nonzero((sts=="INVALID")|(sts=="INVALID_PREVIOUS"))
  status="COMPLETE" if n==required and invalid==0 else "INCOMPLETE"
  # Independent pair of formulas for RMSE; validate with fsum for numerical precision.
  xy_sq=np.sum(e[:,:2]**2,axis=1)
  head_sq=e[:,2]**2
  bias_sq=bias_error**2
  heading_rmse=math.degrees(math.sqrt(float(np.mean(head_sq))))
  xy_rmse=math.sqrt(float(np.mean(xy_sq)))
  bb_rmse=math.degrees(math.sqrt(float(np.mean(bias_sq))))
  chk1=math.degrees(math.sqrt(means(head_sq)))
  chk2=math.sqrt(means(xy_sq))
  if abs(heading_rmse-chk1)>1e-10 or abs(xy_rmse-chk2)>1e-10:
      raise RuntimeError("SCORER_INDEPENDENT_RMSE_FORMULA_FAILED")
  # Mean posterior 95%-coverage over time is diagnostic, not an iid CI.
  ret=dict(status=status,n_expected=required,n_valid=n,
    heading_rmse_deg=heading_rmse,xy_rmse_m=xy_rmse,
    bias_rmse_deg_s=bb_rmse,
    bias_final_deg_s=math.degrees(float(X[np.flatnonzero(valid)[-1],3])),
    bias_final_sigma_deg_s=math.degrees(math.sqrt(float(P[np.flatnonzero(valid)[-1],3,3]))),
    heading_mean_error_deg=math.degrees(float(np.mean(e[:,2]))),
    heading_nees_mean=float(np.mean(hnees)),
    pose_nees_mean=float(np.mean(pose_nees)),
    heading_95_coverage=float(np.mean(hnees<=CHI_HEAD95)),
    pose_95_coverage=float(np.mean(pose_nees<=CHI_POSE95)),
    bias_95_coverage=float(np.mean(bias_sq<=CHI_HEAD95*P[valid,3,3])),
    posterior_heading_sigma_rms_deg=math.degrees(math.sqrt(float(np.mean(P[valid,2,2])))),
    cov_min_eig=min_eig,
    total_steps=len(t),steps_applied=int(accepted),
    steps_rejected=int(rejected),steps_missing=int(missing),
    steps_invalid=int(invalid),
    offered_rf_packets=int(len(t)) if trace["method"]!="DR4" else 0,
    measurement_components_per_attempt={"DR4":0,"R4":1,"J4_SRC":2}[trace["method"]],
    attempted_scalar_components=int(len(t)*{"DR4":0,"R4":1,"J4_SRC":2}[trace["method"]]),
    accepted_scalar_components=int(accepted*{"DR4":0,"R4":1,"J4_SRC":2}[trace["method"]]))
  return ret

def audit_prior_math(trace):
  sys.path.insert(0,str(CORE_PATH))
  import core
  xprev=trace["xpost"];Pprev=trace["Ppost"]
  xprior=trace["xprior"];Pprior=trace["Pprior"]
  controls=trace["controls"]
  stats=trace["status"]
  n=len(xprev)
  max_x=0.;max_P=0.;bad=[];math_gate=0
  for k in range(1,n):
    if stats[k] in ("INVALID_PREVIOUS","INVALID"):
      bad.append([k,stats[k]]);continue
    if not np.isfinite(xprev[k-1]).all() or not np.isfinite(Pprev[k-1]).all():
      bad.append([k,"PREVIOUS_NOT_FINITE"]);continue
    ds=float(controls["ds_odom"][k])
    dt=float(controls["dt_s"][k])
    ga=float(controls["dtheta_gyro"][k])
    Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
    x,P,F,G=core.predict(xprev[k-1],Pprev[k-1],ds,ga,dt,Q)
    diff=x-xprior[k];diff[2]=wrap(diff[2])
    max_x=max(max_x,float(np.max(abs(diff))))
    max_P=max(max_P,float(np.max(abs(P-Pprior[k]))))
    if max(abs(diff))>1e-10 or np.max(abs(P-Pprior[k]))>1e-10:
      bad.append([k,"SELF_PRIOR_RECURSION_DIFFER",float(np.max(abs(diff)))])
    math_gate+=1
  return dict(n=math_gate,max_x=max_x,max_P=max_P,bad=bad[:20],bad_n=len(bad))

def audit_measurement_math(trace):
  """Every accepted/rejected step checks NIS, gain, Joseph and gate DOF."""
  method=trace["method"];s=trace["status"]
  if method=="DR4":
    good=(set(s)=={"DR_ONLY"})
    return dict(n=0,max_innovation=0.,max_nis=0.,max_P=0.,max_x=0.,
                invalid=0 if good else len(s),fail=[] if good else ["DR4_STATUS_BAD"])
  R=np.diag([RR]) if method=="R4" else np.diag([RR,RS])
  df=1 if method=="R4" else 2
  gate=GATE_R if method=="R4" else GATE_J
  mN=0.;mP=0.;mx=0.;mS=0.;mK=0.;fails=[];n_ok=0
  for k,stat in enumerate(s):
    if stat not in ("APPLIED","REJECT"):
      fails.append([k,"NON_RECORDABLE",str(stat)])
      continue
    P=trace["Pprior"][k]
    x=trace["xprior"][k]
    H=trace["H"][k,:df,:]
    nu=trace["innovation"][k,:df]
    S=H@P@H.T+R
    K=P@H.T@np.linalg.inv(S)
    ni=float(nu@np.linalg.solve(S,nu))
    mk=trace["K"][k,:,:df]
    mS=max(mS,float(np.max(abs(S-trace["S"][k,:df,:df]))))
    mK=max(mK,float(np.max(abs(K-mk))))
    mN=max(mN,abs(ni-trace["nis"][k]))
    should="APPLIED" if ni<=gate else "REJECT"
    if stat!=should:
      fails.append([k,"WRONG_GATE",stat,should,ni])
    if stat=="APPLIED":
      out=x+K@nu
      out[2]=wrap(out[2])
      A=np.eye(4)-K@H
      cov=A@P@A.T+K@R@K.T
    else:
      out=x
      cov=P
    dx=out-trace["xpost"][k];dx[2]=wrap(dx[2])
    mx=max(mx,float(np.max(abs(dx))))
    mP=max(mP,float(np.max(abs(cov-trace["Ppost"][k]))))
    if max(mP,mx,mN,mS,mK)>1e-9:
      fails.append([k,"MEASUREMENT_MATH_PARITY",mP,mx,mN,mS,mK])
    n_ok+=1
  return dict(n=n_ok,max_nis=mN,max_P=mP,max_x=mx,
              max_S=mS,max_K=mK,invalid=len(fails),fail=fails[:15])

def verify():
  assert sha(ARCH)==ARCHIVE_SHA,"ARCHIVE_REAL_SHA_CHANGED"
  zf=zipfile.ZipFile(ARCH)
  assert zf.testzip() is None
  summary_archive=json.loads(zf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  assert len(summary_archive["per_case"])==14
  index={(d["case"],d["channel"]):d for d in summary_archive["per_case"]}
  out_dir=OUTPUT/"traces";out_dir.mkdir(parents=True,exist_ok=True)
  route_receipts=[];case_record=[];all_trace=[]
  expected_case=set()
  for route,(nframe,evalframe,ncase) in routes.items():
    directory=ROUTES/route
    rec=js(directory/"P2_ROUTE_RECEIPT.json")
    route_receipts.append(rec)
    assert rec["route"]==route and rec["qa_status"]=="PASS" and len(rec["cases"])==ncase*4,route
    assert not rec["n_failed_events"]
    for row in rec["cases"]:
      case=row["case"];ch=row["channel"];level=row["bias_level"]
      key=(case,ch,level)
      assert key not in expected_case,("DUP_CASE",key)
      expected_case.add(key)
      assert nframe==row["n_steps"] and evalframe==row["n_eval"]
      assert row["n_errors"]==0
      path=directory/row["output_file"]
      assert path.is_file() and sha(path)==row["output_sha256"] and path.stat().st_size==row["output_bytes"],"ROUTE_NPZ_SHA_NOT_MATCHED:"+str(path)
      dest=out_dir/path.name
      if dest.exists():raise RuntimeError("DUPLICATE_TRACE_FILENAME")
      dest.write_bytes(path.read_bytes())
      with np.load(path,allow_pickle=False) as d:
        fields=["names","t_s","pose_id","xprior","Pprior","xpost","Ppost","status",
               "H","S","K","h","innovation","nis","ds_odom","dtheta_gyro","dt_s","z_r_s"]
        assert all(x in d.files for x in fields),"MISSING_TRACE_FIELDS"
        trace={x:d[x].copy() for x in fields}
        assert d["case_id"].item()==case and d["channel"].item()==ch and d["bias_level"].item()==level
        assert trace["names"].tolist()==list(ARM_NAMES)
        assert trace["xpost"].shape==(nframe,3,4) and trace["Ppost"].shape==(nframe,3,4,4)
        assert len(set(map(int,trace["pose_id"])))==nframe
        assert int(np.count_nonzero(trace["t_s"]>=30))==evalframe
        assert np.all(np.diff(trace["t_s"])>0)
        assert trace["z_r_s"].shape==(nframe,2) and np.isfinite(trace["z_r_s"]).all()
        control={k:trace[k] for k in ("ds_odom","dtheta_gyro","dt_s")}
      arc=index[(case,ch)]
      raw=zf.read("P2_OUT/"+arc["trace_file"])
      assert h_bytes(raw)==arc["trace_sha256"]
      with np.load(io.BytesIO(raw),allow_pickle=False) as v:
         truth=v["truth_for_offline_scoring_only"].copy()
         t_arc=v["t_s"].copy();ids_arc=v["pose_id"].copy()
         obs=np.column_stack((v["z_r_m"],v["z_s"]))
      assert np.array_equal(ids_arc,trace["pose_id"]) and np.array_equal(t_arc,trace["t_s"])
      assert np.max(abs(obs-trace["z_r_s"]))<1e-12
      all_trace.append((row,trace,truth))
      case_record.append({**row,"verified_sha256":sha(path)})
  check("U00_FROZEN_AND_OUTPUT_SHA",len(route_receipts)==3 and len(case_record)==28,
         "3 full route receipts and all 28 exact original case/channel/bias NPZ SHA and bytes",
         {"n_routes":len(route_receipts),"npz_count":len(case_record)})
  assert len(expected_case)==28
  all_prior=[];all_math=[]
  counts=Counter();statuses=Counter();error_count=0
  route_controls={}
  for row,trace,truth in all_trace:
    case=row["case"];ch=row["channel"];level=row["bias_level"];route=row["route"]
    control_key=(route,level)
    if control_key not in route_controls:
      route_controls[control_key]={k:trace[k].copy() for k in ("ds_odom","dtheta_gyro","dt_s")}
    else:
      for k in ("ds_odom","dtheta_gyro","dt_s"):
        if not np.array_equal(trace[k],route_controls[control_key][k]):
          errors.append(dict(test="U06_PAIRED_CONTROLS",reason="control differing between cases",case=case,key=k))
    for i,method in enumerate(ARM_NAMES):
      subset={k:trace[k][:,i] for k in ("xprior","Pprior","xpost","Ppost","status","H","S","K","h","innovation","nis")}
      subset["method"]=method
      subset["controls"]={k:trace[k] for k in ("ds_odom","dtheta_gyro","dt_s")}
      nres=audit_prior_math(subset)
      mres=audit_measurement_math(subset)
      all_prior.append((case,ch,level,method,nres))
      all_math.append((case,ch,level,method,mres))
      if nres["bad_n"] or mres["invalid"]:
        errors.append(dict(test="U15_FULL_MATH_REPLAY",case=case,ch=ch,level=level,arm=method,prior_bad=nres["bad"][:3],meas_bad=mres["fail"][:3]))
      score1=score(subset,truth,trace["t_s"],level)
      if score1["status"]!="COMPLETE":
        errors.append(dict(test="U12_SCORE_COMPLETENESS",case=case,ch=ch,level=level,arm=method,status=score1["status"],n=score1["n_valid"]))
      metrics.append(dict(case=case,channel=ch,level=level,route=route,arm=method,
           t_ge_30=30,statistical_independent_scenes=1,
           **score1))
      counts[(ch,level,method)]+=score1["n_valid"]
      statuses[(method,"APPLIED")]+=score1.get("steps_applied",0)
      statuses[(method,"REJECT")]+=score1.get("steps_rejected",0)
      statuses[(method,"INVALID")]+=score1.get("steps_invalid",0)
      print("P2_SCORE",case,ch,level,method,
            "heading",round(score1.get("heading_rmse_deg",math.nan),5),
            "xy",round(score1.get("xy_rmse_m",math.nan),5),
            "gate",score1.get("steps_applied"),score1.get("steps_rejected"),flush=True)
  check("U11_FULL_RECURSION_AND_GATE",not any(x.get("test")=="U15_FULL_MATH_REPLAY" for x in errors),
    "Independent from stored outputs all recursive own-prior propagation and scalar/joint NIS/Joseph at every step",
    dict(n_traces=len(all_prior),max_prior_x=max(x[4]["max_x"] for x in all_prior),
       max_prior_P=max(x[4]["max_P"] for x in all_prior),
       max_measurement_P=max(x[4]["max_P"] for x in all_math),
       max_measurement_nis=max(x[4]["max_nis"] for x in all_math)))
  check("U06_CONTROLS_IDENTICAL_PER_ROUTE",not any(x.get("test")=="U06_PAIRED_CONTROLS" for x in errors),
      "B0/L2 inputs exact identity across same-route anchors, mounts and modes")
  expected=12402 # t>=30 per bias all Full and LoS, across 7 cases
  complete_counts=all(counts[(ch,l,arm)]==6201 for ch in ("full","los") for l in BIAS for arm in ARM_NAMES)
  check("U02_ALL_POSE_AND_EVAL",complete_counts and len(metrics)==84,
        "7case*2channels*2bias*3arms, each level/channel 6201 scored frames, no hidden omission",
        dict(n_metrics=len(metrics),counts={str(k):v for k,v in counts.items()}))
  check("U12_SCORE_STANDALONE",not any(x.get("test")=="U12_SCORE_COMPLETENESS" for x in errors),
        "Ground truth scored only after inference output files, finite valid states and positive covariance")
  # Model resource budget fairness: same one RF packet per time for R4 and J4, but different scalar observation dimensions.
  accurate_resource=all(r["measurement_components_per_attempt"]=={"DR4":0,"R4":1,"J4_SRC":2}[r["arm"]]
                     and r["attempted_scalar_components"]==r["total_steps"]*r["measurement_components_per_attempt"]
                     for r in metrics)
  check("U10_RESOURCE_AND_GATE_DIMENSION",accurate_resource,
        "same anchor/RF packet for R4 & J4_SRC, but one vs two scalar components and distinct chi2 gates, not equal information budget")
  # Pair case-level contrasts without pairing timestamps across independent scenes.
  by={(r["case"],r["channel"],r["level"],r["arm"]):r for r in metrics}
  for case,ch,lev in sorted({(r["case"],r["channel"],r["level"]) for r in metrics}):
    r0=by[(case,ch,lev,"DR4")];r1=by[(case,ch,lev,"R4")];r2=by[(case,ch,lev,"J4_SRC")]
    for left,right in ((r0,r1),(r1,r2),(r0,r2)):
      contrasts.append(dict(case=case,channel=ch,level=lev,baseline=left["arm"],target=right["arm"],
         delta_heading_rmse_deg=right["heading_rmse_deg"]-left["heading_rmse_deg"],
         delta_xy_rmse_m=right["xy_rmse_m"]-left["xy_rmse_m"],
         delta_bias_rmse_deg_s=right["bias_rmse_deg_s"]-left["bias_rmse_deg_s"],
         delta_heading95=right["heading_95_coverage"]-left["heading_95_coverage"],
         delta_pose95=right["pose_95_coverage"]-left["pose_95_coverage"],
         note="Retrospective one-C0, seed0 per route; different scalar observation dimensions"))
  # Pooled RMSE rederived from case RMSE squared weighted by valid evaluation steps.
  by_group=defaultdict(list)
  for r in metrics:by_group[(r["channel"],r["level"],r["arm"])].append(r)
  for (channel,level,arm),data in sorted(by_group.items()):
    n=sum(r["n_valid"] for r in data)
    squared=lambda name:math.sqrt(math.fsum(r["n_valid"]*r[name]**2 for r in data)/n)
    weighted=lambda name:math.fsum(r["n_valid"]*r[name] for r in data)/n
    summary.append(dict(channel=channel,level=level,arm=arm,
       n_eval=n,case_n=len(data),independent_scene_n=1,sensor_seed_n=1,
       pooled_heading_rmse_deg=squared("heading_rmse_deg"),
       pooled_xy_rmse_m=squared("xy_rmse_m"),
       pooled_bias_rmse_deg_s=squared("bias_rmse_deg_s"),
       weighted_heading95=weighted("heading_95_coverage"),
       weighted_pose95=weighted("pose_95_coverage"),
       offered_rf_packets=sum(r["offered_rf_packets"] for r in data),
       accepted_updates=sum(r["steps_applied"] for r in data),
       rejected_updates=sum(r["steps_rejected"] for r in data),
       attempted_scalar_components=sum(r["attempted_scalar_components"] for r in data),
       accepted_scalar_components=sum(r["accepted_scalar_components"] for r in data)))
  check("U15_CONTRAST_COVERAGE",len(contrasts)==28*3 and len(summary)==12,
        "All 28 case/mode/bias triples compared against three methods, all 12 pooled channels/levels/methods",
        dict(contrasts=len(contrasts),summary_rows=len(summary)))
  # Preserve evidence before validating failed cases.
  wr(OUTPUT/"P2_CASE_METRICS.csv",metrics,list(metrics[0]))
  wr(OUTPUT/"P2_PAIRWISE_CONTRASTS.csv",contrasts,list(contrasts[0]))
  wr(OUTPUT/"P2_POOLED_METRICS.csv",summary,list(summary[0]))
  wr(OUTPUT/"P2_TRACE_LEDGER.csv",case_record,list(case_record[0]))
  wr(OUTPUT/"P2_FAILURE_LEDGER.csv",errors,
     ["test","reason","case","ch","level","arm","prior_bad","meas_bad","status","n","key"])
  check("U14_SCIENTIFIC_SCOPE",True,
        "Only historical C0 single scene; no inference on multiple independent scenes, M2 or newly generated RF")
  zf.close()

if __name__=="__main__":
  OUTPUT.mkdir(parents=True,exist_ok=True)
  try:verify()
  except BaseException as exc:
    errors.append(dict(test="AGGREGATE_FATAL",reason=repr(exc),traceback=traceback.format_exc()))
    print("P2_AGG_FATAL",repr(exc),traceback.format_exc(),flush=True)
  technical="PASS" if not errors and len(metrics)==84 and len(summary)==12 else "FAIL_OR_BLOCKED"
  result=dict(schema="DLP_P2_POSTRUN_SEPARATE_SCORER_AND_MATH_QA_V1",status=technical,
      independent_numerical_code_not_human_review=True,
      actor_identity_boundary="Same ChatGPT author; separate GitHub Actions runner, not an external human auditor.",
      contract_id="DLP-EKF-GAPS-001/P2-V1",contract_sha256=CONTRACT,
      config_sha256=CONFIG,tolerance_sha256=TOL,
      prior_audit_receipt_sha256="40dfe491422b61af81d09bb0bd3ded2dd9d8767be3549d25e892f0b64c0cbee7",
      original_rf_archive_sha256=ARCHIVE_SHA,
      route_n=3,case_n=7,mode_n=2,bias_n=2,arm_n=3,
      score_rows=len(metrics),contrast_rows=len(contrasts),pooled_rows=len(summary),
      gates=gates,failures=errors,scene_n=1,sensor_seed=0,
      scientific_verdict="C0_RETROSPECTIVE_DESCRIPTIVE_ONLY_NOT_NEW_HOLDOUT",
      claimed_features=["real original frozen C0 exact RF 7 case-pairs",
        "4state matched prior, process Q and sensor controls",
        "DR4/R4/J4 SourceFFD full self-gated recursion, 0-second start",
        "recorded 1 vs 2 measurement scalar components, not equivalent RF information",
        "All failure cases retained, GT used only in separate scorer"],
      forbidden_claims=["7 independent RF scenes","filter advantage in unseen environments",
        "hardware calibration","Gaussian likelihood proved","time/pose sample IID CI",
        "spatiotemporal 3D covariance or selected M2"],
      code_sha256=sha(__file__),github_run=os.environ.get("GITHUB_RUN_ID"),
      runtime={"python":sys.version,"numpy":np.__version__,"platform":platform.platform(),
               "utc":datetime.datetime.now(datetime.timezone.utc).isoformat()})
  (OUTPUT/"P2_POSTRUN_QA.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
  print("P2_AGGREGATE_FINAL",technical,"METRICS",len(metrics),
        "CONTRASTS",len(contrasts),"POOLED",len(summary),"FAILS",len(errors),flush=True)
  sys.exit(0 if technical=="PASS" else 1)
