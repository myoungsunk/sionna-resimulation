#!/usr/bin/env python3
"""Existing-data truth-only LUT mismatch and range/s temporal-covariance diagnostic.

No new Sionna, EKF, data fitting, filter Q/R modification.
The 7-case fixed FFD LUT and full/native LoS channels have paired true pose labels.
Correlations of a spatially repeated *deterministic RF bias* along a trajectory
must NOT be confused with sampled full state/measurement cross-time covariance.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
T=ROOT/"results/DRIVE_SIM_20261007/S1/routes"
def dd(d,col):
 v=np.asarray(d[col],dtype=float)
 return dict(mean=float(v.mean()),std=float(v.std(ddof=0)),rms=float(np.sqrt(np.mean(v*v))),
             median=float(np.median(v)),p95_abs=float(np.quantile(abs(v),.95)))
def pear(a,b):
 a=np.asarray(a,float);b=np.asarray(b,float)
 ok=np.isfinite(a)&np.isfinite(b)
 if ok.sum()<8 or np.std(a[ok])<1e-10 or np.std(b[ok])<1e-10:return np.nan
 return float(np.corrcoef(a[ok],b[ok])[0,1])
def acf(x,lag):
 return pear(x[:-lag],x[lag:])
def aggregates(df,groups,cols):
 rows=[]
 for keys,g in df.groupby(groups,observed=True,sort=True):
  if not isinstance(keys,tuple):keys=(keys,)
  q=dict(zip(groups,keys));q["n"]=len(g)
  for v in cols:
   if v not in g:continue
   st=dd(g,v)
   q.update({v+"_"+name:value for name,value in st.items()})
  if len(g)>4 and {"e_lut","e_MP"}.issubset(g):
   q["corr_eLUT_eMP"]=pear(g.e_lut,g.e_MP)
  rows.append(q)
 return pd.DataFrame(rows)
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True)
 arg=ap.parse_args();o=arg.out;o.mkdir(parents=True,exist_ok=True)
 labels=pd.read_csv(RUN/"OUTPUT/02_LABELS_EVAL_ONLY.csv")
 fp=pd.read_csv(RUN/"OUTPUT/01_FEATURES.csv",usecols=["case","pose_id","s","range_m","tap"])
 meta=json.loads((RUN/"LUT/hs_lut_meta.json").read_text())
 range_offset=float(meta["range_bias"]["mean_m"])
 expected=["case","route","pose_id","true_x","true_y","true_yaw_deg","true_distance_m",
          "s_lut_truth","s_los","e_s","e_MP","e_range","range_los","tap_los"]
 missing=[p for p in expected if p not in labels]
 assert not missing,missing
 assert not labels.duplicated(["case","pose_id"]).any()
 df=labels.merge(fp,on=["case","pose_id"],validate="one_to_one")
 assert len(df)==9519,(len(df),"expected 9519")
 df["e_lut"]=df.s_los-df.s_lut_truth
 df["s_full"]=df.s
 df["e_lut_identity_diff"]=df.e_s-df.e_MP-df.e_lut
 identity_max=float(df.e_lut_identity_diff.abs().max())
 assert identity_max<1e-12,("s decomposition mismatch",identity_max)
 df["e_range_los"]=df.range_los-df.true_distance_m
 df["e_range_mp"]=df.e_range-df.e_range_los
 df["e_range_model"]=df.e_range-range_offset
 df["abs_e_lut"]=abs(df.e_lut)
 df["abs_e_mp"]=abs(df.e_MP)
 df["abs_e_s_total"]=abs(df.e_s)
 df["distance_bin"]=pd.cut(df.true_distance_m,[0,5,10,np.inf],right=False,
                            labels=["0-5m","5-10m",">=10m"])
 df["yaw_bin"]=pd.cut((df.true_yaw_deg+180)%360-180,
                      [-181,-90,0,90,181],right=False,
                      labels=["-180:-90","-90:0","0:90","90:180"])
 summary=aggregates(df,["distance_bin"],
       ["e_lut","e_MP","e_s","e_range_model","e_range_mp","e_range_los"])
 summary.to_csv(o/"LUT_LOS_RANGE_BY_DISTANCE.csv",index=False)
 case=aggregates(df,["case","distance_bin"],
        ["e_lut","e_MP","e_s","e_range_model","e_range_mp"])
 case.to_csv(o/"LUT_LOS_BY_CASE_DISTANCE.csv",index=False)
 # The exact LoS-v-LUT residual may systematically depend on antenna pointing/azimuth.
 yaw=aggregates(df,["case","yaw_bin"],["e_lut","e_MP","e_s"])
 yaw.to_csv(o/"LUT_MISMATCH_BY_CASE_YAW.csv",index=False)
 df[["case","route","pose_id","true_x","true_y","true_yaw_deg",
      "true_distance_m","e_lut","e_MP","e_s",
      "e_range_model","e_range_mp","e_range_los","tap","tap_los"]].to_csv(
          o/"ORACLE_MODEL_ERROR_PER_POSE.csv.gz",index=False)
 # Primary time series is the *normal Tnone movement*, not the saved yaw-sweep grid.
 lag_records=[]
 aligned=[]
 for route in ["R2","R4","R5"]:
  tt=pd.read_csv(T/f"timeline_{route}_Tnone.csv")
  assert tt.pose_id.notna().all()
  for (name,group) in df[df.route==route].groupby("case"):
   ts=tt[["pose_id","t_s","phase","x","y","yaw_body_deg"]].merge(
       group,on="pose_id",how="inner",validate="one_to_one")
   assert len(ts)==len(tt),(name,len(ts),len(tt))
   assert np.max(abs(ts.x-ts.true_x))<1e-8
   assert np.max(abs(ts.y-ts.true_y))<1e-8
   # Check time increments explicitly.
   gap=np.diff(ts.t_s.values)
   assert np.min(gap)>.19999 and np.max(gap)<.20001,(route,gap.min(),gap.max())
   cols=["e_lut","e_MP","e_s","e_range_model","e_range_mp"]
   trow=dict(case=name,route=route,n_normal=len(ts),
             eMP_vs_rangeMP_pearson=pear(ts.e_MP,ts.e_range_mp),
             eTotalS_vs_rangeModel_pearson=pear(ts.e_s,ts.e_range_model),
             range_bias_model=float(ts.e_range_model.mean()),
             range_bias_original=float(ts.e_range.mean()))
   aligned.append(trow)
   for v in cols:
    a=ts[v].to_numpy(float)
    for lag in (1,2,5,10,25,50):
     if len(a)<=lag:continue
     lag_records.append(dict(case=name,route=route,
        variable=v,lag_samples=lag,lag_seconds=.2*lag,
        n_pairs=len(a)-lag,acf_pearson=acf(a,lag),
        mean_error=float(a.mean()),rms_error=float(np.sqrt(np.mean(a*a)))))
   # Cross-lag between range and s residuals.
   for lag in (0,1,5,10):
    xs=ts.e_range_model.to_numpy(float);ys=ts.e_s.to_numpy(float)
    for shift in (-1,1):
     x=xs[:len(xs)-lag] if shift>=0 and lag else (xs[lag:] if lag else xs)
     y=ys[lag:] if shift>=0 and lag else (ys[:len(ys)-lag] if lag else ys)
     lag_records.append(dict(case=name,route=route,variable="rangeModel_to_s" if shift>=0 else "s_to_rangeModel",
           lag_samples=lag,lag_seconds=.2*lag,n_pairs=len(x),acf_pearson=pear(x,y)))
 pd.DataFrame(lag_records).to_csv(o/"NORMAL_DRIVE_TIME_AND_CROSS_LAG.csv",index=False)
 pd.DataFrame(aligned).to_csv(o/"NORMAL_ROUTE_POSE_MATCHING.csv",index=False)
 # Pairwise same-XY yaw: covariance matrix is a *spatial* site sample,
 # NOT observation-noise time covariance conditional on fixed true pose.
 pairs=[]
 for name,g in df.groupby("case"):
  samples=json.loads((ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"/name/"SAMPLES.json").read_text())
  bypose=g.set_index("pose_id")
  cur=[]
  groups=[]
  for s in samples:
   if cur and (cur[-1]["x"],cur[-1]["y"])!=(s["x"],s["y"]):
    groups.append(cur);cur=[]
   cur.append(s)
  if cur:groups.append(cur)
  for station,group in enumerate(groups):
   if len(group)<5:continue
   ids=[int(group[k]["pose_id"]) for k in (0,2,4)]
   aa=bypose.loc[ids]
   outrow=dict(case=name,route=name.split("_")[0],station=station,
            x=float(group[0]["x"]),y=float(group[0]["y"]),
            distance_m=float(aa.true_distance_m.mean()),
            dpsi_step_1=float(group[2]["yaw_body_deg"]-group[0]["yaw_body_deg"]),
            dpsi_step_2=float(group[4]["yaw_body_deg"]-group[0]["yaw_body_deg"]))
   for j in range(3):
    for variable in ("e_lut","e_MP","e_s","e_range_model","e_range_mp"):
     outrow[f"{variable}_{j}"]=float(aa.iloc[j][variable])
   pairs.append(outrow)
 pairs=pd.DataFrame(pairs)
 assert len(pairs)==169,len(pairs)
 pairs.to_csv(o/"THREE_YAW_STATION_RESIDUALS.csv",index=False)
 cov_list=[]
 for typ in ("e_lut","e_MP","e_s","e_range_model","e_range_mp"):
  a=pairs[[f"{typ}_{j}" for j in range(3)]].to_numpy(float)
  cov=np.cov(a,rowvar=False,ddof=0)
  C=np.corrcoef(a,rowvar=False)
  for i in range(3):
   for j in range(3):
    cov_list.append(dict(variable=typ,i=i,j=j,observed_cov=float(cov[i,j]),
          corr=float(C[i,j]),site_group_count=169,
          channel_noise_independent_repeats=0))
 covx=pd.DataFrame(cov_list)
 covx.to_csv(o/"THREE_YAW_RF_SPATIAL_CROSS_COV.csv",index=False)
 response={
   "state":"COMPLETED_EXISTING_DATA_ORACLE_AND_RF_TEMPORAL_DIAGNOSTIC",
   "e_lut_identity_max":identity_max,
   "data_n_pose":len(df),"normal_route_pairs":pd.DataFrame(aligned).to_dict("records"),
   "n_case_station_groups":len(pairs),
   "range_filter_offset_m":range_offset,
   "range_filter_R_m2":float(.05**2+.05**2+(299792458/(1028*1.953125e6))**2/12),
   "range_filter_sigma_m":float(np.sqrt(.05**2+.05**2+(299792458/(1028*1.953125e6))**2/12)),
   "known_limits":[
       "No reconstructed true E[e_state(t) RF-noise(t+lag)^T] without per-time, per-seed full estimated state/cross covariance AND independent RF noise realizations.",
       "Spatial covariance of deterministic multipath residuals at different yaw angles is NOT temporal pose-measurement covariance conditional on fixed true pose.",
       "Same corridor, seven anchor/mount RF settings, partial motion priors; no independent scene generalization.",
       "Native LOS vs FFD LUT residual estimated on current 7 matching archived direct-LOS arrays. New native five H parity and LUT F01 L1 remain separately unresolved.",
       "Filter range offset is a calibrated mean detector bias; e_range without offset must not be confused with multipath-only bias.",
       "No new simulated RF or filter. Oracle data only for evaluation, never classifier inference."]}
 (o/"STATUS.json").write_text(json.dumps(response,indent=2,ensure_ascii=False,allow_nan=False))
 with (o/"REPORT_KO.md").open("w",encoding="utf-8") as f:
  f.write("# 고정 LUT–LoS 불일치 및 range/s 시간 상관: 실제 기존 데이터 재검산\n\n")
  f.write(f"전체 7케이스 9,519pose, FFD LUT s와 native matched LoS s 구분; e_s=e_MP+e_lut 항등식 최대 잔차 {identity_max:.3e}.\n\n")
  f.write("## 원 자료 오차 분해 (거리 bin)\n\n")
  cols=["distance_bin","n","e_lut_mean","e_lut_rms","e_MP_mean","e_MP_rms","e_s_mean","e_s_rms","e_range_model_mean","e_range_model_rms","e_range_mp_mean","e_range_mp_rms"]
  f.write(summary[cols].to_markdown(index=False,floatfmt=".6f"))
  f.write("\n\n## Tnone 경로 연속 RF 오차 ACF\n\n")
  lag=pd.DataFrame(lag_records)
  f.write(lag[(lag.variable.isin(["e_lut","e_MP","e_s","e_range_model"]))&(lag.lag_samples.isin([1,5,10]))][["case","variable","lag_seconds","acf_pearson"]].to_markdown(index=False,floatfmt=".4f"))
  f.write("\n\n## 같은 XY에서 3 yaw 관측의 oracle residual 공분산 (169 그룹)\n\n")
  f.write(covx[(covx.i<=covx.j)&covx.variable.isin(["e_lut","e_MP","e_s","e_range_model"])][["variable","i","j","observed_cov","corr"]].to_markdown(index=False,floatfmt=".5f"))
  f.write("\n\n## 과학적 결론/제한\n\n")
  f.write("이 값들은 deterministic channel error across spatial sites와 동일 run의 lagged channel error이지 full state–RF cross-time covariance가 아니다. 후자는 동일 시각·장소에서 다수 독립 sensor/RF-noise trial의 error-state plus innovation jointly recorded를 필요로 한다. Jacobian state transition과 noise sharing까지 포함한 predicted joint covariance와 empirical MC sample covariance를 같은 pose/timestamp에서 대조해야 한다. Without this, claim CROSS_TIME_POSE_RF_COV_VALIDATED = FALSE.\n")
 print("AUDIT_RESULT",json.dumps({"n":len(df),"identity_max":identity_max,
 "distance":summary[cols].to_dict("records"),
 "acf1":pd.DataFrame(lag_records).query("lag_samples==1 and variable in ['e_lut','e_MP','e_s','e_range_model']")[["case","variable","acf_pearson"]].to_dict("records"),
 "R_model_m":response["range_filter_sigma_m"]},allow_nan=False),flush=True)
if __name__=="__main__":
 main()
