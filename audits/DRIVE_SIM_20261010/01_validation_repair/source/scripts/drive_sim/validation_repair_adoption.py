"""Step 7: minimal corrected-GSF replay, provenance and adoption evidence."""
import sys
from pathlib import Path
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
import validation_repair as V
from qclean_uwb.drivesim import experiment as E, sensors as S


def main():
    if not (V.OUT/"STEP7_PLAN.json").exists() or not (V.OUT/"STEP6_JOINT_EVALUATION.json").exists():raise ValueError("STAGE_ORDER_OR_PLAN")
    # Reconstruct the exact source used for stage2 from the sole known source edit.
    source=(ROOT/"scripts/drive_sim/validation_repair.py").read_text(encoding="utf-8")
    old=source.replace('def boot(values, median=False):','def boot(values):').replace('    samples=rng.choice(a,size=(2000,len(a)),replace=True)\n    means=np.median(samples,axis=1) if median else samples.mean(1)','    means=rng.choice(a,size=(2000,len(a)),replace=True).mean(1)')
    old=old.replace(',median_delta_seed_bootstrap_ci95=boot(delta,median=True)','').replace('["median_delta_seed_bootstrap_ci95"][1]<=0','["mean_delta_seed_bootstrap_ci95"][1]<=0')
    frozen=V.OUT/"STAGE2_EXECUTED_SOURCE.py.txt"
    frozen.write_text(old,encoding="utf-8",newline="\n")
    receipt=json.loads((V.OUT/"STAGE2_RECEIPT.json").read_text())
    expected=next(h for p,h in receipt["code_sha256"].items() if p.replace("\\", "/")=="scripts/drive_sim/validation_repair.py")
    if V.sha(frozen)!=expected:raise ValueError("STAGE2_SOURCE_RECONSTRUCTION_HASH_MISMATCH")
    V.write("SOURCE_CHANGE_RECEIPT.json",dict(stage2_source_sha256=expected,reconstructed_sha256=V.sha(frozen),current_sha256=V.sha(ROOT/"scripts/drive_sim/validation_repair.py"),
        change="after stage2: add median seed-bootstrap to implement planned median joint criterion; no stage2 numerical code changes",stage2_numerical_path_unchanged=True))
    data=V.load()
    manpath=ROOT/"results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z/results/S2/H_R2_aA_m0.manifest.json"
    manifest=json.loads(manpath.read_text());expected=manifest["outputs"][0]["sha256"];actual=V.sha(V.RAW/"H_R2_aA_m0.npy")
    if expected!=actual:raise ValueError("ORIGINAL_H_MANIFEST_MISMATCH")
    V.write("RAW_ORIGIN_CHECK.json",dict(original_manifest=str(manpath),manifest_sha256=V.sha(manpath),expected_H_sha256=expected,actual_H_sha256=actual,passed=True,
        timeline_geometry_max_abs_diff=data["max_geometry_diff"],limitation="provenance/timeline verification, not RF physics validation"))
    # Identify only canonical final result copies, not archived/snapshot duplicates.
    paths=list((ROOT/"results/DRIVE_SIM_20261007/SNOWBALL_RUNS/01a11582/final_B_20261007T1017Z/B_RESTART_20261007_01a115bd/S6").glob("results_y*.csv"))
    paths+=list((ROOT/"results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z/results/S6_routes").glob("results_*.csv"))
    impact=[]
    for p in paths:
        df=pd.read_csv(p);g=df[df["filter"]=="gsf"]
        impact.append(dict(path=str(p.relative_to(ROOT)),sha256=V.sha(p),total_rows=len(df),gsf_rows=len(g),affected_baselines=sorted(g.baseline.unique()),
            reason="historical GSF uses old reseed; actual numerical effect not assumed until paired replay"))
    # Original machinery exactly, but compare only corrected GSF and its EKF context.
    E.POS_PROCESS_STD=.01;E.FILTER_KINDS_COMPARED=("gsf",)
    store=np.load(V.RAW/"H_R2_aA_m0.npy",mmap_mode="r")
    worlds={p:E.make_world(ROOT/f"results/DRIVE_SIM_20261007/S1/routes/timeline_R2_T{'none' if p is None else '20'}.csv",store,data["freq"],0.,0.,p,route="R2",anchor="A") for p in (None,20.)}
    base=[b for b in E.BASELINES if b["name"] in ("range_s_P0","range_s_P1_T20")]
    runs,_=E.run_unit(worlds,data["lut"],sensor=S.SensorNoise(),mismatch_sigma=.16095229605409875,anchor_xyz=V.ANCHOR,robot_z=V.RZ,
        range_offset=data["meta"]["range_bias"]["mean_m"],snr_db=30.,snr_idx=0,drift_idx=0,seed=0,compare_filters=True,baselines=base)
    legacy=pd.read_csv(ROOT/impact[4]["path"]) if len(impact)>4 and "R2_aA_m0" in impact[4]["path"] else pd.read_csv(next(p for p in paths if p.name=="results_R2_aA_m0.csv"))
    comparisons=[]
    for r in runs:
        if r["error"]:raise ValueError("GSF_REPLAY_FAILED "+r["error"])
        oldrow=legacy[(legacy.seed==0)&(legacy.drift==0)&(legacy.snr_db==30)&(legacy["filter"]==r["filter"])&(legacy.baseline==r["baseline"])]
        if len(oldrow)!=1:raise ValueError("LEGACY_PAIR_MISSING_OR_DUPLICATE")
        oldrow=oldrow.iloc[0]
        comparisons.append(dict(baseline=r["baseline"],filter=r["filter"],seed=0,legacy={k:float(oldrow[k]) for k in ("heading_rmse_deg","pos_rmse_m","nees_mean")},new={k:r[k] for k in ("heading_rmse_deg","pos_rmse_m","nees_mean")},
            delta={k:r[k]-float(oldrow[k]) for k in ("heading_rmse_deg","pos_rmse_m","nees_mean")}))
    V.write("STEP7_GSF_IMPACT.json",V.clean(dict(impact=impact,recalculated=comparisons,regenerated_GSF_rows=2,scientific_PASS=False,
        interpretation="saved-input diagnostic; one seed and two baselines do not replace whole R1/routes GSF results")))
    # Targeted geometry unit check for the actual range derivative.
    x=np.array([7.,.3]);d=float(np.linalg.norm(np.r_[x,V.RZ]-V.ANCHOR));analytic=(x-np.array(V.ANCHOR[:2]))/d
    fd=[]
    for i in range(2):
        dx=np.eye(2)[i]*1e-6
        fd.append((np.linalg.norm(np.r_[x+dx,V.RZ]-V.ANCHOR)-np.linalg.norm(np.r_[x-dx,V.RZ]-V.ANCHOR))/2e-6)
    error=float(np.max(np.abs(analytic-fd)));assert error<1e-8
    ds,dt=S.true_increments(data["rows"])
    V.write("PROCESS_MODEL_LIMITS.json",dict(range_jacobian_fd_max_abs_error=error,
        wheel_exact="ds_odom noiseless = ds + eps_d * wheel_base * dtheta / 4; dtheta_odom noiseless = (dtheta+eps_d*ds/wheel_base)/(1+e_b)",
        legacy_approx="prediction uses ds_odom without eps_d-turn correction; odom update approximates wheelbase error and shares gyro increment noise",
        low_drift_max_ds_diameter_correction_m=float(np.max(np.abs(.002*.287*dt/4))),
        shared_gyro_cross_cov_legacy_omitted=True,whole_F02_causal_fraction="UNKNOWN; no matched shared-gyro/wheel replacement was adopted"))
    print("stage7 GSF replay COMPLETE",len(impact),"files identified")


if __name__=="__main__":main()
