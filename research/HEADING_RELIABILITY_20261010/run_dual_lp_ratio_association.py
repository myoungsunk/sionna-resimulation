#!/usr/bin/env python3
"""Registered exploratory dual-LP power ratio vs RF-heading error, pre-filter.
Input held-out-route RF-off-prior inverse heading labels, full RF features. No training truth leakage.
Same corridor: never generalize to different geometry or independent repetitions.
"""
from __future__ import annotations
import argparse, json, time
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
FROZEN={
    "seed":20261010, "heldout":"leave-one-route-out", "target":"RF-heading correct<=5deg",
    "selection":"available-only original v2 prior based RF inverse; no-match and ambiguous excluded and coverage recorded",
    "folds":["R2","R4","R5"],
    "models":{
        "prevalence":[],
        "range":["range_m"],
        "range+power":["range_m","P5_log_power"],
        "ratio_only":["P5_s","s_abs"],
        "range+power+ratio":["range_m","P5_log_power","P5_s","s_abs"],
        "CIR_shape":["P1_jsd","P2_peak_difference_ns","P3_early_asymmetry","P4_shape_L1"],
        "range+power+ratio+CIR":["range_m","P5_log_power","P5_s","s_abs","P1_jsd","P2_peak_difference_ns","P3_early_asymmetry","P4_shape_L1","D1_mean_ns","D1_diff_ns"]
    },
    "precomputed_metric_contrasts":["range+power+ratio minus range+power",
                                   "range+power+ratio+CIR minus range+power+ratio"],
    "noise":"frozen noise-free full RF H; gyro/wheel from existing v2",
    "cluster":"route + station_group (x,y)"
}
def corr(x,y):
    a=pd.DataFrame({"x":x,"y":y}).replace([np.inf,-np.inf],np.nan).dropna()
    if len(a)<4 or a.x.std()<1e-14 or a.y.std()<1e-14:return (np.nan,np.nan,len(a))
    return (float(a.x.corr(a.y)),float(a.x.corr(a.y,method="spearman")),len(a))

def merged_data():
    feats=pd.read_csv(RUN/"OUTPUT/01_FEATURES.csv")
    assert not feats.duplicated(["case","pose_id"]).any()
    assert (feats.power1>=0).all() and (feats.power2>=0).all()
    feats["s_abs"]=abs(feats["s"])
    feats["lp_ratio_log10"]=10*np.log10(np.maximum(feats.power1,1e-250)/np.maximum(feats.power2,1e-250))
    # Same underlying contrast reparameterized: not independent additional RF information.
    feats["ratio_from_s_db"]=10*np.log10(np.maximum((1+feats.s)/(1-feats.s),1e-250))
    feats["power_equivalent_s"]=((feats.power1-feats.power2)/(feats.power1+feats.power2))
    parity=np.max(abs(feats["s"]-feats["power_equivalent_s"]))
    assert parity<1e-10,parity
    cols=["case","route","pose_id","station_group","range_m","P5_log_power","P5_s","s_abs","lp_ratio_log10","ratio_from_s_db",
          "P1_jsd","P2_peak_difference_ns","P3_early_asymmetry","P4_shape_L1","D1_mean_ns","D1_diff_ns"]
    f=feats[cols]
    info=[];raw=[]
    for route in FROZEN["folds"]:
        file=RUN/"RELIABILITY"/f"{route}_HELD_OUT_PREDICTIONS.csv.gz"
        use=["case","route","pose_id","correct_5deg","heading_error_deg","q_distance_slope","q_DPK"]
        g=pd.read_csv(file,usecols=use)
        assert g.route.nunique()==1 and g.route.iloc[0]==route
        join=g.merge(f,on=["case","route","pose_id"],validate="many_to_one")
        assert len(join)==len(g)
        raw.append(join)
        info.append(dict(route=route,available_rows=len(g),
                         unique_poses=join.groupby(["case","pose_id"]).ngroups))
    d=pd.concat(raw,ignore_index=True)
    d["correct_5deg"]=d.correct_5deg.astype(int)
    return d,info,float(parity)

def fit_by_binomial(train,cols):
    a=train.copy()
    if not cols:return None,float(np.average(a.n_good,weights=None)/a.n.sum())
    x=np.asarray(a[cols],float)
    xx=np.vstack([x,x])
    y=np.r_[np.ones(len(a),int),np.zeros(len(a),int)]
    w=np.r_[a.n_good.values,a.n_bad.values].astype(float)
    good=w>0
    if len(np.unique(y[good]))<2:return None,float(a.n_good.sum()/a.n.sum())
    model=make_pipeline(SimpleImputer(strategy="median",add_indicator=True),
                        StandardScaler(),
                        LogisticRegression(C=1,max_iter=1500,solver="lbfgs"))
    model.fit(xx[good],y[good],logisticregression__sample_weight=w[good])
    return model,None

def prepare_poses(data):
    col=["case","route","pose_id","station_group","range_m","P5_log_power","P5_s","s_abs","lp_ratio_log10","ratio_from_s_db",
       "P1_jsd","P2_peak_difference_ns","P3_early_asymmetry","P4_shape_L1","D1_mean_ns","D1_diff_ns"]
    a=data.groupby(["case","route","pose_id"],as_index=False).agg(
        **{c:(c,"first") for c in col if c not in ["case","route","pose_id"]},
        n=("correct_5deg","size"),n_good=("correct_5deg","sum"),
        heading_mean_err=("heading_error_deg","mean"),
        heading_median_err=("heading_error_deg","median"),
        heading_correct_fraction=("correct_5deg","mean"))
    a["n_bad"]=a.n-a.n_good
    return a

def leave_route_out(poses,outdir):
    rows=[];pred=[]
    for route in FROZEN["folds"]:
        tr=poses[poses.route!=route];te=poses[poses.route==route].copy()
        for label,cols in FROZEN["models"].items():
            model,constant=fit_by_binomial(tr,cols)
            q=(np.full(len(te),constant) if model is None else model.predict_proba(te[cols])[:,1])
            q=np.clip(q,1e-8,1-1e-8)
            # Per-pose weighted Brier = exact average over repeated sensor priors with identical RF features.
            loss=(te.n_good*(1-q)**2+te.n_bad*q**2)/te.n
            brier=float(np.average(loss,weights=te.n))
            y=np.r_[np.ones(len(te),int),np.zeros(len(te),int)]
            wt=np.r_[te.n_good.values,te.n_bad.values].astype(float)
            pp=np.r_[q,q]
            active=wt>0
            auc=float(roc_auc_score(y[active],pp[active],sample_weight=wt[active])) if len(np.unique(y[active]))==2 else float("nan")
            rows.append(dict(route=route,model=label,brier=brier,auroc=auc,n_pose=len(te),
                             n_available=int(te.n.sum()),prevalence=float(te.n_good.sum()/te.n.sum())))
            tmp=te[["case","route","pose_id","station_group","n","n_good","n_bad","heading_mean_err"]].copy()
            tmp["model"]=label;tmp["q_good"]=q;tmp["brier_loss_per_pose"]=loss
            pred.append(tmp)
        print("FOLD",route,[(x["model"],round(x["brier"],4)) for x in rows if x["route"]==route],flush=True)
    pd.DataFrame(rows).to_csv(outdir/"RATIO_MODELS_HELDOUT.csv",index=False)
    pd.concat(pred,ignore_index=True).to_csv(outdir/"RATIO_MODELS_PREDICTIONS.csv.gz",index=False)
    return pd.DataFrame(rows),pd.concat(pred,ignore_index=True)

def correlation(poses,outdir):
    features=["range_m","P5_log_power","P5_s","s_abs","lp_ratio_log10","P1_jsd","P2_peak_difference_ns",
              "P3_early_asymmetry","P4_shape_L1","D1_mean_ns","D1_diff_ns"]
    rows=[]
    for route in ["R2","R4","R5","ALL"]:
        a=poses if route=="ALL" else poses[poses.route==route]
        for f in features:
            for tgt in ["heading_mean_err","heading_correct_fraction"]:
                pear,rho,n=corr(a[f],a[tgt]);rows.append(dict(route=route,feature=f,target=tgt,
                  pearson=pear,spearman=rho,n_unique_case_pose=n,
                  no_truth_in_predictor=True))
    df=pd.DataFrame(rows);df.to_csv(outdir/"RATIO_CORRELATIONS_POSE_MEANS.csv",index=False)
    return df

def bootstrap(pred,outdir):
    base=pred.pivot(index=["case","route","pose_id","station_group"],columns="model",
                     values="brier_loss_per_pose").reset_index()
    if isinstance(base.columns,pd.MultiIndex):
        base.columns=[a if not b else b for a,b in base.columns]
    # Add per-pose counts; every repeated seed is already folded into brier losses.
    N=pred.drop_duplicates(["case","pose_id"]).set_index(["case","pose_id"]).n
    base["n"]=[N.loc[(c,p)] for c,p in zip(base["case"],base["pose_id"])]
    pairs=[("range+power+ratio","range+power"),("range+power+ratio+CIR","range+power+ratio")]
    rng=np.random.default_rng(FROZEN["seed"])
    rec=[]
    for route in FROZEN["folds"]:
        a=base[base.route==route]
        for high,lo in pairs:
            q=a[high]-a[lo]
            group=a.assign(score=q*a.n).groupby("station_group").agg(num=("score","sum"),count=("n","sum"))
            idx=rng.integers(0,len(group),(1000,len(group)))
            bs=group.num.to_numpy()[idx].sum(axis=1)/group["count"].to_numpy()[idx].sum(axis=1)
            rec.append(dict(route=route,contrast=high+" minus "+lo,n_station_groups=len(group),
                     n_poses=len(a),observed_weighted_brier_difference=float(np.average(q,weights=a.n)),
                     ci_low=float(np.quantile(bs,0.025)),ci_high=float(np.quantile(bs,0.975))))
    pd.DataFrame(rec).to_csv(outdir/"RATIO_ADDED_VALUE_STATION_BOOTSTRAP.csv",index=False)
    return rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True)
    o=ap.parse_args().out;o.mkdir(parents=True,exist_ok=True);t0=time.time()
    (o/"EXPERIMENT_SETTINGS.json").write_text(json.dumps(FROZEN,indent=2))
    data,info,parity=merged_data()
    poses=prepare_poses(data)
    correls=correlation(poses,o)
    models,pred=leave_route_out(poses,o)
    ci=bootstrap(pred,o)
    # Naive polarization ratios are deterministic transforms of s and cannot establish Fresnel depolarization.
    selected=correls[(correls.target=="heading_mean_err")&correls.feature.isin(["P5_s","s_abs","lp_ratio_log10","P5_log_power","P1_jsd","D1_mean_ns"])]
    summary={
        "execution":"COMPLETED_EXPLORATORY_SAME_CORRIDOR",
        "question":"How strongly do dual LP power ratio and CIR predictors relate to v2 prior-assisted RF heading accuracy?",
        "input":info,"available_rows_total":int(len(data)),
        "n_distinct_case_poses":int(len(poses)),
        "power_ratio_parity_max_abs_s":parity,
        "correlations_selected":json.loads(selected.to_json(orient="records")),
        "cv_metrics":json.loads(models.to_json(orient="records")),
        "brier_contrasts":ci,
        "limit":["Different routes R2,R4,R5 in same scene; no cross-geometry evidence.",
                 "Train/test per pose by route; RF reused across 150 prior seeds.",
                 "Available branch-selected samples only; no-match omitted and must be reported.",
                 "Operational heading error labels from v2 RF-OFF prior, not filter posterior.",
                 "Magnitude-CIR hardware availability unverified.",
                 "P1/P2 ratio log and s are redundant reparameterizations, not independent polarization evidence.",
                 "No reliable identification of Fresnel-induced depolarization without orientation baseline; two LP powers lack relative phase.",
                 "No probe+CIR joint trained posterior; this experiment only tests passive ratio association."
                ],
        "seconds":time.time()-t0}
    (o/"SUMMARY.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False,allow_nan=False))
    with (o/"RESULTS_KO.md").open("w",encoding="utf-8") as f:
        f.write("# 이중 LP 포트 전력비와 RF heading 오류 탐색 분석\n\n")
        f.write("이 결과는 **RF 업데이트 전 sensor-v2 prior**를 이용해 LoS LUT 역해를 선택한 기존 데이터를 재사용했습니다. 전체 복도 RF-noise-free 조건, 7케이스, 세 route입니다. F01/F02 및 cov 부족 문제를 해결한 실험이 아닙니다.\n\n")
        f.write("## 유일한 case/pose 단위 상관계수\n\n")
        f.write(selected.to_markdown(index=False))
        f.write("\n\n## held-out route 확률분류 성능\n\n")
        f.write(models.to_markdown(index=False))
        f.write("\n\n## 전력비/CIR 특징 추가가치 (station bootstrap)\n\n")
        f.write(pd.DataFrame(ci).to_markdown(index=False))
        f.write("\n\n## 물리적 해석 제한\n\n- s=(P1-P2)/(P1+P2)와 XPD-like ratio 10log10(P1/P2)는 같은 정보의 단조 변환입니다. \n- 부호 있는 s, |s|, power sum은 서로 의미가 다르고 2차원 편파 orientation에 민감합니다. s가 크거나 작다고 탈편파가 확인되는 것은 아닙니다.\n- Fresnel TE/TM 차이, 포트패턴 및 다중경로 합성은 수신 LP 전력비를 바꾸지만 이것은 반드시 Stokes DOP 저하와 같지 않습니다.\n- heading 오차와의 상관 및 calibration은 다른 반사 환경에서 다시 검증해야 합니다.\n")
    print("RATIO_ANALYSIS_RESULT",json.dumps({"n_pose":len(poses),"n_available":len(data),"ratio_parity":parity,"ci":ci},allow_nan=False),flush=True)
if __name__=="__main__":main()
