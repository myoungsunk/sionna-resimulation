#!/usr/bin/env python3
"""Actual full P6 range-only EKF: exactly how range updates x/y/yaw/calibration.
Experiment: dynamically suppress range-to-heading gain only or all non-xy
gain, with Joseph covariance (valid PSD but non-optimal gain), and compare
against baseline/heldout bias-calibrated range.

Original fixed Sionna range, original 5Hz sensor V2, no new RF/Sionna/FFD.
Any use of true pose is post-update EVALUATION ONLY; never in correction.
"""
from __future__ import annotations
import argparse, math, json
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import chi2

from run_range_bias_consistency_ablation import (
    ROOT,RUN,BLOCK,TDIR,CASES,LEVELS,DT,PROGRESS_START,
    context,train_heldout_models,cfg,select_params
)
from qclean_uwb.drivesim import sensor_v2 as V, filter_v2 as F
from qclean_uwb.drivesim.filters import wrap

ARMS=("A_ODOM","B_FULL_P6","C_KPSI_ZERO","D_KXY_ONLY",
      "E_CAL_FULL_P6","F_CAL_KPSI_ZERO")
PERCENTILE=chi2.ppf(.95,3)

def one_run(case,level,seed,arm,ctx,models):
    offset,labels,cases,route_data=ctx
    route=case.split("_")[0]; rt=route_data[route];c=cases[case]
    config=cfg(c,offset)
    P0=np.diag(np.asarray(config.p0_std,float)**2)
    x0=np.r_[rt["pose"][0].copy(),0.,0.,0.]
    x0[:3]+=V.rng(seed,"initial").normal(size=3)*np.asarray(config.p0_std[:3])
    inp,ev=V.generate(rt["t"],rt["ds"],rt["dth"],
                      V.SensorV2Config(level=level,condition="all"),seed)
    f=F.SensorV2Filter(config,None,x0)
    observations=labels[labels.case==case].set_index("pose_id")
    res=[];record=[];perstep=[]
    n_applied=0;n_rejected=0
    for kprogress,(k,poseid) in enumerate(zip(rt["main_indices"],rt["no"].pose_id)):
        if int(k):
            f.step(float(inp["ds_odom"][k]),float(inp["dtheta_gyro"][k]),
                   float(inp["dtheta_odom"][k]),float(inp["dt_s"][k]))
        row=observations.loc[int(poseid)]
        est_pre=f.comps[0].x.copy()
        ppre=f.comps[0].P.copy()
        truth=rt["pose"][k]
        epsi_pre=V.wrap(float(truth[2]-est_pre[2]))
        geom=np.sqrt(np.sum((est_pre[:2]-np.array(c["anchor_xyz"][:2]))**2)+
                     (c["anchor_xyz"][2]-c["robot_z"])**2)
        H=np.zeros(6)
        H[:2]=(est_pre[:2]-np.asarray(c["anchor_xyz"][:2]))/geom
        cal=arm.startswith(("E_","F_"))
        parms=select_params(models[route],geom) if cal else None
        true_mean_correction=float(parms["bias_m"]) if cal else 0.
        R=(float(parms["effective_R_m2"])*models[route]["tau_integrated_AR1_approx"]
            if cal else config.range_sigma**2+config.range_extra_sigma**2+config.range_quant_var)
        u=float(row.range_m)-geom-offset-true_mean_correction
        S=float(H@ppre@H+R)
        K=ppre@H/S
        accepted=(arm!="A_ODOM" and bool(row.detected)
                  and np.isfinite(row.range_m) and u*u/S<=config.gate)
        direct_deltaψ=0.0
        shrink_opt=float(K[2]*K[2]*S)
        if accepted:
            Kuse=K.copy()
            if arm in ("C_KPSI_ZERO","F_CAL_KPSI_ZERO"):Kuse[2]=0.
            if arm=="D_KXY_ONLY":Kuse[2:]=0.
            I=np.eye(6)-np.outer(Kuse,H)
            post=I@ppre@I.T+R*np.outer(Kuse,Kuse)
            f.comps[0].P=(post+post.T)/2
            f.comps[0].x=est_pre+Kuse*u
            f.comps[0].x[2]=wrap(f.comps[0].x[2])
            direct_deltaψ=float(Kuse[2]*u)
            n_applied+=1
        elif arm!="A_ODOM":n_rejected+=1
        est,P=f.mean_cov()
        e=truth-est[:3]
        e[2]=V.wrap(e[2])
        P3=P[:3,:3]
        poseNEES=float(e@np.linalg.solve(P3,e))
        Pxx=P3[:2,:2]
        Pcond=Pxx-np.outer(P3[:2,2],P3[2,:2])/max(P3[2,2],1e-18)
        e_cond=e[:2]-(P3[:2,2]/max(P3[2,2],1e-18))*e[2]
        xyNEES=float(e_cond@np.linalg.solve(Pcond,e_cond))
        psiNEES=float(e[2]*e[2]/P3[2,2])
        assert abs(poseNEES-(xyNEES+psiNEES))<1e-6*max(1,poseNEES)
        crosshat=float(K[2])
        if float(rt["no"].t_s.iloc[kprogress])>=PROGRESS_START:
            res.append(dict(k=int(k),progress=float(rt["no"].t_s.iloc[kprogress]),
                ex=float(e[0]),ey=float(e[1]),epsi_rad=float(e[2]),
                poseNEES=poseNEES,xyNEES=xyNEES,psiNEES=psiNEES,
                Ppsi=float(P3[2,2]),radstd=float(np.sqrt(H@P@H)),
                heading_sigma_deg=float(math.degrees(math.sqrt(P3[2,2]))),
                Kpsi_per_m=crosshat,delta_psi_deg=math.degrees(direct_deltaψ),
                y_range_m=u, range_noise_R=R,range_scalar_S=S,
                range_enabled=int(accepted), optimal_shrink_Ppsi_rad2=shrink_opt))
        if accepted and kprogress and (kprogress%10==0):
            perstep.append(dict(case=case,arm=arm,level=level,seed=seed,
               pose_id=int(poseid),time_progress=float(rt["no"].t_s.iloc[kprogress]),
               K_psi_rad_per_m=crosshat,K_calibration_gain_norm=float(np.linalg.norm(K[3:])),
               K_xy_gain_norm=float(np.linalg.norm(K[:2])),
               innovation_range_m=u,S_range_m2=S,
               delta_psi_applied_deg=math.degrees(direct_deltaψ),
               delta_psi_optimal_deg=math.degrees(K[2]*u),
               yaw_abs_error_before_deg=math.degrees(abs(epsi_pre)),
               yaw_abs_error_after_deg=math.degrees(abs(e[2])),
               yaw_squared_error_change_deg2=math.degrees(e[2])**2-math.degrees(epsi_pre)**2,
               Ppsi_before_rad2=float(ppre[2,2]),Ppsi_after_rad2=float(P[2,2]),
               Ppsi_shrink_actual=float(ppre[2,2]-P[2,2]),
               radial_pretime_geometry=geom,
               true_RF_range_model_error_eval_only=float(row.e_range-offset),
               XY_yaw_cross_Pxy_psi_before=np.asarray(ppre[:2,2]).tolist(),
               P6_before=ppre.tolist(),P6_after=P.tolist()))
        if int(kprogress)==int(len(rt["no"])-1) and arm=="A_ODOM":pass
    g=pd.DataFrame(res);dd=np.degrees(g.epsi_rad)
    out=dict(case=case,route=route,level=level,seed=seed,arm=arm,n_eval=len(g),
         heading_rmse_deg=float(np.sqrt(np.mean(dd**2))),
         pos_rmse_m=float(np.sqrt(np.mean(g.ex**2+g.ey**2))),
         pose_nees_mean=float(g.poseNEES.mean()),
         pose_nees_median=float(g.poseNEES.median()),
         heading_nees_mean=float(g.psiNEES.mean()),
         conditional_xy_nees_mean=float(g.xyNEES.mean()),
         Ppsi_std_deg_median=float(g.heading_sigma_deg.median()),
         pose95_coverage=float((g.poseNEES<=PERCENTILE).mean()),
         total_direct_heading_correction_deg=float(g.delta_psi_deg.sum()),
         mean_abs_direct_range_heading_update_deg=float(g.delta_psi_deg.abs().mean()),
         median_abs_range_Kpsi_rad_per_m=float(g.Kpsi_per_m.abs().median()),
         median_abs_range_innovation_m=float(g.y_range_m.abs().median()),
         accepted_range_updates=int(n_applied),rejected_range_updates=int(n_rejected),
         median_range_scalar_S_m2=float(g.range_scalar_S.median()))
    return out,perstep

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--seeds",type=int,default=8)
    ap.add_argument("--smoke",action="store_true")
    args=ap.parse_args();o=args.out;o.mkdir(parents=True,exist_ok=True)
    ctx=context();train=train_heldout_models(ctx[1],ctx[3],ctx[0],cfg(ctx[2][CASES[0]],ctx[0]))
    jobs=[(CASES[0],0,0)] if args.smoke else [(c,l,s) for c in CASES for l in LEVELS for s in range(args.seeds)]
    outputs=[];steps=[]
    for i,(case,level,seed) in enumerate(jobs,1):
        for arm in ARMS:
            x,ss=one_run(case,level,seed,arm,ctx,train);outputs.append(x)
            if seed==0 and level==0:steps+=ss
        if i%7==0 or args.smoke:print("CAUSAL_P6_PROGRESS",i,len(jobs),flush=True)
    frame=pd.DataFrame(outputs);step=pd.DataFrame(steps)
    frame.to_csv(o/"P6_HEADING_GAIN_ABLATIONS.csv",index=False)
    step.to_csv(o/"REPRESENTATIVE_PER_RANGE_GAIN_AND_P6.csv.gz",index=False)
    summary=frame.groupby("arm")[["heading_rmse_deg","pos_rmse_m","pose_nees_mean",
             "heading_nees_mean","conditional_xy_nees_mean","Ppsi_std_deg_median",
             "pose95_coverage","mean_abs_direct_range_heading_update_deg",
             "median_abs_range_Kpsi_rad_per_m","accepted_range_updates"]].mean()
    summary.to_csv(o/"P6_HEADING_GAIN_SUMMARY.csv")
    frame.groupby(["case","arm"])[["heading_rmse_deg","pos_rmse_m","pose_nees_mean",
        "heading_nees_mean","conditional_xy_nees_mean"]].mean().to_csv(
            o/"P6_HEADING_GAIN_CASES.csv")
    pv=frame.pivot(index=["case","level","seed"],columns="arm",
             values=["heading_rmse_deg","pos_rmse_m","pose_nees_mean"])
    vv=[]
    for a,b in [("B_FULL_P6","C_KPSI_ZERO"),("B_FULL_P6","D_KXY_ONLY"),
                 ("E_CAL_FULL_P6","F_CAL_KPSI_ZERO"),("B_FULL_P6","A_ODOM")]:
        for v in ("heading_rmse_deg","pos_rmse_m","pose_nees_mean"):
            delta=pv[(v,a)]-pv[(v,b)]
            vv.append(dict(a=a,b=b,metric=v,n=len(delta),mean=float(delta.mean()),
                           median=float(delta.median()),better_fraction=float((delta<0).mean())))
    pd.DataFrame(vv).to_csv(o/"P6_HEADING_GAIN_PAIRED_CAUSAL_EFFECT.csv",index=False)
    result=dict(status="EXPLORATORY_RANGE_KPSI_INTERVENTION_COMPLETED",
        source="same 7 cases original native Sionna H observation and sensor-v2",
        experimental_unit="same case/level/seed original driving",
        runs=len(frame),
        arms=ARMS,
        methodological_note=[
          "B_FULL_P6 matches original frozen B range-only Kpsi and P6 update",
          "C_KPSI_ZERO is nonoptimal constrained Kalman gain with Joseph covariance; diagnostic not production",
          "D_KXY_ONLY is nonoptimal XY-only measurement update; P6 covariance retains cross terms",
          "E uses heldout-route conditional mean/bias plus approximate AR1 R-inflation; F turns off only its Kpsi.",
          "True heading used ONLY in outcome, never in range prediction or update.",
          "For every timestep exact poseNEES=headingNEES+Schur XY NEES.",
          "No new RF H, single corridor, no new H source parity or independent geometry."
        ],
        scientific_PASS=False,
        mean=json.loads(summary.reset_index().to_json(orient="records")))
    (o/"STATUS.json").write_text(json.dumps(result,indent=2,allow_nan=False))
    with (o/"RESULTS_KO.md").open("w",encoding="utf-8") as out:
        out.write("# Range-only Sensor-v2 EKF의 실제 6×6 Kalman gain heading 전파 인과 대조\n\n")
        out.write("같은 case,gyro/odom noise seed와 동일 original range 관측을 사용. Range gain Kpsi 또는 비-XY gain만 인위적으로 0으로 제한하고 Joseph P6를 재계산하므로 완전한 새 optimal KF를 주장하지 않는다. 전반적 필터 정확도와 NEES에 영향을 주는 인과적 경로를 구분하기 위한 ablation이다.\n\n")
        out.write(summary.to_markdown(floatfmt=".5f"))
        out.write("\n\n## 대조쌍\n\n")
        out.write(pd.DataFrame(vv).to_markdown(index=False,floatfmt=".4f"))
        out.write("\n\n확인 수식: Hrange=[hx,hy,0,0,0,0], Kpsi=(Pψx hx+Pψy hy)/S, Δψrange=Kpsi·innovation; Joseph covariance with arbitrary chosen constrained gain. Pose NEES = eψ²/Pψψ + e_condxy^T P_condxy^-1 e_condxy. 본 source에는 truth heading 의존 제어가 없다.\n")
    print("GAIN_CAUSAL_RESULT",json.dumps(result,allow_nan=False),flush=True)
if __name__=="__main__":main()
