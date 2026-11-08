#!/usr/bin/env python3
"""PALO motion/CIR reliability diagnostic. R2 frozen model, offline labels only.
Fail closed on provenance, pose pairing, observation parity, or non-finite science.
NO production selector, NO new RF simulation, NO independent environment.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, os, sys, time, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression

REPO = "myoungsunk/sionna-resimulation"
R2_SHA = "8894353b10f790746f32d8d82159213aad9c82a7"
H_SHA = "047cce2acb244ec2d7badc563345ccdd1f48613f"
ROOT = "research/POL_HEADING_RESEARCH_20261107"
GAP = "research/PALO_GAP_STUDY_20261107/results/trajectories"
CROOT = "results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
EXPECTED_H = {
    "H_R2_aB_m0.npy": "b3b4c61e23286b86c78b6e87f5b2995f2d79caa997c467".replace("2995","9b5358"), # checked again below
    "H_LoS_R2_aB_m0.npy": "811bdfb1b152839f85c6378faafc0f94619601416084a0995f2d79caa997c467",
}
# Source manifest's authoritative full-H SHA, never silently repair it:
EXPECTED_H["H_R2_aB_m0.npy"]="b3b4c61e23286b86c78b6e87f5b9b5358121cbde7717bae73e5650cc900b546c"
LEVELS = {"B0":0.0, "L0":0.01, "L1":0.05, "L2":0.2}
DEG = 180/np.pi
OUT = Path("outputs")
OUT.mkdir(parents=True,exist_ok=True)
AUDIT = []
def grab(sha,path,expected_sha=None,expected_size=None):
    url=f"https://raw.githubusercontent.com/{REPO}/{sha}/{path}"
    last=None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"PALO-science-audit"}),timeout=95) as response:
                blob=response.read()
            if blob.startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise RuntimeError(f"LFS_POINTER_NOT_MATERIALIZED:{path}")
            if expected_size is not None and len(blob)!=expected_size: raise RuntimeError(f"SIZE_MISMATCH {path} {len(blob)} vs {expected_size}")
            digest=hashlib.sha256(blob).hexdigest()
            if expected_sha is not None and digest!=expected_sha:
                raise RuntimeError(f"SHA_MISMATCH:{path}:{digest} expected:{expected_sha}")
            AUDIT.append({"ref":sha,"path":path,"sha256":digest,"bytes":len(blob)})
            return blob
        except Exception as e:
            last=e
            if "MISMATCH" in str(e) or "LFS_POINTER" in str(e): raise
            time.sleep(1+attempt)
    raise RuntimeError(f"DOWNLOAD_FAILED {path}: {last}")
def npz(sha,path):
    return {k:a[k].copy() for a in [np.load(io.BytesIO(grab(sha,path)),allow_pickle=False)] for k in a.files}
def wrap(a):return (a+np.pi)%(2*np.pi)-np.pi
def measure(v):return float(np.sqrt(np.mean(np.asarray(v)**2)))
def stat_auc(y,score):
    y=np.asarray(y,dtype=bool);score=np.asarray(score,dtype=float)
    if y.size<6 or sum(y)==0 or sum(y)==len(y) or not np.isfinite(score).all():return None
    return float(roc_auc_score(y,score))
def local_waveform(raw,freq):
    assert raw.ndim==4 and raw.shape[1:]==(257,2,2)
    h=raw[:,:,:,0]
    w=.5-.5*np.cos(2*np.pi*np.arange(257)/256)
    padded=np.zeros((len(h),1028,2),dtype=np.complex128)
    padded[:,:257,:]=h*w[None,:,None]
    cir=np.fft.ifft(padded,axis=1)*257
    mags=np.abs(cir)
    branch=mags.max(axis=1).argmax(axis=1)
    strongest=mags[np.arange(len(h))[:,:,None] if False else np.arange(len(h))[:,None],
                    np.arange(1028)[None,:],branch[:,None]]
    peak=strongest.max(axis=1)
    hits=strongest>=.3*peak[:,None]
    fp=hits.argmax(axis=1)
    pw=mags**2
    pfp=pw[np.arange(len(h)),fp,:]
    with np.errstate(invalid="ignore",divide="ignore"):
        s=(pfp[:,0]-pfp[:,1])/(pfp[:,0]+pfp[:,1])
    assert np.isfinite(s).all() and np.isfinite(pw).all()
    row=np.arange(len(h))[:,None]
    result={"fp_tap":fp.astype(float),"s_rebuilt":s}
    # Pre-register windows around the detected *first path*, not full CIR RMS delay spread.
    for before,after,tag in [(2,4,"narrow"),(4,8,"primary"),(8,16,"wide")]:
        offs=np.arange(-before,after+1)
        taps=fp[:,None]+offs[None,:]
        mask=(taps>=0)&(taps<1028)
        power=pw[row,np.clip(taps,0,1027),:]*mask[:,:,None]
        den=power.sum(axis=1)
        norm=power/np.maximum(den[:,None,:],1e-30)
        means=np.einsum("ntr,t->nr",norm,offs)
        spread=np.sqrt(np.maximum(0,np.einsum("ntr,ntr->nr",norm,(offs[None,:,None]-means[:,None,:])**2)))
        result[f"fp_spread_{tag}"] = spread.mean(axis=1)
        result[f"fp_spread_diff_{tag}"] = np.abs(spread[:,0]-spread[:,1])
        if tag=="primary":
            p0=norm[:,:,0];p1=norm[:,:,1];m=.5*(p0+p1)
            jsd=.5*np.sum(np.where(p0>0,p0*np.log(np.maximum(p0,1e-30)/np.maximum(m,1e-30)),0)+
                         np.where(p1>0,p1*np.log(np.maximum(p1,1e-30)/np.maximum(m,1e-30)),0),axis=1)
            result["fp_jsd_primary"]=np.maximum(jsd,0)
            result["fp_late_fraction"]=power[:,offs>=3,:].sum(axis=(1,2))/np.maximum(power.sum(axis=(1,2)),1e-30)
            result["fp_window_complete"]=mask.all(axis=1)
    for k in [-8,-4,-2,-1,1,2,4,8]:
        taps=np.clip(fp+k,0,1027)
        p=pw[np.arange(len(h)),taps,:]
        ss=(p[:,0]-p[:,1])/np.maximum(p.sum(axis=1),1e-30)
        result[f"delta_s_tap_{k:+d}"]=ss-s
    result["delta_s_tap_absmax2"]=np.maximum(np.abs(result["delta_s_tap_-2"]),np.abs(result["delta_s_tap_+2"]))
    result["rx_early_energy_logratio"]=np.log(np.maximum(pfp[:,0],1e-30)/np.maximum(pfp[:,1],1e-30))
    return pd.DataFrame(result)
def run():
    rawfull=npz(R2_SHA,f"{ROOT}/inputs/original_run/verified_inputs/R2_aB_m0_full_seed0_ONE_STEP.npz")
    rawlos=npz(R2_SHA,f"{ROOT}/inputs/original_run/verified_inputs/R2_aB_m0_los_seed0_ONE_STEP.npz")
    t=np.asarray(rawfull["t_s"],float)
    pos=np.asarray(rawfull["pose_id"],int)
    truth=np.asarray(rawfull["truth_for_offline_scoring_only"],float)
    assert t.shape==(979,) and pos.shape==(979,) and truth.shape==(979,3)
    assert np.all(np.diff(t)>0) and np.array_equal(pos,np.asarray(rawlos["pose_id"],int))
    assert np.max(np.abs(truth-rawlos["truth_for_offline_scoring_only"]))<1e-12
    bias_rows=[]; reliability=[]; packets=[]; arrays={}
    for lv,truebias in LEVELS.items():
        ctl=npz(R2_SHA,f"{ROOT}/experiments/POL_FGO_CORR_20261106_v1/outputs/controls_full_{lv}.npz")
        assert ctl["dtheta_gyro"].shape==(979,) and ctl["ds_odom"].shape==(979,) and ctl["dt_s"].shape==(979,)
        data={donor:npz(R2_SHA,f"{GAP}/baseline_{lv}_{donor}.npz") for donor in ("dr","s4")}
        for donor,a in data.items():
            assert a["X"].shape==(979,4) and a["P"].shape==(979,4,4)
            assert a["prior_X"].shape==(979,4) and a["candidate_X"].shape==(979,4)
            assert np.max(np.abs(a["truth"]-truth))<1e-9
            assert np.max(np.abs(a["t"]-t))<1e-9
            assert np.linalg.eigvalsh(a["P"]).min()>0
            err=wrap(a["X"][:,2]-truth[:,2])*DEG
            sig=np.sqrt(a["P"][:,2,2])*DEG
            espre=wrap(a["prior_X"][:,2]-truth[:,2])*DEG
            espost=wrap(a["candidate_X"][:,2]-truth[:,2])*DEG
            xy_pre=np.linalg.norm(a["prior_X"][:,:2]-truth[:,:2],axis=1)
            xy_post=np.linalg.norm(a["candidate_X"][:,:2]-truth[:,:2],axis=1)
            idx=t>=40
            accepted=np.asarray(a["accepted"],bool)
            gap=np.zeros(len(t));since=0.
            for k in range(1,len(t)):
                since=0 if accepted[k-1] else since+(t[k]-t[k-1])
                gap[k]=since
            for start,end in [(40,100),(100,120),(140,200)]:
                sel=(t>=start)&(t<end)
                q=(err[sel]/sig[sel])**2
                reliability.append(dict(level=lv,donor=donor,window=f"{start}-{end}",n=int(sel.sum()),
                    heading_rmse_deg=measure(err[sel]),head95=float(np.mean(q<=3.841458820694124)),
                    heading_nees=float(np.mean(q)),posterior_sigma_rms_deg=measure(sig[sel]),
                    head_error_gt1_frac=float(np.mean(np.abs(err[sel])>1)),
                    head_error_gt2_frac=float(np.mean(np.abs(err[sel])>2)),
                    sigma_vs_abs_error_spearman=float(pd.Series(sig[sel]).corr(pd.Series(np.abs(err[sel])),method="spearman")) if np.ptp(sig[sel])>1e-10 else None,
                    sigma_auc_error_gt2=stat_auc(np.abs(err[sel])>2,sig[sel])))
            mask=t>=40
            for k in np.where(mask)[0]:
                feat=np.asarray(a["features"][k],float)
                packets.append(dict(k=int(k),t=float(t[k]),pose_id=int(pos[k]),level=lv,donor=donor,
                    nis=float(a["nis"][k]),gate_eligible=bool(a["nis"][k]<=6.6348966010212145),
                    psi_sigma_deg=float(np.sqrt(a["prior_P"][k,2,2])*DEG),
                    bg_sigma_deg_s=float(np.sqrt(a["prior_P"][k,3,3])*DEG),
                    bg_est_deg_s=float(a["prior_X"][k,3]*DEG),
                    dr_since_last_accept_s=float(gap[k]),
                    abs_Hpsi=float(feat[2]),innovation_abs=float(feat[1]),
                    abs_heading_correction_deg=float(abs(wrap(a["candidate_X"][k,2]-a["prior_X"][k,2]))*DEG),
                    signed_heading_correction_deg=float(wrap(a["candidate_X"][k,2]-a["prior_X"][k,2])*DEG),
                    ref_prior_abs_heading_error_deg=float(abs(espre[k])),
                    ref_hed_gain_deg=float(abs(espre[k])-abs(espost[k])),
                    ref_head_harm_gt05=bool(abs(espost[k])-abs(espre[k])>.5),
                    ref_xy_harm_gt001=bool(xy_post[k]-xy_pre[k]>.01),
                    ref_head_benefit=bool(abs(espost[k])<abs(espre[k])),
                    rf_selected=bool(accepted[k])))
            if donor=="s4":
                sel=t>=40
                bval=a["X"][sel,3]*DEG
                bias_rows.append(dict(level=lv,true_bias_deg_s=truebias,
                    bias_est_mean_deg_s=float(np.mean(bval)),bias_est_mae_deg_s=float(np.mean(np.abs(bval-truebias))),
                    bias_est_rmse_deg_s=measure(bval-truebias),
                    bias_sigma_rms_deg_s=float(np.sqrt(np.mean(a["P"][sel,3,3]))*DEG),
                    bias_95_coverage=float(np.mean((bval-truebias)**2<=3.841458820694124*a["P"][sel,3,3]*DEG**2))))
        # True yaw increment only for retrospective reference, not an independent sensor.
        gyro=np.asarray(ctl["dtheta_gyro"],float)
        dt=np.asarray(ctl["dt_s"],float)
        assert np.all(dt[1:]>0)
        true_dyaw=wrap(np.diff(truth[:,2]))
        apparent_gyro_error=(gyro[1:]-true_dyaw)/dt[1:]*DEG
        # A zero-rate bias update needs TRUE stationary segments (no translation and no rotation).
        spatial=np.linalg.norm(np.diff(truth[:,:2],axis=0),axis=1)
        true_stopped=(spatial<.002)&(np.abs(true_dyaw)<np.deg2rad(.1))
        command_candidate=(np.abs(ctl["ds_odom"][1:])<.002)&(np.abs(gyro[1:])<np.deg2rad(.1))
        def windows_at_least(mask,n=10):
            runs=[];i=0
            while i<len(mask):
                if not mask[i]:i+=1;continue
                j=i
                while j<len(mask) and mask[j]:j+=1
                if j-i>=n:runs.append((i,j))
                i=j
            return runs
        runs=windows_at_least(true_stopped,10)
        bias_rows[-1].update(gyro_vs_true_mean_deg_s=float(np.mean(apparent_gyro_error)),
            gyro_vs_true_std_deg_s=float(np.std(apparent_gyro_error)),
            gyro_vs_true_rmse_deg_s=measure(apparent_gyro_error-truebias),
            offline_stationary_samples=int(true_stopped.sum()),online_stop_candidate_samples=int(command_candidate.sum()),
            certified_stationary_windows_2s=len(runs),
            zero_rate_bias_est_deg_s=(float(np.mean(np.concatenate([gyro[1:][i:j]/dt[1:][i:j]*DEG for i,j in runs]))) if runs else None),
            encoder_imu_consistency_status="BLOCKED: independent left/right encoder increments absent",
            lidar_rotation_status="BLOCKED: raw LaserScan or scan-to-scan rotations absent")
        arrays[lv]=data
    pd.DataFrame(bias_rows).to_csv(OUT/"motion_bias_stationarity.csv",index=False)
    pd.DataFrame(reliability).to_csv(OUT/"motion_risk_calibration.csv",index=False)
    df=pd.DataFrame(packets)
    # Pair to the pre-existing, NOISE-FREE source H: never treat the clean LoS as online input.
    cir_status={"status":"NOT_RUN"}
    try:
        samples=json.loads(grab(H_SHA,f"{CROOT}/R2_aB_m0/SAMPLES.json",expected_sha="35af279692a15dc429263f88cfbb4db949c1260cb7cf9d9e0c292172a7505b0e"))
        refpos=np.asarray([[samples[i]["x"],samples[i]["y"],np.deg2rad(samples[i]["yaw_body_deg"])] for i in pos])
        dev_xy=float(np.max(np.abs(refpos[:,:2]-truth[:,:2])))
        dev_head=float(np.max(np.abs(wrap(refpos[:,2]-truth[:,2]))*DEG))
        if dev_xy>.002 or dev_head>.05:
            raise RuntimeError(f"POSE_PAIRING_FAIL:max_pos={dev_xy},max_yawdeg={dev_head}")
        fbuf=grab(H_SHA,f"{CROOT}/FULL_RF/H_R2_aB_m0.npy",expected_sha=EXPECTED_H["H_R2_aB_m0.npy"],expected_size=21431872)
        lbuf=grab(H_SHA,f"{CROOT}/H_LoS_R2_aB_m0.npy",expected_sha=EXPECTED_H["H_LoS_R2_aB_m0.npy"],expected_size=21431872)
        freqs=np.load(io.BytesIO(grab(H_SHA,f"{CROOT}/freqs_hz.npy")),allow_pickle=False)
        fH=np.load(io.BytesIO(fbuf),allow_pickle=False)
        lH=np.load(io.BytesIO(lbuf),allow_pickle=False)
        assert fH.shape==lH.shape==(1303,257,2,2)
        assert freqs.shape==(257,) and np.max(np.abs(np.diff(freqs)-np.diff(freqs)[0]))<1e-3
        f=local_waveform(fH[pos],freqs)
        los=local_waveform(lH[pos],freqs)
        assert np.isfinite(f.select_dtypes(include=[np.number]).to_numpy()).all()
        joined=f.add_prefix("full_")
        joined["oracle_delta_s_full_minus_los"]=rawfull["z_s"]-rawlos["z_s"]
        joined["oracle_delta_s_rebuilt"]=f.s_rebuilt-los.s_rebuilt
        joined["oracle_fp_spread_los_primary"]=los.fp_spread_primary
        joined["oracle_fp_spread_full_minus_los"]=f.fp_spread_primary-los.fp_spread_primary
        # Reconstruction parity is not forced to zero: archived H is noise-free; input z has frozen receiver processing/noise.
        cir_status=dict(status="SOURCE_SHA_AND_POSE_PAIR_PASS",source_kind="NOISE_FREE_SIONNA_FREQUENCY_RESPONSE",
           matched_frames=len(pos),max_pose_error_m=dev_xy,max_yaw_error_deg=dev_head,
           full_vs_frozen_s_rms=measure(f.s_rebuilt.to_numpy()-rawfull["z_s"]),
           los_vs_frozen_s_rms=measure(los.s_rebuilt.to_numpy()-rawlos["z_s"]),
           correlation_full=float(np.corrcoef(f.s_rebuilt.to_numpy(),rawfull["z_s"])[0,1]),
           primary_window="kfp-4..kfp+8 inclusive; power weighted local second central moment",
           wide_window="kfp-8..kfp+16 inclusive",
           first_path_method="Hann257 / zero pad1028 / IFFT*257 / strongest RX / 30pct leading edge")
        for k in ["fp_spread_primary","fp_spread_diff_primary","fp_jsd_primary","fp_late_fraction",
                  "delta_s_tap_absmax2","delta_s_tap_+2","delta_s_tap_-2","fp_tap",
                  "fp_spread_narrow","fp_spread_wide","rx_early_energy_logratio"]:
            df[k]=joined["full_"+k].to_numpy()[df.k.to_numpy(dtype=int)-200]
        df["oracle_delta_s_full_minus_los"]=joined["oracle_delta_s_full_minus_los"].to_numpy()[df.k.to_numpy(dtype=int)-200]
        df["oracle_delta_s_rebuilt"]=joined["oracle_delta_s_rebuilt"].to_numpy()[df.k.to_numpy(dtype=int)-200]
        df["abs_oracle_delta_s"]=np.abs(df["oracle_delta_s_full_minus_los"])
        df["abs_delta_s_temporal"]=np.abs(np.r_[0,np.diff(rawfull["z_s"])])[df.k.to_numpy(dtype=int)]
        df["abs_delta_s_temporal_residual"]=np.abs(
            np.r_[0,np.diff(rawfull["z_s"])]-np.r_[0,np.diff(los.s_rebuilt.to_numpy())])[df.k.to_numpy(dtype=int)]
        # This last temporal residual relies on oracle LoS and must NOT be included in online models.
    except Exception as e:
        cir_status={"status":"BLOCKED_CIR_PAIRING_OR_PAYLOAD","error":str(e)[:1000]}
    (OUT/"CIR_AVAILABILITY.json").write_text(json.dumps(cir_status,indent=2,allow_nan=False))
    # audit predictivity without passing offline truth/LoS/label into online features.
    features=["psi_sigma_deg","bg_sigma_deg_s","bg_est_deg_s","dr_since_last_accept_s",
              "abs_Hpsi","innovation_abs","abs_heading_correction_deg","signed_heading_correction_deg"]
    if cir_status["status"]=="SOURCE_SHA_AND_POSE_PAIR_PASS":
        features+=["fp_spread_primary","fp_spread_diff_primary","fp_jsd_primary","fp_late_fraction",
                   "delta_s_tap_absmax2","fp_spread_narrow","fp_spread_wide","abs_delta_s_temporal"]
    assoc=[]
    for (lv,donor),part in df.groupby(["level","donor"],sort=True):
        eligible=part[part.gate_eligible]
        for name in features+ (["abs_oracle_delta_s"] if "abs_oracle_delta_s" in df else []):
            for lab in ["ref_head_harm_gt05","ref_xy_harm_gt001","ref_head_benefit"]:
                assoc.append(dict(level=lv,donor=donor,feature=name,offline_only=(name=="abs_oracle_delta_s"),
                                  target=lab,n=len(eligible),positive=int(eligible[lab].sum()),
                                  auc_large_score=stat_auc(eligible[lab],eligible[name])))
    pd.DataFrame(assoc).to_csv(OUT/"feature_associations.csv",index=False)
    df.to_csv(OUT/"matched_motion_cir_frames.csv.gz",index=False,compression={"method":"gzip","compresslevel":6,"mtime":0})
    model_rows=[]
    if cir_status["status"]=="SOURCE_SHA_AND_POSE_PAIR_PASS":
        # Development-only time holdout; all levels and priors share time blocks.
        fit=df[(df.t>=40)&(df.t<100)&df.gate_eligible]
        cal=df[(df.t>=100)&(df.t<120)&df.gate_eligible]
        test=df[(df.t>=140)&df.gate_eligible]
        groups={"MOTION":["psi_sigma_deg","bg_sigma_deg_s","bg_est_deg_s","dr_since_last_accept_s"],
                "MOTION_PLUS_SLOPE":["psi_sigma_deg","bg_sigma_deg_s","bg_est_deg_s","abs_Hpsi","innovation_abs","abs_heading_correction_deg"],
                "MOTION_SLOPE_FP":["psi_sigma_deg","bg_sigma_deg_s","bg_est_deg_s","abs_Hpsi","innovation_abs","abs_heading_correction_deg",
                                    "fp_spread_primary","fp_spread_diff_primary","fp_jsd_primary","fp_late_fraction","delta_s_tap_absmax2","abs_delta_s_temporal"]}
        for name,xx in groups.items():
            try:
                pipe=make_pipeline(SimpleImputer(strategy="median"),StandardScaler(),
                    LogisticRegression(C=.3,max_iter=1600,random_state=20261108))
                pipe.fit(fit[xx],fit.ref_head_harm_gt05.astype(int))
                pred=pipe.predict_proba(test[xx])[:,1]
                predcal=pipe.predict_proba(cal[xx])[:,1]
                th=float(np.quantile(predcal,.30))
                for donor in ("dr","s4"):
                    for lv in LEVELS:
                        m=(test.donor==donor)&(test.level==lv)
                        z=test.loc[m]
                        prob=pred[np.where(m)[0]]
                        take=prob<=th
                        model_rows.append(dict(model=name,donor=donor,level=lv,accepted=int(take.sum()),eligible=len(z),
                            accepted_fraction=float(take.mean()) if len(take) else None,
                            risk_all=float(z.ref_head_harm_gt05.mean()),risk_accepted=float(z.ref_head_harm_gt05.to_numpy()[take].mean()) if take.any() else None,
                            h_safety_auc=stat_auc(z.ref_head_harm_gt05,prob),
                            heading_candidate_abs_gain_sum_deg=float(z.ref_hed_gain_deg.to_numpy()[take].sum()),
                            test_robustness="SAME_R2_ROUTE_TIME_HOLDOUT; NO_CLOSED_LOOP",
                            calibration_threshold=th))
            except Exception as e:
                model_rows.append(dict(model=name,status="BLOCKED",error=str(e)[:500]))
    pd.DataFrame(model_rows).to_csv(OUT/"development_risk_guards.csv",index=False)
    summary=dict(status="COMPLETE_R2_ANALYSIS_CIR_"+cir_status["status"],cohort="SIMULATED_R2_ANCHORB_MOUNT0_SEED0",
        evaluated_frames=979,levels=list(LEVELS),total_prior_rows=len(df),
        independent_left_right_encoder="NOT_IN_INPUT",raw_lidar_scans="NOT_IN_INPUT",
        online_zero_rate_bias="ONLY_IF_VERIFIED_STATIONARY; NOT_PERFORMED_ON_MOVING_SAMPLES",
        derived_first_path="NOISE_FREE_RAW_H_PROXY; HARDWARE_AVAILABILITY_UNVERIFIED",
        risks="NOT_A_PRODUCTION_SELECTOR; TIME_HELD_R2_ONLY; NO_CROSS_ROUTE_GENERALIZATION",
        cir=cir_status,motion=bias_rows)
    (OUT/"SUMMARY.json").write_text(json.dumps(summary,indent=2,allow_nan=False))
    (OUT/"INPUT_SHA256.json").write_text(json.dumps(AUDIT,indent=2))
    manifest={p.name:{"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size}
              for p in sorted(OUT.iterdir()) if p.is_file()}
    (OUT/"OUTPUT_SHA256.json").write_text(json.dumps(manifest,indent=2))
    print("PALO_MOTION_CIR_RESULTS "+json.dumps({"status":summary["status"],"frames":979,
        "prior_rows":len(df),"cir":cir_status,
        "stationary":[{"level":r["level"],"windows":r["certified_stationary_windows_2s"],
                         "S4_bias_mae_deg_s":r["bias_est_mae_deg_s"]} for r in bias_rows],
        "model_rows":len(model_rows)},default=str),flush=True)
def publish():
    import base64
    token=os.environ.get("GITHUB_TOKEN")
    branch=os.environ.get("TARGET_BRANCH")
    if not token or not branch:return print("PUBLISH_SKIPPED_NO_TOKEN_OR_BRANCH")
    api=f"https://api.github.com/repos/{REPO}"
    def req(path,method="GET",payload=None):
        data=None if payload is None else json.dumps(payload).encode()
        h={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json",
           "X-GitHub-Api-Version":"2022-11-28","User-Agent":"palo-science"}
        if data:h["Content-Type"]="application/json"
        with urllib.request.urlopen(urllib.request.Request(api+path,data=data,headers=h,method=method),timeout=90) as r:
            return json.load(r)
    refinfo=req("/git/ref/heads/"+branch.replace("/","%2F"))
    parent=refinfo["object"]["sha"]
    source_sha=os.environ.get("GITHUB_SHA")
    if parent!=source_sha:raise RuntimeError(f"CONCURRENT_REF_CHANGE:{parent}!={source_sha}")
    base=req("/git/commits/"+parent)
    run=os.environ.get("GITHUB_RUN_ID","local")
    prefix=f"research/PALO_MOTION_CIR_RISK_20261108/runs/{run}"
    tree=[]
    for file in sorted(OUT.iterdir()):
        if not file.is_file():continue
        data=file.read_bytes()
        blob=req("/git/blobs",method="POST",payload={"content":base64.b64encode(data).decode(),"encoding":"base64"})
        tree.append({"path":f"{prefix}/{file.name}","mode":"100644","type":"blob","sha":blob["sha"]})
    newtree=req("/git/trees",method="POST",payload={"base_tree":base["tree"]["sha"],"tree":tree})
    commit=req("/git/commits",method="POST",payload={"message":"PALO: publish source-verified R2 motion/CIR risk diagnostics; missing raw channels explicitly blocked",
                                                       "tree":newtree["sha"],"parents":[parent]})
    req("/git/refs/heads/"+branch.replace("/","%2F"),method="PATCH",payload={"sha":commit["sha"],"force":False})
    print("PUBLISHED_COMMIT",commit["sha"],"files",len(tree),flush=True)
if __name__=="__main__":
    try:
        run()
        publish()
    except Exception as e:
        (OUT/"FAILED.json").write_text(json.dumps({"error":repr(e)},indent=2))
        raise
