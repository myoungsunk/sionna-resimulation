#!/usr/bin/env python3
"""Original 7-case, matched-seed 5Hz Sensor-v2 range-only consistency ablation.

IMPORTANT: training labels use true range from OTHER ROUTES only. Held-out
route/pose truth never enters the estimator. Existing noise-free RF channels
are replayed; no new Sionna run. Empirical temporal inflation is an
exploratory approximation, NOT an exact colored-noise Kalman filter.
"""
from __future__ import annotations
import argparse, json, math, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
BLOCK=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
TDIR=ROOT/"results/DRIVE_SIM_20261007/S1/routes"
import sys
sys.path.insert(0,str(RUN/"source/src"))
from qclean_uwb.drivesim import sensor_v2 as V, filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
from scipy.stats import chi2

CASES=("R2_aA_m0","R2_aB_m0","R2_aA_m45","R4_aA_m0",
       "R4_aB_m0","R5_aA_m0","R5_aB_m0")
ARMS=("A_ODOM","B_RANGE_FIXED","C_BIAS_BIN","D_BIAS_VAR_BIN",
      "E_BIAS_VAR_TIME","F_VAR_TIME_NO_BIAS")
LEVELS=range(3)
CUTS=(0,5,10,float("inf"))
PROGRESS_START=30.
DT=.2
SEED=20261011

def bins(a):
    return np.where(a<5,0,np.where(a<10,1,2))
def finite_corr(a,b):
    a=np.asarray(a,float);b=np.asarray(b,float)
    mask=np.isfinite(a)&np.isfinite(b)
    if mask.sum()<10 or np.std(a[mask])<1e-12 or np.std(b[mask])<1e-12:
        return 0.
    return float(np.corrcoef(a[mask],b[mask])[0,1])

def context():
    rootmeta=json.loads((RUN/"LUT/hs_lut_meta.json").read_text())
    offset=float(rootmeta["range_bias"]["mean_m"])
    label=pd.read_csv(RUN/"OUTPUT/02_LABELS_EVAL_ONLY.csv")
    features=pd.read_csv(RUN/"OUTPUT/01_FEATURES.csv",
                         usecols=["case","pose_id","range_m","detected"])
    assert not features.duplicated(["case","pose_id"]).any()
    label=label.merge(features,on=["case","pose_id"],validate="one_to_one")
    label["e_corrected"]=label.range_m-label.true_distance_m-offset
    assert np.max(abs(label["e_corrected"]-(label["e_range"]-offset)))<1e-9
    cases={a["case"]:a for a in json.loads((BLOCK/"CASES.json").read_text())}
    traces={}
    for route in ("R2","R4","R5"):
        full=pd.read_csv(TDIR/f"timeline_{route}_T10.csv")
        no=pd.read_csv(TDIR/f"timeline_{route}_Tnone.csv")
        norm=full[full.phase!="probe"].copy()
        assert len(norm)==len(no)
        assert np.array_equal(norm.pose_id.to_numpy(),no.pose_id.to_numpy())
        assert np.max(abs(norm.x.to_numpy()-no.x.to_numpy()))<1e-12
        assert np.max(abs(norm.y.to_numpy()-no.y.to_numpy()))<1e-12
        t=full.t_s.to_numpy(float)
        pose=full[["x","y","yaw_body_deg"]].to_numpy(float)
        pose[:,2]=np.radians(pose[:,2])
        ds,dtheta=V.motion_increments(t,pose,convention="legacy-euler",tolerance=1e-8)
        traces[route]=dict(full=full,no=no,pose=pose,t=t,ds=ds,dth=dtheta,
                           main_indices=np.flatnonzero(full.phase!="probe"))
    return offset,label,cases,traces

def train_heldout_models(label,traces,offset,cfg):
    r0=cfg.range_sigma**2+cfg.range_extra_sigma**2+cfg.range_quant_var
    results={}
    # Remove R2-A m45 train duplication of physical range geometry.
    for heldout in ["R2","R4","R5"]:
        tracks=[]
        for case in CASES:
            route=case.split("_")[0]
            if route==heldout or case.endswith("_m45"):continue
            ids=traces[route]["no"].pose_id
            sub=label[label.case==case].set_index("pose_id").loc[ids].reset_index()
            assert len(sub)==len(ids)
            tracks.append(sub)
        all_train=pd.concat(tracks,ignore_index=True)
        bybin=[]
        for j in range(3):
            g=all_train[bins(all_train.true_distance_m.to_numpy())==j]
            assert len(g)>100,(heldout,j,len(g))
            x=g.e_corrected.to_numpy(float)
            mu=float(x.mean())
            centered_var=float(x.var(ddof=0))
            bybin.append(dict(bin=j,n=int(len(x)),bias_m=mu,
                              centered_variance_m2=centered_var,
                              effective_R_m2=max(r0,centered_var),
                              raw_R_m2=r0))
        # Pool contiguous, same-distance-bin adjacent RF errors for training.
        pairs=[]
        for case in CASES:
            route=case.split("_")[0]
            if route==heldout or case.endswith("_m45"):continue
            ids=traces[route]["no"].pose_id
            sub=label[label.case==case].set_index("pose_id").loc[ids].reset_index()
            n=bins(sub.true_distance_m.to_numpy())
            y=sub.e_corrected.to_numpy(float) - np.array([bybin[j]["bias_m"] for j in n])
            ok=(n[:-1]==n[1:])
            pairs.extend(zip(y[:-1][ok],y[1:][ok]))
        xy=np.asarray(pairs,float)
        rho=finite_corr(xy[:,0],xy[:,1])
        # Approximate information-redundancy inflation for AR(1) model,
        # deliberately capped. NOT EXACT serial covariance filtering.
        tau=float(np.clip((1+max(rho,0))/(1-max(rho,0)+1e-12),1,12))
        results[heldout]=dict(training_routes=[r for r in ["R2","R4","R5"] if r!=heldout],
                              n_train_pose=int(len(all_train)),bins=bybin,
                              ar1_training_residual_corr=rho,
                              tau_integrated_AR1_approx=tau,
                              near_anchor_eval_only=False)
    return results

def cfg(c,offset):
    return FilterConfig(model_version="sensor-v2",kind="ekf",
           s_mode="direct",use_range=True,use_s=False,
           anchor_xyz=tuple(c["anchor_xyz"]),mount_deg=float(c["mount_deg"]),
           robot_z=float(c["robot_z"]),bias_rw_std=0.,
           known_wheelbase_error=0.,range_offset=float(offset))

def select_params(model,d):
    j=int(bins(np.array([d]))[0])
    return model["bins"][j]

def run_case(case,level,seed,arm,context_,models,representative=False):
    off,label,cases,traces=context_
    route=case.split("_")[0]
    rt=traces[route]; c=cases[case];conf=cfg(c,off)
    x0=np.r_[rt["pose"][0].copy(),0.,0.,0.]
    x0[:3]+=V.rng(seed,"initial").normal(size=3)*np.asarray(conf.p0_std[:3])
    sensor,_=V.generate(rt["t"],rt["ds"],rt["dth"],
                        V.SensorV2Config(level=level,condition="all"),seed)
    f=F.SensorV2Filter(conf,None,x0)
    observations=label[label.case==case].set_index("pose_id")
    fit=models[route]
    resid=[];details=[];seen=0
    counts=dict(range_updates=0,range_rejects=0)
    eval_ids=rt["no"].pose_id.to_numpy()
    normal_idx=rt["main_indices"]
    assert len(eval_ids)==len(normal_idx)
    for t_idx,(k,poseid) in enumerate(zip(normal_idx,eval_ids)):
        if int(k):
            f.step(float(sensor["ds_odom"][k]),float(sensor["dtheta_gyro"][k]),
                   float(sensor["dtheta_odom"][k]),DT)
        row=observations.loc[int(poseid)]
        if arm!="A_ODOM" and bool(row["detected"]) and np.isfinite(row["range_m"]):
            if arm=="B_RANGE_FIXED":
                update=f.range_record(float(row["range_m"]))
                # uses constant offset and legacy R.
                z_r=float(row["range_m"])
                d_pred=np.linalg.norm([f.comps[0].x[0]-c["anchor_xyz"][0],
                                      f.comps[0].x[1]-c["anchor_xyz"][1],
                                      c["anchor_xyz"][2]-c["robot_z"]])
                applied_mu=0.
                used_r=conf.range_sigma**2+conf.range_extra_sigma**2+conf.range_quant_var
            else:
                x=f.comps[0].x
                d_pred=math.sqrt((x[0]-c["anchor_xyz"][0])**2+
                                 (x[1]-c["anchor_xyz"][1])**2+
                                 (c["anchor_xyz"][2]-c["robot_z"])**2)
                params=select_params(fit,d_pred)
                H=np.zeros(6,float)
                H[:2]=(x[:2]-np.asarray(c["anchor_xyz"][:2]))/d_pred
                applied_mu=params["bias_m"] if arm not in ("F_VAR_TIME_NO_BIAS",) else 0.
                if arm=="C_BIAS_BIN":
                    R=params["raw_R_m2"]
                elif arm=="D_BIAS_VAR_BIN":
                    R=params["effective_R_m2"]
                else:
                    R=params["effective_R_m2"]*fit["tau_integrated_AR1_approx"]
                used_r=float(R)
                z_r=float(row["range_m"])
                update=f.scalar(z_r,float(d_pred+off+applied_mu),H,float(R),"r")
            if update[3]=="applied":counts["range_updates"]+=1
            if update[3]=="rejected":counts["range_rejects"]+=1
        else: d_pred=np.nan;applied_mu=np.nan;used_r=np.nan
        if float(rt["no"].t_s.iloc[t_idx])<PROGRESS_START:
            continue
        est,P=f.mean_cov()
        tru=rt["pose"][k]
        e=tru-est[:3]
        e[2]=V.wrap(e[2])
        P3=P[:3,:3]
        nees=float(e@np.linalg.solve(P3,e))
        esxy=np.linalg.eigvalsh(P3[:2,:2])
        var_psi=float(P3[2,2])
        Pcond=P3[:2,:2]-np.outer(P3[:2,2],P3[2,:2])/max(var_psi,1e-15)
        eig,u=np.linalg.eigh(Pcond)
        minvec=u[:,0]
        ax=np.asarray(c["anchor_xyz"][:2],float)-est[:2]
        radial=ax/max(np.linalg.norm(ax),1e-12)
        e_cond=e[:2]-P3[:2,2]*e[2]/max(var_psi,1e-15)
        resid.append([e[0],e[1],e[2],nees,float(var_psi),
                      math.sqrt(max(float(eig[0]),0)),
                      float(abs(minvec@radial)),float(abs(e_cond@minvec)/math.sqrt(max(eig[0],1e-15))),
                      float(used_r),float(applied_mu)])
        if representative and t_idx%10==0:
            details.append(dict(case=case,level=level,seed=seed,arm=arm,
                progress_s=float(rt["no"].t_s.iloc[t_idx]),
                x_est=float(est[0]),y_est=float(est[1]),yaw_est_rad=float(est[2]),
                x_true=float(tru[0]),y_true=float(tru[1]),yaw_true_rad=float(tru[2]),
                range_R_effective_m2=float(used_r),estimated_range_bias_m=float(applied_mu),
                minimum_xy_cond_std_m=float(math.sqrt(max(eig[0],0))),
                radial_cos_alignment=float(abs(minvec@radial)),
                minaxis_abs_z=float(abs(e_cond@minvec)/math.sqrt(max(eig[0],1e-15))),
                nees_pose=float(nees),P6=json.dumps(P.tolist())))
    a=np.asarray(resid,dtype=float)
    expected={"R2":829,"R4":592,"R5":1265}[route]
    assert len(a)==expected,(route,len(a),expected)
    h=np.degrees(a[:,2]);pos=np.hypot(a[:,0],a[:,1])
    return dict(case=case,route=route,level=level,seed=seed,arm=arm,
            n_eval=len(a),heading_rmse_deg=float(np.sqrt(np.mean(h**2))),
            position_rmse_m=float(np.sqrt(np.mean(pos**2))),
            pose_nees_mean=float(np.mean(a[:,3])),
            pose_nees_median=float(np.median(a[:,3])),
            pose_nees_p95=float(np.quantile(a[:,3],.95)),
            pose95_coverage=float(np.mean(a[:,3]<=chi2.ppf(.95,3))),
            heading95_coverage=float(np.mean(abs(h)<=np.degrees(1.96*np.sqrt(a[:,4])))),
            min_xy_cond_std_m_median=float(np.median(a[:,5])),
            min_xy_cond_radial_alignment_median=float(np.median(a[:,6])),
            min_xy_cond_abs_z_p90=float(np.quantile(a[:,7],.9)),
            mean_range_R_eff_m2=float(np.nanmean(a[:,8])) if arm!="A_ODOM" else None,
            mean_range_bias_corrector_m=float(np.nanmean(a[:,9])) if arm!="A_ODOM" else None,
            **counts),details

def execute():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--seeds",type=int,default=4)
    ap.add_argument("--smoke",action="store_true")
    args=ap.parse_args()
    o=args.out;o.mkdir(parents=True,exist_ok=True)
    base=context();offset,label,cases,traces=base
    model=train_heldout_models(label,traces,offset,cfg(cases[CASES[0]],offset))
    (o/"HELDOUT_RANGE_MODELS.json").write_text(json.dumps(model,indent=2,allow_nan=False))
    jobs=[(CASES[0],0,0)] if args.smoke else [
       (case,lvl,seed) for case in CASES for lvl in LEVELS for seed in range(args.seeds)]
    outputs=[];snap=[]
    for i,(case,level,seed) in enumerate(jobs,1):
        for arm in ARMS:
            summary,details=run_case(case,level,seed,arm,base,model,
                                     representative=(level==0 and seed==0))
            outputs.append(summary);snap+=details
        if i%7==0 or args.smoke:print("PROGRESS",i,len(jobs),flush=True)
    df=pd.DataFrame(outputs)
    assert len(df)==len(jobs)*len(ARMS)
    df.to_csv(o/"PAIRED_RANGE_ONLY_PER_RUN.csv",index=False)
    pd.DataFrame(snap).to_csv(o/"REPRESENTATIVE_RANGE_FULL_P6.csv.gz",index=False)
    grouped=df.groupby("arm").agg(
      n_runs=("seed","size"),heading_rmse_mean_deg=("heading_rmse_deg","mean"),
      pos_rmse_mean_m=("position_rmse_m","mean"),
      pose_nees_mean=("pose_nees_mean","mean"),
      pose_nees_run_median=("pose_nees_median","median"),
      pose95_coverage=("pose95_coverage","mean"),
      min_cond_xy_std_m=("min_xy_cond_std_m_median","median"),
      min_cond_radial_alignment=("min_xy_cond_radial_alignment_median","median"),
      range_updates=("range_updates","mean"),range_rejects=("range_rejects","mean"))
    grouped.to_csv(o/"RANGE_ONLY_ARM_SUMMARY.csv")
    df.groupby(["case","arm"])[["heading_rmse_deg","position_rmse_m",
        "pose_nees_mean","pose95_coverage","range_updates"]].mean().to_csv(o/"RANGE_ONLY_CASE_ARM.csv")
    paired=df.pivot(index=["case","level","seed"],columns="arm",values=[
                    "heading_rmse_deg","position_rmse_m","pose_nees_mean","pose95_coverage"])
    rec=[]
    for arm in ARMS:
        if arm=="B_RANGE_FIXED":continue
        for m in ["heading_rmse_deg","position_rmse_m","pose_nees_mean","pose95_coverage"]:
            d=paired[(m,arm)]-paired[(m,"B_RANGE_FIXED")]
            rec.append(dict(arm=arm,metric=m,n=len(d),mean_difference=float(d.mean()),
                            share_reduced=float(np.mean(d<0))))
    pd.DataFrame(rec).to_csv(o/"PAIRED_VS_FIXED_RANGE.csv",index=False)
    info=dict(status="SMOKE_DONE" if args.smoke else "EXPLORATORY_HELDOUT_RANGE_RECALIBRATION_EXECUTED",
       source_frozen="sensor-v2 16d22fc / same previous T10 bank and H observations",
       source_RF_H="EXISTING_ONLY",outcome="range-only, same route progress",
       training="leave-one-ROUTE-out bias/variance and lag1 temporal correlation",
       n_runs=len(df),seed_count=args.seeds,case_count=len(CASES),
       baseline_original_R_r=cfg(cases[CASES[0]],offset).range_sigma**2+
         cfg(cases[CASES[0]],offset).range_extra_sigma**2+
         cfg(cases[CASES[0]],offset).range_quant_var,
       fixed_range_offset_m=offset,
       estimability=["binned mean bias and variance train-only",
           "AR1 redundancy variance inflation is approximate, not joint temporal filter",
           "No extra anchor or total 2D ground truth used during evaluation",
           "same corridor geometry: not independent cross-scene generalization"],
       arms=json.loads(grouped.reset_index().to_json(orient="records")),
       scientific_PASS=False)
    (o/"STATUS.json").write_text(json.dumps(info,indent=2,allow_nan=False))
    with (o/"RESULTS_KO.md").open("w") as f:
       f.write("# 기존 7개 RF 케이스 Range-only 평균/분산/AR1 신뢰도 보정 실제 실행\n\n")
       f.write("RF 관측기 고정 offset은 수정하지 않고, train ROUTE의 range 잔차로 조건부 평균·분산 및 AR1 redundancy를 추정했다. 평가 ROUTE의 true xy/range는 filter 입력이 아니다. 같은 물리복도 내 leave-route-out 이다. Gating 등 sensor-v2 원본 유지.\n\n")
       f.write(grouped.to_markdown(floatfmt=".4f"))
       f.write("\n\n## Heldout training model\n\n")
       f.write(json.dumps(model,ensure_ascii=False,indent=2))
       f.write("\n\n## 한계\n\n극단 NEES tail, partial observable single-anchor gauge, 변환된 posterior가 KF consistency라고 자동 입증되지 않음. AR1-based inflation은 정확한 joint likelihood가 아니다. 추가 native Sionna RF나 기존 원본 코드 수정 없음.\n")
    print("RANGE_ABLATION_SUMMARY",json.dumps(info,allow_nan=False),flush=True)
if __name__=="__main__":execute()
