#!/usr/bin/env python3
"""Exploratory nonlinear-LUT multi-angle / multipath-site mixture inference.

Not a calibrated physical receiver or a new sensor-v2 Monte Carlo.
Latent contamination is inferred without any oracle true yaw or oracle e_s.
The existing sensor-v2 PROBES file has heading P only, so position is fixed
at the RF-disabled odometry pose; this is an explicit limitation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logsumexp
from sklearn.metrics import roc_auc_score, brier_score_loss

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
CASE_ROOT = ROOT / "results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
EXPECTED_LUT_SHA = "711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079"
sys.path.insert(0,str(RUN/"source/src"))
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa:E402

CONFIG = {
    "site_bad_prior":0.35,
    "point_bad_prob_clean_site":0.06,
    "point_bad_prob_bad_site":0.55,
    "s_good_std":0.06,
    "s_bad_std":0.30,
    "shared_s_std_clean":0.01,
    "shared_s_std_bad":0.15,
    "shared_heading_std_deg_clean":1.0,
    "shared_heading_std_deg_bad":15.0,
    "white_baseline_s_std":0.09,
    "grid_min_deg":-90.0, "grid_max_deg":90.0,"grid_step_deg":0.5,
    "site_bad_eval_abs_es":0.1,
    "point_bad_eval_abs_es":0.1,
    "bootstrap_seed":20261010,"bootstrap_replicates":1000
}

def wrap_deg(x):
    return (x+180)%360-180

def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def finite_num(x):
    try:
        q=float(x);return np.isfinite(q)
    except Exception:return False

def prepare():
    base=RUN/"LUT"
    lut_path=base/"hs_lut_2deg.npy"
    assert lut_path.exists()
    sha=digest(lut_path)
    assert sha==EXPECTED_LUT_SHA, f"LUT_SHA_MISMATCH expected {EXPECTED_LUT_SHA} actual {sha}"
    meta=json.loads((base/"hs_lut_meta.json").read_text())["meta"]
    phi=meta["phi_deg"];theta=meta["theta_deg"]
    model=HsLut(dict(theta_deg=theta,phi_deg=np.arange(phi[0],phi[1]+.01,phi[2]),s=np.load(lut_path)))
    cases={c["case"]:c for c in json.loads((CASE_ROOT/"CASES.json").read_text())}
    feat=pd.read_csv(RUN/"OUTPUT/01_FEATURES.csv")
    labels=pd.read_csv(RUN/"OUTPUT/02_LABELS_EVAL_ONLY.csv")
    assert feat.duplicated(["case","pose_id"]).sum()==0
    assert labels.duplicated(["case","pose_id"]).sum()==0
    f=feat.set_index(["case","pose_id"])
    t=labels.set_index(["case","pose_id"])
    pr=pd.read_csv(RUN/"PROBES/07_PROBE_STATIONS.csv.gz",low_memory=False)
    eligible=pr[(pr["n_angles"]==3)&(pr["status"]=="OFFLINE_DIAGONAL_SCORE_ONLY")].copy()
    assert len(eligible)*3==int((pr.n_angles>0).sum()),"Wrong probe triple grouping"
    assert len(eligible)==5100, f"EXPECTED 5100 usable priors; got {len(eligible)}"
    assert eligible.duplicated(["case","station","drift","seed"]).sum()==0
    return model,cases,f,t,eligible,dict(n_raw=len(pr),n_evaluable=len(eligible),fixed_lut_sha=sha,
                                      source_readme=str(RUN/"FINAL_REPORT_KO.md"))

def posterior_from_logprob(grid_rad,logs):
    lp=logs-logsumexp(logs)
    w=np.exp(lp)
    m=float(w@grid_rad)
    v=float(max(w@(grid_rad*grid_rad)-m*m,0))
    edge=float(w[(grid_rad<-math.radians(85)) | (grid_rad>math.radians(85))].sum())
    return m,math.sqrt(v),edge,w

def baseline(grid_rad,logprior,residual_grid,s_std):
    logs=logprior-0.5*np.sum((residual_grid/s_std)**2,axis=1)
    return posterior_from_logprob(grid_rad,logs)

def latent_mixture(grid_rad,logprior,resid,H_slope):
    """Exact nonlinear LUT grid; integrate correlated s errors and point/site modes."""
    n=resid.shape[1]
    all_modes=[]
    for site_bad in (False,True):
        prior_site=CONFIG["site_bad_prior"] if site_bad else 1-CONFIG["site_bad_prior"]
        pb=(CONFIG["point_bad_prob_bad_site"] if site_bad else CONFIG["point_bad_prob_clean_site"])
        ts=CONFIG["shared_s_std_bad"] if site_bad else CONFIG["shared_s_std_clean"]
        ty=math.radians(CONFIG["shared_heading_std_deg_bad"] if site_bad else CONFIG["shared_heading_std_deg_clean"])
        for mask in range(1<<n):
            flags=np.array([(mask>>i)&1 for i in range(n)],int)
            point_std=np.where(flags==1,CONFIG["s_bad_std"],CONFIG["s_good_std"])
            cov=np.diag(point_std**2)+ts**2*np.ones((n,n))+ty**2*np.outer(H_slope,H_slope)
            sign,logdet=np.linalg.slogdet(cov)
            assert sign>0
            sol=np.linalg.solve(cov,resid.T).T
            sq=np.sum(resid*sol,axis=1)
            logmodel=math.log(prior_site)+int(flags.sum())*math.log(pb)+(n-int(flags.sum()))*math.log(1-pb)
            loglik=logmodel-0.5*(sq+logdet+n*math.log(2*math.pi))
            all_modes.append(dict(site_bad=int(site_bad),flags=flags,
                                  logs=loglik+logprior))
    stack=np.stack([m["logs"] for m in all_modes],axis=0)
    norm=logsumexp(stack)
    joint=np.exp(stack-norm)
    wg=joint.sum(axis=0)
    mean=float(np.dot(wg,grid_rad))
    sd=float(np.sqrt(max(np.dot(wg,grid_rad**2)-mean**2,0)))
    site=float(sum(joint[i].sum() for i,m in enumerate(all_modes) if m["site_bad"]))
    point=np.array([sum(joint[j].sum()*m["flags"][i] for j,m in enumerate(all_modes))
                    for i in range(n)],float)
    edge=float(wg[(grid_rad<-math.radians(85)) | (grid_rad>math.radians(85))].sum())
    return mean,sd,edge,site,point

def calc_one(raw,model,cases,features,labels,grid_rad):
    case=str(raw["case"]);pose_ids=list(map(int,json.loads(raw["pose_ids"])))
    offsets=np.radians(np.array(json.loads(raw["scheduled_yaw_offsets_deg"]),float))
    x0=np.array(json.loads(raw["pre_rf_state"]),float)
    pv=float(raw["prior_heading_variance"])
    if len(pose_ids)!=3 or not np.isfinite(x0).all() or not (np.isfinite(pv) and pv>1e-12):
        raise ValueError("Missing prior or invalid station input")
    z=np.array([float(features.loc[(case,pid),"s"]) for pid in pose_ids])
    true_es=np.array([float(labels.loc[(case,pid),"e_s"]) for pid in pose_ids])
    true_MP=np.array([float(labels.loc[(case,pid),"e_MP"]) for pid in pose_ids])
    true_yaw=float(labels.loc[(case,pose_ids[0]),"true_yaw_deg"])
    c=cases[case]
    assert abs(float(raw["prior_heading_variance"])-pv)<1e-12
    prior_rad=float(x0[2]);anchor=c["anchor_xyz"];mount=float(c["mount_deg"]);robz=float(c["robot_z"])
    logprior=-0.5*(grid_rad*grid_rad/pv)
    grouped=[]
    for n in (1,2,3):
        dr=offsets[:n]
        # Nonlinear LUT model at the fixed odometry position and each candidate yaw.
        heading_grid=prior_rad+grid_rad[:,None]+dr[None,:]
        h=s_model(model,anchor,robz,float(x0[0]),float(x0[1]),heading_grid,mount,with_jac=False)
        residual=z[:n][None,:]-h
        h0,J=s_model(model,anchor,robz,float(x0[0]),float(x0[1]),prior_rad+dr,mount,with_jac=True)
        slope=np.array(J[:,2],float)
        g_m,g_std,g_edge,_=baseline(grid_rad,logprior,residual,CONFIG["white_baseline_s_std"])
        m_m,m_std,m_edge,q_site,point_bad=latent_mixture(grid_rad,logprior,residual,slope)
        for name,mean,std,edge in (("GAUSS",g_m,g_std,g_edge),("MIX",m_m,m_std,m_edge)):
            est=wrap_deg(math.degrees(prior_rad+mean))
            error=abs(wrap_deg(est-true_yaw))
            output=dict(case=case,route=str(raw["route"]),station=int(raw["station"]),
                  station_x=float(raw["pre_rf_state"] is not None and labels.loc[(case,pose_ids[0]),"true_x"]),
                  station_y=float(labels.loc[(case,pose_ids[0]),"true_y"]),
                  drift=int(raw["drift"]),seed=int(raw["seed"]),n_angles=n,method=name,
                  eval_true_heading_deg=true_yaw,
                  prior_heading_deg=wrap_deg(math.degrees(prior_rad)),
                  prior_heading_sigma_deg=math.degrees(math.sqrt(pv)),
                  heading_est_deg=est,heading_std_deg=math.degrees(std),
                  error_deg=error,
                  prior_error_deg=abs(wrap_deg(math.degrees(prior_rad)-true_yaw)),
                  heading95_covered=int(error<=1.95996398454*math.degrees(std)),
                  edge_probability=edge,
                  q_site_bad=q_site if name=="MIX" else np.nan,
                  q_point_bad_0=point_bad[0] if name=="MIX" else np.nan,
                  q_point_bad_1=point_bad[1] if name=="MIX" and n>=2 else np.nan,
                  q_point_bad_2=point_bad[2] if name=="MIX" and n>=3 else np.nan,
                  true_site_bad3=int(np.any(abs(true_es)>CONFIG["site_bad_eval_abs_es"])),
                  true_bad0=int(abs(true_es[0])>CONFIG["point_bad_eval_abs_es"]),
                  true_bad1=int(abs(true_es[1])>CONFIG["point_bad_eval_abs_es"]),
                  true_bad2=int(abs(true_es[2])>CONFIG["point_bad_eval_abs_es"]),
                  oracle_s_e0=float(true_es[0]),oracle_s_e1=float(true_es[1]),oracle_s_e2=float(true_es[2]),
                  mean_abs_oracle_mp3=float(np.mean(abs(true_MP))),
                  source="existing frozen v2 prior; true recorded yaw offsets (ideal rotation); nonlinear LUT")
            grouped.append(output)
    return grouped

def safe_auc(y,p):
    return float(roc_auc_score(y,p)) if len(set(y))>1 else np.nan

def aggregate(records):
    d=pd.DataFrame(records)
    out=[]
    for (method,n),g in d.groupby(["method","n_angles"],sort=True):
        error=g.error_deg.to_numpy(float)
        groupkey=(g.route+"_"+g.station_x.round(6).astype(str)+"_"+g.station_y.round(6).astype(str))
        row=dict(method=method,n_angles=int(n),n_records=len(g),n_station_case=g.groupby(["case","station"]).ngroups,
                 n_physical_sites=groupkey.nunique(),
                 heading_mae_deg=float(np.mean(error)),
                 heading_rmse_deg=float(np.sqrt(np.mean(error**2))),
                 heading_median_deg=float(np.median(error)),
                 heading_p90_deg=float(np.quantile(error,.9)),
                 heading_p95_deg=float(np.quantile(error,.95)),
                 heading95_coverage=float(g.heading95_covered.mean()),
                 mean_predicted_heading_sigma_deg=float(g.heading_std_deg.mean()),
                 mean_priormae_deg=float(g.prior_error_deg.mean()),
                 edge_probability_gt_001=float((g.edge_probability>0.01).mean()))
        if method=="MIX":
            row.update(site_bad_auc=safe_auc(g.true_site_bad3,g.q_site_bad),
                       site_bad_brier=float(brier_score_loss(g.true_site_bad3,g.q_site_bad)),
                       predicted_dirty_site_fraction=float((g.q_site_bad>=0.5).mean()),
                       actual_dirty_site_fraction=float(g.true_site_bad3.mean()),
                       highconf_clean_but_bad_fraction=float(((g.q_site_bad<0.2)&(g.true_site_bad3==1)).mean()))
            for i in range(n):
                q=g[f"q_point_bad_{i}"];y=g[f"true_bad{i}"]
                row[f"point{i}_bad_auc"]=safe_auc(y,q)
                row[f"point{i}_bad_brier"]=float(brier_score_loss(y,q))
        out.append(row)
    return d,pd.DataFrame(out)

def paired_bootstrap(d):
    rng=np.random.default_rng(CONFIG["bootstrap_seed"])
    a=d.pivot(index=["case","route","station","station_x","station_y","drift","seed"],
              columns=["method","n_angles"],
              values="error_deg")
    a.columns=[f"{x}{int(y)}" for x,y in a.columns]
    a=a.dropna().reset_index()
    contrast={"MIX3-GAUSS3":a["MIX3"]-a["GAUSS3"],
              "MIX3-MIX1":a["MIX3"]-a["MIX1"],
              "MIX3-PRIOR":a["MIX3"]-d[d.method=="MIX"].drop_duplicates(
                  ["case","station","drift","seed"]).set_index(
                  ["case","station","drift","seed"]).loc[
                    a.set_index(["case","station","drift","seed"]).index,"prior_error_deg"].values,
              "GAUSS3-GAUSS1":a["GAUSS3"]-a["GAUSS1"]}
    cluster=(a.route+"_"+a.station_x.round(6).astype(str)+"_"+a.station_y.round(6).astype(str))
    out=[]
    for label,v in contrast.items():
        per=pd.DataFrame(dict(cluster=cluster.to_numpy(),value=np.array(v,float))).groupby("cluster").agg(
            total=("value","sum"),n=("value","size"))
        idx=rng.integers(0,len(per),(CONFIG["bootstrap_replicates"],len(per)))
        den=per.n.to_numpy()[idx].sum(axis=1)
        means=per.total.to_numpy()[idx].sum(axis=1)/den
        out.append(dict(contrast=label,metric="difference of absolute heading error, deg",
                        n_paired=len(a),n_distinct_physical_sites=len(per),
                        mean_delta_deg=float(np.mean(v)),ci95_low=float(np.quantile(means,.025)),
                        ci95_high=float(np.quantile(means,.975)),
                        improvement_fraction=float(np.mean(np.asarray(v)<0))))
    return a,pd.DataFrame(out)

def analyze(outdir):
    started=time.time()
    outdir.mkdir(parents=True,exist_ok=True)
    model,cases,features,labels,rows,provenance=prepare()
    grid_rad=np.radians(np.arange(CONFIG["grid_min_deg"],CONFIG["grid_max_deg"]+1e-7,CONFIG["grid_step_deg"]))
    records=[]
    for i,(_,raw) in enumerate(rows.iterrows(),1):
        records.extend(calc_one(raw,model,cases,features,labels,grid_rad))
        if i%1000==0:print("PROGRESS",i,"/",len(rows),"seconds",round(time.time()-started),flush=True)
    df,sm=aggregate(records)
    paired,pci=paired_bootstrap(df)
    df.to_csv(outdir/"ALL_STATION_POSTERIORS.csv.gz",index=False)
    sm.to_csv(outdir/"MODEL_COMPARISON.csv",index=False)
    paired.to_csv(outdir/"PAIRED_ERRORS.csv.gz",index=False)
    pci.to_csv(outdir/"PAIRED_CLUSTER_BOOTSTRAP.csv",index=False)
    example=df[(df.method=="MIX")&(df.n_angles==3)].copy()
    example["contaminated_angle_count_eval_only"]=example[["true_bad0","true_bad1","true_bad2"]].sum(axis=1)
    examples=(example.groupby(["case","station"]).agg(
        n_seed=("seed","size"),p_site_bad_median=("q_site_bad","median"),
        heading_error_median_deg=("error_deg","median"),
        heading_sigma_median_deg=("heading_std_deg","median"),
        true_site_bad=("true_site_bad3","max"),
        point_bad_0_mean=("q_point_bad_0","mean"),
        point_bad_1_mean=("q_point_bad_1","mean"),
        point_bad_2_mean=("q_point_bad_2","mean"),
        true_bad_0=("true_bad0","max"),true_bad_1=("true_bad1","max"),
        true_bad_2=("true_bad2","max")).reset_index())
    examples.to_csv(outdir/"LOCATION_AND_POINT_CONFIDENCE.csv",index=False)
    summary=dict(status="EXECUTED_EXPLORATORY_ONLY",method="exact nonlinear LUT yaw-grid; uncalibrated 2-layer site/point mixture",
                 config=CONFIG,provenance=provenance,n_rows=len(df),n_stations=len(rows),n_usable_distinct_sites=int(example.assign(coord=example.route+"_"+example.station_x.round(6).astype(str)+"_"+example.station_y.round(6).astype(str)).coord.nunique()),
                 heading_truth_leakage=False,position_covariance_missing=True,real_rotation_noise_not_modeled=True,
                 F01_F02="OPEN",generalization="NOT_PROVEN",
                 tables={"models":json.loads(sm.to_json(orient="records")),"contrasts":json.loads(pci.to_json(orient="records"))},
                 elapsed_s=time.time()-started)
    (outdir/"EXECUTION_STATUS.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    with (outdir/"RESULTS_KO.md").open("w",encoding="utf-8") as f:
        f.write("# 2–3각 Joint heading + site/point 신뢰도 — 탐색적 실행\n\n")
        f.write("**분석 성공 ≠ 모델 검증 PASS**. 같은 복도, 제한된 16개 실제 위치, 34개 case별 위치 그룹, 실제 회전량을 truth에서 가져온 ideal-motion offline 조건입니다. RF-only v2 prior heading 분산만 공개되고 xy 공분산은 없습니다.\n\n")
        f.write("## 계산법\n\n각 yaw 측정이 양품 또는 오염되었다는 잠재 상태와 같은 위치 전체가 multipath 위험인지 나타내는 잠재 상태를 공동 추정했습니다. 모든 점을 사용했으며 최소 잔차점만 선택하지 않았습니다. 비선형 고정 LUT와 v2 RF-off heading prior를 결합했습니다. 결과의 q_site_bad/q_point_bad는 **사전 고정 모형의 명목상 확률**로, 독립 보정되지 않았습니다.\n\n")
        f.write("## Heading 오차 및 불확실성\n\n")
        f.write(sm[["method","n_angles","n_records","n_physical_sites","heading_mae_deg","heading_rmse_deg","heading_p95_deg","heading95_coverage","mean_predicted_heading_sigma_deg"]].to_markdown(index=False))
        f.write("\n\n## site multipath 분류\n\n")
        f.write(sm[sm.method=="MIX"][["n_angles","site_bad_auc","site_bad_brier","predicted_dirty_site_fraction","actual_dirty_site_fraction"]].to_markdown(index=False))
        f.write("\n\n## paired physical site bootstrap\n\n")
        f.write(pci.to_markdown(index=False))
        f.write("\n\n## 과학적 한계\n\n- RF 채널은 noise-free 저장본이고 관측점마다 유효 측정 오차에 강한 시간·공간 상관이 있습니다. 이 상관구조는 임의 사전 파라미터로 근사합니다.\n- 평가 label인 e_s/정답 heading은 모델 입력에 사용하지 않았습니다. 그러나 프로브 yaw offset은 기존 true trajectory의 기록값을 사용했으므로 실제 actuator 성능 평가는 아닙니다.\n- 본 결과는 필터의 full posterior/NEES가 아니라 RF-off v2 prior 조건부 heading correction의 offline 평가입니다.\n- x,y covariance가 공개 PROBES 파일에 없어서 position-heading uncertainty를 완전하게 전파하지 못했습니다.\n")
    print("EXECUTED_SUMMARY",json.dumps({"seconds":round(time.time()-started,1),"models":sm[["method","n_angles","heading_rmse_deg","heading95_coverage","site_bad_auc","site_bad_brier"]].replace({np.nan:None}).to_dict("records"),"contrasts":pci.to_dict("records")},ensure_ascii=False),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    analyze(args.out)
