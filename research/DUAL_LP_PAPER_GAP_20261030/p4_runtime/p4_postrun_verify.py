#!/usr/bin/env python3
"""P4 Pilot postrun separate-formula numerical verifier and truth-only scorer.

Input: 12 physically matched filter traces from 3 routes x 2 modes x 2 biases.
Exactly 7 4-state arms, every original route time-step, NO native C interpolation.
Recomputes all predicted own-prior states/P, NIS, Joseph update, gate outcome
and signed heading/XY/Bias RMSE independently from original saved arrays.
No P4 filter algorithm receives truth, no new Sionna RT.
"""
from __future__ import annotations
import csv,hashlib,json,math,os,pathlib,platform,sys,time,traceback,zipfile
from collections import Counter,defaultdict
import numpy as np

ROOT=pathlib.Path.cwd()
SOURCE=pathlib.Path(os.environ.get("P4_ROUTES","/tmp/p4_route_inputs"))
OUT=pathlib.Path(os.environ.get("P4_FINAL","/tmp/p4_final"))
OUT.mkdir(parents=True,exist_ok=True)
START=time.monotonic()
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
ARM=["DR4","R4_A13","J4_A13","R4_AB13","R4_ABC13","R4_A_EQ12","R4_ABC_EQ4"]
GRR=.0068578637;RS=.0081
GATES={1:6.6348966010212145,2:9.210340371976184,3:11.344866730144373}
BIAS={"B0":0.,"L2":.20}
CHECK={};FAIL=[];REPORT=[];POOL=[];CONTRAST=[]
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open("rb") as f:
   for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_text("utf-8"))
def read_csv(p):
 with pathlib.Path(p).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def write(p,rows):
 if not rows:
  pathlib.Path(p).write_text("EMPTY\n");return
 fields=list(rows[0])
 with pathlib.Path(p).open("w",newline="",encoding="utf-8") as f:
   d=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
   d.writeheader();d.writerows(rows)
def check(name,passed,values):
 CHECK[name]={"status":"PASS" if passed else "FAIL","values":values}
 print("P4_POSTCHECK",name,CHECK[name]["status"],str(values)[:500],flush=True)
 if not passed:FAIL.append(dict(test=name,measured=values))
def w(a):return (np.asarray(a)+np.pi)%(2*np.pi)-np.pi
def calc_scores(x,P,gt,t,level,stat,packets,components):
  sel=t>=30
  d=x[sel,:3]-gt[sel,:3]
  d[:,2]=w(d[:,2])
  n=int(sel.sum())
  rms=lambda a:math.sqrt(float(np.mean(np.asarray(a)**2)))
  rmse_h=math.degrees(rms(d[:,2]))
  rmse_xy=math.sqrt(float(np.mean(np.sum(d[:,:2]**2,axis=1))))
  rmse_b=math.degrees(rms(x[sel,3]-math.radians(BIAS[level])))
  pp=P[sel,:3,:3]
  pose_nees=np.einsum("ij,ij->i",d,np.linalg.solve(pp,d[:,:,None])[:,:,0])
  heading_nees=d[:,2]**2/P[sel,2,2]
  return dict(n_valid=n,heading_rmse_deg=rmse_h,xy_rmse_m=rmse_xy,
    bias_rmse_deg_s=rmse_b,bias_final_est_dps=math.degrees(float(x[-1,3])),
    heading_nees_mean=float(np.mean(heading_nees)),
    pose_nees_mean=float(np.mean(pose_nees)),
    heading95=float(np.mean(heading_nees<=3.841458820694124)),
    pose95=float(np.mean(pose_nees<=7.814727903251179)),
    offered_rf_packets=int(np.sum(packets)),
    offered_scalar_components=int(np.sum(components)),
    applied_epochs=int(np.count_nonzero(stat=="APPLIED")),
    rejected_epochs=int(np.count_nonzero(stat=="REJECT")),
    predicted_no_rf=int(np.count_nonzero(stat=="PREDICT_NO_RF")),
    skipped_budget_epochs=int(np.count_nonzero(stat=="SKIPPED_BUDGET")),
    failed_epochs=int(np.count_nonzero((stat=="INVALID")|(stat=="INVALID_PREVIOUS"))))
def math_qa(d,route,channel,level):
  import core
  t=d["t_s"];n=len(t)
  x=d["xpost"];P=d["Ppost"];xx=d["xprior"];PP=d["Pprior"]
  H=d["H"];nu=d["innovation"];S=d["S"];K=d["K"];nis=d["nis"]
  st=d["status"];pk=d["packets"];com=d["components"];avail=d["native_available"]
  errors=[];max_pred_x=0;max_pred_P=0;max_obs_x=0;max_obs_P=0;max_nis=0
  if x.shape!=(n,7,4) or P.shape!=(n,7,4,4) or int(avail.sum())!=13:
    return {"errors":[{"shape":[x.shape,P.shape],"available":int(avail.sum())}]}
  initial_x=d["initial_x0"];initial_P=d["initial_P0"]
  for j,arm in enumerate(ARM):
    for k in range(n):
      if k==0:
        expected_x,expected_P=initial_x,initial_P
      else:
        ds=float(d["ds_odom"][k]);da=float(d["dtheta_gyro"][k]);dt=float(d["dt_s"][k])
        Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
        expected_x,expected_P,_,_=core.predict(x[k-1,j],P[k-1,j],ds,da,dt,Q)
      xdiff=np.asarray(expected_x)-xx[k,j];xdiff[2]=w(xdiff[2])
      px=float(np.max(abs(xdiff)));pP=float(np.max(abs(expected_P-PP[k,j])))
      max_pred_x=max(max_pred_x,px);max_pred_P=max(max_pred_P,pP)
      if max(px,pP)>1e-9:errors.append((arm,k,"OWN_PRIOR_REPLAY",px,pP))
      status=str(st[k,j]);dim=int(com[k,j]);packet_n=int(pk[k,j])
      if status in ("APPLIED","REJECT"):
        if not 1<=dim<=3 or packet_n<1:errors.append((arm,k,"BAD_DOF_OR_PACKET_COUNT"))
        R=np.diag([GRR,RS]) if arm=="J4_A13" else np.eye(dim)*GRR
        hh=H[k,j,:dim,:];vv=nu[k,j,:dim]
        mat=hh@PP[k,j]@hh.T+R
        gain=PP[k,j]@hh.T@np.linalg.inv(mat)
        si=float(vv@np.linalg.solve(mat,vv))
        max_nis=max(max_nis,abs(si-nis[k,j]))
        if status!=("APPLIED" if si<=GATES[dim] else "REJECT"):
          errors.append((arm,k,"GATE_DOF_WRONG",si,status))
        if status=="APPLIED":
          est=xx[k,j]+gain@vv;est[2]=w(est[2])
          Jm=np.eye(4)-gain@hh
          cov=Jm@PP[k,j]@Jm.T+gain@R@gain.T
        else:
          est=xx[k,j];cov=PP[k,j]
        ed=est-x[k,j];ed[2]=w(ed[2])
        de=float(np.max(abs(ed)));dp=float(np.max(abs(cov-P[k,j])))
        max_obs_x=max(max_obs_x,de);max_obs_P=max(max_obs_P,dp)
        if (max(de,dp,abs(si-nis[k,j]))>1e-9 or
            np.max(abs(mat-S[k,j,:dim,:dim]))>1e-9 or
            np.max(abs(gain-K[k,j,:,:dim]))>1e-9):
            errors.append((arm,k,"JOSEPH_OR_NIS_MISMATCH",de,dp))
      else:
        if status not in ("DR_ONLY","PREDICT_NO_RF","SKIPPED_BUDGET"):
          errors.append((arm,k,"UNEXPECTED_NO_RF_STATUS",status))
        if packet_n or dim or abs(x[k,j]-xx[k,j]).max()>1e-10 or abs(P[k,j]-PP[k,j]).max()>1e-10:
          errors.append((arm,k,"UNRECORDED_UPDATES"))
      if not np.isfinite(P[k,j]).all() or np.linalg.eigvalsh(P[k,j]).min()<=0:
        errors.append((arm,k,"NON_POSITIVE_COV"))
  return dict(error_count=len(errors),errors=errors[:15],max_prior_state=max_pred_x,
      max_prior_P=max_pred_P,max_joseph_state=max_obs_x,max_joseph_P=max_obs_P,max_NIS=max_nis)
def verify():
  sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
  inp=J(P1/"P1_INPUT_LOCK.json")
  truth={}
  for route in ("R2","R4","R5"):
    p=next(z for z in inp["base_assets"] if z["kind"]=="TIMELINE_TNONE" and
           "timeline_"+route+"_" in z["path"])
    rr=read_csv(ROOT/p["path"])
    truth[route]=dict(t=np.array([float(x["t_s"]) for x in rr]),
      x=np.array([[float(x["x"]),float(x["y"]),math.radians(float(x["yaw_body_deg"]))] for x in rr]))
  maxprior=0.;maxposterior=0.;mathfails=[];allkeys=set();trace_files=[]
  for route in ("R2","R4","R5"):
    folder=SOURCE/route
    receipt=J(folder/"P4_ROUTE_RECEIPT.json")
    if receipt["status"]!="PASS" or len(receipt["tracks"])!=4 or receipt["metrics_n"]!=28:
      FAIL.append(dict(test="ROUTE_INCOMPLETE",route=route,receipt=receipt.get("status")))
      continue
    for track in receipt["tracks"]:
      name=track["trace"];file=folder/"traces"/name
      if not file.exists() or sha(file)!=track["sha256"] or file.stat().st_size!=track["bytes"]:
        FAIL.append(dict(test="TRACE_HASH_BAD",file=name));continue
      with np.load(file,allow_pickle=False) as raw:
        data={x:raw[x].copy() for x in raw.files}
      mode=data["channel"].item();bias=data["bias"].item()
      if mode!=track["channel"] or bias!=track["level"] or data["route"].item()!=route:
        FAIL.append(dict(test="TRACE_KEY_BAD",file=name));continue
      if data["arm_names"].tolist()!=ARM:
        FAIL.append(dict(test="ARM_SET_CHANGED",file=name));continue
      if not np.allclose(data["t_s"],truth[route]["t"],atol=1e-9,rtol=0):
        FAIL.append(dict(test="TIMELINE_DIFFERENT",file=name));continue
      key=(route,mode,bias)
      if key in allkeys:FAIL.append(dict(test="DUPLICATE_TRACE",key=key));continue
      allkeys.add(key);trace_files.append((file,track))
      checkmath=math_qa(data,route,mode,bias)
      maxprior=max(maxprior,checkmath.get("max_prior_state",0))
      maxposterior=max(maxposterior,checkmath.get("max_joseph_P",0))
      if checkmath.get("error_count",1)>0:
        mathfails.append(dict(key=key,errors=checkmath.get("errors")))
      for j,arm in enumerate(ARM):
        row=dict(route=route,channel=mode,bias=bias,arm=arm,
              source_trace_sha256=track["sha256"],
              native_C_rf_39_pose_only=True,
              equal_resource_packet_policy="A12 vs ABC4 different cadence, same scalar count",
              original_c0_simulated_scene_n=1,hardware_clock_sync_proven=False,
              **calc_scores(data["xpost"][:,j],data["Ppost"][:,j],truth[route]["x"],
                            data["t_s"],bias,data["status"][:,j],data["packets"][:,j],data["components"][:,j]))
        REPORT.append(row)
  check("V11_FILTER_QA",len(allkeys)==12 and not FAIL and not mathfails,
        {"trace_n":len(allkeys),"full_3route_2mode_2bias":True,
         "prior_max":maxprior,"Joseph_max":maxposterior,
         "failures":(FAIL+mathfails)[:6]})
  original_rows=[]
  for route in ("R2","R4","R5"):
    rr=read_csv(SOURCE/route/"P4_ROUTE_7ARM_METRICS.csv")
    original_rows+=rr
  bykey={(r["route"],r["channel"],r["bias"],r["arm"]):r for r in original_rows}
  diffs=[];case_set=set()
  for r in REPORT:
    key=(r["route"],r["channel"],r["bias"],r["arm"]);case_set.add(key)
    old=bykey.get(key)
    if not old:diffs.append([key,"MISSING"]);continue
    for field in ("heading_rmse_deg","xy_rmse_m","bias_rmse_deg_s","heading95","pose95",
                  "heading_nees_mean","pose_nees_mean","offered_rf_packets","offered_scalar_components"):
      if abs(float(old[field])-float(r[field]))>1e-9:
        diffs.append([key,field,old[field],r[field]])
  check("V12_SCORING",len(case_set)==84 and not diffs,
        {"n":len(REPORT),"strata":len(case_set),"max_differences":diffs[:6]})
  groups=defaultdict(list)
  for r in REPORT:groups[(r["channel"],r["bias"],r["arm"])].append(r)
  for (channel,bias,arm),rr in sorted(groups.items()):
    n=sum(int(r["n_valid"]) for r in rr)
    pooled=lambda k:math.sqrt(math.fsum(r["n_valid"]*r[k]**2 for r in rr)/n)
    weighted=lambda k:math.fsum(r["n_valid"]*r[k] for r in rr)/n
    POOL.append(dict(channel=channel,bias=bias,arm=arm,
      n_eval=n,route_count=len(rr),independent_scene_count=1,
      heading_rmse_deg=pooled("heading_rmse_deg"),
      xy_rmse_m=pooled("xy_rmse_m"),
      bias_rmse_deg_s=pooled("bias_rmse_deg_s"),
      heading95=weighted("heading95"),pose95=weighted("pose95"),
      offered_rf_packets=sum(r["offered_rf_packets"] for r in rr),
      offered_scalar_components=sum(r["offered_scalar_components"] for r in rr),
      accepted_epochs=sum(r["applied_epochs"] for r in rr),
      rejected_epochs=sum(r["rejected_epochs"] for r in rr),
      note="Single C0 simulation, 13 physical RF epochs/route, B0 or positive L2 seed0"))
  by={(r["route"],r["channel"],r["bias"],r["arm"]):r for r in REPORT}
  for route,mode,bias in sorted({(r["route"],r["channel"],r["bias"]) for r in REPORT}):
    primary=by[(route,mode,bias,"R4_A13")]
    equal=by[(route,mode,bias,"R4_A_EQ12")]
    for target in ("R4_AB13","R4_ABC13","J4_A13","R4_ABC_EQ4"):
      ref=equal if target=="R4_ABC_EQ4" else primary
      tgt=by[(route,mode,bias,target)]
      CONTRAST.append(dict(route=route,channel=mode,bias=bias,baseline=ref["arm"],target=target,
        heading_rmse_delta_deg=tgt["heading_rmse_deg"]-ref["heading_rmse_deg"],
        xy_rmse_delta_m=tgt["xy_rmse_m"]-ref["xy_rmse_m"],
        baseline_packets=ref["offered_rf_packets"],target_packets=tgt["offered_rf_packets"],
        equivalent_packet_count=ref["offered_rf_packets"]==tgt["offered_rf_packets"],
        note="Only retrospective sparse model/no hardware clock; budget/cadence differs by policy"))
  # Independent per-epoch resource ledger of exact 13/39/12/12 per route.
  budget_expected={"DR4":0,"R4_A13":13,"J4_A13":13,"R4_AB13":26,
                   "R4_ABC13":39,"R4_A_EQ12":12,"R4_ABC_EQ4":12}
  issue=[]
  for r in REPORT:
    if r["offered_rf_packets"]!=budget_expected[r["arm"]]:
      issue.append([r["route"],r["channel"],r["bias"],r["arm"],r["offered_rf_packets"]])
  check("V09_RESOURCE",not issue and len(REPORT)==84,{"budget_errors":issue[:10]})
  check("V13_CLAIMS",len(POOL)==28 and len(CONTRAST)==48 and all(x["n_eval"]==2686 for x in POOL),
    {"pooled_rows":len(POOL),"contrasts":len(CONTRAST),"single_scene":1,"missing_full_native_C":3097})
  write(OUT/"P4_84_CASE_METRICS.csv",REPORT)
  write(OUT/"P4_28_POOLED_METRICS.csv",POOL)
  write(OUT/"P4_48_PAIRED_CONTRASTS.csv",CONTRAST)
  archive=OUT/"P4_ALL_12_FULL_TIMELINE_7ARM_NATIVE_SPARSE_TRACES.zip"
  with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
    for file,track in trace_files:
      z.write(file,arcname="traces/"+file.name)
  check("V14_EVIDENCE_ARCHIVE",len(trace_files)==12 and
        zipfile.ZipFile(archive).testzip() is None,
        {"archive_sha":sha(archive),"archive_bytes":archive.stat().st_size,"files":len(trace_files)})

if __name__=="__main__":
 try:verify()
 except Exception as exc:
  FAIL.append(dict(test="POSTRUN_FATAL",error=repr(exc),traceback=traceback.format_exc()))
  print("P4_VERIFY_FATAL",repr(exc),traceback.format_exc(),flush=True)
 status="PASS_39_NATIVE_SPARSE_P4" if not FAIL and CHECK and all(x["status"]=="PASS" for x in CHECK.values()) else "FAIL_OR_BLOCKED"
 result=dict(schema="DLP_P4_SPARSE_THREE_ANCHOR_4STATE_POSTRUN_VERIFICATION_V1",
   status=status,checks=CHECK,failures=FAIL,score_rows=len(REPORT),
   pooled_rows=len(POOL),contrasts=len(CONTRAST),n_real_native_C_epochs=39,
   n_missing_full_C_native_epochs=3097,full_P4="BLOCKED_MISSING_NATIVE_C_RF",
   actor="same ChatGPT author, independent arithmetic verification on separate Linux runner; NOT independent human reviewer",
   code_sha256=sha(__file__),github_run=os.environ.get("GITHUB_RUN_ID"),
   runtime_sec=time.monotonic()-START,python=sys.version,numpy=np.__version__,
   scope="one previously seen simulated corridor, no hardware sync, no new RT and no P4 Full claim",
   original_P3_C_native_zip_sha256="f16c91872993f19341a9cb791c4872c9d13567b715596e9ac4dd085d2fe2c5de",
   raw_trace_zip_sha256=sha(OUT/"P4_ALL_12_FULL_TIMELINE_7ARM_NATIVE_SPARSE_TRACES.zip")
       if (OUT/"P4_ALL_12_FULL_TIMELINE_7ARM_NATIVE_SPARSE_TRACES.zip").is_file() else None)
 (OUT/"P4_POSTRUN_QA.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
 print("P4_POSTRUN_FINAL",status,"scores",len(REPORT),"pooled",len(POOL),
       "errors",len(FAIL),"gates",len(CHECK),flush=True)
 sys.exit(0 if status.startswith("PASS") else 1)
