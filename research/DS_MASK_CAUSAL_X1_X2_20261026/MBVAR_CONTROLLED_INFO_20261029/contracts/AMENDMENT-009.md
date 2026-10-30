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

**Pre-freeze technical end-to-end (SMOKE 900/901, reduced design, local; not evidence):**
- S1V4: QA PASS, G2 counter 0.
- C3V4: all gates PASS (PROBE_POWER 100 %).
- BTAP: 80/80 rows; pipeline and outputs produced. Its verdict at n = 2 is meaningless.
- RFRES: code path checked on R4_aB_m0 only.

**Changes between `bf17158` and the freeze:**
- this §8;
- the Timing row above;
- the lock block.

No code or test changes. Verify with `git diff bf17158 <freeze> -- code tests`.

## AMENDMENT_LOCK

```json
{
 "status": "FROZEN",
 "amendment_id": "AMENDMENT-009",
 "frozen_utc_date": "2026-10-30",
 "base_contract_sha256": "68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34",
 "amendment_text_sha256": {
  "AMENDMENT-003": "a94fea6dfbedf34783eed34c76b04d67297698cdec3f1d914303e6f05a1ee6a4",
  "AMENDMENT-004": "a188245a2c827312ffd3f1775bfdc63c8a66a0aca66bd62d64b231489ce51c60",
  "AMENDMENT-005": "0cf11f09cec8e1d4d09509fa9b3a37a9377d167b3c8650a84ed84b0a5b393401",
  "AMENDMENT-006": "0244c8b6f68184f6c0e9e50039f5522eff0d4eb64c6d58c4a7985775a4dd0201",
  "AMENDMENT-007": "1ce644983fb2f57383aa856e6e662297c5ceb71544b72c0ea7c77f4b3197af68",
  "AMENDMENT-008": "0950a1806b655e98f2bc2f31bee9c0fde632ee8b1612d63f45e86bf5d8acd2d5"
 },
 "trigger": {
  "audit_branch": "audit/mbvar-info-s1v3-design-20261030",
  "audit_commit": "353381b3",
  "audited_execution_sha": "c4d84e02",
  "audit_verdict": "DESIGN_CONDITIONALLY_ACCEPTABLE / EXPERIMENTAL_EVIDENCE_PENDING / RT_NO-GO"
 },
 "reviewer_status": "SELF_REVIEW_ONLY; independent re-audit required before HOLDOUT2",
 "resolved": {
  "A9_FIXES": {
   "F1_class_v31": "NOT_CERTIFIED if probe dcost < -0.01 regardless of analytic decrement; else CONVERGED_SMOOTH if decrement <= 1e-10; else LOCAL_MIN_CERTIFIED",
   "F2_polish_trigger": "polish at every row; stop when no probe lowers cost by > 1e-3 chi^2 (<= 30 steps); A8-2 bound unchanged (2 d_ref, 1 chi^2)",
   "F3_axis_probes": "+- rho_a sqrt(P0_jj) on x0 coords, rho_a in {1e-2, 1e-3}",
   "F4_C10_full": "rotated C10 end 4x4 stored; nees4_C10 reported (A8-5 extension, reported)"
  },
  "G2_POSTHOC_S1V3": "count rows with analytic decrement <= 1e-10 and probe_min_dcost < -0.01 in the A008 S1V3 DEV2 run; reported; no retroactive PASS",
  "A8_6_EXCLUSIONS": [
   "without KINK_P_UNCERTAIN",
   "without kink-at-E' rows"
  ],
  "BTAP_RULE": "ROBUST iff all H1/H2/H3/CAL verdicts under TAP_ERR_1 equal TAP_ORACLE; else TAP_SENSITIVE (not a failure; RT requirement)",
  "RFRES_FLAGS": {
   "BIAS": "|mean| > 0.5 sigma_synth",
   "SCALE": "sd/sigma_synth outside [0.5,2]",
   "NON_GAUSSIAN": "|exkurt|>1 or |skew|>0.5",
   "FP_SWITCH": "switch fraction > 0.05",
   "CORR_MISMATCH": "bin with >=200 pairs and |corr_emp - 0.7 k| > 0.3",
   "gate": "none (exploratory)"
  },
  "FINAL_GATES": [
   "G1 DEV2 technical QA",
   "G2 classification audit",
   "G3 A8-5 strata",
   "G4 A8-6 convention+exclusion",
   "G5 C3 + C3V4",
   "G6 HOLDOUT2 after independent re-audit",
   "G7 signed pre-P3 amendment + user numeric budget"
  ],
  "HOLDOUT2_STATUS": "CLOSED until independent re-audit of G1-G5",
  "P3_STATUS": "NO-GO"
 },
 "run_plan": {
  "S1V4": {
   "n_confirm_default": 30,
   "n_confirm_large": 60,
   "power_rule": "As frozen (contract run_plan.S1.power_rule) applied to the S1V4 DEV2 pilot with the primary convention C10; computed only if QA PASS, no A8-5 CALIBRATION_FAIL and no A8-6 multiplicity. HOLDOUT2 ids = first n_confirm of splits.S_field.HOLDOUT2, opened only after independent re-audit.",
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
  "C3V4": {
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
   "split": "DEV2"
  },
  "BTAP": {
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
   "split": "DEV2",
   "conditions": [
    "TAP_ORACLE",
    "TAP_ERR_1",
    "TAP_ERR_4",
    "TAP_STATE"
   ],
   "err_rate": 0.1
  },
  "RFRES": {
   "cases": [
    "R2_aA_m0",
    "R2_aB_m0",
    "R2_aA_m45",
    "R4_aA_m0",
    "R4_aB_m0",
    "R5_aA_m0",
    "R5_aB_m0"
   ],
   "source_commit": "9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13"
  }
 },
 "code_sha256": {
  "code/a8_jac.py": "c1705d2eeeb8addf98f80ab8d48e3c76b1eb0b22030b3ad4a3f1f0873d691137",
  "code/a9_class.py": "32f372dcb41d639bde07aafa232fb50710138fad72c8f8edb1aefdedc5af6465",
  "code/b_tap.py": "68504c01bce0c61495f0f7351c6fb1973c93bcc73c8e751c689c1a82818f81ed",
  "code/c2_conv.py": "f16bf180e8fffe38699638b76b4780878025c34c4f4279acb4158badd0c87205",
  "code/c3_verify.py": "1d1dfc14d1328d542a82c354919b3c5e42da27855b9bbb0792d67f95122fb959",
  "code/c3v4.py": "22414d1b30ceb15c4c65f16e3eba259ab41cc303ca62ab28f89e7bfca5e2f78e",
  "code/c_rfres.py": "eb99d0ad4b8f25468d48de4faa47e1e4ad0590470e6f9d967ffae956c1289f61",
  "code/contract_lock.py": "899029d4a891328fe0859471ed8d5e3bbbbcd1071b297764bc111674d0431fd8",
  "code/filters.py": "7592a8a2511c1dab300a834574348821f21aee6da5f7d742776f2f9a34892118",
  "code/info_core.py": "358180d64d769c5c4f7dde17cc7931550f5cd1ba65169105b4b5ffdc3950c1d4",
  "code/manifest.py": "f63cb34e10c613aeeb8ddb96d1cf09ff8783220609ece00f634f5b676059e370",
  "code/p0_geo2.py": "727953ba1130c86991edd4b47c5b0cd3f098be53e31b00efa578865c4ad86931",
  "code/p0_preflight.py": "1351cf624e7387942241a99233edb68a7f82d9735b28a719ae1f56bdc1bbc1ba",
  "code/rt_keys.py": "0bfb76761e8954a306b78e87c268b1974ea08801cdd960c65471ecfe046db9e7",
  "code/run_phase.py": "de51056dfc74019407d24a53006308a76f1c62fabb63354d768643e1de834c66",
  "code/s0_math.py": "45462c5f024955028e9bb9a9f3136b7552ce3fd94826a395f8ec364cebd10c1a",
  "code/s0v2.py": "78c3cf3bec878f99c6d5764e089897738b8dcfdd3745cf54a66b8ca003113598",
  "code/s1_mc.py": "2457cfd5764bde987b7ddc4bf89233d56b03ca0b2a08b81b86df122b722443e2",
  "code/s1v2.py": "e4ab6005051ea868631bb76d57316b79719496c2212cb2bfeffa443ddbfd226f",
  "code/s1v3.py": "50883732afd7af8ed718efde19f61d16874104157ce8109819025c9658437c9f",
  "code/s1v4.py": "58bf836c07252c9a689fb64fc9b1a5ce228f0ead38459642afd306e72815ba3b",
  "code/world.py": "7544be2772351c1a6afaa70b29b7465dbad6bf4a5a44dd60a85e05bf76e98f69",
  "scripts/validate_contract.py": "1f3438dca634abe2db4d8ef65008a68164ac9304ca463cee0a9e45c428b0720f",
  "tests/test_a8_jacobian.py": "ce379bf1f55ed01bc305575f612aca50ea54a6053f0967ed7a9497e79bc56a59",
  "tests/test_a9_class.py": "b97d08e89861a2d2c58a5d74564a1531021a29d047714ac887c9fa8f875e8b0c",
  "tests/test_contract_validator.py": "6a32fa27dc94e833e834de931f030fbb2d368032b7d528353b5558f8160c4947",
  "tests/test_rt_keys.py": "35939bf3f23a7776f1ab32d4c32ee459afea420b0a37635df0f65a61fcf43c85",
  "tests/test_s0_math_contract.py": "a836c83e115666a5a3b662e40fdbeebd6b7bd7632415732be863346c75cc25f2",
  "tests/test_s1_field_contract.py": "5b343fe326bf38ef2b963c0c0b290657350e1f3db07eab2c94ece87ab76c0e76",
  "audit/audit_s0_independent.py": "1f371284aa041711b8e3315283a078a8ea4e45c18c0b597c39c4658009ffe3e3"
 }
}
```
