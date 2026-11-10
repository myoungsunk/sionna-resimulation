#!/usr/bin/env python3
"""Publish the additional detailed 6272-row prior-mechanism audit and 13 figures.

Inputs are committed frozen OFF traces and the already independently verified
REPLAYED_PRIOR_ROWS_6272.csv. No RF simulation, estimator recursion, or training.
All GT and Full/LoS fields are evaluator-only retrospective features.
"""
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SRC=HERE/"REPLAYED_PRIOR_ROWS_6272.csv"
BASE=ROOT/"research/B_MCG_V1_20261109/RUN_42600632209"
RF=ROOT/"research/B_MCG_V1_20261109/CASE_GALLERY_20261109"
OUT=HERE/"extended_20261110"
FIG=OUT/"figures"
FIG.mkdir(parents=True,exist_ok=True)
DEG=180/np.pi
Z=1.959963984540054
D=pd.read_csv(SRC)
assert len(D)==6272 and not D.duplicated(["route","stratum","k"]).any()
parts=[]
quarters=[]
summaries=[]
for route in ("R2","R4","R5"):
    d=pd.read_csv(RF/f"PRIMARY_{route}_RF_CIR_FEATURES.csv").sort_values("k").reset_index(drop=True)
    assert len(d)=={"R2":979,"R4":742,"R5":1415}[route]
    for stratum in ("B_FROZEN","B_BIAS_COV"):
        a=D[(D.route==route)&(D.stratum==stratum)].sort_values("k").reset_index(drop=True)
        assert len(a)==len(d) and np.array_equal(a.k.values,np.arange(len(a)))
        assert np.array_equal(a.t_s.values,d.t_s.values)
        with np.load(BASE/route/"active"/stratum/"OFF"/f"{route}_OFF.npz",allow_pickle=False) as z:
            tr={k:z[k] for k in z.files}
        assert np.array_equal(tr["pose_id"],d.pose_id.values)
        n=len(a);t=a.t_s.to_numpy()
        x=tr["x"];xp=tr["prior"];P=tr["P"];Pp=tr["Pprior"]
        nu=tr["nu"];K=tr["K"];S=tr["S"]
        dt=np.r_[0,np.diff(t)]
        prv=np.vstack([xp[:1],x[:-1]])
        zprior=pd.DataFrame({
            "route":route,"stratum":stratum,"k":np.arange(n),"t_s":t,
            "truth_heading_deg":a.heading_truth_deg.values,
            "prior_heading_deg":xp[:,2]*DEG,"posterior_heading_deg":x[:,2]*DEG,
            "prior_error_deg":a.heading_prior_error_deg.values,
            "posterior_error_deg":a.heading_posterior_error_deg.values,
            "prior_sigma_deg":a.heading_prior_sigma_deg.values,
            "posterior_sigma_deg":np.sqrt(P[:,2,2])*DEG,
            "prior95_fail":a.prior_95_fail.astype(bool).values,
            "gyro_angular_step_deg":a.gyro_increment_deg.values,
            "gt_angular_step_deg":np.r_[0, (np.diff(np.unwrap(d.yaw_true_rad.values))*DEG)],
            "gyro_minus_gt_step_deg":a.gyro_error_step_deg.values,
            "bias_prediction_step_deg":a.bias_subtraction_step_deg.values,
            "RF_yaw_update_deg":a.RF_heading_step_deg.values,
            "RF_yaw_update_from_range_deg":a.RF_heading_from_range_deg.values,
            "RF_yaw_update_from_s_deg":a.RF_heading_from_s_deg.values,
            "cum_initial_deg":np.full(n,a.heading_prior_error_deg.iloc[0]),
            "cum_gyro_deg":a.cumulative_gyro_error_deg.values,
            "cum_bias_subtraction_deg":a.cumulative_bias_term_deg.values,
            "cum_RF_heading_update_deg":a.cumulative_RF_update_deg.values,
            "cum_error_reconstructed_deg":a.heading_prior_error_deg.iloc[0]+a.cumulative_gyro_error_deg.values+a.cumulative_bias_term_deg.values+a.cumulative_RF_update_deg.values,
            "est_bias_deg_s":a.bias_estimate_deg_s.values,
            "bias_reported_sigma_deg_s":a.bias_sigma_deg_s.values,
            "bias95_fail_assuming_true0":a.bias_95_fail_B0.astype(bool).values,
            "RF_bias_update_range_deg_s":a.bias_RF_range_step_deg_s.values,
            "RF_bias_update_s_deg_s":a.bias_RF_s_step_deg_s.values,
            "Ppsi_psi_prior_deg2":a.P_heading_prior_deg2.values,
            "Ppsi_b_prior_deg2_s":a.P_heading_bias_cross_deg2_s.values,
            "Pbb_prior_deg2_s2":a.P_bias_prior_deg2_s2.values,
            "Pbb_post_deg2_s2":P[:,3,3]*DEG**2,
            "pred_cov_prev_yaw_deg2":np.r_[0,P[:-1,2,2]]*DEG**2,
            "pred_cov_cross_term_deg2":np.r_[0,-2*dt[1:]*P[:-1,2,3]]*DEG**2,
            "pred_cov_bias_term_deg2":np.r_[0,dt[1:]**2*P[:-1,3,3]]*DEG**2,
            "pred_cov_gyro_noise_deg2":np.r_[0,(np.radians(.015)**2*dt[1:])]*DEG**2,
            "RF_P_yaw_reduction_deg2":(Pp[:,2,2]-P[:,2,2])*DEG**2,
            "RF_P_bias_reduction_deg2_s2":(Pp[:,3,3]-P[:,3,3])*DEG**2,
            "NIS":a.NIS.values,
            "innovation_s_whitened":a.normalized_s_innovation.values,
            "innovation_range_whitened":nu[:,0]/np.sqrt(S[:,0,0]),
            "range_obs_minus_model_m":d.e_r_oldmodel_m.values,
            "s_obs_minus_model":a.s_RF_error_vs_model.values,
            "full_minus_LoS_s":a.s_Full_minus_LoS.values,
            "H_s_psi":tr["H"][:,1,2],"K_heading_s":K[:,2,1],
            "RF_s_tap":d.B_F.values,"accepted":tr["mask"],
            "XY_error_m":np.linalg.norm(x[:,:2]-d[["x_true","y_true"]].to_numpy(),axis=1)
        })
        assert np.max(np.abs(zprior.prior_error_deg-a.heading_prior_error_deg))<1e-9
        assert np.max(abs(zprior.cum_error_reconstructed_deg-zprior.posterior_error_deg))<1e-8 or np.max(abs(((zprior.cum_error_reconstructed_deg-zprior.posterior_error_deg+180)%360)-180))<1e-8
        check=(zprior.pred_cov_prev_yaw_deg2+zprior.pred_cov_cross_term_deg2+zprior.pred_cov_bias_term_deg2+zprior.pred_cov_gyro_noise_deg2)
        assert np.max(abs(check.iloc[1:].values-zprior.Ppsi_psi_prior_deg2.iloc[1:].values))<1e-8
        parts.append(zprior)
        summaries.append(dict(route=route,stratum=stratum,n=n,
              prior_heading_RMSE_deg=float(np.sqrt(np.mean(zprior.prior_error_deg**2))),
              prior_heading_mean_error_deg=float(zprior.prior_error_deg.mean()),
              heading_prior_coverage95=float((~zprior.prior95_fail).mean()),
              bias_95_coverage_assuming_true_zero=float((~zprior.bias95_fail_assuming_true0).mean()),
              bias_final_deg_s=float(zprior.est_bias_deg_s.iloc[-1]),
              bias_final_sigma_deg_s=float(zprior.bias_reported_sigma_deg_s.iloc[-1]),
              gyro_cumulative_error_deg=float(zprior.cum_gyro_deg.iloc[-1]),
              bias_subtraction_cumulative_deg=float(zprior.cum_bias_subtraction_deg.iloc[-1]),
              RF_yaw_correction_cumulative_deg=float(zprior.cum_RF_heading_update_deg.iloc[-1])))
        for j,(lo,hi) in enumerate([(0,int(n*.25)),(int(n*.25),int(n*.5)),(int(n*.5),int(n*.75)),(int(n*.75),n)]):
            q=zprior.iloc[lo:hi];v=q.s_obs_minus_model.to_numpy()
            quarters.append(dict(route=route,stratum=stratum,quarter=j+1,n=len(q),
                prior_error_mean_deg=float(q.prior_error_deg.mean()),
                prior_heading_RMSE_deg=float(np.sqrt(np.mean(q.prior_error_deg**2))),
                G95_coverage=float((~q.prior95_fail).mean()),
                bias_coverage=float((~q.bias95_fail_assuming_true0).mean()),
                bias_abs_mean_deg_s=float(q.est_bias_deg_s.abs().mean()),
                reported_bias_sigma_mean_deg_s=float(q.bias_reported_sigma_deg_s.mean()),
                mean_P_heading_deg2=float(q.Ppsi_psi_prior_deg2.mean()),
                mean_abs_RF_s_residual=float(np.mean(abs(v))),
                RF_s_residual_lag1=float(np.corrcoef(v[:-1],v[1:])[0,1]) if len(v)>3 and np.std(v)>1e-15 else None,
                cum_RF_heading_at_end_deg=float(q.cum_RF_heading_update_deg.iloc[-1]),
                cum_bias_at_end_deg=float(q.cum_bias_subtraction_deg.iloc[-1])))
        # Detailed diagnostic views; no interpretation as independent observations.
        fig,ax=plt.subplots(4,1,figsize=(13,11),sharex=True,constrained_layout=True)
        ax[0].plot(t,zprior.prior_error_deg,label="Prior - GT");ax[0].plot(t,Z*zprior.prior_sigma_deg,"--",label="+1.96 sigma");ax[0].plot(t,-Z*zprior.prior_sigma_deg,"--",label="-1.96 sigma");ax[0].legend(fontsize=8);ax[0].set_ylabel("Heading (deg)")
        ax[1].plot(t,zprior.est_bias_deg_s,label="Estimated bias");ax[1].plot(t,Z*zprior.bias_reported_sigma_deg_s,"--",label="+1.96 sigma");ax[1].plot(t,-Z*zprior.bias_reported_sigma_deg_s,"--",label="-1.96 sigma");ax[1].axhline(0,color=".5",ls=":");ax[1].legend(fontsize=8);ax[1].set_ylabel("Bias (deg/s)")
        ax[2].plot(t,zprior.s_obs_minus_model,label="B s - SourceFFD");ax[2].plot(t,zprior.full_minus_LoS_s,label="B Full - LoS s");ax[2].legend(fontsize=8);ax[2].set_ylabel("s residual")
        ax[3].plot(t,zprior.RF_yaw_update_from_range_deg,label="Range → Heading");ax[3].plot(t,zprior.RF_yaw_update_from_s_deg,label="s → Heading");ax[3].plot(t,zprior.bias_prediction_step_deg,label="−bias dt");ax[3].legend(fontsize=8);ax[3].set_xlabel("Time (s)");ax[3].set_ylabel("Correction (deg)")
        for aa in ax:aa.grid(alpha=.15)
        fig.suptitle(f"{route} {stratum} — prior / bias / RF detailed audit")
        fig.savefig(FIG/f"{route}_{stratum}_prior_bias_RF.png",dpi=140);plt.close(fig)
        fig,ax=plt.subplots(3,1,figsize=(13,9),sharex=True,constrained_layout=True)
        ax[0].plot(t,zprior.cum_initial_deg+zprior.cum_gyro_deg,label="Initial + gyro");ax[0].plot(t,zprior.cum_initial_deg+zprior.cum_gyro_deg+zprior.cum_bias_subtraction_deg,label="+ estimated bias");ax[0].plot(t,zprior.cum_error_reconstructed_deg,label="+ RF corrections");ax[0].legend(fontsize=8);ax[0].set_ylabel("Cum. heading (deg)")
        ax[1].plot(t,zprior.Ppsi_psi_prior_deg2,label="P yaw");ax[1].plot(t,zprior.pred_cov_cross_term_deg2,label="Cross −2 dt P_yb");ax[1].plot(t,zprior.pred_cov_bias_term_deg2,label="dt² Pbb");ax[1].plot(t,zprior.pred_cov_gyro_noise_deg2,label="Gyro Q");ax[1].legend(fontsize=8);ax[1].set_ylabel("Variance (deg²)")
        ax[2].plot(t,zprior.innovation_s_whitened,label="s innovation / sqrt(Sss)");ax[2].plot(t,zprior.innovation_range_whitened,label="Range innovation / sqrt(Srr)");ax[2].legend(fontsize=8);ax[2].set_ylabel("Whitened innovation");ax[2].set_xlabel("Time (s)")
        for aa in ax:aa.grid(alpha=.15)
        fig.suptitle(f"{route} {stratum} — cumulative terms / covariance / innovation")
        fig.savefig(FIG/f"{route}_{stratum}_cumulative_covariance.png",dpi=140);plt.close(fig)
full=pd.concat(parts,ignore_index=True)
assert len(full)==6272 and not full.duplicated(["route","stratum","k"]).any()
full.to_csv(OUT/"PRIOR_MECHANISM_ROWS_6272.csv",index=False)
q=pd.DataFrame(summaries);q.to_csv(OUT/"PRIOR_MECHANISM_SUMMARY.csv",index=False)
pd.DataFrame(quarters).to_csv(OUT/"WINDOW_CALIBRATION_24.csv",index=False)
fig,axes=plt.subplots(1,2,figsize=(11,4.3),constrained_layout=True)
for j,st in enumerate(("B_FROZEN","B_BIAS_COV")):
    a=q[q.stratum==st];idx=np.arange(3)+(j-.5)*.36
    axes[0].bar(idx,a.heading_prior_coverage95*100,.35,label=st)
    axes[1].bar(idx,a.bias_95_coverage_assuming_true_zero*100,.35,label=st)
for aa in axes:
    aa.axhline(95,ls="--",color=".5");aa.set_xticks(np.arange(3),["R2","R4","R5"]);aa.set_ylim(0,105);aa.set_ylabel("Empirical inclusion (%)");aa.legend(fontsize=8);aa.grid(axis="y",alpha=.15)
axes[0].set_title("Heading prior 95% interval");axes[1].set_title("B0 gyro bias nominal interval")
fig.savefig(FIG/"coverage_and_bias_confidence.png",dpi=160);plt.close(fig)
manifest={"status":"PASS_ARCHIVED_OUTPUT_RECONSTRUCTION","source_run":42600632209,
          "sources":{"replayed_prior":hashlib.sha256(SRC.read_bytes()).hexdigest()},
          "rows":len(full),"windows":len(quarters),"figures":len(list(FIG.glob("*.png"))),
          "limits":["No original direct gyro input; derived from saved frozen predictor","No new RF or closed-loop EKF",
                    "Original local figure bytes may differ by renderer; numeric evidence reconstructed"],
          "sha256":{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(OUT.rglob("*")) if p.is_file()}}
assert manifest["windows"]==24 and manifest["figures"]==13
(OUT/"EXTENDED_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
print("EXTENDED_PASS",len(full),len(quarters),manifest["figures"])
