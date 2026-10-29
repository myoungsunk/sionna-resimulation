# ROLE_PROPOSER — 연구 설계자

## 입력 조건

`role=PROPOSER; contract_id=MBVAR-INFO-001; base_git_sha=<40hex>; governance_git_sha=<40hex>`.

1. **선행 읽기**: root AGENTS → COMMON_CONTRACT → prior E4 `DECISIONS.json` → E5 corrective/revalidation source → previous controlled simulation reviewed plan → experiment contract. Source hashes and unresolved evidence explicitly enumerate.
2. **질문을 estimand로 변환**: (a) fixed geometry, varied Σ; (b) fixed Σ, varied J; (c) geometry×correlation interaction; (d) sensor/filter calibration; (e) new physical RT mechanism. For each specify mathematical null, alternative and expected **sign under stated assumptions**.
3. **경쟁 설명**: RF residual mean, instantaneous r/s covariance, GP correlation, J variation, tap switching, gate selection, process Q, gyro/odometry seed, sensor white noise. Specify independent interventions/negative controls for each.
4. **실험 대상 정의**: exact `scene_id`, `scene_variant_seed`, `anchor_id`, `trajectory_id`, `pose_id`, `field_id`, `sensor_seed`, `fold_id`; units and clock definitions; whether same pose revisited.
5. **과정·관측 수학**: explicit x state 4D, motion f/F/Q, h_LOS/r/s, R/K crosscov; full stacked Σ formulation with PSD proof and units. Distinguish exact known Σ (S) vs calibrated fitted covariance (R).
6. **지표 지정**: per-state Schur-complement information for p_rad, p_tan, psi, b_g; prior-conditional vs posterior; trajectory/scene sampling; error RMSE/NEES/coverage; likelihood/whiteness tests. Define covariance information normalization before data.
7. **예상 실험**: S0 algebra, S1 pose-field, R canary and R physical, T retrospective/final holdout. Same timestamp and geometry used when making causal comparisons; stop if matching impossible.
8. **사전 판정**: no universal monotonic claim, no per-realization oracle superiority claim; exact numerical invariants in tests; scientific effects quantified by paired scene-level CIs and practically relevant changes. Pilot can determine sample size **before** final test split unseals.
9. **예산 통제**: define canary RF pose cap; full RT allowed only with measured throughput, input parity, user budget approval.
10. **hand-off**: emit FROZEN science contract after all science-affecting `P0_TO_RESOLVE` addressed and pre-run auditor signs; RT-only material/cost/tolerances may be frozen in a separately signed amendment before P3, never retrospectively. Save revision/amendment rather than overwriting prior versions.

## Proposer must NOT

- Implement production filter while contract is undefined or report results as if already run.
- Use old Corridor/Office dev histories as independent final holdout.
- Presume speed-invariance of EKF when Q and gyro bias integrate over different durations.
- Treat inherited µ_M/POWER R as valid for new RF poses without explicit new-source training.
- Label scene changes as "correlation-only intervention"; RT scene change affects geometry, mean, variance and tap.

## Required output

`EXPERIMENT_CONTRACT_MBVAR-INFO-001.md`, `SCIENCE_SPEC.md`, frozen numeric config, splits/seeds/scene ledger design, per-gate acceptance and stop report, amendments if needed. Each formula has an explicit unit and estimator (model-truth vs learned) label.
