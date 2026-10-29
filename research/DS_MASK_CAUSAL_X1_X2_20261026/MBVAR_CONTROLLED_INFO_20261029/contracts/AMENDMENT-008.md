# AMENDMENT-008 — post-fit covariance/convergence diagnostics at FFD kinks (Option 1, conditional), fresh DEV2

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 FROZEN (`68d73bd2…`) + AMENDMENT-003…007. Nothing earlier is edited. |
| Trigger | C2 run `40871327417` = FAIL; independent audit `audit/mbvar-info-c2-40871327417-20261030` (commit `a03cbc1b`), REVISION_REQUIRED, Option 1 conditional |
| Author role | IMPLEMENTER, **SELF_REVIEW_ONLY** |
| Status of this text | Formulated **after** the C2 evidence. It is engineering/exploratory until evaluated on untouched DEV2. **All acceptance rules below are fixed before any DEV2 result.** |
| Preserved, unchanged | A007 C2 FAIL, original-rule C1 FAIL, S1V2 DEV FAIL runs `40864089916` / `40867939262`, every earlier run |
| Splits | **DEV2 = 10–19** (new, unopened). HOLDOUT2 5000–5059 and reserve 5060–5119 stay **unopened**. |
| Terminology correction | The earlier report's "bit-identical" claim is withdrawn. C2 states and costs agree at the 12-significant-digit CSV precision; bitwise equality of the binary arrays was not verified. |

## 1. What does not change

- The measurement model: tap-conditioned FFD with bilinear pattern interpolation, in both generator and estimator.
- The MAP objective and the optimizer `batch_map_v2_ms` (multi-start + rescue).
- The selected basin, state and cost.
- Option 2 (smooth interpolation) is **deferred** to a separately labelled alternate synthetic model.

## 2. Post-fit covariance at the fixed MAP estimate (A8-3)

At the final θ̂ of E, the posterior is recomputed with the same Gauss–Newton/Laplace formula P = J (AᵀA)⁻¹ Jᵀ. Only the observation Jacobian H(X̂) differs between methods:

| Method | Definition | Notes |
|---|---|---|
| `A` | analytic, the current within-cell derivative | |
| `C03` / `C10` / `C30` | central FD with step s·(1 m, 1 m, 0.17453 rad, 1e-6 rad/s), s = 3e-3 / 1e-2 / 3e-2 | `C10` = the rescue step |
| `L` / `R` | backward / forward one-sided FD, s = 1e-7 | approximate the left and right derivatives at a kink |

- **Primary convention: `C10`.** This is a *numerical convention*, **not** a validated posterior. Validation is A8-5.
- **Per row stored:** window-end rotated diag P for every method, the PSD check of every end block and of AᵀA, cond(AᵀA), and `rel_spread = max_states max_m |P_m − P_C10| / P_C10`.
- `KINK_P_UNCERTAIN` = `rel_spread > 0.05` or any non-PSD.
  - 0.05 is fixed now. It is one eighth of the ±log 1.5 equivalence margin.
  - Flagged rows are kept. The H-tests are reported with and without them (A8-6).

## 3. Convergence classification without P (A8-4)

- **Old A007 class** (GN shift / √P_A): still computed and reported, not gating.
- **New class v3:**
  - `CONVERGED_SMOOTH`: analytic Newton decrement at θ̂ ≤ 1e-10.
  - Otherwise, apply an **objective probe** at θ̂. It uses cost values only, never P:
    - (i) **GN line probes**: θ̂ + α·s_m for every Jacobian convention m of §2, where s_m = (A_mᵀA_m)⁻¹A_mᵀb is that convention's Gauss–Newton step and α ∈ {1, 0.5, 0.1, 0.01} (24 probes).
    - (ii) **Random probes**: 8 random direction pairs (±), drawn from a fixed seed per row key. They use a fixed external scale independent of P (x0 components × √diag(P0), v_k components × √q_k) and radius ρ = 0.01.
  - `LOCAL_MIN_CERTIFIED`: no probe lowers the cost by more than τ = 0.01 χ².
  - `NOT_CERTIFIED`: some probe does.
- **Also recorded:** the minimising probe label, accepted-step count, cost descent (start-0 → final), and the multi-start record.
- **Power control (C3 `PROBE_POWER`):** at each row, θ̂ is displaced along a random prior-scaled direction until the cost rises by ≈1 χ² (accepted range 0.5–2). The displaced point must classify as `NOT_CERTIFIED`.
- XMODEL's large χ² is **not** by itself a wrong-basin indicator.

### Pre-freeze engineering note (old DEV data only; DEV2 untouched)

Before this text was frozen, the post-fit code was smoke-tested locally on a few C2 rows of DEV fields 0–9: the 4 NONCONVERGED rows plus a sample of others.

- The A007 class of one NONCONVERGED row came out `CONVERGED_NONSMOOTH` in the local environment. This is the same class-label instability as C2.
- Final costs differed from the C2 CSV by ≤ 4e-6 χ² across environments (local Python 3.13 vs CI). The C3 tolerances below apply within the pinned CI environment.
- A first probe design that used random directions only was judged under-powered: a point ~0.5 posterior sd from the optimum would pass. The GN line probes (i) and the `PROBE_POWER` control were added for this reason.
- No threshold was tuned to make these rows pass.

## 4. Input receipts (A8-1) — every (field, role, cell, sensor)

- Stored float64 arrays: z, ds_m, gy_m, x0, the tap vector.
- Stored fingerprints: pose-key sha256 list; Σ_true and each arm's Σ_model, as trace, Frobenius norm and a fixed 64-vector projection Σ·r.
- Saved as a NumPy `savez_compressed` archive `S1V3_INPUTS_<split>_<tag>.zip`, which is published. The `.zip` name keeps it outside the repository's git-LFS rule for `*.npz`, so CI checkouts get real bytes rather than pointers.
- The C3 verification regenerates the inputs and compares them component by component.

## 5. Gates

### P2_S1V3 on DEV2 (technical QA; must PASS to compute power)

- The S1V2 QA items: rows, failures, Mahalanobis, revisit identity, time differs.
- **Original per-cell rule applied to the new class:** `NOT_CERTIFIED` ≤ 1 % per (arm, window, cell), i.e. 0 of 30. Pooled is reported and is **not** a substitute.
- Old A007 class per-cell result reported in parallel.
- Primary (`C10`) P PSD in every row.

### P2_C3 verification on DEV2 (technical; gates HOLDOUT2 eligibility together with the re-audit)

| Gate | Requirement |
|---|---|
| **INPUT_REPRO** | z ≤ 1e-9 abs; ds_m, gy_m, x0 ≤ 1e-12 abs; taps exact; pose keys exact; Σ fingerprints rel ≤ 1e-12. All records. |
| **STATE_COST_REPRO** | window-end state difference ≤ 1e-6 × fixed scale d_ref = (2 cm, 2 cm, 0.25°, 0.01°/s); \|Δcost\| ≤ 1e-6 χ²; same `ms_best_k`. All rows. |
| **P_REPRO** | primary `C10` diag P rel ≤ 1e-3. All rows. Analytic P reproducibility reported. |
| **STATUS_REPRO** | new class v3 identical in all rows (old class change count reported) |
| **NO_WRONG_BASIN** | cost(E) − C* ≤ 1 χ² for all rows. C* is the best of E and the same 10 starts as C2, so this is a bounded search, not proof of a global optimum. |
| **STATE_STABILITY_FIXED** | \|X_E − X_best\| ≤ 1·d_ref in ≥ 99 % of rows per arm, and ≤ 2·d_ref always (externally fixed scale). The P-normalised version is reported. |
| **ITER_CAP** | for every row whose old class ≠ CONVERGED: re-run E with max_iter 300; window-end state change ≤ 0.1 × d_ref (fixed scale) |
| **LINEAR_EXACT** | affine h (constant H) on the real LOW-window controls: every convention's P within 1e-3 rel of the analytic-H Gauss–Newton P, all PD. Also unit-tested at the H level. |
| **PROBE_POWER** | the displaced-point negative control of §3 is `NOT_CERTIFIED` in ≥ 99 % of rows |
| **KINK_FIXTURES** | piecewise-linear h with left/right slopes 2/5: `L` → 2, `R` → 5 (±1e-6), `C10` → 3.5 (±1e-9). A quadratic smooth control: every FD convention within 1e-6 of the analytic H. Checked in pytest and again in the C3 aggregate. |
| **F7 fix** (reported) | `truth_start_worse_than_E_frac` computed on XMODEL rows only; the all-arm value is reported separately |

### Statistical consistency (A8-5) — scientific gate, not technical

- **Data:** ORACLE arm (true Σ), primary P.
- **Strata:** {kink at E, no kink} × window group {LH, RV} × {tan, psi}.
- **Statistic:** mean(e²/P) with a field-bootstrap CI; coverage of |e|/√P ≤ 1.96.
- **CALIBRATION_FAIL** if the CI of log mean(e²/P) is disjoint from ±log 1.5 (band rule) in any stratum. This keeps the scientific verdict on hold regardless of numerical reproducibility.
- UNDETERMINED is reported.

### Sensitivity (A8-6)

- H1/H2/H3/CAL/H4 (pilot level on DEV2) are computed with each P method, and with and without `KINK_P_UNCERTAIN` rows.
- If any verdict differs across methods, the result is `MULTIPLE_RESULTS_NO_SINGLE_ADOPTION`.

## 6. Afterwards

- **Pass:** DEV2 power then defines n for HOLDOUT2. HOLDOUT2 opens **only after** an independent re-audit of the S1V3 + C3 evidence.
- **Failure:** stop and report. Fixing would require a new amendment and fresh fields.
- P3 RT stays NO-GO.
- CI: an internal FAIL ends the workflow red (A007 R5).

## AMENDMENT_LOCK

