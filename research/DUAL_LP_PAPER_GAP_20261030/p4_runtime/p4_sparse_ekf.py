#!/usr/bin/env python3
"""P4-PILOT: genuine original P3 C Native Sionna H plus C0 A/B range,
seven strictly 4-state EKF arms, entire original timeline with sparse native
C RF updates only at 13 fixed pose epochs per route.

No C Native H fabricated at missing steps, no RF interpolation, no new RT.
Original P2 Seed0 B0/L2 controls, 4-state F/Q/P0, self-gated Joseph.
Scorer reads truth only AFTER inference. Seven arms:
DR4 / R4_A13 / J4_A13 / R4_AB13 / R4_ABC13 /
R4_A_EQ12 / R4_ABC_EQ4.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,os,pathlib,platform,sys,time,traceback,zipfile
from collections import Counter
import numpy as np

ROOT=pathlib.Path.cwd()
LOCK=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P4_20261102"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
BANKROOT=pathlib.Path(os.getenv("P4_BANKS","/tmp/p4_banks"))
START=time.monotonic();ERR=[];GATES={};META={}
RR=.0068578637;RS=.0081;BIAS={"B0":0.,"L2":.2}
N=257;DF=1950000.;C0=299792458.;OFFSET=-.5315983906250129
EXPECTED_SHA={"P4_PILOT_CONFIG_LOCK.json":"ed9e479fc71a2c2cf4e76cb32c16e374875b54a5f97a57f63d3d9ba38c77be0a",
              "P4_PILOT_NUMERIC_GATES.json":"0be33e447fd44be1bd1c344cf501557617462645b741c06a06e63ca60354c0ed",
              "P4_PILOT_PROPOSER_CONTRACT.md":"34891c60e2c3cff30d1920b97a71c200a3f29ffb1b0fa64aa97b435a5c029744"}
ARMS=["DR4","R4_A13","J4_A13","R4_AB13","R4_ABC13","R4_A_EQ12","R4_ABC_EQ4"]
ANCHORS={"A":np.array([4.,0.,2.65]),"B":np.array([10.,0.,2.65]),"C":np.array([16.,.8,2.65])}
THRESH={1:6.6348966010212145,2:9.210340371976184,3:11.344866730144373}
def sha(p):
  h=hashlib.sha256()
  with pathlib.Path(p).open("rb") as f:
    for block in iter(lambda:f.read(1<<20),b""):h.update(block)
  return h.hexdigest()
def shab(b):return hashlib.sha256(b).hexdigest()
def jf(p):return json.loads(pathlib.Path(p).read_text("utf-8"))
def need(ok,msg):
  if not bool(ok):raise RuntimeError(msg)
def wrap(a):return (np.asarray(a)+np.pi)%(2*np.pi)-np.pi
def readcsv(path):
  with pathlib.Path(path).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def writetable(path,rows,fields):
  with pathlib.Path(path).open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
    w.writeheader();w.writerows(rows)
def gate(name,ok,measured):
  GATES[name]={"status":"PASS" if ok else "FAIL","measured":measured}
  print("P4_GATE",name,GATES[name]["status"],str(measured)[:380],flush=True)
  if not ok:ERR.append({"gate":name,"values":measured})
def obs(H):
  """Independent raw detector for A, B and C; no old packet copy or source model."""
  need(H.shape==(N,2,2),"RAW_N_257_RX2_TX2_REQUIRED")
  w=np.sin(np.pi*np.arange(N)/(N-1))**2
  cir=np.fft.ifft(np.asarray(H)[:,:,0]*w[:,None],n=4*N,axis=0)*N
  mag=np.abs(cir);branch=int(mag.max(axis=0).argmax())
  peak=float(mag[:,branch].max())
  need(peak>0,"ZERO_STRONG_BRANCH")
  ix=int(np.argmax(mag[:,branch]>=.3*peak))
  p=np.abs(cir[ix])**2
  need(np.isfinite(p).all() and p.sum()>0,"BAD_FIRST_PATH_POWER")
  signed=float((p[0]-p[1])/p.sum())
  need(abs(signed)<=1+1e-12,"SIGNED_PORT_RATIO_INVALID")
  return np.array([ix*C0/(4*N*DF),signed],float),ix
def range_h(x,anchors):
  h=[];H=[]
  for name in anchors:
    a=ANCHORS[name]
    dr=np.array([x[0]-a[0],x[1]-a[1],.45-a[2]])
    d=float(np.linalg.norm(dr))
    need(d>0,"ZERO_3D_RANGE")
    h.append(d+OFFSET)
    H.append([dr[0]/d,dr[1]/d,0.,0.])
  return np.array(h),np.asarray(H,dtype=float)

def load_and_check():
  rat=jf(LOCK/"P4_PILOT_FROZEN_RATIFICATION.json")
  cfg=jf(LOCK/"P4_PILOT_CONFIG_LOCK.json")
  need(rat["status"]=="FROZEN_P4_SPARSE_39_NATIVE_RF_ONLY","P4_NOT_FROZEN")
  for fname,dig in EXPECTED_SHA.items():
    need(sha(LOCK/fname)==dig,"P4_LOCK_SHA_CHANGED:"+fname)
  need(rat["source_lock_sha256"]=={"config":EXPECTED_SHA["P4_PILOT_CONFIG_LOCK.json"],
    "numeric":EXPECTED_SHA["P4_PILOT_NUMERIC_GATES.json"],
    "contract":EXPECTED_SHA["P4_PILOT_PROPOSER_CONTRACT.md"]},"P4_RATIFICATION_HASH_NOT_MATCHED")
  audit=rat["auditor_receipt"]
  need(audit["verdict"]=="ACCEPT_SPARSE_WITH_BOUNDARIES" and audit["passed"]==11 and audit["failed"]==0,
    "P4_PRE_RUN_AUDIT_NOT_ACCEPTED")
  aud_path=ROOT/audit["path"]
  need(sha(aud_path)==audit["sha256"],"P4_AUDIT_RECEIPT_SHA_CHANGED")
  parsed=jf(aud_path)
  need(parsed["decision"]==audit["verdict"] and not parsed["failures"],"P4_AUDIT_NOT_PASS")
  inp=cfg["sources"]
  for pathfield,sha_field in (("c_zip","c_zip_sha256"),("c_csv","c_csv_sha256"),
                             ("c_qa","c_qa_sha256"),("ab_p1_lock","ab_p1_lock_sha256")):
    need(sha(ROOT/inp[pathfield])==inp[sha_field],"P4_PARENT_SHA_CHANGED:"+pathfield)
  q=jf(ROOT/inp["c_qa"])
  need(q["status"]=="PASS_39_NATIVE_C_SIONNA_RT_CANARY" and not q["failures"],
       "P3_NATIVE_C_NOT_PASS")
  p1=jf(ROOT/inp["ab_p1_lock"])
  # Explicit full-mode precondition: 3136 native C records required, no
  # SourceFFD H, zero-filling, interpolation or A/B substitution allowed.
  rows=readcsv(ROOT/inp["c_csv"])
  need(len(rows)==39 and len({(r["route"],int(r["pose_id"])) for r in rows})==39,
       "P4_39_C_NATIVE_KEYS_MISSING_OR_DUPLICATE")
  return rat,cfg,p1,rows

def load_route_observations(route,cfg,p1,csv_rows):
  czip=zipfile.ZipFile(ROOT/cfg["sources"]["c_zip"])
  need(czip.testzip() is None,"P4_C_NATIVE_ARCHIVE_BAD_CRC")
  crows=sorted([r for r in csv_rows if r["route"]==route],key=lambda x:int(x["pose_id"]))
  need(len(crows)==13,"P4_ROUTE_MUST_HAVE_13_REAL_C_POSES")
  ti=next(x for x in p1["base_assets"] if x["kind"]=="TIMELINE_TNONE" and "timeline_"+route+"_" in x["path"])
  timeline=readcsv(ROOT/ti["path"])
  ids=[int(t["pose_id"]) for t in timeline]
  need(len(ids)==len(set(ids)) and len(ids)==cfg["sources"]["routes_n"][route],
       "P4_TIME_OR_POSE_ID_INVALID")
  need(np.all(np.diff([float(z["t_s"]) for z in timeline])>0),"TIME_NOT_INCREASING")
  t=np.array([float(z["t_s"]) for z in timeline])
  gt=np.array([[float(z["x"]),float(z["y"]),math.radians(float(z["yaw_body_deg"]))] for z in timeline])
  need(np.all(np.isfinite(gt)),"NONFINITE_P4_GT_LABEL")
  cases={}
  Hfiles={}
  for anchor in ("A","B"):
    case=next(x for x in p1["primary_cases"] if x["case_id"]==route+"_a"+anchor+"_m0")
    cases[anchor]=case
    for channel,field in (("full","full_path"),("los","los_path")):
      f=ROOT/case[field]
      item=next(v for v in p1["base_assets"] if v["path"]==case[field])
      need(f.is_file() and sha(f)==item["sha256"] and f.stat().st_size==item["bytes"],
           "ORIGINAL_AB_REAL_H_SHA_CHANGED:"+str(f))
      Hfiles[(anchor,channel)]=np.load(f,mmap_mode="r",allow_pickle=False)
  z=np.full((len(t),2,3,2),np.nan)
  available=np.zeros(len(t),bool)
  taps=np.full((13,2,3),-1,dtype=int)
  route_keys=[]
  for j,r in enumerate(crows):
    pid=int(r["pose_id"])
    need(pid in ids,"C_NATIVE_NOT_ON_ORIGINAL_TIME_AXIS")
    k=ids.index(pid)
    tr=timeline[k]
    delta=np.array([float(tr["x"])-float(r["x_m"]),float(tr["y"])-float(r["y_m"])])
    ya=abs(((float(tr["yaw_body_deg"])-float(r["yaw_deg"])+180)%360)-180)
    dt=abs(float(tr["t_s"])-float(r["original_t_s"]))
    need(float(np.max(abs(delta)))<=1e-6 and ya<=1e-6 and dt<=1e-9,
         "C_NATIVE_POSE_OR_TIME_MISMATCH:"+route+":"+str(pid))
    archive_key=f"traces/P3_NATIVE_C_{route}_pose{pid}_full.npz"
    raw=czip.read(archive_key)
    need(shab(raw)==r["file_sha256"],"C_NATIVE_REAL_NPZ_SHA_CHANGED:"+archive_key)
    with np.load(io.BytesIO(raw),allow_pickle=False) as native:
      need(int(native["pose_id"])==pid and native["route"].item()==route and
           native["H_native_los"].shape==(N,2,2) and native["H_native_full"].shape==(N,2,2),
           "C_NATIVE_ORIGINAL_RF_NOT_MATCHED")
      for i,channel in enumerate(("los","full")):
        Hc=np.asarray(native["H_native_"+channel])
        need(np.isfinite(Hc).all(),"C_NATIVE_NONFINITE")
        zz,ix=obs(Hc)
        val=float(r["native_LoS_signed_s"] if channel=="los" else r["native_Full_signed_s"])
        need(abs(zz[1]-val)<=1e-9,"P3_C_NATIVE_S_RATIO_PARITY")
        taps[j,i,2]=ix
        z[k,i,2]=zz
    for ai,anchor in enumerate(("A","B")):
      case=cases[anchor]
      S=jf(ROOT/case["samples_path"])[pid]
      # Archived original sample may be rounded by <=1e-6 m/degree
      need(max(abs(S["x"]-gt[k,0]),abs(S["y"]-gt[k,1]))<=1e-6 and
          abs(((S["yaw_body_deg"]-math.degrees(gt[k,2])+180)%360)-180)<=1e-6,
          "A_B_ORIGINAL_SAMPLES_POSE_MISMATCH")
      for i,channel in enumerate(("los","full")):
        zz,ix=obs(np.asarray(Hfiles[(anchor,channel)][pid]))
        z[k,i,ai]=zz
        taps[j,i,ai]=ix
    available[k]=True
    route_keys.append(dict(route=route,pose_id=pid,time_s=t[k],original_timeline_k=k,
         pilot_index=j,source="A_B_C_NATIVE_REAL_RF_AT_ORIGINAL_POSE"))
  need(int(available.sum())==13 and np.count_nonzero(np.isfinite(z[:,:,0,0]))==26,
       "EXPECTED_13_SPARSE_EVENTS_ONLY")
  no_new_C_count=len(t)-int(available.sum())
  need(no_new_C_count==len(t)-13,"MISSING_C_UNDERCOUNTED")
  czip.close()
  return t,gt,z,available,route_keys,taps,cases

def stage_fdd(cfg,p1):
  names=[("LP_plus45_bank.npz",cfg["sources"]["bank_plus_sha256"]),
         ("LP_minus45_bank.npz",cfg["sources"]["bank_minus_sha256"])]
  parent=ROOT.parent;manifest={}
  for name,h in names:
    candidate=list(BANKROOT.rglob(name))
    need(len(candidate)==1 and sha(candidate[0])==h,"BANK_SOURCE_SHA_ERROR:"+name)
    target=parent/name
    need(not target.exists() and not target.is_symlink(),"BANK_ALREADY_PRESENT_IN_SCRATCH")
    target.symlink_to(candidate[0]);manifest[name]=h
  (parent/"BANK_MANIFEST.json").write_text(json.dumps({"npz_sha256":manifest}))
  (parent/"ffd_p0p3/out").mkdir(parents=True,exist_ok=True)
  sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
  sys.path.insert(0,str(ROOT/"research/FFD_P0P3_20261016"))
  import core,r2_bias_replay
  from source_model import SourceFFD
  source=SourceFFD()
  need(np.array_equal(source.freqs,6250400000.+DF*np.arange(N)),"P4_FDD_SOURCE_GRID_ERROR")
  return core,r2_bias_replay,source

def filter_route(t,controls,x0,z,available,case_A,source,core,cfg,channel):
  """P4 online signature deliberately has NO truth or true bias input."""
  n=len(t);narm=len(ARMS);J=len(cfg["arms"])
  need(narm==J,"ARM_CONFIG_DRIFT")
  outx=np.full((n,narm,4),np.nan);outP=np.full((n,narm,4,4),np.nan)
  priorx=outx.copy();priorP=outP.copy()
  stat=np.full((n,narm),"NOT_RUN",dtype="<U24")
  nis=np.full((n,narm),np.nan)
  Hstore=np.full((n,narm,3,4),np.nan)
  nustore=np.full((n,narm,3),np.nan)
  zhat=np.full((n,narm,3),np.nan)
  Sstore=np.full((n,narm,3,3),np.nan)
  Kstore=np.full((n,narm,4,3),np.nan)
  packet_offered=np.zeros((n,narm),np.int16)
  component_offered=np.zeros((n,narm),np.int16)
  pilots=np.where(available)[0]
  need(len(pilots)==13,"EXPECTED_13_NATIVE_EPOCHS")
  k_to_ord={int(k):i for i,k in enumerate(pilots)}
  P0=np.diag([.01,.01,math.radians(5)**2,math.radians(.1)**2])
  xstart=np.r_[x0,0.]
  states={arm:(xstart.copy(),P0.copy()) for arm in ARMS}
  invalid=set();failed=[]
  for k in range(n):
    for j,arm in enumerate(ARMS):
      if arm in invalid:
        stat[k,j]="INVALID_PREVIOUS"
        continue
      x,P=states[arm]
      try:
        if k>0:
          ds=float(controls["ds_odom"][k]);dt=float(controls["dt_s"][k])
          da=float(controls["dtheta_gyro"][k])
          need(dt>0 and np.isfinite([ds,dt,da]).all(),"BAD_PREDICTION_INCREMENTS")
          Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
          x,P,_,_=core.predict(x,P,ds,da,dt,Q)
        priorx[k,j]=x;priorP[k,j]=P
        if arm=="DR4":xx,PP,status=x,P,"DR_ONLY"
        elif k not in k_to_ord:xx,PP,status=x,P,"PREDICT_NO_RF"
        else:
          ord_idx=k_to_ord[k]
          spec=cfg["arms"][j]
          sched=spec["epochs"]
          allowed=(sched=="all13" or (isinstance(sched,list) and ord_idx in sched))
          if not allowed:
            xx,PP,status=x,P,"SKIPPED_BUDGET"
          else:
            anc=spec["anchors"];dim=2 if arm=="J4_A13" else len(anc)
            if arm=="J4_A13":
              zz=z[k,channel,0,:]
              model=lambda v:source.model(v,case_A)
            else:
              zz=z[k,channel,[{"A":0,"B":1,"C":2}[a] for a in anc],0]
              model=lambda v,ac=anc:range_h(v,ac)
            zz=np.asarray(zz,dtype=float).reshape(-1)
            need(len(zz)==dim and np.isfinite(zz).all(),"MISSING_NATIVE_RF_PACKET")
            variance=np.diag([RR,RS]) if arm=="J4_A13" else np.eye(dim)*RR
            xx,PP,info=core.gaussian_update(x,P,zz,model,variance,gate_threshold=THRESH[dim])
            status="APPLIED" if info["accepted"] else "REJECT"
            need((info["NIS"]<=THRESH[dim])==bool(info["accepted"]),"WRONG_GATE_DIMENSION")
            packet_offered[k,j]=len(anc)
            component_offered[k,j]=dim
            nis[k,j]=info["NIS"]
            Hstore[k,j,:dim]=info["H"]
            nustore[k,j,:dim]=info["innovation"]
            zhat[k,j,:dim]=zz-info["innovation"]
            Sstore[k,j,:dim,:dim]=info["S"]
            Kstore[k,j,:,:dim]=info["K"]
        need(np.isfinite(xx).all() and np.isfinite(PP).all(),"P4_NONFINITE_STATE")
        need(np.linalg.eigvalsh((PP+PP.T)/2).min()>0 and
             np.max(abs(PP-PP.T))<=1e-10,"P4_NON_PD_COV")
        outx[k,j]=xx;outP[k,j]=PP;stat[k,j]=status
        states[arm]=(xx.copy(),PP.copy())
      except Exception as exc:
        invalid.add(arm)
        stat[k,j]="INVALID"
        failed.append(dict(step=k,time_s=float(t[k]),arm=arm,error=repr(exc),xprior=x.tolist()))
  return dict(xpost=outx,Ppost=outP,xprior=priorx,Pprior=priorP,status=stat,nis=nis,
       H=Hstore,innovation=nustore,h=zhat,S=Sstore,K=Kstore,
       packets=packet_offered,components=component_offered),failed

def score(result,t,truth,level,channel,route):
  """Offline ONLY: true pose does not appear in filter_route signature."""
  ret=[];ev=t>=30.;n=int(np.count_nonzero(ev))
  for j,arm in enumerate(ARMS):
    x=result["xpost"][:,j,:];P=result["Ppost"][:,j,:,:];stat=result["status"][:,j]
    good=np.isfinite(x[ev]).all() and np.isfinite(P[ev]).all()
    if not good:
      ret.append(dict(route=route,channel=channel,bias=level,arm=arm,status="INVALID",n_valid=0,n_expected=n))
      continue
    dif=x[ev,:3]-truth[ev,:3];dif[:,2]=wrap(dif[:,2])
    br=x[ev,3]-math.radians(BIAS[level])
    h2=dif[:,2]**2;xy2=np.sum(dif[:,:2]**2,axis=1);b2=br**2
    pose_cov=P[ev,:3,:3]
    nees_pose=np.einsum('ij,ij->i',dif,np.linalg.solve(pose_cov,dif[:,:,None])[:,:,0])
    nees_heading=h2/P[ev,2,2]
    offered=int(result["packets"][:,j].sum())
    comp=int(result["components"][:,j].sum())
    ret.append(dict(route=route,channel=channel,bias=level,arm=arm,
       status="COMPLETE",n_valid=n,n_expected=n,independent_scenes=1,
       heading_rmse_deg=math.degrees(math.sqrt(float(h2.mean()))),
       xy_rmse_m=math.sqrt(float(xy2.mean())),
       bias_rmse_deg_s=math.degrees(math.sqrt(float(b2.mean()))),
       bias_final_est_dps=math.degrees(float(x[-1,3])),
       heading_nees_mean=float(nees_heading.mean()),
       pose_nees_mean=float(nees_pose.mean()),
       heading95=float(np.mean(nees_heading<=3.841458820694124)),
       pose95=float(np.mean(nees_pose<=7.814727903251179)),
       offered_rf_packets=offered,offered_scalar_components=comp,
       applied_epochs=int(np.count_nonzero(stat=="APPLIED")),
       rejected_epochs=int(np.count_nonzero(stat=="REJECT")),
       predicted_no_rf=int(np.count_nonzero(stat=="PREDICT_NO_RF")),
       skipped_budget_epochs=int(np.count_nonzero(stat=="SKIPPED_BUDGET")),
       failed_epochs=int(np.count_nonzero((stat=="INVALID")|(stat=="INVALID_PREVIOUS"))),
       available_native_C_epochs=13,total_route_steps=len(t),
       comment="Sparse 13 actual Native C pilot epochs, one scene, simulator common timestamp not hardware clock"))
  return ret

def execute(route,out):
  rat,cfg,p1,rows=load_and_check()
  need(route in ("R2","R4","R5"),"UNRECOGNIZED_ROUTE")
  t,truth,z,avail,keys,taps,cases=load_route_observations(route,cfg,p1,rows)
  core,old_replay,source=stage_fdd(cfg,p1)
  route_counts=[];scores=[];all_fails=[]
  out.mkdir(parents=True,exist_ok=False)
  archive_path=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/runs/P2_FROZEN_RANGE_ONLY_41315429738/P2_ALL_28_TRACES_IMMUTABLE.zip"
  need(sha(archive_path)=="063d5c25892365f8d307fc424470b5066db36fa5f825fbf17b5bcb2bcc5531c3",
       "ORIGINAL_P2_FULL_TIMELINE_COMPARISON_SHA_CHANGED")
  p2z=zipfile.ZipFile(archive_path)
  trace_dir=out/"traces";trace_dir.mkdir()
  for level in ("B0","L2"):
    # Read the EXACT archived P2 sensor controls and common initialization.
    # Reconstructing from rounded timeline CSV would introduce small changes
    # and violate the fixed-control P4 comparison.
    reference=f"traces/{route}_aA_m0_full_{level}_seed0_P2_4STATE.npz"
    with np.load(io.BytesIO(p2z.read(reference)),allow_pickle=False) as baseline:
      need(len(baseline["t_s"])==len(t) and np.max(abs(baseline["t_s"]-t))<=1e-9,
           "P4_P2_TIMELINE_NOT_IDENTICAL")
      controls={name:baseline[name].copy() for name in ("ds_odom","dtheta_gyro","dt_s")}
      controls["t_s"]=baseline["t_s"].copy()
      x0=baseline["initial_x0"][:3].copy()
      original_P0=baseline["initial_P0"].copy()
      need(np.max(abs(original_P0-np.diag([.01,.01,math.radians(5)**2,math.radians(.1)**2])))<=1e-12,
           "P4_P2_INITIAL_P0_CHANGED")
    for channel_index,channel in enumerate(("los","full")):
      for anchor_index,anchor in enumerate(("A","B")):
        fname=f"{route}_a{anchor}_m0_{channel}_{level}_seed0_P2_4STATE.npz"
        raw=p2z.read("traces/"+fname)
        with np.load(io.BytesIO(raw),allow_pickle=False) as prior:
          need(len(prior["t_s"])==len(t) and
               np.max(abs(prior["t_s"]-t))<=1e-9 and
               np.array_equal(prior["ds_odom"],controls["ds_odom"]) and
               np.array_equal(prior["dtheta_gyro"],controls["dtheta_gyro"]) and
               np.array_equal(prior["dt_s"],controls["dt_s"]) and
               np.array_equal(prior["initial_x0"][:3],x0),
               "P4_SENSOR_INPUT_NOT_IDENTICAL_TO_P2:"+fname)
          for k in np.where(avail)[0]:
            need(np.max(abs(prior["z_r_s"][k]-z[k,channel_index,anchor_index]))<=1e-9,
                 "P4_ORIGINAL_AB_H_TO_P2_PACKET_NOT_IDENTICAL:"+fname+":"+str(k))
      result,fail=filter_route(t,controls,x0,z,avail,cases["A"],source,core,cfg,channel_index)
      scores.extend(score(result,t,truth,level,channel,route))
      name=f"P4_{route}_{channel}_{level}_7ARM_FULL_TIMELINE.npz"
      fn=trace_dir/name
      np.savez_compressed(fn,
        route=np.array(route),channel=np.array(channel),bias=np.array(level),arm_names=np.array(ARMS),
        t_s=t,pose_id=np.array([int(k["pose_id"]) for k in readcsv(ROOT/next(x for x in p1["base_assets"] if x["kind"]=="TIMELINE_TNONE" and "timeline_"+route+"_" in x["path"])["path"])]),
        native_available=avail,original_native_z=z[:,channel_index],source_tap=taps[:,channel_index],
        ds_odom=controls["ds_odom"],dtheta_gyro=controls["dtheta_gyro"],dt_s=controls["dt_s"],
        initial_x0=np.r_[x0,0.],initial_P0=np.diag([.01,.01,math.radians(5)**2,math.radians(.1)**2]),
        **result)
      for item in fail:all_fails.append({**item,"channel":channel,"bias":level,"route":route})
      route_counts.append(dict(route=route,channel=channel,level=level,
        original_native_epoch_n=int(avail.sum()),predicted_steps=len(t),trace=name,
        sha256=sha(fn),bytes=fn.stat().st_size,
        status={arm:dict(Counter(result["status"][:,j])) for j,arm in enumerate(ARMS)},
        packets={arm:int(result["packets"][:,j].sum()) for j,arm in enumerate(ARMS)},
        scalar_components={arm:int(result["components"][:,j].sum()) for j,arm in enumerate(ARMS)},
        numerical_failures=fail))
      print("P4_ROUTE_TRACK",route,channel,level,"frames",len(t),"real_C_pilot_poses",int(avail.sum()),
            "fail",len(fail),"elapsed_s",round(time.monotonic()-START,2),flush=True)
  p2z.close()
  need(len(scores)==28 and len(route_counts)==4,"P4_CASE_COVERAGE_NOT_COMPLETE")
  # All retained even if an arm is invalid; truthful failures avoid a false PASS.
  fields=sorted(set(k for row in scores for k in row))
  writetable(out/"P4_ROUTE_7ARM_METRICS.csv",scores,fields)
  writetable(out/"P4_NATIVE_PILOT_KEYS.csv",keys,list(keys[0]))
  writetable(out/"P4_ROUTE_FAILURE_LEDGER.csv",all_fails,
             ["route","channel","bias","step","time_s","arm","error","xprior"])
  rec=dict(schema="DLP_P4_SPARSE_NATIVE_ROUTE_EVIDENCE_V1",phase="P4_PILOT_ONLY",
      route=route,status="PASS" if not all_fails and all(r["status"]=="COMPLETE" for r in scores) else "FAIL",
      original_C_real_native_packet_epochs=int(avail.sum()),
      original_full_timeline_steps=len(t),
      never_interpolated_third_C=True,
      full_P4="BLOCKED_MISSING_NATIVE_C_RF_AT_OTHER_TIME_STEPS",
      source_p3_native_zip_sha256=cfg["sources"]["c_zip_sha256"],
      original_p2_all_trace_sha256="063d5c25892365f8d307fc424470b5066db36fa5f825fbf17b5bcb2bcc5531c3",
      frozen_P4_lock_sha256=EXPECTED_SHA,source_pre_run_audit_sha256=rat["auditor_receipt"]["sha256"],
      method_names=ARMS,
      sensor_seed=0,observation_frame="simulated shared pose/time label, not measured clock synchronization",
      scene_independent_count=1,tracks=route_counts,
      n_failures=len(all_fails),trace_evidence_files=len(route_counts),
      metrics_n=len(scores),code_sha256=sha(__file__),
      provenance=dict(github_sha=os.environ.get("GITHUB_SHA"),
          github_run=os.environ.get("GITHUB_RUN_ID"),platform=platform.platform(),
          numpy=np.__version__,seconds=time.monotonic()-START))
  (out/"P4_ROUTE_RECEIPT.json").write_text(json.dumps(rec,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
  return rec

if __name__=="__main__":
  p=argparse.ArgumentParser()
  p.add_argument("--route",choices=("R2","R4","R5"),required=True)
  p.add_argument("--out",required=True)
  p.add_argument("--mode",choices=("pilot","full"),default="pilot")
  args=p.parse_args()
  out=pathlib.Path(args.out)
  try:
    if args.mode=="full":
      rat,cfg,p1,rows=load_and_check()
      missing=sum(cfg["sources"]["routes_n"].values())-len(rows)
      out.mkdir(parents=True,exist_ok=True)
      (out/"P4_FULL_BLOCKED_INPUT.json").write_text(json.dumps(dict(
        status="BLOCKED_MISSING_C_NATIVE_H",expected=3136,found=len(rows),missing=missing,
        source_native_only=True,may_interpolate=False,available_full_R4=False),indent=2)+"\n")
      print("P4_FULL_STOP",missing,"new C native pose/time keys missing",flush=True)
      sys.exit(2)
    v=execute(args.route,out)
    print("P4_ROUTE_RESULT",v["status"],args.route,"ntracks",v["metrics_n"],flush=True)
    sys.exit(0 if v["status"]=="PASS" else 1)
  except Exception as e:
    out.mkdir(parents=True,exist_ok=True)
    (out/"P4_FATAL.json").write_text(json.dumps(dict(status="BLOCKED",error=repr(e),
        traceback=traceback.format_exc(),route=args.route,mode=args.mode),indent=2)+"\n")
    print("P4_ROUTE_FATAL",repr(e),traceback.format_exc(),flush=True)
    sys.exit(1)
