# COMMON_CONTRACT — MBVAR-INFO research governance

Contract scope: `MBVAR-INFO-*` experimental work in `research/DS_MASK_CAUSAL_X1_X2_20261026/MBVAR_CONTROLLED_INFO_20261029/`. This is an extension, **not** a replacement for root AGENTS.md.

## I. Authority and freeze

- A task must include `role`, `contract_id`, `base_git_sha` (40 hex), `governance_git_sha` (40 hex), `experiment_contract_sha256` (64 hex), `intended_scope`, `input_lock_sha256`, `output_root`.
- `DRAFT` contracts are not preregistrations. **Only `P0_PREFLIGHT` math/source/geometry audit** is permitted in a draft after governance SHA is locked; it uses and records `draft_contract_sha256`. All other scientific or RT runs require `FROZEN` proposer+auditor sign-off. `P0_TO_RESOLVE` items that depend on a physical canary may be frozen by a separate phase-specific signed amendment **before** P3. Never call preflight “preregistered experimental success.”
- If a protocol change is necessary after the freeze, create `AMENDMENT-XXX.md` describing original rule, new rule, reason, affected runs, whether a result was seen before change. Affected runs become `EXPLORATORY`; no silent retroactive edit.
- Same governing SHA applies to proposer, implementer, and auditor. Different SHAs are allowed only via explicit amended contract references.
- Prior studies are classified retrospectively; do not relabel as “preregistered” or “independently audited” after the fact.

## II. Scientific estimands and units

- Mechanism: how spatial and temporal correlation interacts with observation Jacobian to change **state-specific information**, followed by impact on uncertainty calibration and Heading/XY accuracy.
- Distinguish `raw_channel_H`, `z_r_m`, `z_s_dimensionless`, `h_LOS`, `mu`, `epsilon_truth`, `innovation_prior`, `state_error`. The reference RF scene is static unless explicitly changed; sensor noise and pose-dependent deterministic error are different components.
- `s` signed port-power ratio in [-1,1]. `r` in meters. Heading in radians internally; degrees in reports. Position in meters internally; RMSE in cm explicitly. Index and anchor directions must match existing baseline.
- New poses cannot inherit packet-keyed `mu_M` from old traces. Track S primary uses `mu=0`; new Track R estimates any mean/R on calibration scenes only and freezes before held-out scene evaluation.
- No test truth, labels, scene parameters, or oracle covariance in a deployable filter. Oracle allowed in synthetic scoring/reference with conspicuous `ORACLE_ONLY` label.

## III. Independence / leakage

- Track S independent sampling unit is `field_realization_id`. Track R is `scene_variant_id`, clustered within `scene_family`; anchor, trajectory, and sensor-seed are repeated observations in the same scene.
- Same RT scene with different anchor or path is **not** an independent RF realization; independent sensors on fixed RF also are not independent RF draws.
- Train/dev/test are split by **scene variant**, with final holdout variants generated from immutable seed lists after freeze and never evaluated for tuning. Previously analyzed Corridor/Office runs are retrospective only.
- Any covariance learned from Track R is `fitted`, not exact; low-sample covariance inversion requires regularization and an independent test. Full stacked empirical covariance from 10 scenes may be singular and must not be inverted unregularized.

## IV. Pipeline gates

| Gate | Required artifact | Failure condition |
|---|---|---|
| G0 | governance SHA + DRAFT contract hash + P0-only audit scope | missing SHA/role or P0 scope violation |
| G1 | P0 preflight parity + source/geometry/math tests; freeze science contract afterward | state/cov mismatch, dimension/PSD or motion failure; protocol not frozen before S0 |
| G2 | Track S0 exact algebra and oracle batch posterior | analytic vs numeric mismatch or unlogged intervention |
| G3 | Track S1 field sampler and paired Monte Carlo | repeat-pose mismatch, covariance PSD/invariant/marginal checks fail |
| G4 | Track R direct-only canary | RF/FFD parity, path classification, or numerical reproducibility fail |
| G5 | controlled reflection RT paired comparison | scene/pose/anchor config mismatch or unreported co-changing RF factors |
| G6 | reserved independent test, reviewer analysis, claim ledger | leakage, cherry-picked run, reviewer `REVISION_REQUIRED` |

- Result status: `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`; never silently drop an invalid seed. Scientific verdict is a separate `SUPPORTED`, `MIXED`, `NOT_SUPPORTED`, `INCONCLUSIVE`.
- A failure must preserve data/log/manifest and stop the dependent downstream gate. Other independent tracks can proceed if clearly separated.

## V. Computational/reproducibility contract

- Old files under `data/raw`, `results/frozen`, `reports/release`, archives and evidence bundles remain immutable. New paths only; no repo cleanup.
- Each result has `MANIFEST.json` with timestamp UTC, full git & governance SHAs, config snapshot + SHA256, input and output hashes, seed ledger, train/test manifest, command, package versions, hardware, solver config, observation extractor code SHA, result status.
- Every table row records `run_id, scene_family, scene_variant, anchor_id, trajectory_id, rf_field_id, sensor_seed, gate_mode, arm, t_window, role_of_truth` as applicable. Report count of *independent* scenes, not just number of packets.
- Equality/near-equality testing uses **fixed tolerances written before run**, not output-dependent tolerances. Numeric math oracle tolerances distinct from RF physics/solver tolerances.
- Unexpected first-path changes, no LoS, nonphysical `s`, invalid geometry, unstable inverse: **log and stop/stratify**, never silently clamp/impute/discard.

## VI. Meaningful reviewer separation

- Proposer controls estimand/design and freezes the contract; cannot assert post-hoc observed improvements as preregistered hypotheses.
- Implementer writes code, runs tests, and reports parity but **cannot issue the independent scientific verdict**.
- Auditor checks with a separate scratch calculation and uses source artifacts, not the implementer's narrative alone. Record auditor identity/session and which code/helpers are shared; if same agent/session, label `SELF_REVIEW_ONLY`.
- CI checks mechanics; reviewer evaluates causal attribution, physical assumptions, nonidentifiability and claims independently.
