# ROLE_IMPLEMENTER — 코드·데이터·재현 책임

**Start contract**: `role=IMPLEMENTER`, `contract_id=MBVAR-INFO-001`, full `governance_git_sha`, `base_git_sha`, `allowed_phase`, `output_root` mandatory. For `P0_PREFLIGHT`, supply `draft_contract_sha256` and scope strictly source/math/geometry audit; do not require frozen contract at this preflight. **For every S0/S1/R performance run**, full frozen `contract_sha256` and independent pre-run audit are mandatory. Missing fields: `BLOCKED_CONTRACT`.

## Required read order

Root `AGENTS.md`, common contract, this role file, frozen experiment contract and science spec, current phase config, source `ctl_core.py`/`reflect_model` and RT implementation, baseline manifests and input hashes.

## Phase P0: verify before building

- Read exact git sources at locked SHA, do not copy generated results from previous run as new.
- Explicit `h/nu/R/mu` data definitions and row alignment; normalizing `s` via signed first-path port powers; `r` calibration and units. Confirm `noise_var=None` for reference static RF or mark claim blocked.
- Baseline `MB_VAR` replay state + covariance numerical parity on at least previously published canary R4-B B0 and R5-A B0, including mask; do not merely compare rounded RMSE.
- Test repeat pose equality separately for raw `H`, `z`, `h`, `mu`, `eps`. Source packet µ may differ even at same pose; log distinct columns.
- Verify collision-free poses, antenna/anchor frames, nonholonomic yaw alignment; reject impossible pose lists.
- Source untracked dependencies, external LFS and model banks by sha256. Fail if mismatched.

## Phase S0/S1: deterministic tests & synth

- Tests MUST independently recompute two-measurement information ratios: for rho=.9 same-sign 0.52631578947 and opposite-sign 10.0 (tolerance <=1e-10).
- Generate a **single** pose-indexed GP field realization per field_id; repeated exact pose outputs identical spatial field value without resampling. Independent time OU and iid noises have separate RNG streams. Paired treatments share deterministic common random numbers or preserve explicit seed crosswalk.
- Use Σ = D_i C D_j [alpha_p k_pose + alpha_t k_time + alpha_w δ_ij], `alpha_p+alpha_t+alpha_w=1`. Validate symmetry, positive semidefiniteness and same diagonal marginal variance under correlation arms.
- Normalize s only by the frozen project observation extractor; never silently clamp out-of-domain s. Out-of-domain -> bad-realization record with count and predefined STOP rule.
- Define S0 fixed-matrix experiment **before** using FFD pose sequences; separate from S1 where H and Σ change together with pose.
- For stacked covariance, do not materialize/invert a huge dense 2N×2N matrix without memory budget; use matrix-free solve, structured kernels or small windows. Compare Cholesky vs independently coded analytical small cases.
- If noise is injected at z-level, label `synthetic_observation_noise`; do not assert it emulates full complex RF nonlinearity.

## Phase R: RT

- New scene IDs C00/C01/C10/C11; pin Sionna RT solver/version/frequency bins/pattern banks, ray depth, allowed mechanisms, material, thickness, deterministic seed and hardware.
- Paired `H_FULL`,`H_LOS` for each exact canonical `(scene_hash, anchor_id, x,y,z,yaw, mount_deg, rx/tx bank, f-grid, solver-config)` key. No interpolation of uncomputed poses.
- Direct-only `C00` checks: LOS path count, complex spectrum parity with reference LoS model and extracted `r,s` with **predeclared separate tolerances**; an arbitrary joint threshold cannot replace per-quantity QA.
- Plate manipulations: verify intended reflection exists, no unintended object/wall collisions, LoS visibility policy and path delays; report changed mean/variance/tap/power alongside spatial ACF. Do not attribute to correlation alone.
- No full RT job until canary QA and measured throughput in `RT_BUDGET_RECEIPT.json`; >approved cost -> `BLOCKED_BUDGET`.

## Phase scoring/run evidence

- Replay baseline and research estimator with shared pose, timestamps and synthetic/RT packet inputs. Fixed gate and self-gate run separately; refuse to present base-mask outcome as deployable system.
- Respect sensor seed independence: `rf_field_id`/`scene_variant_id` is primary, `sensor_seed` is repeated within RF realization.
- Write append-only per run: `MANIFEST.json`, `CONFIG_LOCK.json`, `INPUT_LOCK.sha256`, `POSE_LEDGER.parquet`, `RESULTS.csv`, `QA.json`, `LOG.txt`, `SEED_LEDGER.csv` and failure receipts. If a phase doesn't produce a field mark `NOT_APPLICABLE`, not blank.
- Full git SHA, branch, governance+contract SHA, independent scene counts, source+feature extractor SHA are mandatory. No output before parity tests succeed.

## Code review/quality

- Type/shape assertions for x (4), H (2×4), R (2×2), Σ (2N×2N or operator), radians vs degrees, metres vs cm; PSD and condition numbers, deterministic RNG; no unbounded dense inversion.
- Unit tests include repeated pose, yaw wrap, 0/2π equivalence, kappa=0 white, phi=0, masks, zero noise direct-only, n=1/no observations, and missing RF packet.
- Write mechanical test results separately from scientific evaluation; never mark independent audit `PASS` yourself.

## Done definition

Every report must state files created, files untouched, commands, environment, parity, hashes, results, failure cases, remaining risks, and next gate. A partial job is `INCOMPLETE`, never `PASS` because CI was green.
