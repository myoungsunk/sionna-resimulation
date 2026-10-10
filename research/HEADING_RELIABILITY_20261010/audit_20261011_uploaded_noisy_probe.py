#!/usr/bin/env python3
"""Independent provenance and quantitative scope audit for uploaded noisy probe data.
Reads small published CSV/JSON and source only. Does NOT simulate or tune a filter.
"""
from __future__ import annotations
import argparse, json, math, hashlib
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"results/DRIVE_SIM_NOISY_PROBE_20261010/RUN_01a125b3"
W=BASE/"SUMMARY_CURRENT"
F=BASE/"SUMMARY_FINAL"
H=BASE/"HARNESS"
EXPECTED={
    "old7":{"R2_aA_m0","R2_aB_m0","R2_aA_m45","R4_aA_m0","R4_aB_m0","R5_aA_m0","R5_aB_m0"},
    "new5":{"R2_aB_m45","R4_aA_m45","R4_aB_m45","R5_aA_m45","R5_aB_m45"}
}

def readj(p):return json.loads(p.read_text(encoding="utf-8-sig"))
def metrics(a):
    return dict(count=int(len(a)),mean=float(a.mean()),rms=float(np.sqrt(np.mean(np.asarray(a,float)**2))))
def paired_cluster_gate():
    df=pd.read_csv(W/"FP_CLUSTER_RATIO_existing7.csv")
    keys=["case","station","pose_id"];assert df.duplicated(keys+["mode"]).sum()==0
    a=df[df["mode"]=="full"].set_index(keys).sort_index()
    b=df[df["mode"]=="los"].set_index(keys).sort_index()
    assert a.index.equals(b.index), "Full/LoS first cluster join mismatch"
    assert len(a)==507 and len(b)==507, len(a)
    gate_widths={}
    for ns,expected in [(2,5),(4,9),(8,17)]:
        wn="window_"+str(ns)+"_tap_"
        a_len=(a[wn+"end_exclusive"]-a[wn+"start"]).to_numpy()
        b_len=(b[wn+"end_exclusive"]-b[wn+"start"]).to_numpy()
        assert np.all(a_len==expected) and np.all(b_len==expected)
        gate_widths[str(ns)]={"n_taps":expected,"prior_analysis_expected_taps":int(ns*2),
                               "different_from_prior_fixed_window":expected!=int(ns*2)}
    rec=[]
    for ns in (2,4,8):
        ef=a["s_W_"+str(ns)]-b["s_W_"+str(ns)]
        fp=a["s_FP"]-b["s_FP"]
        st=dict(window_ns=ns,n_matched_poses=len(a),
                fp_rms=float(np.sqrt(np.mean(fp**2))),
                cluster_rms=float(np.sqrt(np.mean(ef**2))),
                pearson_abs_s_mismatch=float(abs(fp).corr(abs(ef))),
                fp_small_cluster_large_fraction=float(np.mean((abs(fp)<.05)&(abs(ef)>.1))),
                abs_cluster_minus_fp_measured_median=float(abs(a["s_W_"+str(ns)]-a.s_FP).median()))
        rec.append(st)
    return df, pd.DataFrame(rec), gate_widths

def run(args):
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    reports={}
    main=readj(F/"FINAL_CONTROL_SUMMARY_CURRENT.json")
    final=readj(F/"NATIVE_FULL_EFFECTIVE_STATUS_FREQUENCY.json")
    los=readj(W/"NATIVE_LOS_STATUS.json")
    matrix=readj(W/"MOUNT_CASE_MATRIX.json")
    status=readj(F/"BODY_ADDITIONAL_V2_STATUS.json")
    independent=readj(F/"ADDITIONAL_INDEPENDENT_CHECK.json")
    cov=readj(W/"RECEIVER_COV_STATUS_existing7.json")
    plan=readj(W/"PLAN.json")
    assert len(matrix)==12 and len({c["case"] for c in matrix})==12
    oldset=EXPECTED["old7"]; newset=EXPECTED["new5"]
    assert {c["case"] for c in matrix}==oldset|newset
    assert {c["case"] for c in final["cases"]}==newset
    assert {c["case"] for c in los["cases"]}==newset
    assert all(len(x["H_sha256"])==64 for x in final["cases"])
    assert all(len(x["H_sha256"])==64 for x in los["cases"])
    assert all(len(x["full_sha256"])==64 for x in matrix)
    # Crucial: inherited 12 legacy Method-B H exists; 5 newly generated native H != demonstrated parity to them.
    assert all(x["full_status"]=="LEGACY_METHOD_B_PRESENT_HASH_VERIFIED" for x in matrix)
    reports["RF_PROVENANCE"]={
      "legacy_full_method_B_H_cases":12,
      "legacy_full_h_sha_verified_claim":True,
      "native_full_new_H_cases":len(final["cases"]),
      "native_los_new_cases":len(los["cases"]),
      "native_full_legacy_equivalence_gate":"NOT_VERIFIED",
      "paired_12_physical_solver_equivalence":"NOT_VERIFIED",
      "native_full_H_SHA256":{x["case"]:x["H_sha256"] for x in final["cases"]},
      "native_los_H_SHA256":{x["case"]:x["H_sha256"] for x in los["cases"]},
      "source":str(F/"NATIVE_FULL_EFFECTIVE_STATUS_FREQUENCY.json")}
    assert main["rows"]==53280 and main["failed_runs"]==0 and main["duplicate_keys"]==0
    assert sum(main["prior_kind_rows"].values())==main["rows"]
    assert status["runs"]==47160 and status["tasks"]==7860 and status["failed"]==0
    assert independent["passed"] and independent["arm_traces"]==47160 and independent["covariance_stage_samples"]==4008600 and independent["total_violation_count"]==0
    reports["TRACE_MATH"]={"all_rows":main["rows"],"new_trace_runs":status["runs"],
         "independent_replayed_covariance_steps":independent["covariance_stage_samples"],
         "equation_violation_count":independent["total_violation_count"],
         "scientific_pass":bool(main["scientific_PASS"]),
         "scope":"Saved truth-trajectory EKF algebra validation, not statistical covariance consistency"}
    a=pd.read_csv(F/"FINAL_SEED_PRIOR_KIND_METRICS.csv")
    keys=["case","drift","snr","arm","seed","prior_kind"]
    assert a.duplicated(keys).sum()==0, "Duplicate seed-level results"
    assert set(a.case)==oldset|newset and set(a.arm)==set("ABCD")|{"G1","G2"}
    assert set(a.prior_kind)==set(main["prior_kind_rows"])
    rec=[]
    for (prior,snr,arm),g in a.groupby(["prior_kind","snr","arm"]):
        rec.append(dict(prior_kind=prior,snr=int(snr),arm=arm,n_seed_units=len(g),
            station_total=int(g.stations.sum()),
            heading_rmse_seed_mean=float(g.heading_endpoint_rmse_deg.mean()),
            position_rmse_seed_mean=float(g.position_endpoint_rmse_m.mean()),
            nees_seed_mean=float(g.nees_pose_df3.mean()),
            pose_coverage_seed_mean=float(g.pose_coverage95.mean())))
    summary_seed=pd.DataFrame(rec)
    assert len(summary_seed)==36
    expect=[x for x in main["descriptive_only"] if x["prior_kind"]=="LEGACY_SAVED_POST_ODOM" and x["snr"]==30]
    for q in expect:
        g=summary_seed[(summary_seed.prior_kind==q["prior_kind"])&(summary_seed.snr==30)&(summary_seed.arm==q["arm"])]
        assert len(g)==1
        err=abs(float(g.heading_rmse_seed_mean.iloc[0])-q["heading_endpoint_rmse_deg_mean"])
        assert err<1e-10,(q["arm"],err)
    summary_seed.to_csv(out/"INDEPENDENT_SEED_PRIOR_RECAP.csv",index=False)
    reports["SEED_RESULTS"]={"n_seed_group_rows":len(a),"seed_ids":sorted(map(int,a.seed.unique())),
                             "distinct_causal_physical_environments":1,
                             "all_prior_kind_groups_reconciled":True,
                             "warning":"Endpoint after fixed truth stop/turn, not entire-route EKF"}
    assert cov["station_case_groups"]==169
    assert cov["calibrated_groups"]+cov["insufficient_groups"]==169
    reports["COVARIANCE"]={"eligible_station_groups":169,
          "spatial_estimated":cov["calibrated_groups"],
          "insufficient_sites":cov["insufficient_groups"],
          "cross_time_covariance_verified":False,
          "model_applied_to_estimator":False,
          "calibrated_site_point_probability":False}
    df,cv,gate_widths=paired_cluster_gate()
    cv.to_csv(out/"FIRST_CLUSTER_S_MATCHED_VALIDATION.csv",index=False)
    reports["FIRST_CLUSTER"]={"total_rows":len(df),"full_los_matched":507,
          "actual_gate_taps":gate_widths,
          "first_cluster_hardware_available":"UNKNOWN",
          "FP_measurement_model_replaced_by_cluster_model":False,
          "physics":"Difference between full and native LoS is a channel/observer mismatch label, not direct measurement of Stokes DoP"}
    # Explicit code-level checks for what was and wasn't implemented.
    control=(H/"body_controls.py").read_text()
    covcode=(H/"receiver_existing7.py").read_text()
    srcs=(H/"body_controls.py").read_text()
    assert "true[:,2]=V.wrap(true[:,2]+yaws)" in control and "ds=np.zeros(n)" in control
    assert "if arm=='C' and m=='s' else obs" in control
    assert "arm in ['G1','G2']" in control
    assert "enabled=obs_i>=0" in control
    assert "estimator_applied=np.array(False)" in covcode
    assert "np.cov" in covcode
    reports["PROTOCOL_MISMATCHES"]={
      "body_truth_uses_predeclared_yaw_and_constant_true_xy":True,
      "physical_acceleration_and_stop_slip_shift_truth_xy":"NOT_IMPLEMENTED",
      "G1_G2_reduce_both_range_and_s_packets":True,
      "isolate_incremental_s_information_G1_G2":"INVALID_AS_RUN",
      "C_uses_full_range_native_los_s_only":True,
      "F_or_H_joint_site_point_inference":"NOT_IMPLEMENTED",
      "post_probe_continuous_EKF_drive_resume":"NOT_RUN",
      "latest_09_spec_fully_complete":False}
    # Independently audit parity of s_FP values versus stored first-cluster actual energies when available.
    good=(df.P1_FP+df.P2_FP)>0
    parity=float(np.max(abs(df.loc[good,"s_FP"]-(df.loc[good,"P1_FP"]-df.loc[good,"P2_FP"])/(df.loc[good,"P1_FP"]+df.loc[good,"P2_FP"]))))
    assert parity<1e-10
    reports["FIRST_PATH_FORMULA_PARITY"]={"max_abs_error":parity}
    result={
       "result":"AUDIT_EXECUTED_WITH_UNRESOLVED_REQUIREMENTS",
       "origin":"codex/probe-mixture-reliability-20261010",
       "test_type":"Independent small published CSV/JSON and harness source reanalysis. No new Sionna or sensor-v2 filter execution.",
       "checks":reports,
       "next_step":"Implement paired G1/G2 s-only ablation, sequential pose-measurement cross-time covariance and separate no-truth-leak q_site/q_i posterior; compare actual bounded T10 driving continuation then new dynamic stop model.",
       "original_scientific_pass":False}
    (out/"AUDIT.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
    with (out/"RESULTS_KO.md").open("w",encoding="utf-8") as q:
        q.write("# 2026-10-11 업로드 신규 Sensor-v2/RF 감사 결과\n\n")
        q.write("실제로 완료된 범위: 12개 legacy Method-B full channel, 신규 native full/LoS 5케이스, station-matched full P6, 고정 truth 궤적 noisy 센서 회전, 53,280행, 독립 SE2/Joseph 수식 검산. 실제 동역학·F/H 확률모형·주행 재개는 미실행. 원 scientific_PASS=false는 변경하지 않음.\n\n")
        q.write("## 신규 RF 5 vs 기존 Method-B 7\n\n")
        q.write("신규 native solver H 5개와 기존 Method-B H 7개를 동일 데이터 생성법으로 간주할 증거가 없으므로 신규 12case 결과만으로 mount0↔45의 물리적 완전 대칭성을 승인하지 않음. 모든 12케이스의 Method-B H도 현 archive manifest에 기록됨. 기존 Method-B native solver 차이의 실제 수치 parity 검증이 필요.\n\n")
        q.write("## Seed/prior 단위 독립 재집계\n\n")
        q.write(summary_seed.to_markdown(index=False))
        q.write("\n\n## 첫 도착 공통창\n\n")
        q.write("기존 20261010 prior L=4/8/16 taps와 달리 업로드 receiver code는 2/4/8ns를 각각 5/9/17 bins로 계산함 (window end = tap+round(ns/dt)+1, exclusive). Gate 비교 결과를 같은 관측정의인 것처럼 결합하지 않을 것.\n\n")
        q.write(cv.to_markdown(index=False))
        q.write("\n\n## 구현상 P1 결손\n\n")
        q.write("- G1/G2는 RF s뿐만 아니라 range도 1/2개 패킷으로 줄이는 대조군이어서 순수한 추가 편파 정보 효과를 분리하지 못함.\n")
        q.write("- body yaw 참값은 사전정해진 이상 회전, slip은 센서에만 들어가므로 실제 XY 이탈/제동구동 성능은 미검증.\n")
        q.write("- Sigma_MP/crossrange는 통계량으로 산출되었지만 F/H q_site,q_point 및 closed-loop 동작에 적용되지 않았음.\n")
        q.write("- 53,280행은 독립 환경/seed 표본 아님. F01/F02 OPEN, L1 FAIL, scientific_PASS=false.\n")
        q.write("\n## 다음 구현 순서\n\n기존 bank의 연속 EKF 재생을 기본으로, range를 모두 유지하는 편파 패킷 개수 대조를 먼저 실행. 그 다음 신규 12case H 입력 parity, Sionna actor pose simulator, joint site/point model, cross-time covariance 검증, trigger→stop→probe→fullP6 update→return→resume. 새 branch에서 재실행과 근거를 기록.\n")
    print("AUDIT_RESULT",json.dumps({k:v for k,v in reports.items() if k not in ("RF_PROVENANCE",)},ensure_ascii=False,allow_nan=False),flush=True)
    print("COMPLETED",len(a),len(df),len(cv),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True)
    x=ap.parse_args();run(x)
