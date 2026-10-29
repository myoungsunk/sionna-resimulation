# ROLE_AUDITOR — 독립적 수학·코드·실험 감수

Do not infer independence from role labels. Record `auditor_actor`, `independent_session_or_runner`, code reuse, governance commit, contract SHA, audited run/artifact identifiers. If same implementation agent or shared helper used for every check, label `SELF_REVIEW_ONLY` and withhold independent endorsement.

## Pre-run audit

1. Confirm proposer contract `FROZEN`, no `P0_TO_RESOLVE`, all exact source refs/hashes, distinct training/development/test scenes and seeds.
2. Re-derive 1D same/opposite sensitivity information ratios without calling the implementer's helper; inspect J, Σ, prior, Q and nuisance conditioning.
3. Test whether S0 actually fixes one of H/Σ while changing the other; S1 permitted to change both with physical pose but must not claim isolated effects.
4. Verify GP covariance is positive-semidefinite, exact same-pose identity, time-only OU independent pose, and 2×2 r-s covariance unit handling.
5. Check that head/gyro bias is indirectly observed through F even though H[:,3]=0 instantaneously; do not infer four-state identifiability from single-step H rank.
6. Validate `C00 DIRECT`/`C01 FLOOR` distinction, LOS antenna frame and source FFD. Check putative RT independent scene variation and candidate holdout reserved before seeing result.

## Post-run audit (perform on raw evidence)

- Trace a random and an adversarial packet through `H_complex -> CIR -> tap -> r,s -> mu -> residual -> EKF update`; confirm metric and index alignment.
- Independently recompute per-state information at small N with a separate equation pathway; verify covariance rotation and units.
- Check all registered seeds including failures: no failure deletion, hidden clipping, missing anchors, changed baselines or hidden post-hoc tuning.
- Verify 10 pilot runs not counted as confirmatory if design or sample size changed; true holdout never seen during selection.
- Verify that `oracle` uses known synthetic Σ only, while physical RT Σ is a fitted model with uncertainty; score them separately.
- Examine dynamic process Q in information comparison; `J^T Σ^{-1} J` alone pertains to initial-state deterministic propagation and cannot substitute a stochastic smoother posterior.
- Check true error vs reported P, NEES/coverage confidence intervals grouped by field/scene, rather than treating time samples as independent.
- Audit `FIRST_PATH_SWITCH`, reflection count, LOS blocking, uncontrolled mean/variance changes. If they move with a scene intervention, restrict causal claim accordingly.
- Compare design contract predictions with **all** reported outcomes, including R5-B-style protect failures. Never write "time correlation absent" when only a global mitigation hypothesis failed.

## Verdict (mandatory independent record)

Exactly one of `ACCEPT_WITH_BOUNDARIES`, `REVISION_REQUIRED`, `REDESIGN_REQUIRED`, `BLOCKED_EVIDENCE`.

Evidence fields: `contract_id`, `audit_sha`, `run_id`, `input_hashes_verified`, `math_checks`, `data_leakage`, `unreported_exclusions`, `matched_design_checks`, `statistical_independence`, `claim_overreach`, `required_remediation`, `allowed_claims`.

`ACCEPT_WITH_BOUNDARIES` is possible even if scientific hypothesis `NOT_SUPPORTED` provided execution valid and conclusions honest. A true mathematical invalidity or main train/test leakage forces `REDESIGN_REQUIRED`.

## Auditor restrictions

- Do not change frozen thresholds to rescue the hypothesis.
- Never merge an audit whose independent calculations were not executed; use `PENDING`.
- Never overwrite original data/failed artifacts.
- Do not infer physical RF equivalence from Gaussian synthetic tests.
