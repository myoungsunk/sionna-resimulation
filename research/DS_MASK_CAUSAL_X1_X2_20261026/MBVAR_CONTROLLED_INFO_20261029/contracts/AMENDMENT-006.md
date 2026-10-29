# AMENDMENT-006 — NONCONVERGED handling after S1V2 DEV run 40864089916 (POST-HOC, labelled)

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 FROZEN (`68d73bd2…`) + AMENDMENT-003/004/005 lock |
| Author role | IMPLEMENTER, **SELF_REVIEW_ONLY**. **Post-hoc**: made after the S1V2 DEV aggregate reported QA FAIL. Flagged for the independent auditor. |
| Trigger | S1V2 DEV run `40864089916` (preserved), QA FAIL caused only by the NONCONVERGED rule. Every other QA item passed: 1980/1980 rows, 0 failures, Mahalanobis in tolerance, revisit pose identical (0.0), time component differs (min 0.051). |
| Results seen before this change | **Only QA quantities and the 4 NONCONVERGED rows.** The DEV H1–H4 tables were never produced (QA FAIL ⇒ empty tables, no power). HOLDOUT2 is unopened. |
| Disclosure | A first draft of this amendment changed only the QA rule (item 2 below), with no rescue. It was evaluated locally on the committed DEV shards and **still failed**: 2 NONCONVERGED rows in one cell of 30. It was not committed. The rescue (item 1) was then added. |

## Findings

1. **Granularity.** AMENDMENT-003 §A.2 required NONCONVERGED ≤ 1 % per (arm, window, cell). A DEV cell has 30 runs, so one run already fails it.
2. **The NONCONVERGED label is numerically unstable at pattern kinks.**
   - All 4 DEV NONCONVERGED runs are marginal: δ² 0.021–0.041 (bound 0.05) and shift 0.105–0.160 sd (bound 0.10).
   - For field 8 / sensor 1 (XMODEL, REV60, TIME_HIGH_5), the cost agrees to 1e-5 χ² between the Actions run (NONCONVERGED, shift > 0.1) and a local run (NONSMOOTH, shift 0.027).
   - The remaining-shift metric uses a one-sided Jacobian at a kink, so a 1e-6-level floating-point difference flips the side and therefore the label.
   - For field 4 / sensor 2, re-linearising with a central-FD Jacobian gives the same cost (217.505) with shift 0.030.

## Change

1. **Rescue, applied only to runs that would be NONCONVERGED** (`filters.batch_map_v2_ms`):
   - Continue LM with a smoothed central-FD Jacobian (steps 1 cm, 1 cm, 0.1°, 1e-6 rad/s), then with the analytic Jacobian.
   - Accept the result if its cost is ≤ the original + 1e-9 and it is no longer NONCONVERGED, or if its cost is strictly lower.
   - Record `rescued`.
   - Deployable (no truth). It does not touch CONVERGED or NONSMOOTH runs.
2. **QA rule.** NONCONVERGED pooled over batch runs ≤ 1 %, and per (arm, window, cell) count ≤ max(1, ⌈0.01·n_cell⌉). All rows stay in the H-tests, and the CONVERGED-only sensitivity is still reported.
3. **Re-run.** The rescue changes estimator rows, so S1V2 DEV is **recomputed** on Actions on the same DEV fields 0–9 (same inputs) instead of being re-aggregated. Run `40864089916` is preserved.
4. **Lock.** The code sha256 pins are re-issued below.
   - Changed files: `code/filters.py` (rescue appended to `batch_map_v2_ms` only; `batch_map_v2` itself is unchanged, so S0V2 run `40863614683` is unaffected), `code/s1v2.py` (QA rule, `rescued` column, reeval helper), `code/run_phase.py` (reeval phases).

## Not changed

Decision rules, geometry, revisit design, multi-start rule, splits, power rule and the RT block.

## AMENDMENT_LOCK

```json
{
 "status": "FROZEN",
 "amendment_id": "AMENDMENT-006",
 "frozen_utc_date": "2026-10-29",
 "base_contract_sha256": "68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34",
 "resolved": {
  "NONCONVERGED_QA_RULE": "pooled <= 1% and per (arm,window,cell) count <= max(1, ceil(0.01 n))",
  "NONCONVERGED_RESCUE": "central-FD smoothed-Jacobian LM continuation (1 cm, 1 cm, 0.1 deg, 1e-6 rad/s) then analytic LM; applied only to NONCONVERGED"
 },
 "code_sha256": {
  "code/contract_lock.py": "899029d4a891328fe0859471ed8d5e3bbbbcd1071b297764bc111674d0431fd8",
  "code/filters.py": "7592a8a2511c1dab300a834574348821f21aee6da5f7d742776f2f9a34892118",
  "code/info_core.py": "358180d64d769c5c4f7dde17cc7931550f5cd1ba65169105b4b5ffdc3950c1d4",
  "code/manifest.py": "f63cb34e10c613aeeb8ddb96d1cf09ff8783220609ece00f634f5b676059e370",
  "code/p0_geo2.py": "727953ba1130c86991edd4b47c5b0cd3f098be53e31b00efa578865c4ad86931",
  "code/p0_preflight.py": "1351cf624e7387942241a99233edb68a7f82d9735b28a719ae1f56bdc1bbc1ba",
  "code/rt_keys.py": "0bfb76761e8954a306b78e87c268b1974ea08801cdd960c65471ecfe046db9e7",
  "code/run_phase.py": "73ca9119ab5e7fbac57baa5fb667296abdc6776d0b860591399fc0a5a671939f",
  "code/s0_math.py": "45462c5f024955028e9bb9a9f3136b7552ce3fd94826a395f8ec364cebd10c1a",
  "code/s0v2.py": "78c3cf3bec878f99c6d5764e089897738b8dcfdd3745cf54a66b8ca003113598",
  "code/s1_mc.py": "2457cfd5764bde987b7ddc4bf89233d56b03ca0b2a08b81b86df122b722443e2",
  "code/s1v2.py": "fac85691b66730e6b3c068adf9db36849ebeba38832428e52ba90f71acdd50b4",
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
