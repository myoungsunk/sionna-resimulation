# AMENDMENT-007 — audit re-review (REVISION_REQUIRED) response: original-rule judgements, C2 convergence verification, CI failure propagation, shared C10

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 FROZEN (`68d73bd2…`) + AMENDMENT-003…006 |
| Trigger | Independent re-audit of 2026-10-29 20:51 KST (user-supplied): `REVISION_REQUIRED`, requirements R1–R7. Proposer decision D1 (user directive: "제안자로서 D1의 방향은 확정"). |
| Author role | IMPLEMENTER for R1–R5/R7; PROPOSER for D1/R6, under the user directive. **SELF_REVIEW_ONLY**. |
| Results seen | Everything up to S1V2 DEV run `40864089916` QA and the re-audit. The S1V2 DEV re-run `40867939262` (AMENDMENT-006 rescue) was in flight when this text was written. **No C2 result exists. HOLDOUT2 is unopened.** |

## R1 / R3 / R4 — judgements under the ORIGINAL rules (no retroactive PASS)

| Item | Original rule | Recorded judgement |
|---|---|---|
| C1-d (run `40857100181`) | AMENDMENT-004 strict, ≥ 99 % within 1e-3 χ² | **FAIL** (97.8 %), preserved |
| C1-f (run `40857100181`) | AMENDMENT-003, ≤ 1 % NONCONVERGED **per (arm, window, cell)** | **FAIL**: ORACLE·LOW·POSE_HIGH 3/30, ORACLE·LOW·POSE_HIGH_C03 2/30, ORACLE·HIGH·POSE_HIGH 1/30. The old aggregator checked only the pooled 1.0 %; that was an implementation defect. |
| AMENDMENT-005 (> 1 χ² wrong-basin rule) | — | Accepted as an **auxiliary engineering check only**. The `PASS` of run `40862934784` is relabelled `A005_AUXILIARY_PASS / ORIGINAL_CONTRACT_FAIL`. |
| AMENDMENT-006 granularity rule | — | **Withdrawn as a gate.** The original per-cell 1 % rule is restored (at n = 30 per cell that means 0 NONCONVERGED). The rescue estimator is kept and is evaluated by C2. |
| AMENDMENT-005/006 status | — | Both are post-hoc. This lock freezes their text sha256 and states that their PASS labels are not contract PASSes. |

## R2 — convergence verification C2 (registered here, before any C2 run)

- **Scope.** DEV fields 0–9 with exactly the S1V2 DEV inputs. All four windows (LOW, HIGH, REV60, FWD60), every cell, every batch arm, including **XMODEL** (deliberately misspecified covariance) and the revisit windows: 1080 runs.
- **Estimator E.** S1V2 `batch_map_v2_ms` (multi-start trigger + rescue).
- **Always-run start grid.** Heading k·sd_ψ for k = −3…3, plus +1 sd in x and +1 sd in y, plus the true-θ start: 10 starts. C* = the lowest cost found by E or any start.
- **Gating criteria.**
  - C2-a: E rows equal the S1V2 DEV rows: |Δe|/sd and |ΔP|/P ≤ 1e-3, all 1080.
  - C2-b (wrong basin): cost(E) − C* ≤ 1 χ² for all runs.
  - C2-c (state stability): window-end |X_E − X_best| ≤ 0.5 posterior sd in ≥ 99 % of runs per arm, and ≤ 1.0 sd always.
  - C2-d (**original** per-cell rule): NONCONVERGED ≤ 1 % per (arm, window, cell).
  - C2-e (iteration cap): runs that are not CONVERGED change by ≤ 0.1 sd with max_iter 300.
- **Reported, not gating.**
  - C2-c strict: cost gap ≤ 1e-3 χ² in ≥ 99 %.
  - C2-f, kink hypothesis: share of flagged runs with ≥ 1 kink pose at E vs share among clean runs.
  - Spread of near-optimal solutions in sd.
  - C2-g: XMODEL gaps, the trigger fraction, and whether the truth start is ever worse than E.
- **Outcome.** C2 FAIL keeps HOLDOUT2 closed. Rules are not re-tuned after a C2 result; any further change needs a new amendment and fresh DEV fields.

## R5 — CI failure propagation

The aggregate step keeps publishing evidence. A final step then fails the workflow when `MANIFEST.execution_status != PASS` or when the MANIFEST is missing. A green Actions run therefore equals an internal PASS.

## R6 / D1 — shared C10 plate (PROPOSER decision, final direction)

- **C10_SHARED_PLATE**: centre (2.75, 1.50) m, length 2.0 m, orientation 0°, z 0–2.7 m, ITU `metal`, 5 mm, anchor A (2, 2, 2.65).
- **The same plate is used for every window.** Per-window plates are withdrawn because they confound geometry with the scene.
- **Recomputed with `p0_geo2._plate_eval`.** All four windows pass the LoS-not-cut, footprint-clearance and anchor-distance constraints.

| Window | Specular point inside plate | Excess delay median / max |
|---|---|---|
| LOW | 100 % | 6.19 / 6.29 taps |
| HIGH | 100 % | 6.27 / 6.32 taps |
| REV60 | 100 % | 5.95 / 6.12 taps |
| FWD60 | 100 % | 5.72 / 6.12 taps |

The auditor's independent values agree to within 0.01 tap.

- **Rule added before any RT.** Every evaluated pose (not only the median) must have excess delay ≤ 8 taps.
- **C11 is excluded from confirmatory comparison** until a shared C11 geometry satisfies the same rules.
- **Pre-RT geometry only.** Reflected power, polarisation change and first-path interaction are unverified. An actual Δs must be measured in the canary. If C10 shows no physical effect, the plate is **not moved**; the result is preserved as "insufficient designed effect".

## R7 — order

1. R1–R5 fixes.
2. Freeze this lock (rules and code sha256) **before** any C2 run.
3. Under this lock: re-aggregate the S1V2 DEV re-run `40867939262` with the original per-cell rule, and run C2.
4. **Stop for the independent re-audit.** The implementer does not open HOLDOUT2.
5. HOLDOUT2 (5000–5059), only after the re-audit.
6. P3 canary, only after the signed pre-P3 amendment and the user's numeric budget approval.

## AMENDMENT_LOCK

```json
{
 "status": "FROZEN",
 "amendment_id": "AMENDMENT-007",
 "frozen_utc_date": "2026-10-29",
 "base_contract_sha256": "68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34",
 "amendment_text_sha256": {
  "AMENDMENT-003": "a94fea6dfbedf34783eed34c76b04d67297698cdec3f1d914303e6f05a1ee6a4",
  "AMENDMENT-004": "a188245a2c827312ffd3f1775bfdc63c8a66a0aca66bd62d64b231489ce51c60",
  "AMENDMENT-005": "0cf11f09cec8e1d4d09509fa9b3a37a9377d167b3c8650a84ed84b0a5b393401",
  "AMENDMENT-006": "0244c8b6f68184f6c0e9e50039f5522eff0d4eb64c6d58c4a7985775a4dd0201"
 },
 "reviewer_status": "SELF_REVIEW_ONLY; independent re-audit required before HOLDOUT2",
 "resolved": {
  "ORIGINAL_RULE_JUDGEMENTS": {
   "C1d_strict_A004_run_40857100181": "FAIL",
   "C1f_per_cell_run_40857100181": "FAIL",
   "A005_wrong_basin_run_40862934784": "AUXILIARY_PASS_ONLY",
   "S1V2_DEV_run_40864089916": "FAIL"
  },
  "NONCONVERGED_QA_RULE": "ORIGINAL AMENDMENT-003: <= 1% per (arm,window,cell); A006 granularity rule withdrawn as a gate (reported only)",
  "C2_GATING": [
   "C2a_inputs_identical_to_S1V2_DEV",
   "C2b_no_wrong_basin",
   "C2c_state_stability",
   "C2d_nonconverged_per_cell_original",
   "C2e_iter_cap"
  ],
  "C10_SHARED_PLATE": {
   "cx": 2.75,
   "cy": 1.5,
   "L": 2.0,
   "rot_deg": 0.0,
   "z_m": [
    0.0,
    2.7
   ],
   "material": "itu_metal",
   "thickness_m": 0.005,
   "rule": "all evaluated poses: specular point inside (0.10 m edge margin, z 0.10-2.60), excess delay <= 8 taps; LoS not cut; clearance >= 0.10 m",
   "C11": "EXCLUDED_FROM_CONFIRMATORY"
  },
  "HOLDOUT2_STATUS": "CLOSED until independent re-audit"
 },
 "run_plan": {
  "C2": {
   "fields": [
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
   "groups": [
    "LH",
    "RV"
   ],
   "starts": "psi k*sd k=-3..3, x+1sd, y+1sd, truth"
  }
 },
 "code_sha256": {
  "code/c2_conv.py": "f16bf180e8fffe38699638b76b4780878025c34c4f4279acb4158badd0c87205",
  "code/contract_lock.py": "899029d4a891328fe0859471ed8d5e3bbbbcd1071b297764bc111674d0431fd8",
  "code/filters.py": "7592a8a2511c1dab300a834574348821f21aee6da5f7d742776f2f9a34892118",
  "code/info_core.py": "358180d64d769c5c4f7dde17cc7931550f5cd1ba65169105b4b5ffdc3950c1d4",
  "code/manifest.py": "f63cb34e10c613aeeb8ddb96d1cf09ff8783220609ece00f634f5b676059e370",
  "code/p0_geo2.py": "727953ba1130c86991edd4b47c5b0cd3f098be53e31b00efa578865c4ad86931",
  "code/p0_preflight.py": "1351cf624e7387942241a99233edb68a7f82d9735b28a719ae1f56bdc1bbc1ba",
  "code/rt_keys.py": "0bfb76761e8954a306b78e87c268b1974ea08801cdd960c65471ecfe046db9e7",
  "code/run_phase.py": "3d84eb86f3957ebe51676b33eadf0ccd264941c6a39443df14a64419f634599a",
  "code/s0_math.py": "45462c5f024955028e9bb9a9f3136b7552ce3fd94826a395f8ec364cebd10c1a",
  "code/s0v2.py": "78c3cf3bec878f99c6d5764e089897738b8dcfdd3745cf54a66b8ca003113598",
  "code/s1_mc.py": "2457cfd5764bde987b7ddc4bf89233d56b03ca0b2a08b81b86df122b722443e2",
  "code/s1v2.py": "e4ab6005051ea868631bb76d57316b79719496c2212cb2bfeffa443ddbfd226f",
  "code/world.py": "7544be2772351c1a6afaa70b29b7465dbad6bf4a5a44dd60a85e05bf76e98f69",
  "scripts/validate_contract.py": "1f3438dca634abe2db4d8ef65008a68164ac9304ca463cee0a9e45c428b0720f",
  "tests/test_contract_validator.py": "6a32fa27dc94e833e834de931f030fbb2d368032b7d528353b5558f8160c4947",
  "tests/test_rt_keys.py": "35939bf3f23a7776f1ab32d4c32ee459afea420b0a37635df0f65a61fcf43c85",
  "tests/test_s0_math_contract.py": "a836c83e115666a5a3b662e40fdbeebd6b7bd7632415732be863346c75cc25f2",
  "tests/test_s1_field_contract.py": "5b343fe326bf38ef2b963c0c0b290657350e1f3db07eab2c94ece87ab76c0e76",
  "audit/audit_s0_independent.py": "1f371284aa041711b8e3315283a078a8ea4e45c18c0b597c39c4658009ffe3e3"
 }
}
```
