#!/usr/bin/env python3
"""P4 Full C0+ covariance overconfidence forensic analysis; read-only.

Input is the frozen 12-original NPZ ZIP of P4 FULL run 41435839892, archived
origin hash and the original three route Tnone truth tables. No simulator RT,
EKF filter rerun, tuning, R fitting, probability ensemble or train/test claim.

All formulas written independently from the frozen P4 full scorer:
GT range residual, cross-anchor centered sample covariance, one-step
Full-vs-NativeLoS observation intervention on the SAME Full EKF prior, true
error before/after a gate, reported P contraction, NEES/NIS, geometric rank.
Same ChatGPT author -> SELF_REVIEW_ONLY, no independent human signoff.
"""
from __future__ import annotations
import csv,hashlib,io,json,math,os,pathlib,sys,traceback,time,platform,datetime,zipfile
from collections import Counter,defaultdict
import numpy as np

ROOT=pathlib.Path.cwd()
OUT=pathlib.Path(os.environ.get("P4_FORENSIC_OUT","/tmp/p4_covariance_forensics"))
OUT.mkdir(parents=True,exist_ok=True)
SRC=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/runs/P4_FULL_C0PLUS_NATIVE_41435839892"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
ZIP=SRC/"P4_FULL_12_COMPLETE_4STATE_EKF_TRACES.zip"
ZIP_HASH="5ecf2a326ec17c8ce4ccc7a42fe76227ecf6ad7ec027df9cdfcd2304dcb0acfe"
RR=.0068578637;OFFSET=-.5315983906250129
A=np.array([[4.,0.,2.65],[10.,0.,2.65],[16.,.8,2.65]])
CASES={"R2":979,"R4":742,"R5":1415}
ARMS=["DR4","R4_A_FULL","J4_A_FULL","R4_AB_FULL","R4_ABC_FULL","R4_A_EQPKT","R4_ABC_EQPKT"]
MODES=("los","full"); BIASES=("B0","L2");AN=("A","B","C")
CHI2={1:3.841458820694124,2:5.991464547107979,3:7.814727903251179}
GATE={1:6.6348966010212145,2:9.210340371976184,3:11.344866730144373}
TSTART=time.monotonic()
ALL={};GT={};SOURCE={};CHECKS={};ERRORS=[]
ROWS_COV=[];ROWS_ANCHOR=[];ROWS_FILTER=[];ROWS_UPDATES=[];ROWS_COUNTER=[];ROWS_TIME=[]
SUM={};PER_ROUTE={}
def file_sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def json_file(p):return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
def check(k,passed,details):
 CHECKS[k]={"status":"PASS" if passed else "FAIL","measure":details}
 if not passed:ERRORS.append(dict(id=k,details=details))
 print("COV_FORENSIC_CHECK",k,CHECKS[k]["status"],str(details)[:460],flush=True)
def require(v,why):
 if not bool(v):raise ValueError(why)
def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def readcsv(p):
 with pathlib.Path(p).open(newline="",encoding="utf-8") as f:
  return list(csv.DictReader(f))
def writecsv(p,rows):
 if not rows:
  pathlib.Path(p).write_text("NO_ROWS\n");return
 columns=list(rows[0])
 with pathlib.Path(p).open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=columns,extrasaction="ignore")
  w.writeheader();w.writerows(rows)
def finite(x):return bool(np.isfinite(x).all())
def sqr(a):return np.asarray(a)*np.asarray(a)
def rmse(x):return float(np.sqrt(np.mean(sqr(x))))
def cov2(x):
 c=np.cov(np.asarray(x),rowvar=False,ddof=1)
 return c
def corr(x):
 x=np.asarray(x,float)
 with np.errstate(divide="ignore",invalid="ignore"):
  return np.corrcoef(x,rowvar=False)
def pr(x,p):return float(np.percentile(np.asarray(x),p))
def lag1(arr):
 x=np.asarray(arr,float)
 if len(x)<3 or np.std(x[:-1])<=1e-15 or np.std(x[1:])<=1e-15:return None
 return float(np.corrcoef(x[:-1],x[1:])[0,1])
def sample_mean(x):return float(np.mean(x))
def summarize_filter(r,mode,bias,data,truth,indices,arm):
 idx=ARMS.index(arm);mask=data["t_s"]>=30
 x=data["xpost"][:,idx];P=data["Ppost"][:,idx]
 delta=x[mask,:3]-truth[mask,:3]
 delta[:,2]=wrap(delta[:,2])
 pose=P[mask,:3,:3];xy=P[mask,:2,:2]
 pose_nees=np.einsum("ni,nij,nj->n",delta,np.linalg.inv(pose),delta)
 err_xy_sq=sqr(delta[:,0])+sqr(delta[:,1])
 mean_p_xy=sample_mean(P[mask,0,0]+P[mask,1,1])
 mean_p_heading=sample_mean(P[mask,2,2])
 head_err=sqr(delta[:,2])
 xy_nees=np.einsum("ni,nij,nj->n",delta[:,:2],np.linalg.inv(xy),delta[:,:2])
 hnees=head_err/P[mask,2,2]
 accepted=np.count_nonzero(data["status"][:,idx]=="APPLIED")
 rejected=np.count_nonzero(data["status"][:,idx]=="REJECT")
 n=len(delta)
 row=dict(route=r,mode=mode,bias=bias,arm=arm,n_eval=n,
  original_scene_n=1,
  heading_rmse_deg=math.degrees(math.sqrt(sample_mean(head_err))),
  xy_rmse_m=math.sqrt(sample_mean(err_xy_sq)),
  posterior_heading_sigma_rms_deg=math.degrees(math.sqrt(mean_p_heading)),
  posterior_xy_radial_sigma_rms_m=math.sqrt(mean_p_xy),
  heading_rmse_over_p_sigma=float(math.sqrt(sample_mean(head_err)/mean_p_heading)),
  xy_rmse_over_p_sigma=float(math.sqrt(sample_mean(err_xy_sq)/mean_p_xy)),
  mean_P_xx_m2=sample_mean(P[mask,0,0]),mean_P_yy_m2=sample_mean(P[mask,1,1]),
  mean_P_heading_rad2=mean_p_heading,
  median_P_heading_rad2=pr(P[mask,2,2],50),
  pose_nees_mean=sample_mean(pose_nees),pose_nees_median=pr(pose_nees,50),
  pose_nees_p95=pr(pose_nees,95),
  heading_nees_mean=sample_mean(hnees),
  xy_nees_mean=sample_mean(xy_nees),
  pose95=sample_mean(pose_nees<=CHI2[3]),
  heading95=sample_mean(hnees<=CHI2[1]),
  xy95=sample_mean(xy_nees<=CHI2[2]),
  posthoc_alpha_to_pose95=float(pr(pose_nees,95)/CHI2[3]),
  posthoc_alpha_from_meanNEES=float(sample_mean(pose_nees)/3.),
  accepted_epochs=int(accepted),rejected_epochs=int(rejected),
  offered=int(accepted+rejected),
  rejected_fraction=float(rejected/max(1,accepted+rejected)),
  n_is_true_ensemble=False,
  label="Retrospective model-diagnostic; scalar alpha is NOT out-of-sample calibration")
 return row
def init():
 require(file_sha(ZIP)==ZIP_HASH,"EXACT_ORIGINAL_P4_FULL_TRACE_ZIP_SHA_INVALID")
 p1=json_file(P1/"P1_INPUT_LOCK.json")
 prior=json_file(SRC/"P4_FULL_POSTRUN_QA.json")
 require(prior["status"]=="PASS_FULL_C0PLUS_4STATE_EKF" and prior["score_rows"]==84 and
       prior["pooled_rows"]==28 and not prior["failures"],"ORIGINAL_P4_RESULT_UNAVAILABLE")
 names=set()
 with zipfile.ZipFile(ZIP) as z:
  require(z.testzip() is None,"ORIGINAL_P4_NPZ_ZIP_CRC_INVALID")
  for route,n in CASES.items():
   item=next(x for x in p1["base_assets"] if x["kind"]=="TIMELINE_TNONE" and
       "timeline_"+route+"_" in x["path"])
   fp=ROOT/item["path"]
   require(fp.exists() and file_sha(fp)==item["sha256"],"ORIGINAL_ROUTE_GT_SHA_CHANGED:"+route)
   items=readcsv(fp)
   require(len(items)==n,"ORIGINAL_ROUTE_COUNT_CHANGED:"+route)
   truth=np.array([[float(t["x"]),float(t["y"]),math.radians(float(t["yaw_body_deg"]))] for t in items])
   t=np.array([float(v["t_s"]) for v in items])
   pose_id=np.array([int(v["pose_id"]) for v in items])
   require(np.unique(pose_id).size==n and np.all(np.diff(t)>0),"DUPLICATE_NONMONOTONE_POSE")
   GT[route]=dict(x=truth,t=t,pose_id=pose_id,rows=items)
   for mode in MODES:
    for bias in BIASES:
     name=f"traces/P4_FULL_{route}_{mode}_{bias}_7STATE_EKF.npz"
     require(name in z.namelist(),"MISSING_EXACT_TRACE:"+name)
     with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as f:
      d={k:f[k].copy() for k in f.files}
     require(d["names"].tolist()==ARMS and
       d["route"].item()==route and d["channel"].item()==mode and
       d["bias"].item()==bias and
       np.array_equal(d["pose_id"],pose_id) and
       np.max(abs(d["t_s"]-t))<=1e-9,
       "P4_12_TRACE_KEY_POSE_TIME_NOT_SOURCE:"+name)
     require(d["xpost"].shape==(n,7,4) and d["Ppost"].shape==(n,7,4,4) and
       d["raw_native_ABC_z"].shape==(n,3,2) and
       finite(d["xpost"]) and finite(d["Ppost"]) and finite(d["raw_native_ABC_z"]),
       "P4_TRACE_MISSING_OR_NONFINITE:"+name)
     require(np.all(np.linalg.eigvalsh(d["Ppost"].reshape(-1,4,4))>0),
       "ORIGINAL_P4_COV_NOT_PD:"+name)
     require(np.all(np.isin(d["status"],["APPLIED","REJECT","DR_ONLY","SKIP_BUDGET"])),
       "UNEXPECTED_FILTER_STATE:"+name)
     names.add(name)
     ALL[(route,mode,bias)]=d
  require(len(z.namelist())==len(names)==12,"ORIGINAL_TRACE_ARCHIVE_UNEXPECTED_MEMBER_OR_COUNT")
 check("Q00_PINNED_12_TRACE_SHA",len(ALL)==12,{"SHA256":ZIP_HASH,"n_traces":len(ALL)})
 check("Q01_GT_POSE_TIME",sum(len(GT[r]["t"]) for r in CASES)==3136,
       {"full_C_native_epochs":3136,"unique_route_counts":CASES,"matched_all_12":True})
 for route in CASES:
  for mode in MODES:
   if not np.array_equal(ALL[(route,mode,"B0")]["raw_native_ABC_z"],
                         ALL[(route,mode,"L2")]["raw_native_ABC_z"]):
     ERRORS.append(dict(id="RAW_RF_DIFFERS_BY_SENSOR_BIAS",route=route,mode=mode))
  for bias in BIASES:
   los=ALL[(route,"los",bias)];full=ALL[(route,"full",bias)]
   for k in ("ds_odom","dtheta_gyro","dt_s","initial_x0","initial_P0"):
    if not np.array_equal(los[k],full[k]):
     ERRORS.append(dict(id="CONTROLS_OR_INIT_NOT_MATCHED",route=route,bias=bias,key=k))
 require(not ERRORS,"CONTROLS_INPUTS_NOT_MATCHED")
 check("Q02_IDENTICAL_PAIRED_CONTROLS_AND_RF",True,{"B0_L2_raw_RF_same":True,"Full_LoS_controls_same":True})
def compute_raw():
 for route,n in CASES.items():
  t=GT[route]["t"];gt=GT[route]["x"]
  dr=gt[:,None,:2]-A[None,:,:2]
  dd=np.sqrt(np.sum(dr*dr,axis=2)+(.45-A[None,:,2])**2)
  h=dd+OFFSET
  rawL=ALL[(route,"los","B0")]["raw_native_ABC_z"][:,:,0]
  rawF=ALL[(route,"full","B0")]["raw_native_ABC_z"][:,:,0]
  resL=rawL-h;resF=rawF-h;mp=rawF-rawL
  SOURCE[route]=dict(h=h,los=resL,full=resF,contrast=mp)
  for mode,res in (("los",resL),("full",resF),("full_minus_los",mp)):
   for i,anchor in enumerate(AN):
    e=res[:,i];evale=e[t>=30]
    ROWS_ANCHOR.append(dict(route=route,mode=mode,anchor=anchor,n=len(e),
      n_eval=len(evale),mean_m=sample_mean(evale),median_m=pr(evale,50),
      std_ddof1_m=float(np.std(evale,ddof=1)),
      rmse_m=rmse(evale),rmse_over_sqrt_R=float(rmse(evale)/math.sqrt(RR)),
      centered_variance_over_R=float(np.var(evale,ddof=1)/RR),
      mean_abs_m=sample_mean(abs(evale)),p95_abs_m=pr(abs(evale),95),
      mean_square_over_R=sample_mean(sqr(evale))/RR,
      positive_frac=sample_mean(evale>0),negative_frac=sample_mean(evale<0),
      route_lag1_corr=lag1(evale),description="sample error at GT, single route not IID"))
   sel=t>=30
   C=cov2(res[sel]);R=np.corrcoef(res[sel],rowvar=False)
   eig=np.linalg.eigvalsh(C)
   m=np.mean(res[sel],axis=0)
   ROWS_COV.append(dict(route=route,mode=mode,n=int(sel.sum()),
       mean_A_m=float(m[0]),mean_B_m=float(m[1]),mean_C_m=float(m[2]),
       cov_AA_m2=float(C[0,0]),cov_AB_m2=float(C[0,1]),cov_AC_m2=float(C[0,2]),
       cov_BB_m2=float(C[1,1]),cov_BC_m2=float(C[1,2]),cov_CC_m2=float(C[2,2]),
       corr_AB=float(R[0,1]),corr_AC=float(R[0,2]),corr_BC=float(R[1,2]),
       min_cov_eigen_m2=float(eig[0]),max_cov_eigen_m2=float(eig[-1]),
       original_Rr_m2=RR,
       diag_R_min_eigen_scale=float(eig[0]/RR),
       diag_R_max_eigen_scale=float(eig[-1]/RR),
       n_simulation_scenes=1))
 # Pooled time-label empirical moments, don't treat route/time as IID ensemble
 for mode in ("los","full","full_minus_los"):
  chunks=[]
  for route in CASES:
   e=SOURCE[route]["contrast" if mode=="full_minus_los" else mode]
   chunks.append(e[GT[route]["t"]>=30])
  e=np.concatenate(chunks,axis=0)
  for i,anchor in enumerate(AN):
   d=e[:,i];ROWS_ANCHOR.append(dict(route="POOLED",mode=mode,anchor=anchor,n=len(d),
     n_eval=len(d),mean_m=sample_mean(d),median_m=pr(d,50),
     std_ddof1_m=float(np.std(d,ddof=1)),rmse_m=rmse(d),
     rmse_over_sqrt_R=rmse(d)/math.sqrt(RR),
     centered_variance_over_R=float(np.var(d,ddof=1)/RR),
     mean_abs_m=sample_mean(abs(d)),p95_abs_m=pr(abs(d),95),
     mean_square_over_R=sample_mean(sqr(d))/RR,
     positive_frac=sample_mean(d>0),negative_frac=sample_mean(d<0),
     route_lag1_corr=None,description="pooled time-dependent source error, NOT independent realization"))
  C=cov2(e);R=corr(e);eig=np.linalg.eigvalsh(C);m=e.mean(axis=0)
  ROWS_COV.append(dict(route="POOLED",mode=mode,n=len(e),mean_A_m=float(m[0]),
    mean_B_m=float(m[1]),mean_C_m=float(m[2]),
    cov_AA_m2=float(C[0,0]),cov_AB_m2=float(C[0,1]),cov_AC_m2=float(C[0,2]),
    cov_BB_m2=float(C[1,1]),cov_BC_m2=float(C[1,2]),cov_CC_m2=float(C[2,2]),
    corr_AB=float(R[0,1]),corr_AC=float(R[0,2]),corr_BC=float(R[1,2]),
    min_cov_eigen_m2=float(eig[0]),max_cov_eigen_m2=float(eig[-1]),
    original_Rr_m2=RR,diag_R_min_eigen_scale=float(eig[0]/RR),
    diag_R_max_eigen_scale=float(eig[-1]/RR),n_simulation_scenes=1))
 check("Q03_ALL_PHYSICAL_GT_RESIDUALS",len(ROWS_COV)==12 and len(ROWS_ANCHOR)==36 and
     all(x["min_cov_eigen_m2"]>=-1e-10 for x in ROWS_COV),
     {"route_mode_groups":len(ROWS_COV),"anchor_groups":len(ROWS_ANCHOR)})
def geometric():
 groups=[]
 for route in CASES:
  gt=GT[route]["x"];t=GT[route]["t"];g=gt[t>=30]
  dr=g[:,None,:2]-A[None,:,:2]
  d=np.sqrt(np.sum(dr*dr,axis=2)+(.45-A[None,:,2])**2)
  H=dr/d[:,:,None]
  for name,sub in (("A",H[:,:1]),("AB",H[:,:2]),("ABC",H)):
   # Broadcast all actual GT positions, 2D geometry only; first singular
   # value of single row is rank1 and second is mathematically zero.
   gram=np.einsum("nai,naj->nij",sub,sub)/RR
   eig=np.linalg.eigvalsh(gram)
   groups.append(dict(route=route,anchor_set=name,n=len(g),
      min_eig_information_p10=float(np.quantile(eig[:,0],.10)),
      min_eig_information_median=float(np.median(eig[:,0])),
      min_eig_information_mean=float(np.mean(eig[:,0])),
      trace_information_median=float(np.median(np.trace(gram,axis1=1,axis2=2))),
      weak_eig_gt_1e_minus6_fraction=float(np.mean(eig[:,0]>1e-6)),
      scene_n=1,explanation="instantaneous range xy information at GT, not EKF observability in yaw/bias"))
 return groups
def filters():
 original=readcsv(SRC/"P4_FULL_28_POOLED_METRICS.csv")
 published={(r["channel"],r["bias"],r["arm"]):r for r in original}
 paired=defaultdict(list)
 for route in CASES:
  gt=GT[route]["x"]
  for mode in MODES:
   for bias in BIASES:
    data=ALL[(route,mode,bias)]
    for arm in ARMS:
     row=summarize_filter(route,mode,bias,data,gt,None,arm)
     ROWS_FILTER.append(row)
     paired[(mode,bias,arm)].append(row)
 maxbaseline=0.
 for key,items in paired.items():
  n=sum(r["n_eval"] for r in items)
  orig=published[key]
  h=math.sqrt(sum(x["n_eval"]*x["heading_rmse_deg"]**2 for x in items)/n)
  xy=math.sqrt(sum(x["n_eval"]*x["xy_rmse_m"]**2 for x in items)/n)
  coverage=sum(x["n_eval"]*x["pose95"] for x in items)/n
  deviation=max(abs(h-float(orig["heading_rmse_deg"])),
      abs(xy-float(orig["xy_rmse_m"])),abs(coverage-float(orig["pose95"])))
  maxbaseline=max(maxbaseline,deviation)
  if deviation>1e-9:ERRORS.append(dict(id="BASELINE_MISMATCH",key=key,values=[h,xy,coverage],delta=deviation))
  # exact timeweighting; combine squared error/sigma ratios correctly
  ratio_h=math.sqrt(sum(x["n_eval"]*(math.radians(x["heading_rmse_deg"])**2) for x in items)/
      sum(x["n_eval"]*x["mean_P_heading_rad2"] for x in items))
  ratio_xy=math.sqrt(sum(x["n_eval"]*x["xy_rmse_m"]**2 for x in items)/
      sum(x["n_eval"]*(x["mean_P_xx_m2"]+x["mean_P_yy_m2"]) for x in items))
  SUM[key]=dict(mode=key[0],bias=key[1],arm=key[2],n_eval=n,
   heading_rmse_deg=h,xy_rmse_m=xy,pose95=coverage,
   heading_to_reported_sigma=ratio_h,xy_error_to_radial_sigma=ratio_xy,
   mean_P_xy_trace_m2=sum(x["n_eval"]*(x["mean_P_xx_m2"]+x["mean_P_yy_m2"]) for x in items)/n,
   mean_P_heading_rad2=sum(x["n_eval"]*x["mean_P_heading_rad2"] for x in items)/n,
   mean_pose_NEES=sum(x["n_eval"]*x["pose_nees_mean"] for x in items)/n,
   n_accepted=sum(x["accepted_epochs"] for x in items),
   n_rejected=sum(x["rejected_epochs"] for x in items))
 check("Q04_RECOMPUTE_FROZEN_28_SCORES",len(SUM)==28 and maxbaseline<=1e-9,
       {"pooled_score_n":len(SUM),"max_heading_XY_coverage_difference":maxbaseline})
def event_groups():
 # filter only the primary range methods; other arms remain in score report.
 for route in CASES:
  gt=GT[route]["x"];time=GT[route]["t"];ids=GT[route]["pose_id"]
  for mode in MODES:
   for bias in BIASES:
    data=ALL[(route,mode,bias)]
    for arm in ("R4_A_FULL","R4_AB_FULL","R4_ABC_FULL","J4_A_FULL"):
     j=ARMS.index(arm)
     status=data["status"][:,j]
     accept=(status=="APPLIED")
     reject=(status=="REJECT")
     offered=accept|reject
     xp=data["xprior"][:,j];x=data["xpost"][:,j]
     priorP=data["Pprior"][:,j];P=data["Ppost"][:,j]
     de1=xp[:,:3]-gt;de2=x[:,:3]-gt
     de1[:,2]=wrap(de1[:,2]);de2[:,2]=wrap(de2[:,2])
     prior_xy_sq=np.sum(sqr(de1[:,:2]),axis=1)
     post_xy_sq=np.sum(sqr(de2[:,:2]),axis=1)
     prior_head_sq=sqr(de1[:,2]);post_head_sq=sqr(de2[:,2])
     ptr1=priorP[:,0,0]+priorP[:,1,1];ptr2=P[:,0,0]+P[:,1,1]
     prior_headvar=priorP[:,2,2];post_headvar=P[:,2,2]
     nis=data["nis"][:,j];dims=2 if arm=="J4_A_FULL" else {"R4_A_FULL":1,"R4_AB_FULL":2,"R4_ABC_FULL":3}[arm]
     gate_threshold=GATE[dims]
     max_error=0.
     if accept.any():
      delta=x[accept]-xp[accept]
      delta[:,2]=wrap(delta[:,2])
      correction=np.einsum("nij,nj->ni",data["K"][accept,j,:,:dims],
                           data["innovation"][accept,j,:dims])
      dd=correction-delta;dd[:,2]=wrap(dd[:,2])
      max_error=float(np.max(abs(dd)))
     use=accept&(time>=30)
     offered_scored=offered&(time>=30)
     n=int(np.count_nonzero(use))
     row=dict(route=route,mode=mode,bias=bias,arm=arm,
       n_offered_all=int(offered.sum()),n_accepted_all=int(accept.sum()),
       n_rejected_all=int(reject.sum()),rejected_fraction_all=float(reject.sum()/max(1,offered.sum())),
       n_accepted_t_ge30=n,n_offered_t_ge30=int(offered_scored.sum()),
       dimension=dims,chisq99_gate=gate_threshold,
       mean_NIS_all=float(np.mean(nis[offered])),
       median_NIS_all=float(np.median(nis[offered])),
       mean_NIS_accepted=float(np.mean(nis[accept])) if accept.any() else None,
       NIS_above_gate_fraction=float(np.mean(nis[offered]>gate_threshold)),
       XY_error_sq_benefit_fraction=float(np.mean(post_xy_sq[use]<prior_xy_sq[use])) if n else None,
       XY_error_sq_harm_fraction=float(np.mean(post_xy_sq[use]>prior_xy_sq[use])) if n else None,
       mean_change_XY_error_sq_m2=float(np.mean(post_xy_sq[use]-prior_xy_sq[use])) if n else None,
       heading_error_sq_benefit_fraction=float(np.mean(post_head_sq[use]<prior_head_sq[use])) if n else None,
       mean_change_heading_error_sq_rad2=float(np.mean(post_head_sq[use]-prior_head_sq[use])) if n else None,
       mean_prior_XY_error_m=float(np.mean(np.sqrt(prior_xy_sq[use]))) if n else None,
       mean_post_XY_error_m=float(np.mean(np.sqrt(post_xy_sq[use]))) if n else None,
       median_Pxy_trace_contract_fraction=float(np.median(1-ptr2[use]/ptr1[use])) if n else None,
       mean_Pxy_trace_contract_fraction=float(np.mean(1-ptr2[use]/ptr1[use])) if n else None,
       median_heading_variance_contract_fraction=float(np.median(1-post_headvar[use]/prior_headvar[use])) if n else None,
       mean_heading_variance_contract_fraction=float(np.mean(1-post_headvar[use]/prior_headvar[use])) if n else None,
       max_error_stored_K_innovation_identity=max_error,
       accepted_state_change_not_using_true_state=True)
     ROWS_UPDATES.append(row)
     # Save all original paired time-point science evidence for reproducibility.
     if arm in ("R4_AB_FULL","R4_ABC_FULL"):
      for k in range(len(time)):
       ROWS_TIME.append(dict(route=route,mode=mode,bias=bias,arm=arm,
        pose_id=int(ids[k]),time_s=float(time[k]),step=k,status=str(status[k]),
        NIS=float(nis[k]),gate_threshold=gate_threshold,
        prior_xy_error_m=float(math.sqrt(prior_xy_sq[k])),
        posterior_xy_error_m=float(math.sqrt(post_xy_sq[k])),
        prior_heading_error_deg=float(math.degrees(de1[k,2])),
        posterior_heading_error_deg=float(math.degrees(de2[k,2])),
        prior_P_xy_trace_m2=float(ptr1[k]),posterior_P_xy_trace_m2=float(ptr2[k]),
        prior_P_heading_rad2=float(prior_headvar[k]),posterior_P_heading_rad2=float(post_headvar[k]),
        evaluated=bool(time[k]>=30),
        original_single_simulation_scene=True))
 check("Q05_ALL_UPDATES_AND_K_IDENTITY",len(ROWS_UPDATES)==48 and
     all(r["max_error_stored_K_innovation_identity"]<1e-9 for r in ROWS_UPDATES),
     {"n_update_groups":len(ROWS_UPDATES),"n_all_AB_ABC_time_rows":len(ROWS_TIME),
      "max_Knu_identity":max(r["max_error_stored_K_innovation_identity"] for r in ROWS_UPDATES)})
def counterfactual():
 for route in CASES:
  gt=GT[route]["x"];t=GT[route]["t"]
  for bias in BIASES:
   full=ALL[(route,"full",bias)]
   los=ALL[(route,"los",bias)]
   for arm in ("R4_AB_FULL","R4_ABC_FULL"):
    j=ARMS.index(arm);dim=2 if arm=="R4_AB_FULL" else 3
    xprev=full["xprior"][:,j,:];xpost=full["xpost"][:,j,:]
    status=full["status"][:,j]
    K=full["K"][:,j,:,:dim];S=full["S"][:,j,:dim,:dim]
    nuF=full["innovation"][:,j,:dim]
    zF=full["raw_native_ABC_z"][:,:dim,0]
    zL=los["raw_native_ABC_z"][:,:dim,0]
    h=zF-nuF
    nuL=zL-h
    fullNIS=np.einsum("ni,nij,nj->n",nuF,np.linalg.inv(S),nuF)
    losNIS=np.einsum("ni,nij,nj->n",nuL,np.linalg.inv(S),nuL)
    fullgate=fullNIS<=GATE[dim];losgate=losNIS<=GATE[dim]
    matched=(status=="APPLIED")==fullgate
    require(np.all(matched),"REPLAY_FULL_GATE_STATUS_NOT_IDENTICAL")
    Knu=np.einsum("nij,nj->ni",K,nuL)
    xcf=xprev.copy();xcf[losgate]=xprev[losgate]+Knu[losgate]
    xcf[:,2]=wrap(xcf[:,2])
    errF=xpost[:,:3]-gt;errCF=xcf[:,:3]-gt
    errF[:,2]=wrap(errF[:,2]);errCF[:,2]=wrap(errCF[:,2])
    errxyF=np.sum(sqr(errF[:,:2]),axis=1)
    errxyCF=np.sum(sqr(errCF[:,:2]),axis=1)
    headingF=sqr(errF[:,2]);headingCF=sqr(errCF[:,2])
    only=(t>=30)&(status=="APPLIED")&losgate
    cf_vs_full_delta=Knu-np.einsum("nij,nj->ni",K,nuF)
    model_identity=cf_vs_full_delta-np.einsum("nij,nj->ni",K,zL-zF)
    max_identity=float(np.max(abs(model_identity)))
    count=int(only.sum())
    row=dict(route=route,bias=bias,arm=arm,rf_mode="Full-prior_Full-vs-Native-LoS_same-step",
      n_all=len(t),n_full_accepted=int(fullgate.sum()),n_los_counterfactual_accepted=int(losgate.sum()),
      n_both_accepted_t_ge30=count,
      max_fixed_gain_delta_identity=max_identity,
      full_xy_rmse_on_common_prior_m=float(np.sqrt(np.mean(errxyF[only]))) if count else None,
      los_replacement_xy_rmse_same_prior_m=float(np.sqrt(np.mean(errxyCF[only]))) if count else None,
      full_heading_rmse_on_common_prior_deg=float(math.degrees(np.sqrt(np.mean(headingF[only])))) if count else None,
      los_replacement_heading_rmse_same_prior_deg=float(math.degrees(np.sqrt(np.mean(headingCF[only])))) if count else None,
      fraction_los_replacement_reduces_xy_error=float(np.mean(errxyCF[only]<errxyF[only])) if count else None,
      fraction_los_replacement_reduces_heading_error=float(np.mean(headingCF[only]<headingF[only])) if count else None,
      mean_shift_in_xy_from_paired_Full_minus_LoS_observation_m=float(np.mean(np.linalg.norm(np.einsum("nij,nj->ni",K,zF-zL)[only,:2],axis=1))) if count else None,
      p95_shift_in_xy_from_paired_Full_minus_LoS_m=pr(np.linalg.norm(np.einsum("nij,nj->ni",K,zF-zL)[only,:2],axis=1),95) if count else None,
      hypothesis_scope="Single step on SAME frozen Full prior/H/K; counterfactual LoS is not a new full-trajectory EKF",
      source_gt_used_for_diagnostic_only=True)
    ROWS_COUNTER.append(row)
 check("Q06_FIXED_PRIOR_FULL_LOS_COUNTERFACTUAL",len(ROWS_COUNTER)==12 and
     max(x["max_fixed_gain_delta_identity"] for x in ROWS_COUNTER)<=1e-9,
     {"cases":len(ROWS_COUNTER),"max_algebraic_delta_K_zi_identity":max(x["max_fixed_gain_delta_identity"] for x in ROWS_COUNTER)})
def execute():
 init()
 compute_raw()
 geom=geometric()
 filters()
 event_groups()
 counterfactual()
 require(not ERRORS,"DIAGNOSTIC_NUMERIC_QA_FAILED:"+repr(ERRORS[:5]))
 writecsv(OUT/"P4_RANGE_RESIDUAL_DISTRIBUTIONS.csv",ROWS_ANCHOR)
 writecsv(OUT/"P4_CROSS_ANCHOR_ERROR_COVARIANCE.csv",ROWS_COV)
 writecsv(OUT/"P4_RANGE_GEOMETRY_INFORMATION.csv",geom)
 writecsv(OUT/"P4_FILTER_POSTERIOR_CONSISTENCY.csv",ROWS_FILTER)
 writecsv(OUT/"P4_ACCEPTED_UPDATE_MECHANISM.csv",ROWS_UPDATES)
 writecsv(OUT/"P4_FULL_LOS_FIXED_PRIOR_COUNTERFACTUAL.csv",ROWS_COUNTER)
 writecsv(OUT/"P4_AB_ABC_PER_STEP_EVENT_LEDGER.csv",ROWS_TIME)
 pooled=list(SUM.values())
 writecsv(OUT/"P4_28_POOLED_POSTERIOR_SIGMA_VS_ERROR.csv",pooled)
 full_only=[x for x in pooled if x["mode"]=="full" and x["arm"] in ("DR4","R4_A_FULL","R4_AB_FULL","R4_ABC_FULL")]
 keyanchor=[x for x in ROWS_ANCHOR if x["route"]=="POOLED" and x["mode"]=="full"]
 keycov=next(x for x in ROWS_COV if x["route"]=="POOLED" and x["mode"]=="full")
 info=dict(schema="DLP_P4_FULL_C0PLUS_COVARIANCE_MECHANISM_DIAGNOSTIC_V1",
   status="PASS_SOURCE_BACKED_EXPLORATORY_DIAGNOSTIC",source_zip_sha256=ZIP_HASH,
   original_p4_full_run="41435839892",single_corridor_scene_n=1,sensor_seed=0,
   route_full_n=3136,route_evaluation_n=2686,
   modes=["full","los"],biases=["B0","L2"],arms_original=ARMS,
   source_reused_no_R_fit=True,source_raw_H_not_rerun=True,
   source_range_noise_Rr_m2=RR,source_range_noise_sigma_r_m=math.sqrt(RR),
   checks=CHECKS,all_route_full_pose_sigma_evidence=full_only,
   pooled_full_range_anchor_stats=keyanchor,
   pooled_full_cross_anchor_covariance=keycov,
   full_los_counterfactual=ROWS_COUNTER,
   geometry=geom,
   row_counts=dict(raw_anchor_stats=len(ROWS_ANCHOR),cross_cov=len(ROWS_COV),
      geometry=len(geom),filter_consistency=len(ROWS_FILTER),
      pooled=len(pooled),update_events=len(ROWS_UPDATES),
      counterfactual=len(ROWS_COUNTER),time_point_ledger=len(ROWS_TIME)),
   scope_limits=[
    "Sample covariance across correlated route/time is not true independent sensor noise R",
    "Empirical alpha for coverage is retrospective on same C0, not certified covariance adjustment",
    "Full→LoS one-step substitution holds frozen Full prior/gain, not a complete alternative trajectory",
    "Finite errors may reflect systematic range bias, spatial correlation, nonlinearity and process model simultaneously",
    "This numerical arithmetic does not provide independent human-reviewed scientific causality"
   ],
   code_sha256=file_sha(__file__),github_run=os.environ.get("GITHUB_RUN_ID"),
   runtime=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),
     elapsed_sec=time.monotonic()-TSTART,UTC=datetime.datetime.now(datetime.timezone.utc).isoformat()))
 (OUT/"P4_COVARIANCE_MECHANISM_QA.json").write_text(json.dumps(info,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
 print("P4_COVARIANCE_FORENSICS_FINAL",info["status"],"CHECKS",len(CHECKS),
    "GT_COV",len(ROWS_COV),"UPDATES",len(ROWS_UPDATES),
    "PAIR_COUNTERFACTUAL",len(ROWS_COUNTER),flush=True)
if __name__=="__main__":
 try:execute()
 except Exception as exc:
  ERRORS.append(dict(id="UNHANDLED_DIAGNOSTIC_EXCEPTION",error=repr(exc),traceback=traceback.format_exc()))
  print("P4_COVARIANCE_FORENSICS_FATAL",repr(exc),traceback.format_exc(),flush=True)
  (OUT/"P4_FORENSICS_BLOCKED.json").write_text(json.dumps(dict(
    status="BLOCKED",source_sha256=ZIP_HASH,errors=ERRORS,already_checked=CHECKS,
    code_sha256=file_sha(__file__)),indent=2,ensure_ascii=False,allow_nan=False)+"\n")
  sys.exit(1)
