#!/usr/bin/env python3
"""Offline 7-case first-arrival common-window two-LP ratio, operational-heading association.
One-shot quality feature diagnostic only, NOT the requested closed-loop drive EKF.
No oracle labels or true pose leak into model features. Existing fixed observer parity is gated.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
RUN=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
CASES=("R2_aA_m0","R2_aB_m0","R2_aA_m45","R4_aA_m0",
       "R4_aB_m0","R5_aA_m0","R5_aB_m0")
SEED=20261010
GATES=(4,8,16)
FEATS={
 "CONSTANT":[],
 "FP_ONLY":["range_m","P5_log_power","s_fp","abs_s_fp"],
 "FP_PLUS_GATE4":["range_m","P5_log_power","s_fp","abs_s_fp","s_c4","delta_abs_c4"],
 "FP_PLUS_GATES":["range_m","P5_log_power","s_fp","abs_s_fp","s_c4","s_c8","s_c16",
                  "delta_abs_c4","delta_abs_c8","delta_abs_c16"],
 "EARLY_ONLY":["P5_log_power","s_c4","s_c8","s_c16"],
 "FP_PLUS_CIR_SHAPE":["range_m","P5_log_power","s_fp","abs_s_fp",
                      "P1_jsd","P2_peak_difference_ns","P3_early_asymmetry","P4_shape_L1"]
}
C0=299792458.0

def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for q in iter(lambda:f.read(4*1024*1024),b""):h.update(q)
 return h.hexdigest()

def packet(h4,freqs):
 """Original Hann, 4N padded CIR, 30% leading edge common two-port FP plus gate energies."""
 n=len(h4);nf=len(freqs);assert len(h4.shape)==4 and h4.shape[1:]==(nf,2,2)
 w=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
 buf=np.zeros((n,4*nf,2),np.complex128)
 buf[:,:nf,:]=np.asarray(h4[...,0],np.complex128)*w[None,:,None]
 cir=np.fft.ifft(buf,axis=1)*nf
 power=np.abs(cir)**2
 peak=np.sqrt(power).max(axis=1)
 branch=peak.argmax(axis=1)
 best=np.sqrt(power)[np.arange(n)[:,None],np.arange(4*nf)[None,:],branch[:,None]]
 fp=(best>=.3*best.max(axis=1)[:,None]).argmax(axis=1)
 p=power[np.arange(n),fp,:]
 den=p.sum(axis=1)
 s=np.divide(p[:,0]-p[:,1],den,out=np.full(n,np.nan),where=den>0)
 out=dict(tap=fp,port=branch,s_fp=s,P1=p[:,0],P2=p[:,1])
 for L in GATES:
  idx=fp[:,None]+np.arange(L)[None,:]
  valid=idx[:,-1]<power.shape[1]
  assert valid.all(),"CIR early gate crosses end of buffer"
  energy=power[np.arange(n)[:,None,None],idx[:,:,None],np.arange(2)[None,None,:]].sum(axis=1)
  tot=energy.sum(axis=1)
  out[f"P1_c{L}"]=energy[:,0]
  out[f"P2_c{L}"]=energy[:,1]
  out[f"s_c{L}"]=np.divide(energy[:,0]-energy[:,1],tot,out=np.full(n,np.nan),where=tot>0)
 return out

def from_full_los():
 features=pd.read_csv(RUN/"OUTPUT/01_FEATURES.csv")
 oracle=pd.read_csv(RUN/"OUTPUT/02_LABELS_EVAL_ONLY.csv")
 assert not features.duplicated(["case","pose_id"]).any()
 assert not oracle.duplicated(["case","pose_id"]).any()
 stored=features.set_index(["case","pose_id"])
 truth=oracle.set_index(["case","pose_id"])
 cases={a["case"]:a for a in json.loads((B/"CASES.json").read_text())}
 f=np.load(B.parent/"freqs_hz.npy")
 assert len(f)==257
 dt_ns=1e9/(4*len(f)*(f[1]-f[0]))
 rows=[];labels=[];parity=[]
 for case in CASES:
  c=cases[case]
  p=B/"FULL_RF"/f"H_{case}.npy";pl=B/f"H_LoS_{case}.npy"
  assert sha(p)==c["input_H_sha256"],case+" full SHA"
  assert sha(pl)==c["H_sha256"],case+" LoS SHA"
  h=np.load(p,mmap_mode="r");hl=np.load(pl,mmap_mode="r")
  assert h.shape==hl.shape==(c["poses"],257,2,2)
  samples=json.loads((B/case/"SAMPLES.json").read_text())
  assert len(samples)==len(h)
  sample_ids=[int(s["pose_id"]) for s in samples]
  assert len(set(sample_ids))==len(sample_ids)
  v=stored.loc[[(case,i) for i in sample_ids]].reset_index()
  z=truth.loc[[(case,i) for i in sample_ids]].reset_index()
  assert np.array_equal(v.pose_id.to_numpy(),sample_ids)
  full=packet(h,f);clean=packet(hl,f)
  max_fp=float(np.nanmax(abs(v.s.to_numpy()-full["s_fp"])))
  max_tap=int(np.max(abs(v.tap.to_numpy()-full["tap"])))
  max_los=float(np.nanmax(abs(z.s_los.to_numpy()-clean["s_fp"])))
  max_mp=float(np.nanmax(abs(z.e_MP.to_numpy()-(full["s_fp"]-clean["s_fp"]))))
  parity.append(dict(case=case,n_pose=len(h),s_fp_max_abs=max_fp,tap_mismatch_max=max_tap,
     los_s_fp_max_abs=max_los,eMP_max_abs=max_mp,sha_full=sha(p),sha_los=sha(pl)))
  print("PARITY",case,"full_fp",max_fp,"tap",max_tap,"los",max_los,"eMP",max_mp,flush=True)
  assert max_fp<1e-12 and max_los<1e-12 and max_mp<1e-12 and max_tap==0,case+" OBSERVER_PARITY_FAIL"
  d=(v[["case","route","pose_id","station_group","range_m","P5_log_power","P1_jsd",
         "P2_peak_difference_ns","P3_early_asymmetry","P4_shape_L1"]].copy())
  d["mount_deg"]=int(c["mount_deg"]);d["anchor_name"]=case.split("_")[1]
  d["s_fp"]=full["s_fp"];d["abs_s_fp"]=abs(full["s_fp"])
  d["power_sum"]=full["P1"]+full["P2"]
  d["P1_fp"]=full["P1"];d["P2_fp"]=full["P2"];d["tap"]=full["tap"]
  d["tap_los"]=clean["tap"]
  a=z[["case","route","pose_id","true_distance_m","e_s","e_MP"]].copy()
  a["s_fp_full"]=full["s_fp"];a["s_fp_los"]=clean["s_fp"];a["tap_shift_fp"]=full["tap"]-clean["tap"]
  for L in GATES:
   d[f"s_c{L}"]=full[f"s_c{L}"]
   d[f"delta_abs_c{L}"]=abs(d[f"s_c{L}"]-d["s_fp"])
   d[f"contrast_c{L}"]=10*np.log10(np.maximum(full[f"P1_c{L}"],1e-250)/np.maximum(full[f"P2_c{L}"],1e-250))
   d[f"power_c{L}"]=full[f"P1_c{L}"]+full[f"P2_c{L}"]
   a[f"s_c{L}_los"]=clean[f"s_c{L}"]
   a[f"e_MP_c{L}"]=full[f"s_c{L}"]-clean[f"s_c{L}"]
   a[f"e_total_cluster_c{L}"]=np.nan  # no validated cluster-specific FFD LUT; unavailable
  rows.append(d);labels.append(a)
 return pd.concat(rows,ignore_index=True),pd.concat(labels,ignore_index=True),parity,float(dt_ns)

def operational_label():
 frames=[]
 for route in ("R2","R4","R5"):
  path=RUN/"RELIABILITY"/f"{route}_HELD_OUT_PREDICTIONS.csv.gz"
  x=pd.read_csv(path,usecols=["case","route","pose_id","station_group","correct_5deg","heading_error_deg"])
  assert x.route.nunique()==1 and x.route.iloc[0]==route
  v=x.groupby(["case","route","pose_id","station_group"],as_index=False).agg(
      n=("correct_5deg","size"),n_good=("correct_5deg","sum"),
      mean_heading_error_deg=("heading_error_deg","mean"),
      median_heading_error_deg=("heading_error_deg","median"))
  v["n_bad"]=v.n-v.n_good
  v["correct_fraction"]=v.n_good/v.n
  frames.append(v)
 return pd.concat(frames,ignore_index=True)

def prob_model(train,keys):
 if not keys:return None,float(train.n_good.sum()/train.n.sum())
 X=train[keys].to_numpy(dtype=float)
 xx=np.vstack([X,X]);y=np.r_[np.ones(len(X),int),np.zeros(len(X),int)]
 w=np.r_[train.n_good.to_numpy(float),train.n_bad.to_numpy(float)]
 valid=w>0
 if len(np.unique(y[valid]))<2:return None,float(train.n_good.sum()/train.n.sum())
 model=make_pipeline(SimpleImputer(strategy="median",add_indicator=True),
                      StandardScaler(),LogisticRegression(C=1,max_iter=2000))
 model.fit(xx[valid],y[valid],logisticregression__sample_weight=w[valid])
 return model,None

def evaluate(df,out):
 res=[];preds=[];bins=[]
 for route in ("R2","R4","R5"):
  train=df[df.route!=route];test=df[df.route==route]
  for name,keys in FEATS.items():
   model,default=prob_model(train,keys)
   q=np.full(len(test),default) if model is None else model.predict_proba(test[keys])[:,1]
   q=np.clip(q,1e-7,1-1e-7)
   loss=(test.n_good*(1-q)**2+test.n_bad*q**2)/test.n
   brier=float(np.average(loss,weights=test.n))
   yy=np.r_[np.ones(len(test),int),np.zeros(len(test),int)]
   ww=np.r_[test.n_good,test.n_bad]
   qq=np.r_[q,q]
   active=ww>0
   auc=float(roc_auc_score(yy[active],qq[active],sample_weight=ww[active])) if len(np.unique(yy[active]))>1 else None
   rec=dict(route=route,model=name,n_pose=len(test),n_available=int(test.n.sum()),
            brier=brier,auroc=auc,correct_prevalence=float(test.n_good.sum()/test.n.sum()),
            firstcluster_hardware_support="UNKNOWN",
            calibrated_independent_site=False)
   res.append(rec)
   print("FOLD",route,name,"brier",round(brier,5),"auc",None if auc is None else round(auc,4),flush=True)
   p=test[["case","route","pose_id","station_group","n","n_good","n_bad"]].copy()
   p["model"]=name;p["q_good"]=q;p["brier_per_pose"]=loss
   preds.append(p)
   k=np.minimum((q*10).astype(int),9)
   for i in range(10):
    m=(k==i)
    if m.any():bins.append(dict(route=route,model=name,bin=i,n_pose=int(m.sum()),
                        n_available=int(test.n.to_numpy()[m].sum()),
                        q_mean=float(np.average(q[m],weights=test.n.to_numpy()[m])),
                        actual_correct=float(test.n_good.to_numpy()[m].sum()/test.n.to_numpy()[m].sum())))
 pd.DataFrame(res).to_csv(out/"HELDOUT_CORRECT5.csv",index=False)
 pred=pd.concat(preds,ignore_index=True)
 pred.to_csv(out/"HELDOUT_PREDICTIONS.csv.gz",index=False)
 pd.DataFrame(bins).to_csv(out/"CALIBRATION_BINS.csv",index=False)
 return pd.DataFrame(res),pred

def bootstrap(pred):
 p=pred.pivot(index=["case","route","pose_id","station_group"],columns="model",
              values="brier_per_pose").reset_index()
 p.columns=[str(a) if not b else str(b) for a,b in p.columns.to_flat_index()] if isinstance(p.columns,pd.MultiIndex) else list(p.columns)
 cnt=pred.drop_duplicates(["case","pose_id"]).set_index(["case","pose_id"]).n
 p["n"]=[cnt.loc[(r.case,r.pose_id)] for r in p.itertuples()]
 rng=np.random.default_rng(SEED);result=[]
 for route in ("R2","R4","R5"):
  d=p[p.route==route]
  for a,b in (("FP_PLUS_GATE4","FP_ONLY"),("FP_PLUS_GATES","FP_ONLY"),
              ("FP_PLUS_CIR_SHAPE","FP_ONLY")):
   diff=d[a]-d[b]
   gr=d.assign(ss=diff*d.n).groupby("station_group").agg(total=("ss","sum"),n=("n","sum"))
   idx=rng.integers(0,len(gr),(1000,len(gr)))
   boot=gr.total.to_numpy()[idx].sum(axis=1)/gr.n.to_numpy()[idx].sum(axis=1)
   result.append(dict(route=route,contrast=a+" minus "+b,n_physical_stations=len(gr),
      n_case_pose=len(d),brier_delta=float(np.average(diff,weights=d.n)),
      ci95_lo=float(np.quantile(boot,.025)),ci95_hi=float(np.quantile(boot,.975)),
      n_bootstrap=1000))
 return pd.DataFrame(result)

def correlations(f,truth,oper):
 z=f.merge(truth,on=["case","route","pose_id"],validate="one_to_one").merge(
     oper[["case","route","pose_id","n","correct_fraction","mean_heading_error_deg"]],
     on=["case","route","pose_id"],validate="one_to_one")
 rows=[]
 covariates=["s_fp","abs_s_fp","s_c4","s_c8","s_c16","delta_abs_c4",
             "delta_abs_c8","delta_abs_c16","P5_log_power","range_m",
             "P1_jsd","P4_shape_L1"]
 for route in ("R2","R4","R5","ALL"):
  q=z if route=="ALL" else z[z.route==route]
  for feature in covariates:
   for target in ("mean_heading_error_deg","correct_fraction","e_MP","e_MP_c4","e_MP_c8","e_MP_c16"):
    x=q[feature];y=q[target]
    a=x.corr(y);b=x.corr(y,method="spearman")
    rows.append(dict(route=route,feature=feature,target=target,n_case_pose=len(q),
                  pearson=float(a) if pd.notna(a) else None,
                  spearman=float(b) if pd.notna(b) else None))
 return pd.DataFrame(rows)

def oracle_diagnostics(f,truth):
 z=f.merge(truth,on=["case","route","pose_id"],validate="one_to_one")
 z["distance_bin"]=pd.cut(z.true_distance_m,[0,5,10,np.inf],right=False).astype(str)
 rec=[]
 for (case,mount,distance),g in z.groupby(["case","mount_deg","distance_bin"],observed=True):
  for L in GATES:
   y=g[f"e_MP_c{L}"];v=g.e_MP
   rec.append(dict(case=case,mount_deg=mount,distance_bin=distance,n=len(g),cluster_taps=L,
                   fp_bias=float(v.mean()),fp_std=float(v.std(ddof=0)),fp_rms=float(np.sqrt(np.mean(v**2))),
                   cluster_bias=float(y.mean()),cluster_std=float(y.std(ddof=0)),cluster_rms=float(np.sqrt(np.mean(y**2))),
                   fp_small_cluster_large_rate=float(((abs(v)<.05)&(abs(y)>.1)).mean()),
                   cluster_vs_fp_abs_error_corr=float(abs(y).corr(abs(v))) if len(g)>3 else None,
                   median_abs_fp_cluster_measured_diff=float(np.median(g[f"delta_abs_c{L}"]))))
 return pd.DataFrame(rec)

def data_coverage():
 b=RUN/"PROBES/07_PROBE_STATIONS.csv.gz"
 if not b.exists():return dict(state="NO_PROBE_TRACE",closed_loop="NOT_RUN")
 z=pd.read_csv(b,usecols=["case","route","station","drift","seed","n_angles","status","pre_rf_state"] if False else
                     ["case","route","station","drift","seed","n_angles","status"])
 a=z[z.n_angles==3]
 eligible=a[a.status=="OFFLINE_DIAGONAL_SCORE_ONLY"]
 cases_all=a.groupby("case").station.nunique().to_dict()
 cases_ok=eligible.groupby("case").station.nunique().to_dict()
 return dict(original_sweep_case_station_count=int(a.groupby(["case","station"]).ngroups),
        evaluated_case_station_count=int(eligible.groupby(["case","station"]).ngroups),
        evaluated_prior_records=int(len(eligible)),
        old_cases_7=True,new_mount45_cases_needed=5,
        eligible_by_case={x:int(cases_ok.get(x,0)) for x in CASES},
        total_possible_by_case={x:int(cases_all.get(x,0)) for x in CASES},
        arbitrary_xy_and_yaw_RFs_available=False,
        closed_loop_trigger_stop_turn_return="NOT_RUN",
        reason="Stored sweep poses are sparse predefined stations, not an on-demand RF oracle at the actual low-reliability trigger position")

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True);args=ap.parse_args()
 out=args.out;out.mkdir(parents=True,exist_ok=True);start=time.time()
 (out/"EXECUTION_STATUS.json").write_text(json.dumps({"status":"STARTED","closed_loop_event_EKF":"NOT_RUN"},indent=2))
 f,t,checks,dt_ns=from_full_los()
 f.to_csv(out/"FIRST_CLUSTER_FEATURES.csv.gz",index=False)
 t.to_csv(out/"FIRST_CLUSTER_ORACLE_LABELS.csv.gz",index=False)
 (out/"PARITY.json").write_text(json.dumps({"cases":checks,"gate_taps":GATES,
                            "sample_grid_dt_ns":dt_ns,"observer_full_los_parity":"PASS"},indent=2))
 op=operational_label()
 op2=op.merge(f,on=["case","route","pose_id","station_group"],validate="many_to_one")
 print("operational_pose_count",len(op),"sensor_prior_repeated_available",int(op.n.sum()),flush=True)
 scores,pred=evaluate(op2,out)
 ci=bootstrap(pred);ci.to_csv(out/"CLUSTER_BOOTSTRAP.csv",index=False)
 corr=correlations(f,t,op)
 corr.to_csv(out/"ASSOCIATIONS.csv",index=False)
 diag=oracle_diagnostics(f,t)
 diag.to_csv(out/"FIRST_CLUSTER_DISTANCE_CASE_STATS.csv",index=False)
 coverage=data_coverage()
 (out/"CLOSED_LOOP_DATA_COVERAGE.json").write_text(json.dumps(coverage,indent=2))
 summary=dict(status="EXPLORATORY_FIRST_CLUSTER_COMPLETED",closed_loop_event_trigger="NOT_RUN",
       case_count=len(CASES),full_channel_pose_rows=len(f),
       operational_distinct_case_pose=len(op),prior_repeated_rows=int(op.n.sum()),
       dt_zero_padded_ns=dt_ns,fp_parity=checks,
       heldout=json.loads(scores.to_json(orient="records")),
       comparisons=json.loads(ci.to_json(orient="records")),
       observations_and_limitations=[
         "Existing amplitude-only CIR synthesized from full complex H; not verified hardware full CIR access.",
         "Numerous adjacent zero-padded CIR bins are correlated; cluster sum does not separate unresolved reflected rays.",
         "Window L=4/8/16 is a feature; an FP-only FFD LUT is NOT a calibrated observation model for cluster s.",
         "No online event trigger/controller simulation; arbitrary trigger station RF missing.",
         "Known single physical corridor, 7 case geometries, 5 mount45 cases outstanding.",
         "Operational heading label from saved RF-off sensor-v2 prior-based LUT inverse; only available subset.",
         "No new sensor noise arm; observation full/LoS H is noise-free.",
         "F01/F02 OPEN scientific_PASS=false."])
 (out/"SUMMARY.json").write_text(json.dumps(summary,indent=2,allow_nan=False))
 with (out/"SUMMARY_KO.md").open("w",encoding="utf-8") as w:
  w.write("# 7케이스 first-arrival 공통 창 LP 비 분석 완료\n\n")
  w.write("매시점 closed-loop EKF+위험 감지+제자리 프로브+주행 재개는 이번 실험에서 NOT_RUN입니다. 기존 7개 H의 오프라인 first-cluster 특징과 sensor-v2 heading 정답 관련성만 평가했습니다. \n\n")
  w.write("## FP 파형 및 gate 규약\n\nOriginal shared 30%-leading-edge FP tap; 4×zero-padded CIR 공통창 L=4/8/16 taps. sample grid step ns = "+str(round(dt_ns,6))+". LoS-only와 full에 동일 관측기 적용. 원 FP s/tap parity PASS. Gate signal은 실제 독립 경로 분해를 뜻하지 않습니다.\n\n")
  w.write("## Leave-one-route-out RF heading correct5 분류\n\n")
  w.write(scores.to_markdown(index=False))
  w.write("\n\n## FP_ONLY 대비 first-cluster 추가가치: 물리 station bootstrap\n\n")
  w.write(ci.to_markdown(index=False))
  w.write("\n\n## 오차정의\n\n")
  w.write("- 온라인 입력: s_FP, s_L, FP–cluster 차이, 수신전력, range. \n- Offline 정답: e_MP_FP = s_FP(full)−s_FP(LoS), e_MP_L = s_L(full)−s_L(LoS), and RF-heading 오류. \n- Full response first cluster에 대한 별도 h_L FFD LUT가 검증되지 않았으므로 s_L을 EKF에서 곧바로 대체 업데이트하지 않습니다.\n\n")
  w.write("## 물리 모델/데이터 가용성 한계\n\n"+json.dumps(coverage,ensure_ascii=False,indent=2)+"\n")
 print("FIRST_CLUSTER_RESULT",json.dumps({"pose_rows":len(f),"operational_pose":len(op),
 "scores":scores[["route","model","brier","auroc"]].to_dict("records"),
 "bootstrap":ci[["route","contrast","brier_delta","ci95_lo","ci95_hi"]].to_dict("records"),
 "coverage":coverage},allow_nan=False),flush=True)
 summary["elapsed_s"]=time.time()-start
 (out/"EXECUTION_STATUS.json").write_text(json.dumps({"status":"COMPLETED",
    "parity":"PASS","closed_loop_event_EKF":"NOT_RUN","n_pose":len(f),
    "n_operational_pose":len(op),"elapsed_s":summary["elapsed_s"]},indent=2))
if __name__=="__main__":
 main()
