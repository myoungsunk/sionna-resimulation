# 06. 다음 요청부터 그대로 실행하는 Runbook: 게이트·분기·보고 형식

**상태:** 실행 준비 문서. F0–F7의 새 실험은 이 문서의 Git commit 시점에 수행하지 않는다. 기존 결과를 덮어쓰거나 train/test split을 시험 중에 바꾸지 않는다.

## 1. 실행 시작 이전 소스·자산 확인

1. 새 실행 branch는 이 plan branch에서 생성하지만 original scientific baseline source는 Git ref/blob SHA로 read-only pinning. 원본 N4-B/C/R2, Exp1–4, pole replay, odom-Q/High-Vr artifacts 체크섬 재확인.
2. 각 실험에 필요한 FFD bank, R4/R5 motion controls, independent scene archives를 scene_manifest.json과 SHA로 inventory. 파일 없으면 **BLOCKED_INPUT**으로 정확히 보고, 다른 실행 가능 실험을 진행.
3. GT/FP/LoS/Full + code schema mismatch, AST, Jacobian non-differentiable pole, wrong dt, NaN, source blob 변경은 **TECHNICAL_HOLD**; 소스 무효 문제면 수정 후 재감사. 단순히 과학적 성능이 나쁜 것은 source issue가 아니므로 끝없는 진단 없이 **SCIENTIFIC_FAIL** 보고.
4. Gold parity: original R2 FrozenLut old branch J4/SR4 POWER source matching; independent 48 pole replay parity. Old R0 original source immutable. Every new candidate has own scheme version/commit.
5. F0 source FFD 없다면 old/pole-candidate proxy는 exploratory only; new model labels are not validated truth.

## 2. Dependency DAG / 가능한 병렬처리

~~~text
G0: source/data/license/hash/version/manifest read-only audit
 ├─ Acquire original FFD banks (SIM-A)
 │    └─ F0 EM-LUT source correction + off-pole interpolation
 │         └─ F1 corrected P2/N4-B retraining
 │              ├─ F3 LoS-preserving RF integrity model
 │              └─ F4 temporal/state covariance final fits
 ├─ F2 physical r/s/bias/gain attribution (frozen R2 pilot)
 │    └─ after F1: corrected-model mechanism
 ├─ F5 G4/gain/FP diagnostics (frozen old-source pilot)
 │    └─ after F0/F1: corrected-source and independent-scene final
 └─ Acquire authentic motion + independent Sionna scenes (SIM-B,C)
      └─ schema audit + immutable scene TRAIN / VALIDATION / LOCKED TEST
           └─ F3 / F4 / F5 fit TRAIN/VALIDATION only
                └─ F6 independent test evaluation
                     └─ F7 independent final freeze, figures, claims
~~~

F2/F4/F5 source-frozen preliminary controls can begin after G0 if SIM-A/B/C absent, but cannot be promoted to independent evidence. **No broad explorations after final train/test freeze.**

## 3. Required per-stage executable checklist

### G0 source audit
- Full SHA lists from 03, immutable archives, source bank and simulator availability.
- Original 14 archived RF channels and original J4/SR4 POWER baseline replay checks.
- Scene and model leakage inventory; missing files explicitly marked. Output SOURCE_RECEIPT.json, INPUT_INVENTORY.csv, EXPERIMENT_HASHES.json.

### F0 physical pole and interpolation
- Original complex antenna FFD bank and actual Tx/Rx mapping; near-pole, 1mm ring, phi periodic seam and global Cartesian projection.
- Original/pole-hotfix/direct source FFD; compare 9519 Native LoS and F01 original 500-point test, solve failure rather than setting pass=true.
- Output LUT_SOURCE_REBUILD.json, HSBANK_DIRECT_TEST.csv, JACOBIAN_STRESS.csv, F01_QA.json, CANDIDATE_LUT.npy.

### F1 corrected labels / trained RF errors
- Native and Full residuals from source-corrected h, original pose/time pairing; same R2/R4/R5 source split as original for paired demonstration, entirely new independent scene splits for final generality.
- Train-only scaler, q quantile cuts and regression, mean/R fits; heldout route/component analysis. Output LABEL_CORRECTION.csv, FOLD_STATS.csv, FITTED_POWER_PARAMS.json.

### F2 bias leakage / Dual LP
- Matched fixed-prior and natural recursive; r-only, s-only, DR4, full, q+range/no s, 4R0, Gate-only, μr/μs/Crs and G4.
- Record K_bias,r/s ν, accepted counts, Heading and signed Gyro Bias, XY and conditionalXY NEES, same-Gate counterfactuals.
- Output F2_ATTRIBUTION.csv, F2_TRACE.npz, F2_COUNTERFACTUAL.csv, F2_DECISION_KO.md.

### F3 LoS integrity
- Expected q_LoS from calibrated FFD/gain and estimated prior, or explicitly blocked if source bank absent.
- Fit quality and regime conditional mean/covariance on independent TRAIN/VALIDATION; Native LoS negative control R0 vs Full POWER, no full-trained mean blindly applied to clean packet.
- Output F3_LOS_GUARD.csv, F3_FEATURE_AVAILABILITY.csv, MODEL_PARAMS.json, per-scene false-correction rates.

### F4 time-correlated RF state
- Raw and detrended residual site/lag/gate conditional, repeated site under independent RF situations; fixed scene vs independent noise.
- Candidate colored time/site correction and report-only covariance learned from independent training, compare original POWER and identical set of noises and scene.
- Output F4_ACF_SITE.csv, F4_STATE_NEES.csv, F4_SCENE_BLOCK_CI.json, PRE_GATE_NIS.csv.

### F5 G4/FP/Gain
- Fixed-prior mean↔cov cross-swap, G4 vs POWER quality, covariance eigenvalues/K/NIS/FP tail by Heading information.
- FP threshold 20/30/40, 1/3/5 tap, ±3/6 dB common gain, port swap, group-delay offset.
- Output F5_G4_GAIN_GATE.csv, F5_FEATURE_STRESS.csv, F5_INFO_VS_INTEGRITY.csv.

### F6 new independent Full RF scenes
- SIM-C actual complex Full and LoS source streams, source scene/time/mount/anchor/seed metadata and duplicate/leakage checks.
- Scene-independent split before any fit; parameters frozen before locked test. Each source scenario and failure case reported separately.
- Output SCENE_DISJOINT_SPLITS.json, FINAL_LOCKED_METRICS.csv, SCENE_CI.json, FAILURE_CASES.csv.

### F7 publication QA
- Independent evaluator from original per-frame NPZ (not summary CSV) computes FP, h/H, model params, x/P, 4-state/pose/Heading/condXY/bias consistency, scene CIs.
- Figures and supplementary from frozen code, limitations/negative controls including pole and LoS damage, source/Git/artifact hashes, all scenes.
- Output FINAL_PASS_FAIL.json, figures and source CSV, PAPER_RESULTS_KO.md, SOURCE_BUNDLE_MANIFEST.json.

## 4. Stop & resume decision matrix

| Finding | Stop | Scientific label | Next step |
|---|---|---|---|
| Source SHA mismatch, GT leak, missing required array, non-SPD posterior | affected stage YES | TECHNICAL_INVALID | source repair → re-audit → single canary → affected numeric rerun |
| Missing original FFD bank | F0 source YES, F1 final YES | BLOCKED_INPUT (SIM-A) | continue F2/F4/F5 source-frozen preliminary |
| No authentic gyro-wheel R4/R5 | archival R4/R5 actual recursion YES | BLOCKED_INPUT (SIM-B) | regenerate **new** labeled synthetic controls if allowed; never claim original |
| No independent Full complex RF scenes | F6/F7 YES | BLOCKED_INPUT (SIM-C) | continue scoped prior pilots only |
| LoS-damaging candidate | final universal estimator YES | SCIENTIFIC_FAIL | simpler F3 LoS-safe selector |
| Bad heading/bias at other mount | new model not adopted | SCIENTIFIC_FAIL | preserve baseline and adverse case |
| No heldout posterior calibration despite good RMSE | consistent Bayesian claim YES | SCIENTIFIC_FAIL or UNRESOLVED | report accurate empirical correction only |
| G4 spike mechanism rejected | NO | HYPOTHESIS_REJECTED | report Gate/site/model shift |
| Active RF yaw sweep lacks real Full H at each yaw | optional study deferred | DEFERRED | not part of current POWER paper |

## 5. Versioned execution and audit workflow

- Document branch research/powerjoint-final-preexecution-20261016 contains plan files, manifest and **no new scientific runs**.
- When explicitly told to execute, create a separate research/powerjoint-final-f0-... branch; pin original source commits and hash audited input archives; do not change source branches.
- Each GitHub Actions job: checkout exact original code → code and source audit → dependency/unit physics checks → source parity → target experiment → independent metrics evaluation → report always uploads result/failure.
- Technical invalid results must not become statistical PASS; fix only source contracts that invalidate results, rerun once with source SHA pinned. Scientifically negative valid results stay unchanged in history.
- Locked test feedback shall not change model/thresholds; new tuning requires new candidate and new unopened test scenes. Persist raw Source H and FFD banks beyond GitHub Actions retention for paper.
- Output each F report with first table: code audit/old parity, second: complete conditions, third: original/new matched metrics and CI, fourth: claim supported/falsified/blocked and Git artifact paths.

## 6. 사용자에게 제공할 단계별 결과 형식

For each F, disclose:
1. Code/source audit (SHA, modified paths, input/hash).
2. Falsifiable hypothesis and baseline controls.
3. Full numeric metrics by scene/anchor/mount/LoS/Full/Bias: Heading/XY/Bias RMSE; 4/Pose/Heading/condXY/narrow NEES/95%, NIS/gate/sharpness.
4. Source-only and natural recursive vs one-step and common-gate contrasts with selection bias caveat.
5. Technical readiness, scientific status, independent generalization status each distinct.
6. Git commit/run/job ids, raw NPZ, split scene IDs, artifacts, separate independent reviewer.

No additional exploratory scope after final F0–F7 experiments unless a proven critical source failure forces a transparent new scientific revision.
