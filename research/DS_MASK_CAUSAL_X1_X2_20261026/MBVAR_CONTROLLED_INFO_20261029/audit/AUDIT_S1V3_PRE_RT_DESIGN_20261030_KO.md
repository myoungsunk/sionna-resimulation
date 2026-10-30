# MBVAR-INFO-001 — S1V3 / AMENDMENT-008 independent design audit (pre-DEV2 outcome)

## Scope, provenance, independence

- Contract: MBVAR-INFO-001, base contract sha256 \`68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34\`, AMENDMENT-008 \`FROZEN\` as a **developer-authored/self-review** contract. Existing C1/C2 failures remain immutable.
- Reviewed source SHA: \`c4d84e02b878af9835bef09d515d45f4010caa74\`; branch \`research/mbvar-info-001-20261029\`.
- Run 40981032471 launched on 2026-10-30 00:39Z and **in progress at audit**. **No DEV2 numerical result audited at the time of authoring.**
- Audit method: independent source/contract inspection, comparison to past S0V2/C2 results and mathematical logic checks. **Not a fresh independent FFD rerun**, not an audit of as-yet unavailable DEV2 outputs, no physical RT.
- Author: separate auditor/proposer review session, not the implementer's own self-test. This document has a distinct GitHub **audit** branch; no experiment code or original result altered.
- Final pre-RT release verdict: **PENDING_EXECUTION_AND_FIXES**; HOLDOUT2 and physical RT remain **NO-GO**.

## 1. Scientifically supported / already observed

1. S0V2 (run 40863614683) reports exact Gaussian posterior parity and information-form self-check, role A LOW vs HIGH, \`DID_infl_tan=+0.4348592653\`, \`DID_infl_psi=-0.4276505375\`. This is under a known synthetic covariance/FFD LOS linearisation, not from physical ray-traced reflections.
2. S1V2 DEV failed; C2 run 40871327417 failed per preregistered C2-a and C2-d. C2 found 20/1080 P reproducibility mismatches with state errors close to zero, and two convergence-label flips; all 20 mismatches had kink poses. C2 local C* is the best of limited starts, not a global oracle.
3. A008 improves source reproducibility: \`make_inputs\` and \`S1V3_INPUTS\` receipt \`z,x0,ds_m,gy_m,taps,pose_keys,Sigma fingerprints\`; C3 checks those against regenerated arrays; alternative Jacobians A/C03/C10/C30/L/R, primary C10; fixed-scale state difference; all failures preserved.
4. A008 discloses **post-SMOKE** choice to add E' polish and relax E→E' scope bound from 0.1 to 2 d_ref; the choice occurred **before DEV2**, so it is prospective to DEV2, but not blind to prior synthetic design outcomes. \`E'\` changes MAP state, not only P; the original \`E\` estimator is preserved for paired comparison.

## 2. Source-level defects / claim limits to audit after DEV2

### F1. PROBE-OVERRIDE: smooth label can mask a negative probe (MATERIAL CODE LOGIC)

\`code/s1v3.py::class_v3(dec_A,dmin)\` returns \`CONVERGED_SMOOTH\` whenever \`dec_A <= FL.V2_DEC_TOL\`, **ignoring \`dmin\`**. \`polish()\` similarly skips probing when analytic decrement is small. The condition \`dec_A <= 1e-10, dmin < -0.01\` would be incorrectly classified smooth despite an objectively descending probe at the kink. This is possible even though no affected DEV2 row has yet been observed. **Audit-only immediate test on stored DEV2 fields:** for all batch rows with finite \`dec_A_fixed\`, assert \`!(dec_A_fixed<=1e-10 && probe_min_dcost<-0.01)\`; save count and keys. If any -> classification semantically invalid, stop before HOLDOUT2; correct using a new, prospectively locked amendment and untouched field IDs. If none -> no observed effect from this flaw on DEV2; disclose structural limit and require a kink adversarial unit fixture before HOLDOUT2.

### F2. POST-FIT PSD ≠ calibrated posterior (MATERIAL SCIENTIFIC LIMIT)

\`post_fit_P\` computes \(J_N (A_m^T A_m)^{-1}J_N^T\) at a potentially nondifferentiable final estimate for each Jacobian convention. C10 primary uses ±1cm and ±0.1° FD stencil; L/R at tiny steps. Chosen stencil scale is an engineered numerical convention, not proof of a correct posterior near piecewise-linear FFD knots. A8-5 must check kink/nonkink mean standardized errors and coverage on independent fields, and all six covariance sensitivity summaries. If material failures -> no single scientific covariance claim even if P_REPRO is perfect.

### F3. Full 4x4 NEES is analytic even when user-facing per-state P is C10

\`eval_batch()\` obtains \`_PA_end\` and calls \`V._row_from(w,Xp,PA,"A")\`, which records \`nees4\` based on **analytic** \(P_A\). \`with_P(rows,m)\` replaces only marginal \`P_{rad,tan,psi,bg}\` for each convention. Therefore any displayed \`nees4\` is NOT a C10 full-covariance NEES and must not be described as such. Add \`P_C10_end\` full matrix output and recompute \`NEES4_C10\` (and calibration CI by independent field), or restrict science verdict to per-state metrics. New code/claims require prospectively governed scope.

### F4. Ideal true-LoS tap used as known side-information

\`s1v2.setup\` computes \`w["taps"]=Wd.taps_of(w["Xtrue"],anchor)\`. \`s1v3.eval_batch\` conditions the FFD observation on those taps. The injected additive Gaussian errors apply **after** \`htrue\` is extracted, so no noisy CIR detector has generated those taps. This is a valid **ideal fixed-tap conditional synthetic experiment**, but not a deployable noisy first-path measurement. The recursive baseline calls free tap \`model.batch\`; batch/EKF performance comparisons involve a tap information/forward-model difference. Before physical RT, disclose and optionally add a matched tap-conditioned recursive baseline or a controlled \`tap_error\` sensitivity (delay/tap switch, not tuned from labels). Actual RT must extract taps from channel samples using frozen receiver detector, not from Xtrue.

### F5. PROBE_CERTIFICATION is not global-optimum proof

\`E'\` polish intentionally descends the same GN line probes down to Δcost <1e-3, while \`class_v3\` declares LOCAL_MIN_CERTIFIED if no probe decreases >0.01. These tests overlap by construction. \`PROBE_POWER\` and C3 multi-start are useful negative/stability controls but still limited. Report \`NO_DESCENT_IN_REGISTERED_PROBES\`, not unconditional mathematical optimality. \`C*\` is lowest among enumerated starts including truth diagnostic, not the global minimum.

### F6. A8-5 missing group can silently disappear

\`calibration(b)\` loops only over observed groupby \`(LH/RV,kink True/False)\`. If any registered group is empty, no result row for that stratum; \`cal_fail\` and \`cal_und\` need not become true. Gate should report 2x2x2=8 intended strata, number of independent fields and missing groups explicitly. If a stratum lacks enough fields, mark \`NOT_EVALUABLE\`, not PASS. \`mean(e²/P)\` is a valid standardized-error diagnostic but distinct from S0 \`E(e²)/E(P)\` ratio; do not equate these estimands without explanation.

### F7. Result gating and sensitivity sample selection

\`S1V3\` technical PASS requires row QA + NOT_CERTIFIED + C10 positive-definiteness + polish scope. A8-5 \`CALIBRATION_FAIL\` and A8-6 \`MULTIPLE_RESULTS_NO_SINGLE_ADOPTION\` **do not change the MANIFEST technical status**, but they prevent power calculation. Review BOTH \`S1V3_QA.json\` and \`S1V3_DECISION_DEV2.json\`; green GitHub is insufficient to authorize HOLDOUT2. The \`without_KINK_P_UNCERTAIN\` sensitivity additionally changes the analyzed sample; report this as **selection sensitivity**, separate from fixed-key Jacobian-only sensitivity. \`KINK_P_UNCERTAIN\` can be frequent even if C10 is positive definite.

### F8. End-to-end mathematical independence remains incomplete

C3 reuses \`s1v3.eval_batch\`, \`s1v3.post_fit_P\` and the same FFD source for replays. This checks deterministic regeneration, not an independent implementation of the posterior at FFD kink. Independent auditor should recompute selected adversarial rows' raw H/tap/J/P with a separately authored path, and verify input receipts and negative fixtures.

### F9. Single fixed synthetic family not representative of RT physics

S1V3 data model: \`z=h_LOS_FFD(x)+epsilon\`, \`epsilon\` = known Gaussian pose-field + time OU + white error (plus correlated range/s). True RT reflections produce pose-dependent deterministic, potentially non-Gaussian, multimodal, first-path-switching and heteroscedastic residuals. S1 holds anchor A and one FFD bank/scene, fixed 60-step windows. HOLDOUT2 uses new **field draws within that same generative family**, not independent scene variants. Therefore even fully successful HOLDOUT2 supports **controlled mechanism under the specified generative assumptions**, not physical generalisation.

## 3. Proposer option matrix

| Option | Method | Scientific added value | Status/recommendation |
|---|---|---|---|
| **A. Finish A008 DEV2→C3→HOLDOUT2** | Freeze code, inspect semantics F1, re-audit technical + A8-5/6, then run true held-out fields | Strongest clean evidence for *synthetic controlled mechanism* | **MANDATORY before claiming complete Track S**. Existing run must not be rewritten. |
| **B. Ideal-tap and robust-P bridge canaries** | Compare fixed true-tap vs simulated detector-tap; matched EKF and batch; independent P/NEES in small windows | Exposes conditional tap side-information and kink uncertainty | **RECOMMENDED** as separate pre-RT engineering bridge. Can be done after A008 audit, no need to retune primary H2. |
| **C. Replay actual historical FULL/LOS RF residuals** | Frozen r,s extractor, no tuning on outcome; fit only retrospective development, report conditional residual law, tap switches, mean/variance | Tests whether synthetic GP assumptions resemble actual RF before new RT | **RECOMMENDED diagnostic**, not independent scene confirmation; old corridor has already been examined. |
| **D. Replace bilinear FFD interpolation** | Smooth FFD generator and estimator, separate parity | Removes numerical knots but changes forward observation model | **DEFER** to separately labelled sensitivity study; not use as rescue for H2. |
| **E. Full Bayesian/piecewise posterior canary** | Small N and selected knot poses, numerical integration/importance sampling/local sampling near knots to compare Hessian P | Tests physical relevance of single-Gaussian P near non-smooth models | **OPTIONAL research-strengthening** if A8-5 fails or C10 P varies materially. |

## 4. Release criteria / representativeness statement

- **What S0V2 already represents:** analytical linear-Gaussian information/covariance predictions for selected FFD LOS Jacobians and prescribed \(\Sigma\). DID_tan +0.4349 and DID_psi −0.4277 are design predictions, not observed physics.
- **What a completed S1V3 + C3 + untouched HOLDOUT2 could represent:** the sampling distribution of that same nonlinear LOS FFD, fixed ideal tap, four windows, one anchor, specified GP/OU noise and Q/prior, comparing IID, oracle, XMODEL and recursive controls. It should report H1/H2/H3/CAL/H4 with independent field-level CIs and missing/failed rows. No exact global MAP or universal P claim.
- **What only Track R can establish:** specular ray geometry, reflected path Jones/amplitude/phase and tap selection, actual \(\Delta s\), scenario dependence, physical residual cross-time/space covariance, comparison of R5-A-like and R5-B-like mechanisms. A shared C10 plate with ≤8 tap geometric excess is a pre-RT design, not a measured \(\Delta s\). New scene variants must form independent units for generalization.

Pre-RT action gate:
1. **Await recorded DEV2 result**; inspect internal MANIFEST + QA, A8-5/6, input receipts, \`KINK_P_UNCERTAIN\` counts, old vs new class.
2. **Run C3** on DEV2 and audit all gates + F1 adversarial case. If gate FAIL, preserve outputs and stop. Any changed interpretation/criteria after seeing DEV2 requires append-only amendment and *fresh* DEV IDs; don't quietly move to HOLDOUT2.
3. **Independent audit/approval before HOLDOUT2**. If passing, confirm preregistered H1/H2/H3/CAL/H4 on unopened 5000–5059, and keep 5060–5119 unopened as reserve. Changed covariance convention and sensitivity exclusions must be reported, not optimized from test outcomes.
4. **Before RT:** physical material, solver/port/tap extraction, shared-plate geometry and exact numeric budget must have signed pre-P3 amendment. DIRECT/FLOOR/C10 canary before full production; direct tap from actual modeled complex CIR.

**Current verdict: REVIEW_PENDING_DEV2; experimental Track S has not been completed; physical RT has not started.** This is a scientific scope decision, not a declaration that all source code is invalid.
