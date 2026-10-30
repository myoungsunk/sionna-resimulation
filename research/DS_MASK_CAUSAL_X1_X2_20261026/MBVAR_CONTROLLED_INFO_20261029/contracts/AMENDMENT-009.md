# AMENDMENT-009 — S1V3 design-audit fixes (class v3.1, polish trigger, axis probes, full C10 NEES), tap robustness (B), exploratory RT residual check (C), HOLDOUT2 / RT entry gates

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 FROZEN (`68d73bd2…`) + AMENDMENT-003…008. Nothing earlier is edited. |
| Trigger | Independent S1V3 design audit `audit/mbvar-info-s1v3-design-20261030`, commit `353381b3`, on execution SHA `c4d84e02`. Verdict: `DESIGN_CONDITIONALLY_ACCEPTABLE / EXPERIMENTAL_EVIDENCE_PENDING / RT_NO-GO`. |
| Author role | IMPLEMENTER, also PROPOSER for §3 at the user's request (2026-10-30). **SELF_REVIEW_ONLY.** |
| Timing | Rules and code were written and committed as draft `bf17158` while S1V3 DEV2 run `40981032471` (AMENDMENT-008) was executing, **before any S1V3 DEV2 result was read**. The lock is frozen after that run finished and was read; §8 lists every change between `bf17158` and the freeze, so it can be checked that no rule changed after reading. All rules are fixed before any S1V4, BTAP or RFRES result. |
| Frozen code untouched | `s1v3.py` and `c3_verify.py` (AMENDMENT-008) are **not modified**. All A009 code lives in new files (`s1v4.py`, `c3v4.py`, `b_tap.py`, `c_rfres.py`). So C3 on the S1V3 run still reproduces the AMENDMENT-008 code exactly. |
| Splits | DEV2 = 10–19 is reused for S1V4 and BTAP as **development** data (second and third DEV2 passes, not independent). HOLDOUT2 5000–5059 and reserve 5060–5119 stay **unopened**. |
| Preserved | Every earlier FAIL: C2 `40871327417`, C1 `40857100181`, S1V2 DEV `40864089916` / `40867939262`. The S1V3 DEV2 result is kept as recorded under AMENDMENT-008, whatever it is. |

## 1. Logical weaknesses that require correction

| ID | Weakness | Source | Effect if left |
|---|---|---|---|
| W1 | `class_v3` returns `CONVERGED_SMOOTH` whenever the analytic Newton decrement is ≤ 1e-10, **before** it looks at the probe. A probe descent > τ (e.g. −0.02 χ²) is then ignored. | auditor §1 | A non-minimal point at an FFD kink can be labelled converged. This is the failure mode A008 was meant to remove. |
| W2 | The A008 polish is skipped under the same condition (analytic decrement ≤ 1e-10). | implementer, same root as W1 | Such a point is also never polished. |
| W3 | `nees4` uses the analytic P, while C10 is the primary convention. | auditor §4 | Joint (4-state) consistency claims would mix conventions. |
| W4 | `LOCAL_MIN_CERTIFIED` means "no descent found by the finite probe set". It is not a proof of local or global optimality. | auditor §1 | Over-interpretation. |
| W5 | EKF arms use the state-derived detector tap; batch arms use the true tap. | auditor §2-B | EKF vs batch error comparisons mix the value of the correlated covariance with the value of knowing the tap. |
| W6 | HOLDOUT2 fields are new random realisations of the **same** generator. They are not independent RT scenes. | auditor §3 | A HOLDOUT2 PASS supports only reproducibility within the controlled synthetic model. It says nothing about RF multipath. |
| W7 | S1V4 and BTAP reuse DEV2 after S1V3 has been read. | implementer | Their DEV2 numbers are development evidence. HOLDOUT2 stays the only confirmatory synthetic set. |

## 2. Required corrections (S1V4 = S1V3 + F1–F4; the A008 rules are otherwise inherited unchanged)

- **F1 — class v3.1.**
  - `NOT_CERTIFIED` if any probe lowers the cost by more than τ = 0.01 χ², regardless of the analytic decrement.
  - Otherwise `CONVERGED_SMOOTH` if the analytic decrement is ≤ 1e-10.
  - Otherwise `LOCAL_MIN_CERTIFIED`.
  - The A008 rule is also stored in every row (`class_v3_A008_rule`).
- **F2 — polish trigger.** The polish (A008 §1) runs at every row. It stops only when no probe lowers the cost by more than 1e-3 χ² (at most 30 steps). The A8-2 bound is unchanged: E → E' ≤ 2·d_ref and ≤ 1 χ².
- **F3 — one-sided axis probes** (left/right directional cost change at kinks). The probe set is the A008 set plus ±ρ_a·√P0_jj on each of the four x0 coordinates, with ρ_a ∈ {1e-2, 1e-3} (16 probes).
- **F4 — full C10 end covariance.**
  - Store all 10 unique entries of the rotated window-end C10 4×4, and `nees4_C10` = e₄ᵀ P_C10⁻¹ e₄.
  - `nees4` (analytic) is kept. A8-5 adds the ORACLE `nees4_C10/4` per window group, with a field bootstrap and the ±log 1.5 band, as a reported item.
  - **For the A008 S1V3 run**, joint-consistency claims are limited to the per-state A8-5 statistics.
- **G2 post-hoc check on S1V3 (reported, never a retroactive PASS).** For the S1V3 DEV2 rows: count rows with analytic decrement ≤ 1e-10 and `probe_min_dcost < −τ`. If > 0, the S1V3 class gate would have failed under v3.1, and that is reported. A correction can only add failures.
- **A8-6 extended** with a second exclusion check: C10 without rows that have a kink at E', next to "without `KINK_P_UNCERTAIN`".
  - `A86_convention_outcome`: same verdicts across the six conventions.
  - `A86_exclusion_outcome`: verdicts unchanged by either exclusion.
- **A8-5 reporting (G3):** all 8 strata (kink × LH/RV × tan/psi) are listed. A stratum with fewer than 2 fields is `evaluable = false` → UNDETERMINED, and is counted.

## 3. Proposer review of additional design options

| Option | Content | Decision |
|---|---|---|
| A | Complete S1V3 → C3, then S1V4 → C3V4 on DEV2, then HOLDOUT2 (S1V4 code) after independent re-audit | **required**, first priority |
| B | Tap-knowledge robustness on DEV2 (§4) | **run now**, before RT |
| C | Exploratory transfer check of the synthetic residual model against the existing corridor RT Full/LoS channels (§5) | **run now**, small, exploratory |
| D | Smooth FFD interpolation as an alternate synthetic model | **deferred**. It changes the generator; not needed for the RT decision. |

No further synthetic expansion is proposed. After A (with B and C as context), the next step is the physical RT stage.

## 4. Option B — tap robustness (P2_BTAP; DEV2 sensitivity, not confirmatory)

- **Design:** DEV2 fields 10–19 × sensors 0–2 × windows LOW/HIGH × cells LOWCORR/POSE_HIGH.
  - Arms: `IID_BATCH`, `ORACLE_CORR_BATCH` (S1V4 E' + post-fit + class v3.1; primary C10 P).
  - Plus `EKF_STATE_TAP` (the S1V2 EKF) and `EKF_ORACLE_TAP` (same EKF with the true tap) for W5.
- **Estimator tap conditions** (generator unchanged):
  - `TAP_ORACLE`: true taps.
  - `TAP_ERR_1`: ±1 detector index at 10 % of poses.
  - `TAP_ERR_4`: ±4 indices, i.e. one raw tap.
  - `TAP_STATE`: tap re-derived from the state, i.e. no tap observation.
- **Pre-registered rule:** `ROBUST` if every H1 / H2 / H3 / CAL verdict under `TAP_ERR_1` equals `TAP_ORACLE`; otherwise `TAP_SENSITIVE`. `TAP_ERR_4` and `TAP_STATE` are reported. `TAP_SENSITIVE` is not a failure: it becomes a requirement on the RT stage (real tap extraction must be validated before RT conclusions use it).
- **Expected rows:** 10 × 3 × 2 × 2 × (4 × 2 + 2) = 1200.

## 5. Option C — exploratory RT residual replay (P2_RFRES; no gate)

- **Data:** all 7 corridor cases of DRIVE_SIM BLOCK_C (commit `9bcd5da2`), Full and LoS-only RT channels. Drive-trace truth poses; noise-free first-path observation (same chain as the FFD model).
- **Residuals:**
  - e_tot = obs(Full) − FFD(truth)
  - e_mp = obs(Full) − obs(LoS), the multipath part
  - e_los = obs(LoS) − FFD(truth)
- **Statistics:** moments, first-path switch fraction, jumps at switches, the e_mp correlogram vs the synthetic pose kernel, and the ACF.
- **Pre-declared descriptive flags:**
  - `BIAS`: |mean| > 0.5 σ_synth
  - `SCALE`: sd/σ_synth ∉ [0.5, 2]
  - `NON_GAUSSIAN`: |excess kurtosis| > 1 or |skew| > 0.5
  - `FP_SWITCH`: switch fraction > 5 %
  - `CORR_MISMATCH`: a distance bin with ≥ 200 pairs where |corr_emp − 0.7 k| > 0.3
- **Use:** this data was used by earlier studies, so the result is **not** confirmation. Flags become explicit items of the pre-P3 amendment (G7). They state what the RT stage must not assume from the synthetic model.
- **Pre-freeze note:** a local single-case check (R4_aB_m0) was made only to verify the code path. Its numbers are not evidence. No threshold above was set from it.

## 6. Final gates for HOLDOUT2 and physical RT

| Gate | Evidence | If not met |
|---|---|---|
| **G1** DEV2 technical QA | S1V3 QA (A008) and S1V4 QA (A009): rows, input receipts, failures, revisit identity, Mahalanobis, per-cell NOT_CERTIFIED ≤ 1 %, C10 PD, A8-2 | stop |
| **G2** classification audit | S1V3 post-hoc W1 count (§2); S1V4 `G2_smooth_with_probe_descent` and class v3 → v3.1 cross-table | if S1V3 > 0: recorded as S1V3 class FAIL under v3.1; S1V4 decides going forward |
| **G3** covariance statistics | A8-5: 8 strata, evaluable count, CALIBRATION_FAIL; `nees4_C10` (reported) | any CALIBRATION_FAIL → scientific verdict on hold; unevaluable stratum → UNDETERMINED |
| **G4** result stability | A8-6 convention outcome and exclusion outcome | no single P / no single conclusion adopted |
| **G5** C3 reproducibility | C3 on S1V3 (A008 gates) and C3V4 on S1V4 (same gates, class v3.1): input / state / cost / P / class, basin, stability, ITER_CAP, PROBE_POWER, LINEAR_EXACT, KINK_FIXTURES | stop |
| **G6** independent confirmation | HOLDOUT2 with S1V4 code, n from S1V4 DEV2 power, **only after an independent re-audit of G1–G5**. The verdict (SUPPORTED / NOT_SUPPORTED / MIXED / INCONCLUSIVE) is reported as is. A validly tested NOT_SUPPORTED H2 is a scientific result, distinct from a technical failure. | report as is |
| **G7** pre-P3 contract | Signed pre-P3 amendment covering: complex-channel RT with real first-path tap extraction (BTAP outcome); the shared C10 plate; DIRECT parity; RFRES flags addressed; **user's numeric budget approval** | P3 stays NO-GO |

**Entry rules:**
- **HOLDOUT2** requires G1, G2, G4 and G5 decided, the A8-5 status known (G3), and the independent re-audit.
  - Its execution lock is a short follow-up amendment: S1V4 code; HOLDOUT2 ids = first n_confirm; no rule change.
- **Physical RT (P3)** requires G6 reported and G7 signed with the budget approval.

## 7. Order

1. Freeze this lock.
2. In parallel: C3 on S1V3 (AMENDMENT-008 code); S1V4 on DEV2; BTAP; RFRES.
3. C3V4 on the S1V4 run.
4. Gate report G1–G7. **Stop for the independent re-audit.** Do not open HOLDOUT2. No RT.

## 8. State at freeze (reported; no rule below was changed after reading)

**S1V3 DEV2 run `40981032471` (AMENDMENT-008), read after draft `bf17158`:**
- **QA:** PASS, 1980/1980 rows. There are no A008 NOT_CERTIFIED cells, and one old-A007 NONCONVERGED (reported).
- **A8-5:** no CALIBRATION_FAIL; 6 of 8 strata PASS, and RV non-kink tan/psi are UNDETERMINED.
- **A8-6:** consistent across conventions. No `KINK_P_UNCERTAIN` rows.
- **Pilot outcome (not a decision):** `NOT_SUPPORTED`, because of H1 LOW POSE_HIGH tan FAIL and H2 tan FAIL. Power: n_confirm = 60, underpowered at max.
- **G2 post-hoc (W1):** 4 rows, all `XMODEL_BATCH`, have an analytic decrement ≤ 1e-10 together with a probe descent of 0.012–0.049 χ² (GN step of C30/C10; no kink at E). Under class v3.1, these would make 3 (arm, window, cell) cells fail the per-cell rule. The AMENDMENT-008 record is unchanged. This is the evidence that W1 was not hypothetical.

**Changes between `bf17158` and the freeze:**
- this §8;
- the Timing row above;
- the lock block.

No code changes.

## AMENDMENT_LOCK
