# MBVAR-INFO-001 — Track R P3 Sionna RT preflight & canary PREPARATION (DRAFT / NO RUN)

**Date:** 2026-11-04 · **Role:** PROPOSER / `RT_PRE_P3_PREPARATION_ONLY` · **status:** `NOT_FROZEN / RT_NO_GO / USER_BUDGET_PENDING`  
**Input science policy:** `AMENDMENT-010-PROPOSER-SCIENCE-DECISIONS-FINAL-20261104.md`; operational estimator unchanged S1V5 E′.  
**Governing sources:** `contracts/EXPERIMENT_CONTRACT_MBVAR-INFO-001.md`, `SCIENCE_SPEC.md`, `docs/research-governance/COMMON_CONTRACT.md`, `ROLE_PROPOSER.md`, `code/rt_keys.py`.

## 1. Why RT is a separate prospective intervention

Track S synthetic GP error data is not equivalent to Sionna RT. Track R tests **matched physical complex-channel mechanisms**; a change in plate/reflector/scene can modify LoS, reflected paths, arrival angles, complex amplitude, first-path switching, measurement mean/variance and tap selection **at the same time**. Never advertise a physical multi-factor scene change as a pure covariance-only causal effect.

Track R is `scene_variant_id` clustered in `scene_family`; multiple poses/anchors/sensor-seeds in one variant are repeated measurements, not independent RT realizations. Fixed calibration data and unseen evaluation scenes must remain separate. Do not import previous Corridor/Office residual mean or S1's exact oracle Σ as a fitted physical RT model.

## 2. Proposed staged run plan — zero current execution

| Stage | Proposed scope | Prerequisite | Non-negotiable stop |
|---|---|---|---|
| P3-R0 inventory only | enumerate source FFD/mesh/material/extractor hashes, physical coordinate convention, 257-bin/two-port input mapping, numerical budget proposal | no RT compute | any missing hash/units/frame/first-path convention -> BLOCKED_PREP |
| P3-R1 DIRECT reference canary | **C00 DIRECT**, a small pre-signed subset of exact `(scene,anchor,pose)` keys; legacy direct-only parity | signed pre-P3 material/parity/source and user-approved numeric budget | wrong complex H, geometric pose, ports or LoS path count -> STOP |
| P3-R2 matched floor check | same exact pose/anchor/scene family **C01 FLOOR** vs C00 | R1 parity PASS | scene/material/solver/tap mismatch or untracked factor -> STOP |
| P3-R3 reflector mechanism | matched **C10/C11 plate/reflection** vs fixed baseline and C01 | R2 PASS and variant split lock | untracked first-path switch, response invalid, leakage -> STOP or isolate |
| P3-R4 field/scene science study | independent `scene_variant_id` and calibration/test split; physical means and variances fitted with uncertainty | signed pilot power/effect-size and separate higher-cost authorization | improperly pooled pose samples, unmodelled multipath mean, or noninvertible Σ -> BLOCKED |

A single canary with a physical contrast does not independently establish repeatable stochastic time correlation. The **entire planned canary cap is ≤288 unique pose–anchor–scene configurations**, not an authorization to run 288. Approved executed count must be given exactly in a signed separate action. `N_canary=0` now.

## 3. Immutable and still MISSING inputs

- `scene_geometry_sha256`: **MISSING** exact Sionna mesh material association and scene geometric coordinate origin.
- `materials_sha256`: **MISSING** exact complex ε/σ/scattering material parameters and any plate geometry.
- `anchor_xyz_m`: A=(2,2,2.65)m in existing synthetic world; physical P3 needs **explicit verification** that source RT coordinate system and anchor have identical transforms. Do not silently reuse synthetic coordinates for a new RT scene.
- `pose_xy_m`, `yaw_deg`, `robot_z_m`, `mount_deg`: full planned pose ledger and antenna frame for each scene **MISSING**. Synthetic robot z=.45m/mount 0° are *references*, not silently asserted physical geometry.
- `ffd_bank_sha256`: **MISSING** exact full bank source hashes and port basis/orientation. Existing source model may be pinned but no physical P3 parity claim without archive.
- `solver`, `solver_version`, `max_depth`, `solver_flags`, `freq_grid_sha256`: **MISSING** explicit RT software backend/versions/path-depth/frequency set; do not guess or change defaults mid-run.
- `extractor_sha256`: **MISSING** frozen complex H→tap→first-path/257-bin r and signed s extractor including calibration offset and port convention. LoS-only analytic `h/H` and full RT path extraction must have explicit parity checks.
- `source_git_sha`, `governance_git_sha`, `input_lock_sha256`, `scene_variant_id`, `scene_family`, `fold_id`: must be pinned and immutable in a separate signed manifest.
- Direct-vs-floor numeric `H_complex` parity tolerances, path count/tap thresholds, phase convention: **MISSING** numeric pre-registered acceptance and fail-closed rules.
- Exact RT costs/throughput: **MISSING** (do not invent seconds, GPU hours, price per config).

**Cache key must include all fields in existing `code/rt_keys.py:REQUIRED`; a synthetic `pose_key()` is not an RT cache key.**

## 4. Cost/throughput gate requiring explicit user permission

Freeze a **finite** numeric budget before any C00 canary:
- `N_keys_approved` (# unique configurations) and `N_solver_calls_max` (includes repeated extractions/retries), both exact.
- GPU/CPU model, worker count, backend versions and measured canary per-key `t_wall_p50_s`, `t_wall_p95_s`, `peak_gpu_gb`; **unknown until non-RT benchmark or separately authorized pilot**.
- Total projected worst-case: `T_worst_hours = (N_solver_calls_max * t_wall_p95_s) / (3600 * concurrency_eff) + fixed_setup_hours`; `cost_cap = GPU_hours_cap * currency/hour + storage/transfer`. For unknown throughput, user must authorize a conservative bounded pilot with hard time/compute stop rather than claim an estimate.
- Stop before exceeding either `N_keys_approved`, `N_solver_calls_max`, `GPU_hours_cap`, `storage_gb_cap`, `user_cost_cap`; no extra runs to rescue failing path parity.
- User approval must specify **number, unit, hardware, currency**, not a vague approval to “do RT”.

Current placeholders: `N_keys_approved=0`; `N_solver_calls_max=0`; `GPU_hours_cap=0`; `user_cost_cap=0`. Thus **no physical RT invocation is permitted now**.

## 5. Data contract and audit plan for later P3

Every key: source/geometry/materials/solver/extractor SHA256, scene family/variant, anchor position and orientation, path/trajectory/pose ID, physical antenna polarization/port basis, full complex H and path/tap metadata, extracted range (m), signed s (unitless), complete first-path index, LoS/blocked flags, RF direct-vs-floor/plate contrasts, timestamp only if actually dynamic, original failure reason and SHA manifest. Failures must remain in the denominator; no hidden masking/clipping/synthesized observation as “measured”.

After each gate independent reviewer must distinguish `NUMERIC_REPLAY_PASS`, `PHYSICAL_PARITY_PASS`, `SCENE_LEVEL_EFFECT_SUPPORTED/MIXED/NOT_SUPPORTED/INCONCLUSIVE`. HOLDOUT2 and physical Track R test variants remain sealed until separately released.

## 6. Exact authorization / STOP record

```json
{
  "contract_id": "MBVAR-INFO-001",
  "phase": "P3_RT",
  "status": "PREP_ONLY_NOT_FROZEN",
  "signed_pre_p3_amendment": false,
  "material_and_mesh_input_sha_locked": false,
  "direct_floor_complex_H_tolerances_frozen": false,
  "scene_variant_splits_frozen": false,
  "user_approved_numeric_budget": false,
  "n_approved_rt_keys": 0,
  "max_solver_calls": 0,
  "rt_canary": "NO-GO",
  "rt_bulk": "NO-GO",
  "holdout2": "NO-GO"
}
```

**No code in this document runs Sionna RT; no DEV3 field is opened; none of the old failing artifacts are modified.**
