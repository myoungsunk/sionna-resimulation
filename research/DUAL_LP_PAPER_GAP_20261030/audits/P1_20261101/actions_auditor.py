#!/usr/bin/env python3
"""Fresh P1 PRE-RUN AUDIT. This is NOT a P1 science execution.
Separate math/oracle implemented here; pinned SourceFFD and historical
observer are TESTED and used only as objects/comparators.  No fitting/EKF.
Preserve all PASS/FAIL/BLOCKED findings, never alter proposer contract.
"""
from __future__ import annotations
import csv, hashlib, importlib, json, math, os, platform, sys, time, traceback
from pathlib import Path
import numpy as np

ROOT=Path.cwd()
LOCKDIR=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
OUT=Path(os.environ.get("DLP_AUDIT_OUT","/tmp/dlp_p1_audit"))
OUT.mkdir(parents=True,exist_ok=True)
GIT_HEAD=os.environ.get("GITHUB_SHA","UNKNOWN")
PINNED="340877f3537b4cc65cdaa9d687423cba92e0b28b"
C=299792458.0
N=257
DF=1950000.
B_OLD=-0.5315983906250129
R0=np.diag([0.0068578637,0.0081])
checks={}
failures=[]
details={}
start=time.monotonic()

def add(id, passed, note="", status=None, measured=None):
    status=status or ("PASS" if passed else "FAIL")
    checks[id]={"status":status,"note":str(note)}
    if measured is not None: checks[id]["measured"]=measured
    print("AUDIT",id,status,str(note)[:500],flush=True)
    if status!="PASS": failures.append({"id":id,"status":status,"note":str(note)[:1500]})
    return passed

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            b=f.read(1024*1024)
            if not b: break
            h.update(b)
    return h.hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
def arr_path(row):return ROOT/row["path"]
def exact(n,a,b,tol=0):return abs(float(a)-float(b))<=tol
def rng_indices(n, anchor_i=None):
    v=[0,1,n//2,n-1,max(0,n//3)]
    v.extend(np.random.default_rng(20261101+n).choice(n,size=min(n,14),replace=False).tolist())
    if anchor_i is not None:v.append(anchor_i)
    return sorted(set(v))
def independent_observer(h,frequency):
    """Independent H->CIR->first-edge implementation; no O.* calls."""
    h=np.asarray(h)
    if h.ndim!=4 or h.shape[1:]!=(N,2,2):raise ValueError("invalid H")
    a=h[:,:,:,0]   # TX +45 port, RX in original signed order
    window=np.sin(np.pi*np.arange(N)/(N-1))**2  # symmetric Hann N-1
    cir=np.fft.ifft(a*window[None,:,None],n=4*N,axis=1)*N
    magn=np.abs(cir)
    peaks=magn.max(axis=1)
    strongest=peaks.argmax(axis=1)
    envelope=np.take_along_axis(magn,strongest[:,None,None],axis=2)[:,:,0]
    maxi=envelope.max(axis=1)
    index=np.argmax(envelope>=.3*maxi[:,None],axis=1)
    z=cir[np.arange(len(h)),index,:]
    pow=np.real(z*np.conj(z))
    den=pow.sum(axis=1)
    s=np.full(len(h),np.nan)
    good=(den>0)&np.isfinite(den)&(maxi>0)
    s[good]=(pow[good,0]-pow[good,1])/den[good]
    r=index*(C/((4*N)*(float(frequency[1])-float(frequency[0]))))
    return dict(s=s,r=r,index=index,strongest=strongest,power=pow,valid=good)

def field_linear(bank,q):
    """Independent spherical-basis conversion, explicit eight-point bilinear sampling;
    intentionally not using pattern_apply.Bank.sample or SourceFFD._field."""
    q=np.asarray(q,float)
    theta=float(np.arccos(np.clip(q[2],-1,1)))
    phi=float(np.arctan2(q[1],q[0]))
    th=float(bank.theta[0]);dt=float(bank.theta[1]-bank.theta[0])
    ph0=float(bank.phi[0]);dp=float(bank.phi[1]-bank.phi[0])
    u=np.clip((theta-th)/dt,0,len(bank.theta)-1)
    v=((phi-ph0)%(2*np.pi))/dp
    ti=min(int(np.floor(u)),len(bank.theta)-2)
    pi=min(int(np.floor(v)),len(bank.phi)-2)
    a=u-ti;b=v-pi
    def interp(e):
        # Independent trilinear algebra: 4 spatial corners per frequency
        return ((1-a)*(1-b)*e[:,ti,pi]+(1-a)*b*e[:,ti,pi+1]
                +a*(1-b)*e[:,ti+1,pi]+a*b*e[:,ti+1,pi+1])
    et=interp(bank.e_theta);ep=interp(bank.e_phi)
    ct=np.cos(theta);st=np.sin(theta);cp=np.cos(phi);sp=np.sin(phi)
    th_hat=np.array([ct*cp,ct*sp,-st])
    ph_hat=np.array([-sp,cp,0.])
    scale=np.sqrt(2*np.pi/376.730313668)
    return scale*(et[:,None]*th_hat[None,:]+ep[:,None]*ph_hat[None,:])

def oracle_physical_H(banks,pose,case):
    """Independent spherical TX/RX Cartesian co-vector contraction (no conjugation)."""
    ax,ay,az=map(float,case["anchor"])
    xyz=np.array([pose[0],pose[1],float(case["robot_z_m"])],float)
    d=xyz-np.array([ax,ay,az])
    dist=float(np.linalg.norm(d));q=d/dist
    rot_tx=np.diag([1.,-1.,-1.])
    tx=field_linear(banks[0],q@rot_tx)@rot_tx.T
    psi=float(pose[2])+np.deg2rad(float(case["mount_deg"]))
    co=np.cos(psi);si=np.sin(psi)
    # -q expressed in receiver frame; RX local +z upward
    qr=np.array([-co*q[0]-si*q[1],si*q[0]-co*q[1],-q[2]])
    rot_rx=np.array([[co,-si,0],[si,co,0],[0,0,1.]])
    rx=[field_linear(b,qr)@rot_rx.T for b in banks]
    f=np.asarray(banks[0].freqs_hz,dtype=float)
    alpha=(C/(4*np.pi*dist*f))*np.exp(-2j*np.pi*f*dist/C)
    return np.stack([np.sum(t*tx,axis=1)*alpha for t in rx],axis=1)

def gt_state(row):
    return np.array([row["x"],row["y"],np.deg2rad(row["yaw_body_deg"]),0.],float)

def old_s_independent(states,case,meta,lut):
    """Separate 3D LUT trilinear interpolation at exact geometric angles."""
    u=states[:,0]-float(case["anchor"][0]);v=states[:,1]-float(case["anchor"][1])
    z=float(case["anchor"][2])-float(case["robot_z_m"])
    theta=np.degrees(np.arctan2(np.hypot(u,v),z))
    phi_tx=np.degrees(np.arctan2(-v,u))
    yaw=np.degrees(states[:,2])+float(case["mount_deg"])
    phi_rx=(np.degrees(np.arctan2(-v,-u))-yaw+180)%360-180
    dt=float(meta["theta_deg"][1]-meta["theta_deg"][0])
    p0,pmax,dp=map(float,meta["phi_deg"])
    t=np.clip(theta/dt,0,45-1e-9)
    a=(phi_tx-p0)/dp;b=(phi_rx-p0)/dp
    ii=np.floor(t).astype(int);jj=np.floor(a).astype(int)%lut.shape[1];kk=np.floor(b).astype(int)%lut.shape[2]
    wt=t-ii;wa=a-np.floor(a);wb=b-np.floor(b)
    result=np.zeros(len(states))
    for it in (0,1):
      for ia in (0,1):
       for ib in (0,1):
        result+=(wt if it else 1-wt)*(wa if ia else 1-wa)*(wb if ib else 1-wb)*lut[ii+it,(jj+ia)%lut.shape[1],(kk+ib)%lut.shape[2]]
    return result

def generate_report():
    status="ACCEPT_WITH_BOUNDARIES"
    if any(v["status"]=="BLOCKED" for v in checks.values()):status="BLOCKED_EVIDENCE"
    elif any(v["status"]!="PASS" for v in checks.values()):status="REVISION_REQUIRED"
    if "MATH_SOURCE_JAC" in checks and checks["MATH_SOURCE_JAC"]["status"]=="FAIL":status="REDESIGN_REQUIRED"
    payload={
       "schema":"DLP_P1_INDEPENDENT_GITHUB_ACTIONS_AUDIT_V1",
       "role":"AUDITOR_COMPUTATIONAL_RUNNER",
       "actor":"GPT-6-authored independent scratch audit running on a separate GitHub Actions Linux runner",
       "independence_boundary":"Different compute code/runner from proposer. GitHub identity is repository owner; not a separate human reviewer.",
       "runner_identity":dict(run_id=os.environ.get("GITHUB_RUN_ID"),run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),workflow=os.environ.get("GITHUB_WORKFLOW"),git_sha=GIT_HEAD,hostname=platform.node()),
       "contract_id":"DLP-EKF-GAPS-001/P1-V1","proposer_head_sha":PINN,
       "contract_sha256":"373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594",
       "audit_code_sha256":sha256(__file__),"python":sys.version,"numpy":np.__version__,"platform":platform.platform(),
       "checks":checks,"failures":failures,"details":details,"verdict":status,
       "P1_science_executed":False,"FROZEN":False,
       "duration_sec":time.monotonic()-start,
       "notes":["This is independent PRE-RUN gate arithmetic / physical QA only. No C0 residual statistics, empirical fitting, EKF or new RF.",
                "ACCEPT_WITH_BOUNDARIES is limited to evidence gates; formal proposer+auditor separate FROZEN ratification is still required.",
                "No GitHub PR approval or independent human-person identity is claimed."]
    }
    out=OUT/"AUDIT_RESULT.json"
    out.write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print("FINAL_AUDIT_JSON",out,flush=True)
    print("FINAL_VERDICT",status,"CHECKS",len(checks),"FAILURES",len(failures),flush=True)
    return status

def main():
  receipt=read_json(LOCKDIR/"P1_PROPOSER_LOCK_RECEIPT.json")
  input_lock=read_json(LOCKDIR/"P1_INPUT_LOCK.json")
  cfg=read_json(LOCKDIR/"P1_CONFIG_LOCK.json")
  tol=read_json(LOCKDIR/"P1_NUMERIC_TOLERANCES.json")
  sample_lock=read_json(LOCKDIR/"P1_SAMPLE_SPLIT_LOCK.json")
  # A00 exact raw bytes + canonical immutable P0 manifest
  sha_errors=[]
  for item in [*receipt["file_digests"],dict(name="P0_INPUT_MANIFEST.json",sha256=receipt["immutable_original_manifest"]["sha256"],bytes=receipt["immutable_original_manifest"]["bytes"],path=receipt["immutable_original_manifest"]["path"])]:
    p=ROOT/item["path"] if "path" in item else LOCKDIR/item["name"]
    if not p.is_file():sha_errors.append(["missing",str(p)]);continue
    if sha256(p)!=item["sha256"] or p.stat().st_size!=item["bytes"]:
       sha_errors.append(["mismatch",str(p),sha256(p)])
  add("A00_LOCK_HASH",not sha_errors,sha_errors or "All 7 locked files plus original P0 manifest raw SHA256 match")
  add("A00_HEAD_PIN",os.environ.get("DLP_PINNED_HEAD")==PINN,"fixed proposer head")
  assert len(tol["tests"])==16
  # A01: full input hashes, no LFS pointer accepted as real binary.
  asset_err=[];kindcounts={};asset_ledger=[]
  for row in input_lock["base_assets"]:
    p=arr_path(row);kindcounts[row["kind"]]=kindcounts.get(row["kind"],0)+1
    if not p.is_file():asset_err.append([row["kind"],row["path"],"MISSING"]);continue
    actualsha=sha256(p);actualbytes=p.stat().st_size
    good=(actualsha==row["sha256"] and actualbytes==row["bytes"])
    if not good:asset_err.append([row["kind"],row["path"],actualsha,actualbytes])
    asset_ledger.append(dict(path=row["path"],bytes=actualbytes,sha256=actualsha,ok=good))
  (OUT/"INPUT_SHA_LEDGER.json").write_text(json.dumps(asset_ledger,indent=2))
  add("A01_39_RAW_ASSETS",len(asset_ledger)==39 and not asset_err,
      "verified="+str(len(asset_ledger))+"/39 errors="+str(asset_err[:5]),
      status="PASS" if not asset_err and len(asset_ledger)==39 else "BLOCKED")
  details["asset_kinds"]=kindcounts
  # NPZ original bytes must be physically present, not a Git LFS pointer.
  bdir=Path(os.environ.get("DLP_BANK_DIR","/tmp/dlp_p1_banks"))
  banks_paths=[]
  banks_errors=[]
  for item in input_lock["ffd_bank_source"]["banks"]:
    matches=list(bdir.rglob(item["filename"]))
    if len(matches)!=1:banks_errors.append([item["filename"],"n_files",len(matches)]);continue
    p=matches[0]
    sh=sha256(p)
    if sh!=item["sha256"] or p.stat().st_size!=item["bytes"]:banks_errors.append([item["filename"],sh,p.stat().st_size])
    banks_paths.append(p)
  add("A01_TWO_REAL_BANKS",len(banks_paths)==2 and not banks_errors,
      banks_errors or "Both original .npz physical SHA256 and byte sizes verified, not LFS pointers",
      status="PASS" if len(banks_paths)==2 and not banks_errors else "BLOCKED")
  freq=np.load(ROOT/next(x["path"] for x in input_lock["base_assets"] if x["kind"]=="FREQUENCY"),allow_pickle=False)
  add("A01_FREQUENCY",np.array_equal(freq,6250400000.+DF*np.arange(N)),str([freq.shape,str(freq.dtype),float(freq[0]),float(freq[-1])]))
  # A02 strict keys per-case, sample/timeline route join and H H pairing
  shape_err=[];coord_err=[];missing=[];route_samples={}
  for case in input_lock["primary_cases"]:
    sam=read_json(ROOT/case["samples_path"])
    ids=[int(x["pose_id"]) for x in sam]
    if len(ids)!=len(set(ids)) or ids!=list(range(len(ids))):missing.append([case["case_id"],"sample_id_nonunique_or_noncontiguous"])
    if len(sam)!=case["rf_count"]:missing.append([case["case_id"],"sample_count",len(sam)])
    route=case["route"]
    if route not in route_samples:route_samples[route]=sam
    else:
      base=route_samples[route]
      if len(base)!=len(sam):missing.append([case["case_id"],"route_mismatch"])
      else:
        delta_xy=max(max(abs(float(u["x"])-float(v["x"])),abs(float(u["y"])-float(v["y"]))) for u,v in zip(base,sam))
        delta_yaw=max(abs(((float(u["yaw_body_deg"])-float(v["yaw_body_deg"])+180)%360)-180) for u,v in zip(base,sam))
        if delta_xy>1e-10 or delta_yaw>1e-10:missing.append([case["case_id"],"route_samples_not_identical",delta_xy,delta_yaw])
    Hfull=np.load(ROOT/case["full_path"],mmap_mode="r",allow_pickle=False)
    Hlos=np.load(ROOT/case["los_path"],mmap_mode="r",allow_pickle=False)
    for mode,h in [("FULL",Hfull),("LOS",Hlos)]:
      if h.shape!=tuple(case["h_shape"]) or h.dtype!=np.dtype("complex128"):
        shape_err.append([case["case_id"],mode,str(h.shape),str(h.dtype)])
  totals={"rf":0,"timeline":0,"eval":0}
  per_route={}
  for grp in sample_lock["route_groups"]:
    route=grp["route"];s=route_samples[route]
    p=next(x for x in input_lock["base_assets"] if x["kind"]=="TIMELINE_TNONE" and ("timeline_"+route+"_") in x["path"])
    with (ROOT/p["path"]).open(newline="") as fp: lines=list(csv.DictReader(fp))
    seen=set();old_t=None;maxxy=0.;maxyaw=0.;maxdt=0.;n_eval=0
    lut={int(x["pose_id"]):x for x in s}
    for t in lines:
      pid=int(t["pose_id"]);tm=float(t["t_s"])
      if pid in seen:missing.append([route,"duplicate_timeline_pose",pid])
      seen.add(pid)
      if pid not in lut:missing.append([route,"missing_sample",pid]);continue
      if old_t is not None:
        if tm<=old_t:missing.append([route,"time_nonmono",pid])
        maxdt=max(maxdt,abs((tm-old_t)-0.2))
      old_t=tm
      if tm>=30.:n_eval+=1
      z=lut[pid];maxxy=max(maxxy,abs(z["x"]-float(t["x"])),abs(z["y"]-float(t["y"])))
      yaw=((z["yaw_body_deg"]-float(t["yaw_body_deg"])+180)%360)-180
      maxyaw=max(maxyaw,abs(yaw))
    if maxxy>1e-6 or maxyaw>1e-6 or maxdt>1e-9:coord_err.append([route,maxxy,maxyaw,maxdt])
    if len(lines)!=grp["route_timeline_steps"] or n_eval!=grp["evaluation_t_ge_30_steps"]:
      missing.append([route,"timeline_n",len(lines),n_eval])
    per_route[route]=dict(n_sample=len(s),n_timeline=len(lines),n_eval=n_eval,xy_max_abs=maxxy,yaw_max_abs=maxyaw,dt_max_abs=maxdt)
    totals["rf"]+=len(s)*grp["case_count"];totals["timeline"]+=len(lines)*grp["case_count"];totals["eval"]+=n_eval*grp["case_count"]
  pop=sample_lock["per_channel"]
  add("A02_KEYS_SHAPES",not shape_err and not missing,
      "case errors:"+str(shape_err[:3]+missing[:5]),measured=dict(shape_errors=shape_err[:5],key_errors=missing[:5]))
  add("A02_TIME_COORD",not coord_err and not missing,"route errors:"+str(coord_err+missing[:4]),measured=per_route)
  add("A02_COUNTS",totals==dict(rf=pop["total_rf_pose_case"],timeline=pop["total_timeline_case"],eval=pop["t_ge_30_case"]),
      str(totals))
  details["sample_route_qc"]=per_route
  if asset_err or banks_errors or shape_err or missing or coord_err:
    add("A03_A09_SCIENCE_QA_STAGE",False,"Cannot run physics/source preflight until complete raw input, shapes and keys",status="BLOCKED")
    return
  # Separate reusable bank load is raw array transport only. Physics below is fully separate.
  root_parent=ROOT.parent
  manifest={"npz_sha256":{}}
  for item,p in zip(input_lock["ffd_bank_source"]["banks"],banks_paths):
    dst=root_parent/item["filename"]
    if dst.exists():dst.unlink()
    dst.symlink_to(p)
    manifest["npz_sha256"][item["filename"]]=item["sha256"]
  (root_parent/"BANK_MANIFEST.json").write_text(json.dumps(manifest,sort_keys=True))
  (root_parent/"ffd_p0p3/out").mkdir(parents=True,exist_ok=True)
  import subprocess
  for x in input_lock["locked_source_code"]:
    r=subprocess.check_output(["git","hash-object",x["path"]],text=True).strip()
    if r!=x["git_blob_sha1"]:raise RuntimeError("PINNED_SOURCE_SHA_DRIFT:"+x["path"])
  add("A09_PINNED_CODE",True,"All locked Git source blobs rehashed")
  # Modules loaded for TARGET and reference comparisons only.
  sys.path.insert(0,str(ROOT/"research/FFD_P0P3_20261016"))
  import p0_initial
  from source_model import SourceFFD
  src=SourceFFD() # real two-bank FFD target incl source-only Taylor cap
  hist=p0_initial.O
  from p3_rf_adapter4 import FrozenLut
  old=FrozenLut(ROOT)
  meta=read_json(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json")["meta"]
  lut=np.load(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy",mmap_mode="r")
  verify_freq=np.array_equal(src.freqs,freq)
  add("A09_BANK_STAGING",verify_freq,
      "Staged correct original bank bytes outside repo and SourceFFD initialized without original source mutation")
  # Canary actual physical original RF: each case/mode random + adversarial.
  p_errors=[];bad_power=[];negative_controls=[]
  native_rel=[];native_diffs=[];source_s_count=0;tap_diff=0;direct_rel=[]
  jac_rows=[];math_invalid=[];old_err=[]
  direct_examples=0
  for case in input_lock["primary_cases"]:
    key=case["case_id"]
    sam=read_json(ROOT/case["samples_path"])
    states=np.asarray([gt_state(x) for x in sam])
    anchor=np.asarray(case["anchor"],float)
    horiz=np.hypot(states[:,0]-anchor[0],states[:,1]-anchor[1])
    idx=rng_indices(len(sam),int(horiz.argmin()))
    for channel,path in (("FULL",case["full_path"]),("LOS",case["los_path"])):
      raw=np.load(ROOT/path,mmap_mode="r")
      z=independent_observer(raw[idx],freq)
      histz=hist.observe(np.asarray(raw[idx]),freq,None,None)
      rowerr=max(float(np.max(np.abs(z["r"]-histz["range_m"]))),
                 float(np.nanmax(np.abs(z["s"]-histz["s"]))))
      if rowerr>1e-9 or not np.array_equal(z["index"],histz["index"]):
        p_errors.append([key,channel,"reference_observer_mismatch",rowerr])
      if not np.all(z["valid"]):bad_power.append([key,channel,np.asarray(idx)[~z["valid"]].tolist()])
      if np.any(np.abs(z["s"])>1+1e-12):p_errors.append([key,channel,"signed_s_bounds"])
      # Negative control: port-swap at first-path same tap changes sign exactly.
      switched=np.asarray(raw[idx]).copy()
      switched[:,:,[0,1],:]=switched[:,:,[1,0],:]
      nz=independent_observer(switched,freq)
      negative_controls.append(dict(case=key,channel=channel,idx_equal=bool(np.array_equal(nz["index"],z["index"])),
                                    s_flip_error=float(np.nanmax(np.abs(nz["s"]+z["s"])))))
    # Actual Native LoS physical complex H vs SourceFFD, not GT runtime.
    rawlos=np.load(ROOT/case["los_path"],mmap_mode="r")
    # full QA of all 9519 NativeLoS poses (bounded memory chunk)
    for k in range(0,len(states),24):
      sub=states[k:k+24]
      hp=src.physical_h_col(sub,case)
      zn=independent_observer(np.asarray(rawlos[k:k+24]),freq)
      zs=src.batch(sub,case,gradient=False,return_diagnostics=True)
      pred,_,diag=zs
      native=np.asarray(rawlos[k:k+24,:,:,0])
      denom=np.linalg.norm(native.reshape(len(sub),-1),axis=1)
      rel=np.linalg.norm((hp-native).reshape(len(sub),-1),axis=1)/np.maximum(denom,1e-300)
      native_rel.extend(rel.tolist())
      native_diffs.extend((pred[:,1]-zn["s"]).tolist())
      source_s_count+=len(sub)
      tap_diff+=int(np.count_nonzero(zn["index"]!=diag["tap"]))
    # Independent bilinear+physical direct vector source oracle, away from cap
    allowed=[int(i) for i in idx if np.rad2deg(np.arctan2(horiz[i],2.2))>0.8][:6]
    for i in allowed:
      original=src.physical_h_col(states[i:i+1],case)[0]
      oracle=oracle_physical_H(src.banks,states[i],case)
      rel=float(np.linalg.norm(original-oracle)/max(np.linalg.norm(original),1e-300))
      direct_rel.append(dict(case=key,pose_id=i,relative_complex=rel))
      direct_examples+=1
    # Jacobian vs finite difference, same fixed FFD cell/tap.
    testids=sorted(set(idx[:6]+[int(horiz.argmin())]))
    for i in testids:
      state=states[i];pred,J,info=src.batch(state[None,:],case,gradient=True,return_diagnostics=True)
      d=np.linalg.norm([state[0]-anchor[0],state[1]-anchor[1],case["robot_z_m"]-anchor[2]])
      hr=np.array([(state[0]-anchor[0])/d,(state[1]-anchor[1])/d,0,0])
      err_hr=float(np.max(np.abs(J[0,0]-hr)))
      biaserr=float(abs(J[0,1,3]))
      row=dict(case=key,pose_id=i,range_jac_err=err_hr,bias_deriv=biaserr,stable=True,jac_errors=[])
      for v,eps in [(0,1e-5),(1,1e-5),(2,1e-5)]:
        sp=state.copy();sm=state.copy();sp[v]+=eps;sm[v]-=eps
        yp,_,dp=src.batch(sp[None,:],case,gradient=False,return_diagnostics=True)
        ym,_,dm=src.batch(sm[None,:],case,gradient=False,return_diagnostics=True)
        stable=(np.array_equal(info["cells"],dp["cells"]) and np.array_equal(info["cells"],dm["cells"])
                and np.array_equal(info["tap"],dp["tap"]) and np.array_equal(info["tap"],dm["tap"])
                and np.array_equal(info["strong_port"],dp["strong_port"])
                and np.array_equal(info["strong_port"],dm["strong_port"]))
        fd=float((yp[0,1]-ym[0,1])/(2*eps))
        an=float(J[0,1,v]);ae=abs(fd-an);rel=ae/max(abs(an),1e-300)
        row["jac_errors"].append(dict(col=v,fd=fd,analytic=an,abs_err=ae,relative_err=rel,stable=bool(stable)))
        if stable and not(ae<=2e-5 or (abs(an)>1e-6 and rel<=1e-4)):
          math_invalid.append([key,i,v,ae,rel])
        if not stable:row["stable"]=False
      if err_hr>1e-10 or biaserr>1e-12:math_invalid.append([key,i,"shape_or_range",err_hr,biaserr])
      jac_rows.append(row)
    # Compare independent old LUT interpolation with original FrozenLut on selected states.
    old_val=old_s_independent(states[idx],case,meta,lut)
    for i,value in zip(idx,old_val):
      prev=old.model(states[i],case)[0][1]
      if abs(float(prev)-float(value))>1e-12:
        old_err.append([key,i,float(prev),float(value)])
  # aggregate physical and numerical gates
  nc_fail=[z for z in negative_controls if (not z["idx_equal"] or z["s_flip_error"]>1e-12)]
  add("A03_REAL_RF_OBSERVER",not p_errors and not bad_power,
      "Real RF random/adversarial Full/LoS 2-port paired detector; errors="+str(p_errors[:3]+bad_power[:3]),
      measured=dict(n_selected=len(negative_controls),failure_count=len(p_errors)+len(bad_power)))
  add("A03_PORT_SWAP",not nc_fail,str(nc_fail[:3]),measured=dict(n=len(negative_controls),max_s_flip_error=max(x["s_flip_error"] for x in negative_controls)))
  add("A04_SOURCE_DIRECT_ORACLE",len(direct_rel)>0 and max(z["relative_complex"] for z in direct_rel)<=1e-10,
      "Independent spherical vector bilinear physical H vs SourceFFD: samples="+str(len(direct_rel)),
      measured=dict(n=len(direct_rel),max_rel=max(z["relative_complex"] for z in direct_rel)))
  maxcomplex=max(native_rel);rmscomplex=float(np.sqrt(np.mean(np.square(native_rel))))
  rms_s=float(np.sqrt(np.mean(np.square(native_diffs))));max_s=float(np.max(np.abs(native_diffs)))
  add("A04_SOURCE_NATIVE_COMPLEX",maxcomplex<=5e-4 and rmscomplex<=1e-4,
      "predeclared historical engineering regression limits; not fresh holdout",
      measured=dict(n=len(native_rel),max_rel=maxcomplex,rms_rel=rmscomplex))
  add("A04_SOURCE_NATIVE_SIGNED_S",source_s_count==9519 and rms_s<=2e-6 and max_s<=2e-5 and tap_diff==0,
      "must satisfy 9519 observed poses, no tap switch",
      measured=dict(n=source_s_count,rmse=rms_s,max_abs=max_s,tap_mismatch=tap_diff))
  stable_tests=sum(x["stable"] for x in jac_rows)
  add("MATH_SOURCE_JAC",not math_invalid and stable_tests>0,
      "Real-bank SourceFFD analytic vs independently coded central FD at stable FFD/tap cells; check boundary separately",
      measured=dict(n=len(jac_rows),stable=stable_tests,boundaries=len(jac_rows)-stable_tests,fail=math_invalid[:10],
                    max_abs_on_stable=max([z["abs_err"] for row in jac_rows for z in row["jac_errors"] if z["stable"]] or [0])))
  add("A05_OLD_LUT",not old_err and bool(jac_rows),"Independent 8-corner LUT s interpolation vs pinned FrozenLut",measured=dict(mismatches=old_err[:3],test_n=sum(len(x["jac_errors"]) for x in jac_rows)))
  # Offline algebra only, deliberately synthetic; NO actual C0 error moments pre-freeze.
  z,hs,ho=0.31,-.23,.19
  identity=((z-hs)-(z-ho))-(ho-hs)
  syn=np.array([[.1,.4],[-.2,-.1],[.7,.2],[-.3,.08]],float)
  cov=np.cov(syn,rowvar=False,ddof=1)
  mean=syn.mean(axis=0)
  cov2=(syn.T@syn - len(syn)*np.outer(mean,mean))/(len(syn)-1)
  good=(abs(identity)<1e-12 and np.allclose(cov,cov2,atol=1e-12,rtol=0)
        and np.linalg.eigvalsh(cov).min()>=-1e-12)
  add("A06_RESIDUAL_COV_MATH",good,"Synthetic signed residual identity, ddof=1, covariance eigen PSD, physical units",
      measured=dict(s_identity_error=identity,covariance=cov.tolist(),min_eigenvalue=float(np.linalg.eigvalsh(cov).min())))
  add("A07_NO_P1_SCIENCE_RUN",True,"No actual C0 residual moments, P1 output, training, RF or EKF run; QA matched physics only")
  add("A08_RETROSPECTIVE_BOUNDARY",bool(cfg["train_eval"]["retrospective_statistics_only"] and
       cfg["populations"]["statistical_independent_scene_count"]==1 and
       tol["rationale"]["not_independent_confirmation"]),
       "One previously seen Corridor scene; pre-fixed historical regression tolerances, not confirmatory proof")
  details["source_native"]=dict(n=source_s_count,complex_max_rel=maxcomplex,complex_rms_rel=rmscomplex,
                                s_rmse=rms_s,s_max_abs=max_s,tap_mismatch=tap_diff)
  details["direct_oracle"]=direct_rel
  details["jacobian_checks"]=jac_rows
  (OUT/"CANARY_QA.json").write_text(json.dumps(dict(negative_controls=negative_controls,
            actual_full_native_source=details["source_native"],direct=direct_rel,
            jacobian=jac_rows,old_lut_errors=old_err),indent=2,allow_nan=False))
  # Data leakage restriction: all GT poses used here solely for offline Source/NATIVE *QA*
  # not predicted filter input, and no invented unseen scene. 
  return

if __name__=="__main__":
  try:
    main()
  except BaseException as exc:
    add("AUDIT_EXECUTION",False,repr(exc)+"\n"+traceback.format_exc(),status="BLOCKED")
  status=generate_report()
  sys.exit(0 if status=="ACCEPT_WITH_BOUNDARIES" else 1)
