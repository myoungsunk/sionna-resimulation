# AMENDMENT-004 — deployable heading multi-start after C1-d failure (pre-freeze of AMENDMENT-003)

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 FROZEN (sha256 `68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34`), not edited |
| Builds on | AMENDMENT-003 (DRAFT rules, commit `2b273ab`). All AMENDMENT-003 rules stay in force except where changed below. |
| Author role | IMPLEMENTER, **SELF_REVIEW_ONLY** |
| Trigger | AMENDMENT-003 C1 verification: DEV field 3 (local technical run) and P0_GEO2 run `40852253296` (Actions, all 10 DEV fields; status FAIL, preserved) |
| Results seen | C1 diagnostics only, all on old-geometry DEV inputs. **No S0V2/S1V2 noise outcome on the v2 geometry exists.** Geometry v2, revisit and plate choices were computed by the registered §B–§D rules and are not changed here. |

## Finding (C1-d failed)

The v2 optimizer run from the prior mean sometimes converges to a **spurious basin**:

- Example: field 3, HIGH window, sensor seed 1. The initial heading is 1.66 prior sd (8.3°) off truth.
- Result from the prior mean: final cost 2966–5239 χ², against 2N = 120 residuals; window-end error ≈ 1 m.
- The same data started at the true θ reaches cost 58–146 χ² with errors of a few cm.
- Local field-3 tally: 11/60 batch runs had |cost(prior start) − cost(true start)| > 1e-3, 8 of them gross (> 1500 χ²).
- Run `40852253296` (600 runs): 7 gross local minima (truth start better by > 10 χ²), all in the HIGH window. The v1 estimator's final cost exceeded χ²₀.₉₉₉(120) in 2.2 % of runs.
- The same run also showed: v1 vs v2 (free tap) cost gap up to 23.3 χ² (v2 never worse beyond 1e-10); free-tap v2 NONCONVERGED 142/600; tap-conditioned v2 NONCONVERGED 3/600, NONSMOOTH 235/600; iteration cap 100 → 300 changes nothing; near-linear exact-posterior test passes (≤ 3e-5 sd, ≤ 3e-6 relative covariance).

This also applies to the frozen v1 estimator. So **the earlier S1 DEV/HOLDOUT batch results (runs `40844896963`, `40845647224`) can contain gross local-minimum outliers**. Their H1/H3/CAL numbers are kept as recorded but must be read as *conditional on that optimizer*. They are superseded for interpretation by the S1V2 runs.

## Change

1. **Batch estimator `batch_map_v2_ms`** (deployable, no truth):
   - Run `batch_map_v2` from the prior mean.
   - If the final cost > χ²₀.₉₉₉(2N) (Wilson–Hilferty, 173.67 for N = 60), re-run from heading offsets k·sd_ψ(P0), k ∈ {−1, +1, −2, +2, −3, +3}, with v = 0.
   - Keep the minimum-cost solution.
   - Recorded per run: trigger, best k, start-0 cost, number of distinct minima (cost gaps > 1 χ²), final misfit flag.
   - Used by every batch arm of S1V2 (IID, ORACLE, XMODEL) and by C1.
2. **C1-d criterion** (replaces the AMENDMENT-003 wording):
   - Pass if cost(estimator) − cost(true-θ start) ≤ 1e-3 in ≥ 99 % of C1 runs, and never > 10 χ².
   - The deployable estimator must reach a minimum at least as good as the one found from the truth, up to the nonsmooth tolerance.
   - Also reported: trigger fraction, final-misfit fraction, and the v1 misfit fraction (contamination estimate for the old runs).
3. **C1-a criterion.** Bitwise reproduction is not achievable across runner hardware. Run `40852253296` regenerated the stored DEV rows with max absolute difference 2.8e-6 (median ≤ 4e-10); a local machine gave 1.7e-2 on POSE cells. The pose-field `eigh` square root of an ill-conditioned kernel and the free-tap discontinuities amplify floating-point differences.
   - New criterion, evaluated on Actions: for all 1500 rows, |Δe|/sd ≤ 1e-3 and |ΔP|/P ≤ 1e-3, using the stored posterior sd and variance.
   - The fraction of bit-identical rows is reported.
   - For S1V2 this is a reproducibility limitation: realisations are tied to the platform, and their distribution is not.
4. **Manifest.** `independence_unit` for P0_GEO2 = `mathematical_deterministic` (schema enum). The P0_GEO2 run `40852253296` aggregate stopped on this schema error; its shard evidence is preserved.
5. **Lock location.** The AMENDMENT_LOCK covering AMENDMENT-003 + 004 is appended **below in this file**. `RUN_REQUEST.amendments` lists both; AMENDMENT-003 carries rules only.

## Not changed

Geometry v2 objective and choice rule, revisit rule, plate rule, decision rules, splits (HOLDOUT2 5000–5059), RT block.

## AMENDMENT_LOCK

Appended after a P0_GEO2 re-run with this estimator reports `PASS`.

Frozen after P0_GEO2 run `40862934784` = PASS. The last json block governs.

```json
{
 "status": "FROZEN",
 "amendment_id": "AMENDMENT-004",
 "frozen_utc_date": "2026-10-29",
 "base_contract_sha256": "68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34",
 "governing_p0_geo2_run": "40862934784",
 "c1_source_run": "40857100181 (re-evaluated under AMENDMENT-005)",
 "p0_geo2_source_git_sha": "f8cb1d16a58ddfc1fcbbeb167e84b2da7f7a4db1",
 "reviewer_status": "SELF_REVIEW_ONLY (implementer); audit of 2026-10-29 addressed; independent re-audit pending",
 "resolved": {
  "HGEOMETRY_CHOICE_V2": {
   "low": "A|S_c7.5_A0.4_W4|0",
   "high": "A|S_c7.5_A0.8_W4|0",
   "dG": 0.521964308340455,
   "DID_psi": -0.4276505375207176,
   "DID_tan": 0.4348592652979715,
   "tan_testable": true
  },
  "REVISIT_CHOICE": {
   "REV60": "A|REV60_y7_x3.0|0",
   "FWD60": "A|FWD60_y7_x3.0|0",
   "y": 7,
   "x0": 3.0,
   "n_revisited_poses": 29,
   "revisit_lag_s_min": 1.0,
   "revisit_lag_s_max": 29.0
  },
  "PLATE_DESIGN_PRE_P3": {
   "LOW": {
    "C10": {
     "cx": 2.75,
     "cy": 1.5,
     "L": 2.0,
     "rot_deg": 0.0,
     "frac_inside": 1.0,
     "excess_delay_taps_median": 6.1851121397611575,
     "status": "ACCEPTED"
    },
    "C11": {
     "cx": 1.75,
     "cy": 8.0,
     "L": 2.0,
     "rot_deg": 45.0,
     "frac_inside": 1.0,
     "excess_delay_taps_median": 10.453355568733695,
     "status": "ACCEPTED"
    }
   },
   "HIGH": {
    "C10": {
     "cx": 2.75,
     "cy": 10.0,
     "L": 2.0,
     "rot_deg": 0.0,
     "frac_inside": 1.0,
     "excess_delay_taps_median": 26.261733961526225,
     "status": "ACCEPTED"
    },
    "C11": {
     "cx": 1.75,
     "cy": 8.0,
     "L": 2.0,
     "rot_deg": 45.0,
     "frac_inside": 1.0,
     "excess_delay_taps_median": 6.498191155109897,
     "status": "ACCEPTED"
    }
   },
   "REV60": {
    "C10": {
     "cx": 3.75,
     "cy": 7.5,
     "L": 2.0,
     "rot_deg": 0.0,
     "frac_inside": 1.0,
     "excess_delay_taps_median": 5.94993408765993,
     "status": "ACCEPTED"
    },
    "C11": {
     "cx": 2.75,
     "cy": 7.5,
     "L": 2.0,
     "rot_deg": 45.0,
     "frac_inside": 1.0,
     "excess_delay_taps_median": 7.560552574671289,
     "status": "ACCEPTED"
    }
   }
  },
  "ESTIMATOR_V2": "batch_map_v2_ms: strict-decrease LM (dec_tol 1e-10, max_iter 100, NONSMOOTH dec<=0.05 & shift<=0.1 sd) + misfit-triggered heading multi-start (chi2_0.999(2N), k in -3..3 sd_psi) + tap-conditioned FFD model for batch arms",
  "C1_CONVERGENCE_VERIFICATION": {
   "C1a_inputs_reproduced": true,
   "C1a_v1_copy_equal": true,
   "C1b_v2_not_worse": true,
   "C1c_iter_cap": true,
   "C1d_truth_start": true,
   "C1e_linear": true,
   "C1f_nonconverged": true
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
   ]
  }
 },
 "run_plan": {
  "S1V2": {
   "fields_DEV": [
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
   "n_confirm_default": 30,
   "n_confirm_large": 60,
   "power_rule": "As frozen (contract run_plan.S1.power_rule), applied to the S1V2 DEV pilot; HOLDOUT2 uses the first n_confirm ids of splits.S_field.HOLDOUT2.",
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
   "canary_trace": "DEV field 0 sensor 0, all windows/cells/arms"
  }
 },
 "stop_before": "P3 RT (pre-P3 amendment + numeric user-approved budget required)",
 "code_sha256": {
  "code/contract_lock.py": "899029d4a891328fe0859471ed8d5e3bbbbcd1071b297764bc111674d0431fd8",
  "code/filters.py": "cc830e55302a416b053c0227fec60a7f2789290a06b19c50233df9e671b35ee9",
  "code/info_core.py": "358180d64d769c5c4f7dde17cc7931550f5cd1ba65169105b4b5ffdc3950c1d4",
  "code/manifest.py": "f63cb34e10c613aeeb8ddb96d1cf09ff8783220609ece00f634f5b676059e370",
  "code/p0_geo2.py": "727953ba1130c86991edd4b47c5b0cd3f098be53e31b00efa578865c4ad86931",
  "code/p0_preflight.py": "1351cf624e7387942241a99233edb68a7f82d9735b28a719ae1f56bdc1bbc1ba",
  "code/rt_keys.py": "0bfb76761e8954a306b78e87c268b1974ea08801cdd960c65471ecfe046db9e7",
  "code/run_phase.py": "9eb0e892e96f78ea58ede4476bbd450e0723eafdef193f655a3b7b36c04d638d",
  "code/s0_math.py": "45462c5f024955028e9bb9a9f3136b7552ce3fd94826a395f8ec364cebd10c1a",
  "code/s0v2.py": "78c3cf3bec878f99c6d5764e089897738b8dcfdd3745cf54a66b8ca003113598",
  "code/s1_mc.py": "2457cfd5764bde987b7ddc4bf89233d56b03ca0b2a08b81b86df122b722443e2",
  "code/s1v2.py": "33be66f46eab25c56f1a0b997f970de936b23ee76c3f21b3e285136c6c126a3d",
  "code/world.py": "7544be2772351c1a6afaa70b29b7465dbad6bf4a5a44dd60a85e05bf76e98f69",
  "scripts/validate_contract.py": "747ca81c05d202353ccda63955ede7ab0012f4b9d38655c9cab0447d004728ff",
  "tests/test_contract_validator.py": "6a32fa27dc94e833e834de931f030fbb2d368032b7d528353b5558f8160c4947",
  "tests/test_rt_keys.py": "35939bf3f23a7776f1ab32d4c32ee459afea420b0a37635df0f65a61fcf43c85",
  "tests/test_s0_math_contract.py": "a836c83e115666a5a3b662e40fdbeebd6b7bd7632415732be863346c75cc25f2",
  "tests/test_s1_field_contract.py": "5b343fe326bf38ef2b963c0c0b290657350e1f3db07eab2c94ece87ab76c0e76",
  "audit/audit_s0_independent.py": "1f371284aa041711b8e3315283a078a8ea4e45c18c0b597c39c4658009ffe3e3"
 }
}
```
