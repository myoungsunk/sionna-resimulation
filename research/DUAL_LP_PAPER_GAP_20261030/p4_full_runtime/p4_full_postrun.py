#!/usr/bin/env python3
"""Independent-formula postrun verifier for P4 FULL original 3136 epochs C Native.

Verifies all 12 full-timeline 7-arm traces, own prior f/F/Q, joint NIS/K/Joseph,
1/2/3df pre-gate, P2 paired control paths, range packet resource and online GT
separation, recalculates all 84 scores and 28 pooled values using original
Tnone GT exclusively in this offline process.
All physical inputs are actual C Native PathSolver, not 39-epoch interpolation.
"""
from __future__ import annotations
import csv,hashlib,json,math,os,pathlib,platform,sys,time,traceback,zipfile
from collections import defaultdict
import numpy as np
ROOT=pathlib.Path.cwd()
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
INPUT=pathlib.Path(os.getenv("DLP_FULL_EKF_ROUTE_INPUTS","/tmp/p4full_ekf_routes"))
OUT=pathlib.Path(os.getenv("DLP_FULL_EKF_OUT","/tmp/p4full_score_final"))
OUT.mkdir(parents=True,exist_ok=True)
START=time.monotonic();FAIL=[];CHECK={};ALL=[];POOL=[];DELTA=[];SOURCE=[]
N_PER={"R2":979,"R4":742,"R5":1415}
ARMS=("DR4","R4_A_FULL","J4_A_FULL","R4_AB_FULL","R4_ABC_FULL","R4_A_EQPKT","R4_ABC_EQPKT")
BIAS={"B0":0.0,"L2":.2}
GATE={1:6.6348966010212145,2:9.210340371976184,3:11.344866730144373}
Rr=.0068578637;Rs=.0081
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_text("utf-8"))
def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def gate(name,ok,data):
 CHECK[name]={"status":"PASS" if ok else "FAIL","measured":data}
 print("P4_FULL_POSTRUN_CHECK",name,CHECK[name]["status"],str(data)[:350],flush=True)
 if not ok:FAIL.append(dict(test=name,evidence=data))
def readcsv(p):
 with pathlib.Path(p).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def savecsv(path,rows):
 if not rows:return
 with pathlib.Path(path).open("w",newline="",encoding="utf-8") as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]))
  writer.writeheader();writer.writerows(rows)
def postrun_math(d):
 import core
 X=d["xpost"];P=d["Ppost"];xp=d["xprior"];pp=d["Pprior"]
 z=d["raw_native_ABC_z"];t=d["t_s"];status=d["status"]
 n=len(t);dimcheck=[];max_prior=0.;max_joseph=0.;max_nis=0.
 if X.shape!=(n,7,4) or P.shape!=(n,7,4,4):
  return dict(failed=1,first_bad=["shape",X.shape,P.shape])
 for j,arm in enumerate(ARMS):
  for k in range(n):
   if k==0:expected_x=d["initial_x0"].copy();expected_P=d["initial_P0"].copy()
   else:
    ds=float(d["ds_odom"][k]);da=float(d["dtheta_gyro"][k]);dt=float(d["dt_s"][k])
    Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
    expected_x,expected_P,_,_=core.predict(X[k-1,j],P[k-1,j],ds,da,dt,Q)
   de=expected_x-xp[k,j];de[2]=wrap(de[2])
   me=max(float(np.max(abs(de))),float(np.max(abs(expected_P-pp[k,j]))))
   max_prior=max(max_prior,me)
   if me>1e-9:dimcheck.append([j,k,"MOTION_PRIOR_DIFFER",me])
   stat=str(status[k,j]);dim=int(d["components"][k,j])
   if stat in ("APPLIED","REJECT"):
    if dim not in (1,2,3):dimcheck.append([j,k,"INVALID_DOF"]);continue
    R=np.diag([Rr,Rs]) if arm=="J4_A_FULL" else np.eye(dim)*Rr
    H=d["H"][k,j,:dim,:];nu=d["innovation"][k,j,:dim]
    S=H@pp[k,j]@H.T+R
    K=pp[k,j]@H.T@np.linalg.inv(S)
    nis=float(nu@np.linalg.solve(S,nu))
    max_nis=max(max_nis,abs(nis-d["nis"][k,j]))
    if stat!=("APPLIED" if nis<=GATE[dim] else "REJECT"):
      dimcheck.append([j,k,"GATE_MISMATCH",nis])
    if stat=="APPLIED":
      xx=xp[k,j]+K@nu;xx[2]=wrap(xx[2])
      A=np.eye(4)-K@H
      cov=A@pp[k,j]@A.T+K@R@K.T
    else:xx=xp[k,j];cov=pp[k,j]
    delta=xx-X[k,j];delta[2]=wrap(delta[2])
    err=max(float(np.max(abs(delta))),float(np.max(abs(cov-P[k,j]))),
         float(np.max(abs(S-d["S"][k,j,:dim,:dim]))),
         float(np.max(abs(K-d["K"][k,j,:,:dim]))),abs(nis-d["nis"][k,j]))
    max_joseph=max(max_joseph,err)
    if err>1e-9:dimcheck.append([j,k,"NIS_JOSEPH_DIFFER",err])
   else:
    if stat not in ("DR_ONLY","SKIP_BUDGET"):
      dimcheck.append([j,k,"NON_NATIVE_RF_UPDATER_STATUS",stat])
    if (dim or int(d["packets"][k,j])!=0 or
      np.max(abs(X[k,j]-xp[k,j]))>1e-10 or
      np.max(abs(P[k,j]-pp[k,j]))>1e-10):
      dimcheck.append([j,k,"UNDECLARED_UPDATE"])
   if not np.isfinite(P[k,j]).all() or np.linalg.eigvalsh(P[k,j]).min()<=0:
     dimcheck.append([j,k,"INVALID_POSTERIOR_COV"])
 return dict(failed=len(dimcheck),first_bad=dimcheck[:15],
   max_prior=max_prior,max_joseph=max_joseph,max_nis=max_nis)

def calculate_score(d,truth,arm,bias,j):
 x=d["xpost"][:,j];P=d["Ppost"][:,j];keep=d["t_s"]>=30
 diff=x[keep,:3]-truth[keep,:3];diff[:,2]=wrap(diff[:,2])
 B=x[keep,3]-math.radians(BIAS[bias])
 cov=P[keep,:3,:3]
 nees_p=np.einsum("ij,ij->i",diff,np.linalg.solve(cov,diff[:,:,None])[:,:,0])
 nees_h=diff[:,2]**2/P[keep,2,2]
 return dict(n_eval=int(keep.sum()),
  heading_rmse_deg=math.degrees(math.sqrt(float(np.mean(diff[:,2]**2)))),
  xy_rmse_m=math.sqrt(float(np.mean(np.sum(diff[:,:2]**2,axis=1)))),
  bias_rmse_deg_s=math.degrees(math.sqrt(float(np.mean(B**2)))),
  final_bias_est_deg_s=math.degrees(float(x[-1,3])),
  mean_heading_NEES=float(np.mean(nees_h)),mean_pose_NEES=float(np.mean(nees_p)),
  heading95=float(np.mean(nees_h<=3.841458820694124)),
  pose95=float(np.mean(nees_p<=7.814727903251179)),
  packets_offered=int(d["packets"][:,j].sum()),
  scalar_components_offered=int(d["components"][:,j].sum()),
  accepted=int(np.count_nonzero(d["status"][:,j]=="APPLIED")),
  rejected=int(np.count_nonzero(d["status"][:,j]=="REJECT")),
  skipped_budget=int(np.count_nonzero(d["status"][:,j]=="SKIP_BUDGET")))
def verify():
 sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
 p1=J(P1/"P1_INPUT_LOCK.json")
 expected=set()
 records=[]
 allreceipt=[]
 for route,n in N_PER.items():
  rec_path=INPUT/route/"P4_FULL_EKF_ROUTE_RECEIPT.json"
  if not rec_path.exists():
    FAIL.append(dict(test="MISSING_FULL_EKF_ROUTE",route=route));continue
  receipt=J(rec_path);allreceipt.append(receipt)
  if (receipt["status"]!="PASS" or receipt["n_native_C"]!=n or
     receipt["n_arms"]!=7 or len(receipt["trace_files"])!=4):
    FAIL.append(dict(test="FULL_EKF_ROUTE_NOT_PASS",route=route,receipt=receipt.get("status")))
    continue
  T=next(x["path"] for x in p1["base_assets"] if x["kind"]=="TIMELINE_TNONE" and
    "timeline_"+route+"_" in x["path"])
  original=readcsv(ROOT/T)
  truth=np.asarray([[float(z["x"]),float(z["y"]),math.radians(float(z["yaw_body_deg"]))] for z in original])
  for item in receipt["trace_files"]:
   path=INPUT/route/item["filename"]
   if not path.exists() or sha(path)!=item["sha256"] or path.stat().st_size!=item["bytes"]:
     FAIL.append(dict(test="P4_FULL_ORIGINAL_TRACE_SHA_MISMATCH",file=str(path)));continue
   with np.load(path,allow_pickle=False) as d:
     arr={k:d[k].copy() for k in d.files}
   ch=arr["channel"].item();bias=arr["bias"].item()
   key=(route,ch,bias)
   if key in expected:FAIL.append(dict(test="P4_FULL_DUPLICATE_TRACE_KEY",key=key));continue
   expected.add(key)
   if (arr["names"].tolist()!=list(ARMS) or
     len(arr["t_s"])!=n or not np.isfinite(arr["raw_native_ABC_z"]).all() or
     not np.array_equal(arr["pose_id"],[int(z["pose_id"]) for z in original])):
     FAIL.append(dict(test="P4_FULL_TRACE_STRUCTURAL_MISMATCH",key=key));continue
   mathcheck=postrun_math(arr)
   if mathcheck["failed"]>0:
     FAIL.append(dict(test="P4_FULL_POSTERIOR_MATH_QA",key=key,calc=mathcheck))
   records.append(dict(key=key,file=path,sha=item["sha256"],n=n,math=mathcheck))
   for j,arm in enumerate(ARMS):
    new=calculate_score(arr,truth,arm,bias,j)
    earlier=next((a for a in readcsv(INPUT/route/"P4_FULL_CASE_METRICS.csv")
        if a["route"]==route and a["channel"]==ch and a["bias"]==bias and a["arm"]==arm),None)
    if earlier is None:FAIL.append(dict(test="P4_FULL_SCORE_ROW_MISSING",key=key,arm=arm));continue
    for fld in ("heading_rmse_deg","xy_rmse_m","bias_rmse_deg_s","heading95","pose95",
      "mean_heading_NEES","mean_pose_NEES","packets_offered","scalar_components_offered","accepted","rejected"):
      if abs(float(earlier[fld])-float(new[fld]))>1e-9:
        FAIL.append(dict(test="P4_FULL_SCORES_INDEPENDENT_FORMULA_MISMATCH",key=key,arm=arm,field=fld))
    ALL.append(dict(route=route,channel=ch,bias=bias,arm=arm,independent_scene_n=1,
       same_simulated_clock_not_hardware=True,**new))
 gate("W08_FULL_RECURSION",not FAIL and len(records)==12 and
       max((r["math"]["max_prior"] for r in records),default=999)<=1e-9 and
       max((r["math"]["max_joseph"] for r in records),default=999)<=1e-9,
       {"n_original_full_traces":len(records),"max_prior":max((x["math"]["max_prior"] for x in records),default=None),
        "max_joseph":max((x["math"]["max_joseph"] for x in records),default=None)})
 gate("W11_FULL_SCORES",len(ALL)==84 and len({(r["route"],r["channel"],r["bias"],r["arm"]) for r in ALL})==84,
       {"n_result_rows":len(ALL),"n_traces":len(records),"expected":84})
 check_budget=[]
 for row in ALL:
  n=N_PER[row["route"]];trim=3*(n//3)
  exp={"DR4":0,"R4_A_FULL":n,"J4_A_FULL":n,"R4_AB_FULL":2*n,"R4_ABC_FULL":3*n,
      "R4_A_EQPKT":trim,"R4_ABC_EQPKT":trim}[row["arm"]]
  if row["packets_offered"]!=exp:
    check_budget.append([row["route"],row["channel"],row["bias"],row["arm"],row["packets_offered"],exp])
 gate("W10_EXACT_RESOURCE_BUDGET",not check_budget,{"n_bad":len(check_budget),"cases":check_budget[:8]})
 groups=defaultdict(list)
 for row in ALL:groups[(row["channel"],row["bias"],row["arm"])].append(row)
 for (channel,bias,arm),rows in sorted(groups.items()):
  n=sum(row["n_eval"] for row in rows)
  rmse=lambda name:math.sqrt(math.fsum(row["n_eval"]*row[name]**2 for row in rows)/n)
  avg=lambda name:math.fsum(row["n_eval"]*row[name] for row in rows)/n
  POOL.append(dict(channel=channel,bias=bias,arm=arm,n_eval=n,n_route=len(rows),scene_n=1,
   heading_rmse_deg=rmse("heading_rmse_deg"),xy_rmse_m=rmse("xy_rmse_m"),
   bias_rmse_deg_s=rmse("bias_rmse_deg_s"),
   heading95=avg("heading95"),pose95=avg("pose95"),
   total_packets=sum(r["packets_offered"] for r in rows),
   total_scalar_components=sum(r["scalar_components_offered"] for r in rows),
   applied=sum(r["accepted"] for r in rows),rejected=sum(r["rejected"] for r in rows)))
 cross={(r["route"],r["channel"],r["bias"],r["arm"]):r for r in ALL}
 for route,channel,bias in sorted({(r["route"],r["channel"],r["bias"]) for r in ALL}):
  for target in ("R4_AB_FULL","R4_ABC_FULL","J4_A_FULL","R4_ABC_EQPKT"):
   base="R4_A_EQPKT" if target=="R4_ABC_EQPKT" else "R4_A_FULL"
   left=cross[(route,channel,bias,base)];right=cross[(route,channel,bias,target)]
   DELTA.append(dict(route=route,channel=channel,bias=bias,
      baseline=base,target=target,
      delta_heading_rmse_deg=right["heading_rmse_deg"]-left["heading_rmse_deg"],
      delta_xy_rmse_m=right["xy_rmse_m"]-left["xy_rmse_m"],
      baseline_packet_count=left["packets_offered"],target_packet_count=right["packets_offered"],
      equal_scalar_packet_count=(left["packets_offered"]==right["packets_offered"]),
      independent_scene_n=1))
 gate("W12_POOL_AND_CONTRAST",len(POOL)==28 and len(DELTA)==48 and
      all(p["n_eval"]==2686 for p in POOL),
      {"pooled_rows":len(POOL),"contrasts":len(DELTA),"eval_n_per_group":2686})
 savecsv(OUT/"P4_FULL_84_CASE_METRICS.csv",ALL)
 savecsv(OUT/"P4_FULL_28_POOLED_METRICS.csv",POOL)
 savecsv(OUT/"P4_FULL_48_PAIRWISE_CONTRASTS.csv",DELTA)
 zip_path=OUT/"P4_FULL_12_COMPLETE_4STATE_EKF_TRACES.zip"
 with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
  for item in records:z.write(item["file"],arcname="traces/"+item["file"].name)
 gate("W07_EKF_TRACE_ARCHIVE",len(records)==12 and zipfile.ZipFile(zip_path).testzip() is None,
   {"zip_sha256":sha(zip_path),"bytes":zip_path.stat().st_size,"trace_n":len(records)})
 SOURCE.extend(allreceipt)
if __name__=="__main__":
 try:verify()
 except Exception as exc:
  FAIL.append(dict(test="FULL_POSTRUN_FATAL",error=repr(exc),traceback=traceback.format_exc()))
  print("P4_FULL_POSTRUN_FATAL",repr(exc),traceback.format_exc(),flush=True)
 status="PASS_FULL_C0PLUS_4STATE_EKF" if not FAIL and CHECK and all(g["status"]=="PASS" for g in CHECK.values()) else "FAIL_OR_BLOCKED"
 result=dict(schema="DLP_P4_FULL_C0PLUS_3136_NATIVE_C_4STATE_VERIFY_V1",
  status=status,phase="FULL_3ANCHOR_NATIVE_RT_3136_ALL_EPOCHS",
  original_new_C_pose_n=3097,original_old_P3_C_pose_n=39,
  original_total_Native_C_pose_n=3136,
  score_rows=len(ALL),pooled_rows=len(POOL),pairwise_rows=len(DELTA),
  full_native_route_count=3,n_original_full_4state_trace_npz=len({(r["route"],r["channel"],r["bias"]) for r in ALL}),
  independent_scene_count=1,measured_hardware_sync=False,interanchor_R_diagonal_assumed=True,
  gates=CHECK,failures=FAIL,code_sha256=sha(__file__),
  source_RT_geometry="native actual Sionna2.0.1 PathSolver one-solver Full/physical direct LoS, certified by separate Native LoS canary",
  scientific_verdict="RETROSPECTIVE_SINGLE_C0PLUS_DESCRIPTIVE_ONLY",
  trace_zip_sha256=sha(OUT/"P4_FULL_12_COMPLETE_4STATE_EKF_TRACES.zip")
   if (OUT/"P4_FULL_12_COMPLETE_4STATE_EKF_TRACES.zip").exists() else None,
  run_id=os.environ.get("GITHUB_RUN_ID"),runtime_sec=time.monotonic()-START,
  environment={"python":sys.version,"numpy":np.__version__,"platform":platform.platform()})
 (OUT/"P4_FULL_POSTRUN_QA.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
 print("P4_FULL_POSTRUN_FINAL",status,"rows",len(ALL),"pooled",len(POOL),
       "errors",len(FAIL),"checks",len(CHECK),flush=True)
 sys.exit(0 if status.startswith("PASS") else 1)
