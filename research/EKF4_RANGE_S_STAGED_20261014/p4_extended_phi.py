"""Audited frozen 2-degree LoS LUT: theta/phi_tx/phi_rx sensitivity along R2.

One frozen seed0 DR prior trajectory per R2 mount0/mount45.
No Full yaw-sweep measurements exist; phi_rx change is LoS-only prediction.
"""
import argparse,json,math,os,collections
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from p3_frozen_inputs import open_verified_archive,load_frozen_rf_trace
from p3_rf_adapter4 import FrozenLut,RS
from p4_lut_boundary import lut_angles
from p4_extended_audit import require_audit,digest,ORIGINAL_RF_SHA,ROOT
HERE=Path(__file__).resolve().parent
CASES=("R2_aA_m0","R2_aA_m45")
def percentiles(values):
    v=np.asarray(values,float)
    finite=v[np.isfinite(v)]
    if not len(finite):return {"n":0}
    return {"n":int(len(finite)),"p10":float(np.quantile(finite,.1)),
       "median":float(np.median(finite)),"p90":float(np.quantile(finite,.9)),
       "mean":float(np.mean(finite)),"max":float(np.max(finite))}
def fisher_conditional(g, rho):
    # Uniform-stationary independent or AR1 correlated R0 covariance
    # scaled in s units. The nuisance common offset is marginalized
    # via Schur complement, not treated as independent heading GT.
    n=len(g);C=RS*rho**np.abs(np.subtract.outer(np.arange(n),np.arange(n)))
    ones=np.ones(n)
    ig=np.linalg.solve(C,g)
    io=np.linalg.solve(C,ones)
    I=float(g@ig-(g@io)**2/(ones@io))
    return max(I,0.)
def trace_sensitivity(lut,case,trace):
    vals=[];sweeps=[];fisher={k:[] for k in
       [(10,0.),(10,.8),(10,.95),(45,0.),(45,.8),(45,.95)]}
    for k,x in enumerate(trace.prior_x):
        theta,tx,rx=lut_angles(x,case)
        s,g=lut(theta,tx,rx)
        vals.append([theta,tx,rx,s,*g,math.hypot(g[1],g[2])])
        res={}
        for span in (10,45):
            # Same 11 measurements per sweep for fair comparison:
            offsets=np.linspace(-span,span,11)
            s_rx=np.array([lut(theta,tx,rx-d)[0] for d in offsets])
            s_tx=np.array([lut(theta,tx+d,rx)[0] for d in offsets])
            slope=np.array([-lut(theta,tx,rx-d)[1][2]*180/math.pi
                            for d in offsets])
            res[f"rx_swing_{span}"]=float(np.ptp(s_rx))
            res[f"tx_swing_{span}"]=float(np.ptp(s_tx))
            res[f"rx_first_to_last_{span}"]=float(s_rx[-1]-s_rx[0])
            for rho in (0.,.8,.95):
                I=fisher_conditional(slope,rho)
                fisher[(span,rho)].append(math.degrees(1/math.sqrt(I)) if I>0 else math.inf)
        sweeps.append(res)
    value=np.asarray(vals)
    report={
        "samples":len(vals),"theta_deg":percentiles(value[:,0]),
        "phi_tx_deg":percentiles(value[:,1]),
        "phi_rx_deg":percentiles(value[:,2]),
        "abs_ds_dtheta_per_deg":percentiles(abs(value[:,4])),
        "abs_ds_dphi_tx_per_deg":percentiles(abs(value[:,5])),
        "abs_ds_dphi_rx_per_deg":percentiles(abs(value[:,6])),
        "abs_ds_dyaw_per_rad":percentiles(abs(value[:,6])*180/math.pi),
        "relative_phi_tx_vs_phi_rx":
           {"fraction_abs_tx_gt_rx":float(np.mean(abs(value[:,5])>abs(value[:,6]))),
            "median_abs_rx_over_abs_tx":float(np.median(abs(value[:,6])/(abs(value[:,5])+1e-12)))},
    }
    for metric in sweeps[0]:
        report[metric]=percentiles([r[metric] for r in sweeps])
    for (span,rho),sds in fisher.items():
        report[f"optimistic_deg_sd_span{span}_AR1rho{rho:g}"]=percentiles(sds)
    return report,value,sweeps
def main(archive,audit,out):
    require_audit(audit)
    if digest(archive)!=ORIGINAL_RF_SHA:raise RuntimeError("ORIGINAL_RF_ZIP_SHA_MISMATCH")
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
    cases={c["id"]:c for c in manifest["cases"]}
    lut=FrozenLut(ROOT)
    report={"schema":"R2_FROZEN_LOS_LUT_ANGULAR_SENSITIVITY_V1",
      "git_sha":os.environ["GITHUB_SHA"],"input_sha256":ORIGINAL_RF_SHA,
      "mounts":[0,45],"grid_step_deg":2,
      "scope":"LoS model at stored frozen R2 DR priors; NOT measured Full yaw scan",
      "sweep_model":"fixed x,y,theta,phi_tx, yaw offsets change phi_rx only",
      "noise_assumptions":{"s_sigma":math.sqrt(RS),
        "AR1_rho":[0.,.8,.95],"all_fisher_sd_optimistic_not_calibrated":True},
      "cases":[],"scientific_PASS":False}
    with open_verified_archive(archive) as z:
        summary=json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
        for case_id in CASES:
            d=next(x for x in summary["per_case"] if x["case"]==case_id and x["channel"]=="los")
            t=load_frozen_rf_trace(z,d)
            model,value,sw=trace_sensitivity(lut,cases[case_id],t)
            row={"case":case_id,"mount_deg":cases[case_id]["mount_deg"],
                 "channel":"los","model_sensitivity":model}
            report["cases"].append(row)
            # pick median swing candidate among t>=30 for visualization
            xs=np.array([x["rx_swing_10"] for x in sw])
            eval_idx=np.flatnonzero(t.t_s>=30)
            km=int(eval_idx[np.argmin(abs(xs[eval_idx]-np.median(xs[eval_idx])))])
            theta,tx,rx=value[km,:3]
            offsets=np.linspace(-45,45,181)
            ys_rx=np.array([lut(theta,tx,rx-d)[0] for d in offsets])
            ys_tx=np.array([lut(theta,tx+d,rx)[0] for d in offsets])
            fig,ax=plt.subplots(figsize=(9,4.8))
            ax.plot(offsets,ys_rx,label="Physical yaw: phi_rx changes")
            ax.plot(offsets,ys_tx,linestyle="--",
                    label="Hypothetical phi_tx variation at fixed phi_rx")
            ax.axvspan(-10,10,alpha=.12,label="+/-10 deg small sweep")
            ax.set(xlabel="Angular perturbation (deg)",
              ylabel="Frozen LoS LUT s",
              title=f"{case_id}, R2 t={t.t_s[km]:.1f}s (fixed x,y)")
            ax.legend();ax.grid(alpha=.25);fig.tight_layout()
            fig.savefig(out/(case_id+"_phi_sensitivity.png"),dpi=170)
            plt.close(fig)
            np.savez_compressed(out/(case_id+"_R2_LOS_SENSITIVITY.npz"),
                 t_s=t.t_s,pose_id=t.pose_id,angles_theta_tx_rx=value[:,:3],
                 derivatives_per_deg=value[:,4:7],
                 swing_rx10=np.array([r["rx_swing_10"] for r in sw]),
                 swing_rx45=np.array([r["rx_swing_45"] for r in sw]))
            print("PHI_CASE "+json.dumps({"case":case_id,"mount":row["mount_deg"],
                "median_ds_dtx":model["abs_ds_dphi_tx_per_deg"]["median"],
                "median_ds_drx":model["abs_ds_dphi_rx_per_deg"]["median"],
                "swing10_med":model["rx_swing_10"]["median"],
                "swing45_med":model["rx_swing_45"]["median"],
                "fisher_sd10_uncorr":model["optimistic_deg_sd_span10_AR1rho0"]["median"]}),flush=True)
    report["status"]="FROZEN_LOS_LUT_SENSITIVITY_COMPUTED"
    report["time_utc"]=datetime.now(timezone.utc).isoformat()
    (out/"PHI_FINAL.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("PHI_FINAL "+json.dumps({"status":report["status"],
        "mounts":len(report["cases"]),"scientific_PASS":False}),flush=True)
    return 0
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for key in ("archive","audit","out"):p.add_argument("--"+key,required=True)
    a=p.parse_args();raise SystemExit(main(a.archive,a.audit,a.out))
