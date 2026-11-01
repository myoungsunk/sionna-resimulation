# AMENDMENT-010 — canonical inputs, solver reproducibility, mode ambiguity (DRAFT — not frozen)

| Field | Value |
|---|---|
| Status | **DRAFT.** It is frozen only after a separate independent audit has signed (proposer handoff, Phase A010-FREEZE). Until then no DEV3 field is opened and no estimator or threshold below is used for any gate. |
| Source | Proposer handoff `reviews/PROPOSER_A010_IMPLEMENTER_HANDOFF_DRAFT_20261030_KO.md` and audit `audit/AUDIT_C3_C3V4_20261030_KO.md` on branch `audit/mbvar-info-c3-a010-proposal-20261030` (`ef0b707c`). Both were written in one session in the proposer and auditor roles, so `INDEPENDENT_AUDITOR_SIGNED=false`. |
| Trigger | C3 `40992589158` FAIL, C3V4 `41005158792` FAIL. Implementer analysis `reviews/C3_FAILURE_ANALYSIS_A010_OPTIONS_20261030_KO.md`. |
| Preserved | All earlier runs and verdicts. G5 = FAIL for S1V3/C3 and S1V4/C3V4 is not superseded by any rule below. AMENDMENT-008/009 code, inputs and outputs are unchanged. |
| Executed so far | Only Phase A010-P0, the forensic ablation on 4 existing DEV2 keys, under the separate execution lock `AMENDMENT-010-P0`. It carries code hashes and the frozen key list, and no scientific rule. |

## 1. Decisions adopted from the proposer (to be frozen after audit)

- **R1 canonical input (mandatory).**
  - Freeze the exact world pose-field factor `Lhalf`: float64, 180×180, little-endian, with its SHA-256, the pose-ledger order, `Kp`, the config and the FFD bank hashes.
  - Archive per key `z, x0, ds_m, gy_m, taps`, the poses, and the full `Sigma_true` and `Sigma_model` arrays.
  - C3V5 replays these bytes. Generator-law checks are separate from solver replay.
- **R2 deeper polish:** a **separately labelled candidate** (τ_cost = 1e-9 χ², ≤ 300 steps). S1V4 remains the baseline arm. It does not claim to solve mode selection.
- **R3 portable tolerances (prospective only):**
  - The strict A008 metrics are always reported.
  - The candidate kink-row metrics (≤ 1e-2 d_ref, ≤ 1e-5 χ², ≤ 1e-2 relative covariance, |Δ log inflation| ≤ 0.02 with unchanged categorical verdicts) apply only to rows that a **geometric** kink classifier certifies. A classifier is not yet defined; until it is, the label is `KINK_CLASS_UNCERTAIN` and no exception is granted.
  - These values were formulated after seeing C3. They never relabel a historical run.
- **R4 close minima:**
  - `AMBIGUOUS_STATE_IDENTIFICATION` iff a truth-free solution has Δcost ≤ 1 χ² **and** end-state distance > 2 d_ref (the existing NO_WRONG_BASIN / STATE_STABILITY pair).
  - Diagnostic candidate: the nine truth-free starts (yaw −3…+3 SD, x+1 SD, y+1 SD), taking the lowest objective. The truth start is `ORACLE_ONLY` and never selects a solution.
  - Not promoted to the main H-tests without a separate prospective freeze.
- **R5 architecture:** environment, BLAS and threads are pinned and recorded as diagnostics only. Primary reproducibility uses canonical input bytes.
- **G2:** the diagnostic uses the final E' `dec_A_fixed` together with the final E' probe.
- **G4:** primary H-tests use all valid keys. Kink inclusion is reported as subgroup heterogeneity or selection sensitivity. `EXCLUSION_CHANGES_RESULT` is a material caveat, and the power output is never an authorisation.
- **G5 split:** `INPUT_EXACT`, `GENERATOR_DISTRIBUTION` (field law), `SOLVER_REPRO` (same input, ≥ 2 runners), `MODE_AMBIGUITY`, and `FULL_C10_REPRO` (10 unique entries, PSD, condition number, `nees4_C10`).
- **G7 wording correction:**
  - The RFRES `FP_SWITCH` flag measured Full-vs-LoS first-path index disagreement **at the same pose**. It is not a temporal switching rate.
  - Four separate metrics are reported in `reviews/A010_G7_TAP_METRICS/`. The RT stage must test both kinds.

## 2. Open items for the freeze (not decided here)

1. A geometric kink classifier, i.e. the distance to the nearest 1° pattern-cell boundary along the FFD interpolation axes, with its tolerance.
2. Whether S1V5 (the primary estimator for DEV3) is unchanged S1V4, or S1V4 with deep polish, or with the fixed start grid. Whichever is chosen is a new estimator and is disclosed as such.
3. The final numeric portable thresholds, accepted independently before DEV3.
4. DEV3 = 20–29: opened only after the freeze.

## 3. Order

A010-P0 (forensic, now) → implementer report → independent audit of P0 and of this text → A010-FREEZE → DEV3 / S1V5 / C3V5 → audit → HOLDOUT2 decision by the user. **No auto-HOLDOUT, no auto-RT.**
