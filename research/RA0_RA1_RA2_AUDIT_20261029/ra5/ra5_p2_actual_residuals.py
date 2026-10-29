#!/usr/bin/env python3
"""RA5-2 read-only actual 7-case source residual/cross-covariance diagnostics.
No claim of independent noise, physical-time field or incremental Fisher information.
"""
import argparse,csv,datetime,gzip,hashlib,json,math,pathlib
import numpy as np
import pandas as pd

EXPECTED=("R2_aA_m0","R2_aB_m0","R2_aA_m45","R4_aA_m0",
          "R4_aB_m0","R5_aA_m0","R5_aB_m0")
def must(x,msg):
    if not x:raise RuntimeError(msg)
def dump(path,rows):
    if isinstance(rows,pd.DataFrame):rows.to_csv(path,index=False);return
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def corr_lag1(x):
    x=np.asarray(x,float)
    if len(x)<3 or np.std(x[:-1])<1e-14 or np.std(x[1:])<1e-14:return float("nan")
    return float(np.corrcoef(x[:-1],x[1:])[0,1])

def main(root,out):
    root=pathlib.Path(root);out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    loaded=[];srcs=[]
    fs=list(root.rglob("RA5_P0_RAW_TAPS.csv.gz"))
    ms=list(root.rglob("RA5_P0_MANIFEST.json"))
    must(len(fs)==len(ms)==7,"ERR_MISSING_CASE_FEATURE_MANIFEST "+str((len(fs),len(ms))))
    for f in fs:
        manpath=f.parent/"RA5_P0_MANIFEST.json"
        must(manpath.is_file(),"ERR_NO_MANIFEST "+str(f))
        meta=json.loads(manpath.read_text())
        must(meta["status"]=="PASS_P0_SOURCE_REPLAY_ONLY","ERR_NONPASS_P0 "+str(f))
        df=pd.read_csv(f)
        must(len(df)==meta["n_all"] and len(df.query("phase == 'TIMELINE'"))==meta["n_timeline"],"ERR_PACKET_DENOM")
        must(len(set(df["case"]))==1 and df["case"].iloc[0]==meta["case"],"ERR_CASE_ID")
        must(not df.duplicated(["case","pose_id"]).any(),"ERR_DUPLICATE_POSE_ID")
        must(df[["r_full","s0_full","s1_full","ds1","e_s_oracle","e_r_oracle_m","r_los","s0_los"]].notna().all().all(),"ERR_NONFINITE_DATA")
        must(np.max(np.abs(df["ds1"]-(df["s1_full"]-df["s0_full"])))<2e-14,"ERR_DS1_DEFINITION")
        srcs.append(dict(case=meta["case"],n_all=meta["n_all"],n_timeline=meta["n_timeline"],n_auxiliary=meta["n_auxiliary"],
           h_sha=[x["sha256"] for x in meta["source_assets"] if x["kind"]=="FULL_H"][0],
           los_sha=[x["sha256"] for x in meta["source_assets"] if x["kind"]=="LOS_H"][0],
           packet_replay_max_s=meta["max_abs_native_s"],packet_replay_max_r_m=meta["max_abs_native_r_m"]))
        loaded.append(df)
    must(set(x["case"] for x in srcs)==set(EXPECTED),"ERR_MISSING_ROUTE_OR_MOUNT")
    allrows=pd.concat(loaded,ignore_index=True)
    df=allrows[allrows["phase"]=="TIMELINE"].copy()
    must(len(allrows)==9519 and len(df)==7251 and set(df["route"])=={"R2","R4","R5"},"ERR_FROZEN_RF_DENOM "+str((len(allrows),len(df))))
    # Original RF difference Full-LoS is a DETERMINISTIC model discrepancy.
    # It is NOT a measured stochastic sensor noise realization.
    df["ds1_los"]=df["s1_los"]-df["s0_los"]
    df["e_ds1_oracle"]=df["ds1"]-df["ds1_los"]
    df["rho"]=np.sqrt((df["x"]-np.where(df["anchor"]=="A",4.,10.))**2+df["y"]**2)
    feats=("e_r_oracle_m","e_s_oracle","e_ds1_oracle")
    results=[];acf=[];revisit=[];idcheck=[]
    for c,g in df.groupby("case",sort=True):
        g=g.sort_values("t_s")
        t=g["t_s"].to_numpy()
        must(np.all(np.diff(t)>0),"ERR_NONMONOTONIC_TIME "+c)
        x=g["e_s_oracle"].to_numpy()
        dr=g["e_r_oracle_m"].to_numpy()
        ds=g["e_ds1_oracle"].to_numpy()
        acf.append(dict(case=c,route=c[:2],n=len(g),lag1_e_s=corr_lag1(x),
            lag1_e_r=corr_lag1(dr),lag1_e_ds1=corr_lag1(ds),
            mean_e_s=float(x.mean()),rms_e_s=float(np.sqrt(np.mean(x*x))),
            max_abs_e_s=float(np.max(np.abs(x))),n_tap_switch=int(g["tap_switch"].sum())))
        # Exact full pose including yaw. Static same-H revisit is not an independent time realization.
        v=g.copy()
        v["pose_key"]=list(zip(v["x"].round(6),v["y"].round(6),v["yaw_body_deg"].round(4)))
        groups=v.groupby("pose_key").agg(n=("t_s","size"),tspan=("t_s",lambda x:float(x.max()-x.min())))
        qualifying=groups[(groups["n"]>1)&(groups["tspan"]>1e-6)]
        revisit.append(dict(case=c,qualifying_revisit_groups=len(qualifying),
                             max_tspan_s=float(qualifying["tspan"].max()) if len(qualifying) else 0.,
                             independent_time_field_samples=0,
                             time_field_identifiability="BLOCKED_STATIC_H_SINGLE_REALIZATION"))
        # Raw covariance [s0,s1] vs transformed [s0,s1-s0], exact empirical identity.
        y=g[["s0_full","s1_full"]].to_numpy();cov=np.cov(y,rowvar=False)
        TT=np.array([[1,0],[-1,1.]])
        yh=g[["s0_full","ds1"]].to_numpy()
        check=np.max(np.abs(np.cov(yh,rowvar=False)-(TT@cov@TT.T)))
        must(check<1e-12,"ERR_FULL_COV_TAP_TRANSFORM "+c+" "+str(check))
        idcheck.append(dict(case=c,cov_transform_max_abs=float(check),n=len(g)))
    for held in ("R2","R4","R5"):
        train=df[df["route"]!=held]
        test=df[df["route"]==held]
        must(len(train)>0 and len(test)>0,"ERR_ZERO_FOLD")
        X=train[list(feats)].to_numpy(float)
        sig=np.cov(X,rowvar=False)
        eig=np.linalg.eigvalsh(sig)
        must(eig.min()>=-1e-12 and np.isfinite(sig).all(),"ERR_COV_PSD "+held)
        # Schur complement of deterministic model-discrepancy covariance.
        sigzz=sig[:2,:2];sigd=sig[2,:2]
        must(np.linalg.cond(sigzz)<1e12,"ERR_SINGULAR_TWO_BRANCH_COV "+held)
        cond=float(sig[2,2]-sigd@np.linalg.solve(sigzz,sigd))
        must(cond>=-1e-12,"ERR_NEGATIVE_CONDITIONAL_VARIANCE "+held)
        corr=np.corrcoef(X,rowvar=False)
        test_cov=np.cov(test[list(feats)].to_numpy(float),rowvar=False)
        results.append(dict(heldout_route=held,n_train=len(train),n_test=len(test),
          n_train_rf_families=int(train["route"].nunique()),
          e_r_std_m=float(np.sqrt(sig[0,0])),e_s_std=float(np.sqrt(sig[1,1])),
          e_ds1_std=float(np.sqrt(sig[2,2])),
          corr_e_r_e_s=float(corr[0,1]),corr_e_s_e_ds1=float(corr[1,2]),
          corr_e_r_e_ds1=float(corr[0,2]),
          conditional_var_e_ds1_given_er_es=float(max(cond,0)),
          min_cov_eigen=float(eig.min()),max_cov_eigen=float(eig.max()),
          heldout_cov_error_fro=float(np.linalg.norm(test_cov-sig)),
          covariance_type="DETERMINISTIC_FULL_MINUS_LOS_MODEL_DISCREPANCY",
          usable_as_sensor_R="NO_UNTIL_STOCHASTIC_NOISE_OR_CALIBRATED_RESIDUALS",
          conditional_fisher_additional="NOT_ESTIMATED_J1_OBSERVATION_MODEL_MISSING"))
    dump(out/"RA5_P2_ORIGINAL_INPUTS.csv",srcs)
    dump(out/"RA5_P2_REVISIT.csv",revisit)
    dump(out/"RA5_P2_ACF.csv",acf)
    dump(out/"RA5_P2_TWO_TAP_COV_IDENTITY.csv",idcheck)
    dump(out/"RA5_P2_LORO_CROSSCOV.csv",results)
    qa=dict(status="PASS_RETROSPECTIVE_RESIDUAL_DIAGNOSTIC",
       n_full_los_pose_pairs=len(allrows),n_timeline_case_rows=len(df),n_case=7,n_route=3,
       n_independent_environments=1,
       sha_control="7_7_P0_PASS",result_type="EXPLORATORY_MODEL_DISCREPANCY_COVARIANCE",
       covariance_spatial_field_time_identifiable=False,
       spatial_temporal_gate="BLOCKED_STATIC_H_SINGLE_REALIZATION",
       independent_noise_covariance_calibrated=False,
       new_raw_tap_info="CANDIDATE_NOT_YET_PHYSICAL_J_INFORMATION",
       online_hardware_tap_status="UNVERIFIED",
       downstream_RA5_3="MATH_AND_MATCHED_PRIOR_QA_ALLOWED_NOT_PHYSICS_CLAIM",
       downstream_RA5_4="CALIBRATED_FILTERING_BLOCKED",
       downstream_RA5_5="LATENT_STATE_PHYSICAL_CLAIM_BLOCKED",
       downstream_RA5_6="NEW_INDEPENDENT_SCENE_REQUIRED",
       independent_auditor=False,science_release=False,
       created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_P2_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_P2_FINAL "+json.dumps(qa),flush=True)
    print("RA5_P2_LORO "+json.dumps(results),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();main(a.input_dir,a.out)
