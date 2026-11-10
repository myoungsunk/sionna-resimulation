#!/usr/bin/env python3
"""Reproduce B0 prior/bias audit from already committed B-MCG NPZ and RF CSV.
No RF simulation or policy training. Evaluator GT is audit-only.
"""
from pathlib import Path
import json,math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"research/B_MCG_V1_20261109/RUN_42600632209"
CIR=ROOT/"research/B_MCG_V1_20261109/CASE_GALLERY_20261109"
OUT=Path(__file__).resolve().parent
FIG=OUT/"figures"
FIG.mkdir(exist_ok=True)
DEG=180/np.pi
Z=1.959963984540054
def wrap(a): return (np.asarray(a)+np.pi)%(2*np.pi)-np.pi
def sinc_half(a):
    if abs(a)<1e-4:
        v=a*a
        return 1-v/24+v*v/1920-v*v*v/322560, -a/12+a**3/480-a**5/53760
    h=a/2
    return np.sin(h)/h,(h*np.cos(h)-np.sin(h))/(2*h*h)
rows=[]
means=[]
for route in ("R2","R4","R5"):
    d=pd.read_csv(CIR/f"PRIMARY_{route}_RF_CIR_FEATURES.csv").sort_values("k").reset_index(drop=True)
    n=len(d)
    assert n=={"R2":979,"R4":742,"R5":1415}[route]
    truth=d.yaw_true_rad.to_numpy()
    times=d.t_s.to_numpy()
    dt=np.r_[0,np.diff(times)]
    truthstep=np.r_[0,wrap(np.diff(truth))]
    gyro_basis=None
    for stratum in ("B_FROZEN","B_BIAS_COV"):
        path=BASE/route/"active"/stratum/"OFF"/f"{route}_OFF.npz"
        with np.load(path,allow_pickle=False) as nf:
            trace={k:nf[k] for k in nf.files}
        assert len(trace["x"])==n
        assert np.array_equal(trace["pose_id"],d.pose_id.to_numpy())
        assert np.allclose(trace["t"],times,atol=1e-9,rtol=0)
        x=trace["x"];xp=trace["prior"];P=trace["P"];Pp=trace["Pprior"]
        H=trace["H"];K=trace["K"];nu=trace["nu"];R=trace["Rbase"]
        prv=np.vstack([xp[0],x[:-1]])
        gyro=np.zeros(n);ds=np.zeros(n)
        qterms=np.zeros((n,4))
        max_p=0.
        for k in range(1,n):
            gyk=float(wrap(xp[k,2]-prv[k,2]))+prv[k,3]*dt[k]
            gyro[k]=gyk
            ang=gyk-prv[k,3]*dt[k];c,dc=sinc_half(ang);phi=prv[k,2]+ang/2
            u=np.array([np.cos(phi),np.sin(phi)]);up=np.array([-u[1],u[0]])
            ds[k]=np.dot(xp[k,:2]-prv[k,:2],u)/c
            dr=ds[k]*c*u;v=ds[k]*(dc*u+c*up/2)
            assert max(abs(xp[k,:2]-prv[k,:2]-dr))<1e-12
            F=np.eye(4);F[:2,2]=[-dr[1],dr[0]];F[:2,3]=-dt[k]*v;F[2,3]=-dt[k]
            G=np.zeros((4,3));G[:2,0]=c*u;G[:2,1]=v;G[2,1]=1.;G[3,2]=1.
            Q=np.diag([2e-5*abs(ds[k]),np.radians(.015)**2*dt[k],0.])
            pp=F@P[k-1]@F.T+G@Q@G.T
            max_p=max(max_p,float(np.max(abs(pp-Pp[k]))))
            qterms[k]=[P[k-1,2,2],-2*dt[k]*P[k-1,2,3],dt[k]**2*P[k-1,3,3],Q[1,1]]
        assert max_p<1e-11,(route,stratum,max_p)
        if gyro_basis is None:gyro_basis=gyro.copy()
        else:assert max(abs(gyro-gyro_basis))<1e-12
        priorerr=wrap(xp[:,2]-truth)
        posterr=wrap(x[:,2]-truth)
        gyerr=gyro-truthstep
        biasterm=-prv[:,3]*dt
        ud=wrap(x[:,2]-xp[:,2])
        recomputed=wrap(priorerr[0]+np.cumsum(gyerr)+np.cumsum(biasterm)+np.cumsum(ud))
        assert max(abs(wrap(recomputed-posterr)))<1e-10
        db=x[:,3]-xp[:,3]
        dbr=K[:,3,0]*nu[:,0];dbs=K[:,3,1]*nu[:,1]
        assert max(abs(db-dbr-dbs))<1e-12
        assert max(abs(xp[1:,3]-x[:-1,3]))<1e-12
        I=np.eye(4)[None]-K@H
        joseph=I@Pp@I.transpose(0,2,1)+K@R@K.transpose(0,2,1)
        assert max(abs(joseph-P).ravel())<1e-10
        std=np.sqrt(Pp[:,2,2])*DEG
        bdeg=x[:,3]*DEG;bsig=np.sqrt(P[:,3,3])*DEG
        fail=np.abs(priorerr*DEG)>Z*std
        f_b=np.abs(bdeg)>Z*bsig
        S=trace["S"]
        innovation=nu/np.sqrt(np.diagonal(S,axis1=1,axis2=2))
        NIS=np.einsum("ni,nij,nj->n",nu,np.linalg.inv(S),nu)
        means.append({"route":route,"stratum":stratum,"n":n,
            "prior_heading_RMSE_deg":float(np.sqrt(np.mean((priorerr*DEG)**2))),
            "prior_heading_mean_error_deg":float(np.mean(priorerr*DEG)),
            "prior_coverage_95":float(np.mean(~fail)),
            "bias_coverage_95_B0_zero":float(np.mean(~f_b)),
            "initial_bias_sigma_deg_s":float(np.sqrt(Pp[0,3,3])*DEG),
            "final_bias_sigma_deg_s":float(bsig[-1]),
            "final_estimated_bias_deg_s":float(bdeg[-1]),
            "final_bias_variance_shrink":float(Pp[0,3,3]/P[-1,3,3]),
            "gyro_cumulative_deg":float(np.sum(gyerr)*DEG),
            "bias_subtraction_cumulative_deg":float(np.sum(biasterm)*DEG),
            "RF_heading_cumulative_deg":float(np.sum(ud)*DEG),
            "bias_range_cumulative_deg_s":float(np.sum(dbr)*DEG),
            "bias_s_cumulative_deg_s":float(np.sum(dbs)*DEG),
            "P_predict_parity_max":max_p,
            "mean_NIS":float(NIS.mean())})
        a=pd.DataFrame({"route":route,"stratum":stratum,"k":np.arange(n),"t_s":times,
            "heading_truth_deg":truth*DEG,
            "heading_prior_error_deg":priorerr*DEG,"heading_prior_sigma_deg":std,
            "heading_posterior_error_deg":posterr*DEG,
            "gyro_increment_deg":gyro*DEG,"gyro_error_step_deg":gyerr*DEG,
            "bias_subtraction_step_deg":biasterm*DEG,
            "RF_heading_step_deg":ud*DEG,
            "RF_heading_from_range_deg":K[:,2,0]*nu[:,0]*DEG,
            "RF_heading_from_s_deg":K[:,2,1]*nu[:,1]*DEG,
            "cumulative_gyro_error_deg":np.cumsum(gyerr)*DEG,
            "cumulative_bias_term_deg":np.cumsum(biasterm)*DEG,
            "cumulative_RF_update_deg":np.cumsum(ud)*DEG,
            "bias_estimate_deg_s":bdeg,"bias_sigma_deg_s":bsig,
            "bias_RF_range_step_deg_s":dbr*DEG,
            "bias_RF_s_step_deg_s":dbs*DEG,
            "P_heading_prior_deg2":Pp[:,2,2]*DEG**2,
            "P_heading_bias_cross_deg2_s":Pp[:,2,3]*DEG**2,
            "P_bias_prior_deg2_s2":Pp[:,3,3]*DEG**2,
            "prior_95_fail":fail,"bias_95_fail_B0":f_b,
            "s_RF_error_vs_model":d.e_s_oldmodel.to_numpy(),
            "s_Full_minus_LoS":d.e_s_mp.to_numpy(),
            "normalized_s_innovation":innovation[:,1],
            "NIS":NIS})
        rows.append(a)
        fig,axs=plt.subplots(3,1,figsize=(11,8),sharex=True,layout="constrained")
        axs[0].plot(times,a.heading_prior_error_deg,label="prior minus GT")
        axs[0].plot(times,Z*std,"--",label="+1.96sigma")
        axs[0].plot(times,-Z*std,"--",label="-1.96sigma")
        axs[0].set_ylabel("Heading (deg)");axs[0].legend(fontsize=7)
        axs[1].plot(times,bdeg,label="estimated bias")
        axs[1].plot(times,Z*bsig,"--",label="+1.96sigma")
        axs[1].plot(times,-Z*bsig,"--",label="-1.96sigma")
        axs[1].axhline(0,ls=":",label="true bias (B0)");axs[1].legend(fontsize=7)
        axs[1].set_ylabel("deg/s")
        axs[2].plot(times,a.s_RF_error_vs_model,label="s vs model residual")
        axs[2].plot(times,a.s_Full_minus_LoS,label="Full minus LoS s")
        axs[2].set_ylabel("s");axs[2].set_xlabel("time (s)");axs[2].legend(fontsize=7)
        for ax in axs:ax.grid(alpha=.2)
        fig.suptitle(f"{route} {stratum}: prior uncertainty, gyro bias, RF residual")
        fig.savefig(FIG/f"{route}_{stratum}.png",dpi=120)
        plt.close(fig)
summary=pd.DataFrame(means);detail=pd.concat(rows,ignore_index=True)
summary.to_csv(OUT/"REPLAYED_PRIOR_SUMMARY.csv",index=False)
detail.to_csv(OUT/"REPLAYED_PRIOR_ROWS_6272.csv",index=False)
assert len(detail)==6272 and not detail.duplicated(["route","stratum","k"]).any()
expected={("R2","B_FROZEN"):0.5403472931562819,("R4","B_FROZEN"):0.555256064690027,
          ("R5","B_FROZEN"):0.8777385159010601}
for row in means:
    key=row["route"],row["stratum"]
    if key in expected:assert abs(row["prior_coverage_95"]-expected[key])<1e-9
(OUT/"REPLAY_RECEIPT.json").write_text(json.dumps({"status":"PASS_REPLAY_FROM_PINNED_GITHUB_SOURCES",
    "source_run":42600632209,"n_unique":3136,"n_stratum_rows":6272,
    "scope":"Archived traces and evaluator-only reference; no new closed-loop EKF",
    "original_gyro_npz_directly_reloaded":False,"source_code":"audit_gha_replay.py"},indent=2))
print(summary[["route","stratum","prior_coverage_95","bias_coverage_95_B0_zero"]].to_string(index=False))
