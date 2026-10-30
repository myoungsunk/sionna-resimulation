#!/usr/bin/env python3
"""Fail-closed aggregation of THREE already-successful immutable GitHub Action evidences.
No physical source material, estimator fitting, original data or holdout mutation.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,pathlib,statistics
import numpy as np

EXPECT={
 "RA5_FIELD_TIME_QA.json":"PASS_SYNTHETIC_FIELD_TIME_GENERATOR_AND_REVISIT_IDENTIFIABILITY",
 "RA5_TAP_JACOBIAN_QA.json":"PASS_TAP_JACOBIAN_SELECTED_POSES",
 "RA5_TAP_QA.json":"PASS_ASSUMED_COMPLEX_CFR_MONTE_CARLO",
 "RA5_FFD_CONDITIONAL_QA.json":"PASS_SAME_SCENE_CONDITIONAL_INFORMATION_DIAGNOSTIC",
 "RA5_NEW_GEOMETRY_QA.json":"PASS_NEW_GEOMETRY_SYNTHETIC_STRESS_ONLY"}
def must(test,msg):
    if not test:raise RuntimeError(msg)
def checksum(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for data in iter(lambda:f.read(1024*1024),b""):h.update(data)
    return h.hexdigest()
def csvdata(path):
    with path.open(newline="") as f:return list(csv.DictReader(f))
def median(vals):
    return float(np.median(np.array(vals,dtype=float))) if vals else None

def main(args):
    root=pathlib.Path(args.root);out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    qas={};recs=[];hashlist={}
    for name,expected in EXPECT.items():
        files=list(root.rglob(name))
        required=2 if name=="RA5_TAP_QA.json" else 1
        must(len(files)==required,"ERR_EVIDENCE_COUNT "+name+":"+str(len(files)))
        arr=[]
        for p in files:
            obj=json.loads(p.read_text())
            must(obj.get("status")==expected,"ERR_STATUS "+str(p)+":"+str(obj.get("status")))
            arr.append(obj);hashlist[str(p.relative_to(root))]=checksum(p)
            recs.append(dict(filename=str(p.relative_to(root)),kind=name,status=obj["status"],sha256=checksum(p)))
        qas[name]=arr
    all_tap=qas["RA5_TAP_QA.json"]
    must(sum(x["n_cells"] for x in all_tap)==48 and sum(x["singular_R_cells"] for x in all_tap)==8,
         "ERR_ORIGINAL_FULL_H_48_CELL_SCOPE")
    cond=qas["RA5_FFD_CONDITIONAL_QA.json"][0]
    must(cond["n_cells"]==36 and cond["n_conditional_fisher_fullrank"]==36,"ERR_CONDITIONAL_CELLS")
    field=qas["RA5_FIELD_TIME_QA.json"][0]
    must(field["n_synthetic_scenarios"]==3 and field["n_independent_field_draws_per_arm"]==600,"ERR_FIELD_SCOPE")
    jac=qas["RA5_TAP_JACOBIAN_QA.json"][0]
    must(jac["n_analytic_fd_matched"]==6,"ERR_JAC_SOURCE_PARITY")
    novel=qas["RA5_NEW_GEOMETRY_QA.json"][0]
    must(novel["n_configurations"]==48 and novel["n_original_RT_calls"]==0,"ERR_NOVEL_SCOPE")
    rows0=list(root.rglob("RA5_FFD_SAME_SCENE_CONDITIONAL_INFO.csv"))
    must(len(rows0)==1,"ERR_CONDITIONAL_CSV")
    data=csvdata(rows0[0]);must(len(data)==36,"ERR_CONDITIONAL_CSV_COUNT")
    must(all(r["conditional_I_supported"]=="True" for r in data),"ERR_FISHER_SUBSET")
    by=[]
    for snr in (-5.,5.,20.):
        for jit in (0.,150.):
            x=[r for r in data if float(r["snr_db"])==snr and float(r["jitter_ps"])==jit]
            must(len(x)==6,"ERR_CONDITIONAL_STRATUM")
            by.append(dict(snr_db=snr,jitter_ps=jit,n_poses=6,
                median_abs_corr_s0_s1=median([abs(float(r["same_packet_correlation"])) for r in x]),
                median_extra_heading_data_FI=median([float(r["extra_heading_data_fisher"]) for r in x]),
                median_baseline_heading_data_FI=median([float(r["baseline_heading_data_fisher"]) for r in x]),
                min_extra_heading_data_FI=min(float(r["extra_heading_data_fisher"]) for r in x),
                max_basis_Fisher_rel=max(float(r["I_equivalence_relative"]) for r in x),
                caveat="LOCAL_DATA_ONLY_CONDITIONED_NO_NUISANCE_MARGINALIZATION"))
    with (out/"RA5_CONDITIONAL_BY_SNR.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(by[0]));w.writeheader();w.writerows(by)
    with (out/"RA5_EXECUTION_SOURCE_LEDGER.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(recs[0]));w.writeheader();w.writerows(recs)
    summary=dict(status="PASS_COMBINED_TECHNICAL_NO_RT_EVIDENCE",
      source_runs=[40986273213,40985784668,40986462306],
      n_original_archived_Full_H_cases=2,n_original_H_poses=4,
      source_noise_cells=48,source_noise_draws=24576,
      source_noise_singular_R=8,source_noise_tap_switch_cells=40,
      original_FFD_J_poses=6,max_FD_error=jac["max_fd_err_on_stable"],
      known_synthetic_field_scenarios=3,field_realizations_per_scenario=600,
      synthetic_time_observation_count=108000,
      same_scene_FFD_Fisher_cells=36,same_scene_Fisher_valid=36,
      same_scene_noise_draws=36*768,
      novel_synthetic_echo_configs=48,novel_synthetic_echo_draws=48*256,
      novel_synthetic_echo_tap_transitions=novel["n_echo_detector_tap_changes"],
      estimated_Fisher_is_raw_s_only=True,
      true_physical_environment_tests=0,
      RT_solver_calls=0,
      independent_physical_time_field_identification=False,
      hardware_available_raw_tap="NOT_VERIFIED",
      full_joint_range_likelihood="NOT_YET_VALIDATED",
      four_state_vs_five_state_filter="NOT_RUN",
      independent_new_physical_scenes=0,
      independent_auditor=False,science_release=False,
      recording_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      source_QA_checksums=hashlist)
    (out/"RA5_INTEGRATION_QA.json").write_text(json.dumps(summary,indent=2)+"\n")
    line=["# RA5 no-large-RT integrated execution summary (2026-10-30)","",
          "**Method/engineering self-review:** PASS. **Physics/hardware/generalization:** NOT ESTABLISHED.","",
          "- Archived original Full H and fixed source FFD never modified.",
          "- Original Full H noise: 48 conditions, 24,576 complex-noise draws; 8 singular full 3x3 R and 40 tap-switching cells.",
          "- SourceFFD LoS J0/J1 selected-pose analytic vs independent FD: 6/6 pass; max abs diff "+str(jac["max_fd_err_on_stable"])+".",
          "- Same-scene s0/s1 conditional information: 36/36 invertible polarization sub-blocks, exact full-covariance basis equivalence; NOT full r,s0,s1 filter proof.",
          "- MBVAR-INFO source math field-time: 3 scenarios x 600 independent fields x 60 samples, spatial revisit identity; synthetic only.",
          "- New predeclared 12x12 geometry and coherent delayed-echo stress: 48 configurations / "+str(48*256)+" noise realizations, "+str(novel["n_echo_detector_tap_changes"])+" clean tap transitions, **not** a physical RT scene.",
          "- Source runs: https://github.com/myoungsunk/sionna-resimulation/actions/runs/40986273213 ; https://github.com/myoungsunk/sionna-resimulation/actions/runs/40985784668 ; https://github.com/myoungsunk/sionna-resimulation/actions/runs/40986462306 .",
          "",
          "## Critical block",
          "The original FFD mean range is continuous, whereas raw first-edge range uses discrete tap index. Do not invert a singular empirical 3x3 covariance, silently replace R, or mix Jacobians and R from different scenes. Calibrated receiver/sensor likelihood and physical multipath J are absent.",
          "",
          "## Next",
          "A standalone conditional (s0,s1) simulation can be analysed now. Release-grade 3-component EKF, 4-vs-5-state, physics time drift and unseen physical scene generalization remain blocked pending independent calibrated measurement/RT and approvals. Existing Office is DEV, not new blind TEST.",
          ""]
    (out/"RA5_INTEGRATION_EXECUTIVE_KO.md").write_text("\n".join(line))
    print("RA5_AGGREGATE_FINAL "+json.dumps({k:v for k,v in summary.items() if k!="source_QA_checksums"}),flush=True)
    for rec in by:print("RA5_CONDITIONAL_SUMMARY "+json.dumps(rec),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--root",required=True);ap.add_argument("--out",required=True)
    main(ap.parse_args())
