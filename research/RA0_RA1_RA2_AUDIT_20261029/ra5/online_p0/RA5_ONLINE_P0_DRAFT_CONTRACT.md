# RA5-ONLINE-P0 — engineering implementation contract (DRAFT, no science release)

Role: PROPOSER-design specification, IMPLEMENTER code/execution, AUDITOR independent verdict **PENDING**.
Contract ID: RA5-ONLINE-P0-20261030. Allowed phase: P0_PREFLIGHT_AND_RETROSPECTIVE_ENGINEERING.
base_git_sha: bfff111357ffd54baa2627dfda01df99548a6cd9
governance_git_sha: 250d617ad89a4105fa1af546cc83ceed9de98f42
original_RF_source_git_sha: 9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13
reference_contract: MBVAR-INFO-001 frozen, consulted for conventions, NOT amended or reused as approval.
draft_contract_sha256: compute SHA256 of THIS file at runtime; do not claim FROZEN.
output_root: GitHub Actions artifacts ra5-online-p0-* and only new online_p0/ code.
Source: seven frozen Corridor Full H and SAMPLES, frozen 257-bin FFD banks, original B0 E1 controls.
External independent scene count: ONE (all route/case rows are correlated). Office is previously seen DEV. No new RT.

## Original problem and four interventions

- Historical BB_ORIG uses original [r_integer,s0] packet z, mu_B, original R0 and BASE mask, frozen predictor. Reproduce full x/P/mask within 1e-10 on R4_aB_m0 and R5_aA_m0 **before** any new filter output.
- New INT2_CAL: observed r_integer and s0, same raw H; train-only mean correction and covariance matching the observation definition; no old packet-keyed mu_M reuse.
- New SUB2_CAL: observed r_fractional and s0. Train-only mean and covariance, no hidden test truth. Requires measured fractional-edge tap valid and source H SHA.
- New SUB3_JOINT: observed r_fractional,s0,ds1. Train-only full joint 3×3 covariance (including r–s, r–ds and s–ds) and shared-Full-CIR detector. No diagonal independence assumption.
- BASE_FIXED: original BB_ORIG mask on identical timeline. SELF_NIS: own R, J, x/P, z, conditional observed rank; threshold 9.210340371976184 (2 DOF) or 11.344866730144373 (3 DOF) exactly. SELF_NIS is not blended with BASE_FIXED. Failure/deterioration is valid.
- FFD LoS h_s0, h_ds1 model: SourceFFD spectrum with predicted LoS tap; measured Full tap mismatch logged and stratified. Range mean h_r=geometric_distance + fitted b(features(x_prior,...)). When computing H_r analytic/FD, bias model and geometry are differentiated. Test GT never enters filter or feature inference. Original r/s control & mu/R must not be casually reused after change.
- Variance/covariance: residuals of deterministic Full-H minus LoS with train-only bias, pooled across **other 2 routes**. Offdiagonals preserve shared-model/error correlation. Predeclared shrinkage to 0.85R+0.15diag(R), no artificial jitter/positive inverse on raw rank-deficient input. This is an **effective retrospective RF model covariance**, not independent receiver stochastic R nor a proven online law.
- Where tap index changes, wrong arrival, near-threshold, weak port, or unmatched Full vs LoS tap: report separate strata and full switch proportions. Use an empirical train-only tap-switch conditional distribution p(Full tap - LoS prior tap | observable SNR/edge quality) as a *diagnostic categorical model*, never force ordinary Gaussian likelihood through a switch without a mixture test.
- P, x initial, Q, ds/gyro controls, original z/r/s observation definition, original case/pose/time and scoring t>=30s stay fixed. No new hardware or independent RF drawn.

## Predeclared engineering gates

G1: Source hashes, complete controls/packet alignment, native first-path replay <=1e-12 for s0 and <=1e-9m for r, required cases/denominator, no missing/NaN rows. NO GT in test inference.
G2: Parent BB_ORIG source code replay state/P/mask maxabs<=1e-10 on R4-B B0 and R5-A B0; ref full-length original exp_pb plus new wrapper. negative fixture muM->muB, sigma->0 remains documented in prior RA4.
G3: Observer fractional crossing selection, signed s0/ds1, normalized 2 port power, tap/port flip and invalid handling, joint noise matrix raw-vs-differenced transform exact maxabs<=1e-10. No source H modification.
G4: Source-only mean train route vs held route, variable feature computed from true pose ONLY on TRAIN. On TEST, prior x from the filter; neither test GT, archived true heading, Full-H label, nor oracle bias may enter the online features. Guard with deliberately perturbed/NaN scoring truth.
G5: Train-only PSD 2×2 and 3×3 joint covariance finite, positive, chosen shrinkage fixed; if singular stop arm with explicit rank failure; no silent diagonalization. Independently verify 2D vs 3D Schur and basis transform. NIS DOF matches chosen arm. No front-end temporal independence claim.
G6: Paired BASE_FIXED and SELF_NIS full-length replay, at first mask change pre-flip x/P must match for same arm (tolerance 1e-10), record rho/sigma/R/K/x/P. Same stream & mean, only gate policy differs.
G7: Evaluation heading/XY RMSE, heading/XY NEES and 95% coverage, NIS distribution, accepted/masked, source/held route. Engineering PASS if intervention and calculations correct, *regardless of improvement sign*. No model/hyperparameter choice from held-out outcomes presented as prospective success.

## Stop/claim policy

- DRAFT and SELF_REVIEW_ONLY. The original MBVAR-INFO scientific HOLDOUT2, future external scenes, PRE-P3 RT and existing Office-as-TEST are prohibited.
- Any early code failure/negative fixture triggers FAIL/BLOCKED, all logs retained. No masking bad entries to obtain better RMSE.
- No claim of calibrated deployed receiver noise, physically correct Full multipath Jacobian, completely independent spatial/time field, unseen-scene generalization, or publication-ready P0 result.
- For independent science approval: different auditor execution with independently recalculated H->CIR->tap->mu/R->K, source and manifest hash checks, no split overlap; final frozen science contract and independent new scene required.
