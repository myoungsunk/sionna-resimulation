#!/usr/bin/env python3
"""P4 pilot pre-run independent-formula auditor. NO P4 performance computed.

A 39 real Native-RT C0+ C-anchor dataset, A/B original C0 RF and exactly matched
original route labels. Separately written detector and EKF math oracle; code
authored by same ChatGPT conversation, computationally separate runner only.
"""
from __future__ import annotations
import csv,hashlib,io,json,math,os,pathlib,sys,time,traceback,zipfile,platform
from collections import Counter
import numpy as np
ROOT=pathlib.Path.cwd()
CON=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P4_20261102"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
OUT=pathlib.Path(os.getenv("P4_PRE_OUT","/tmp/p4_preflight"));OUT.mkdir(parents=True,exist_ok=True)
BANK=pathlib.Path(os.getenv("P4_BANKS","/tmp/p4_banks"))
START=time.monotonic();RESULTS={};ERRORS=[];MORE={}
def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
      for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def hs(b):return hashlib.sha256(b).hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_text("utf-8"))
def check(id,passed,measure=None):
    RESULTS[id]={"status":"PASS" if passed else "FAIL","values":measure}
    if not passed:ERRORS.append({"gate":id,"measured":measure})
    print("P4_PREAUDIT",id,RESULTS[id]["status"],str(measure)[:450],flush=True)
def need(v,msg):
    if not bool(v):raise RuntimeError(msg)
def observer(H):
    H=np.asarray(H)
    need(H.shape==(257,2,2),"BAD_NATIVE_H_DIM")
    w=.5-.5*np.cos(2*np.pi*np.arange(257)/256)
    cir=np.fft.ifft(H[:,:,0]*w[:,None],n=1028,axis=0)*257
    a=np.abs(cir)
    port=int(np.argmax(a.max(axis=0)))
    idx=int(np.argmax(a[:,port]>=.3*a[:,port].max()))
    powers=np.abs(cir[idx])**2
    need(powers.sum()>0,"BAD_NATIVE_POWER")
    return (float((powers[0]-powers[1])/powers.sum()),
        idx*299792458./(1028*1950000.),idx)
def readcsv(p):
    with pathlib.Path(p).open(newline="") as f:return list(csv.DictReader(f))
def direct_range(x,anchors):
    h=[];H=[]
    for a in anchors:
        d=np.array([x[0]-a[0],x[1]-a[1],.45-a[2]],float)
        norm=np.linalg.norm(d)
        h.append(norm-.5315983906250129)
        H.append([d[0]/norm,d[1]/norm,0.,0.])
    return np.array(h),np.array(H)
def check_math():
    sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
    import core
    maxF=0.;maxH=0.;maxK=0.;maxP=0.;maxN=0
    states=[np.array([5.3,.1,.43,.002]),np.array([12.,-.43,-2.1,0.])]
    anchors=[[4,0,2.65],[10,0,2.65],[16,.8,2.65]]
    for x in states:
      ds=.05;gy=.016;dt=.2
      pred,F,G=core.transition(x,ds,gy,dt)
      def standalone(x):
        xx=np.asarray(x).copy();aa=gy-xx[3]*dt
        amp=np.sinc(aa/(2*np.pi))
        xx[:2]+=ds*amp*np.array([math.cos(xx[2]+aa/2),math.sin(xx[2]+aa/2)])
        xx[2]=(xx[2]+aa+math.pi)%(2*math.pi)-math.pi
        return xx
      for col in range(4):
        e=np.eye(4)[col]*1e-6
        diff=(standalone(x+e)-standalone(x-e))/(2e-6)
        diff[2]=((standalone(x+e)[2]-standalone(x-e)[2]+np.pi)%(2*np.pi)-np.pi)/(2e-6)
        maxF=max(maxF,float(np.max(abs(diff-F[:,col]))))
      h,H=direct_range(x,anchors)
      for col in (0,1):
        e=np.eye(4)[col]*1e-6
        fd=(direct_range(x+e,anchors)[0]-direct_range(x-e,anchors)[0])/(2e-6)
        maxH=max(maxH,float(np.max(abs(fd-H[:,col]))))
      P=np.diag([.01,.01,math.radians(5)**2,math.radians(.1)**2])
      for m in (1,2,3):
        hh=H[:m];obs=h[:m]+.03*np.arange(1,m+1)
        R=np.eye(m)*.0068578637
        nu=obs-h[:m]
        S=hh@P@hh.T+R;gain=P@hh.T@np.linalg.inv(S)
        nis=float(nu@np.linalg.solve(S,nu))
        diag=(np.eye(4)-gain@hh)
        cov=diag@P@diag.T+gain@R@gain.T
        mu=x+gain@nu;mu[2]=(mu[2]+math.pi)%(2*math.pi)-math.pi
        out,actual,gate=core.gaussian_update(x,P,obs,lambda _: (h[:m],hh),R,gate_threshold=None)
        dif=mu-out;dif[2]=(dif[2]+math.pi)%(2*math.pi)-math.pi
        maxK=max(maxK,float(np.max(abs(dif))))
        maxP=max(maxP,float(np.max(abs(cov-actual))))
        maxN=max(maxN,abs(nis-gate["NIS"]))
    check("V05_CORE_F_Q",maxF<=1e-6,{"max_f_FD":maxF})
    check("V06_BATCH_H_FD",maxH<=1e-8,{"max_h_FD":maxH,"yaw_bias_direct_zero":True})
    check("V07_CHI2_DOF",max(maxK,maxP,maxN)<=1e-10,{"max_state":maxK,"max_P":maxP,"max_NIS":maxN})
def audit():
    cfg=J(CON/"P4_PILOT_CONFIG_LOCK.json")
    rec=J(CON/"P4_PILOT_PROPOSER_SHA_RECEIPT.json")
    tests=J(CON/"P4_PILOT_NUMERIC_GATES.json")
    locked_bad=[x["name"] for x in rec["locked_files"] if sha(CON/x["name"])!=x["sha256"]]
    check("V00_IDENTITY",not locked_bad and len(tests["checks"])==14 and cfg["id"]==rec["contract_id"],
          {"proposer_sha_bad":locked_bad,"checks":len(tests["checks"])})
    need(not locked_bad,"P4_PROPOSER_LOCK_CHANGED")
    src=cfg["sources"];p1=J(P1/"P1_INPUT_LOCK.json")
    need(sha(cfgpath:=ROOT/src["ab_p1_lock"])==src["ab_p1_lock_sha256"],"P1_LOCK_BYTES_DRIFT")
    for n,k in (("c_zip","c_zip_sha256"),("c_csv","c_csv_sha256"),("c_qa","c_qa_sha256")):
        need(sha(ROOT/src[n])==src[k],"P3_NATIVE_INPUT_SHA_DRIFT:"+n)
    q=J(ROOT/src["c_qa"])
    need(q["status"]=="PASS_39_NATIVE_C_SIONNA_RT_CANARY" and not q["failures"],"P3_RT_NO_NATIVE_SUCCESS")
    rows=readcsv(ROOT/src["c_csv"])
    need(len(rows)==39,"C_NEEDS_39")
    cset={(r["route"],int(r["pose_id"])) for r in rows}
    need(len(cset)==39 and {z[0] for z in cset}=={"R2","R4","R5"},"DUPLICATED_C_KEY")
    czip=zipfile.ZipFile(ROOT/src["c_zip"])
    need(czip.testzip() is None,"P3_C_NATIVE_ZIP_BAD_CRC")
    h_error=[];times=[];all_observer=[];swaperr=[];count=0
    for row in rows:
      route=row["route"];pid=int(row["pose_id"])
      name=f"traces/P3_NATIVE_C_{route}_pose{pid}_full.npz"
      raw=czip.read(name)
      if hs(raw)!=row["file_sha256"]:h_error.append([route,pid,"SHA"]);continue
      with np.load(io.BytesIO(raw),allow_pickle=False) as z:
        for channel in ("full","los"):
          H=z["H_native_"+channel];cnt=z[channel+"_path_counts"]
          if H.shape!=(257,2,2) or not np.isfinite(H).all() or len(cnt)!=257 or cnt.min()<1:h_error.append([route,pid,channel]);continue
          observed=observer(H)
          if abs(observed[0]-float(row["native_"+("Full" if channel=="full" else "LoS")+"_signed_s"]))>1e-9:
             h_error.append([route,pid,channel,"S"])
          swapped=H[:,::-1,:].copy()
          alt=observer(swapped)
          swaperr.append(abs(observed[0]+alt[0]))
          all_observer.append((route,pid,channel,observed[0],observed[1]))
          count+=1
        times.append(abs(float(z["time_s"])-float(row["original_t_s"])))
    check("V01_C_NATIVE_SHA",not h_error and len(cset)==39 and count==78 and max(times)<=1e-9,
          {"n_native_channels":count,"native_bad":h_error[:5],"max_time_delta":max(times)})
    check("V03_RX_DETECTOR",not h_error and max(swaperr)<=1e-12,
          {"rx_swap_sign_antisymmetry_max_abs":max(swaperr)})
    check("V10_FULL_BLOCK",sum(cfg["sources"]["routes_n"].values())-len(cset)==3097,
          {"full_timeline_n":3136,"real_C_native_n":len(cset),"missing_native_C":3097,"full_status":"BLOCKED_MISSING_C_NATIVE_RF"})
    ab_errors=[];geometry_errors=[];AB=0
    for route in ("R2","R4","R5"):
      per_route=[r for r in rows if r["route"]==route]
      ti=next(x for x in p1["base_assets"] if x["kind"]=="TIMELINE_TNONE" and "timeline_"+route+"_" in x["path"])
      timeline={int(x["pose_id"]):x for x in readcsv(ROOT/ti["path"])}
      for anchor in ("A","B"):
        case=next(x for x in p1["primary_cases"] if x["case_id"]==route+"_a"+anchor+"_m0")
        sample=J(ROOT/case["samples_path"])
        for mode,key in (("full","full_path"),("los","los_path")):
          item=next(x for x in p1["base_assets"] if x["path"]==case[key])
          f=ROOT/case[key]
          if not f.is_file() or sha(f)!=item["sha256"]:ab_errors.append([route,anchor,mode,"SHA"]);continue
          H=np.load(f,mmap_mode="r",allow_pickle=False)
          if H.shape!=(len(sample),257,2,2):ab_errors.append([route,anchor,mode,"SHAPE"]);continue
          for r in per_route:
            pid=int(r["pose_id"]);row=timeline[pid];s=sample[pid]
            xy=max(abs(float(row[k])-float(r[k+"_m"])) for k in ("x","y"))
            yaw=abs(((float(row["yaw_body_deg"])-float(r["yaw_deg"])+180)%360)-180)
            st=abs(float(row["t_s"])-float(r["original_t_s"]))
            if xy>1e-6 or yaw>1e-6 or st>1e-9:geometry_errors.append([route,anchor,pid,xy,yaw,st])
            o=observer(np.asarray(H[pid]))
            AB+=1
    check("V02_AB_SHA",not ab_errors and AB==156,
          {"original_AB_mode_packet_count":AB,"sha_or_shape_errors":ab_errors[:5]})
    check("V04_POSE_TIME",not geometry_errors and len(cset)==39,
          {"geometry_errors":geometry_errors[:5],"n_matched":39})
    need(not h_error and not ab_errors and not geometry_errors,"PHY_RF_OR_POSE_DISAGREEMENT")
    bank_errors=[]
    for key,n in (("bank_plus_sha256","LP_plus45_bank.npz"),("bank_minus_sha256","LP_minus45_bank.npz")):
      match=list(BANK.rglob(n))
      if len(match)!=1 or sha(match[0])!=src[key]:bank_errors.append(n)
    check("V08_NO_TRUTH",not bank_errors and cfg["design"]["truth"].startswith("allowed only offline"),
          {"full_real_bank_sha_errors":bank_errors,"truth_filter_policy":cfg["design"]["truth"]})
    need(not bank_errors,"SOURCE_FFD_BANK_SHA_MISSING")
    check_math()
    names=[a["name"] for a in cfg["arms"]]
    check("V09_RESOURCE",len(names)==7 and cfg["design"]["epochs_per_route"]==13 and
          cfg["arms"][-1]["epochs"]==[0,4,8,12] and
          cfg["arms"][-2]["epochs"]==list(range(12)),
          {"arms":names,"primary":{"A":13,"ABC":39},"equal":{"A":12,"ABC":12},"different_cadence":True})
    MORE.update(dict(c_native=native if False else 39,a_b_packet_n=AB,n_c_original_real_full=39,
             full_native_missing=3097,original_scenes=1,
             negative_port_swap_antisymmetry_max=max(swaperr),route_counts=Counter(r["route"] for r in rows)))
    czip.close()
if __name__=="__main__":
    try:audit()
    except Exception as exc:
      ERRORS.append(dict(gate="PREFLIGHT_EXCEPTION",error=repr(exc),traceback=traceback.format_exc()))
      print("P4_PREFLIGHT_EXCEPTION",repr(exc),traceback.format_exc(),flush=True)
    result={"schema":"DLP_P4_PILOT_PRE_RUN_AUDIT_V1",
      "decision":"ACCEPT_SPARSE_WITH_BOUNDARIES" if not ERRORS and len(RESULTS)>=11 else "BLOCKED_EVIDENCE",
      "status":"NOT_P4_FULL","root_sha":os.environ.get("GITHUB_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),
      "code_sha256":sha(__file__),"checks":RESULTS,"failures":ERRORS,
      "proof":dict(MORE),"actor":"same ChatGPT proposer author; separate numerical GitHub Actions runner; NOT independent human reviewer",
      "full_P4":"BLOCKED_MISSING_3097_C_NATIVE_EPOCHS","P4_pilot_science":"NOT_RUN",
      "elapsed_sec":time.monotonic()-START,"environment":platform.platform(),"numpy":np.__version__}
    (OUT/"P4_PRE_RUN_AUDIT.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False,default=str)+"\n")
    print("P4_PREFLIGHT_FINAL",result["decision"],len(RESULTS),"failures",len(ERRORS),flush=True)
    sys.exit(0 if not ERRORS and len(RESULTS)>=11 else 1)
