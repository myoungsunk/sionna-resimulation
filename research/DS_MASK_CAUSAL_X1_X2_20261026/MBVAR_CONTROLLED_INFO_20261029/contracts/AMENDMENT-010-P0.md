# AMENDMENT-010-P0 — execution lock for the A010 forensic ablation only

| Field | Value |
|---|---|
| Scope | Runs `code/a10_p0.py` (phases P2_A010P0_GEN, P2_A010P0_ABL) on **4 existing DEV2 keys**. Forensic and **not confirmatory**. No estimator, threshold or scientific rule is adopted. AMENDMENT-010 stays DRAFT. |
| Why a lock | The workflow runs only under a FROZEN lock with matching code hashes. This lock fixes the code and the key list before any A010 result exists. |
| Keys | K1 `10/LOW/TIME_1/s2/ORACLE` (C3 kink bifurcation) · K2 `11/REV60/TIME_HIGH_5/s0/ORACLE` (near-alternative minimum) · K3 `10/LOW/LOWCORR/s1/IID` (smooth no-kink control, the first S1V4 row meeting the rule field ∈ {10, 11}, LOW, LOWCORR, IID, CONVERGED_SMOOTH, kink 0) · K4 `15/REV60/POSE_HIGH/s1/ORACLE` (largest C3V4 Δcost) |
| Canonical input | S1V4 run `40992623257` receipts, byte copies. The S1V3 receipt hash is recorded alongside. |
| Replicates | Each key is run in two separate CI jobs (A, B) from identical archived inputs. The CPU and library of each job are recorded. Distinct CPUs cannot be forced, so their number is reported, not assumed. |
| Fixed parameters | Polish τ ∈ {1e-3 (baseline, ≤ 30 steps), 1e-3, 1e-6, 1e-9 (≤ 300 steps)}. Perturbation fixture: 1e-14 · N(0, 1) on z, seeds 1–3, τ ∈ {1e-3, 1e-9}. `Lhalf` check: \|LLᵀ − K_psd\|_max / \|K\|_max ≤ 1e-10. K2 straight-line profile at t ∈ [−0.25, 1.25], 31 points. |
| Preserved | Everything earlier. G5 FAIL stands. HOLDOUT2 and P3 are NO-GO. |
| Role | IMPLEMENTER, SELF_REVIEW_ONLY |

## Pre-freeze local technical check (not evidence)

- Local runs, in-memory lock: GEN; ABL K3 A and B; ABL K2 A; aggregate.
- Two code bugs were found and fixed before this freeze: an `Xp` reference before assignment, and a missing contract file in the manifest.
- All negative fixtures were detected.
- Observations from these runs are not used to set any parameter above.

## AMENDMENT_LOCK

```json
{
 "status": "FROZEN",
 "amendment_id": "AMENDMENT-010-P0",
 "frozen_utc_date": "2026-11-01",
 "base_contract_sha256": "68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34",
 "amendment_text_sha256": {
  "AMENDMENT-003": "a94fea6dfbedf34783eed34c76b04d67297698cdec3f1d914303e6f05a1ee6a4",
  "AMENDMENT-004": "a188245a2c827312ffd3f1775bfdc63c8a66a0aca66bd62d64b231489ce51c60",
  "AMENDMENT-005": "0cf11f09cec8e1d4d09509fa9b3a37a9377d167b3c8650a84ed84b0a5b393401",
  "AMENDMENT-006": "0244c8b6f68184f6c0e9e50039f5522eff0d4eb64c6d58c4a7985775a4dd0201",
  "AMENDMENT-007": "1ce644983fb2f57383aa856e6e662297c5ceb71544b72c0ea7c77f4b3197af68",
  "AMENDMENT-008": "0950a1806b655e98f2bc2f31bee9c0fde632ee8b1612d63f45e86bf5d8acd2d5",
  "AMENDMENT-009": "e498b1e54b85c164710698d4ca7a8386f7e4cde91ac3c86fa1daabbcc8f6a939",
  "AMENDMENT-010_DRAFT": "63e61784351ce01ce81efc5dc8bd897f85351ca3bfd74c2e8d65056c85d47a09"
 },
 "scope": "forensic ablation of 4 existing DEV2 keys only; no estimator/threshold/science rule adopted; AMENDMENT-010 remains DRAFT",
 "trigger": {
  "proposer_handoff": "reviews/PROPOSER_A010_IMPLEMENTER_HANDOFF_DRAFT_20261030_KO.md",
  "audit_branch": "audit/mbvar-info-c3-a010-proposal-20261030",
  "audit_commit": "ef0b707c"
 },
 "reviewer_status": "SELF_REVIEW_ONLY",
 "resolved": {
  "A010P0_PARAMETERS": {
   "taus": [
    0.001,
    1e-06,
    1e-09
   ],
   "tau_max_steps": 300,
   "baseline": "S1V4 polish 1e-3 / 30",
   "perturbation": "1e-14 N(0,1) on z, seeds 1-3, tau 1e-3 and 1e-9",
   "LLt_rel_tol": 1e-10,
   "profile_t": "linspace(-0.25,1.25,31)",
   "starts_K2": "psi k=-3..3 sd, x+1, y+1 (truth-free); truth ORACLE_ONLY",
   "AMBIGUOUS_rule": "truth-free solution with dcost <= 1 chi^2 and end-state > 2 d_ref"
  },
  "HOLDOUT2_STATUS": "CLOSED",
  "P3_STATUS": "NO-GO",
  "DEV3_STATUS": "CLOSED until AMENDMENT-010 freeze after independent audit"
 },
 "run_plan": {
  "A010P0": {
   "cases": {
    "K1": [
     10,
     "LOW",
     "TIME_1",
     2,
     "ORACLE_CORR_BATCH"
    ],
    "K2": [
     11,
     "REV60",
     "TIME_HIGH_5",
     0,
     "ORACLE_CORR_BATCH"
    ],
    "K3": [
     10,
     "LOW",
     "LOWCORR",
     1,
     "IID_BATCH"
    ],
    "K4": [
     15,
     "REV60",
     "POSE_HIGH",
     1,
     "ORACLE_CORR_BATCH"
    ]
   },
   "reps": [
    "A",
    "B"
   ],
   "canonical_source": "results/P2_S1V4_run_40992623257 receipts"
  }
 },
 "code_sha256": {
  "code/a10_p0.py": "7e40049a8d292376f3e1c94745fb451ba6b19a549f196c6d83948935dd10d672",
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
  "code/run_phase.py": "a646cda4ce5e33d6c4df935634d98b8f7bb45cd3f42994294e891561778ed770",
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
