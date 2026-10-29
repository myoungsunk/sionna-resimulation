# CI_REQUIREMENTS — expected future executable enforcement

Status: `DESIGN_ONLY`. This document does NOT claim there is an installed GitHub Actions enforcement workflow. Implementer must create real code + workflow, then run it, and an auditor must verify the checks fail on deliberately broken fixtures.

## Proposed executable paths (implement in dedicated scope)

- Workflow: `.github/workflows/mbvar-info-contract-check.yml`
- Validator: `research/DS_MASK_CAUSAL_X1_X2_20261026/MBVAR_CONTROLLED_INFO_20261029/scripts/validate_contract.py`
- Math tests: `.../tests/test_s0_math_contract.py`
- Pose/field tests: `.../tests/test_s1_field_contract.py`
- RF pipeline tests: `.../tests/test_rt_canary_contract.py`
- Phase manifest schema: `.../schemas/manifest.schema.json`

## CI triggers and enforcement

- On PR touching governance docs, root AGENTS router, MBVAR experiment contracts/config and controlled-info folder: lint docs and draft validity, scientific formatting, scope violation, and source lock.
- On `PHASE=P0_PREFLIGHT` require governance SHA and exact draft-contract hash; **only source/math/geometry evidence is allowed**. On merge/workflow_dispatch for `GATE=G2/G3/...` require FROZEN contract, proposer/auditor sign-off, governance SHA, contract_sha256, source SHA and phase-specific manifest. Reject placeholders, mutated source archives or outputs at protected paths.
- On new experiment run: store all output SHA256/manifest and upload artifacts even on failure. If an independent audit is missing, mark the run `TECHNICAL_QA_ONLY`, not `RESEARCH_RELEASE`.
- Explicit **negative fixtures** (intentionally failing) must be included: invalid sha, unregistered seed, train/test overlap, wrong `D^{-1} I D^{-1}`, non-PSD covariance, pose same but resampled spatial draw, fake direct=reflective equivalence, missing output hash, run with changed governance SHA.

## Exact checks and error codes

| Machine check | PASS condition | Failure code |
|---|---|---|
| `CHECK_ROLE_ROUTING` | role + contract ID + governance SHA, all read/acknowledged in run config | `ERR_ROLE_ROUTING` |
| `CHECK_FROZEN_CONTRACT` | DRAFT hash only for P0_PREFLIGHT; FROZEN and SHA stable for S0/S1/R | `ERR_CONTRACT_DRAFT` |
| `CHECK_SOURCE_LOCK` | full pin and hashes match materialized source | `ERR_SOURCE_HASH` |
| `CHECK_PROTECTED_PATHS` | no writes to root raw/frozen/release/archives or previous evidence | `ERR_PROTECTED_WRITE` |
| `CHECK_SPLIT_LEAK` | train/dev/test scene variant IDs disjoint, field ID properly scoped | `ERR_SPLIT_LEAK` |
| `CHECK_S0_ANALYTIC` | info ratios 0.5263157894736842/10 at rho=.9, abs tolerance 1e−10 | `ERR_S0_MATH` |
| `CHECK_S0_DYNAMIC` | independent batch Q-aware posterior matches small-case direct solution | `ERR_S0_Q` |
| `CHECK_S1_KERNEL` | PSD/symmetry/unit marginal, same pose same spatial draw | `ERR_S1_COV` |
| `CHECK_OBSERVATION_DOMAIN` | signed s range/finite r and tap/LOS status handled; no silent clamp | `ERR_S_DOMAIN` |
| `CHECK_BASELINE_PARITY` | R4-B B0 and R5-A B0 full state and covariance parity pinned | `ERR_PARITY` |
| `CHECK_RT_HASH` | exact canonical pose key + H_FULL/H_DIRECT source/hash, fixed physics config | `ERR_RT_DATA` |
| `CHECK_RT_COST` | canary runtime+GPU receipts and approved cap | `ERR_RT_BUDGET` |
| `CHECK_STAT_UNIT` | track S field_id, track R scene variant within family; packet/anchor not iid | `ERR_STAT_GRAIN` |
| `CHECK_OUTPUT_MANIFEST` | sources/config/output hashes, UTC, commands, seed ledger, failures | `ERR_MANIFEST` |
| `CHECK_AUDITOR_LINK` | separate audit report and source refs present for research release | `ERR_AUDIT_PENDING` |

## Required CLI and exit behavior

Proposed contract:

- `python scripts/validate_contract.py --contract contracts/EXPERIMENT_CONTRACT_MBVAR-INFO-001.md --mode draft`: validate structure and report placeholders, exit 0 if draft coherently states it is **not frozen**; does not unlock experiments.
- `python scripts/validate_contract.py --contract ... --mode frozen --phase G2 --manifest <path>`: exit 0 only if complete and matched; code 1 on validation errors; error log includes machine code and failed field. Full source SHA and governance SHA checked.
- `python -m pytest -q tests/test_s0_math_contract.py`: pass independent analytic math before Track S1.
- `python -m pytest -q tests/test_s1_field_contract.py`: pass GP/OU/pose tests before Track R.

Do not silently coerce unsupported mode; do not use success of the draft validator to run expensive RF.

## Governance review workflow

- Proposer submits contract in `DRAFT` with resolution ledger, no run claims.
- Auditor verifies math and freeze requirements before implementer starts P0/science runs.
- Implementer submits small PR of tests/manifest first, and incremental phase PRs (P0, S0, S1, R-canary, R-pilot, independent holdout).
- Every phase has separately linked CI mechanical PASS and auditor verdict. Re-running the same file after changing run outcomes does not count as independent preregistration.
