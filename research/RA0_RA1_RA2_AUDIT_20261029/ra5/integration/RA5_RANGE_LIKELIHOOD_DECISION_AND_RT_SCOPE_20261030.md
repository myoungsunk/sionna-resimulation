# RA5 ToA likelihood and low-cost RT — executed decision report (2026-10-30)

**Verdict:** TECHNICAL_METHOD_PASS / DISTANCE_CALIBRATION_NOT_TRANSFERABLE / PHYSICAL_EKF_NOT_RELEASED. Independent auditor: NOT ASSIGNED. Original Full/LoS H, SAMPLES, original BB/MB_VAR, MBVAR-INFO and POL-XCORR frozen contracts unchanged.

## 1. Original purpose and observer audit

A: continuous fractional threshold-crossing at 30% amplitude on strongest RX. Native detector first selects integer n0. If threshold is between samples n0-1 and n0, linear interpolation returns a fractional range; same n0 is shared across both RX ports. This creates a new measurement definition. New h_r and its state Jacobian plus R_rr/mean must be recalibrated.

B: preserve integer first-edge tap n0, r=n0*c/(4*N*df), estimate receiver conditional distribution P(n0|state) or separately calibrated mean and variance from train-only data. Exact discrete/categorical likelihood is allowed; do not assume a full-rank Gaussian R when tap index is stationary.

C: 257-bin complex two-port CFR likelihood, exactly equivalent to a full correlated CIR likelihood under an invertible subspace transformation. In the current diagnostic the original saved Full H template at test pose is known and a single global complex gain is profiled out. It is an ORACLE/upper-bound for delay recovery, not an online generative multipath model.

The current SourceFFD h_r is continuous geometric range + B_OLD, while old measured range is integer edge tap. They do not define one correctly specified differentiable Gaussian measurement likelihood. The first-edge index is discontinuous and sub-tap interpolation may also jump at tap/port switching.

## 2. Executed A/B/C controlled study

Source run https://github.com/myoungsunk/sionna-resimulation/actions/runs/40988773341 ; independent aggregate https://github.com/myoungsunk/sionna-resimulation/actions/runs/40989025519 .

- Original H: R5_aA_m0 poses 100,900; R2_aA_m45 poses 200,500, frozen source commit 9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13, SHA checked.
- Fixed common H rigid delay shift on all paths and same port pattern, NOT true moving scene. Per-bin Gaussian SNR -5,5,20 dB; RX jitter 0,150 ps; correlated RX noise rho=0.3.
- TRAIN delta (-0.24,-0.12,0,+0.12,+0.24)m, 128 draws/shift. TEST delta (-0.18,-0.06,+0.06,+0.18)m, 192 draws/shift. Disjoint RNG streams; same test complex noise for all arms.
- 24 pose/noise cells, 18,432 test realizations per method. Calibration is scene/pose-conditional and known-geometry; it has not been transferred to unseen physical spaces.

| Case | SNR | jitter | B integer-Gaussian RMSE | A fractional RMSE | B categorical RMSE | C known-H raw complex RMSE |
|---|---:|---:|---:|---:|---:|---:|
| R5-A | 5 dB | 0ps | 4.64cm | 1.85cm | 4.06cm | 0.54cm |
| R5-A | 20 dB | 0ps | 4.10cm | 0.37cm | 4.39cm | 0.10cm |
| R5-A | 20 dB | 150ps | 6.07cm | 4.44cm | 5.20cm | 4.12cm |
| R2-A m45 | 5 dB | 0ps | 5.33cm | 3.36cm | 4.61cm | 0.66cm |

Sub-tap A improved RMSE over native integer 12/12 conditional case/SNR/jitter cells, C known-H oracle best 12/12. At SNR -5 dB for R2-A, false leading-edge detection yielded multi-metre RMSE; B categorical appeared much better only with a strong narrow +/-0.24m synthetic prior. Never promote this as universal detector robustness. Report full stratum RMSE, predictive log-likelihood, coverage, tap/port switching, outliers rather than only average errors.

## 3. Cross-pose transfer and uncertainty failure

https://github.com/myoungsunk/sionna-resimulation/actions/runs/40989283065

Calibrate mean and variance exclusively on one original pose; test the other original pose with new noise and relative shifts. At SNR=20dB, RX jitter=0ps:

| Train -> Test | Native calibrated RMSE | A fractional RMSE | A 95% interval coverage |
|---|---:|---:|---:|
| R5A 100 -> 900 | 4.82cm | 2.07cm | 0% |
| R5A 900 -> 100 | 3.40cm | 2.15cm | 0% |
| R2A-m45 200 -> 500 | 15.77cm | 14.89cm | 0% |
| R2A-m45 500 -> 200 | 16.26cm | 14.91cm | 0% |

This is a documented negative result. Lower within-pose receiver variance cannot represent between-pose deterministic RF model bias. The same pose-noise model does not retain 95% uncertainty coverage when moved between two saved poses. It is not a population-wide statistical coverage estimate.

## 4. Seven-case saved H retrospective route holdout

https://github.com/myoungsunk/sionna-resimulation/actions/runs/40989668488

Original seven SHA-verified Full-H arrays and matching pose table; 7,251 timeline case observations. Hold one route (R2/R4/R5) out, fit constant vs range/angle/mount geometry mean bias on other two. All geometry covariates on heldout were computed from GT pose, so this is OFFLINE CONDITIONAL ERROR DIAGNOSTIC, NOT AN ONLINE estimator. Receiver noise not resampled, no Gaussian R calibration.

| Heldout | integer+constant | sub-tap+constant | sub-tap+geometry |
|---|---:|---:|---:|
| R2 aA m0 | 10.62cm | 9.75cm | 8.31cm |
| R2 aB m0 | 9.25cm | 8.10cm | 7.20cm |
| R2 aA m45 | 12.28cm | 11.63cm | 9.49cm |
| R4 aA m0 | 11.99cm | 11.25cm | 9.67cm |
| R4 aB m0 | 9.09cm | 7.55cm | 6.91cm |
| R5 aA m0 | 15.85cm | 15.05cm | 13.81cm |
| R5 aB m0 | 12.35cm | 11.50cm | 10.58cm |

This is retrospective same-corridor RF, not a new independent physical scene. No 4-state EKF RMSE or NEES claimed.

## 5. Fixes in strict priority

P0-1 (implemented diagnostic): native first-edge plus optional fractional crossing, shared port, valid/invalid, tap-switching flags. Cross-pose mean QA shows calibration not transferable. Maintain native unchanged in baseline.

P0-2 (required next): revise source-only mean h_r = distance(x)+b_train(range, bearing, mount, channel quality). At inference all covariates must come from own prior and online CIR, not ground truth. Freeze train, validation and held-route embargo before fitting. Do not reuse original mu_B,mu_M blindly with the changed range observable.

P0-3 (required next): partition receiver stochastic variance, geometry-dependent RF model error, calibration uncertainty and shared r/s0/ds1 covariance (count common terms once). Train-only conditional covariance with PSD/rank audit; mixed true-edge/false-edge at tap switching requires calibrated categorical or robust mixture; never force singular full 3x3 covariance invertible merely to continue.

P1 (required): for fractional range, differentiate actual continuous leading-edge crossing against state at fixed tap and compare with finite differences, independently check tap threshold discontinuities. Original SourceFFD continuous geometrical J_r cannot substitute for this measurement Jacobian without likelihood equivalence evidence.

P2 (conditional): 4-state correct split/joint EKF with Joseph covariance, same BASE mask, separate SELF_NIS and first packet rho/sigma/R/K/x/P lineage; correct measurement rank/dof for NIS. Only then revisit fifth nuisance b_s and correlated temporal covariance with independent field evidence. Same raw s0 and s1 with full cross-cov, not independent diagonal terms. No truth leakage.

C raw complex online use requires its own FFD/direct/reflection template uncertainty, phase/gain/clock nuisance and frequency covariance. Current known-H raw profile is a best-case reference, not a deployable feature model.

## 6. Additional RT scope, lightest first

A. **Zero new RT, DONE:** A/B/C controlled comparison, cross-pose calibration, seven-case LORO. All original saved Full H unchanged.

B. **Tiny engine smoke, DONE:** https://github.com/myoungsunk/sionna-resimulation/actions/runs/40989930064 . Sionna RT 2.0.1 real PathSolver called exactly 2 times on an empty scene, ideal isotropic V port, max depth 0, receiver [3,7,.45] and [5,7,.45] from anchor [2,2,2.65]. Geometric direct path delay errors 1.747e-15 and 1.221e-15s. Verifies solver runtime and direct geometry only. First two failed attempts 40989398187 / 40989714446 were constructor and DrJit API mismatches, fixed and retained. Not original complex FFD, not a reflective physical scene.

C. **Source PRE-P3 geometry, DONE with zero RT:** https://github.com/myoungsunk/sionna-resimulation/actions/runs/40990030858 . 3 windows LOW/HIGH/REV60 ×8 poses ×3 C00/C01/C10 theoretical scenes=72, plus four repeat-pose QA=76 planned. Shared plate 24 analytic specular checks PASS; maximum excess path 6.3231 zero-pad taps, threshold 8 taps. This is not physical frequency/material/Jones parity.

D. **Next genuine physical canary, NOT EXECUTED:** start only with first 8 C00 DIRECT configurations using actual FFD complex 2port/257freq, compare SourceFFD direct complex, reference phase, range, signed s, tap/branch, and path list. Old MBVAR-INFO PRE-P3 is still UNSIGNED; numeric RT budget and independent audit not approved. C00 must pass before floor/reflection C01 and plate C10. Do not equate ideal engine smoke with C00 parity.

E. **After D:** add physical floor C01, shared plate C10, first 8 pose sets, then possible 76 configuration expansion. Only after pre-frozen materials/scene/solver/FFD SHA, approval, and passing D. No automatic scale-up.

F. **Final blind unseen scene:** totally new physical room/reflector/material/anchor family and untouched split, not prior Office/Corridor/MBVAR DEV. New scene needs RT or measurements and distinct independent auditor. The old observed Office is a useful DEV cross-environment negative result, not an unopened test.

## 7. Final status

Original sources untouched. A/B/C mathematics/computation PASS. Sub-tap promising as a candidate observable, but cross-pose calibration and coverage FAIL for a naive single-source bias/variance transfer. Full 3x3 measurement likelihood, 4-state/5-state online filters, physical temporal drift, original-FFD canary and independent-scene generalization NOT YET VALIDATED. Large RT was not executed. All failures remain available.
