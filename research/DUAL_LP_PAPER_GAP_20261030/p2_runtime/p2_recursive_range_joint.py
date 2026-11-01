#!/usr/bin/env python3
"""DLP P2 phase-frozen original C0 4state recursive comparison (R2/R4/R5).

DR4: 4state dead-reckoning
R4:  4state 1-anchor scalar range update (1D chi2 gate)
J4_SRC: 4state 1-anchor joint [raw r, signed s] update with pinned SourceFFD
All from exact same original frozen RF packet; same motion and initial state.

This script does inference only. Actual trajectory truth is passed solely into
the fixed historical sensor-v2 *input simulation*, NOT the runtime EKF.
Scoring is performed only later in p2_score_aggregate.py on frozen traces.

Every filter evolves its OWN posterior across t=0...end; invalid/rejected
updates are recorded. No new RT/FFD, training, learned R, M2 or hidden rescue.
"""
from __future__ import annotations
import argparse,base64,csv,datetime,hashlib,io,json,math,os,pathlib,platform,subprocess,sys,time,traceback,zipfile
from collections import Counter
import numpy as np
ROOT=pathlib.Path.cwd()
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
P2=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P2_20261101"
BANK=pathlib.Path(os.getenv("DLP_BANK_DIR","/tmp/dlp_p2_bank"))
ARCHIVE=pathlib.Path(os.getenv("DLP_RF_ZIP","/tmp/dlp_p2_raw_rf.zip"))
CONTRACT="568ef6b794457f682ae9fd96e30d8a6f072d0283fcfd17aed4dcc2adfb76a48b"
CONFIG="99c4f6303ece8d19b2a30f1217f62c852df3074583dff6c388245a54c555cc43"
TOL="ab385d88538b0f2485fdcf1cceef31262a08a7a5c214751c4dfc6949e6101ae3"
AUDIT="40dfe491422b61af81d09bb0bd3ded2dd9d8767be3549d25e892f0b64c0cbee7"
AUDIT_COMMIT="d8f97207b71302b87c4c9669f1ff7e8b311d167e"
RFZIP="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
P1QA="0e94c32edcbf4aaf10938c48fa548b813508a50f46bfcd4e01b09d46f779ad1d"
RR=0.0068578637
RS=0.0081
OFFSET=-0.5315983906250129
GATE_SCALAR=6.6348966010212145
GATE_JOINT=9.210340371976184
METHODS=("DR4","R4","J4_SRC")
BIAS=("B0","L2")
run_start=time.monotonic()
def sha(path):
  d=hashlib.sha256()
  with pathlib.Path(path).open("rb") as f:
    for b in iter(lambda:f.read(1<<20),b""):d.update(b)
  return d.hexdigest()
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def jf(path):return json.loads(pathlib.Path(path).read_text("utf-8"))
def need(ok,msg):
  if not bool(ok):raise RuntimeError(msg)
def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def proof_sha_bytes(path,expected):
  need(pathlib.Path(path).is_file() and sha(path)==expected,
       "STOP_LOCKED_BYTES_SHA:"+str(path))
def verify_gate_and_inputs():
  rat=jf(P2/"P2_FROZEN_RATIFICATION_20261101.json")
  lock=jf(P2/"P2_PROPOSER_LOCK_RECEIPT.json")
  cfg=jf(P2/"P2_CONFIG_LOCK.json")
  toler=jf(P2/"P2_NUMERIC_TOLERANCES.json")
  need(rat["status"]=="FROZEN" and rat["phase_authorized"]=="P2_4STATE_RANGE_ONLY_RECURSIVE_ONLY",
       "P2_RATIFICATION_NOT_FROZEN")
  for name,dig in [("P2_EXPERIMENT_CONTRACT_PROPOSER_LOCKED.md",CONTRACT),
                   ("P2_CONFIG_LOCK.json",CONFIG),("P2_NUMERIC_TOLERANCES.json",TOL)]:
    proof_sha_bytes(P2/name,dig)
  need(lock["file_digests"] and len(toler["tests"])==16,"P2_LOCK_CHANGED")
  need(rat["binding_sha256"]["contract"]==CONTRACT and
       rat["binding_sha256"]["config"]==CONFIG and
       rat["binding_sha256"]["numeric_tolerances"]==TOL,"P2_SIGNED_HASH_BINDING_CHANGED")
  auditrec=rat["linked_approvals"]["auditor"]
  need(auditrec["raw_audit_sha256"]==AUDIT and
       auditrec["decision"]=="ACCEPT_WITH_BOUNDARIES" and
       auditrec["auditor_ref_commit"]==AUDIT_COMMIT,"UNSIGNED_AUDITOR")
  full="repos/myoungsunk/sionna-resimulation/contents/"+auditrec["audit_path"]+"?ref="+AUDIT_COMMIT
  encoded=subprocess.check_output(["gh","api",full,"--jq",".content"],text=True)
  payload=base64.b64decode(encoded.replace("\n",""))
  need(sha_bytes(payload)==AUDIT,"AUDIT_RECEIPT_HASH_DRIFT")
  a=json.loads(payload)
  need(a["verdict"]=="ACCEPT_WITH_BOUNDARIES" and len(a["checks"])==12 and
       len(a["failures"])==0 and a["input_contract_sha256"]==CONTRACT,
       "AUDIT_RECEIPT_NOT_PASS")
  p1qa=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/runs/P1_SOURCE_HARMONIZATION_41300302082/P1_SCIENCE_QA.json"
  proof_sha_bytes(p1qa,P1QA)
  src=jf(p1qa)
  need(src["status"]=="PASS" and len([k for k in src["gates"] if k.startswith("T")])==16,
       "P1_DATA_SCIENCE_QA_CHANGED")
  p1inputs=jf(P1/"P1_INPUT_LOCK.json")
  verify=[]
  for item in p1inputs["base_assets"]:
    p=ROOT/item["path"]
    proof_sha_bytes(p,item["sha256"])
    need(p.stat().st_size==item["bytes"],"C0_BYTES_CHANGED:"+item["path"])
    verify.append({"path":item["path"],"sha256":item["sha256"],"bytes":item["bytes"]})
  for item in cfg["pinned_sources"]:
    code_sha=subprocess.check_output(["git","hash-object",item["path"]],text=True).strip()
    need(code_sha==item["git_blob"],"PINNED_SOURCE_CHANGED:"+item["path"])
  bankpaths=[]
  for x in p1inputs["ffd_bank_source"]["banks"]:
    got=list(BANK.rglob(x["filename"]))
    need(len(got)==1 and got[0].stat().st_size==x["bytes"] and sha(got[0])==x["sha256"],
         "REAL_FFD_BANK_BAD:"+x["filename"])
    bankpaths.append(got[0])
  proof_sha_bytes(ARCHIVE,RFZIP)
  return cfg,p1inputs,bankpaths,verify

def stage_bank(p1inputs,bankpaths):
  dest=ROOT.parent
  data={}
  for p,x in zip(bankpaths,p1inputs["ffd_bank_source"]["banks"]):
    target=dest/x["filename"]
    need(not target.exists() and not target.is_symlink(),"BANK_ALREADY_STAGED")
    target.symlink_to(p)
    data[x["filename"]]=x["sha256"]
  (dest/"BANK_MANIFEST.json").write_text(json.dumps({"npz_sha256":data},sort_keys=True))
  (dest/"ffd_p0p3/out").mkdir(parents=True,exist_ok=True)

def load_source():
  sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
  sys.path.insert(0,str(ROOT/"research/FFD_P0P3_20261016"))
  sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
  import core, r2_bias_replay
  from source_model import SourceFFD
  return core,r2_bias_replay,SourceFFD()

def open_trace_pair(route,config):
  z=zipfile.ZipFile(ARCHIVE)
  need(z.testzip() is None,"SOURCE_ARCHIVE_ZIP_CRC_BAD")
  summary=z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json")
  need(sha_bytes(summary)=="8412e39cbeafa41656041ffe9f7778ef7f0d597508d3cfb2747e4735c4e83634",
       "ORIGINAL_14_TRACE_SUMMARY_SHA_CHANGED")
  index=json.loads(summary)
  need(len(index["per_case"])==14,"ARCHIVE_NOT_14_PAIR")
  selected=set(c for c in config["cases"] if c.startswith(route+"_"))
  expected={(c,ch) for c in selected for ch in ("full","los")}
  by={}
  for desc in index["per_case"]:
    if desc["case"] not in selected:continue
    file=z.read("P2_OUT/"+desc["trace_file"])
    need(sha_bytes(file)==desc["trace_sha256"],"ARCHIVE_NPZ_SHA_INVALID:"+desc["trace_file"])
    with np.load(io.BytesIO(file),allow_pickle=False) as a:
      need(all(x in a.files for x in ("t_s","pose_id","z_r_m","z_s","detected","truth_for_offline_scoring_only")),
           "ARCHIVE_FIELDS_MISSING")
      t=a["t_s"].copy();ids=a["pose_id"].copy()
      truth=a["truth_for_offline_scoring_only"].copy()
      obs=np.column_stack((a["z_r_m"],a["z_s"]))
      detected=a["detected"].copy()
    need(obs.shape==(len(t),2) and truth.shape==(len(t),3) and
         np.all(np.diff(t)>0) and np.isfinite(obs).all() and np.all(detected),
         "ORIGINAL_RF_INVALID:"+desc["trace_file"])
    by[(desc["case"],desc["channel"])]=dict(t=t,ids=ids,truth=truth,obs=obs,
       trace_sha=desc["trace_sha256"])
  need(set(by)==expected,"ROUTE_CASE_OR_FULL_NATIVE_MISSING:"+route)
  first=None
  for trace in by.values():
    if first is None:first=trace
    else:
      need(np.array_equal(trace["t"],first["t"]) and
           np.array_equal(trace["ids"],first["ids"]) and
           np.array_equal(trace["truth"],first["truth"]),
           "SAME_ROUTE_BUT_DIFFERENT_POSE_TIME_TRUTH")
  z.close()
  return by,first

def range_model(x,case):
  x=np.asarray(x,float)
  u=float(x[0]-case["anchor"][0]);v=float(x[1]-case["anchor"][1])
  dz=float(case["robot_z_m"]-case["anchor"][2])
  d=math.sqrt(u*u+v*v+dz*dz)
  h=np.array([d+OFFSET])
  H=np.zeros((1,4));H[0,:2]=u/d,v/d
  return h,H

def replay(controls,observed,detected,case,x0,core,source):
  """No truth, label, bias, future-state arguments; exact historical prior per arm."""
  n=len(observed);NARM=len(METHODS)
  xposterior=np.full((n,NARM,4),np.nan)
  Pposterior=np.full((n,NARM,4,4),np.nan)
  xprior=np.full((n,NARM,4),np.nan)
  Pprior=np.full((n,NARM,4,4),np.nan)
  predicted_z=np.full((n,NARM,2),np.nan)
  innov=np.full((n,NARM,2),np.nan)
  Hmatrix=np.full((n,NARM,2,4),np.nan)
  Smat=np.full((n,NARM,2,2),np.nan)
  Kmat=np.full((n,NARM,4,2),np.nan)
  nis=np.full((n,NARM),np.nan)
  status=np.full((n,NARM),"NOT_RUN",dtype="<U26")
  near_pole=np.zeros((n,NARM),bool)
  traceerr=[]
  initP=np.diag([.1**2,.1**2,math.radians(5)**2,math.radians(.1)**2])
  x_init=np.r_[np.asarray(x0,float),0.]
  states={name:(x_init.copy(),initP.copy()) for name in METHODS}
  invalid=set()
  # A single observed RF packet is shared; measurement modality changes.
  for k in range(n):
    packet=np.asarray(observed[k],float)
    need(packet.shape==(2,),"PACKET_NOT_RANGE_SIGNED_S")
    for j,method in enumerate(METHODS):
      if method in invalid:
        status[k,j]="INVALID_PREVIOUS"
        continue
      x,P=states[method]
      try:
        if k:
          ds=float(controls["ds_odom"][k])
          angle=float(controls["dtheta_gyro"][k])
          dt=float(controls["dt_s"][k])
          need(dt>0 and np.isfinite([ds,angle,dt]).all(),"NONFINITE_OR_ZERO_DT")
          Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
          x,P,_,_=core.predict(x,P,ds,angle,dt,Q)
        xprior[k,j]=x
        Pprior[k,j]=P
        near_pole[k,j]=(math.hypot(x[0]-case["anchor"][0],x[1]-case["anchor"][1])<=.1)
        if method=="DR4":
          out=x.copy();cov=P.copy();stat="DR_ONLY"
        elif not bool(detected[k]):
          out=x.copy();cov=P.copy();stat="MISSING"
        else:
          if method=="R4":
            prediction=lambda v:range_model(v,case)
            z=packet[:1];R=np.array([[RR]]);threshold=GATE_SCALAR
          elif method=="J4_SRC":
            prediction=lambda v:source.model(v,case)
            z=packet;R=np.diag([RR,RS]);threshold=GATE_JOINT
          else:raise RuntimeError("UNKNOWN_ARM:"+method)
          out,cov,diag=core.gaussian_update(x,P,z,prediction,R,gate_threshold=threshold)
          stat="APPLIED" if diag["accepted"] else "REJECT"
          count=len(z)
          nis[k,j]=float(diag["NIS"])
          innov[k,j,:count]=diag["innovation"]
          predicted_z[k,j,:count]=z-diag["innovation"]
          Hmatrix[k,j,:count]=diag["H"]
          Smat[k,j,:count,:count]=diag["S"]
          Kmat[k,j,:,:count]=diag["K"]
          need(bool((nis[k,j]<=threshold)==diag["accepted"]),"GATE_WRONG_DOF_OR_REUSED")
        need(np.isfinite(out).all() and np.isfinite(cov).all() and
             np.linalg.eigvalsh((cov+cov.T)*.5).min()>0 and
             float(np.max(abs(cov-cov.T)))<1e-10,
             "INVALID_NONPD_POSTERIOR")
        xposterior[k,j]=out
        Pposterior[k,j]=cov
        status[k,j]=stat
        states[method]=(out,cov)
      except BaseException as e:
        status[k,j]="INVALID"
        invalid.add(method)
        traceerr.append(dict(timeline_index=k,arm=method,reason=repr(e),
                 case=case["id"],pre_x=x.tolist(),t_s=float(controls["t_s"][k])))
  return dict(xpost=xposterior,Ppost=Pposterior,xprior=xprior,Pprior=Pprior,
              h=predicted_z,innovation=innov,H=Hmatrix,S=Smat,K=Kmat,nis=nis,
              status=status,near_pole=near_pole),traceerr

def save_csv(path,rows,headers):
  with pathlib.Path(path).open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=headers,extrasaction="ignore");w.writeheader()
    for r in rows:w.writerow(r)

def execute_route(route,out):
  cfg,locked,bankpaths,assetledger=verify_gate_and_inputs()
  need(route in ("R2","R4","R5"),"UNRECOGNIZED_ROUTE")
  stage_bank(locked,bankpaths)
  core,old_replay,src=load_source()
  allmeta={c["id"]:c for c in jf(ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json")["cases"]}
  by,basetrace=open_trace_pair(route,cfg)
  caseids=[c for c in cfg["cases"] if c.startswith(route+"_")]
  need(len(caseids)==(3 if route=="R2" else 2),"CASE_ROUTE_COVERAGE_DIFFER")
  controls_by_level={}
  for label in BIAS:
    # Real trajectory truth used ONLY here to produce synthetic sensor readings.
    controls,x0=old_replay.build_positive_bias_controls(
        basetrace["t"],basetrace["truth"],label,seed=0)
    need(len(x0)==3 and x0.shape==(3,) and
       np.allclose(controls["t_s"],basetrace["t"],atol=0,rtol=0),
       "CONTROL_GENERATION_NOT_SOURCE_PAIRED")
    controls_by_level[label]=(controls,x0)
  if np.max(abs(controls_by_level["B0"][0]["ds_odom"]-
                controls_by_level["L2"][0]["ds_odom"]))>1e-12:
    raise RuntimeError("L2_NONBIAS_WHEEL_DRIFT")
  # Reversible per-route run outputs. Every channel and bias/arm retained.
  out.mkdir(parents=True,exist_ok=False)
  trace_dir=out/"traces";trace_dir.mkdir()
  ledger=[]
  records=[]
  for cid in caseids:
    case=allmeta[cid]
    for channel in ("full","los"):
      trace=by[(cid,channel)]
      for label in BIAS:
        controls,x0=controls_by_level[label]
        data,fail=replay(controls,trace["obs"],np.ones(len(trace["obs"]),bool),
                        case,x0,core,src)
        name=f"{cid}_{channel}_{label}_seed0_P2_4STATE.npz"
        fn=trace_dir/name
        np.savez_compressed(fn,
             case_id=np.array(cid),channel=np.array(channel),bias_level=np.array(label),
             names=np.array(METHODS),t_s=trace["t"],pose_id=trace["ids"],
             xprior=data["xprior"],Pprior=data["Pprior"],xpost=data["xpost"],
             Ppost=data["Ppost"],h=data["h"],innovation=data["innovation"],
             H=data["H"],S=data["S"],K=data["K"],nis=data["nis"],
             status=data["status"],near_pole=data["near_pole"],
             z_r_s=trace["obs"],ds_odom=controls["ds_odom"],
             dtheta_gyro=controls["dtheta_gyro"],dt_s=controls["dt_s"],
             original_trace_sha256=np.array(trace["trace_sha"]),
             initial_x0=np.r_[x0,0.],initial_P0=np.diag([.01,.01,math.radians(5)**2,math.radians(.1)**2]))
        for row in fail:ledger.append({**row,"channel":channel,"bias_level":label})
        count={method:dict(Counter(data["status"][:,j])) for j,method in enumerate(METHODS)}
        expected=len(trace["t"])
        record=dict(case=cid,channel=channel,bias_level=label,route=route,
                    n_steps=expected,n_eval=int(np.count_nonzero(trace["t"]>=30)),
                    bias_dps=0.0 if label=="B0" else .2,
                    statuses=count,source_archive_trace_sha256=trace["trace_sha"],
                    output_file=str(fn.relative_to(out)),output_sha256=sha(fn),output_bytes=fn.stat().st_size,
                    errors=fail[:8],n_errors=len(fail),source_model="Pinned SourceFFD for J4_SRC only",
                    observation_dimensions={"DR4":0,"R4":1,"J4_SRC":2},
                    R0_assumption="Diagonal conventional unverified cross-channel independence")
        records.append(record)
        print("P2_CASE_COMPLETE",cid,channel,label,
              "status",count,"failures",len(fail),
              "source_s_filt_elapsed_s",round(time.monotonic()-run_start,2),flush=True)
  summary=dict(schema="DLP_P2_FROZEN_RANGE_ONLY_ROUTE_RESULT_V1",
       phase="DLP-EKF-GAPS-001/P2-V1",route=route,
       qa_status="PASS" if not ledger and len(records)==len(caseids)*4 else "FAIL",
       original_archive_sha256=RFZIP,original_39_sha_verified=len(assetledger),
       bank_sha_verified=[sha(p) for p in bankpaths],
       frozen_contract_sha256=CONTRACT,config_sha256=CONFIG,tolerances_sha256=TOL,
       audit_receipt_sha256=AUDIT,original_P1_qa_sha256=P1QA,
       source_version_git_blob=next(x["git_blob"] for x in cfg["pinned_sources"] if x["path"].endswith("/source_model.py")),
       ekf4_core_blob=next(x["git_blob"] for x in cfg["pinned_sources"] if x["path"].endswith("/core.py")),
       method_names=list(METHODS),bias=list(BIAS),seed=0,independent_scene_count=1,
       no_truth_runtime=True,no_new_RF=True,no_learned_mu_R=True,
       cases=records,n_failed_events=len(ledger),runner_script_sha256=sha(__file__),
       runtime=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),
                    run_id=os.getenv("GITHUB_RUN_ID"),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    seconds=time.monotonic()-run_start))
  (out/"P2_ROUTE_RECEIPT.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
  save_csv(out/"P2_ROUTE_FAILURE_LEDGER.csv",ledger,
           ["case","channel","bias_level","timeline_index","t_s","arm","reason","pre_x"])
  if summary["qa_status"]!="PASS":raise RuntimeError("P2_ROUTE_INFERENCE_FAILURE_PRESERVED:"+route)
  return summary

if __name__=="__main__":
  parser=argparse.ArgumentParser()
  parser.add_argument("--route",required=True,choices=("R2","R4","R5"))
  parser.add_argument("--out",required=True)
  args=parser.parse_args()
  out=pathlib.Path(args.out)
  try:
    q=execute_route(args.route,out)
    print("P2_ROUTE_FINAL",q["qa_status"],"route",args.route,
          "cases",len(q["cases"]),"errors",q["n_failed_events"],flush=True)
    sys.exit(0)
  except BaseException as e:
    print("P2_ROUTE_FATAL",repr(e),traceback.format_exc(),flush=True)
    out.mkdir(parents=True,exist_ok=True)
    (out/"P2_FATAL.json").write_text(json.dumps(dict(
        phase="P2",route=args.route,status="BLOCKED",reason=repr(e),
        traceback=traceback.format_exc(),source_code_sha256=sha(__file__),
        run_id=os.getenv("GITHUB_RUN_ID")),indent=2)+"\n")
    sys.exit(1)
