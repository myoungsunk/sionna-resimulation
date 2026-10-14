# G2/G3 B–F staged execution — pre-run source and claim audit (2026-10-14)

## Decision before cloud execution

**GO_WITH_CLAIM_LIMITATION for B/C/D/E0, F only as dependency verdict**. No production G2/G3 or recursive-pose run is authorized until B independent calibration, actual nonlinear D reference, and full one-step E are valid. Merely running a workflow or model is not scientific PASS.

User-requested source of classification: EKF4 PRE_RUN_AUDIT_POLICY_20261014_KO.md at 9beb061f354edef18e1f977f5d462d7e0d8b1f2e / Git blob df9ec6121f3f0c953e58ef8e85ce436ed9a79334.

Assistant reviewed equations and GitHub source; no independent human reviewer. Cloud independent GH-versus-RQMC checks are separate numerical paths; same helper alone is not independent validation.

## Existing verified evidence reused exactly

- Frozen signed RF and D0/D4 parity source: Run 38523237789 / artifact 11875206058 / ZIP sha256 56276ccb88605382b801f080cb97b58bc465bcff46c78677bcaf14fcd1b62bd5.
- Original scalar radial likelihood is unchanged `research/G2G3_AUDITED_MINIMAL_20261014/model.py`, Git blob `1b13e7fa1909168f3f7cb2d35d2d86d4c00cb5b9`.
- Original analytic vs numerical identity: Run 38526264898, 6/6 normalized radial and 9/9 linear 3-state; same-code reuse allowed only for same algebra, not as full G3 scientific evidence.
- Direct probability readout: Run 38527848155; 4/4 CDF vs independent integral. The current guarded rule uses the exact event p(|RF-r| < |DR-r| | z,d) and not the fault/inlier-event probability.
- Original G3 41->65 posterior TV=0.387065 is **unchanged CASE_RESULT_INVALID**, not retroactive success.
- Spatial eligibility frozen at 0.5 m: R2 and R5 held-out have zero eligible cross-route train samples. Calibrated online RF likelihood would be a **CLAIM_BLOCK**. Route-heldout summaries are descriptive rather than disjoint-scene validation.

## Source review and decision consequences

| ID | Severity | Check/question | Decision |
|---|---|---|---|
| B01 | HARD_EXECUTION_BLOCK if fail | Artifact SHA, extracted input SHA, raw RF row grain, D0/H3 coordinate alignment | stop only dependent B/E0 or D numerical reconstruction |
| B02 | CLAIM_BLOCK | Route independence and 0.5m spatial buffer leave R2/R5 uncalibrated | no certified p_RF / no external generalization; C math and D numerical can proceed |
| C01 | HARD_EXECUTION_BLOCK | Signed residual z_rf - h(x), meters, DR variance sigma_innovation² - frozen Rr, original inlier/outlier weights and support | stop affected calculation |
| C02 | CLAIM_BLOCK if contradicted | C1 nominal preserve, C2 drift rescue, C3 negative RF overcorrection preserve, C4 positive RF outlier preserve | run bounded pre-approved C controls; no retuning to fix hypothesis |
| D01 | CASE_RESULT_INVALID | GH tilted proposal uses exact target/proposal ratio, full XY-Heading cross P, same frozen S and corrected Range, independent QMC | failed cell cannot be used as full G3 posterior |
| D02 | CLAIM_BLOCK | Original GH G3 failed; tilted GH convergence alone not independent reference | require independent scrambled QMC / correct evidence before D PASS |
| E01 | CLAIM_BLOCK | E0 scalar radial shadow is NOT 3state full one-step E, and follows exactly original saved input | descriptive comparisons only |
| F01 | NOT_RUN_DEPENDENCY | Recursive 3state needs independent B plus D numerical and E full-pose validated | F records NOT_RUN honestly; does not claim no calculation possible |
| T01 | DIAGNOSTIC_DEFECT_OR_WARNING | JSON formatting metadata / plots can fail without affecting an independently verified posterior | limit to affected report and repair that path only |

## Mathematical assumptions and prohibited inference

- For a scalar range d=DR, z=RF, positive delta d-z means shorter RF. The event that RF is more accurate is r < (d+z)/2; prior posterior CDF measures this probability. This is not a claim that RF error is always nonnegative.
- Require `P_RF_better >= 0.95`, `d>z` and original `NIS>6.634896601` for a single exploratory guarded radial correction; otherwise exactly retain d. This is inherited from prior decision and is an engineering test, not independently calibrated reliability.
- On protection controls, the actual numerical estimator output must stay unchanged when the guard is not activated. A Boolean OFF alone does not prove point-estimate safety.
- No same Range in both prior and likelihood; original DR-only innovation sigma is recovered once by subtracting original Rr. No truth, injected bias label, case ID or route into online inference. Truth is permitted only after predictions for scoring.
- One anchor range does not observe azimuth or yaw; E0 radial metrics must not be represented as 2D/Heading RMSE, pose NEES, or G2/G3 posterior covariance.
- Tilted proposal is a *numerical importance change*, not an alternative physical posterior. Original prior, LUT S measurement and Rr/Rs never changed. Numerical posterior claims require TV <= .001 and MAP shift <= 0.1° and evidence agreement <= .005 across independent computation.
- Same physical RF scene is reused under DR seeds, so time/seed rows are not independent external RF environments.
- No numerical Gate below existing user constraints has been added as a new reason to prohibit unrelated diagnosis. QMC evidence check is local to the proposed numerical reference.

## Fixed execution stages and budget

1. Audit environment before importing scientific modules/dependency installation.
2. Reuse audited immutable source acquisition with its historical code hash gate.
3. Audit B then run signed route holdout descriptive calibration and frozen 0.5m spatial-eligibility check.
4. Audit C then run 4 safety fixtures on guarded radial-only correction.
5. Audit D then run original failed G3 cell under GH 9/17/25/41 with range-tilted full-support Gaussian, plus RQMC seed 1069/2099 at N=8192. Exact target-proposal ratio is mandatory.
6. Audit E0 then run archived 223236-row radial-only *shadow*; do not claim it is full G2/G3 E.
7. Audit F then emit strictly dependency-based full-state recursive NOT_RUN when not eligible.
8. Preserve all numerical receipts including failed cases, original 195.6s failure unchanged.

Stage C/D unexpected results trigger a bounded evidence comparison; re-fitting or changing model assumptions requires a new amended contract and direction confirmation. Run-time implementation/diagnostic defects may be repaired with a fresh source-hash audit, not by quietly modifying thresholds.

## Execution source control

APPROVAL.json must be the **last trigger file**; the GitHub workflow listens to its push path only. It contains expected reviewed Git blob hashes for CONTRACT/stages/tilted_g3/audit/workflow plus the immutable original model/gate/acquire. For every stage the runner verifies executed Git blob and source SHA, and writes an explicit `PRE_RUN_STAGE.json` before that computation; `audited_code_matches_execution_sha` becomes true only at runtime.

Initial scientific_PASS=false. The run decision is **GO_WITH_CLAIM_LIMITATION**, not `B PASS` or `F PASS`.
