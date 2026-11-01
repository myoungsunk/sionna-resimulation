#!/usr/bin/env python3
"""DLP-EKF-GAPS-001/P1. FROZEN retrospective C0 harmonization ONLY.

The only supported outputs are matched offline signed observation residuals,
selected SourceFFD/Jacobian diagnostics, and ddof=1 descriptive moments.
NO EKF, no RF regeneration, no calibration fit, no scene holdout.
Fail closed and retain every original row and boundary ledger.

Implementer logic is newly written. The historical SourceFFD and LUT are
pinned TARGET models, while original archived trace and frozen observation
module are independent consistency references, not new labels.
"""
from __future__ import annotations
import base64,csv,datetime,hashlib,io,json,math,os,platform,subprocess,sys,time,traceback
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np

ROOT=Path.cwd()
BASE=ROOT/"research/DUAL_LP_PAPER_GAP_20261030"
LOCK=BASE/"contracts/DLP-EKF-GAPS-001/P1_20261101"
OUT=Path(os.environ.get("DLP_OUT","/tmp/dlp_p1_science"))
OUT.mkdir(parents=True,exist_ok=True)
BANK_ROOT=Path(os.environ.get("DLP_BANK_DIR","/tmp/dlp_p1_banks"))
TRACE_ROOT=Path(os.environ.get("DLP_TRACE_DIR","/tmp/dlp_p1_original_traces"))
START=time.monotonic()
HEAD="340877f3537b4cc65cdaa9d687423cba92e0b28b"
SHA_CONTRACT="373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594"
SHA_AUDIT="d9530bccdd5eb753aecba0475c52ed092bf3aaf221b3cba389ed2aa492a9548c"
C=299792458.
N=257
DF=1950000.
OFFSET=-0.5315983906250129
ERRS=[]
GATES={}
WARN=[]
METRICS={}
COUNTS=Counter()
CROSS=Counter()
RESULTS=[]
ROWS=[]
PARITY=[]
CANARY=[]
LEDGER=[]
SCENE_N=1

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            b=f.read(1024*1024)
            if not b:break
            h.update(b)
    return h.hexdigest()
def sha_bytes(data):return hashlib.sha256(data).hexdigest()
def jf(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def record(id,pass_,info,values=None,block=False):
    GATES[id]={"status":"PASS" if pass_ else ("BLOCKED" if block else "FAIL"),"note":str(info)}
    if values is not None:GATES[id]["measured"]=values
    if not pass_:ERRS.append(dict(gate=id,note=str(info),values=values))
    print("P1_GATE",id,GATES[id]["status"],str(info)[:250],flush=True)
def expect(cond,msg):
    if not bool(cond):raise RuntimeError(msg)
def origin_asset_check(lock):
    errors=[];ledger=[]
    for a in lock["base_assets"]:
        f=ROOT/a["path"]
        if not f.is_file():errors.append(dict(path=a["path"],error="missing"));continue
        h=sha_file(f);size=f.stat().st_size
        good=(h==a["sha256"] and size==a["bytes"])
        ledger.append(dict(path=a["path"],kind=a["kind"],sha256=h,bytes=size,expected_sha256=a["sha256"],ok=good))
        if not good:errors.append(dict(path=a["path"],bytes=size,sha256=h,expected=a["sha256"]))
    (OUT/"P1_INPUT_HASH_RECEIPT.json").write_text(json.dumps(ledger,indent=2))
    record("T00_INPUT_SHA",len(ledger)==39 and not errors,
           "all original C0 SHA256 and byte lengths verified; errors="+str(errors[:3]),
           dict(n=len(ledger),fails=errors[:10]),block=True)
    expect(not errors and len(ledger)==39,"STOP_INPUT_39_ORIGINAL_SHA_OR_SIZE")
    banks=[]
    for a in lock["ffd_bank_source"]["banks"]:
        m=list(BANK_ROOT.rglob(a["filename"]))
        expect(len(m)==1,"STOP_BANK_PATH_MISSING_OR_AMBIGUOUS:"+a["filename"])
        p=m[0]
        sh=sha_file(p)
        expect(sh==a["sha256"] and p.stat().st_size==a["bytes"],"STOP_BANK_REAL_BYTES_SHA:"+a["filename"])
        banks.append((a,p))
    METRICS["bank_provenance"]=[dict(name=a["filename"],sha256=sha_file(p),bytes=p.stat().st_size) for a,p in banks]
    # Original p0_initial.py loads bank files from ROOT.parent. Populate transient
    # links in runner scratch only after complete SHA check.
    ext=ROOT.parent
    manifest={"npz_sha256":{}}
    for a,p in banks:
        target=ext/a["filename"]
        expect(not target.exists() and not target.is_symlink(),"TRANSIENT_STAGING_ALREADY_EXISTS")
        target.symlink_to(p)
        manifest["npz_sha256"][a["filename"]]=a["sha256"]
    (ext/"BANK_MANIFEST.json").write_text(json.dumps(manifest,sort_keys=True))
    (ext/"ffd_p0p3/out").mkdir(parents=True,exist_ok=True)

def require_freeze():
    f=jf(LOCK/"P1_FROZEN_RATIFICATION_20261101.json")
    a=f["immutable_artifacts"]
    checks=[
      ("EXPERIMENT_CONTRACT_DLP-EKF-GAPS-001_P1_PROPOSER_LOCKED.md","contract_sha256"),
      ("P1_INPUT_LOCK.json","input_lock_sha256"),
      ("P1_CONFIG_LOCK.json","config_lock_sha256"),
      ("P1_NUMERIC_TOLERANCES.json","numerical_tolerances_sha256"),
      ("P1_SAMPLE_SPLIT_LOCK.json","sample_split_sha256"),
      ("P1_SCIENCE_SPEC_LOCKED.md","source_science_spec_sha256")]
    mismatches=[name for name,k in checks if sha_file(LOCK/name)!=a[k]]
    expect(f["ratification_status"]=="FROZEN" and f["science_authorization"]=="P1_ONLY","NOT_FROZEN_P1_ONLY")
    expect(f["immutable_proposer_head"]==HEAD and a["contract_sha256"]==SHA_CONTRACT,"FROZEN_BAD_IDENTITY")
    expect(not mismatches,"FROZEN_LOCK_CHANGED:"+str(mismatches))
    audited_ref=f["linked_signatures"]["auditor"]
    expect(audited_ref["signed_verdict"]=="ACCEPT_WITH_BOUNDARIES" and audited_ref["audit_result_sha256"]==SHA_AUDIT,"AUDITOR_COSIGN_INVALID")
    expect(f["linked_signatures"]["proposer"]["approval"]=="EXPLICIT_USER_AUTHORIZATION_FOR_APPEND_ONLY_RATIFICATION_AND_P1_SCIENCE","PROPOSER_AUTHORIZATION_MISSING")
    # Independently retrieve signed immutable audit and raw runner evidence
    # using GitHub HTTPS read API, not mutable labels or editable notes.
    ref=audited_ref["auditor_verdict_pinned_git_ref"]
    def github_bytes(path):
        full=f"repos/myoungsunk/sionna-resimulation/contents/{path}?ref={ref}"
        encoded=subprocess.check_output(["gh","api",full,"--jq",".content"],text=True)
        return base64.b64decode(encoded.replace("\n",""))
    signed=json.loads(github_bytes(audited_ref["auditor_verdict_ref"]))
    raw=github_bytes(audited_ref["immutable_raw_report_path"])
    assert sha_bytes(raw)==SHA_AUDIT, "AUDITOR_SHA_MISMATCH"
    original=json.loads(raw)
    expect(signed["verdict"]=="ACCEPT_WITH_BOUNDARIES" and
        signed["audit_sha"]==SHA_AUDIT and
        signed["contract_sha256"]==SHA_CONTRACT and
        original["verdict"]=="ACCEPT_WITH_BOUNDARIES" and
        not original["failures"] and len(original["checks"])>=21,
        "AUDIT_VERDICT_OR_CONTENT_NOT_ACCEPTED")
    input_lock=jf(LOCK/"P1_INPUT_LOCK.json")
    cfg=jf(LOCK/"P1_CONFIG_LOCK.json")
    tolerances=jf(LOCK/"P1_NUMERIC_TOLERANCES.json")
    split=jf(LOCK/"P1_SAMPLE_SPLIT_LOCK.json")
    expect(len(tolerances["tests"])==16 and [x["id"] for x in tolerances["tests"]]==[
      "T00_INPUT_SHA","T01_SHAPE","T02_POSE_KEYS","T03_TIME","T04_COORD","T05_OBSERVER",
      "T06_SOURCE_DIRECT_INTERNAL","T07_SOURCE_NATIVE_COMPLEX","T08_SOURCE_NATIVE_S",
      "T09_SOURCE_JAC","T10_OLD_LUT","T11_MODEL_SHIFT","T12_COV","T13_S_DOMAIN",
      "T14_COUNTS","T15_P1_METRICS"],"TOLERANCE_COUNT_IDS_CHANGED")
    expect(cfg["train_eval"]["new_model_fitting"]==False and cfg["train_eval"]["retrospective_statistics_only"] and cfg["populations"]["statistical_independent_scene_count"]==1,
           "P1_MODEL_OR_DESCRIPTIVE_SCOPE_CHANGED")
    expect(len(input_lock["primary_cases"])==7 and len(input_lock["base_assets"])==39,
           "P1_PRIMARY_INPUT_LOCK_CHANGED")
    record("FREEZE_GATE",True,"Proposer + prior independent computational auditor SHA signed; unchanged contract/config/tolerances",
           dict(auditor_sha=SHA_AUDIT,contract_sha=SHA_CONTRACT,original_head=HEAD))
    return input_lock,cfg,tolerances,split,original

def validate_source_blob(input_lock):
    for a in input_lock["locked_source_code"]:
        calc=subprocess.check_output(["git","hash-object",a["path"]],text=True).strip()
        expect(calc==a["git_blob_sha1"],"LOCKED_SOURCE_BLOB_CHANGED:"+a["path"])
    print("P1 PINNED_SOURCE_CODE_SHA all exact")
def independent_observer(H,freq):
    """Entire original RF H -> native raw z, independent from historical helper."""
    if H.ndim!=4 or H.shape[1:]!=(257,2,2):raise ValueError("H must be N*257*2*2")
    # Exact symmetric Hann N-1, algebraically identical to 0.5-0.5*cos.
    win=np.sin(np.pi*np.arange(N)/(N-1))**2
    h=np.fft.ifft(np.asarray(H)[:,:,:,0]*win[None,:,None],
                  n=4*N,axis=1)*N
    abs_h=np.abs(h)
    branch=abs_h.max(axis=1).argmax(axis=1)
    strength=abs_h[np.arange(len(H)),:,branch]
    peak=strength.max(axis=1)
    index=(strength>=0.3*peak[:,None]).argmax(axis=1)
    cf=h[np.arange(len(H)),index,:]
    power=np.abs(cf)**2
    den=power.sum(axis=1)
    valid=(den>0)&np.isfinite(den)&(peak>0)
    s=np.full(len(H),np.nan)
    s[valid]=(power[valid,0]-power[valid,1])/den[valid]
    r=index*C/(4*N*(freq[1]-freq[0]))
    return dict(s=s,r=r,index=index,valid=valid,branch=branch,power=power)

def old_independent(states,case,lut,meta):
    """Explicit eight-corner interpolation and angular chain rule independent of FrozenLut.model."""
    ax,ay,az=map(float,case["anchor"])
    dx=states[:,0]-ax;dy=states[:,1]-ay;z=az-float(case["robot_z_m"])
    rho2=np.maximum(dx*dx+dy*dy,1e-12);rho=np.sqrt(rho2)
    th=np.degrees(np.arctan2(rho,z))
    yaw=np.degrees(states[:,2])+float(case["mount_deg"])
    tx=np.degrees(np.arctan2(-dy,dx))
    rx=(np.degrees(np.arctan2(-dy,-dx))-yaw+180)%360-180
    dt=float(meta["theta_deg"][1]-meta["theta_deg"][0])
    dp=float(meta["phi_deg"][2])
    t=np.clip(th/dt,0,lut.shape[0]-1-1e-9)
    a=(tx-float(meta["phi_deg"][0]))/dp
    b=(rx-float(meta["phi_deg"][0]))/dp
    ti=np.floor(t).astype(int);aj=np.floor(a).astype(int)%lut.shape[1]
    bj=np.floor(b).astype(int)%lut.shape[2]
    ft=t-ti;fa=a-np.floor(a);fb=b-np.floor(b)
    # Explicit sum over each corner, separate analytic weighted derivative.
    n=len(t);val=np.zeros(n);g_t=np.zeros(n);g_a=np.zeros(n);g_b=np.zeros(n)
    for ti_bit in (0,1):
      for aj_bit in (0,1):
       for bj_bit in (0,1):
        v=lut[ti+ti_bit,(aj+aj_bit)%lut.shape[1],(bj+bj_bit)%lut.shape[2]]
        wt=ft if ti_bit else (1-ft)
        wa=fa if aj_bit else (1-fa)
        wb=fb if bj_bit else (1-fb)
        val+=v*wt*wa*wb
        g_t+=v*(1 if ti_bit else -1)*wa*wb/dt
        g_a+=v*wt*(1 if aj_bit else -1)*wb/dp
        g_b+=v*wt*wa*(1 if bj_bit else -1)/dp
    rad=180/np.pi
    dth_x=z/(rho2+z*z)*dx/rho*rad
    dth_y=z/(rho2+z*z)*dy/rho*rad
    dtx_x=dy/rho2*rad;dtx_y=-dx/rho2*rad
    drx_x=-dy/rho2*rad;drx_y=dx/rho2*rad
    J=np.zeros((n,4))
    J[:,0]=g_t*dth_x+g_a*dtx_x+g_b*drx_x
    J[:,1]=g_t*dth_y+g_a*dtx_y+g_b*drx_y
    J[:,2]=-g_b*rad
    return val,J

def read_archive():
    summ=list(TRACE_ROOT.rglob("P2_ONE_STEP_SUMMARY.json"))
    expect(len(summ)==1,"ARCHIVED_TRACE_SUMMARY_MISSING_OR_AMBIGUOUS:"+str(summ))
    s=summ[0]
    expect(sha_file(s)=="8412e39cbeafa41656041ffe9f7778ef7f0d597508d3cfb2747e4735c4e83634","ARCHIVED_SUMMARY_SHA_DRIFT")
    summary=jf(s)
    expect(len(summary["per_case"])==14,"ARCHIVED_TRACE_NOT_14")
    out={}
    for a in summary["per_case"]:
        path=s.parent/a["trace_file"]
        expect(path.exists() and sha_file(path)==a["trace_sha256"],
               "ARCHIVED_TRACE_HASH_MISMATCH:"+a["trace_file"])
        with np.load(path,allow_pickle=False) as v:
            needed=("pose_id","t_s","z_s","z_r_m","detected")
            expect(all(n in v.files for n in needed),"ARCHIVED_TRACE_FIELDS_MISSING")
            arr={k:v[k].copy() for k in needed}
        expect(a["case"] and a["channel"] in ("los","full"),"ARCHIVED_TRACE_UNEXPECTED_CASE")
        expect(len(np.unique(arr["pose_id"]))==len(arr["pose_id"]) and
               np.all(np.diff(arr["t_s"])>0),"ARCHIVE_DUP_OR_NONMONOTONIC")
        key=(a["case"],a["channel"].upper())
        expect(key not in out,"ARCHIVE_DUPLICATE_CASE")
        out[key]=dict(arr=arr,sha=a["trace_sha256"],file=a["trace_file"])
    expect(len(out)==14,"ARCHIVE_CASE_PAIR_COUNT_DIFFER")
    METRICS["archived_reference"]={"source_run":38331588521,"summary_sha256":sha_file(s),
       "trace_sha256s":{str(k):v["sha"] for k,v in out.items()}}
    return out

def time_rows(input_lock):
    times={}
    for route in ("R2","R4","R5"):
        a=next(x for x in input_lock["base_assets"] if x["kind"]=="TIMELINE_TNONE" and f"timeline_{route}_" in x["path"])
        with (ROOT/a["path"]).open(newline="") as f:rows=list(csv.DictReader(f))
        keys=[int(z["pose_id"]) for z in rows]
        expect(len(set(keys))==len(keys),"TIME_DUPLICATE:"+route)
        tt=np.array([float(z["t_s"]) for z in rows])
        expect(np.all(np.diff(tt)>0),"TIME_NONMONOTONIC:"+route)
        times[route]={int(x["pose_id"]):x for x in rows}
    return times

def writetable(path,rows,columns):
    with (OUT/path).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction="ignore")
        w.writeheader()
        for row in rows:w.writerow(row)

def summarize(rows):
    """Fixed strata, no independent scene inference, 2 independent covariance formulas."""
    groups=defaultdict(list)
    for r in rows:
        if r["status"]!="VALID":continue
        for model in ("old","source"):
            e_s=r["e_s_old"] if model=="old" else r["e_s_source"]
            er=r["e_r_m"]
            labels=[
               ("CASE_BIN",r["case_id"],r["channel"],r["distance_bin"]),
               ("CASE_ALL",r["case_id"],r["channel"],"ALL"),
               ("ROUTE_BIN",r["route"],r["channel"],r["distance_bin"]),
               ("CHANNEL_BIN","ALL",r["channel"],r["distance_bin"]),
               ("CHANNEL_ALL","ALL",r["channel"],"ALL")]
            for level,case,channel,dbin in labels:
                groups[(level,case,channel,dbin,model)].append((er,e_s))
    out=[];max_mu_err=0.;max_cov_err=0.;bad=[];small=[];total=0
    for key,data in sorted(groups.items()):
        level,case,channel,dist,model=key
        A=np.asarray(data,float)
        n=len(A);total+=n
        mean=A.mean(axis=0)
        mean_b=np.array([math.fsum(float(z) for z in A[:,j])/n for j in (0,1)])
        max_mu_err=max(max_mu_err,float(np.max(np.abs(mean-mean_b))))
        cov=np.full((2,2),np.nan)
        cov2=np.full((2,2),np.nan)
        eigmin=np.nan;status="INSUFFICIENT" if n<2 else "VALID"
        if n>=2:
            X=A-mean
            cov=X.T@X/(n-1)
            cov2=np.cov(A,rowvar=False,ddof=1)
            eigmin=float(np.linalg.eigvalsh(cov).min())
            max_cov_err=max(max_cov_err,float(np.max(np.abs(cov-cov2))))
            if (eigmin< -1e-12 or float(abs(cov[0,1]-cov[1,0]))>=1e-12):
                bad.append((key,eigmin))
        else:small.append(key)
        row=dict(stratum_level=level,stratum_id=case,channel=channel,distance_bin=dist,
             arm=model,n=n,mean_e_r_m=float(mean[0]),mean_e_s=float(mean[1]),
             rmse_e_r_m=float(np.sqrt(np.mean(A[:,0]**2))),
             rmse_e_s=float(np.sqrt(np.mean(A[:,1]**2))),
             std_e_r_m=float(np.std(A[:,0],ddof=1)) if n>=2 else "",
             std_e_s=float(np.std(A[:,1],ddof=1)) if n>=2 else "",
             C_rr_m2=float(cov[0,0]) if n>=2 else "",
             C_rs_m=float(cov[0,1]) if n>=2 else "",
             C_ss=float(cov[1,1]) if n>=2 else "",
             min_cov_eigen=float(eigmin) if n>=2 else "",
             status=status,statistical_independent_scenes=SCENE_N)
        out.append(row)
    METRICS["moment_validation"]={"max_mean_crosscheck_difference":max_mu_err,
        "max_covariance_crosscheck_difference":max_cov_err,
        "bad_psd_groups":bad,"n_insufficient_groups":len(small),
        "strata":len(out),"computed_cells":total}
    return out, max_mu_err,max_cov_err,bad

def main():
    lock,cfg,tol,split,audit=require_freeze()
    origin_asset_check(lock)
    validate_source_blob(lock)
    frequency=np.load(ROOT/next(x["path"] for x in lock["base_assets"] if x["kind"]=="FREQUENCY"),allow_pickle=False)
    shape_errors=[];invalid_count=0
    expect(np.array_equal(frequency,6250400000.+DF*np.arange(N)),"FREQUENCY_GRID_CHANGE")
    archive=read_archive()
    route_t=time_rows(lock)
    sys.path.insert(0,str(ROOT/"research/FFD_P0P3_20261016"))
    import p0_initial
    from source_model import SourceFFD
    from p3_rf_adapter4 import FrozenLut
    source=SourceFFD()
    legacy=FrozenLut(ROOT)
    lut=np.load(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy",mmap_mode="r")
    meta=jf(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json")["meta"]
    expect(np.array_equal(source.freqs,frequency),"MODEL_FREQUENCY_GRID_NOT_MATCH")
    n_archive=0;n_parity_bad=0;max_parity_s=0;max_parity_r=0
    n_nomode=0;counts_h={"FULL":0,"LOS":0};timeline_counts={"FULL":0,"LOS":0};eval_counts={"FULL":0,"LOS":0}
    maxcoord=0.;maxyaw=0.;max_t_diff=0
    max_obs_s=0;max_obs_r=0;obs_tap_dif=0
    max_source_old_identity=0.;max_range_unchanged=0.;max_r_jac=0.;max_bias_jac=0
    max_old_s=0.;max_old_j=0.;max_source_native=0.;complex_sq=0.;s_sq=0.;max_native_s=0.;n_s=0;n_native_tap_diff=0
    qfd_max=0.;qfd_count=0;qfd_fail=0
    n_LUT=0;feature_rows=[]

    # Process 7 exact cases; FULL/LOS independently read from locked original files
    # and paired by the very same immutable case,pose ID. All rows are retained.
    for case in lock["primary_cases"]:
        caseid=case["case_id"];route=case["route"];mount=int(case["mount_deg"])
        raw_samples=jf(ROOT/case["samples_path"])
        pose=np.array([int(x["pose_id"]) for x in raw_samples],dtype=int)
        expect(np.array_equal(pose,np.arange(len(raw_samples))),"POSE_KEYS_NOT_ONE_TO_ONE:"+caseid)
        state=np.array([[x["x"],x["y"],np.deg2rad(x["yaw_body_deg"]),0.] for x in raw_samples],float)
        anc=np.asarray(case["anchor"],float)
        d=np.sqrt((state[:,0]-anc[0])**2+(state[:,1]-anc[1])**2+
                  (case["robot_z_m"]-anc[2])**2)
        rhat=d+OFFSET
        bins=np.where(d<5,"0-5m",np.where(d<10,"5-10m","10m-inf"))
        # Full 4D h_s source H_s and archived old 2deg LUT H_s computed on same poses.
        sn=len(state);pred=np.empty((sn,2));J=np.empty((sn,2,4))
        diag_tap=np.empty(sn,int);diag_port=np.empty(sn,int);diag_cells=[];diag_fpm=[]
        for k in range(0,sn,32):
            en=min(k+32,sn)
            p,h,diag=source.batch(state[k:en],case,gradient=True,return_diagnostics=True)
            pred[k:en]=p;J[k:en]=h;diag_tap[k:en]=diag["tap"];diag_port[k:en]=diag["strong_port"]
            diag_cells.append(diag["cells"]);diag_fpm.extend(diag["fp_margin"].tolist())
        cells=np.concatenate(diag_cells,axis=0)
        js=pred[:,1]
        max_r_jac=max(max_r_jac,float(np.max(abs(J[:,0,0]-(state[:,0]-anc[0])/d))),
                      float(np.max(abs(J[:,0,1]-(state[:,1]-anc[1])/d))))
        max_bias_jac=max(max_bias_jac,float(np.max(abs(J[:,:,3]))))
        expect(np.all(np.isfinite(pred)) and np.all(np.isfinite(J)) and J.shape==(sn,2,4),
               "SOURCE_PREDICTOR_NAN_OR_SHAPE:"+caseid)
        jp_range=np.max(abs(pred[:,0]-rhat))
        max_range_unchanged=max(max_range_unchanged,float(jp_range))
        old_p=np.empty(sn);old_J=np.empty((sn,4))
        for i in range(sn):
            a,h=legacy.model(state[i],case)
            old_p[i]=a[1];old_J[i]=h[1]
        alt,altjac=old_independent(state,case,lut,meta)
        max_old_s=max(max_old_s,float(np.max(abs(old_p-alt))))
        max_old_j=max(max_old_j,float(np.max(abs(old_J-altjac))))
        n_LUT+=sn
        # All C0 Source vs Native LoS complex channel and signed s QA.
        Hlos=np.load(ROOT/case["los_path"],mmap_mode="r",allow_pickle=False)
        Hfull=np.load(ROOT/case["full_path"],mmap_mode="r",allow_pickle=False)
        for mode,raw in [("FULL",Hfull),("LOS",Hlos)]:
            if raw.shape!=tuple(case["h_shape"]) or raw.dtype!=np.dtype("complex128"):
                shape_errors.append([caseid,mode,list(raw.shape),str(raw.dtype)])
        expect(not shape_errors,"ORIGINAL_RF_H_SHAPE_DTYPE_CHANGED:"+str(shape_errors))
        readings={}
        for mode,raw in [("FULL",Hfull),("LOS",Hlos)]:
            n=len(raw);counts_h[mode]+=n
            z={k:np.empty(n,dtype=float if k in ("s","r") else (int if k in ("index","branch") else bool))
                  for k in ("s","r","index","branch","valid")}
            for k in range(0,n,32):
                en=min(k+32,n)
                arr=np.asarray(raw[k:en])
                indep=independent_observer(arr,frequency)
                refer=p0_initial.O.observe(arr,frequency,None,None)
                max_obs_s=max(max_obs_s,float(np.nanmax(abs(indep["s"]-refer["s"]))))
                max_obs_r=max(max_obs_r,float(np.nanmax(abs(indep["r"]-refer["range_m"]))))
                obs_tap_dif+=int(np.count_nonzero(indep["index"]!=refer["index"]))
                for field in z:z[field][k:en]=indep[field]
            readings[mode]=z
            bad=np.where(~z["valid"] | ~np.isfinite(z["s"]) |
                           (np.abs(z["s"])>1+1e-12))[0]
            for i in bad.tolist():
                LEDGER.append(dict(case_id=caseid,channel=mode,pose_id=i,t_s="",
                                   type="INVALID_PACKET",axis="",
                                   reason="ZERO_POWER_OR_NONFINITE_SIGNED_S"))
            invalid_count+=len(bad)
        # Map matched physical path differences with one pose and same detector for both modes.
        zs_full=readings["FULL"]["s"];zs_los=readings["LOS"]["s"]
        delta_mp=zs_full-zs_los
        for k in range(0,sn,32):
            en=min(k+32,sn)
            h=source.physical_h_col(state[k:en],case)
            native=np.asarray(Hlos[k:en,:,:,0])
            den=np.linalg.norm(native.reshape(en-k,-1),axis=1)
            rel=np.linalg.norm((h-native).reshape(en-k,-1),axis=1)/np.maximum(den,1e-300)
            max_source_native=max(max_source_native,float(np.max(rel)))
            complex_sq+=float(np.dot(rel,rel))
            delta_s=js[k:en]-zs_los[k:en]
            s_sq+=float(np.dot(delta_s,delta_s))
            max_native_s=max(max_native_s,float(np.max(abs(delta_s))))
            n_s+=len(rel)
            n_native_tap_diff+=int(np.count_nonzero(diag_tap[k:en]!=readings["LOS"]["index"][k:en]))
        # True finite-difference crossings and stable-cell Jacobian test across ALL 9519 case poses.
        flags=np.zeros(sn,bool)
        for axis,eps in [(0,1e-5),(1,1e-5),(2,1e-5)]:
            for k in range(0,sn,32):
                en=min(k+32,sn)
                pp=state[k:en].copy();mm=pp.copy()
                pp[:,axis]+=eps;mm[:,axis]-=eps
                yp,_,dp=source.batch(pp,case,gradient=False,return_diagnostics=True)
                ym,_,dm=source.batch(mm,case,gradient=False,return_diagnostics=True)
                tap_switch=(dp["tap"]!=diag_tap[k:en])|(dm["tap"]!=diag_tap[k:en])
                port_switch=(dp["strong_port"]!=diag_port[k:en])|(dm["strong_port"]!=diag_port[k:en])
                cell_switch=np.any(dp["cells"]!=cells[k:en],axis=1)|np.any(dm["cells"]!=cells[k:en],axis=1)
                switched=tap_switch|port_switch|cell_switch
                flags[k:en]|=switched
                fd=(yp[:,1]-ym[:,1])/(2*eps)
                err=np.abs(fd-J[k:en,1,axis])
                accepted=err<=2e-5
                accepted|=(np.abs(J[k:en,1,axis])>1e-6)&(
                    err/np.maximum(np.abs(J[k:en,1,axis]),1e-30)<=1e-4)
                stable=~switched
                if stable.any():
                    qfd_count+=int(np.count_nonzero(stable))
                    qfd_max=max(qfd_max,float(np.max(err[stable])))
                flagged=stable&(~accepted)
                qfd_fail+=int(np.count_nonzero(flagged))
                for local in np.flatnonzero(switched|flagged).tolist():
                    i=k+local
                    if tap_switch[local]: name="FIRST_PATH_SWITCH"
                    elif port_switch[local]: name="STRONG_PORT_SWITCH"
                    elif cell_switch[local]: name="FFD_CELL_SWITCH"
                    else:name="SOURCE_JAC_MISMATCH"
                    CROSS[(caseid,name)]+=1
                    LEDGER.append(dict(case_id=caseid,channel="SOURCE_MODEL",pose_id=i,
                        t_s=route_t[route].get(i,{}).get("t_s",""),type=name,
                        axis=("x","y","yaw")[axis],
                        reason=("BOUNDARY_EXCLUDED_FROM_SMOOTH_FD" if switched[local] else
                                "STABLE_INTERIOR_FD_TOO_LARGE"),
                        analytic=float(J[i,1,axis]),fd=float(fd[local]),abs_error=float(err[local])))
        # Report each real RF matched packet; *no dropping even at source cell boundaries*.
        for mode in ("FULL","LOS"):
            z=readings[mode]
            archived=archive[(caseid,mode)]
            tr=archived["arr"];tkeys=[int(t) for t in tr["pose_id"]]
            archived_keys=set(tkeys)
            expected_keys=set(route_t[route])
            expect(archived_keys==expected_keys,"ARCHIVED_POSE_ID_NOT_EXACT_TIMELINE:"+caseid+mode)
            expect(np.all(tr["detected"]),"ARCHIVED_TRACE_UNDETECTED:"+caseid+mode)
            if not np.array_equal(np.asarray(tkeys,dtype=int),np.asarray(sorted(tkeys),dtype=int)):
                raise RuntimeError("ORIGINAL_TRACE_IDS_NOT_ASCENDING")
            for kk,idx in enumerate(tkeys):
                t_exp=route_t[route][idx]
                t_s=float(t_exp["t_s"])
                dt=abs(t_s-float(tr["t_s"][kk]))
                max_t_diff=max(max_t_diff,dt)
                ds=abs(float(tr["z_s"][kk])-float(z["s"][idx]))
                dr=abs(float(tr["z_r_m"][kk])-float(z["r"][idx]))
                max_parity_s=max(max_parity_s,ds)
                max_parity_r=max(max_parity_r,dr)
                if ds>1e-9 or dr>1e-9 or dt>1e-9:
                    n_parity_bad+=1
                    LEDGER.append(dict(case_id=caseid,channel=mode,pose_id=idx,t_s=t_s,
                        type="ARCHIVE_TRACE_PARITY_FAIL",reason=f"ds={ds},dr={dr},dt={dt}"))
                maxcoord=max(maxcoord,abs(float(t_exp["x"])-float(raw_samples[idx]["x"])),
                          abs(float(t_exp["y"])-float(raw_samples[idx]["y"])))
                yawdiff=((float(t_exp["yaw_body_deg"])-float(raw_samples[idx]["yaw_body_deg"])+180)%360)-180
                maxyaw=max(maxyaw,abs(yawdiff))
                timeline_counts[mode]+=1
                if t_s>=30:eval_counts[mode]+=1
                PARITY.append(dict(case_id=caseid,route=route,anchor_id=("A" if "aA" in caseid else "B"),
                    mount_deg=mount,channel=mode,pose_id=idx,t_s=t_s,
                    archive_z_r_m=float(tr["z_r_m"][kk]),derived_z_r_m=float(z["r"][idx]),
                    abs_delta_r_m=dr,archive_s=float(tr["z_s"][kk]),
                    derived_s=float(z["s"][idx]),abs_delta_s=ds,first_path_tap=int(z["index"][idx]),
                    historical_trace_sha256=archived["sha"],status="PASS" if ds<=1e-9 and dr<=1e-9 else "FAIL"))
            for i in range(sn):
                zz=float(z["s"][i]);rr=float(z["r"][i])
                es_old=zz-float(old_p[i]);es_src=zz-float(js[i])
                shift=float(old_p[i]-js[i]);ident=(es_src-es_old)-shift
                max_source_old_identity=max(max_source_old_identity,abs(float(ident)))
                tinfo=route_t[route].get(i)
                tval=float(tinfo["t_s"]) if tinfo is not None else ""
                er=rr-float(rhat[i])
                stat="VALID" if bool(z["valid"][i]) else "INVALID_PACKET"
                ROWS.append(dict(scene_family="C0_Corridor",case_id=caseid,
                   route=route,anchor_id=("A" if "aA" in caseid else "B"),
                   mount_deg=mount,channel=mode,pose_id=i,t_s=tval,
                   time_joined=(tinfo is not None),eval_t_ge_30=(bool(tinfo is not None and float(tinfo["t_s"])>=30)),
                   x_truth_offline_m=float(state[i,0]),y_truth_offline_m=float(state[i,1]),
                   yaw_truth_offline_rad=float(state[i,2]),d_truth_offline_m=float(d[i]),
                   distance_bin=str(bins[i]),z_r_raw_m=rr,z_s_signed=zz,
                   first_path_tap=int(z["index"][i]),strong_port=int(z["branch"][i]),
                   h_r_m=float(rhat[i]),h_s_old=float(old_p[i]),h_s_source=float(js[i]),
                   e_r_m=er,e_s_old=es_old,e_s_source=es_src,
                   delta_e_s=es_src-es_old,h_old_minus_source=shift,
                   multipath_s_contrast=float(delta_mp[i]),
                   source_first_path_tap=int(diag_tap[i]),
                   source_near_boundary=bool(flags[i]),fp_margin=float(diag_fpm[i]),
                   status=stat))
            # Deterministic canaries, separate from full 19038 packet complete tables.
            ids=sorted(set([0,sn//2,sn-1,int(np.argmin(d))]))
            for i in ids:
                CANARY.append(dict(case_id=caseid,channel=mode,pose_id=i,
                    z_r_m=float(z["r"][i]),z_s=float(z["s"][i]),tap=int(z["index"][i]),
                    h_r=float(rhat[i]),h_s_source=float(js[i]),h_s_old=float(old_p[i]),
                    H_r=json.dumps(J[i,0].tolist()),H_s_source=json.dumps(J[i,1].tolist()),
                    H_s_old=json.dumps(old_J[i].tolist()),
                    signed_delta_e_s=float(old_p[i]-js[i]),
                    first_path_switch=bool(flags[i]),status="DIAGNOSTIC_ONLY"))
        print("P1_CASE",caseid,"npose",sn,"jac_n",qfd_count,
              "arcpair",len(archive[(caseid,"FULL")]["arr"]["pose_id"]),
              "elapsed",round(time.monotonic()-START,2),flush=True)
    # All rows retained with stable case/channel/pose keys, no hidden exclusion.
    METRICS.update(dict(full_n=counts_h["FULL"],los_n=counts_h["LOS"],
         timeline_n=timeline_counts,eval_n=eval_counts,
         archive_compared=n_archive+len(PARITY),
         archive_bad=n_parity_bad,max_archived_s_error=max_parity_s,
         max_archived_r_error_m=max_parity_r,max_archive_t_error_s=max_t_diff,
         max_coord_xy_m=maxcoord,max_wrapped_yaw_deg=maxyaw,
         raw_observer_max_s_diff=max_obs_s,raw_observer_max_r_diff_m=max_obs_r,
         raw_observer_tap_mismatch=obs_tap_dif,raw_invalid_packets=invalid_count,
         source_native_n=n_s,
         source_native_h_rel_max=max_source_native,
         source_native_h_rel_rms=float(np.sqrt(complex_sq/n_s)),
         source_native_s_rmse=float(np.sqrt(s_sq/n_s)),
         source_native_s_max_abs=max_native_s,
         source_native_tap_mismatch=n_native_tap_diff,
         model_shift_identity_max_abs=max_source_old_identity,
         range_model_max_abs_unchanged=max_range_unchanged,
         source_Hr_max_abs_error=max_r_jac,model_bias_jac_max_abs=max_bias_jac,
         old_LUT_max_abs_s_diff=max_old_s,
         old_LUT_max_abs_J_diff=max_old_j,
         source_FD_max_stable_abs=qfd_max,source_FD_stable_total=qfd_count,
         source_FD_interior_fails=qfd_fail,
         source_boundary_unique_keys=sum(int(r["source_near_boundary"]) for r in ROWS if r["channel"]=="FULL"),
         crossings={k[0]+"/"+k[1]:v for k,v in CROSS.items()}))
    # T00 verified in stage, freeze verified before scientific outputs
    record("T01_SHAPE",not shape_errors and np.array_equal(frequency,6250400000.+DF*np.arange(N)),
           "7 cases * 2 channels exact H complex128, 257 bins",dict(errors=shape_errors))
    record("T02_POSE_KEYS",len(ROWS)==19038 and len({(x["case_id"],x["channel"],x["pose_id"]) for x in ROWS})==19038,
           "all seven Full and NativeLoS pose pairs with exact immutable integer keys")
    record("T03_TIME",max_t_diff<=1e-9,
           "original archive and route timeline timestamps exact within 1e-9 seconds",dict(max_abs_s=max_t_diff))
    record("T04_COORD",maxcoord<=1e-6 and maxyaw<=1e-6,
           "rounded SAMPLES vs precise timeline xyz/yaw within locked CSV rounding allowance",
           dict(xy_m=maxcoord,yaw_deg=maxyaw))
    record("T05_OBSERVER",n_parity_bad==0 and max_obs_s<=1e-9 and max_obs_r<=1e-9 and
           obs_tap_dif==0 and len(PARITY)==14502,
           "archived frozen RF trace 14502 packets vs independent raw 4N observer plus pinned original extractor",
           dict(n=len(PARITY),bad=n_parity_bad,max_s=max_parity_s,max_r_m=max_parity_r,
                original_tap_mismatch=obs_tap_dif))
    direct=audit["checks"]["A04_SOURCE_DIRECT_ORACLE"]["measured"]
    record("T06_SOURCE_DIRECT_INTERNAL",direct["max_rel"]<=1e-10 and direct["n"]>=42,
           "Reused signed independent original-bank SOURCE/direct oracle from frozen pre-run audit, SHA-linked not a new runtime fit",direct)
    record("T07_SOURCE_NATIVE_COMPLEX",max_source_native<=5e-4 and np.sqrt(complex_sq/n_s)<=1e-4,
           "Native complex H matched, no common-phase scalar adjustment",
           dict(n=n_s,max_rel=max_source_native,rms_rel=np.sqrt(complex_sq/n_s)))
    record("T08_SOURCE_NATIVE_S",n_s==9519 and np.sqrt(s_sq/n_s)<=2e-6 and
           max_native_s<=2e-5 and n_native_tap_diff==0,
           "NativeLoS source signed s and common first tap",
           dict(n=n_s,rmse=np.sqrt(s_sq/n_s),max_abs=max_native_s,tap_mismatch=n_native_tap_diff))
    record("T09_SOURCE_JAC",qfd_fail==0 and qfd_count>0 and
           max_r_jac<=1e-10 and max_bias_jac<=1e-12,
           "all poses stable interior finite diff with per-axis crossings ledger; no FD PASS on boundaries",
           dict(stable_fd_axes=qfd_count,fd_max_abs=qfd_max,fail=qfd_fail,
                source_Hr_max_error=max_r_jac,bias_direct_column_max=max_bias_jac,
                crossings=dict(METRICS["crossings"])))
    record("T10_OLD_LUT",max_old_s<=1e-12 and max_old_j<=1e-12 and n_LUT==9519,
           "independent eight-corner numeric LUT s and analytic J on all 9519 C0 poses",
           dict(n=n_LUT,s_max=max_old_s,J_max=max_old_j))
    record("T11_MODEL_SHIFT",max_source_old_identity<=1e-10 and max_range_unchanged<=1e-12,
           "signed e_s_source - e_s_old == h_old-h_src; exact frozen continuous range model",
           dict(s_err=max_source_old_identity,r_err_m=max_range_unchanged))
    moments,mean_err,cov_err,bad_groups=summarize(ROWS)
    record("T12_COV",not bad_groups,
           "within-stratum sample covariance with ddof=1 and native units; never inverted; PSD verified",
           dict(groups=len(moments),bad_psd=bad_groups[:8]))
    finite_all=(invalid_count==0 and all(x["status"]=="VALID" and np.isfinite(x["z_s_signed"])
                        and abs(x["z_s_signed"])<=1+1e-12 and np.isfinite(x["e_s_source"]) for x in ROWS))
    record("T13_S_DOMAIN",finite_all,"all signed ratios finite [-1,1], no clipping; original invalid logged",
           dict(original_invalid=invalid_count))
    record("T14_COUNTS",counts_h=={"FULL":9519,"LOS":9519} and
           timeline_counts=={"FULL":7251,"LOS":7251} and eval_counts=={"FULL":6201,"LOS":6201},
           "one Corridor; 19038 RF rows, 14502 archive-matched temporal rows, t>=30 12402",
           dict(H=dict(counts_h),timeline=dict(timeline_counts),eval=dict(eval_counts)))
    record("T15_P1_METRICS",mean_err<=1e-10 and cov_err<=1e-9,
           "two independent moment formulas, same n, no rejected row deletion",
           dict(mean_max=mean_err,cov_max=cov_err,groups=len(moments)))
    METRICS["quantiles_abs_model_shift"]={str(q):float(np.quantile(
        np.abs(np.array([r["delta_e_s"] for r in ROWS if r["channel"]=="FULL"])),q)) for q in (.5,.9,.95,.99,1.)}
    METRICS["full_los_mp_s"]={
        "n":9519,
        "rmse":float(np.sqrt(np.mean(np.array([r["multipath_s_contrast"] for r in ROWS if r["channel"]=="FULL"])**2))),
        "mean":float(np.mean(np.array([r["multipath_s_contrast"] for r in ROWS if r["channel"]=="FULL"])))}
    METRICS["distance_strata"]=["0-5m","5-10m","10m-inf"]
    METRICS["statistical_independent_scenes"]=1
    METRICS["num_invalid_ledger_records"]=len(LEDGER)
    csvs=[
     ("P1_SOURCE_OBSERVER_CANARY.csv",CANARY,list(CANARY[0])),
     ("P1_RAW_OBSERVER_PARITY.csv",PARITY,list(PARITY[0])),
     ("P1_MATCHED_SIGNED_ERRORS.csv",ROWS,list(ROWS[0])),
     ("P1_STRATIFIED_MOMENTS.csv",moments,list(moments[0])),
     ("P1_INVALID_AND_BOUNDARY_LEDGER.csv",LEDGER,
       ["case_id","channel","pose_id","t_s","type","axis","reason","analytic","fd","abs_error"])]
    for name,rows,cols in csvs:
        writetable(name,rows,cols)
        print("P1_OUTPUT",name,len(rows),flush=True)
    # Descriptive only, no model ranking based on holdout; all cases included.
    source_all=[x for x in moments if x["stratum_level"]=="CHANNEL_ALL"]
    METRICS["channel_all"]=source_all
    print("P1_MODEL_COMPARISON",json.dumps(source_all),flush=True)
    return

if __name__=="__main__":
  error=None
  try:main()
  except BaseException as exc:
      error=repr(exc)
      tb=traceback.format_exc()
      print("P1_ERROR",error,"\n",tb,flush=True)
      ERRS.append(dict(gate="RUNNER_EXCEPTION",error=error,traceback=tb))
  # Every failure writes a truthful machine-readable receipt, NEVER a green CI.
  verdict="PASS" if not ERRS and len([k for k in GATES if k.startswith("T")])==16 else "FAIL"
  if error:verdict="BLOCKED"
  result={
   "schema":"DLP_EKF_GAPS_001_P1_FROZEN_EXECUTION_QA_V1",
   "status":verdict,"science_verdict":"RETROSPECTIVE_DESCRIPTIVE_ONLY",
   "contract_id":"DLP-EKF-GAPS-001/P1-V1","contract_sha256":SHA_CONTRACT,
   "immutable_original_git_head":HEAD,"auditor_receipt_sha256":SHA_AUDIT,
   "freeze_file":"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101/P1_FROZEN_RATIFICATION_20261101.json",
   "runner_script_sha256":sha_file(__file__),
   "run_id":os.environ.get("GITHUB_RUN_ID"),"github_sha":os.environ.get("GITHUB_SHA"),
   "hardware":platform.platform(),"python":sys.version,"numpy":np.__version__,
   "cmdline":sys.argv,"duration_seconds":round(time.monotonic()-START,3),
   "gates":GATES,"failed_tests":ERRS,"metrics":METRICS,
   "result_rows":dict(full_plus_los=len(ROWS),original_trace_parity=len(PARITY),
       canary=len(CANARY),invalid_boundary_ledger=len(LEDGER)),
   "assumptions":["Existing single C0 scene. Repeated paths/anchors are not independent scenes.",
     "All source/old comparisons use same original H and range bridge.",
     "True pose is used ONLY for offline residual labels and physical source QA.",
     "Full/Native LoS contrast is deterministic matched contrast, not iid stochastic noise.",
     "Historical regression tolerances and previous known data prohibit new confirmatory accuracy claims.",
     "No P2, P3, P4, EKF, new RF, fitted conditional mean/covariance or hidden tuning is performed."],
   "sourcefd_complex_correction":"NONE","sourcefd_prior_2026_10_16":"HISTORICAL_REFERENCE_ONLY",
   "independent_scenes":SCENE_N,
   "not_approved":["new scene generalization","EKF improvement","posterior calibration","causal multipath effect"]
  }
  (OUT/"P1_SCIENCE_QA.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
  print("P1_FINAL_STATUS",verdict,"GATES",len(GATES),"FAILURES",len(ERRS),flush=True)
  sys.exit(0 if verdict=="PASS" else 1)
