# AMENDMENT-003 — post-freeze redesign after the independent audit (REDESIGN_REQUIRED)

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 FROZEN (sha256 `68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34`). The contract file is **not edited**. This amendment overlays its lock. |
| Governance | `250d617ad89a4105fa1af546cc83ceed9de98f42` |
| Trigger | Independent audit of 2026-10-29 (user-supplied): verdict `REDESIGN_REQUIRED`, P3 `NO-GO` |
| Author role | IMPLEMENTER under the user directive of 2026-10-29 18:17 KST ("감사 결과 바탕으로 재구현 - 검증"); **SELF_REVIEW_ONLY** |
| Results seen before this amendment | Everything up to and including S1 HOLDOUT run `40845647224` (fields 1000–1059) and the audit. |
| Seen after drafting the rules, before the geometry v2 / plate / revisit rules below were fixed | Only the local optimizer diagnostics of §A, on SMOKE field 900 (old geometry). **No new-geometry window, plate or revisit quantity has been computed.** |
| Preserved | Every earlier run directory, contract text and amendment, unchanged. |

## 0. Status of earlier evidence

- **S1 HOLDOUT 1000–1059** is opened. It is demoted to `POST_HOC`: usable for descriptive or post-hoc re-analysis only, never confirmatory.
- DEV 0–9 stays DEV (pilot/power only).
- A new confirmatory split **HOLDOUT2 = 5000–5059** is reserved, with reserve 5060–5119.
- The RNG root stays the frozen contract sha256, so the old DEV inputs can be regenerated exactly (§A). New field ids are independent draws.

## A. Batch estimator (audit finding 1)

### A.1 Diagnosis on SMOKE field 900 (old geometry, before this text was final)

- `batch_map` v1 stopped at points that are not optima. For the same input, the v2 optimizer reaches a cost lower by up to 0.11 χ², and the final state moves by up to 1.9 cm.
- The deeper cause is that the FFD observation `h_s` is **discontinuous**. When the first-path detector's tap index changes (the leading-edge threshold inequality is active; margin 1e-14 at the stalled pose), `s` jumps.
- At one stalled point the cost rose by **+1.52 χ²** for an infinitesimal step. The optimizer had parked a pose exactly on a tap boundary.
- What remains after removing the jumps are continuous kinks from the 1° bilinear pattern grid. There, LM stalls with Newton decrement ≤ 5e-3 and a remaining state shift ≤ 0.05 posterior sd.

### A.2 New estimator rules (frozen by this amendment)

1. **`batch_map_v2`** (`code/filters.py`; v1 kept byte-identical for reproduction):
   - Levenberg–Marquardt over θ = (x0, v_1..v_{N−1}).
   - A step is accepted **only if the cost strictly decreases**; on rejection λ is multiplied by 10.
   - `max_iter = 100`, λ_max = 1e12.
   - Recorded per run: final cost, initial cost, Newton decrement δ² = gᵀN⁻¹g, scaled gradient ∞-norm, last step ∞-norm, accept/reject counts, λ, and stop reason.
2. **Convergence classes**:
   - `CONVERGED`: δ² ≤ 1e-10.
   - `CONVERGED_NONSMOOTH`: stopped by λ saturation or the iteration cap, with δ² ≤ 0.05 **and** the remaining Gauss–Newton state shift at the window end ≤ 0.1 posterior sd for every state.
   - `NONCONVERGED`: anything else.
   - All rows are kept.
   - QA: `NONCONVERGED` ≤ 1 % per (arm, window, cell).
   - The H-tests use all rows. A sensitivity analysis restricted to `CONVERGED` rows is reported.
3. **Tap-conditioned observation model for the batch arms** (`IID_BATCH`, `ORACLE_CORR_BATCH`, `XMODEL_BATCH`):
   - `h(x; k)` evaluates the frozen FFD chain with the first-path tap index fixed to the index **reported by the detector for that packet**.
   - The detector index is an observable of the receiver, not truth.
   - In Track S the detection is noise-free, so k equals the tap at the true pose. Noise is added after detection, which is the frozen generator definition.
   - Parity: equal to `SourceFFD.batch` (h and H) when k is the model's own tap.
   - The EKF arms keep the original free-tap model as the deployable baseline. They are descriptive only.
4. **Verification phase C1** (old geometry, old DEV fields 0–9, old ledger; regenerated inputs). All criteria below are pass/fail:
   - C1-a: the regenerated inputs plus v1 reproduce the stored `S1_RESULTS_DEV.csv` of run `40844896963` (all `e_*`, `P_*`, `nees4`) within 1e-9 absolute. This proves the inputs are identical.
   - C1-b: final cost of v1 vs v2 (free tap) vs v2 (tap-conditioned); report the distribution of cost(v1) − cost(v2, free tap). Pass if v2's cost is ≤ v1's in every case, within 1e-9.
   - C1-c: v2 tap-conditioned with `max_iter` 100 vs 300. Pass if `CONVERGED` runs agree to ≤ 1e-8 in state, and the class distribution is reported.
   - C1-d: multi-start from the true θ (true x0, true control perturbation). Pass if `CONVERGED` runs agree in cost to ≤ 1e-6 and in window-end state to ≤ 0.01 posterior sd; `NONSMOOTH` runs are reported.
   - C1-e: near-linear exact-posterior test. Affine h (truth Jacobian), all covariances scaled by κ = 1e-8. Pass if the v2 mean is within 1e-3 posterior sd and the covariance within relative 1e-3 of exact linear-Gaussian conditioning.
   - C1-f: NONCONVERGED fraction (tap-conditioned v2) ≤ 1 %.

## B. Geometry v2 (audit problem A) — objective = the registered interaction

Candidate paths. All use anchor A and C, yaw = path tangent, 0.05 m arc-length spacing, x = 2 → 10 m, and non-overlapping windows N = 60 at starts 0, 60, 120, …:

- Lines `L_y{c}`: y = c, c ∈ {5, 6, 7, 8, 9}.
- Sinusoids `S_c{c}_A{A}_W{λ}`: y = c + A sin(2π(x−2)/λ), with c ∈ {5.5, 6.5, 7.5}, A ∈ {0.4, 0.8, 1.2}, λ ∈ {4, 8}.
- Diagonals `D_{d}`: y = −x + d, d ∈ {12, 14}; only poses with 2 ≤ x ≤ 10 and 0.5 ≤ y ≤ 11.5.

Validity rules:
- Unchanged: |h_s| ≤ 0.7; AMENDMENT-002 smoothness (≤ 5 % kink poses); positive information ratios; room, plate and LoS checks as in P0.
- Pairs: range median and IQR differences ≤ 0.5 m, no shared pose indices, distinct windows.

Selection:
- Predicted interaction, from the S0 JOINT design with the frozen S1 parameters: DID_a = log infl_IID(LOW, POSE_HIGH) − log infl_IID(HIGH, POSE_HIGH). LOWCORR inflation is exactly 1.
- LOW/HIGH labels follow G (lower G = LOW).
- **Primary state ψ.** Choose the pair with max |DID_ψ| subject to |DID_ψ| ≥ log 1.5. Tie-break: larger |DID_tan|, then lexicographic.
- tan is secondary: testable iff |DID_tan| ≥ log 1.25.
- If no pair qualifies → `BLOCKED_INTERACTION_UNTESTABLE`, and S0v2/S1v2 do not start.

## C. Revisit experiment (audit problem C)

- **Path.** Forward then reverse along a straight line on the same poses (differential drive driving backward). REV60 = forward p0…p30, then back p29…p1, so poses p1…p29 are revisited at a later time with the same yaw. FWD60 = forward p0…p59 from the same start.
- **Candidates.** Lines y ∈ {7, 6, 8}, start x ∈ {3.0, 4.0, 5.0, 3.5, 4.5}, anchor A, yaw 0. The first, in that nested order, whose REV60 and FWD60 both satisfy the §B validity rules is chosen.
- **Cells.** LOWCORR, POSE_HIGH (0.7, 0, 0.3), TIME_HIGH_5 (0, 0.7, 0.3; τ = 5 s). Marginal variances are identical across cells.
- **Arms.** `IID_BATCH`, `ORACLE_CORR_BATCH`, `XMODEL_BATCH`. XMODEL is the wrong kernel with identical marginals: POSE data with the TIME_HIGH_5 model, and TIME data with the POSE_HIGH model.
- **H4a (QA).** At revisited poses the pose component is identical (max diff = 0) and the time component is not (max diff > 0).
- **H4b.** S0 sandwich inflation of XMODEL, separability SEP_a = log infl_X(REV) − log infl_X(FWD) per data cell.
  - Testable iff |SEP_S0| ≥ log 1.25.
  - S1 test: H2 rule (CI excludes 0 on the predicted side; FAIL if the upper bound < 0.5 |SEP_S0|).
  - IID and XMODEL inflations must also reproduce S0 under the H1 equivalence rule (reported as `H4_REPRO`).

## D. Reflector redesign (audit problem B) — geometry only, no RT

For each selected window (LOW, HIGH, REV60), one plate per scene variant:

- **Candidates.** Vertical rectangle, length L ∈ {2, 3, 4} m, z ∈ [0, 2.7] m. Centre on a 0.25 m grid with ≥ 0.3 m wall margin. Orientation C10 = mean path heading of the window rounded to 15°; C11 = C10 + 45°.
- **Constraints.**
  - The plate does not cut the anchor–robot LoS at any window pose (3-D height check).
  - Plate-to-footprint distance ≥ 0.10 m.
  - Plate ≥ 0.5 m from the anchor horizontally.
- **Objective.** Fraction of window poses whose first-order specular point (anchor image across the plate plane) lies inside the plate, ≥ 0.10 m from the vertical edges, with z ∈ [0.10, 2.60] m.
  - Maximise the fraction; tie-break shorter L, then smaller centre-to-path-centroid distance, then lexicographic (cx, cy).
  - Accept if ≥ 0.95, else `NOT_AVAILABLE` for that variant.
- **Reported, not used in the choice.** Specular excess path length, its excess delay in 4×-zero-padded tap units, and the incidence angle.

## E. RF cache key (P1)

`code/rt_keys.py::rf_cache_key()` hashes the canonical JSON of:
- the scene mesh/material/plate geometry hash
- anchor xyz
- the pose (canonical yaw)
- robot z and mount
- the FFD bank sha256 set
- solver name and version
- max depth and the remaining solver flags
- the frequency grid hash
- the observation-extractor settings hash

Pure function, unit-tested, not yet used for any RT.

## F. Q consistency (P1)

Per run, report max_k |q(ds_meas)/q(ds_true) − 1| (generator uses the true |ds|; estimators use the measured |ds|). Also report the S0 sensitivity: predictions recomputed with q(ds_meas), the max relative change of infl over DEV canary inputs. Report only.

## G. Canary traces (P1)

DEV field 0, sensor seed 0, every window and cell, every arm. Per-time CSV:
- EKF arms: prior and posterior state with diag P, z, h, H, innovation, S, K, NIS, used.
- Batch arms: final state, diag P, whitened residual, tap index.

## H. S1v2 decision rules

- H1, H3 and CAL rules are as frozen.
- H2: ψ is primary and testable by construction (§B); tan is secondary.
- **Verdict:**
  - Any H1 FAIL → NOT_SUPPORTED.
  - Any H1 UNDETERMINED → INCONCLUSIVE.
  - H1 all PASS, then:
    - H2-ψ, every applicable H3 and CAL all PASS → SUPPORTED.
    - Otherwise, any PASS or FAIL among them → MIXED.
    - Else INCONCLUSIVE.
  - H4 is reported as its own registered result and does not change the H1–H3 verdict.
- Power rule as frozen, applied to the DEV pilot. n_confirm ∈ {30, 60} = first ids of HOLDOUT2.

## I. Not changed

RT stays blocked (MATERIAL, DIRECT_PARITY_TOL, RF_BUDGET, Track R effect sizes). No canary or bulk RT runs without a signed pre-P3 amendment and a numeric user-approved budget.

## AMENDMENT_LOCK

Appended after the P0-GEO2 / C1 run resolves §B–§D. Until then this amendment is DRAFT and S0v2/S1v2 cannot run.
