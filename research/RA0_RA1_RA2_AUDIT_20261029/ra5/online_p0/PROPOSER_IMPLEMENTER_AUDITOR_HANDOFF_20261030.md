# RA5-ONLINE-P0 role handoff and implementation audit

**Status**: implementation files and CI workflow committed; GitHub Actions currently QUEUED; scientific audit **NOT ACCEPTED**.
**Role routing reviewed (actual GitHub docs)**: root AGENTS, COMMON_CONTRACT, ROLE_PROPOSER, ROLE_IMPLEMENTER, ROLE_AUDITOR, CI_REQUIREMENTS, original MBVAR-INFO-001 experiment contract, SourceFFD and RA4 original filter source.
governance_git_sha = 250d617ad89a4105fa1af546cc83ceed9de98f42
base_git_sha = bfff111357ffd54baa2627dfda01df99548a6cd9
source_data_git_sha = 9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13
contract_id = RA5-ONLINE-P0-20261030 (DRAFT, RETROSPECTIVE ENGINEERING)
Frozen MBVAR-INFO-001 contract not edited; this task is not its S0/S1/R confirmatory phase.

## PROPOSER role — estimands and limits

- Preserve historical native BB_ORIG h/z/mu/R/BASE mask exactly and use full state/P parity, not only RMSE.
- Interventions SUB2_CAL and SUB3_JOINT use **same** original Full-H complex-port measurement for r_frac,s0,ds1; train-only mean and R model of the NEW observer, with geometric/relative-yaw features computed from the EKF's OWN prediction in evaluation. Correct range expected value is the *SourceFFD fractional-crossing detector* plus learned bias, not the old continuous distance+B_OLD.
- Tap switching has (A) deterministic Full minus LoS model discrepancy and (B) noisy vs clean first-edge detector random flip. They are different estimands: no conflation of P(delta_tap|quality) with physical independent observation. Categorical random-flip model can be fitted on synthetic assumed noise without online access to true clean Full H.
- Joint covariance R_{r,s0,ds1}: estimate train-only from full-minus-LoS deterministic residuals on two OTHER routes, 15% fixed diagonal shrink; quality bin dependence and full offdiagonal preserved, no artificially positive-definite duplicate.
- Confirmatory real receiver R or state information improvement NOT claimed. Independent scenes remain one Corridor; R2/R4/R5 and gyro levels are repeated observations in the same scene. Existing Office previously observed DEV.
- BASE_FIXED and SELF_NIS are separate policies; same state/P/source/control, with 2-DoF chi-square 9.210340371976184 and 3-DoF 11.344866730144373 respectively. Deterioration is valid evidence.

## IMPLEMENTER role — committed code and execution

- online_observer.py: native first-edge and fractional crossing, source model 3×4 Jacobian, prior-only geometry bias features, categorical switch and full covariance with structural rank rejection before shrinkage.
- run_prior_joint_canary.py: 7 original SHA verified H+SAMPLES, B0 original control parity; 5 other-route source H cases form train for R4B/R5A; source-fold bias and 3x3 joint R; SUB2/SUB3 paired BASE_FIXED/SELF_NIS, Joseph P, state/P/mask/innovation trace, 30sec scorings, first-mask prior check, no GT argument in run_online.
- p0_mechanical_fixtures.py: separate source fractional Jacobian test, degenerate covariance negative test, exact information-equivalence test, prior argument absence check.
- tap_switch_conditional_mc.py: noisy-tap vs clean-tap conditional model train one original saved-H pose/test another; same complex noise, wrong-tap and invalid sample denominator fully retained.
- .github/workflows/ra5-online-p0-unit.yml, ra5-online-p0-recursive-canaries.yml, ra5-online-p0-tap-noise-switch.yml; original H/FFD bank SHA and DRAFT hash checked in workflows; artifacts always uploaded; no RT called.

## AUDITOR role — independent red-team checks before science release

An actual separate auditor has **not** run. A new reviewer must independently, without importing the implementation's observer/covariance/gate helpers:

1. Independently compute first 30 native r/s packets from saved complex H (257 frequency bins, Hann, IFFT ×257, 4× zero-pad, strongest-port 30% threshold, shared n0) and compare to original source packet.
2. Recreate one fractional crossing and its x/y/yaw Jacobian from complex FFD using independent centered FD, check tap/peak/port switching cases and source source-J interpretation.
3. Recompute full 3×3 R from raw train residuals, check unit m/1/1, PSD, off-diagonal, FULL-vs-LOS and switching strata, and verify exact transform [r,s0,s1] vs [r,s0,s1−s0]. Deliberately duplicate a column and ensure structural reject before shrinkage.
4. Verify train vs held route IDs and that filter update never receives test pose/GT, oracle mu/r or test route coefficients. The observer's source spectrum uses the *prior x*, not the scoring GT.
5. Trace random plus R4-B/R5-A first discrepant packets through rho,sigma,R,K,x,P,Joseph update and mask. Compare original BB_ORIG entire x/P to frozen exp_pb within 1e-10.
6. Verify first divergence for same arm BASE_FIXED vs SELF_NIS has same pre-update prior, R, source z and mean, with only policy change. Recompute performance from t>=30s, heading units, XY NEES/95% coverage and all excluded/invalid rows.
7. Independently validate noise categorical conditional p(switch|SNR,jitter,observed quality): confirm clean-H teacher labels used only for TRAIN/SCORING, test labels not used to fit or gate. Report Brier and logloss alongside raw counts.
8. Verify manifest includes code, source, config, run IDs, all input/output file SHA, failure runs and no protected path changed. Explicitly note independent RF-scene denominator = 1, and no science/RT release.

**Scientific review status**: PENDING_SEPARATE_AUDITOR. No same-agent score is an independent verdict. If a numerical or source-data failure occurs, mark FAIL, retain artifacts and STOP dependent science claims.

## Release and implementation checklist

| Deliverable | Engineering check | Science verdict |
|---|---|---|
| A: prior-only mean with true fractional crossing model | GitHub Actions unit and canaries (queued at handoff) | NOT RELEASED |
| B: tap quality conditional discrepancy distribution | source-only train/cross-route diagnostic | NOT RELEASED |
| C: source-noise conditional switching distribution | synthetic assumed receiver, train pose/test pose | NOT RELEASED |
| D: full empirical 3×3 R with cross terms | no actual receiver R calibrated; train-only Full-LoS effective covariance | NOT RELEASED |
| E: recursive 4-state SUB2/SUB3 fixed-vs-self | parity run pending; independent auditor pending | NOT RELEASED |
| F: 5-state or new physical RT canary | Not authorized by this DRAFT contract | NOT_RUN |

No source modification, no data moves or deletions. Next exact commands are in the workflows; execution depends on successful runner and source artifact QA.
