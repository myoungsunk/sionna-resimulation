# EXPERIMENT_CONTRACT_MBVAR-INFO-001 — proposer draft, NOT FROZEN

| Property | Value / rule |
|---|---|
| ID | `MBVAR-INFO-001` |
| stage | `DRAFT-0.1`; invalid for confirmatory runs until P0 required locks |
| author role | `PROPOSER` |
| goal | State-specific RF information overcount vs true spatial/time covariance, followed by physical Sionna RT mechanism replication |
| base repository | `myoungsunk/sionna-resimulation` |
| base branch candidate | `research/mbvar-e2-e5-revalidation-20261029` — full git SHA must be locked |
| governance commit | `P0_TO_RESOLVE_GOVERNANCE_SHA` |
| full source commit | `P0_TO_RESOLVE_SOURCE_SHA` |
| params | `config/PLAN_PARAMETERS.json` frozen SHA after P0 |
| data isolation | S synthetic field_id, R scene_variant_id nested in family; anchor/path/gyro seeds repeated |
| baseline | 4-state `[px,py,psi,b_g]`, r/s measurement, original `ctl_core` parity |
| prior studies | E4 `H_TC=REJECT` globally; E5 uncorrected information normalization not reusable |

## Registered estimands

**E1 fixed-H covariance effect**: For a fixed linearized `F,H,Q,P0`, compare per-state nuisance-marginalized info/posterior variance with `Σ_corr` vs `Σ_blockdiag` at identical marginal σ. Controlled from ex ante symbolic Σ; repeated independent draws validate theoretical prediction.

**E2 fixed-Σ geometry effect**: For identical `Σ,F,Q,P0`, compare `H_low` vs `H_high` schedules selected from FFD-only pilot using geometry (not residual or RMSE). Physics may not realize fixed-Σ geometry changes; E2 is S0 mathematical experiment.

**E3 geometry×correlation interaction**: 
`DID_a = [log(OC_a(highcorr,LOWgeom))−log(OC_a(lowcorr,LOWgeom))] − [log(OC_a(highcorr,HIGHgeom))−log(OC_a(lowcorr,HIGHgeom))]`.
`OC_a=I_iid,eff(a)/I_corr,eff(a)` on a consistent prior/parameter target; no universal sign preregistered. Compute exact predicted DID from selected matrices **before** noise outcomes.

**E4 estimator consequence**: Under matched synthetic datasets and known true Σ, compare ensemble Heading/rad/tan/XY MSE, posterior covariance calibration and 4-state NEES of IID model and oracle correlated Gaussian reference. No “oracle wins each realization” rule.

**E5 physical RT mechanism**: Within each paired scene variant and exact anchor/pose, compare C00 DIRECT vs C01 FLOOR vs C10/C11 plate complex H, s/r, paths/taps, and the direction of matched state information/accuracy metrics. RT intervention is multifactor (mean/variance/tap) and does not isolate correlation.

**E6 robustness/transfer**: Record B0 and sensor-seed variations without counting them as new RF scenes; final unseen scene variants withheld until estimator and claims frozen. Existing Corridor/Office runs for retrospective diagnostic only.

## Competing explanations and decisive controls

| Explanation | Controlled observation | Distinguishing evidence |
|---|---|---|
| inter-time covariance alone | S0 fixed H/Σ arms | exact predicted OC and Gaussian posterior |
| spatial pose field vs pure temporal drift | same pose, different t / different pose, same elapsed time | pose-field repeated exactly; OU varies with t |
| H/J variation | S0 fixed covariance, swapped H | conditional state information change |
| RF mean and distance dependent variance | S1 primary zero mean constant σ; R reports raw mean and σ separately | eliminate confounding from synthetic primary, quantify in physical |
| r/s cross-correlation | C_rs=I then c=.3 | per-state info sensitivity |
| geometry/model linearization | full FFD h/H vs exact finite differences, ell remainder | report large nonlinear error |
| tap switching | raw tap index and first-path discontinuity | separate strata, do not delete |
| gate selection | no-gate/fixed/self separate | changes from gate are not called covariance-only effect |
| gyro/odometry | paired sensor seeds, same paths | within-field repeated effects |

## Acceptance tests (technical, non-scientific)

- `MATH-01`: same/opp analytic ratios at rho=.9 `.5263157894736842`, `10.0` within 1e−10.
- `MATH-02`: symmetric PSD covariance operator; max asymmetry ≤1e−12 scale-normalized, eigenvalue min ≥−1e−10×largest eigenvalue on canary N≤32; Cholesky with explicit diagonal jitter policy or STOP.
- `MATH-03`: correct normalized information `D^T I D`, validated under m↔cm and rad↔deg unit transformations within relative 1e−10.
- `DATA-01`: identical canonical `(scene, anchor, pose, solver)` yields identical `H` digest; pose GP spatial part equal within 1e−12.
- `DATA-02`: marginal variance invariant under low/high correlation arms to relative 1e−12 by construction. Monte Carlo sample covariance is approximate and uses predeclared tolerance set from field-trial power, not a blanket deterministic ±10% rule.
- `FILTER-01`: original MB_VAR on R4-B and R5-A B0 state+P full-trace parity ≤1e−10 absolute to pinned reference (if input version mismatch -> BLOCKED_INPUT).
- `RF-01`: direct-only and floor distinct path counts; full/LoS complex reference differences preflight-defined in `P0_TO_RESOLVE_DIRECT_PARITY_TOL` and frozen *before* canary.
- `RF-02`: no invalid robot/anchor pose, unreported blocking, invisible path, or changed 2×2 port/channel convention; if unsupported -> STOP.
- `LEAK-01`: no train/development/test overlapping `field_realization_id` or `scene_variant_id`. Matching repeated anchors within scene retained in one fold.
- `REPRO-01`: all frozen config/source/scene/pose hashes and raw output manifests preserved; failures are tracked.

## Candidate experimental values (all PLAN; not physical truth)

- `rho_S0 ∈ {0,0.5,0.9}`; `sigma_S0=1` for analytic proof.
- S1 `sigma_r=.05 m, sigma_s=.02`, `alpha_high=.7`, `ell_p=.5m`, `ell_psi=20°`, `time-alpha=0`, `c_rs=0`; white control `alpha_p=0,alpha_w=1`.
- Negative controls: `alpha_t=.3`, `tau∈{1,5}s` (synthetic-only), `c_rs=.3`, same pose exact revisit.
- Anchors A=(2,2,2.65), C=(6,10,2.65), B=(10,2,2.65) reserve; robot z=.45, mount=0°, 12×12 m world.
- Paths T1 x=2..10 y=6 yaw0; T4 sinusoidal y=5.5+.8sin(2π(x−2)/8) tangent yaw; T5 (6,6) spin 0..360° step 5°, initial=final same physical pose.
- Track R canary C00/C01/C10 at no more than 288 unique pose-anchor-scene configs plus exact pose identity QA; actual budget require user approval before higher-scale RT.

## Units and interventions

All code must log whether an effect changes H, covariance, measurement mean, observation selection, time, Q and gate; **no intervention may be described as single-factor unless all other components invariant**. 

## Expected scientific verdicts (labels only, no declared outcome)

- `SUPPORTED`: evidence satisfies preregistered effect/uncertainty conditions in S0/S1 and/ or R, exactly specifying which track.
- `MIXED`: mechanism works in some geometry/scene conditions but not global; R5-B-type harm reported.
- `NOT_SUPPORTED`: pre-specified expected quantitative effect not observed with valid data and sufficient power.
- `INCONCLUSIVE`: insufficient independent realizations, PSD/geometry mismatch, model nonidentifiability, or unresolved covariance fitting.

No exact effect-size/CI threshold for physical R may be assigned until **P0_TO_RESOLVE_EFFECT_SIZE** from pilot/design power is frozen before holdout. A missed threshold is not a technical runtime failure.

## Lock/STOP fields (required before a run can be called confirmatory)

`P0_TO_RESOLVE_GOVERNANCE_SHA` ; `P0_TO_RESOLVE_SOURCE_SHA` ; `P0_TO_RESOLVE_MATERIAL` ; `P0_TO_RESOLVE_HGEOMETRY` ; `P0_TO_RESOLVE_DIRECT_PARITY_TOL` ; `P0_TO_RESOLVE_FINAL_SPLITS` ; `P0_TO_RESOLVE_RF_BUDGET` ; `P0_TO_RESOLVE_EFFECT_SIZE`.

Science-affecting fields (`GOVERNANCE_SHA`, `SOURCE_SHA`, `HGEOMETRY`, `FINAL_SPLITS`, `EFFECT_SIZE`) block S0/S1 until resolved and science contract freeze. RF-only (`MATERIAL`, `DIRECT_PARITY_TOL`, `RF_BUDGET`) may instead be resolved and frozen in a signed **pre-P3 RT amendment**, but no canary/bulk RT may run without exact config and a numerical budget. P0_PREFLIGHT is allowed with DRAFT contract hash, audit only.

## FROZEN_LOCK

The draft text above is kept verbatim (append-only). This section freezes the science contract after P0 `PASS` (run `40842954635`). It resolves the science fields for S0/S1. RF fields stay deferred to a signed pre-P3 amendment. `code_sha256` pins every file under code/, scripts/, tests/ and audit/. Any later change needs an amendment ID and a new run. Machine-readable lock (the last json block in this section governs):

```json
{
 "status": "FROZEN",
 "contract_id": "MBVAR-INFO-001",
 "frozen_utc_date": "2026-10-29",
 "governance_git_sha": "250d617ad89a4105fa1af546cc83ceed9de98f42",
 "base_git_sha": "af8e0a1b5299ae5e279f9b602afd2f1bb710c4e3",
 "draft_contract_sha256": "9fc4538c2d1c90e7b26acacfd460255ea9af9dc0bceceeeb3b7926082f974955",
 "p0_status": "PASS",
 "p0_runs": {
  "40840192251": "BLOCKED_GEOMETRY_MATCH (preserved)",
  "40840770105": "PASS, geometry superseded by AMENDMENT-002 (preserved, unused)",
  "40842954635": "PASS (governing P0 for this freeze; source_git_sha a42b7e99b9f9a25b5d50b0f862b7a855286bc263)"
 },
 "amendments": [
  "AMENDMENT-001",
  "AMENDMENT-002"
 ],
 "reviewer_status": "SELF_REVIEW_ONLY: no independent PROPOSER/AUDITOR session exists; user directive 2026-10-29 authorises proceeding; every output is TECHNICAL_QA_ONLY, not a research release",
 "resolved": {
  "GOVERNANCE_SHA": "250d617ad89a4105fa1af546cc83ceed9de98f42",
  "SOURCE_SHA": {
   "base_git_sha": "af8e0a1b5299ae5e279f9b602afd2f1bb710c4e3",
   "fetch_inputs_commit": "9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13",
   "pinned_sha256": {
    "repo:pol_bias_model/exp_pb.py": "a637c3ef0322546215cab7aef76889f1e6e256048bb2821f1b9967679e534972",
    "repo:reflect_model/common.py": "7371c3f7effb3daad61114e35691fb8807cd7632c1472a73b9032400a912209d",
    "repo:reflect_model/fetch_inputs.sh": "e7680b95f4d4b087e29531d1b76cfcae41d042f7b880bdea1ffd705cf5e8fc95",
    "repo:config/PLAN_PARAMETERS.json": "bba7fbc5e165359da2583f94b16c78ed8e475e216c6935080361a38442b28bbc",
    "repo:contract(draft)": "9fc4538c2d1c90e7b26acacfd460255ea9af9dc0bceceeeb3b7926082f974955",
    "pinned:EKF4_RANGE_S_STAGED_20261014/core.py": "1abdac002631e1de2303b0ef7c39c6c9eb619b53d9ba9fd8d89d1a3cd9c630d1",
    "pinned:FFD_P0P3_20261016/source_model.py": "e2591ecb238917e656e2effe50b0cb92543be343e90aef460edcf7b859820ba3",
    "pinned:EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py": "dfec050fcc81ff39aed0058a2654b3b845b8d3320437136a3f2317033e5efe22",
    "pinned:qclean_uwb/drivesim/observation.py": "95079dc044a31d94a1aa7f771fb0d59093d15571bcc4752167ad93e47837dbab",
    "pinned:qclean_uwb/drivesim/pattern_apply.py": "ab991a70a7333dbd7b0b9b90d8845ce306fc5e1bd6c73de7c6e62184242969e8",
    "pinned:qclean_uwb/drivesim/sensor_v2.py": "56ea1c8f5afbd1c9662885366155c490d7ad01009d8a0bf8ebe3d7f85647c2ac",
    "bank:LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
    "bank:LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9",
    "rf:H_R4_aB_m0.npy": "30743ca017615bbfede78a8350739262a756d47ac2213c60b08eb109cebfe1b0",
    "rf:SAMPLES_R4_aB_m0.json": "a7978081d26d4f67cc420af0f3e1dffab77eed44a2205043bf2e67858e43967e",
    "rf:H_R5_aA_m0.npy": "026a2c5ebb17916633f74d767ec8675f9358c93f8a4ee0df465733838ec89f80",
    "rf:SAMPLES_R5_aA_m0.json": "cd0c1e202e4c99b4946de09a0a5a407d8397b6b8c19a768c6e2c5fe29ac0335a"
   },
   "plan_parameters_sha256": "bba7fbc5e165359da2583f94b16c78ed8e475e216c6935080361a38442b28bbc"
  },
  "HGEOMETRY": "RESOLVED by P0 run 40842954635 (PLAN_P0_P6 \u00a7K + AMENDMENT-001 + AMENDMENT-002)",
  "HGEOMETRY_CHOICE": {
   "low": "A|T2_TANGENT_A_Y7|0",
   "high": "A|T4_S_CURVE|60",
   "dG": 0.7821977853504691
  },
  "FINAL_SPLITS": "see splits (Track S field ids frozen; Track R scene-variant ids reserved, frozen with configs in the pre-P3 amendment)",
  "EFFECT_SIZE": "Track S rules in EFFECT_SIZE_RULES; Track R physical thresholds DEFERRED to the signed pre-P3 amendment (to be set from S results + R pilot power, before any R holdout)",
  "EFFECT_SIZE_RULES": {
   "scope": "P2_S1 Track S only",
   "equivalence_factor": 1.5,
   "did_min_predicted_factor": 1.25,
   "did_min_fraction_of_prediction": 0.5,
   "oracle_gain_ratio_max": 0.8,
   "ci": "95% percentile field bootstrap, B=4000, seed 20261029, resampling field_realization_id (sensor seeds stay inside their field)",
   "H1": "IID_BATCH realised inflation infl=mean_f(MSE)/mean_f(claimed var), states tan & psi at the window end, LOW/HIGH x LOWCORR/POSE_HIGH: PASS if CI of log(infl_S1/infl_S0) inside +-log(1.5); FAIL if disjoint; else UNDETERMINED",
   "H2": "DID of log infl (IID_BATCH) [LOW:POSE_HIGH-LOWCORR]-[HIGH:POSE_HIGH-LOWCORR], states tan & psi; testable iff |DID_S0(JOINT)|>=log(1.25); PASS if CI excludes 0 on the predicted side; FAIL if the predicted-side upper bound < 0.5|DID_S0|; else UNDETERMINED",
   "H3": "POSE_HIGH: MSE(ORACLE_CORR_BATCH)/MSE(IID_BATCH) for tan & psi, both windows; applicable iff S0 ratio <= 0.8; PASS if CI upper < 1; FAIL if CI lower > 1; else UNDETERMINED",
   "CAL": "ORACLE_CORR_BATCH realised/claimed variance, tan & psi, both windows, primary cells: CI of log inside +-log(1.5)",
   "verdict": "any H1 FAIL -> NOT_SUPPORTED; any H1 UNDETERMINED or no testable H2/H3 -> INCONCLUSIVE; all testable H2/H3 + CAL PASS -> SUPPORTED; any PASS or FAIL among them otherwise -> MIXED; else INCONCLUSIVE; QA or S0-reference failure -> INCONCLUSIVE with execution FAIL",
   "sensitivity_cells": "TIME_1, TIME_5, POSE_HIGH_C03 and states rad/bg are reported (S1_SENS) but do not enter the verdict",
   "descriptive_only": "IID_EKF_NOGATE, IID_EKF_SELFGATE, MB_VAR_NOGATE are reported (S1_STATS) without a registered hypothesis"
  },
  "MATERIAL": "DEFERRED_PRE_P3_AMENDMENT",
  "DIRECT_PARITY_TOL": "DEFERRED_PRE_P3_AMENDMENT",
  "RF_BUDGET": "DEFERRED_PRE_P3_AMENDMENT"
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
   "HOLDOUT": [
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
   ]
  },
  "R_scene_variant": {
   "CAL": [
    2000,
    2001,
    2002,
    2003,
    2004,
    2005,
    2006,
    2007,
    2008,
    2009
   ],
   "DEV": [
    2100,
    2101,
    2102,
    2103,
    2104,
    2105,
    2106,
    2107,
    2108,
    2109
   ],
   "HOLDOUT": [
    2200,
    2201,
    2202,
    2203,
    2204,
    2205,
    2206,
    2207,
    2208,
    2209,
    2210,
    2211,
    2212,
    2213,
    2214,
    2215,
    2216,
    2217,
    2218,
    2219,
    2220,
    2221,
    2222,
    2223,
    2224,
    2225,
    2226,
    2227,
    2228,
    2229,
    2230,
    2231,
    2232,
    2233,
    2234,
    2235,
    2236,
    2237,
    2238,
    2239
   ]
  }
 },
 "run_plan": {
  "S1": {
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
   "power_rule": "From the DEV pilot only: for every primary H1/CAL/testable-H2/applicable-H3 contrast, projected 95% half-width 1.96*se_dev*sqrt(n_dev/n) must be <= its margin (H1/CAL: log1.5-|dev|; H2: |DID_S0|/2; H3: |log ratio_S0|/2). n_confirm = 30 if all fit, else 60 (flag underpowered_at_max if 60 does not fit). HOLDOUT uses the first n_confirm ids of splits.S_field.HOLDOUT.",
   "smoke": "SMOKE ids are technical execution checks only; never pooled or used for any decision",
   "sensor_seeds": [
    0,
    1,
    2
   ],
   "window_N": 60,
   "dt_s": 0.5,
   "arms": [
    "IID_EKF_NOGATE",
    "IID_EKF_SELFGATE",
    "MB_VAR_NOGATE",
    "IID_BATCH",
    "ORACLE_CORR_BATCH"
   ],
   "cells": {
    "LOWCORR": "alpha (0,0,1) c 0",
    "POSE_HIGH": "(0.7,0,0.3) c 0",
    "TIME_1": "(0,0.3,0.7) tau 1 s",
    "TIME_5": "(0,0.3,0.7) tau 5 s",
    "POSE_HIGH_C03": "(0.7,0,0.3) c 0.3"
   },
   "generator": "z = h_LOS(x_true) + eps, mu = 0, no clipping; control noise ~N(0,q) as filter Q; x0 ~ N(x_true0, P0 = diag(0.1 m, 0.1 m, 5 deg, 0.2 deg/s)^2); RNG key (contract_sha256, cell_id, field, stream, window, sensor) per code/s1_mc.py docstring",
   "self_gate": "joint NIS 9.210340371976184 (own filter)"
  }
 },
 "stop_before": "P3 RT (no canary or bulk RT without a signed pre-P3 amendment and a numeric user-approved budget)",
 "code_sha256": {
  "code/filters.py": "b90bbaaa69764131728fc6b1757def570884af6ab736fca5308280876d8130ff",
  "code/info_core.py": "358180d64d769c5c4f7dde17cc7931550f5cd1ba65169105b4b5ffdc3950c1d4",
  "code/manifest.py": "f63cb34e10c613aeeb8ddb96d1cf09ff8783220609ece00f634f5b676059e370",
  "code/p0_preflight.py": "1351cf624e7387942241a99233edb68a7f82d9735b28a719ae1f56bdc1bbc1ba",
  "code/run_phase.py": "c8ff754bb038730eb7693ce2956bd88b6ea2fe070fc4ea3808b342b6ca580467",
  "code/s0_math.py": "3ebdf9a726d08cc89d787018c4387f76bdd89c1792341e79328811073a00e3cc",
  "code/s1_mc.py": "2457cfd5764bde987b7ddc4bf89233d56b03ca0b2a08b81b86df122b722443e2",
  "code/world.py": "ac6e2de5ada3c1e418cabd27498cfe1b7809ab2ab4181121fb8be65d60818e4f",
  "scripts/validate_contract.py": "aa33b75bf613fd1c873116b080c0bf407793814bd86ce7e4998a80100d61a99a",
  "tests/test_contract_validator.py": "6a32fa27dc94e833e834de931f030fbb2d368032b7d528353b5558f8160c4947",
  "tests/test_s0_math_contract.py": "a836c83e115666a5a3b662e40fdbeebd6b7bd7632415732be863346c75cc25f2",
  "tests/test_s1_field_contract.py": "5b343fe326bf38ef2b963c0c0b290657350e1f3db07eab2c94ece87ab76c0e76",
  "audit/audit_s0_independent.py": "1f371284aa041711b8e3315283a078a8ea4e45c18c0b597c39c4658009ffe3e3"
 }
}
```
