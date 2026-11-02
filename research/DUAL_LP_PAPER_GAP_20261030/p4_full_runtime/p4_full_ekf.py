#!/usr/bin/env python3
"""P4 FULL: 3136 exact original RF-pose epochs, 4state seven self-gated EKF arms.

Load physically verified NEW C Native H Full/LoS (3097 original newly traced
+39 previous actual P3), original A/B frozen C0 H, original P2 controls and
initial state/P. All route timesteps have all three actual RF packets.
GT used only offline for scoring and old control simulation provenance.
No new RF inference, Source-only C, fitted R or non-pinned f/F/Q.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,os,pathlib,platform,subprocess,sys,time,traceback,zipfile
from collections import Counter
import numpy as np
ROOT=pathlib.Path.cwd()
LOCK=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P4_FULL_20261102"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
NATIVE=pathlib.Path(os.getenv("DLP_P4_FULL_NATIVE_BUNDLE","/tmp/p4full_route_native"))
BANKS=pathlib.Path(os.getenv("DLP_FULL_BANK_DIR","/tmp/p4full_physical_banks"))
OUT=pathlib.Path(os.getenv("DLP_P4_FULL_FILTER_OUT","/tmp/p4full_ekf_result"))
START=time.monotonic()
C=299792458.;N=257;DF=1950000.;OFFSET=-.5315983906250129
RR=.0068578637;RS=.0081;GATE={1:6.6348966010212145,2:9.210340371976184,3:11.344866730144373}
ARMS=("DR4","R4_A_FULL","J4_A_FULL","R4_AB_FULL","R4_ABC_FULL","R4_A_EQPKT","R4_ABC_EQPKT")
BIASES={"B0":0.0,"L2":.20};ANCHOR={"A":(4.,0.,2.65),"B":(10.,0.,2.65),"C":(16.,.8,2.65)}
FAILED=[];RESULTS=[]
def sha(p):
  h=hashlib.sha256()
  with pathlib.Path(p).open("rb") as f:
    for b in iter(lambda:f.read(1<<20),b""):h.update(b)
  return h.hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_text("utf-8"))
def require(condition,msg):
  if not bool(condition):raise RuntimeError(msg)
def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def readcsv(p):
  with pathlib.Path(p).open(newline="",encoding="utf-8") as f:
    return list(csv.DictReader(f))
def detector(h):
  """Entire actual frequency response raw CFR -> same first-path r/s per
  pose; vectorized, no SourceFFD or inferred C channel.
  h: [pose, 257, rx2, tx2]."""
  h=np.asarray(h)
  require(h.ndim==4 and h.shape[1:]==(N,2,2),"RAW_N257_2RX_2TX_REQUIRED")
  w=.5-.5*np.cos(2*np.pi*np.arange(N)/(N-1))
  total=len(h);s=np.empty(total);r=np.empty(total);taps=np.empty(total,np.int16)
  for start in range(0,total,64):
    a=h[start:start+64,:,:,0]
    cir=np.fft.ifft(a*w[None,:,None],n=4*N,axis=1)*N
    mag=np.abs(cir);power_max=mag.max(axis=1)
    strongest=power_max.argmax(axis=1)
    env=np.take_along_axis(mag,strongest[:,None,None],axis=2)[:,:,0]
    peak=env.max(axis=1)
    ix=np.argmax(env>=.3*peak[:,None],axis=1)
    first=cir[np.arange(len(a)),ix,:]
    p=np.abs(first)**2;den=p.sum(axis=1)
    require(np.isfinite(den).all() and np.all(den>0),"BAD_RAW_FIRST_PATH_POWER")
    z=(p[:,0]-p[:,1])/den
    require(np.isfinite(z).all() and np.all(abs(z)<=1+1e-12),"INVALID_SIGNED_S")
    s[start:start+len(a)]=z
    r[start:start+len(a)]=ix*C/(4*N*DF)
    taps[start:start+len(a)]=ix
  return np.column_stack((r,s)),taps
def range_model(state,names):
  z=[];H=[]
  for name in names:
    a=ANCHOR[name]
    d=np.array([state[0]-a[0],state[1]-a[1],.45-a[2]],float)
    D=float(np.linalg.norm(d))
    require(D>0,"ZERO_GEOMETRIC_3D_DISTANCE")
    z.append(D+OFFSET)
    H.append([d[0]/D,d[1]/D,0.,0.])
  return np.asarray(z),np.asarray(H)
def load_original():
  freeze=J(LOCK/"P4_FULL_FROZEN_RATIFICATION.json")
  cfg=J(LOCK/"P4_FULL_CONFIG_LOCK.json")
  require(freeze["status"]=="FROZEN_NATIVE_C_FULL_LOS_3097_EXTENSION","P4_FULL_NOT_FROZEN")
  for item in freeze["locked_files"]:
    require(sha(LOCK/item["name"])==item["sha256"],"P4_FULL_SCIENCE_LOCK_BYTES_DRIFT")
  audit=freeze["pre_run_canary"]
  require(audit["decision"]=="FULL_DIRECT_CERTIFIED" and audit["n_frequencies"]==54,
          "NATIVE_DIRECT_PATH_NOT_CERTIFIED")
  root=ROOT/audit["receipt_path"]
  require(sha(root)==audit["receipt_sha256"],"P4_FULL_CANARY_RECEIPT_CHANGED")
  obs=J(root)
  require(obs["status"]=="PASS_WITH_MODE_DECISION" and obs["algorithm_mode"]=="FULL_DIRECT_CERTIFIED",
          "P4_FULL_CANARY_NOT_CERTIFIED")
  p1=J(P1/"P1_INPUT_LOCK.json")
  return cfg,p1,freeze

def source_model(cfg,p1):
  import importlib
  sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
  sys.path.insert(0,str(ROOT/"research/FFD_P0P3_20261016"))
  import core
  from source_model import SourceFFD
  f=ROOT/"research/EKF4_RANGE_S_STAGED_20261014/core.py"
  sha_blob=subprocess.check_output(["git","hash-object",str(f)],text=True).strip()
  require(sha_blob=="0a0851e6867c14fec5eefe02df471100cb9e9e1d","PINNED_EKF4_CORE_SOURCE_CHANGED")
  for b in p1["ffd_bank_source"]["banks"]:
    matches=list(BANKS.rglob(b["filename"]))
    require(len(matches)==1 and sha(matches[0])==b["sha256"] and
      matches[0].stat().st_size==b["bytes"],"PHYSICAL_BANK_SOURCE_SHA_CHANGED")
    dest=ROOT.parent/b["filename"]
    require(not dest.exists() and not dest.is_symlink(),"FFD_STAGING_ALREADY_PRESENT")
    dest.symlink_to(matches[0])
  manifest={b["filename"]:b["sha256"] for b in p1["ffd_bank_source"]["banks"]}
  (ROOT.parent/"BANK_MANIFEST.json").write_text(json.dumps({"npz_sha256":manifest},sort_keys=True))
  (ROOT.parent/"ffd_p0p3/out").mkdir(parents=True,exist_ok=True)
  source=SourceFFD()
  require(np.array_equal(source.freqs,6250400000.+DF*np.arange(N)),"SOURCE_FREQ_CHANGED")
  return core,source
def input_rf(route,cfg,p1):
  receipt_path=NATIVE/f"P4_FULL_C_{route}_ROUTE_RECEIPT.json"
  receipt=J(receipt_path)
  n=cfg["geometry"]["routes_n"][route]
  require(receipt["status"]=="PASS" and receipt["original_timeline_epochs"]==n and
     receipt["newly_generated_original_native_count"]==n-13 and receipt["missing"]==0,
     "INCOMPLETE_REAL_C_NATIVE_ROUTE:"+route)
  zippath=NATIVE/receipt["raw_archive_file"]
  require(zippath.is_file() and sha(zippath)==receipt["raw_archive_sha256"],
          "REAL_FULL_C_NATIVE_ROUTE_ZIP_SHA_MISSING")
  with zipfile.ZipFile(zippath) as z:
    member=z.read(receipt["merged_npz_member"])
    require(hashlib.sha256(member).hexdigest()==receipt["merged_native_C_npz_sha256"],
      "COMPACT_C_NATIVE_ROUTE_MANIFEST_SHA_MISMATCH")
    with np.load(io.BytesIO(member),allow_pickle=False) as a:
      cfull=a["H_native_full"].copy();clos=a["H_native_los"].copy()
      t=a["original_time_s"].copy();pids=a["pose_id"].copy()
      cprev_z=a["raw_r_s"].copy();ctap=a["first_path_tap"].copy()
  require(cfull.shape==(n,N,2,2) and clos.shape==(n,N,2,2) and
      np.isfinite(cfull).all() and np.isfinite(clos).all(),
      "C_NATIVE_ALL_EPOCH_H_DIM_OR_FINITE")
  T=next(z["path"] for z in p1["base_assets"] if z["kind"]=="TIMELINE_TNONE" and
      "timeline_"+route+"_" in z["path"])
  tm=readcsv(ROOT/T)
  require(np.max(abs(np.array([float(z["t_s"]) for z in tm])-t))<=1e-9,
      "REAL_NATIVE_C_TIMELINE_DOES_NOT_MATCH_C0")
  require(np.array_equal(pids,np.asarray([int(z["pose_id"]) for z in tm])),
      "REAL_NATIVE_C_ALL_3136_POSE_ID_MISMATCH")
  obs=np.full((n,2,3,2),np.nan)
  taps=np.zeros((n,2,3),np.int16)
  Cnative=[clos,cfull]
  for i,mode in enumerate(("los","full")):
    oz,otap=detector(Cnative[i])
    require(np.max(abs(oz-cprev_z[:,i]))<=1e-10 and
        np.array_equal(otap,ctap[:,i]),"NEW_C_NATIVE_RAW_H_DETECTOR_NOT_REPRODUCED")
    obs[:,i,2]=oz;taps[:,i,2]=otap
  case_A=None
  for ai,aname in enumerate(("A","B")):
    case=next(x for x in p1["primary_cases"] if x["case_id"]==route+"_a"+aname+"_m0")
    if aname=="A":case_A=case
    for modeindex,(mode,field) in enumerate((("los","los_path"),("full","full_path"))):
      path=ROOT/case[field]
      row=next(z for z in p1["base_assets"] if z["path"]==case[field])
      require(path.is_file() and sha(path)==row["sha256"] and path.stat().st_size==row["bytes"],
              "ORIGINAL_A_B_FULL_RF_SHA_CHANGED:"+str(path))
      H=np.load(path,mmap_mode="r",allow_pickle=False)
      # Original bank has more sampled RF poses than the route timeline.
      # Full EKF must index the EXACT frozen timeline pose IDs (no re-sampling).
      require(H.ndim==4 and H.shape[1:]==(N,2,2) and
           int(pids.min())>=0 and int(pids.max())<len(H),
           "ORIGINAL_A_B_BANK_TO_TIMELINE_POSE_INDEX_INVALID")
      H_timeline=np.asarray(H[pids])
      zz,tt=detector(H_timeline)
      require(len(zz)==n,"ORIGINAL_A_B_MATCHED_TIME_SAMPLE_COUNT_BAD")
      obs[:,modeindex,ai]=zz
      taps[:,modeindex,ai]=tt
  require(np.isfinite(obs).all(),"A_B_C_REAL_NATIVE_RAW_Z_MISSING")
  return t,pids,tm,obs,taps,case_A,receipt

def replay(t,inputs,z,source,case_A,core):
  """Inference-only: contains NO ground truth, no true-bias or scoring data."""
  n=len(t);m=len(ARMS);ntrim=3*(n//3)
  X=np.full((n,m,4),np.nan);P=np.full((n,m,4,4),np.nan)
  PX=X.copy();PP=P.copy()
  status=np.full((n,m),"NOT_RUN",dtype="<U24");NIS=np.full((n,m),np.nan)
  H=np.full((n,m,3,4),np.nan)
  S=np.full((n,m,3,3),np.nan)
  K=np.full((n,m,4,3),np.nan)
  NU=np.full((n,m,3),np.nan)
  packet=np.zeros((n,m),np.int16);component=np.zeros((n,m),np.int16)
  start_x=inputs["x0"].copy();start_P=inputs["P0"].copy()
  states={arm:(start_x.copy(),start_P.copy()) for arm in ARMS}
  invalid=set();failed=[]
  for step in range(n):
    for j,arm in enumerate(ARMS):
      if arm in invalid:
        status[step,j]="INVALID_PREVIOUS";continue
      prior,cov=states[arm]
      try:
        if step>0:
          ds=float(inputs["ds_odom"][step]);dt=float(inputs["dt_s"][step])
          gy=float(inputs["dtheta_gyro"][step])
          needQ=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
          prior,cov,_,_=core.predict(prior,cov,ds,gy,dt,needQ)
        PX[step,j]=prior;PP[step,j]=cov
        if arm=="DR4":out,pc,st=prior,cov,"DR_ONLY"
        elif arm=="R4_A_EQPKT" and step>=ntrim:out,pc,st=prior,cov,"SKIP_BUDGET"
        elif arm=="R4_ABC_EQPKT" and (step>=ntrim or step%3!=0):out,pc,st=prior,cov,"SKIP_BUDGET"
        else:
          if arm=="J4_A_FULL":
            observation=np.asarray(z[step,0,:],float)
            model=lambda x:source.model(x,case_A)
            dims=2;nf_packets=1;R=np.diag([RR,RS])
          else:
            names={"R4_A_FULL":["A"],"R4_AB_FULL":["A","B"],
              "R4_ABC_FULL":["A","B","C"],"R4_A_EQPKT":["A"],
              "R4_ABC_EQPKT":["A","B","C"]}[arm]
            ix=[{"A":0,"B":1,"C":2}[aname] for aname in names]
            observation=np.asarray(z[step,ix,0],float)
            model=lambda x,nms=names:range_model(x,nms)
            dims=len(names);nf_packets=dims;R=np.eye(dims)*RR
          require(observation.shape==(dims,) and np.isfinite(observation).all(),
             "REAL_NATIVE_RF_OBSERVATION_INVALID")
          out,pc,diag=core.gaussian_update(prior,cov,observation,model,R,
                                             gate_threshold=GATE[dims])
          st="APPLIED" if diag["accepted"] else "REJECT"
          require((diag["NIS"]<=GATE[dims])==bool(diag["accepted"]),
             "CHI2_DOF_GATE_PARITY_BAD")
          packet[step,j]=nf_packets;component[step,j]=dims
          H[step,j,:dims]=diag["H"];NU[step,j,:dims]=diag["innovation"]
          S[step,j,:dims,:dims]=diag["S"];K[step,j,:,:dims]=diag["K"]
          NIS[step,j]=diag["NIS"]
        require(np.isfinite(out).all() and np.isfinite(pc).all() and
                np.linalg.eigvalsh((pc+pc.T)/2).min()>0 and
                np.max(abs(pc-pc.T))<=1e-10,
                "NONFINITE_OR_NONPOSITIVE_4STATE_COVARIANCE")
        X[step,j]=out;P[step,j]=pc;status[step,j]=st
        states[arm]=(out.copy(),pc.copy())
      except Exception as exc:
        invalid.add(arm);status[step,j]="INVALID"
        failed.append(dict(step=step,arm=arm,cause=repr(exc),time_s=float(t[step])))
  return dict(xpost=X,Ppost=P,xprior=PX,Pprior=PP,status=status,nis=NIS,
      H=H,S=S,K=K,innovation=NU,packets=packet,components=component),failed

def score(result,t,truth,bias,route,channel):
  # Dedicated OFFLINE scoring after inference. Never pass GT to replay().
  n=len(t);keep=t>=30.;nkeep=int(keep.sum());allscore=[]
  for j,arm in enumerate(ARMS):
    x=result["xpost"][:,j];P=result["Ppost"][:,j]
    s=result["status"][:,j]
    if not np.isfinite(x).all() or not np.isfinite(P).all():
      allscore.append(dict(route=route,channel=channel,bias=bias,arm=arm,
        status="INVALID",n_eval=nkeep,score_valid=0));continue
    e=x[keep,:3]-truth[keep,:3];e[:,2]=wrap(e[:,2])
    b=x[keep,3]-math.radians(BIASES[bias])
    pc=P[keep,:3,:3]
    poseNEES=np.einsum("ij,ij->i",e,np.linalg.solve(pc,e[:,:,None])[:,:,0])
    headingNEES=e[:,2]**2/P[keep,2,2]
    allscore.append(dict(route=route,channel=channel,bias=bias,arm=arm,
      status="COMPLETE",n_eval=nkeep,score_valid=nkeep,
      heading_rmse_deg=math.degrees(math.sqrt(float(np.mean(e[:,2]**2)))),
      xy_rmse_m=math.sqrt(float(np.mean(np.sum(e[:,:2]**2,axis=1)))),
      bias_rmse_deg_s=math.degrees(math.sqrt(float(np.mean(b**2)))),
      final_bias_est_deg_s=math.degrees(float(x[-1,3])),
      mean_heading_NEES=float(headingNEES.mean()),
      mean_pose_NEES=float(poseNEES.mean()),
      heading95=float(np.mean(headingNEES<=3.841458820694124)),
      pose95=float(np.mean(poseNEES<=7.814727903251179)),
      packets_offered=int(result["packets"][:,j].sum()),
      scalar_components_offered=int(result["components"][:,j].sum()),
      accepted=int(np.count_nonzero(s=="APPLIED")),
      rejected=int(np.count_nonzero(s=="REJECT")),
      skipped_budget=int(np.count_nonzero(s=="SKIP_BUDGET")),
      full_native_C_epochs=n,sensor_seed=0,independent_scene_count=1,
      hardware_sync_proven=False,R_interanchor_diagonal_assumed=True))
  return allscore

def run(route):
  cfg,p1,freeze=load_original()
  out=OUT
  out.mkdir(parents=True,exist_ok=True)
  t,pids,tm,raw,taps,case_A,c_receipt=input_rf(route,cfg,p1)
  core,source=source_model(cfg,p1)
  source_path=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_ALL_28_TRACES_IMMUTABLE.zip"
  require(sha(source_path)=="063d5c25892365f8d307fc424470b5066db36fa5f825fbf17b5bcb2bcc5531c3",
       "P2_FROZEN_SENSOR_CONTROLS_ARCHIVE_SHA_DRIFT")
  P2=zipfile.ZipFile(source_path)
  ground_truth=np.array([[float(row["x"]),float(row["y"]),
                         math.radians(float(row["yaw_body_deg"]))] for row in tm])
  n=len(t);ntrim=3*(n//3)
  errors=[];metrics=[];traces=[]
  for bias in ("B0","L2"):
    reference=f"traces/{route}_aA_m0_full_{bias}_seed0_P2_4STATE.npz"
    with np.load(io.BytesIO(P2.read(reference)),allow_pickle=False) as p:
      require(len(p["t_s"])==n and np.max(abs(p["t_s"]-t))<=1e-9,
         "OLD_P2_GYRO_SENSOR_TIMELINE_CHANGED")
      controls={key:p[key].copy() for key in ("ds_odom","dtheta_gyro","dt_s")}
      controls["x0"]=p["initial_x0"].copy()
      controls["P0"]=p["initial_P0"].copy()
      require(controls["x0"].shape==(4,) and controls["P0"].shape==(4,4),
            "STATE_4_INITIAL_POSE_DIMENSION_DRIFT")
    for ch,m in (("los",0),("full",1)):
      for anchor_idx,aname in enumerate(("A","B")):
        fname=f"traces/{route}_a{aname}_m0_{ch}_{bias}_seed0_P2_4STATE.npz"
        with np.load(io.BytesIO(P2.read(fname)),allow_pickle=False) as original:
          require(len(original["t_s"])==n and
             np.max(abs(original["t_s"]-t))<=1e-9 and
             np.array_equal(original["ds_odom"],controls["ds_odom"]) and
             np.array_equal(original["dtheta_gyro"],controls["dtheta_gyro"]) and
             np.array_equal(original["dt_s"],controls["dt_s"]),
            "P4_FULL_C_CONTROLS_NOT_SAME_AS_P2")
          require(np.max(abs(original["z_r_s"]-raw[:,m,anchor_idx,:]))<=1e-9,
            "ALL_ORIGINAL_A_B_RF_Z_MISMATCH_WITH_FROZEN_P2")
      data,failed=replay(t,controls,raw[:,m],source,case_A,core)
      errors.extend(dict(route=route,channel=ch,bias=bias,**row) for row in failed)
      metrics+=score(data,t,ground_truth,bias,route,ch)
      name=f"P4_FULL_{route}_{ch}_{bias}_7STATE_EKF.npz"
      with (out/name).open("wb") as _:
        pass
      np.savez_compressed(out/name,route=np.array(route),channel=np.array(ch),bias=np.array(bias),
        names=np.array(ARMS),t_s=t,pose_id=pids,
        raw_native_ABC_z=raw[:,m],original_native_C_real=True,
        original_native_tap=taps[:,m],
        ds_odom=controls["ds_odom"],dtheta_gyro=controls["dtheta_gyro"],
        dt_s=controls["dt_s"],initial_x0=controls["x0"],initial_P0=controls["P0"],
        **data)
      traces.append(dict(route=route,channel=ch,bias=bias,filename=name,
        sha256=sha(out/name),bytes=(out/name).stat().st_size,
        status="PASS" if not failed else "FAIL",n_errors=len(failed),
        source_C_route_zip_sha256=c_receipt["raw_archive_sha256"],
        time_step_count=n,full_native_C_observation_epochs=n,
        resource_budget={"A":n,"ABC":3*n,"EQ_A":ntrim,"EQ_ABC":ntrim}))
      print("P4_FULL_EKF_TRACE",route,ch,bias,"frames",n,"full_C",n,
        "numerical_errors",len(failed),"elapsed_s",round(time.monotonic()-START,1),flush=True)
  P2.close()
  with (out/"P4_FULL_CASE_METRICS.csv").open("w",newline="") as f:
    keys=sorted({k for row in metrics for k in row})
    writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(metrics)
  with (out/"P4_FULL_FAILURE_LEDGER.csv").open("w",newline="") as f:
    keys=["route","channel","bias","step","arm","cause","time_s"]
    writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(errors)
  status="PASS" if not errors and len(metrics)==28 and all(row["status"]=="COMPLETE" for row in metrics) else "FAIL"
  result=dict(schema="DLP_P4_FULL_3ANCHOR_RECURSIVE_4STATE_ROUTE_V1",
      status=status,route=route,n_timeline=n,n_native_C=n,
      n_native_C_new=n-13,n_native_C_old=13,
      n_eval=int(np.count_nonzero(t>=30)),
      n_arms=len(ARMS),n_metric_rows=len(metrics),
      original_full_C_archive_sha256=c_receipt["raw_archive_sha256"],
      original_P2_sensor_archive_sha256="063d5c25892365f8d307fc424470b5066db36fa5f825fbf17b5bcb2bcc5531c3",
      original_C0_scene_n=1,hardware_clock_sync=False,diagonal_R_assumed=True,
      original_C0_AB_source_unchanged=True,failed=errors,trace_files=traces,
      numeric_pass=status=="PASS",code_sha256=sha(__file__),
      github_run=os.environ.get("GITHUB_RUN_ID"),runner_git_sha=os.environ.get("GITHUB_SHA"),
      runtime_sec=time.monotonic()-START)
  (out/"P4_FULL_EKF_ROUTE_RECEIPT.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
  return status

if __name__=="__main__":
  parser=argparse.ArgumentParser()
  parser.add_argument("--route",choices=("R2","R4","R5"),required=True)
  args=parser.parse_args()
  try:
    flag=run(args.route)
    print("P4_FULL_EKF_FINAL",flag,args.route,"elapsed",time.monotonic()-START,flush=True)
    sys.exit(0 if flag=="PASS" else 1)
  except Exception as e:
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"P4_FULL_EKF_FATAL.json").write_text(json.dumps(dict(status="BLOCKED",
      error=repr(e),traceback=traceback.format_exc(),route=args.route),indent=2)+"\n")
    print("P4_FULL_EKF_FATAL",repr(e),traceback.format_exc(),flush=True)
    sys.exit(1)
