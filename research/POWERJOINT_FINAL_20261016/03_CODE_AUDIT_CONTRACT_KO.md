# 03. 클린 코드 설계·소스 감사·재현성 계약

**목적:** 현행 원본 N4-B/C, Exp 1–4와 pole 후보 소스를 임의로 섞지 않고, 논문 제출 가능한 재현성·데이터 분리·부정대조를 만족하는 하나의 clean research runner를 구현할 명세. **이번 문서는 코드 구현 계약이며 새 estimator는 아직 구축하거나 실행하지 않았다.**

## 1. 원본 Read-only 및 추적 가능한 Source of Truth

| 계층 | 동결 원본 경로 / Git blob | 접근 원칙 |
|---|---|---|
| 4-state motion/filter | research/EKF4_RANGE_S_STAGED_20261014/core.py / 0a0851e6867c14fec5eefe02df471100cb9e9e1d | 원본 F,G, Joseph posterior update, r/s joint gate 기준 불변 |
| Gyro/Wheel R2 replay | research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py / b1de0de13e82cd414306cba3182af18ac97607bf | seed0, B0/L0/L1/L2, R0, t/pose ID source parity |
| Frozen FFD LUT observer | research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py / cb676aea8e6710ff2c0e175e1e422271b696cebe | old LUT는 항상 비교 가능한 reader로 유지 |
| Antenna/FP source LUT builder | results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb/drivesim/hs_lut.py / a205e43bb381fbbdf3a41f9bb029ede0d4293231 | 복소 FFD 직접 채널 생성과 first-path operator까지 trace |
| N4-B residual predictor | research/R5_N4B_20261015/n4b_rf_errors.py / abd654dd9efde61fc7baffc350188b2a8b4904a3 | train/validation/test split 및 original error labels 전부 명시 |
| N4-C original POWER/SR4 | research/R5_N4C_20261015/n4c_joint_sr4.py / 40c795fa8799c4090c0766ebdccf6e2be83df6a0 | original μ/R policy, J4/SR4 source-boundary baseline |
| Exp2/3/4 factor controls | research/EXP234_CAUSAL_20261016/exp234_recursive.py / 4ec38ff42a5daecf00067902369b03bfec3495cd | 실제 이미 수행, new science "발견"으로 재실행 보고 금지 |
| Pole θ0 candidate | research/POLE_RECURSIVE_20261016/pole_lut_fix.py / d2474fcac8bc02dc20d1bad253b6c39956412376 | 특정 orientation/grid에 한정, 원본 NPY 파일 직접 변경 금지 |
| Pole R2 recursive canary | research/POLE_RECURSIVE_20261016/pole_recursive.py / f16066251088774752b2f0b19a3d7463afc0d60a | original J4/SR4/POWER state/P/gates 48 matched |
| Main R2/R4/R5 contract | research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json / 8bf216cf606f5e3c11139cacbf42f15a44556feb | pose/time/antenna/truth/control/archived dataset origin |

**Original raw archived ZIP SHA256**:
- RF: 88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63
- R2: ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399
- N4-B: 170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b
- N4-C: f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9
- Original hs_lut_2deg.npy SHA256: 711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079
- Existing experimental theta0 NPY candidate SHA256: e6db187d2b8f0507ab588affb0bae66d26d2b778ce9244c36154342800f33f0b (separate user attachment, *not* in source Git branch).
- Exp2–Exp4 successful GitHub Actions run 38852849031 artifact 12025759278; pole recursive run 38857292101 artifact 12027528128.

SHA256 of archive ZIP verifies provenance of supplied bytes, while Git blob ID verifies source text identity. Both used; never conflate them. GitHub Actions artifacts have retention/expiry; pin/copy checksums and archive to durable project storage before publication.

## 2. Clean modules: new namespace, no in-place monkeypatching original source

**Recommended self-contained package**, incremental, under research/POWERJOINT_FINAL_20261016/src/:

- io/manifest.py: frozen source/asset hashes; observations, paired pose/time IDs, scene/seed identifiers, splitting and source bank types. Central typed schema prohibits missing time and silent pose joins.
- physics/ffd_reference.py: source antenna bank loader with explicit Cartesian-to-TX/RX basis projection and θ pole limit; geometry+gain+delay. No original LUT overwrite.
- physics/lut_adapter.py: OldLut, PoleCandidateLut, SourceRebuiltLut with identical observation signature (value, H). Explicit near-pole and φ seam flags; finite differences tests.
- observer/first_path.py: one source of FP window/Hann/IFFT/threshold and usable hardware-like packet fields. Versioned detector types and coherent oracle flag.
- rf_models/power.py: frozen legacy POWER inference and exact train-fold model readback, no on-the-fly fit.
- rf_models/los_integrity.py: optional expected-LoS power, integrity features/calibrated risk scores (the data path remains normalized or flagged empirical heuristic).
- rf_models/likelihood.py: explicit p(q,r,s|x) and/or approximation; no double count; SPD (eigen/sqrt/Cholesky), fully declared conditional cov, no future or GT in inference.
- state/recursive_filter.py: pass explicit motion core, z, quality estimate, μ,R, gate; returns x-/P-, h/H/K/NIS/gate, x+/P+. Original filter imported/validated but unmodified.
- state/uncertainty.py: conditional XY Schur, posterior 4-state and bias conditioning, independent report covariance branch. Output method/report_only bool.
- evaluations/experiment.py: group by scene, channel, route, mount, anchor, bias, seed, actual model name; frozen paired comparisons and pre-registered thresholds.
- audits/source_audit.py and audits/independent_review.py: static code/manifest SHA, build stage, no-leakage dynamic negative tests, independent recomputation.
- reporting/figures.py: panel figures with original/direct/experimental labels, negative controls and sample independent count.

Use small typed dataclasses rather than flexible arrays where unit/axis errors matter: ObservationPacket(time_s, pose_id, r_m, s_dimless, fp_p1, fp_p2, fp_tap, scenario_id, rf_seed), MotionPacket(ds_m, gyro_increment_rad, dt_s, sensor_seed), Prior(x4,P4, original_sha), AntennaConfig(anchor, rx_mount, tx_pol, frequency_vector, FFD_sha).

Typed output has provenance (source file/sha, sample IDs, revision, q source and train_fold) on every row. Binary raw per-packet H(f) and RF observer derived data must be versioned separately so q from Native LoS never silently equals q from Full.

## 3. Reproducibility and safety tests (mandatory unit+integration)

### Physics
1. Exact original 14 channel × 14,502 archived RF z_r/z_s observation parity before doing any model change.
2. Original 4-state J4/SR4 POWER x/P/Gate parity; 48 pole-replay checks, 32 Exp2 original checks, 48 ODOM Q original parity as appropriate.
3. $r$ and $s$ order consistent everywhere; meters, radians, rad/s, m² and dimensionless s. Original Range observer $B_\mathrm{OLD}=-.5315983906250129$m not double subtracted.
4. $P_1,P_2>0$, $s\in[-1,1]$, $q=\log_{10}(P_1+P_2)$; positive definite R, P with stable Cholesky.
5. $H$ exact FFD analytic chain rule vs finite-difference, including near-pole/periodic seam/boundary. No acceptance at Jacobian undefined poles without coordinate alternative.
6. Exact correlated SR4 whitening: $a=C_{rs}/V_r$, $V_{s|r}=V_s-C_{rs}^2/V_r>0$, conditional joint one-packet update. Test toy linear Gaussian J4 equivalence; don't claim exact nonlinear J4=SR4.
7. FFD θ0 direct complex near-limit and F01 interpolation test; meta gate passed=false is a P0 source blocker until corrected/adjudicated.

### Statistical/data leakage
8. Train and test disjoint by *RF scene* (and time/pose/route within scene if suitable). Fitted scaler/Ridge cuts, empirical covariance/variance floor threshold independent from test.
9. GT never enters production Prior/Quality/Control after recorded measurements generated. Inject synthetic/poisoned GT into estimator test and assert output bit-identical. GT-only inputs explicitly tagged oracle and never serialized with online feature schema.
10. Same packet q/s dependency handled either normalized joint density contract or explicit HEURISTIC tag; no implicit independence, no second s pseudo-measurement.
11. Physics q expected LoS gain uses only $\hat x^-,P^-$ and calibratable antenna/receiver metadata; not GT or future. Port label swap p1↔p2 & s sign, global gain scaling test.
12. Keep RF complex channel seed distinct from sensor seed; recreating controls with new seed but fixed H(f) does not provide independent multipath sample.

### Numerical/score
13. Per packet unit tests for innovation, gain, Cholesky/Joseph covariance, 99% NIS gate and fixed-mask exact.
14. Important identity $\mathrm{NEES}_{pose}=\mathrm{NEES}_{\psi}+\mathrm{NEES}_{XY|\psi}$ tested to error <1e−7 relative to scale; also $\mathrm{NEES}_4=\mathrm{NEES}_{pose}+\mathrm{NEES}_{b|pose}$.
15. NEES free dimension d is only a *nominal expectation under ideal conditional model*; do not test 829 temporally correlated points as 829 independent chi² samples. Use scene/seed independent test splits, cluster CI, per-scene coverage.
16. Mean± covariance report separation: filter P vs report P. If reported covariance inflated, point estimates unchanged but formal normalized Bayesian posterior claim cannot follow without a coherent model.
17. Compare zero-multipath synth, original clean Native LoS, corrupted Full, high-power false confidence, low-Hψ and multi-heading branches, FP tap switch, no-s negative controls.
18. Explicit errors on invalid NaN/Inf, PSD and angular wrap/seam; invalid runs don't become zero-valued metrics or PASS.

## 4. Strict CI execution stages and no-gaming policy

- PREAUDIT (read-only): exact source SHA + manifest + FFD/input availability + script AST + workflow order + no original file edits.
- UNIT (pure): math Jacobian, SPD, whitened SR4, truth-stripping test, likelihood normalization/integration where claimed.
- CANARY: 1 case × B0 × R0/POWER × LoS/Full; exact old baseline; new model only if input ready. Record all raw traces.
- PILOT: remaining scenes from **train/validation only**, full B0/L0/L1/L2 etc and optional ablations. If failure identify actual source invalidates science, repair + re-audit once then re-run affected groups; don't loop forever over cosmetic diagnostics.
- FROZEN EXPERIMENT: model/weights/features/cuts/gates committed and hashed before locked test. Must not change after looking at test results. Any necessary changes create new candidate revision and new untouched test, not "same holdout passed".
- INDEPENDENT_REVIEW: fresh evaluator recomputes metrics and integrity from NPZ not from emitted summary CSV; check original code/manifest/gates and independent scene hash.
- REPORT: must include fail table and all competing hypotheses, no cherry-picking M0 Full improvements while suppressing M45 or Native LoS.

**No false SUCCESS:** TECHNICAL_PASS, SOURCE_PHYSICS_PASS, OBSERVATION_MODEL_VALID, RECURSIVE_CONFIDENCE_PASS, LOS_GUARD_PASS, INDEPENDENT_SCENE_PASS are separate Boolean fields (no single optimistic PASS).

## 5. Minimal result CSV / JSON schema to support paper audit

Required keyed dimensions:
scenario_id, scene_sha, RF_realization_seed, trajectory_id, motion_seed, anchor_id, mount_deg, channel(full/native_los), gyro_bias_true_dps, solver, arm/policy_id, lut_sha, estimator_sha, model_fit_sha, model_fit_split_sha, frame_n, timestamp, pose_id.

Time-level quantities:
truth_for_scoring_only (separate controlled file), measured ds_odom/dtheta_gyro/dt, $r,s,P1,P2,q$, $\mu_r,\mu_s,V_r,V_s,C_{rs}$, fp_tap/quality/quality_model_version, $h,H,\nu,K,NIS$ pre-gate, gate status, $x^-/P^-,x^+/P^+$, report-only covariance and model status flags.

Aggregate and interval:
Heading/XY/Bias RMSE, signed gyro bias mean and endpoint, time windows, 4/Pose/ψ/conditionalXY/narrow-axis NEES and each 95% coverage, innovation NIS/whiteness and accepted-only bias, covariance sharpness/logdet, confidence interval grouped at scene level, predictive NLL, LoS clean false-correction rate, RF retention, FP switch/gain stress performance.

Raw archives: original RF complex channel as immutable SHA-per-scene, emitted source-corrected LUT separate SHA, fitted parameter JSON (train-only), actual per-arm NPZ, independent evaluation CSV, artifact schema version, git SHA, workflow run/job ID, hardware sensor/observer revision. Source bank license and raw artifact persistence must be checked before paper submission.

## 6. Engineering guardrails when refining code

- Do not copy large original code and silently change constants. Delegate only via explicit dependency injection of observation-model revision, motion/measurement model interface, regime quality and reported covariance.
- Do not modify original immutable git branches, original LUT bytes, original N4-C results; new branches are new experiment candidates.
- Never infer missing Gyro/Wheel controls from pose samples and call it original measured Sensor-v2 data. If truly new *synthetic* controls are generated, label them as regenerated simulation with exact generator version+seed, not original recorder.
- Do not extrapolate q-only Range bias from Full to Native LoS without LoS negative control.
- One-step common-mask/oracle experiments are research interventions; online deployable algorithms must pass natural gate from own prior and quality.
- Scientific failure is a legitimate and preserved outcome. Baselines and adverse conditions appear in the same result file.
