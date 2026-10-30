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

## 1. What does not change, and the one estimator addition

**Unchanged:**
- The measurement model: tap-conditioned FFD with bilinear pattern interpolation, in both generator and estimator.
- The MAP objective and the optimizer `batch_map_v2_ms` (multi-start + rescue), called **E**.
- Option 2 (smooth interpolation) is **deferred** to a separately labelled alternate synthetic model.

**Addition — E' = E + polish** (user decision 2026-10-30, taken before any DEV2 result; see §3 note):
- When E ends with an analytic Newton decrement > 1e-10, the polish starts from θ̂_E.
- Each step takes the best descending probe of §3: the GN steps of all six Jacobian conventions × α, plus random prior-scaled directions.
- A step is accepted only while it lowers the cost by more than 1e-3 χ². At most 30 steps are taken.
- The polish is deterministic, using a seed from the row key.
- The objective, the basin and the multi-start are untouched. The polish only descends within the basin E found.
- **A8-2 scope bound (gating in S1V3 QA):** in every row, the window-end change E → E' ≤ 2·d_ref, and the cost decrease ≤ 1 χ². These are the same tolerances C3 already uses for "the same solution": the STATE_STABILITY_FIXED maximum and NO_WRONG_BASIN. A larger change counts as outside Option 1's scope, and QA FAILs.
  - *History:* first proposed as 0.1·d_ref / 0.1 χ². In SMOKE, the stalled row's polish reached C* exactly (Δcost 0.047 χ²) while moving 1.06·d_ref (≈ 2 cm along a flat direction, ≈ 0.23 sd). The user then chose (2026-10-30) to tie the bound to the existing C3 tolerances. **This bound was set after seeing that SMOKE row.** It is not derived from DEV2, and no DEV2 data exist.
- Both are reported: E (`xendE_*`, `cost_E`, old A007 class) and E' (`xend_*`, `cost`, class v3, all P conventions, errors). All analyses use E'.

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
- A technical SMOKE run (fields 900/901, reduced design; SMOKE ids are never used for decisions) found 1 of 48 batch rows `NOT_CERTIFIED`. That was REV60 POSE_HIGH ORACLE, where E stopped by `NONCONVERGED_LAMBDA` at a kink. The C30 GN step lowered the cost by 0.0136 χ², and the C3 start grid found a point 0.047 χ² lower, 1.02·d_ref away. So E can stall at a non-minimal kink point. Two responses were possible: keep τ = 0.01 and the per-cell rule, which would very likely FAIL DEV2; or add the polish of §1. The user chose the polish (2026-10-30). Changing τ was rejected as threshold tuning.
- No threshold was tuned to make these rows pass.
- **Consequence for interpretation.** After the polish, the GN-line part of the class-v3 probe is satisfied by construction down to 1e-3 χ². What remains independent is (a) the random probes, which use a seed different from the polish, (b) the 30-step cap, (c) the A8-2 E → E' bound, (d) the C3 start grid (NO_WRONG_BASIN, STATE_STABILITY_FIXED), and (e) `PROBE_POWER`.

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
- A8-2: every row within the E → E' scope bound (§1). The number of polished rows, the cap hits, and the cross-table of old class → class v3 are reported.

### P2_C3 verification on DEV2 (technical; gates HOLDOUT2 eligibility together with the re-audit)

| Gate | Requirement |
|---|---|
| **INPUT_REPRO** | z ≤ 1e-9 abs; ds_m, gy_m, x0 ≤ 1e-12 abs; taps exact; pose keys exact; Σ fingerprints rel ≤ 1e-12. All records. |
| **STATE_COST_REPRO** | E': window-end state difference ≤ 1e-6 × fixed scale d_ref = (2 cm, 2 cm, 0.25°, 0.01°/s); \|Δcost\| ≤ 1e-6 χ²; same `ms_best_k`. All rows. Raw E reported. |
| **P_REPRO** | primary `C10` diag P rel ≤ 1e-3. All rows. Analytic P reproducibility reported. |
| **STATUS_REPRO** | new class v3 identical in all rows (old class change count reported) |
| **NO_WRONG_BASIN** | cost(E') − C* ≤ 1 χ² for all rows. C* is the best of E' and the same 10 starts as C2, so this is a bounded search, not proof of a global optimum. |
| **STATE_STABILITY_FIXED** | \|X_E' − X_best\| ≤ 1·d_ref in ≥ 99 % of rows per arm, and ≤ 2·d_ref always (externally fixed scale). The P-normalised version is reported. |
| **ITER_CAP** | for every row whose old class ≠ CONVERGED: re-run E' with E at max_iter 300; window-end state change vs E' ≤ 0.1 × d_ref (fixed scale) |
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

## 5b. Pre-freeze technical end-to-end (SMOKE 900/901, reduced design, local; not evidence)

- Reduced design: 2 LH cells, sensor 0. 48 batch rows plus EKF rows; an in-memory lock.
- **S1V3 aggregate:** QA PASS. 1 polished row, within the final A8-2 bound. Class v3: 32 `CONVERGED_SMOOTH`, 16 `LOCAL_MIN_CERTIFIED`. A8-6 consistent across the six conventions.
- **A8-5:** `CALIBRATION_FAIL` in the RV-kink-tan stratum, at n = 3. Recorded as a pipeline check only. The rule is unchanged, and on DEV2 it decides.
- **C3:** all gates PASS (rows, input/state/P/status reproducibility, basin, stability, ITER_CAP, PROBE_POWER 100 %, LINEAR_EXACT, KINK_FIXTURES).
- These SMOKE outputs live in a scratch directory. They are not committed evidence and are never pooled.

## 6. Afterwards

- **Pass:** DEV2 power then defines n for HOLDOUT2. HOLDOUT2 opens **only after** an independent re-audit of the S1V3 + C3 evidence.
- **Failure:** stop and report. Fixing would require a new amendment and fresh fields.
- P3 RT stays NO-GO.
- CI: an internal FAIL ends the workflow red (A007 R5).

## AMENDMENT_LOCK

```json
{
 "status": "FROZEN",
 "amendment_id": "AMENDMENT-008",
 "frozen_utc_date": "2026-10-30",
 "base_contract_sha256": "68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34",
 "amendment_text_sha256": {
  "AMENDMENT-003": "a94fea6dfbedf34783eed34c76b04d67297698cdec3f1d914303e6f05a1ee6a4",
  "AMENDMENT-004": "a188245a2c827312ffd3f1775bfdc63c8a66a0aca66bd62d64b231489ce51c60",
  "AMENDMENT-005": "0cf11f09cec8e1d4d09509fa9b3a37a9377d167b3c8650a84ed84b0a5b393401",
  "AMENDMENT-006": "0244c8b6f68184f6c0e9e50039f5522eff0d4eb64c6d58c4a7985775a4dd0201",
  "AMENDMENT-007": "1ce644983fb2f57383aa856e6e662297c5ceb71544b72c0ea7c77f4b3197af68"
 },
 "trigger": {
  "c2_run": "40871327417",
  "c2_status": "FAIL",
  "audit_branch": "audit/mbvar-info-c2-40871327417-20261030",
  "audit_commit": "a03cbc1b",
  "audit_verdict": "REVISION_REQUIRED (Option 1 conditional)"
 },
 "reviewer_status": "SELF_REVIEW_ONLY; independent re-audit required before HOLDOUT2",
 "resolved": {
  "ORIGINAL_RULE_JUDGEMENTS_PRESERVED": {
   "C2_run_40871327417": "FAIL",
   "C1_run_40857100181": "FAIL",
   "S1V2_DEV_run_40864089916": "FAIL",
   "S1V2_DEV_run_40867939262": "FAIL"
  },
  "A8_ESTIMATOR": {
   "E": "filters.batch_map_v2_ms, unchanged",
   "E_prime": "E + polish when analytic Newton decrement > 1e-10: best descending probe (GN steps of 6 conventions x alpha {1,0.5,0.1,0.01} + 8 random +- pairs rho=0.01 prior-scaled), accept while decrease > 1e-3 chi^2, <= 30 steps",
   "A8_2_scope_bound": "per row |X_E - X_Eprime|_end <= 2 d_ref and cost decrease <= 1 chi^2 (= C3 STATE_STABILITY max / NO_WRONG_BASIN; set after SMOKE row, user 2026-10-30; gating in S1V3 QA)",
   "decision": "user 2026-10-30, before any DEV2 result"
  },
  "A8_POST_FIT_P": {
   "methods": {
    "A": "analytic",
    "C03": "central s=3e-3",
    "C10": "central s=1e-2",
    "C30": "central s=3e-2",
    "L": "backward s=1e-7",
    "R": "forward s=1e-7"
   },
   "step_vector": "s*(1 m, 1 m, 0.17453292519943295 rad, 1e-6 rad/s)",
   "primary": "C10 (numerical convention, not a validated posterior)",
   "KINK_P_UNCERTAIN": "rel_spread > 0.05 or any non-PD end block / A'A"
  },
  "A8_CLASS_V3": {
   "CONVERGED_SMOOTH": "analytic Newton decrement <= 1e-10",
   "probe": "GN line probes alpha in {1,0.5,0.1,0.01} for all 6 conventions + 8 random +- pairs, rho=0.01 prior-scaled",
   "tau_chi2": 0.01,
   "NOT_CERTIFIED_rule": "<= 1% per (arm, window, cell) (original per-cell rule; pooled reported only)"
  },
  "A8_C3_TOL": {
   "z_abs": 1e-09,
   "ctl_x0_abs": 1e-12,
   "sigma_fp_rel": 1e-12,
   "state_dref": 1e-06,
   "cost_chi2": 1e-06,
   "P_C10_rel": 0.001,
   "basin_chi2": 1.0,
   "stability_1dref_frac_per_arm": 0.99,
   "stability_max_dref": 2.0,
   "itercap_dref": 0.1,
   "linear_exact_rel": 0.001,
   "probe_power_frac": 0.99,
   "d_ref": "(0.02 m, 0.02 m, 0.25 deg, 0.01 deg/s)"
  },
  "A8_5_CALIBRATION": "ORACLE arm, C10 P, strata kink x {LH,RV} x {tan,psi}: CALIBRATION_FAIL if field-bootstrap CI of log mean(e^2/P) disjoint from +-log 1.5",
  "A8_6_SENSITIVITY": "H1/H2/H3/CAL/H4/H4_REPRO verdicts under all 6 conventions and C10 without KINK_P_UNCERTAIN rows; any difference -> MULTIPLE_RESULTS_NO_SINGLE_ADOPTION",
  "S1V3_QA_GATING": [
   "S1V2 QA items",
   "NOT_CERTIFIED per-cell",
   "C10 PD all rows",
   "A8-2 polish within scope all rows"
  ],
  "C3_GATING": [
   "INPUT_REPRO",
   "STATE_COST_REPRO",
   "P_REPRO",
   "STATUS_REPRO",
   "NO_WRONG_BASIN",
   "STATE_STABILITY_FIXED",
   "ITER_CAP",
   "PROBE_POWER",
   "LINEAR_EXACT",
   "KINK_FIXTURES",
   "rows"
  ],
  "HOLDOUT2_STATUS": "CLOSED until independent re-audit of S1V3 + C3",
  "P3_STATUS": "NO-GO"
 },
 "run_plan": {
  "S1V3": {
   "n_confirm_default": 30,
   "n_confirm_large": 60,
   "power_rule": "As frozen (contract run_plan.S1.power_rule) applied to the S1V3 DEV2 pilot with the primary convention C10; computed only if QA PASS, no A8-5 CALIBRATION_FAIL and no A8-6 multiplicity. HOLDOUT2 ids = first n_confirm of splits.S_field.HOLDOUT2, opened only after independent re-audit.",
   "windows": {
    "LOW": "A|S_c7.5_A0.4_W4|0",
    "HIGH": "A|S_c7.5_A0.8_W4|0",
    "REV60": "A|REV60_y7_x3.0|0",
    "FWD60": "A|FWD60_y7_x3.0|0"
   },
   "cells_LOW_HIGH": [
    "LOWCORR",
    "POSE_HIGH",
    "TIME_1",
    "TIME_5",
    "POSE_HIGH_C03"
   ],
   "cells_REVISIT": [
    "LOWCORR",
    "POSE_HIGH",
    "TIME_HIGH_5"
   ],
   "arms_LOW_HIGH": [
    "IID_EKF_NOGATE",
    "IID_EKF_SELFGATE",
    "MB_VAR_NOGATE",
    "IID_BATCH",
    "ORACLE_CORR_BATCH"
   ],
   "arms_REVISIT": [
    "IID_BATCH",
    "ORACLE_CORR_BATCH",
    "XMODEL_BATCH"
   ],
   "sensor_seeds": [
    0,
    1,
    2
   ],
   "fields": [
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19
   ],
   "split": "DEV2"
  },
  "C3": {
   "fields": [
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19
   ],
   "groups": [
    "LH",
    "RV"
   ],
   "split": "DEV2",
   "starts": "psi k*sd k=-3..3, x+1sd, y+1sd, truth"
  }
 },
 "splits": {
  "S_field": {
   "SMOKE": [
    900,
    901
   ],
   "DEV": [
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9
   ],
   "POST_HOC": [
    1000,
    1001,
    1002,
    1003,
    1004,
    1005,
    1006,
    1007,
    1008,
    1009,
    1010,
    1011,
    1012,
    1013,
    1014,
    1015,
    1016,
    1017,
    1018,
    1019,
    1020,
    1021,
    1022,
    1023,
    1024,
    1025,
    1026,
    1027,
    1028,
    1029,
    1030,
    1031,
    1032,
    1033,
    1034,
    1035,
    1036,
    1037,
    1038,
    1039,
    1040,
    1041,
    1042,
    1043,
    1044,
    1045,
    1046,
    1047,
    1048,
    1049,
    1050,
    1051,
    1052,
    1053,
    1054,
    1055,
    1056,
    1057,
    1058,
    1059
   ],
   "HOLDOUT2": [
    5000,
    5001,
    5002,
    5003,
    5004,
    5005,
    5006,
    5007,
    5008,
    5009,
    5010,
    5011,
    5012,
    5013,
    5014,
    5015,
    5016,
    5017,
    5018,
    5019,
    5020,
    5021,
    5022,
    5023,
    5024,
    5025,
    5026,
    5027,
    5028,
    5029,
    5030,
    5031,
    5032,
    5033,
    5034,
    5035,
    5036,
    5037,
    5038,
    5039,
    5040,
    5041,
    5042,
    5043,
    5044,
    5045,
    5046,
    5047,
    5048,
    5049,
    5050,
    5051,
    5052,
    5053,
    5054,
    5055,
    5056,
    5057,
    5058,
    5059
   ],
   "HOLDOUT2_RESERVE": [
    5060,
    5061,
    5062,
    5063,
    5064,
    5065,
    5066,
    5067,
    5068,
    5069,
    5070,
    5071,
    5072,
    5073,
    5074,
    5075,
    5076,
    5077,
    5078,
    5079,
    5080,
    5081,
    5082,
    5083,
    5084,
    5085,
    5086,
    5087,
    5088,
    5089,
    5090,
    5091,
    5092,
    5093,
    5094,
    5095,
    5096,
    5097,
    5098,
    5099,
    5100,
    5101,
    5102,
    5103,
    5104,
    5105,
    5106,
    5107,
    5108,
    5109,
    5110,
    5111,
    5112,
    5113,
    5114,
    5115,
    5116,
    5117,
    5118,
    5119
   ],
   "DEV2": [
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19
   ]
  }
 },
 "code_sha256": {
  "code/a8_jac.py": "c1705d2eeeb8addf98f80ab8d48e3c76b1eb0b22030b3ad4a3f1f0873d691137",
  "code/c2_conv.py": "f16bf180e8fffe38699638b76b4780878025c34c4f4279acb4158badd0c87205",
  "code/c3_verify.py": "1d1dfc14d1328d542a82c354919b3c5e42da27855b9bbb0792d67f95122fb959",
  "code/contract_lock.py": "899029d4a891328fe0859471ed8d5e3bbbbcd1071b297764bc111674d0431fd8",
  "code/filters.py": "7592a8a2511c1dab300a834574348821f21aee6da5f7d742776f2f9a34892118",
  "code/info_core.py": "358180d64d769c5c4f7dde17cc7931550f5cd1ba65169105b4b5ffdc3950c1d4",
  "code/manifest.py": "f63cb34e10c613aeeb8ddb96d1cf09ff8783220609ece00f634f5b676059e370",
  "code/p0_geo2.py": "727953ba1130c86991edd4b47c5b0cd3f098be53e31b00efa578865c4ad86931",
  "code/p0_preflight.py": "1351cf624e7387942241a99233edb68a7f82d9735b28a719ae1f56bdc1bbc1ba",
  "code/rt_keys.py": "0bfb76761e8954a306b78e87c268b1974ea08801cdd960c65471ecfe046db9e7",
  "code/run_phase.py": "03a1a5c3e2d37dc07f6d1bdc6f70362fdc77f3ce77663af0bd6de4e5f293bbc9",
  "code/s0_math.py": "45462c5f024955028e9bb9a9f3136b7552ce3fd94826a395f8ec364cebd10c1a",
  "code/s0v2.py": "78c3cf3bec878f99c6d5764e089897738b8dcfdd3745cf54a66b8ca003113598",
  "code/s1_mc.py": "2457cfd5764bde987b7ddc4bf89233d56b03ca0b2a08b81b86df122b722443e2",
  "code/s1v2.py": "e4ab6005051ea868631bb76d57316b79719496c2212cb2bfeffa443ddbfd226f",
  "code/s1v3.py": "50883732afd7af8ed718efde19f61d16874104157ce8109819025c9658437c9f",
  "code/world.py": "7544be2772351c1a6afaa70b29b7465dbad6bf4a5a44dd60a85e05bf76e98f69",
  "scripts/validate_contract.py": "1f3438dca634abe2db4d8ef65008a68164ac9304ca463cee0a9e45c428b0720f",
  "tests/test_a8_jacobian.py": "ce379bf1f55ed01bc305575f612aca50ea54a6053f0967ed7a9497e79bc56a59",
  "tests/test_contract_validator.py": "6a32fa27dc94e833e834de931f030fbb2d368032b7d528353b5558f8160c4947",
  "tests/test_rt_keys.py": "35939bf3f23a7776f1ab32d4c32ee459afea420b0a37635df0f65a61fcf43c85",
  "tests/test_s0_math_contract.py": "a836c83e115666a5a3b662e40fdbeebd6b7bd7632415732be863346c75cc25f2",
  "tests/test_s1_field_contract.py": "5b343fe326bf38ef2b963c0c0b290657350e1f3db07eab2c94ece87ab76c0e76",
  "audit/audit_s0_independent.py": "1f371284aa041711b8e3315283a078a8ea4e45c18c0b597c39c4658009ffe3e3"
 }
}
```
