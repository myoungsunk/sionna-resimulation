# 10A — 기존 7케이스 첫 도착 신호 공통 창 편파비 분석 등록

2026-10-10 / frozen before new early-gate results. 데이터는 기존 full/LoS H 7케이스 (9,519 pose-case), 고정 FP observer, sensor-v2 RF-off prior 기반 heading error label. 새 RF H와 full-route event-loop은 이 실행에서 만들지 않는다. F01/F02 OPEN 유지.

## 비교/정답

- 동일 common first-path tap k를 각 full/LoS channel에서 original strongest receiver 30% leading-edge rule로 계산하고 original OUTPUT/01_FEATURES.csv의 tap/s와 parity 확인한다.
- zero-padded CIR sample step 약 0.5ns. 공통 창 [k,k+L), L=4,8,16 taps (약 2,4,8ns), 양 RX에 동일 적용. Full complex H → IFFT offline → amplitude → per-port |CIR|² summed → s_L. LoS-only H에도 똑같이 적용. Noise-free source; noise-floor subtraction =0; k full/LoS difference 기록.
- FP single-tap s_FP가 기존 모델 LUT에 해당하고, cluster s_L용 별도 LoS LUT가 없으므로 **cluster를 EKF의 s 관측으로 직접 대체하지 않는다**. 현재 cluster 값은 quality FEATURE이고, e_MP,L = s_L(full)−s_L(LoS)는 oracle-label-only이다.
- Online-compatible features: measured s_FP, |s_FP|, Psum, s_L, |s_L−s_FP| for L=4/8/16, per-gate energy sum, dB ratio when well defined. LoS-specific e_MP,L, e_MP,FP, true pose, heading labels are NOT training/inference features.
- Labels: abs(e_MP,L), abs(e_MP,FP), abs(e_s total); v2 pre-RF prior-assisted inverse heading correct<=5deg from published route-held-out results. heading_error_deg is evaluation target only, no truth prior in estimator.

## 비교 방법

- D1: correlation of oracle |e_MP,FP| with |e_MP,L|, FP-small / gate-large cases, route/mount/distance strata; no physical depolarization claim.
- D2: measured cluster P1/P2 and FP ratio vs RF-heading error Pearson/Spearman. Report route and physical pose, NOT replicated seed points as independent channel.
- D3: leave-one-ROUTE-out supervised correct5 probability prediction:
  - CONSTANT prevalence;
  - FP_ONLY = measured range, total firstpath power, signed s_FP, |s_FP|;
  - FP_PLUS_GATE4 = FP_ONLY + s_L4 + |s_L4−s_FP|;
  - FP_PLUS_GATES = FP_ONLY + s_L4/s_L8/s_L16 + each |s_L−s_FP|;
  - EARLY_ONLY = s_L4/s_L8/s_L16 plus total firstpath power;
  - FP_PLUS_CIR_SHAPE = FP_ONLY plus previously stored P1_jSD/P2_peakDiff/P3_asym/P4_shapeL1.
  - L2 logistic C=1, train-only standardized/missing impute, repeated RF pose prior labels aggregated into single pose with binomial sample weight (no 150 repeated identical RF observations as independent environments). Per heldout route: Brier, ROC-AUC, calibration bins, availability, physical-station-cluster 1000 bootstrap of FP_PLUS_GATES minus FP_ONLY Brier.
- D4: predict actual multipath FP mismatch as separate oracle diagnostic, never confuse with heading correctness.

Frozen seed=20261010. Site bootstrap group route+XY; identical route different anchor/mount share physical location but independence of scenes not claimed. Stop if original s/tap parity difference>1e-12, missing H or mismatched pose. No detector using oracle LOS for current s trust in online policy.

Required outputs: FIRST_CLUSTER_FEATURES.csv.gz, FIRST_CLUSTER_ORACLE_LABELS.csv.gz, PARITY.json, FIRST_CLUSTER_DISTANCE_CASE_STATS.csv, ASSOCIATIONS.csv, HELDOUT_CORRECT5.csv, HELDOUT_PREDICTIONS.csv.gz, CLUSTER_BOOTSTRAP.csv, CLOSED_LOOP_DATA_COVERAGE.json, SUMMARY_KO.md, EXECUTION_STATUS.json.

Scope: first-cluster association CAN be executed from seven existing channels; full closed-loop trigger-stop-probe-resume remains NOT_RUN until RF is generated on demand at actually triggered coordinates (plus missing mount45 cases).
